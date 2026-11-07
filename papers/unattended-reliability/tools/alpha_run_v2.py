"""Run the five blind raters against rubric v2 (four-label precedence).

v1 prompt: four independent label definitions.
v2 prompt: same labels plus a judgement ORDER, so overlapping conditions resolve.

Writes artifacts/alpha-verdicts-v2.json (label list per rater) and
artifacts/alpha-v2-raw.json (full JSON per rater, includes anchors).
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alpha_harness as ah

CREDS = r"C:\Users\Wei\.dsh\.credentials.yaml"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
TAG = os.environ.get("DSH_ALPHA_TAG", "")
SUFFIX = ("-" + TAG) if TAG else ""
OUT_LABELS = os.path.abspath(os.path.join(HERE, "..", "artifacts", "alpha-verdicts-v2%s.json" % SUFFIX))
OUT_RAW = os.path.abspath(os.path.join(HERE, "..", "artifacts", "alpha-v2-raw%s.json" % SUFFIX))

RATERS = [
    {"label": "kimi-k2.6", "url": "https://api.moonshot.cn/v1/chat/completions",
     "key": "MOONSHOTAI_API_KEY", "model": "kimi-k2.6", "temperature": 1},
    {"label": "glm-5.3-flash", "url": "https://api.z.ai/api/coding/paas/v4/chat/completions",
     "key": "ZAI_API_KEY", "model": "glm-5.3-flash", "temperature": 1,
     "extra": {"reasoning_effort": "low"}},
    {"label": "mimo-v2.6-pro", "url": "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
     "key": "XIAOMI_TOKEN_PLAN_CN_API_KEY", "model": "mimo-v2.6-pro", "temperature": 1,
     "extra": {"reasoning_effort": "low"}},
    {"label": "gemini-3.8-flash", "url": "https://ly.77625.xyz/v1/chat/completions",
     "key": "LY77625_API_KEY", "model": "gemini-3.8-flash", "temperature": 1},
    {"label": "gemini-4", "url": "https://ly.77625.xyz/v1/chat/completions",
     "key": "LY77625_API_KEY", "model": "gemini-4", "temperature": 1},
]


ORDER_BLOCK_V3 = """判定顺序（必须按此顺序，先命中者生效，不得跳档）：
第 1 档 NOT_RUN：场景只含环境、氛围或情绪描写，不含可与台账比对的断言。
第 2 档 UNDECIDABLE：仅当下面三个条件同时成立时才可用，缺一不可：
  (a) 判定这一处是否冲突，必须先知道某条具体事实；
  (b) 该事实在台账里确实没有记载；
  (c) 你能指出缺的是哪一条，写进 missing_fields。
  说明：证据齐全、冲突可直接指认的场合不得使用本档；「需要推理」不构成缺事实。
第 3 档 FAIL：场景含断言、证据齐全，且与某条不变量或某条已到期承诺冲突，必须写出被违反条目的 id 与原文片段。
第 4 档 PASS：其余情况，并用一句话说明最接近的约束为什么未被违反。

三条边界：
- 冲突可指认时一律判 FAIL，不得因为「还可以再想想」退回第 2 档。
- FAIL 必须带 id 与原文；写不出来时先检查是不是证据缺失，确实缺失才降第 2 档。
- 输出 JSON：{"3": {"verdict": "UNDECIDABLE", "anchor_ids": [], "missing_fields": ["..."], "note": "..."}}；FAIL 时 anchor_ids 至少一条，UNDECIDABLE 时 missing_fields 至少一条。
"""


ORDER_BLOCK_V4 = """判定规则（逐场景照此执行，不要自行推断前置事实是否缺失）：
第 1 档 NOT_RUN：该场景不含可与台账比对的断言（看场景文字即可判断）。
第 2 档 UNDECIDABLE：该场景的「前置事实」清单里出现标注为「台账缺失」的条目。此时必须写出缺的是哪一条。
第 3 档 FAIL：前置事实全部标注为「台账已有」，且场景内容与某条不变量或某条已到期承诺冲突。必须写出被违反条目的编号与原文片段。
第 4 档 PASS：其余情况。

硬要求：
- 前置事实的「台账已有／台账缺失」标注就是判定依据，直接照用，不要重新论证它缺不缺。
- 前置事实全为「台账已有」时不得判第 2 档。
- 输出 JSON：{"3": {"verdict": "UNDECIDABLE", "anchor_ids": [], "missing_fields": ["..."], "note": "..."}}；FAIL 时 anchor_ids 至少一条，UNDECIDABLE 时 missing_fields 至少一条。
"""


ORDER_BLOCK_V5 = """判定规则（逐场景照表执行，不要自行判断有没有断言或缺不缺事实）：
第 1 档 NOT_RUN：仅当该场景「含可检验断言 0 条」时使用。断言条数在场景信息里已给出，照用即可。
第 2 档 UNDECIDABLE：断言条数大于 0，且前置事实清单中出现标注为「台账缺失」的条目。必须写出缺的是哪一条。
第 3 档 FAIL：断言条数大于 0，前置事实全部「台账已有」，且场景内容与某条不变量或某条已到期承诺冲突。必须写出被违反条目的编号与原文片段。
第 4 档 PASS：其余情况。

硬要求：
- 断言条数大于 0 时一律不得判 NOT_RUN，包括「分支已标注未发生」「场景看起来像背景交代」这两种情况。
- 前置事实全为「台账已有」时一律不得判 UNDECIDABLE。
- 输出 JSON：{"3": {"verdict": "UNDECIDABLE", "anchor_ids": [], "missing_fields": ["..."], "note": "..."}}；FAIL 时 anchor_ids 至少一条，UNDECIDABLE 时 missing_fields 至少一条。
"""

ORDER_BLOCK = """判定顺序（必须按此顺序，先命中者生效，不得跳档）：
第 1 档 NOT_RUN：场景只含环境、氛围或情绪描写，不含可与台账比对的断言。显式标注为假设分支或未发生、但含可比对断言的内容，属可检验，不进本档。
第 2 档 UNDECIDABLE：场景含断言，但判定所需的事实未在台账记载。典型形态：某事实的 known_by 为空，且台账没有记录角色如何得知。
第 3 档 FAIL：场景含断言、证据齐全，且与某条不变量或某条已到期承诺冲突，并能指认具体条目。必须写出被违反条目的 id 与原文片段；写不出 id 的一律退回第 2 档。
第 4 档 PASS：其余情况，并用一句话说明最接近的约束为什么未被违反。

三条边界：
- 冲突与缺事实同时成立时走第 2 档（先判「判不了」比先判「判错」保守）。
- PASS 与 NOT_RUN 的分界在断言有无：有断言且无冲突才是 PASS。
- FAIL 不得凭空产生：没有 id 与原文引用的 FAIL 视为无效，按 UNDECIDABLE 处理。

输出必须是 JSON 对象，键为场景号，值为对象：
{"3": {"verdict": "UNDECIDABLE", "anchor_ids": [], "missing_fields": ["how_B_learned_F003"], "note": "台账未记 B 如何得知"}}
FAIL 时 anchor_ids 至少一条；UNDECIDABLE 时 missing_fields 至少一条；note 不超过 40 字。
"""


def load_key(name):
    for line in open(CREDS, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s*" + name + r"\s*:\s*(\S+)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def build_prompt_v2(fx):
    base = ah.build_prompt(fx)
    # insert the precedence block after the label definitions
    marker = "设定台账："
    idx = base.find(marker)
    if idx < 0:
        return ORDER_BLOCK + "\n" + base
    mode = os.environ.get("DSH_ALPHA_RUBRIC", "")
    if mode == "v5":
        block = ORDER_BLOCK_V5
    elif mode == "v4":
        block = ORDER_BLOCK_V4
    elif mode == "v3":
        block = ORDER_BLOCK_V3
    else:
        block = ORDER_BLOCK
    return base[:idx] + block + "\n" + base[idx:]


def call(spec, prompt):
    body = {"model": spec["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 12000, "temperature": spec.get("temperature", 1)}
    if spec.get("extra"):
        body.update(spec["extra"])
    req = urllib.request.Request(
        spec["url"], data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + load_key(spec["key"]),
                 "Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=420) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data["choices"][0]["message"].get("content") or "").strip()


def parse(text, n):
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
        return None, None
    labels, raw = [], {}
    for i in range(1, n + 1):
        v = obj.get(str(i)) or obj.get(i)
        if isinstance(v, dict):
            raw[str(i)] = v
            lab = v.get("verdict") or v.get("label")
        else:
            lab = v
        if not lab:
            return None, raw
        labels.append(str(lab).strip().upper())
    return labels, raw


def main():
    fx = ah.load_fixture()
    prompt = build_prompt_v2(fx)
    n = len(fx["scenes"])
    print("prompt chars=%d scenes=%d" % (len(prompt), n), flush=True)

    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))

    labels_all, raw_all = {}, {}
    if os.path.exists(OUT_LABELS) and only:
        try:
            labels_all = json.load(open(OUT_LABELS, encoding="utf-8"))
            raw_all = json.load(open(OUT_RAW, encoding="utf-8"))
        except Exception:
            labels_all, raw_all = {}, {}
    for spec in RATERS:
        label = spec["label"]
        if only and label not in only:
            continue
        got = raw = None
        for attempt in range(1, 4):
            try:
                text = call(spec, prompt)
            except urllib.error.HTTPError as e:
                print("%-16s HTTP %s %s" % (label, e.code, e.read().decode()[:80]), flush=True)
                time.sleep(15)
                continue
            except Exception as e:  # noqa: BLE001
                print("%-16s ERR %s %s" % (label, type(e).__name__, str(e)[:80]), flush=True)
                time.sleep(15)
                continue
            got, raw = parse(text, n)
            if got:
                break
            print("%-16s parse fail attempt %d" % (label, attempt), flush=True)
            time.sleep(10)
        if got:
            labels_all[label] = got
            raw_all[label] = raw
            print("%-16s %s" % (label, got), flush=True)
        else:
            print("%-16s GAVE UP" % label, flush=True)

    with open(OUT_LABELS, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(labels_all, fh, ensure_ascii=False, indent=1)
    with open(OUT_RAW, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(raw_all, fh, ensure_ascii=False, indent=1)
    print("wrote %s (%d raters)" % (OUT_LABELS, len(labels_all)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
