"""Broadcast draft linter.

Built after Hermes' critique: our own broadcasts leaned on the "不是 X，是 Y"
construction, which reads like insight but is often rhetoric with no verifiable
half. Also checks the thing that actually matters for discoverability: whether
the draft carries an anchor (a number, version, date, or proper noun) that makes
it distinguishable from the rest of the batch.

Usage:
    python broadcast_lint.py draft.txt
    python broadcast_lint.py --text "..."

Exit code is 0 when no blocking issue is found, 1 otherwise. Blocking issues are
rhetorical templates and a missing anchor; the rest are warnings.
"""

import json
import re
import sys

# Rhetorical templates that read as insight but usually carry no claim.
TEMPLATES = [
    (r"不是[^，。；]{1,24}[，,]\s*(?:而)?是", "不是X，是Y 对偶"),
    (r"与其说[^，。；]{1,20}[，,]\s*不如说", "与其说X，不如说Y"),
    (r"真正的[^，。；]{1,12}[是在]", "真正的X是 断言型"),
    (r"[^，。；]{2,16}比[^，。；]{2,16}更重要", "A比B更重要 排序型"),
    (r"这才是", "这才是 强调型"),
    (r"说到底", "说到底 收束型"),
]

# Anchors: things that make a draft distinguishable from the batch.
ANCHORS = [
    (r"\d+(?:\.\d+)?\s*(?:%|秒|分钟|小时|天|字|条|次|个|GB|MB|KB|k|万|元|块|章|镜|帧)", "数量"),
    (r"[一二三四五六七八九十百千两]{1,3}(?:条|项|个|次|章|步|类|层|种|型|人|档)", "数量(中文)"),
    (r"v?\d+\.\d+(?:\.\d+)?", "版本号"),
    (r"20\d{2}[-/年]\d{1,2}", "日期"),
    (r"arXiv[:\s]*\d{4}\.\d{4,5}", "论文编号"),
    (r"[A-Za-z][A-Za-z0-9_]*(?:[-_.][A-Za-z0-9_]+)+", "标识符/命令"),
    (r"[A-Za-z]+\.(?:py|json|yaml|md|jsonl|mp4|wav)\b", "文件名"),
]


QUOTED = re.compile(r"「[^」]{0,120}」|“[^”]{0,120}”|\"[^\"]{0,120}\"")


def strip_quoted(text):
    """Blank out quoted spans so that citing a template is not using it."""
    return QUOTED.sub(lambda m: "□" * len(m.group(0)), text)


def find_templates(text):
    hits = []
    scan = strip_quoted(text)
    for pattern, label in TEMPLATES:
        for m in re.finditer(pattern, scan):
            hits.append({"kind": label, "text": m.group(0)})
    return hits


def find_anchors(text):
    hits = []
    for pattern, label in ANCHORS:
        for m in re.finditer(pattern, text):
            hits.append({"kind": label, "text": m.group(0)})
    return hits


def sentence_count(text):
    return len([s for s in re.split(r"[。！？\n]", text) if s.strip()])


def opening_keywords(text, keywords, window=120):
    head = text[:window]
    return [k for k in keywords if k in head]


def lint(text, summary=None, keywords=None):
    issues = []
    warnings = []

    templates = find_templates(text)
    if templates:
        issues.append({
            "code": "RHETORICAL_TEMPLATE",
            "detail": "命中 %d 处修辞模板：%s" % (
                len(templates), "；".join(t["text"] for t in templates[:3])),
            "advice": "把对偶拿掉，检查剩下那半句有没有可验证的东西；没有就降级成假设或删掉。",
        })

    anchors = find_anchors(text)
    if not anchors:
        issues.append({
            "code": "NO_ANCHOR",
            "detail": "全文没有可识别的数量、版本、日期、编号或引用片段。",
            "advice": "补一个只属于这条的锚（哪台机器、什么版本、什么参数下得出的）。缺锚的结论只能写成假设。",
        })

    if summary is not None:
        s_anchors = find_anchors(summary)
        if not s_anchors:
            issues.append({
                "code": "SUMMARY_NO_ANCHOR",
                "detail": "摘要里没有锚，同批多条时会与模板不可区分。",
                "advice": "摘要至少带一个专属信息（数字/版本/日期/专名）。",
            })

    if keywords:
        head = opening_keywords(text, keywords)
        if not head:
            warnings.append({
                "code": "KEYWORDS_NOT_IN_HEAD",
                "detail": "开头 120 字内没有出现任何关键词：%s" % "、".join(keywords),
                "advice": "检索可能只看片段，把两三个核心词自然放进开头。",
            })

    n = sentence_count(text)
    if n < 6:
        warnings.append({"code": "TOO_SHORT", "detail": "句子数 %d，可能展开不足。" % n})
    if len(text) > 900:
        warnings.append({"code": "TOO_LONG", "detail": "字数 %d，广播建议 400-700。" % len(text)})

    return {
        "ok": not issues,
        "blocking": issues,
        "warnings": warnings,
        "stats": {
            "chars": len(text),
            "sentences": n,
            "template_hits": len(templates),
            "anchor_hits": len(anchors),
            "anchors": [a["text"] for a in anchors[:8]],
        },
    }


def main(argv):
    if len(argv) > 1 and argv[1] == "--text":
        text = argv[2]
    elif len(argv) > 1:
        with open(argv[1], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    result = lint(text.strip())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
