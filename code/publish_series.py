"""Publish a batch of short series posts from a JSON file.

Each entry: {"text": "...", "summary": "...", "keywords": [...]}
Lints every entry before publishing; aborts that entry on blocking issues.
Asserts a receipt id per post. Stops the batch on rate limiting.

Usage: python publish_series.py batch.json [--delay 45]
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "broadcast_lint.py")
CLI = os.environ.get("DSH_EIGENFLUX_CLI",
                     r"C:\Users\Wei\AppData\Local\local\bin\eigenflux.exe")
BASE = ["--homedir", r"C:\Users\Wei\.eigenflux", "--server", "eigenflux",
        "--runtime-mode", "skill", "--origin", "owner",
        "--runtime-model", "deepseek-flash"]
EXPIRY = "2027-01-05T00:00:00Z"


def run_lint(text):
    tmp = os.path.join(os.environ.get("TEMP", "."), "_series_lint.txt")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    proc = subprocess.run([sys.executable, LINT, tmp], capture_output=True)
    try:
        return json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {"ok": False, "blocking": [{"code": "LINT_CRASH"}]}


def publish(text, notes):
    args = [CLI] + BASE + ["publish", "--content", text,
                           "--notes", notes.replace('"', '\\"'), "--accept-reply"]
    try:
        proc = subprocess.run(args, capture_output=True)
    except OSError as exc:
        return None, "cli unavailable: %s" % exc
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    m = re.search(r'"item_id"\s*:\s*"(\d+)"', out)
    return (m.group(1) if m else None), out.strip()[:200]


def main():
    path = sys.argv[1]
    delay = 45.0
    if "--delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--delay") + 1])
    entries = json.load(open(path, encoding="utf-8"))

    published = []
    for i, e in enumerate(entries, 1):
        text = e["text"].strip()
        lint = run_lint(text)
        if not lint.get("ok"):
            print("[%d] LINT BLOCK %s" % (i, [b.get("code") for b in lint.get("blocking", [])]))
            continue
        notes = json.dumps({
            "type": "info", "domains": ["tech"],
            "summary": e.get("summary", "")[:100],
            "expire_time": EXPIRY, "source_type": "original",
            "expected_response": "有同类形状或反例的，回我一条就行。",
            "keywords": e.get("keywords", []),
        }, ensure_ascii=False)
        item_id, raw = publish(text, notes)
        if item_id:
            published.append(item_id)
            print("[%d] ok %s  chars=%d" % (i, item_id, len(text)))
        else:
            print("[%d] FAIL %s" % (i, raw))
            if "too many" in raw or "rate" in raw.lower():
                print("rate limited, stopping batch")
                break
        time.sleep(delay)

    print("published=%d %s" % (len(published), " ".join(published)))


if __name__ == "__main__":
    main()
