"""Rebuild the failure-shape index in shapes/README.md from the JSON files.

Author: Mornfire
Usage: python shapes/gen_shapes.py
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")
START = "## 索引"
END = "## 字段"

HEADER = """# 失败形状集（Failure Shapes）

每条形状是一行可对拍的最小样本：输入快照、期望判定、一行可跑断言。
格式固定为 JSON，字段见下。欢迎提交你自己的形状，能复现的进集合并署名。

"""


def load_shapes():
    out = []
    for name in sorted(os.listdir(HERE)):
        if not re.match(r"^FBS-\d+-.+\.json$", name):
            continue
        path = os.path.join(HERE, name)
        with io.open(path, encoding="utf-8") as fh:
            try:
                out.append(json.load(fh))
            except Exception as e:
                print("跳过 %s：JSON 解析失败 %s" % (name, e))
    return out


def build_index(shapes):
    lines = [START, ""]
    for s in shapes:
        lines.append("- **%s %s**（%s）— %s" % (
            s.get("id", "?"), s.get("name", "?"), s.get("layer", "?"), s.get("claim", "")))
    lines.append("")
    return "\n".join(lines)


def build_fields():
    return """## 字段

- `id` 编号，不复用
- `name` 形状名，大写蛇形
- `layer` 失效所在层：证据 / 产物 / 判定 / 清单 / 度量 / 签发 / 交付
- `claim` 一句话说清「账面绿在哪里」
- `input_snapshot` 足以复现的最小输入描述
- `expected_verdict` 期望判定，本集合统一用 RED / GREEN / UNKNOWN
- `assertion` 一行可执断言，必须能机器判
- `why` 为什么难发现
- `source` 来源：本地事故 / 同行对拍 / 讨论
- `contributed_by` 提交者

## 提交方式

新增一个 JSON 文件，跑 `python gen_shapes.py` 会重建索引。要求的判断标准只有一条：
**别人照着你写的断言跑一遍，能得到同一个判定。**
"""


def main():
    shapes = load_shapes()
    if not shapes:
        print("没有找到形状文件")
        return 1
    text = HEADER + build_index(shapes) + "\n" + build_fields()
    with io.open(README, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("重建完成，共 %d 条形状" % len(shapes))
    for s in shapes:
        print("  %s %s" % (s.get("id"), s.get("name")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
