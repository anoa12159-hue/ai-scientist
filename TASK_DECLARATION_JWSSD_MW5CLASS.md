# JW-SSD Mount Wilson 五分类四模态评测任务声明

状态：`FROZEN_FOR_IMPLEMENTATION`

创建日期：2026-08-26

适用范围：组委会提供的官方 JW-SSD 五分类四模态评测集；后续数据读取、模型开发、推理、评测和质量门均以本声明为准。

## 1. 任务身份

| 项 | 定义 |
|---|---|
| `task_id` | `JWSSD_MountWilson_5class_multimodal` |
| 评测集 | `SHRGT45_官方五分类四模态扩展样本_20260826.zip` |
| 数据 SHA256 | `db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4` |
| 数据来源 | 组委会提供的官方 `JW-SSD_Dataset` 四模态数据 |
| 当前评测集 | 195 条样本组、780 个文件；每组包含连续谱 FITS/PNG 和磁图 FITS/PNG |
| 单样本 | 同一 `HARPNUM + T_REC + Mount Wilson 类别` 的四个配对文件 |
| 标签 | `alpha`、`beta`、`beta-delta`、`beta-gamma`、`beta-gamma-delta` |
| 预测目标 | 从四模态观测预测 Mount Wilson 黑子分类 |

一行 `样本清单.csv` 对应一条样本组。类别和文件配对以该清单为准，不从文件名推断标签。

## 2. 输入与预处理

- 允许输入连续谱 PNG/FITS 和磁图 PNG/FITS；四模态缺一时该样本组不得进入完整四模态评测。
- FITS 仅使用经过头字段、图像形状、有限值和来源键校验的图像数据。
- 保留并审计 `HARPNUM`、`NOAA_AR`、`T_REC`、`QUALITY` 等元数据；元数据不得作为未经声明的标签替代品。
- 该 ZIP 是冻结评测集，不得用于训练、调参、阈值选择或模型选择；训练/验证数据必须使用另行登记的来源。
- 任何开发切分按 `NOAA_AR` 或 `HARPNUM` 分组，禁止同一活动区跨 split，并必须另存版本化 manifest。

## 3. 输出与指标

推荐输出：

```text
sample_id,pred_label,prob_alpha,prob_beta,prob_beta-delta,prob_beta-gamma,prob_beta-gamma-delta
```

必须报告混淆矩阵、每类 Precision/Recall/F1、macro-F1、balanced accuracy 和少数类召回率。类别不平衡时不得只报告 accuracy。

本任务不定义耀斑正类，不直接计算 M1+ 的 TSS/HSS/AUC；主评测使用五分类指标。如将类别折叠为二分类，必须另建任务声明和决策记录，写明折叠规则及标签依据。

## 4. 数据与科学边界

- Mount Wilson 类别是黑子/活动区形态分类标签，不是耀斑发生标签。
- 本数据包不是完整 12 分钟连续序列，不能直接构造 `T0` 前 3 小时历史窗口或替代正式 `SHRGT45` 研究数据。
- 当前 195 条样本是官方数据包冻结的评测集；评测结论只适用于本声明、该数据版本和已记录的模型/代码版本。
- 该任务的分类结果不得写入任何耀斑预测标签或 M1+ 指标文件。

## 5. 晋级条件

评测前必须完成：输入清单哈希核对、四模态配对检查、标签不可见推理审计、模型/代码版本记录和独立指标计算。评测集本身不得回流训练链。
