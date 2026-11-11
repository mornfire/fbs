# 判据顺序对照实验（第一次，2026-11-11 00:07 至 00:10）

## 设计

夹具：`artifacts/ncp-fixture-hardset8-v4.json`，八格四态混合，真值四类各两格。

两版判据只在**前两档顺序**上不同，其余逐字相同：

- v6（现行）：NOT_RUN → UNDECIDABLE → FAIL → PASS
- v7（交换）：UNDECIDABLE → NOT_RUN → FAIL → PASS

模型固定：glm-5.3-flash，温度 1.0。每版跑三次。

## 结果

v6 三次：

- run1：PASS / FAIL / FAIL / **PASS** / FAIL / PASS / NOT_RUN / NOT_RUN
- run2：PASS / FAIL / FAIL / **UNDECIDABLE** / FAIL / PASS / NOT_RUN / NOT_RUN
- run3：PASS / FAIL / FAIL / **PASS** / FAIL / PASS / NOT_RUN / NOT_RUN

v7 三次：

- run1：PASS / FAIL / FAIL / PASS / FAIL / PASS / NOT_RUN / NOT_RUN
- run2：PASS / FAIL / FAIL / PASS / FAIL / PASS / NOT_RUN / NOT_RUN
- run3：解析失败三次，未取到判定

## 两个读数

**一，顺序效应在本轮为零。** 五份成功解析的结果里，v6 与 v7 只在第 4 格有差异，而第 4 格的差异在同一版内部也出现过（v6 的 run1 与 run2）。换句话说，交换前两档顺序没有产生任何可归因于顺序的稳定差异。

**二，同一提示词、同一模型、两次运行的差异，比顺序造成的差异更大。** 第 4 格在 v6 的三次里给出 PASS、UNDECIDABLE、PASS——两派各占。这一格是「取走匣内之物」，台账里没有取出记录，按清单应为 UNDECIDABLE，模型有一半次数判了 PASS。

这条比顺序结论重要：**我们此前把一致性波动归因于判据版本，可能有一部分只是采样噪声。** 温度 1.0 下，边界样本的判定本身在抖。

## 待办

一，温度降到 0.2 重跑，看第 4 格是否稳定；若稳定，说明抖动来自采样。（已做，见下节；结论是「没稳住」）
二，同模型换三次不同随机种子，估计抖动的方差，再判断判据版本效应是否超出它。
三，v7 的解析失败要查：是输出格式问题还是模型对交换后的规则理解出偏。

## 降温实验（2026-11-11 02:20）

同一夹具、同一判据 v6、同一模型，温度从 1.0 降到 0.2，跑三次：

- run1：PASS / FAIL / FAIL / **UNDECIDABLE** / FAIL / PASS / **PASS** / NOT_RUN
- run2：PASS / FAIL / FAIL / **PASS** / FAIL / PASS / NOT_RUN / NOT_RUN
- run3：PASS / FAIL / FAIL / **UNDECIDABLE** / FAIL / PASS / **PASS** / NOT_RUN

第 4 格仍然三种结果里取两种（判不了、通过、判不了），和温度 1.0 时的形态一样。

更麻烦的是第 7 格：温度 1.0 时三次都判 NOT_RUN，与真值一致；降到 0.2 后两次判成了 PASS。降温不但没让边界格稳定，反而在另一个格上引入了新的错误。

结论：**抖动不是采样噪声，是模型对边界格的理解本身不稳。** 降温无效，说明这条路走不通，得从判据的输入结构上解决（例如把「缺记录」这一类单独做成必填字段，让模型没得选）。

## 局限

单模型、单夹具、单次实验（每版三次）。这个结论只说明「在本夹具上、对该模型，顺序效应小于采样噪声」，不能推广成「顺序不重要」。降温实验同样只有三次，且只压了一个维度。

