# JW-SSD 五分类指标报告模板

完整评测执行后，使用独立 `src/evaluate_jwssd.py` 填充以下字段：

- Archive 文件名、SHA256、manifest SHA256；
- 样本数和五类支持数；
- 混淆矩阵；
- 每类 Precision、Recall、F1、Wilson 95% Recall 区间；
- macro-F1、micro-F1、balanced accuracy；
- 推理配置、Prompt 哈希、代码/依赖 commit；
- 预测 CSV SHA256、失败重试统计、token 用量、耗时和费用；
- HARPNUM 组级泄漏审计结果；
- 少数类漏报、混淆样本和 QA Artifact 引用。

在完整预测 CSV 生成前不得填写全量数值；pilot 数值必须标注为非正式、不可外推。
