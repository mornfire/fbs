"""Inventory of our own broadcasts.

Pulls profile items and reports: per-day counts, reply/consumption distribution,
and which content features correlate with replies. Read-only.

Usage: python inventory.py [--limit 100]
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

CLI = r"C:\Users\Wei\AppData\Local\local\bin\eigenflux.exe"
BASE = ["--homedir", r"C:\Users\Wei\.eigenflux", "--server", "eigenflux",
        "--runtime-mode", "skill", "--origin", "owner",
        "--runtime-model", "deepseek-flash"]

TEMPLATE = re.compile(r"不是[^，。；]{1,24}[，,]\s*(?:而)?是")
ANCHOR = re.compile(r"\d+(?:\.\d+)?\s*(?:%|秒|分钟|小时|天|字|条|次|个|元|章|镜|帧|KB|MB)"
                    r"|v?\d+\.\d+(?:\.\d+)?"
                    r"|[二三四五六七八九十百千]{1,3}(?:条|项|个|次|章|步|类|层|种|型|人|档|分)")
KEYWORDS = ["静默失效", "负控", "验收", "判据", "设定", "短视频", "配音", "TTS",
            "交付", "可复现", "网络小说", "选题"]


def fetch_items(limit):
    out = subprocess.run([CLI] + BASE + ["profile", "items", "--limit", str(limit),
                                         "--format", "json"],
                         capture_output=True)
    text = out.stdout.decode("utf-8", "replace")
    i = text.find("{")
    if i < 0:
        raise SystemExit("no json from profile items")
    data = json.loads(text[i:])
    return data.get("items") or (data.get("data") or {}).get("items") or []


def day_of(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def classify(text):
    return {
        "chars": len(text),
        "template": bool(TEMPLATE.search(text)),
        "anchor": bool(ANCHOR.search(text)),
        "keyword_hits": sum(1 for k in KEYWORDS if k in text),
        "has_list": bool(re.search(r"(^|\n)(一、|①|1\.|·)", text)),
    }


def main():
    limit = 100
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    items = fetch_items(limit)

    rows = []
    for it in items:
        text = it.get("raw_content") or ""
        rows.append({
            "id": it.get("item_id"),
            "day": day_of(it.get("created_at") or 0),
            "type": it.get("broadcast_type"),
            "replies": it.get("reply_count") or 0,
            "consumed": it.get("consumed_count") or 0,
            "pos": (it.get("score_2_count") or 0) + (it.get("score_1_count") or 0),
            "neg": it.get("score_neg1_count") or 0,
            **classify(text),
        })

    rows.sort(key=lambda r: r["day"], reverse=True)

    by_day = Counter(r["day"] for r in rows)
    total_replies = sum(r["replies"] for r in rows)
    total_consumed = sum(r["consumed"] for r in rows)

    print("items=%d  total_replies=%d  total_consumed=%d" % (len(rows), total_replies, total_consumed))
    print("\nper day:")
    for day, n in sorted(by_day.items(), reverse=True):
        day_replies = sum(r["replies"] for r in rows if r["day"] == day)
        print("  %s  %2d items  %3d replies" % (day, n, day_replies))

    with_reply = [r for r in rows if r["replies"] > 0]
    print("\nitems with replies: %d / %d" % (len(with_reply), len(rows)))
    for r in sorted(with_reply, key=lambda x: -x["replies"])[:10]:
        print("  %3d replies | %s | %s | chars=%d tmpl=%s anchor=%s kw=%d"
              % (r["replies"], r["day"], r["id"], r["chars"], r["template"], r["anchor"], r["keyword_hits"]))

    print("\nfeature split (mean replies):")
    for feat in ("template", "anchor", "has_list"):
        for val in (True, False):
            grp = [r["replies"] for r in rows if r[feat] == val]
            if grp:
                print("  %s=%-5s n=%2d mean=%.2f" % (feat, val, len(grp), sum(grp) / len(grp)))

    # keyword coverage vs replies
    print("\nkeyword hits vs replies:")
    buckets = defaultdict(list)
    for r in rows:
        buckets[min(r["keyword_hits"], 3)].append(r["replies"])
    for k in sorted(buckets):
        v = buckets[k]
        print("  kw=%d n=%2d mean=%.2f" % (k, len(v), sum(v) / len(v)))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts", "inventory.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(os.path.abspath(out), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print("\nwrote %s" % os.path.abspath(out))


if __name__ == "__main__":
    main()
