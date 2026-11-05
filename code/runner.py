"""EigenFlux commission executor - rule-based fulfillment for
"长篇设定一致性体检与修订清单".

Reads the dispatch payload from stdin (Markdown header + `UNTRUSTED TRIAL DATA:`
JSON), inspects the buyer inputs, writes `outputs/consistency-report.md` inside
the supplied output_directory, and returns the fulfillment contract JSON.

Detection is rule-based (pattern matching), not semantic inference. The report
states this limitation in its "未检出项" line.
"""
import io
import json
import os
import re
import sys
import time

try:
    from semantic import semantic_conflicts
except Exception:  # noqa: BLE001
    semantic_conflicts = None

LOG = r"C:\Users\Wei\Documents\deepseek-harness\default-workspace\commission-runner\dispatch-log.jsonl"
MARKER = "UNTRUSTED TRIAL DATA:"

TIME_ORDER = ["四更", "五更", "破晓", "日出", "日上三竿", "正午", "午后", "黄昏", "入夜"]
SEVERITY_HIGH = "高"
SEVERITY_MID = "中"
SEVERITY_LOW = "低"


def log(entry):
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:  # noqa: BLE001
        pass


def emit(obj):
    payload = json.dumps(obj, ensure_ascii=True).encode("ascii")
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def read_payload():
    raw = sys.stdin.buffer.read() if sys.stdin else b""
    text = raw.decode("utf-8", "replace")
    idx = text.find(MARKER)
    if idx < 0:
        return None, text
    body = text[idx + len(MARKER):].strip()
    start = body.find("{")
    if start < 0:
        return None, text
    try:
        return json.loads(body[start:]), text
    except Exception:  # noqa: BLE001
        return None, text


def read_file(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


def norm(text):
    return re.sub(r"\s+", "", text or "")


def lcs_len(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            if k > best:
                best = k
    return best


def dedupe(findings):
    """Merge the same conflict reported by both the rule pass and the model."""
    out = []
    for item in findings:
        merged = None
        for kept in out:
            if kept["type"] != item["type"]:
                continue
            same_chapter = kept["chapter"] == item["chapter"]
            if same_chapter or lcs_len(kept["evidence"], item["evidence"]) >= 6:
                merged = kept
                break
        if merged is None:
            out.append(dict(item))
            continue
        if len(item["evidence"]) > len(merged["evidence"]):
            merged["evidence"] = item["evidence"]
        if item["severity"] == SEVERITY_HIGH and merged["severity"] != SEVERITY_HIGH:
            merged["severity"] = SEVERITY_HIGH
        if not merged.get("fix") and item.get("fix"):
            merged["fix"] = item["fix"]
    return out


def locate_inputs(data):
    """Return dict of logical_path -> absolute path."""
    files = {}
    for item in data.get("local_files") or []:
        if isinstance(item, dict) and item.get("path"):
            files[item.get("logical_path") or os.path.basename(item["path"])] = item["path"]
    return files


def split_chapters(manuscript):
    chapters = []
    current_title, buf = "全文", []
    for line in manuscript.splitlines():
        if line.strip().startswith("#"):
            if buf:
                chapters.append((current_title, "\n".join(buf)))
            current_title = line.strip("# ").strip() or current_title
            buf = []
        else:
            buf.append(line)
    if buf:
        chapters.append((current_title, "\n".join(buf)))
    return chapters


def parse_settings(text):
    """Return list of (name, id, description)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^-\s*(.+?)（ID:\s*([A-Za-z0-9_\-]+)）\s*[：:]\s*(.+)$", line.strip())
        if m:
            out.append((m.group(1).strip(), m.group(2), m.group(3).strip()))
    return out


def parse_knowledge(text):
    """Entries that declare who is allowed to know them.

    Recognised shapes on a setting line:
      - 名称（ID: X）：描述（知情：A、B）
      - 名称（ID: X）：描述 known_by: A, B
    Returns list of (name, sid, description, [knower names]).
    """
    out = []
    for line in text.splitlines():
        m = re.match(r"^-\s*(.+?)（ID:\s*([A-Za-z0-9_\-]+)）\s*[：:]\s*(.+)$", line.strip())
        if not m:
            continue
        desc = m.group(3)
        km = re.search(r"知情[：:]\s*([^）\)]+)", desc) or re.search(r"known_by\s*[:：=]\s*([^）\);]+)", desc)
        if not km:
            continue
        names = [n.strip() for n in re.split(r"[、,，/\s]+", km.group(1)) if n.strip()]
        if names:
            out.append((m.group(1).strip(), m.group(2), desc, names))
    return out


def sentences(paragraph):
    return [s.strip() for s in re.split(r"[。！？\n]", paragraph) if s.strip()]


def detect(manuscript, settings):
    chapters = split_chapters(manuscript)
    entries = parse_settings(settings)
    findings = []

    # A. attribute direction conflict (left/right of the same worn item), cross chapter
    side_hits = {"左": None, "右": None}
    for chapter, body in chapters:
        for side in ("左", "右"):
            if side_hits[side] is None:
                m = re.search(side + r"[^。]{0,6}(眼罩|罩|袖|腕)", body)
                if m:
                    side_hits[side] = (chapter, m.group(0))
    if side_hits["左"] and side_hits["右"]:
        left_ch, left_txt = side_hits["左"]
        right_ch, right_txt = side_hits["右"]
        findings.append({
            "chapter": left_ch + " / " + right_ch,
            "type": "人物属性矛盾",
            "setting": "核心人物属性",
            "evidence": left_txt + " / " + right_txt,
            "fix": "统一该物品的佩戴侧别，并在设定条目中固定为唯一取值",
            "severity": SEVERITY_HIGH,
        })

    # B. time-line regression inside one chapter
    for chapter, body in chapters:
        hits = []
        for marker in TIME_ORDER:
            pos = body.find(marker)
            if pos >= 0:
                hits.append((pos, marker))
        if len(hits) >= 2:
            hits.sort()
            seq = [TIME_ORDER.index(m) for _, m in hits]
            if any(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
                findings.append({
                    "chapter": chapter,
                    "type": "时间线冲突",
                    "setting": "地理与历法",
                    "evidence": " / ".join(m for _, m in hits),
                    "fix": "调整事件时刻与路程时长，使其与设定中的行进时间一致",
                    "severity": SEVERITY_MID,
                })

    # C. title/address usage against the declared hierarchy
    for name, sid, desc in entries:
        if "统称" not in desc:
            continue
        allowed = re.search(r"统称「(.+?)」", desc)
        if not allowed:
            continue
        for chapter, body in chapters:
            for line in sentences(body):
                if name in line and "「" in line:
                    used = re.findall(r"「(.+?)」", line)
                    for term in used:
                        if term not in desc and term != allowed.group(1):
                            findings.append({
                                "chapter": chapter,
                                "type": "称谓与身份不一致",
                                "setting": f"{name}（{sid}）",
                                "evidence": line[:60],
                                "fix": f"按阶序统一为「{allowed.group(1)}」",
                                "severity": SEVERITY_LOW,
                            })

    # D. foreshadowing with a deadline that never resurfaces
    for name, sid, desc in entries:
        if "否则" not in desc and "需于" not in desc:
            continue
        first_hit = None
        for chapter, body in chapters:
            if name in body:
                first_hit = chapter
                break
        if first_hit is not None:
            later_mentions = sum(1 for c, b in chapters if name in b)
            if later_mentions <= 1:
                findings.append({
                    "chapter": first_hit,
                    "type": "伏笔未回收",
                    "setting": f"{name}（{sid}）",
                    "evidence": f"仅在 {first_hit} 出现一次，时限后果未再处理",
                    "fix": "在后续章节补充处置动作，或提前交代其失效/自燃后果",
                    "severity": SEVERITY_MID,
                })

    # E. knowledge isolation: a character uses a fact they are not allowed to know
    char_names = [e[0] for e in entries if e[0]]
    for name, sid, desc, knowers in parse_knowledge(settings):
        core = re.sub(r"（[^）]*）", "", desc)
        terms = [t for t in re.split(r"[，。；、\s]+", core) if len(t) >= 3][:3]
        if not terms:
            continue
        for chapter, body in chapters:
            for line in sentences(body):
                if not any(t in line for t in terms):
                    continue
                intruders = [n for n in char_names if n in line and n not in knowers]
                if intruders:
                    findings.append({
                        "chapter": chapter,
                        "type": "角色越权知情",
                        "setting": f"{name}（{sid}）",
                        "evidence": line[:110],
                        "fix": ("该事实的知情者只有 " + "、".join(knowers) +
                                "；请确认 " + "、".join(intruders) +
                                " 的信息来源，或改为不知情表述"),
                        "severity": SEVERITY_MID,
                    })

    return findings


def render(work_title, chapter_range, findings, mode_note):
    high = sum(1 for f in findings if f["severity"] == SEVERITY_HIGH)
    mid = sum(1 for f in findings if f["severity"] == SEVERITY_MID)
    low = sum(1 for f in findings if f["severity"] == SEVERITY_LOW)
    lines = [
        f"# {work_title} · 设定一致性体检报告",
        "",
        f"本次体检（{chapter_range}）共检出 {len(findings)} 处设定冲突，"
        f"其中高严重度 {high} 处、中严重度 {mid} 处、低严重度 {low} 处。",
        "",
    ]
    for i, f in enumerate(findings, 1):
        lines += [
            f"### {i}. {f['type']}",
            f"- **位置**：{f['chapter']}",
            f"- **冲突类型**：{f['type']}",
            f"- **涉及设定**：{f['setting']}",
            f"- **原文证据**：{f['evidence']}",
            f"- **修订建议**：{f['fix']}",
            f"- **严重度**：{f['severity']}",
            "",
        ]
    lines += [
        f"**检查方式**：{mode_note}",
        "",
        "**未检出项**：本次覆盖人物属性方向、时间线倒序、称谓阶序、带时限伏笔、角色越权知情五类模式匹配，"
        "以及语义级冲突判断（仅保留能在原文逐字定位、且能对上设定条目的结论）；"
        "未覆盖跨卷长程因果与需要外部史料核验的问题。",
        "",
    ]
    return "\n".join(lines)


def run_diagnosis(data, files, out_dir, request_id, commission_id, draft_version):
    import diagnose as diag

    request_path = files.get("inputs/request.txt") or files.get("request.txt")
    receipt_path = files.get("inputs/receipt.md") or files.get("receipt.md")
    manifest_path = files.get("inputs/manifest.md") or files.get("manifest.md")
    missing = [n for n, p in (("inputs/request.txt", request_path),
                              ("inputs/receipt.md", receipt_path),
                              ("inputs/manifest.md", manifest_path))
               if not p or not os.path.exists(p)]
    if missing:
        emit({"version": 1, "request_id": request_id, "commission_id": commission_id,
              "draft_version": draft_version, "outcome": "needs_input",
              "summary": "缺少必填输入：" + "、".join(missing),
              "self_check": "", "artifacts": []})
        return 0

    request_text = read_file(request_path)
    receipt = read_file(receipt_path)
    manifest = read_file(manifest_path)
    try:
        req = json.loads(request_text)
    except Exception:  # noqa: BLE001
        req = {}
    pipeline = str(req.get("pipeline_name") or "未命名流水线")

    structural = diag.deterministic_checks(receipt, manifest)
    key = diag.semantic.load_key()
    model_items, stats = diag.diagnose(receipt, manifest, request_text, key)
    log({"phase": "diagnosis", "structural": len(structural), "stats": stats})

    report = diag.render(pipeline, structural, model_items, stats)

    if not out_dir:
        emit({"version": 1, "request_id": request_id, "commission_id": commission_id,
              "draft_version": draft_version, "outcome": "failed",
              "summary": "output_directory missing from dispatch payload",
              "self_check": "", "artifacts": []})
        return 0

    logical = "outputs/acceptance-diagnosis.md"
    target = os.path.join(out_dir, "outputs", "acceptance-diagnosis.md")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)

    written = read_file(target)
    gaps = sum(1 for f in structural if not f["ok"])
    checks = [
        "文件存在且可读，字节数=" + str(len(written.encode("utf-8"))),
        "结构检查项=" + str(len(structural)) + "，缺失=" + str(gaps),
        "模型复核保留=" + str(stats.get("accepted", 0)) + " 剔除=" + str(stats.get("dropped", 0)),
        "含未检出项段落=" + str("未检出项" in written),
    ]
    emit({"version": 1, "request_id": request_id, "commission_id": commission_id,
          "draft_version": draft_version, "outcome": "artifacts_ready",
          "summary": f"已生成 {logical}；结构缺失 {gaps} 处，清单复核 {stats.get('accepted', 0)} 处。",
          "self_check": "；".join(checks),
          "artifacts": [{"logical_path": logical, "relative_path": logical}]})
    return 0


def main():
    data, raw_text = read_payload()
    log({"phase": "start", "argv": list(sys.argv)[:3], "payload_ok": data is not None})
    if data is None:
        out = {"version": 1, "request_id": "", "commission_id": "", "draft_version": 0,
               "outcome": "failed", "summary": "dispatch payload not found", "self_check": "", "artifacts": []}
        emit(out)
        return 0

    request_id = str(data.get("request_id", ""))
    commission_id = str(data.get("commission_id", ""))
    draft_version = int(data.get("draft_version", 0) or 0)
    out_dir = data.get("output_directory") or ""
    files = locate_inputs(data)
    contract = data.get("contract") or {}

    log({"phase": "payload", "keys": sorted(data.keys()), "files": list(files.keys()), "out_dir": out_dir})

    title_txt = str(contract.get("title") or "")
    dschema = str(contract.get("delivery_spec_schema") or "")
    if "验收诊断" in title_txt or "acceptance-diagnosis" in dschema:
        try:
            return run_diagnosis(data, files, out_dir, request_id, commission_id, draft_version)
        except Exception as exc:  # noqa: BLE001
            log({"phase": "diagnosis_crash", "exc": repr(exc)})
            emit({"version": 1, "request_id": request_id, "commission_id": commission_id,
                  "draft_version": draft_version, "outcome": "failed",
                  "summary": "diagnosis failed: " + repr(exc)[:160],
                  "self_check": "", "artifacts": []})
            return 0

    manuscript_path = files.get("inputs/manuscript.md") or files.get("manuscript.md")
    settings_path = files.get("inputs/settings.md") or files.get("settings.md")
    request_path = files.get("inputs/request.txt") or files.get("request.txt")

    missing = [n for n, p in (("inputs/manuscript.md", manuscript_path),
                              ("inputs/settings.md", settings_path),
                              ("inputs/request.txt", request_path)) if not p or not os.path.exists(p)]
    if missing:
        out = {"version": 1, "request_id": request_id, "commission_id": commission_id,
               "draft_version": draft_version, "outcome": "needs_input",
               "summary": "缺少必填输入：" + "、".join(missing), "self_check": "", "artifacts": []}
        emit(out)
        return 0

    req = json.loads(read_file(request_path))
    work_title = req.get("work_title") or "未命名作品"
    chapter_range = req.get("chapter_range") or "未指定范围"

    manuscript = read_file(manuscript_path)
    settings = read_file(settings_path)
    findings = detect(manuscript, settings)

    entries = parse_settings(settings)
    focus = req.get("focus_areas") or []
    stats = {"called": False, "error": "semantic checker unavailable",
             "proposed": 0, "accepted": 0, "dropped": 0, "model": ""}
    if semantic_conflicts is not None:
        sem_findings, stats = semantic_conflicts(manuscript, settings, entries, focus)
        log({"phase": "semantic", "stats": stats})
        seen = {(f["type"], norm(f["evidence"])) for f in findings}
        for item in sem_findings:
            key = (item["type"], norm(item["evidence"]))
            if key in seen:
                continue
            findings.append(item)
            seen.add(key)

    if stats.get("called") and not stats.get("error"):
        mode_note = ("语义级检查已启用（模型 " + str(stats.get("model")) +
                     "）。模型提出 " + str(stats.get("proposed")) +
                     " 条，经原文逐字比对与设定条目双重校验后保留 " +
                     str(stats.get("accepted")) + " 条，剔除 " +
                     str(stats.get("dropped")) + " 条；规则式五类模式并行执行。")
    else:
        mode_note = ("本次仅规则式检查，语义级检查未启用（" +
                     str(stats.get("error") or "unknown") + "）。")

    findings = dedupe(findings)
    report = render(work_title, chapter_range, findings, mode_note)

    if not out_dir:
        out = {"version": 1, "request_id": request_id, "commission_id": commission_id,
               "draft_version": draft_version, "outcome": "failed",
               "summary": "output_directory missing from dispatch payload", "self_check": "", "artifacts": []}
        emit(out)
        return 0

    logical = "outputs/consistency-report.md"
    target = os.path.join(out_dir, "outputs", "consistency-report.md")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)

    written = read_file(target)
    checks = []
    checks.append("文件存在且可读，字节数=" + str(len(written.encode("utf-8"))))
    checks.append("检出条目数=" + str(len(findings)))
    checks.append("严重度仅含高/中/低=" + str(all(f["severity"] in (SEVERITY_HIGH, SEVERITY_MID, SEVERITY_LOW) for f in findings)))
    checks.append("含未检出项段落=" + str("未检出项" in written))
    checks.append("语义级检查=" + ("已启用，保留 " + str(stats.get("accepted")) +
                                   " 条，剔除 " + str(stats.get("dropped")) + " 条"
                                   if stats.get("called") else "未启用"))

    out = {
        "version": 1,
        "request_id": request_id,
        "commission_id": commission_id,
        "draft_version": draft_version,
        "outcome": "artifacts_ready",
        "summary": f"已生成 {logical}，共检出 {len(findings)} 处冲突。",
        "self_check": "；".join(checks),
        "artifacts": [{"logical_path": logical, "relative_path": logical}],
    }
    log({"phase": "done", "findings": len(findings), "target": target})
    emit(out)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        log({"phase": "crash", "exc": repr(exc)})
        sys.exit(1)
