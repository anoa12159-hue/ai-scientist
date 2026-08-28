# JW-SSD 批量运行 Runbook

当前不执行批量评测。只有项目负责人明确授权后，才允许运行完整 195 条 Qwen-VL 评测。

## 闸门与预算

- 完整 Qwen 运行必须显式携带 `--confirm-batch`；没有该参数时入口拒绝无界运行。
- 配置上限：`max_requests=195`、`max_input_tokens=500000`、`max_output_tokens=50000`、`max_cost_cny=200.0`。
- 每次请求超时 `180s`；失败重试最多 `3` 次，指数退避上限 `16s`，请求间最小间隔 `0.2s`。
- 实际费用依赖百炼当日价格和 token 用量；运行前必须核对控制台价格，运行后以脱敏遥测和供应商账单为准。未执行前不填写虚构费用或耗时。

## 执行顺序

1. 校验 ZIP 文件名和 SHA256。
2. 运行 `audit_inference_source_isolation` 和四模态 QA 抽样。
3. 确认 `DASHSCOPE_API_KEY` 只存在于本地环境文件，不进入命令行、日志或 Artifact。
4. 使用 `src/infer_batch.py --mode qwen --confirm-batch` 生成预测 CSV。
5. 使用独立 `src/evaluate_jwssd.py` 读取标签并生成指标 JSON。
6. 保存失败重试摘要、请求数、token 用量、总耗时、预测 CSV SHA256 和 `JWSSDPilotAudit`/批量审计 Artifact。

任何标签隔离、输入哈希、预算、授权或 Artifact 校验失败都必须停止，不得用部分结果冒充完整评测。
