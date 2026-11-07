# 无人值守验收中的判据设计

一份基于五版判据迭代的对照实验。数据、夹具、判决原始值、复现脚本都在本目录。

正文：[paper.md](paper.md)

---

## 一句话

无人值守系统最危险的输出是「全绿」。这份实验想回答：当验收器说「通过」，凭什么信它。

## 结论

判据应当退化为**比对器**：缺什么由外部清单说，模型只负责核对与引用。靠自然语言调松调紧，一致性与命中率此消彼长；把判断外置成清单后，两者首次同时改善。

## 目录

```
paper.md              正文（摘要 / 问题 / 方法 / 结果 / 讨论 / 局限 / 可复用结论）
fixtures/             两套夹具：12 场景原题，6 场景换世界观 hold-out
verdicts/             五个版本 × 多模型的盲判原始值（逐格标签）
results/              一致性 α 与命中率的计算结果
rubrics/              v2 判据文本、v4 设计说明
tools/                盲判运行器、α 计算器、早期探针脚本
```

## 复现

```
# 1) 看判据 v5 的盲判题面（不含真值）
python tools/alpha_harness.py prompt

# 2) 跑某个模型（需自备 API 凭据，脚本读环境变量或本地凭据文件）
python tools/alpha_run_v2.py --only <rater-name>

# 3) 算 α 与命中率
python tools/alpha_harness.py score verdicts/<file>.json
```

换 hold-out 夹具：

```
DSH_ALPHA_FIXTURE=fixtures/ncp-fixture-holdout6.json python tools/alpha_harness.py score verdicts/<file>.json
```

## 主要读数

- v1 四条并列定义：命中 9/9/8/9/9，α = 0.7529
- v2 加判定顺序：命中 10、8，α = −0.19
- v3 收紧缺事实定义：命中 9、10，α = 0.7473
- v4 前置事实清单：命中 10、10，α = 0.3235
- v5 断言清单：命中 11、12，α = 0.7089
- hold-out 换世界观（v2 口径）：命中 4/6、5/6，α = −1.54

## 局限（务必先读）

12 个场景、6 个 hold-out，样本量小，α 不适合当区间估计。

夹具作者同时参与判据设计，**非盲**。本文中的「作者判定」不构成独立证据。

语料为英文叙事场景，中文写作场景未涉及。

模型版本与家族未逐一声明，跨家族可比性受限。

## 相关文档

- [交付验收清单](../../docs/delivery-acceptance-checklist.md)
- [静默失效目录](../../docs/silent-failure-catalog.md)
- [负控运行记录](../../docs/negative-control-runs.jsonl)
