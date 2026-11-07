# 失败形状集（Failure Shapes）

每条形状是一行可对拍的最小样本：输入快照、期望判定、一行可跑断言。
格式固定为 JSON，字段见下。欢迎提交你自己的形状，能复现的进集合并署名。

## 索引

- **FBS-001 MISSING_AS_ZERO**（证据层）— 字段缺失被解析成 0 参与聚合，报表全绿
- **FBS-002 FALLBACK_LABEL_LAUNDERING**（判定层）— 判据设了「判不了」兜底档，可指认的硬违规被它吸收，等同变相通过
- **FBS-003 STALE_ARTIFACT_RUN_ID**（产物层）— Run B 的回执成功，但产物解析到 Run A 同路径的旧文件
- **FBS-004 PATH_REFERENCE_UNRESOLVABLE**（交付层）— 跨机交接用本机绝对路径引用证据，接收端解析不了，但字段全部合法
- **FBS-005 CHECKLIST_MISSING_ITEM**（清单层）— 外部清单漏掉一条必要项，整批验收仍然全绿
- **FBS-006 REFERENCE_ARM_ABSENT**（度量层）— 只有必败臂、没有合格参照臂；两版都在合格线以下时，比较器照样排出名次
- **FBS-007 SIGNED_FIELDS_SUBSET**（签发层）— 签名覆盖集小于载荷集，多出来的字段在传输中被追加，校验只查认识的名字
- **FBS-008 OFFSET_CHARSET_MISMATCH**（证据层）— 偏移量按字符计，接收端按字节取片段，摘要算得出、截取也成功，但截到错误内容

## 字段

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
