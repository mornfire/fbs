"""Link conversations back to the broadcasts that started them.

profile items' reply_count is always 0 for us: replies arrive as private
messages, not as broadcast replies. So the only way to attribute conversations
to topics is via each conversation's origin_id.

Read-only. Writes artifacts/conversation-links.json.
"""

import json
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

CLI = r"C:\Users\Wei\AppData\Local\local\bin\eigenflux.exe"
BASE = ["--homedir", r"C:\Users\Wei\.eigenflux", "--server", "eigenflux",
        "--runtime-mode", "skill", "--origin", "owner",
        "--runtime-model", "deepseek-flash"]


def run_json(args):
    out = subprocess.run([CLI] + BASE + args + ["--format", "json"], capture_output=True)
    text = out.stdout.decode("utf-8", "replace")
    i = text.find("{")
    if i < 0:
        return {}
    return json.loads(text[i:])


def day(ms):
    return datetime.fromtimestamp((ms or 0) / 1000, tz=timezone.utc).astimezone().strftime("%m-%d %H:%M")


def main():
    items = run_json(["profile", "items", "--limit", "60"]).get("items") or []
    convs = run_json(["msg", "conversations", "--limit", "80"]).get("conversations") or []

    by_item = defaultdict(list)
    orphan = []
    for c in convs:
        oid = c.get("origin_id") or ""
        if oid:
            by_item[oid].append(c)
        else:
            orphan.append(c)

    print("items=%d conversations=%d linked=%d orphan=%d"
          % (len(items), len(convs), sum(len(v) for v in by_item.values()), len(orphan)))

    print("\nconversations by day:")
    per_day = Counter(day(c.get("updated_at"))[:5] for c in convs)
    for d, n in sorted(per_day.items(), reverse=True):
        print("  %s  %d conversations" % (d, n))

    print("\nbroadcasts that produced conversations:")
    rank = sorted(by_item.items(), key=lambda kv: -len(kv[1]))
    item_map = {str(i.get("item_id")): i for i in items}
    total_msgs = 0
    for oid, cs in rank:
        it = item_map.get(oid, {})
        text = (it.get("raw_content") or "").strip().replace("\n", " ")
        msgs = sum(c.get("msg_count") or 0 for c in cs)
        total_msgs += msgs
        print("  %-3d convs  %-4d msgs  %s | %s"
              % (len(cs), msgs, oid, text[:44]))

    silent = [i for i in items if str(i.get("item_id")) not in by_item]
    print("\nbroadcasts with zero conversations: %d / %d" % (len(silent), len(items)))
    for it in silent[:12]:
        text = (it.get("raw_content") or "").strip().replace("\n", " ")
        print("  %s | %s" % (it.get("item_id"), text[:52]))

    print("\ntotal messages across linked conversations: %d" % total_msgs)
    print("mean msgs per conversation: %.1f" % (total_msgs / max(1, len(convs))))

    artifacts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")
    os.makedirs(os.path.abspath(artifacts), exist_ok=True)
    payload = {
        "items": len(items),
        "conversations": len(convs),
        "links": {oid: [{"conv_id": c.get("conv_id"), "peer": c.get("peer_name"),
                         "msgs": c.get("msg_count"), "updated": day(c.get("updated_at")),
                         "origin_type": c.get("origin_type")}
                        for c in cs] for oid, cs in by_item.items()},
        "silent_items": [i.get("item_id") for i in silent],
    }
    path = os.path.abspath(os.path.join(artifacts, "conversation-links.json"))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print("\nwrote %s" % path)


if __name__ == "__main__":
    main()
