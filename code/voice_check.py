"""Voice compression robustness check (real codec version).

The audio we generate and the audio the buyer finally hears are not the same
object: platforms re-encode on upload. This script encodes the source WAV through
real codecs at realistic bitrates, decodes back, re-transcribes with MiMo ASR,
and reports character error rate (CER) plus spectral band loss.

Limits stated up front:
  * Speaker similarity (SIM) is NOT measured here: no speaker-embedding model on
    this host. Content intelligibility and spectral drift only.
  * Bitrate profiles approximate platform paths. Thresholds for spectral loss are
    reported, not enforced, because the acceptable loss depends on the target
    platform.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import urllib.request
import wave

CREDENTIALS = os.environ.get("DSH_CREDENTIALS",
                           os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml"))
ENDPOINT = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
ASR_MODEL = "mimo-v2.5-asr"
KEY_NAME = "XIAOMI_TOKEN_PLAN_CN_API_KEY"

FFMPEG_CANDIDATES = [
    r"C:\Users\Wei\.zcode\workspace\default\_ffbin\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe",
    r"C:\Users\Wei\Documents\deepseek-harness\default-workspace\tools\bin\ffmpeg.exe",
]

# name -> (container extension, ffmpeg codec args)
PROFILES = {
    "mp3_64k": ("mp3", ["-c:a", "libmp3lame", "-b:a", "64k"]),
    "mp3_32k": ("mp3", ["-c:a", "libmp3lame", "-b:a", "32k"]),
    "aac_64k": ("m4a", ["-c:a", "aac", "-b:a", "64k"]),
    "opus_24k": ("ogg", ["-c:a", "libopus", "-b:a", "24k"]),
}


def find_ffmpeg():
    for path in FFMPEG_CANDIDATES:
        if os.path.exists(path):
            return path
    return shutil.which("ffmpeg")


def load_key():
    try:
        with open(CREDENTIALS, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"^\s*" + KEY_NAME + r"\s*:\s*(\S+)\s*$", line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        return None
    return None


def read_wav(path):
    with wave.open(path, "rb") as w:
        params = {"channels": w.getnchannels(), "sampwidth": w.getsampwidth(),
                  "framerate": w.getframerate(), "nframes": w.getnframes()}
        frames = w.readframes(w.getnframes())
    return params, frames


def encode_decode(ffmpeg, src_wav, workdir, name, ext, codec_args):
    """Encode to a lossy codec, then decode back to WAV. Returns decoded path."""
    enc_path = os.path.join(workdir, "enc-%s.%s" % (name, ext))
    dec_path = os.path.join(workdir, "dec-%s.wav" % name)
    enc = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src_wav] + codec_args + [enc_path],
        capture_output=True)
    if enc.returncode != 0:
        raise RuntimeError("encode failed: " + enc.stderr.decode("utf-8", "replace")[:200])
    dec = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", enc_path,
         "-c:a", "pcm_s16le", dec_path],
        capture_output=True)
    if dec.returncode != 0:
        raise RuntimeError("decode failed: " + dec.stderr.decode("utf-8", "replace")[:200])
    return dec_path, enc_path


def spectral_profile(path):
    import numpy as np
    params, frames = read_wav(path)
    dtype = np.int16 if params["sampwidth"] == 2 else np.int8
    x = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if params["channels"] > 1:
        x = x.reshape(-1, params["channels"]).mean(axis=1)
    n_fft, hop = 512, 256
    if len(x) < n_fft:
        return None
    windows = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop]
    spec = np.abs(np.fft.rfft(windows * np.hanning(n_fft), axis=1))
    mean_spec = spec.mean(axis=0) + 1e-9
    freqs = np.fft.rfftfreq(n_fft, 1.0 / params["framerate"])
    high = spec[:, freqs > 4000].sum() / (spec.sum() + 1e-9)
    return {"log_spec": np.log(mean_spec), "high_ratio": float(high)}


def spectral_drift(orig_path, deg_path):
    import numpy as np
    a = spectral_profile(orig_path)
    b = spectral_profile(deg_path)
    if not a or not b:
        return None
    denom = (np.linalg.norm(a["log_spec"]) * np.linalg.norm(b["log_spec"])) + 1e-9
    cos = float(np.dot(a["log_spec"], b["log_spec"]) / denom)
    return {"cosine": round(cos, 4), "drift": round(1.0 - cos, 4),
            "high_band_ratio_orig": round(a["high_ratio"], 4),
            "high_band_ratio_degraded": round(b["high_ratio"], 4)}


def transcribe(wav_path, key):
    raw = open(wav_path, "rb").read()
    body = {"model": ASR_MODEL, "messages": [{
        "role": "user",
        "content": [{"type": "input_audio",
                     "input_audio": {"data": base64.b64encode(raw).decode(),
                                     "format": "wav"}}]}]}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data["choices"][0]["message"].get("content") or "").strip()


def normalize(text):
    return re.sub(r"[\s，。、！？；：,.!?;:\"'“”‘’（）()【】\[\]]", "", text or "")


def cer(reference, hypothesis):
    a = normalize(reference)
    b = normalize(hypothesis)
    if not a:
        return 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1] / float(len(a))


def run(wav_path, expected_text, thresholds=None, workdir=None):
    th = thresholds or {"max_baseline_cer": 0.05,
                        "max_variant_cer": 0.15,
                        "max_cer_delta": 0.10}
    key = load_key()
    if not key:
        return {"ok": False, "error": "credential unavailable"}
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg not found"}

    workdir = workdir or os.path.dirname(os.path.abspath(wav_path))
    base_text = transcribe(wav_path, key)
    base_cer = cer(expected_text, base_text)

    results = []
    for name, (ext, args) in PROFILES.items():
        try:
            dec_path, enc_path = encode_decode(ffmpeg, wav_path, workdir, name, ext, args)
        except Exception as exc:  # noqa: BLE001
            results.append({"profile": name, "error": str(exc)[:160], "pass": False})
            continue
        text = transcribe(dec_path, key)
        c = cer(expected_text, text)
        drift = spectral_drift(wav_path, dec_path) or {}
        band_loss = None
        if drift.get("high_band_ratio_orig"):
            band_loss = round((drift["high_band_ratio_orig"] - drift["high_band_ratio_degraded"])
                              / drift["high_band_ratio_orig"], 4)
        content_ok = (c <= th["max_variant_cer"] and (c - base_cer) <= th["max_cer_delta"])
        results.append({
            "profile": name,
            "encoded_bytes": os.path.getsize(enc_path) if os.path.exists(enc_path) else None,
            "transcript": text,
            "cer": round(c, 4),
            "delta": round(c - base_cer, 4),
            "spectral_drift": drift.get("drift"),
            "high_band_loss": band_loss,
            "content_pass": content_ok,
            "pass": content_ok,
        })

    overall = base_cer <= th["max_baseline_cer"] and all(r.get("pass") for r in results)
    return {
        "ok": True,
        "ffmpeg": ffmpeg,
        "baseline": {"transcript": base_text, "cer": round(base_cer, 4)},
        "variants": results,
        "thresholds": th,
        "overall_pass": overall,
        "note": ("SIM 未测量（本机无说话人嵌入模型）。真实编解码压缩；"
                 "高频带损失仅报告不判定——可接受损耗取决于目标平台。"),
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(run(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2))
