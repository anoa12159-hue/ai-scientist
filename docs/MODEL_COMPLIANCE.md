# Qwen 模型合规与预算冻结

状态：`FROZEN_FOR_IMPLEMENTATION`  
日期：2026-08-25

## 模型与部署

| 项 | 冻结值 |
|---|---|
| Provider | 阿里云百炼 DashScope |
| 接口 | OpenAI-compatible Chat Completions |
| API Base | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 模型 ID | `qwen-plus` |
| 密钥环境变量 | `DASHSCOPE_API_KEY` |
| 部署 | 百炼托管 API；不在提交包中分发基础模型权重 |
| Temperature | `0` |
| Seed | `42`（接口支持时传递；否则记录 `unsupported`） |
| 单请求超时 | 180 秒 |
| 最大修复轮数 | 2 |
| 最大 Agent 轮数 | 8 |
| 自动模型切换 | 禁止 |

`qwen-plus` 是当前工程选择而非官网唯一指定型号。每次响应必须记录 API 返回的实际模型字段；若百炼停止提供该 ID，先建立决策记录和新配置版本，不得静默切换。

## 预算

- 单次 Research Run：最多 30 次 LLM 请求、累计最多 200,000 输入 token 和 40,000 输出 token。
- 单请求默认上限：8,192 输出 token；具体节点可以更低，不得更高。
- 单次 Research Run 成本软上限：人民币 10 元；价格由运行时配置表提供，无法可靠计价时按 token 硬上限停止。
- Benchmark Run 不允许按测试样本自由展开 Agent 对话；LLM 调用必须批量化并受同一总预算约束。
- 达到任一上限时生成预算错误 Artifact，不返回伪造的完整结果。

## 结构化输出与错误

- 业务层只依赖统一 `QwenChatModel` 接口，不直接导入 DashScope 专用 SDK。
- 响应必须经过 JSON Schema 校验；仅允许两次有限修复，原错误和修复轨迹均写入脱敏 Artifact。
- 对 429、5xx 和可恢复网络错误执行带抖动的指数退避；认证、Schema 和预算错误不盲目重试。
- 日志不得包含 API Key、Authorization 头、完整论文正文或未脱敏个人信息。

## 额外数值模型

允许使用额外的确定性统计模型或可复现数值模型承担 Benchmark 预测，但必须满足：

1. Qwen 仍是研究智能体的基座模型并通过百炼调用；
2. 数值模型名称、训练数据、权重 SHA256、许可证、随机种子和推理资源全部登记；
3. 若包含自研权重，同时履行训练模型路线的一键复现要求；
4. 数值模型不得读取 test 标签，也不得把 Research Mode 的探索性 55 条记录包装成训练基准。

当前阶段不训练或交付自研权重。
