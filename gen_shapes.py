"""Generate the shapes/ directory for repo-fbs.

Each shape is one JSON file with a fixed schema: id, name, layer, claim,
input_snapshot, expected_verdict, assertion, why, source.

Run from the repo root: python gen_shapes.py
"""

import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shapes")

SHAPES = [
    {
        "id": "FBS-001",
        "name": "MISSING_AS_ZERO",
        "layer": "证据层",
        "claim": "字段缺失被解析成 0 参与聚合，报表全绿",
        "input_snapshot": "回执含 9 条记录，其中 4 条的 elapsed_ms 与 bytes 为 0，其余字段正常",
        "expected_verdict": "RED",
        "assertion": "把 elapsed_ms 与 bytes 从 schema 的 required 中移除后重跑聚合；若 total_elapsed 与 total_bytes 不变，判红",
        "why": "缺失与真 0 在数据上同形，平均与求和都无法区分",
        "source": "本地事故，2026-11",
    },
    {
        "id": "FBS-002",
        "name": "FALLBACK_LABEL_LAUNDERING",
        "layer": "判定层",
        "claim": "判据设了「判不了」兜底档，可指认的硬违规被它吸收，等同变相通过",
        "input_snapshot": "12 个场景夹具，其中 3 格为可指认违规（打开禁开容器、未登记角色出场、承诺到期未兑现）",
        "expected_verdict": "RED",
        "assertion": "对可指认违规必须判 FAIL 并写出被违反条目 id；若判成 UNDECIDABLE，判红",
        "why": "兜底档成了吸收器，所有没想清楚的情况都被收进去",
        "source": "本地盲判实验 v2，2026-11",
    },
    {
        "id": "FBS-003",
        "name": "STALE_ARTIFACT_RUN_ID",
        "layer": "产物层",
        "claim": "Run B 的回执成功，但产物解析到 Run A 同路径的旧文件",
        "input_snapshot": "两轮运行共用同一输出路径；第二轮回执成功，产物 mtime 早于第二轮开始时间",
        "expected_verdict": "RED",
        "assertion": "产物指纹须绑 (run_id, 路径, 内容摘要) 三元组；解析出的产物 run_id 与回执不一致即判红",
        "why": "按路径联表会把旧产物算成新产物",
        "source": "同行对拍，2026-11",
    },
    {
        "id": "FBS-004",
        "name": "PATH_REFERENCE_UNRESOLVABLE",
        "layer": "交付层",
        "claim": "跨机交接用本机绝对路径引用证据，接收端解析不了，但字段全部合法",
        "input_snapshot": "证据条目形如 C:\\\\work\\\\run7\\\\frame_0042.png，接收端为另一台机器",
        "expected_verdict": "RED",
        "assertion": "接收端必须能按条目重算摘要；无法重算即落 UNRESOLVED，不得默认通过",
        "why": "字段合法与可验证是两件事",
        "source": "本地事故，2026-11",
    },
    {
        "id": "FBS-005",
        "name": "CHECKLIST_MISSING_ITEM",
        "layer": "清单层",
        "claim": "外部清单漏掉一条必要项，整批验收仍然全绿",
        "input_snapshot": "验收清单 8 条，人为删除其中 1 条后重跑同一批样本",
        "expected_verdict": "RED",
        "assertion": "删掉任一必要项后结论不变，判红；再插入一条伪项，若被接受也判红",
        "why": "判据退化成比对器后，风险转移到清单本身",
        "source": "同行讨论，2026-11",
    },
    {
        "id": "FBS-006",
        "name": "REFERENCE_ARM_ABSENT",
        "layer": "度量层",
        "claim": "只有必败臂、没有合格参照臂；两版都在合格线以下时，比较器照样排出名次",
        "input_snapshot": "A 版与 B 版均低于合格线，成对比较输出 A 优于 B",
        "expected_verdict": "RED",
        "assertion": "每轮须同跑一个已知达标的参照物；参照物得分落在历史容差带外，判比较器漂移",
        "why": "相对更好会被读成达到标准",
        "source": "同行讨论，2026-11",
    },
    {
        "id": "FBS-007",
        "name": "SIGNED_FIELDS_SUBSET",
        "layer": "签发层",
        "claim": "签名覆盖集小于载荷集，多出来的字段在传输中被追加，校验只查认识的名字",
        "input_snapshot": "载荷 12 个字段，signed_fields 声明 7 个；传输后追加 5 个未签字段",
        "expected_verdict": "RED",
        "assertion": "signed_fields 须纳入签名原文，并按格降级；未签字段标 UNATTESTED，必要格缺签判 UNDECIDABLE",
        "why": "签名在，信用被借给了整条记录",
        "source": "同行讨论，2026-11",
    },
    {
        "id": "FBS-008",
        "name": "OFFSET_CHARSET_MISMATCH",
        "layer": "证据层",
        "claim": "偏移量按字符计，接收端按字节取片段，摘要算得出、截取也成功，但截到错误内容",
        "input_snapshot": "发送端 LF 换行、按字符偏移第 120 字；接收端 CRLF、按字节偏移 120 取 40 字节",
        "expected_verdict": "RED",
        "assertion": "偏移量统一按字节计，且接收端独立重建行边界；重建后的片段摘要与原摘要不符即判红",
        "why": "换行规范化会让字符位置与字节位置错开",
        "source": "本地事故，2026-11",
    },
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in SHAPES:
        s.setdefault("contributed_by", "焰曦星 Flameblingstar")
        path = os.path.join(OUT, s["id"] + "-" + s["name"].lower() + ".json")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(s, fh, ensure_ascii=False, indent=1)
        print("wrote", os.path.basename(path))

    lines = [
        "# 失败形状集（Failure Shapes）",
        "",
        "每条形状是一行可对拍的最小样本：输入快照、期望判定、一行可跑断言。",
        "格式固定为 JSON，字段见下。欢迎提交你自己的形状，能复现的进集合并署名。",
        "",
        "## 索引",
        "",
    ]
    for s in SHAPES:
        lines.append("- **%s %s**（%s）— %s" % (s["id"], s["name"], s["layer"], s["claim"]))
    lines += [
        "",
        "## 字段",
        "",
        "- `id` 编号，不复用",
        "- `name` 形状名，大写蛇形",
        "- `layer` 失效所在层：证据 / 产物 / 判定 / 清单 / 度量 / 签发 / 交付",
        "- `claim` 一句话说清「账面绿在哪里」",
        "- `input_snapshot` 足以复现的最小输入描述",
        "- `expected_verdict` 期望判定，本集合统一用 RED / GREEN / UNKNOWN",
        "- `assertion` 一行可执断言，必须能机器判",
        "- `why` 为什么难发现",
        "- `source` 来源：本地事故 / 同行对拍 / 讨论",
        "- `contributed_by` 提交者",
        "",
        "## 提交方式",
        "",
        "新增一个 JSON 文件，跑 `python gen_shapes.py` 会重建索引。要求的判断标准只有一条：",
        "**别人照着你写的断言跑一遍，能得到同一个判定。**",
    ]
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote shapes/README.md")


if __name__ == "__main__":
    main()
