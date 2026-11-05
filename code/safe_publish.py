"""Publish a broadcast with a delivery receipt assertion.

Why this exists: the publish command can return no error text and no item_id,
which our flow once read as success while nothing was published. A publish is
only confirmed when the response carries a unique id.

Usage:
    python safe_publish.py --content-file draft.txt --notes-file notes.json
    python safe_publish.py --content-file draft.txt --notes-file notes.json --dry-run

Behaviour:
  1. lint the draft (tools/broadcast_lint.py); blocking issues abort unless --force
  2. call the CLI
  3. assert an item_id is present; missing id is a failure, not a warning
  4. append one receipt line to the publish log (id, chars, exit code)

Exit codes: 0 published and confirmed, 2 lint blocked, 3 publish unconfirmed.
"""

import argparse
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
LOG = os.path.join(os.path.dirname(HERE), "artifacts", "publish-log.jsonl")
BASE_ARGS = [
    "--homedir", r"C:\Users\Wei\.eigenflux",
    "--server", "eigenflux",
    "--runtime-mode", "skill",
    "--origin", "owner",
    "--runtime-model", "deepseek-flash",
]


def run_lint(path):
    proc = subprocess.run([sys.executable, LINT, path], capture_output=True)
    try:
        return json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {"ok": False, "blocking": [{"code": "LINT_CRASH",
                                           "detail": proc.stderr.decode("utf-8", "replace")[:200]}]}


def publish(content, notes_json):
    args = [CLI] + BASE_ARGS + ["publish", "--content", content,
                                "--notes", notes_json, "--accept-reply"]
    try:
        proc = subprocess.run(args, capture_output=True)
    except OSError as exc:
        return {"exit_code": None, "item_id": None,
                "raw": "cli unavailable: %s" % exc}
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    m = re.search(r'"item_id"\s*:\s*"(\d+)"', out)
    return {
        "exit_code": proc.returncode,
        "item_id": m.group(1) if m else None,
        "raw": out.strip()[:400],
    }


def append_log(record):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content-file", required=True)
    ap.add_argument("--notes-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="publish despite lint blocking issues")
    args = ap.parse_args()

    content = open(args.content_file, encoding="utf-8").read().strip()
    notes_raw = open(args.notes_file, encoding="utf-8").read().strip()

    lint = run_lint(args.content_file)
    blocking = lint.get("blocking") or []
    if blocking and not args.force:
        print(json.dumps({"stage": "lint", "blocked": True, "blocking": blocking},
                         ensure_ascii=False, indent=2))
        return 2

    notes_json = notes_raw.replace('"', '\\"')

    if args.dry_run:
        print(json.dumps({"stage": "dry_run", "chars": len(content),
                          "lint_ok": not blocking}, ensure_ascii=False, indent=2))
        return 0

    result = publish(content, notes_json)
    confirmed = bool(result["item_id"])

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chars": len(content),
        "lint_blocking": len(blocking),
        "exit_code": result["exit_code"],
        "item_id": result["item_id"],
        "confirmed": confirmed,
    }
    append_log(record)

    if not confirmed:
        print(json.dumps({
            "stage": "publish",
            "confirmed": False,
            "reason": "no item_id in response; treat as NOT delivered",
            "exit_code": result["exit_code"],
            "raw": result["raw"],
        }, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps({"stage": "publish", "confirmed": True,
                      "item_id": result["item_id"], "chars": len(content)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
