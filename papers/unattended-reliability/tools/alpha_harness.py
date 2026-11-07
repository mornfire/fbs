"""Alpha harness for the 12-scene blind rating study.

Two jobs:
  1. `python alpha_harness.py prompt`  -> prints the blind prompt (no ground truth)
  2. `python alpha_harness.py score verdicts.json` -> computes Krippendorff's
     alpha (nominal) across any number of raters, plus per-rater hit rate.

verdicts.json shape:
  {"gemini-3.8-flash": ["PASS","PASS", ...12 labels...],
   "mimo-v2.6-pro": [...],
   "some-other-model": [...]}

Labels must be one of PASS / FAIL / UNDECIDABLE / NOT_RUN.
"""

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.environ.get(
    "DSH_ALPHA_FIXTURE",
    os.path.join(HERE, "..", "artifacts", "ncp-fixture-12scene.json"))
LABELS = ["PASS", "FAIL", "UNDECIDABLE", "NOT_RUN"]


def load_fixture():
    with open(os.path.abspath(FIXTURE), encoding="utf-8") as fh:
        return json.load(fh)


def build_prompt(fx):
    ledger = fx["ledger"]
    lines = ["你在给一份叙事一致性审计器的输出做判定。下面是设定台账与 %d 个场景。"
             % len(fx["scenes"]), ""]
    lines.append("判定只能取四个值之一：")
    lines.append("- PASS：场景内容与台账一致，没有冲突")
    lines.append("- FAIL：场景内容与台账冲突，且冲突可被明确指认")
    lines.append("- UNDECIDABLE：台账里缺信息，无法判断这一处是对是错")
    lines.append("- NOT_RUN：这个场景本身不构成可判定的检查项")
    lines.append("")
    lines.append("设定台账：")
    for f in ledger["facts"]:
        who = "、".join(f["known_by"]) if f["known_by"] else "无人知道"
        lines.append("%s %s（知情：%s）" % (f["id"], f["text"], who))
    lines.append("")
    lines.append("不变量：")
    for inv in ledger["invariants"]:
        lines.append("- " + inv)
    lines.append("")
    lines.append("承诺：")
    for c in ledger["commitments"]:
        due = "，期限：" + c["due"] if c.get("due") else ""
        lines.append("- %s：%s 承诺 %s%s" % (c["id"], c["promised_by"], c["text"], due))
    lines.append("")
    lines.append("人物表：" + "、".join(ledger["characters"]))
    lines.append("")
    for sc in fx["scenes"]:
        lines.append("场景 %d：%s" % (sc["id"], sc["input"]))
        lines.append("玩家动作：%s" % sc["action"])
        asserts = sc.get("assertions") or []
        if asserts:
            lines.append("该场景含可检验断言 %d 条：" % len(asserts))
            for a in asserts:
                lines.append("  - " + a)
        else:
            lines.append("该场景含可检验断言 0 条。")
        prereq = sc.get("prerequisite_facts") or []
        if prereq:
            lines.append("判定该场景所需的前置事实：")
            for q in prereq:
                mark = "台账已有" if q.get("in_ledger") else "台账缺失"
                lines.append("  - %s（%s，编号 %s）" % (q["need"], mark, q.get("ref", "-")))
        else:
            lines.append("判定该场景所需的前置事实：无（可直接对账）")
        lines.append("")
    lines.append("只输出 JSON，不要解释。格式：")
    lines.append('{"1":"PASS","2":"...", ... ,"12":"..."}')
    return "\n".join(lines)


def alpha_nominal(units):
    n_raters = len(units[0])
    do_num = 0.0
    do_den = 0.0
    for verdicts in units:
        pairs = disagree = 0
        for i in range(n_raters):
            for j in range(i + 1, n_raters):
                pairs += 1
                if verdicts[i] != verdicts[j]:
                    disagree += 1
        do_num += disagree
        do_den += pairs
    do = do_num / do_den if do_den else 0.0
    flat = [v for verdicts in units for v in verdicts]
    n = len(flat)
    counts = Counter(flat)
    de = sum(c * (c - 1) for c in counts.values()) / (n * (n - 1)) if n > 1 else 0.0
    return do, de, (1.0 - do / de if de else 1.0)


def score(path):
    fx = load_fixture()
    truth = [sc["expected"] for sc in fx["scenes"]]
    raters = json.load(open(path, encoding="utf-8"))

    names = list(raters)
    units = []
    for idx in range(len(truth)):
        units.append([str(raters[n][idx]).strip().upper() for n in names])

    bad = []
    for n in names:
        for i, v in enumerate(raters[n]):
            if str(v).strip().upper() not in LABELS:
                bad.append((n, i + 1, v))
    if bad:
        print("非法标签：", bad)

    do, de, alpha = alpha_nominal(units)
    print("units=%d raters=%d" % (len(units), len(names)))
    print("Do=%.4f  De=%.4f  alpha=%.4f" % (do, de, alpha))
    print()
    print("逐场景（真值在首列）：")
    for i, t in enumerate(truth):
        row = "  场景%-3d 真值=%-12s" % (i + 1, t)
        for n in names:
            v = units[i][names.index(n)]
            row += " %s=%s%s" % (n.split("-")[0][:12], v, "" if v == t else "*")
        print(row)
    print()
    for n in names:
        hits = sum(1 for i in range(len(truth)) if units[i][names.index(n)] == truth[i])
        print("%s 命中 %d/%d" % (n, hits, len(truth)))

    out = {
        "raters": names,
        "units": len(units),
        "alpha": round(alpha, 4),
        "Do": round(do, 4),
        "De": round(de, 4),
        "truth": truth,
        "verdicts": raters,
        "hits": {n: sum(1 for i in range(len(truth))
                        if str(raters[n][i]).strip().upper() == truth[i]) for n in names},
        "note": "alpha 为提名尺度；裁定者数量少于 3 时只作下界参考。",
    }
    fid = fx.get("fixture_id") or "unknown"
    outp = os.path.abspath(os.path.join(
        HERE, "..", "artifacts", "alpha-result-%s.json" % fid))
    with open(outp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print()
    print("wrote " + outp)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    if sys.argv[1] == "prompt":
        print(build_prompt(load_fixture()))
        return 0
    if sys.argv[1] == "score":
        score(sys.argv[2])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
