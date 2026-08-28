# ADR-0002：冻结 JW-SSD 五分类四模态评测任务

状态：Accepted

日期：2026-08-26

## 背景

项目负责人确认：`SHRGT45_官方五分类四模态扩展样本_20260826.zip` 是后续评测集。该压缩包来自组委会提供的官方 JW-SSD 数据，样本标签为 Mount Wilson 五分类。

## 判断

- 后续实现、推理和评测统一以官方 JW-SSD 五分类四模态评测集为数据边界。
- 本决策是项目负责人对既有选题边界的明确更新；移交材料中“JW-SSD 不作为主线”的历史表述不再约束后续实现。
- JW-SSD 的类别是 `alpha`、`beta`、`beta-delta`、`beta-gamma`、`beta-gamma-delta`，不是 `flare_label_M1.0_24hr` 等耀斑标签。
- 评测集 SHA256 为 `db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4`。
- ZIP 内部目录保留 `SHRGT45_官方五分类四模态扩展样本_20260825 2/` 名称，但以外层 20260826 ZIP 和 SHA256 作为版本身份。

## 决策

1. 以 `TASK_DECLARATION_JWSSD_MW5CLASS.md` 作为当前冻结任务声明，任务 ID 为 `JWSSD_MountWilson_5class_multimodal`。
2. 后续任务默认使用该评测集，不得回退到已删除的 JW-FD 根任务声明或 M1+ 标签语义。
3. 训练/验证数据与该评测集隔离；评测集不得用于训练、调参、阈值选择或模型选择。
4. 当前主指标为五分类指标和少数类召回率，不生成 M1+ 耀斑 TSS/HSS。
