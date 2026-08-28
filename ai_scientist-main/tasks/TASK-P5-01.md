# TASK-P5-01：JW-SSD 唯一批量推理入口

> 状态：`COMPLETED`

`src/infer_batch.py` 是当前唯一批量推理入口。它只读取无标签样本身份和四模态路径，校验冻结 ZIP SHA256，并将预测写入固定 CSV；`uniform_predictor` 仅用于管道 smoke 验证，正式模式使用本地 `config.qwen_jwssd.toml` 的 Qwen-VL 模型。

推理进程不访问 `mount_wilson_class`，标签与指标必须由独立评测进程读取。后续模型接入只替换预测器，不改变输入隔离和 CSV 输出契约。
