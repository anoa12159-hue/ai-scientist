# AI Scientist MVP 技术方案（交付源稿）

## 目标

系统以 LangGraph 编排可审计的 Research Mode Replay，并提供冻结 JW-SSD Mount Wilson 五分类的 Evaluation Mode。当前不训练本地模型，视觉推理使用 Qwen-VL/百炼适配器；科学状态保持 `NOT_EVALUATED`、结果成熟度保持 `DEVELOPMENTAL`。

## 数据与边界

评测集为 `SHRGT45_官方五分类四模态扩展样本_20260826.zip`，SHA256 为 `db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4`，195 组、780 个四模态文件。推理端只读取无标签样本；标签、混淆矩阵、macro/micro-F1、balanced accuracy 和 Wilson Recall 区间由独立评测器计算。

## 架构

Provider、Skill、ArtifactStore、Ledger 和 Checkpoint 组成可替换边界。每个 Artifact 使用 canonical JSON 或原始字节哈希，父项和来源通过不可变引用绑定。S05 反例与 S06 磁图 QA 并行，在报告阶段汇合；QA PASS 不表示机制、因果或预测证据。

## 运行与安全

Qwen 调用只从本地 `DASHSCOPE_API_KEY` 读取，日志脱敏。完整 195 条运行必须显式 `--confirm-batch`，并受请求数、token、成本、超时、退避和限流约束。当前只完成 1–4 条 pilot，不执行完整评测。

## 验收

离线验收包含 ZIP SHA256、四模态 QA、标签隔离、路径无关、Artifact 血缘、Replay 中断恢复、API ReadModel 和静态前端契约。正式发布前仍需项目许可证/数据再分发许可确认、浏览器验收、PDF 渲染和完整评测指标。
