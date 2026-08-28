# TASK-P5-03：JW-SSD 独立五分类评测进程

> 状态：`COMPLETED`

`src/evaluate_jwssd.py` 独立读取冻结 ZIP 的 Mount Wilson 标签和推理输出 CSV，校验样本 ID 完整性、概率范围及和为 1，再生成混淆矩阵、每类指标、macro/micro-F1、balanced accuracy 和 Recall Wilson 95% 区间。推理入口不调用本模块。
