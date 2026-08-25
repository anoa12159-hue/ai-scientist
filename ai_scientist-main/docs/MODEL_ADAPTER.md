# Qwen 模型适配器

`ai_scientist_mvp.agent.llm.QwenChatModel` 是业务 Agent 使用的统一 Chat Completions
边界。它只依赖 Python 标准库，不直接导入 DashScope 或其他供应商 SDK。

## 默认绑定

- API Base：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 模型：`qwen-plus`
- API Key 环境变量：`DASHSCOPE_API_KEY`
- Temperature：`0`
- Seed：`42`
- 单请求超时：`180` 秒

这些默认值来自 `docs/MODEL_COMPLIANCE.md`。运行参数和预算现在由仓库根目录的
`config.example.toml` 统一描述，并通过不可变的 `QwenRuntimeConfig`/`ModelBudget` 加载校验。

## 调用边界

```python
from ai_scientist_mvp.agent.llm import ChatMessage, QwenChatModel, QwenModelConfig

model = QwenChatModel(QwenModelConfig())
response = model.invoke([ChatMessage("user", "Return a short answer.")])
print(response.message.content)
```

调用只在 `invoke()` 时读取密钥并发起 HTTPS 请求。缺少密钥、空消息、无效配置或无效
响应会产生类型化 `ModelError`；不会把 Authorization 头或完整原始响应写入异常。

## 离线测试

测试通过构造函数注入 `requester`，不需要网络或 API Key。研究 Replay 不调用模型适配器，
因此可以在无凭证环境中完整运行。

## 结构化输出

`StructuredQwenChatModel` 接收 Draft 2020-12 JSON Schema，要求模型返回
`response_format.type = json_schema`，并在本地再次校验响应。解析或校验失败时，它只追加
包含确定性错误位置的修复提示，最多执行配置的 `max_repair_rounds`；耗尽后抛出
`StructuredOutputError`，不会把无效结果传给业务层。

## 重试与错误 Artifact

`ResilientChatModel` 使用 `config.example.toml` 中的 `llm.retry` 策略。429、5xx 和网络
异常才允许有限重试；认证、配置和无效响应直接 Fail Closed。退避带可注入抖动，调用间隔
由 `RateLimiter` 控制。耗尽后抛出携带 `ModelErrorArtifact` 的 `ModelRequestError`，其中
只保存分类、状态码、尝试次数、模型和截断后的安全错误摘要，不保存 Authorization 头或密钥。
