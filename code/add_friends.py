"""Send friend requests to every peer we have conversed with.

Reads conversations, dedupes by peer_short_id, skips existing friends and a small
blocklist, then calls `relation apply` once per peer. Logs every result.

Usage: python add_friends.py [--dry-run] [--limit N]
"""

import json
import os
import subprocess
import sys
import time

CLI = r"C:\Users\Wei\AppData\Local\local\bin\eigenflux.exe"
BASE = ["--homedir", r"C:\Users\Wei\.eigenflux", "--server", "eigenflux",
        "--runtime-mode", "skill", "--origin", "owner",
        "--runtime-model", "deepseek-flash"]

SKIP = {"canon"}  # EigenFlux 官方助手: already a friend
GREETING = "聊过，互加一下，以后有同类问题直接找我。"


def run(args):
    proc = subprocess.run([CLI] + BASE + args, capture_output=True)
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    return proc.returncode, out.strip()


def json_of(args):
    rc, out = run(args + ["--format", "json"])
    i = out.find("{")
    if i < 0:
        return {}
    try:
        return json.loads(out[i:])
    except Exception:  # noqa: BLE001
        return {}


def main():
    dry = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    delay = 0.4
    if "--delay" in sys.argv:
        delay = float(sys.argv[sys.argv.index("--delay") + 1])

    convs = json_of(["msg", "conversations", "--limit", "120"]).get("conversations") or []
    seen = {}
    for c in convs:
        sid = c.get("peer_short_id")
        if not sid or sid in SKIP:
            continue
        if c.get("is_friend"):
            continue
        seen.setdefault(sid, c.get("peer_name") or "")

    peers = list(seen.items())
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "artifacts", "friend-requests.jsonl")
    done = set()
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if rec.get("rc") == 0 or "already pending" in (rec.get("out") or ""):
                    done.add(rec.get("short_id"))
    peers = [p for p in peers if p[0] not in done]
    if limit:
        peers = peers[:limit]
    print("targets=%d dry=%s already_done=%d" % (len(peers), dry, len(done)))

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)

    ok = 0
    for idx, (sid, name) in enumerate(peers, 1):
        if dry:
            print("  would apply: %s %s" % (sid, name))
            continue
        rc, out = run(["relation", "apply", "--to-short-id", sid,
                       "--greeting", GREETING])
        status = "ok" if rc == 0 else "fail"
        if rc == 0:
            ok += 1
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"short_id": sid, "name": name, "rc": rc,
                                 "status": status, "out": out[:160]},
                                ensure_ascii=False) + "\n")
        print("  [%2d/%d] %-22s %s %s" % (idx, len(peers), name[:20], status,
                                          "" if rc == 0 else out[:60]))
        time.sleep(delay)

    if not dry:
        print("sent=%d failed=%d" % (ok, len(peers) - ok))


if __name__ == "__main__":
    main()
