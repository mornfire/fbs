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
    (r"[二三四五六七八九十百千]{1,3}(?:条|项|个|次|章|步|类|层|种|型|人|档|分)", "数量(中文)"),
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


def split_sentences(text):
    return [s.strip() for s in re.split(r"[。！？\n]", text) if s.strip()]


def classify_template_findings(text):
    """Split template hits into two classes, per 录事's suggestion.

    rule_defect   - the template's neighbourhood carries an anchor, so the claim
                    may be concrete and the flag is a rule's fault.
    rhetoric      - no anchor anywhere near the template; nothing verifiable.

    The neighbourhood is the sentence plus its immediate neighbours: an anchor in
    the next sentence usually still supports the claim being made.
    """
    defects, rhetoric = [], []
    sents = split_sentences(text)
    for idx, sent in enumerate(sents):
        hits = find_templates(sent)
        if not hits:
            continue
        window = " ".join(sents[max(0, idx - 1): idx + 2])
        has_anchor = bool(find_anchors(window))
        record = {"sentence": sent[:80], "hits": [h["text"] for h in hits]}
        if has_anchor:
            defects.append(record)
        else:
            rhetoric.append(record)
    return defects, rhetoric


STALE_DAYS = 180


def stale_anchors(text, now=None):
    """Date anchors that are old enough to have expired as evidence."""
    import datetime
    today = now or datetime.date.today()
    out = []
    for m in re.finditer(r"(20\d{2})[-/年](\d{1,2})", text):
        year, month = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12):
            continue
        try:
            anchor_date = datetime.date(year, month, 1)
        except ValueError:
            continue
        age = (today - anchor_date).days
        if age > STALE_DAYS:
            out.append({"anchor": m.group(0), "age_days": age})
    return out


def anchor_coverage(text):
    """Share of text left after removing every anchor.

    Suggested by Hermes as a replacement for blacklisting sentence patterns:
    a blacklist expires the moment the writer changes phrasing, but the ratio of
    anchor-free text is a metric. Higher ratio = more of the text carries no
    verifiable content.
    """
    cleaned = QUOTED.sub(lambda m: m.group(0), text)
    spans = []
    for pattern, _label in ANCHORS:
        for m in re.finditer(pattern, cleaned):
            spans.append((m.start(), m.end()))
    if not spans:
        return 1.0, 0
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    anchored_chars = sum(e - s for s, e in merged)
    body = re.sub(r"[\s，。、！？；：,.!?;:\"'“”‘’（）()【】\[\]]", "", text)
    if not body:
        return 1.0, len(merged)
    left = max(0, len(body) - anchored_chars)
    return left / float(len(body)), len(merged)


def sentence_count(text):
    return len([s for s in re.split(r"[。！？\n]", text) if s.strip()])


def opening_keywords(text, keywords, window=120):
    head = text[:window]
    return [k for k in keywords if k in head]


def lint(text, summary=None, keywords=None):
    issues = []
    warnings = []

    templates = find_templates(text)
    defects, rhetoric = classify_template_findings(text)

    # Blocking only when the sentence carrying the template has nothing behind it.
    if rhetoric:
        issues.append({
            "code": "RHETORIC_NO_ANCHOR",
            "detail": "%d 处修辞模板所在的句子没有任何锚点：%s" % (
                len(rhetoric), "；".join(r["sentence"][:40] for r in rhetoric[:2])),
            "advice": "把对偶拿掉，这半句里补一个可验证的东西；补不出就降级成假设或删掉。",
        })

    # A template in a sentence that does carry an anchor is likely a rule defect,
    # not empty rhetoric — warn rather than block.
    if defects:
        warnings.append({
            "code": "TEMPLATE_WITH_ANCHOR",
            "detail": "%d 处模板所在句子其实带锚点（疑似规则缺陷，非空话）：%s" % (
                len(defects), "；".join(r["sentence"][:40] for r in defects[:2])),
            "advice": "这类不该按空话处理，改句式即可，不必删内容。",
        })

    stale = stale_anchors(text)
    if stale:
        warnings.append({
            "code": "STALE_ANCHOR",
            "detail": "日期锚点已超过 %d 天：%s" % (
                STALE_DAYS, "、".join("%s（%d 天前）" % (s["anchor"], s["age_days"]) for s in stale[:3])),
            "advice": "时效类锚点会过期。若是引用当时的数据，写明「截至某时」；否则换一个新读数。",
        })

    anchors = find_anchors(text)
    unanchored, anchor_spans = anchor_coverage(text)
    if not anchors:
        issues.append({
            "code": "NO_ANCHOR",
            "detail": "全文没有可识别的数量、版本、日期、编号或引用片段。",
            "advice": "补一个只属于这条的锚（哪台机器、什么版本、什么参数下得出的）。缺锚的结论只能写成假设。",
        })
    elif unanchored > 0.85:
        warnings.append({
            "code": "LOW_ANCHOR_DENSITY",
            "detail": "删掉锚点后仍剩 %.0f%% 的字，共 %d 处锚点——锚点太少，正文很可能仍是修辞为主。" % (
                unanchored * 100, anchor_spans),
            "advice": "不是加一个数字就够。让锚点分布在几个关键判断上，而不是集中在开头一句。",
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
            "template_rhetoric": len(rhetoric),
            "template_with_anchor": len(defects),
            "stale_anchors": len(stale),
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
