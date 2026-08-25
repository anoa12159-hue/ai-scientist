# XH-202619 任务定义声明

状态：`FROZEN_FOR_IMPLEMENTATION`  
冻结日期：2026-08-25  
路线：智能体；若后续加入自研数值模型，同时按训练模型路线交付  
适用范围：本声明冻结比赛批量评测任务；研究模式的 SHRGT45 案例边界见第 6 节。

## 1. 主评测任务

| 项 | 冻结值 |
|---|---|
| `task_id` | `M1_24h_png_th1000` |
| 输入模态 | JW-FD `png_600_Th1000` 单帧磁图；允许读取同一无标签样本清单中的非标签标识字段 |
| 单样本 | 一张 600×600 PNG，对应一个 `image_filename` 和时刻 `T0` |
| 预处理 | RGB/灰度统一为单通道；有限值检查；按训练集统计量归一化；不做会改变标签语义的时间拼接 |
| 目标 | `T0` 后 24 小时内是否发生 `≥M1.0` 耀斑 |
| 官方标签列 | `flare_label_M1.0_24hr` |
| 正类 | 标签值 `1`，即 `≥M1.0` |
| 负类 | 标签值 `0` |
| 输出 | `image_filename,probability,prediction` |
| 阈值 | 只在 `val` 上选择使 TSS 最大的阈值；确定后写入冻结配置，默认回退值为 `0.5` |
| 主指标 | TSS、HSS；同时报告 TP、FP、TN、FN、Precision、Recall/POD、F1、FAR、Accuracy、ROC-AUC、PR-AUC |

输出文件名为 `predictions__M1_24h_png_th1000.csv`。`probability` 必须位于 `[0,1]`，`prediction` 必须为整数 `0` 或 `1`。

## 2. 数据边界

- 训练只读取官方 `train`，阈值和超参数只使用 `val`。
- 公共 `test` 标签只允许在推理完成后由独立评测命令读取；`src/infer_batch.py` 不接受标签列参数，也不得打开标签文件。
- 私有终评只替换 `data_root`，不得更换 Prompt、模型、权重、阈值或代码。
- 切分以官方 AR 级划分为准；同一 AR 不得跨 `train/val/test`。
- `image_path` 仅作来源字段，运行时根据 `data_root` 和 `image_filename` 解析路径，不使用提交者机器上的绝对路径。
- 外部数据和预训练资源必须先登记到 `docs/DATA_GOVERNANCE.md`；许可证未知的资源不得进入可发布训练或推理链。

## 3. 批量推理契约

唯一入口冻结为：

```bash
python src/infer_batch.py \
  --data_root /path/to/JW-FD_subset \
  --config config.example.yaml \
  --out predictions__M1_24h_png_th1000.csv
```

入口必须在无标签 test-like 目录工作，不需要人工点击，不读取本机绝对路径，不在运行中访问公开 test 标签。

## 4. 可复现配置

- 随机种子：`42`。
- LLM：`qwen-plus`，采样温度 `0`；详细限制见 `docs/MODEL_COMPLIANCE.md`。
- Prompt、工具清单、离线语料快照、模型/权重标识、阈值和依赖版本全部纳入版本化配置。
- 运行日志记录输入清单哈希、配置哈希、模型返回版本、token 用量、重试、耗时和输出 SHA256，但不得记录密钥或完整敏感输入。

## 5. 任务变更规则

下列变化均视为新任务，必须创建新 `task_id` 和决策记录，不得覆盖本声明：输入时间序列长度、标签时间窗、正类阈值、类别折叠规则、预处理语义或阈值选择数据集。

## 6. Research Mode 科学任务

Research Mode 保留独立的 `SHRGT45 + future_3_6h_same_unit_Mplus` 研究问题：

- 输入为同一活动区 `T0` 前 3 小时的 SHARP `SHRGT45` 时间序列，主估计量为真实 `T_REC` 轴上的 OLS 斜率；
- 目标为同一空间单位在未来非重叠 `3–6h` 窗口内是否发生 `≥M1.0` 耀斑；
- 当前 55 条 Demo 记录是开发性、画像性证据，不能作为独立样本训练集或确认性结论；
- 该研究任务不冒充 `M1_24h_png_th1000` 的比赛成绩。两者共享证据、治理和工具层，不共享标签含义。

两种任务不直接等价，采用并行双任务的原因与禁止映射见 `docs/decisions/ADR-0001-task-mapping.md`。

## 7. 待提交者填写

- 队名、作品名、联系人：提交前填写。
- 最终冻结阈值：模型在 `val` 上完成后填写。
- 预计推理耗时、硬件、权重或镜像校验值：实现和基准测试后填写。
- 诚信确认与队长签字：正式提交时填写。
