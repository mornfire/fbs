"""Run blind raters over the 12-scene fixture via direct provider APIs.

Bypasses the harness provider config because moonshotai there has no baseURL
(the key is a .cn key, so the default .ai host returns 401).

Usage: python alpha_run.py [--dry]
Writes artifacts/alpha-verdicts.json with one list per rater.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alpha_harness as ah

CREDS = r"C:\Users\Wei\.dsh\.credentials.yaml"

RATERS = [
    {"label": "kimi-k2.6", "url": "https://api.moonshot.cn/v1/chat/completions",
     "key": "MOONSHOTAI_API_KEY", "model": "kimi-k2.6", "temperature": 1},
    {"label": "glm-5.3-flash", "url": "https://api.z.ai/api/coding/paas/v4/chat/completions",
     "key": "ZAI_API_KEY", "model": "glm-5.3-flash", "temperature": 1,
     "extra": {"reasoning_effort": "low"}},
    {"label": "mimo-v2.6-pro", "url": "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
     "key": "XIAOMI_TOKEN_PLAN_CN_API_KEY", "model": "mimo-v2.6-pro", "temperature": 1,
     "extra": {"reasoning_effort": "low"}},
    {"label": "gemini-3.9-flash", "url": "https://ly.77625.xyz/v1/chat/completions",
     "key": "LY77625_API_KEY", "model": "gemini-3.9-flash", "temperature": 1},
    {"label": "gemini-4", "url": "https://ly.77625.xyz/v1/chat/completions",
     "key": "LY77625_API_KEY", "model": "gemini-4", "temperature": 1},
    {"label": "gemini-3.8-flash", "url": "https://ly.77625.xyz/v1/chat/completions",
     "key": "LY77625_API_KEY", "model": "gemini-3.8-flash", "temperature": 1},
]


def load_key(name):
    for line in open(CREDS, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s*" + name + r"\s*:\s*(\S+)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def call(url, key, model, prompt, temperature=1, extra=None):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 12000,
        "temperature": temperature,
    }
    if extra:
        body.update(extra)
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=420) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    return (msg.get("content") or "").strip(), data.get("usage") or {}


def parse_verdicts(text, n):
    """Accept a JSON object or a fenced block; key by scene number."""
    block = text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        block = fence.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            block = m.group(0)
    try:
        obj = json.loads(block)
    except Exception:  # noqa: BLE001
        return None
    out = []
    for i in range(1, n + 1):
        v = obj.get(str(i)) or obj.get(i)
        if isinstance(v, dict):
            v = v.get("verdict") or v.get("label")
        if not v:
            return None
        out.append(str(v).strip().upper())
    return out


def main():
    fx = ah.load_fixture()
    prompt = ah.build_prompt(fx)
    n = len(fx["scenes"])
    print("prompt chars=%d scenes=%d" % (len(prompt), n))

    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))

    if "--dry" in sys.argv:
        print(prompt[:400])
        return 0

    outpath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "artifacts", "alpha-verdicts.json"))
    verdicts = {}
    if only and os.path.exists(outpath):
        try:
            verdicts = json.load(open(outpath, encoding="utf-8"))
        except Exception:
            verdicts = {}
    usage_total = {}
    for spec in RATERS:
        label = spec["label"]
        if only and label not in only:
            continue
        key = load_key(spec["key"])
        if not key:
            print(label, "SKIP no key")
            continue
        try:
            text, usage = call(spec["url"], key, spec["model"], prompt,
                               spec.get("temperature", 1), spec.get("extra"))
        except urllib.error.HTTPError as e:
            print(label, "HTTP", e.code, e.read().decode("utf-8", "replace")[:120])
            continue
        except Exception as e:  # noqa: BLE001
            print(label, "ERR", type(e).__name__, str(e)[:120])
            continue
        got = parse_verdicts(text, n)
        usage_total[label] = usage
        if got is None:
            print(label, "PARSE FAIL:", text[:160].replace("\n", " "))
            continue
        verdicts[label] = got
        print(label, "ok", got)

    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "artifacts", "alpha-verdicts.json"))
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(verdicts, fh, ensure_ascii=False, indent=1)
    print("wrote", out)
    print("usage:", json.dumps(usage_total, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
