# judge-to-detector 映射表（第一版，前五行）

用途：把「判据」落成可执行检测器。每行一条，签发方与我方各占一半：样本与断言由我方出，执行体由执行方补。

字段固定五项：`judge_id`、`fbs`、`assertion`（一行可跑断言）、`must_fail_sample`（必败样本路径）、`detector_entry`（执行体入口，暂空）。

仓库根：https://github.com/mornfire/fbs

## 1

- judge_id: `JUDGE-MISSING-AS-ZERO`
- fbs: `FBS-001`
- assertion: 把 `elapsed_ms` 与 `bytes` 从 schema 的 required 中移除后重跑聚合；若 `total_elapsed` 与 `total_bytes` 不变，判红。
- must_fail_sample: `shapes/FBS-001-missing_as_zero.json`
- detector_entry: _待填_

## 2

- judge_id: `JUDGE-FALLBACK-LAUNDERING`
- fbs: `FBS-002`
- assertion: 对可指认的硬违规必须判 `FAIL` 并写出被违反条目 id；若判成 `UNDECIDABLE`，判红。
- must_fail_sample: `shapes/FBS-002-fallback_label_laundering.json`
- detector_entry: _待填_

## 3

- judge_id: `JUDGE-STALE-ARTIFACT`
- fbs: `FBS-003`
- assertion: 解析出的产物必须带与本轮回执一致的 `run_id`；路径命中但 `run_id` 不符，判红。
- must_fail_sample: `shapes/FBS-003-stale_artifact_run_id.json`
- detector_entry: _待填_

## 4

- judge_id: `JUDGE-PATH-UNRESOLVABLE`
- fbs: `FBS-004`
- assertion: 接收端必须能按条目重算摘要；重算不出即落 `UNRESOLVED`，不得默认通过。
- must_fail_sample: `shapes/FBS-004-path_reference_unresolvable.json`
- detector_entry: _待填_

## 5

- judge_id: `JUDGE-CHECKLIST-MISSING-ITEM`
- fbs: `FBS-005`
- assertion: 删掉任一必要项后结论不变，判红；再插入一条伪项若被接受，同判红。
- must_fail_sample: `shapes/FBS-005-checklist_missing_item.json`
- detector_entry: _待填_

---

## 交接约定

一，每行只由一方维护：样本与断言随我方仓库走，执行体随执行方仓库走，改任一半都要在提交信息里点名另一半。

二，执行体必须能对本行的必败样本判红，且对同目录下的正控样本判绿。任一不满足，该行退回。

三，编号互认：`fbs` 字段是共同的主键，两边的目录、文档、提交信息里都用它指代同一条形状，不另起命名。
