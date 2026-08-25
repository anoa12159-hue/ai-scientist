# AI Scientist 实施方案

更新时间：2026-08-25

## 1. 目标与范围

本项目面向阿里云赛事赛道一“科学问题”方向二“金乌·太阳物理建模迭代与假设生成”，当前采用 B1 × A1 口径：以耀斑触发前兆因果链发现为科学内核，以活动区磁场复杂度定量分析作为验证引擎。

项目系统同时提供两种入口：

1. **Research Mode**：专家候选参数 → 文献证据 → 可检验假设 → 数据验证 → 反例审查 → 磁图 QA → 研究报告。
2. **Benchmark Mode**：`data_root` → 固定配置批量推理 → 官方格式预测 CSV；不得读取 test 标签或依赖人工点击。

当前策略不是从头重写 Agent，也不是原样上线 `deep_research_agent_v13`，而是：

- 以现有 LangGraph MVP 作为状态机、契约、ArtifactStore、Ledger、Checkpoint 和报告内核；
- 将深度检索项目拆分为可测试的文献研究 Skills；
- 所有语言推理调用统一通过 Qwen 适配器；
- 将数据处理、统计检验、磁图 QA 和预测计算实现为确定性 Python Skills；
- 用结构化 Artifact 连接各阶段，避免 Agent 之间自由聊天。

## 2. 已知基线

详见根目录 `AI_Scientist_MVP_学长移交报告.md`：

- 已有 37 类 JSON Schema、内容身份、ArtifactStore、Ledger、Run/Stage 和 Checkpoint；
- SHRGT45 离线 Replay 已跑通 S01-S07 的主要流程；
- S05 与 S06 已设计为并行分支；
- T006 尚需完成完整回归和正式收尾；
- API、前端、端到端验收和演示包尚未完成；
- 当前 MVP 仍是历史研究回放，不是正式科学预测系统。

`deep_research_agent_v13` 可复用的能力包括多角度检索、Semantic Scholar 引用链、概念图谱、全文问答、逐字引用验证和 Phase 1/Phase 2 分层研究。它当前绑定 DeepSeek、自由文本输出、外部网络缓存和独立输出目录，必须通过适配层接入主系统。

## 3. 目标架构

```text
API / CLI / Frontend
        |
        v
Supervisor（LangGraph 状态机，不直接做科学计算）
        |
        +--> S01 任务与参数定义
        +--> S02 文献检索与候选排序
        +--> S03 机制证据与引用审计
        +--> S04 假设生成与操作化
        +--> S05 数据计划、特征计算与统计验证
        |          |
        |          +--> S06 反例审查与下一步计划
        |          +--> S07 磁图 QA 与视觉证据
        +--> S08 报告、前端结果与评测输出
        |
        v
ArtifactStore + Ledger + Checkpoint
```

每个阶段必须有明确的输入 Schema、输出 Schema、质量门和失败状态。Agent 节点只负责有限的规划、选择、解释和结构化生成；所有重要事实和计算结果必须落入 ArtifactStore/Ledger。

## 4. Agent 与 Skills 划分

### 4.1 Supervisor

- 根据 Run 配置路由阶段；
- 控制重试、超时、预算和人工审核；
- 不保存大段原文，只保存 Artifact 引用和哈希；
- 支持中断、恢复、幂等重放。

### 4.2 Qwen Agent 节点

- 文献 Scout：规划检索角度、筛选候选论文；
- Evidence Auditor：将声明绑定到逐字证据、位置和来源；
- Hypothesis Engineer：生成可操作、可证伪的假设；
- Falsification Reviewer：解释假阳性、假阴性和反例；
- Report Composer：从已验证 Artifact 生成报告。

Agent 节点之间只传 `ParameterProfile`、`EvidenceTable`、`MechanismBrief`、`Hypothesis`、`DataPlan`、`ValidationReport` 等结构化对象。

### 4.3 确定性 Skills

- `parameter_registry`：SHARP 参数定义、单位、公式和别名校验；
- `paper_search` / `paper_fetch`：搜索、全文获取、缓存和版本记录；
- `quote_verifier`：逐字引用、数字和位置一致性校验；
- `data_loader`：FITS、CSV、时间序列读取；
- `feature_compute`：磁场复杂度和候选参数计算；
- `stats`：时间切分、统计检验、TSS/HSS、置信区间和泄漏检查；
- `counterexample_miner`：假阳性、假阴性和边界样本提取；
- `magnetogram_qa`：缺失、饱和、投影、WCS、质量标记和 cadence 检查；
- `report_renderer`：从 Artifact 生成 HTML/Markdown/PDF；
- `prediction_writer`：生成官方格式的批量预测 CSV。

## 5. Qwen 模型接入原则

所有语言模型调用必须经过统一接口，不允许业务代码直接依赖某一家 SDK：

```yaml
llm:
  provider: dashscope
  model: <赛事当前允许的 Qwen 模型 ID>
  temperature: 0
  seed: 42
  max_iterations: 8
  timeout_seconds: 180
```

要求：

- 模型 ID、API Base、temperature、seed、最大轮数和预算都进入配置；
- 密钥只从环境变量读取；
- 使用 JSON Schema 或结构化输出；
- API 失败执行有限重试、退避和限流；
- 记录模型、Prompt 版本、工具版本、输入哈希和 token 用量；
- 开发和评测使用固定模型 ID，不在运行中自动切换；
- 官网要求使用 Qwen 系列并通过阿里云百炼或推荐工具调用，但未指定唯一型号。工程基线冻结为 `qwen-plus` 和百炼 OpenAI-compatible API，详见 `docs/MODEL_COMPLIANCE.md`。

初期不训练自有大模型。只有在积累了足够人工修订轨迹、明确错误类型并证明 Prompt/工具方案的瓶颈后，才评估 Qwen LoRA/SFT。若采用自研权重，必须额外满足权重、校验值和离线复现要求。

## 6. 两种运行模式

### 6.1 Research Mode

允许网络检索、论文缓存和人工审核，用于研究探索、前端演示和老师评议。每次运行仍必须保存完整 Artifact、Ledger 和脱敏日志。

### 6.2 Benchmark Mode

提供唯一批量入口：

```bash
export LLM_API_KEY=***
python src/infer_batch.py \
  --data_root /path/to/data_root \
  --config config.example.yaml \
  --out /path/to/out/pred.csv
```

Benchmark Mode 必须不读取标签、不需要人工操作、不依赖本机绝对路径，并输出官方规定的预测 CSV。外部检索应使用随包提供或可重建的语料快照；网络不可用时要有明确的离线策略。

## 7. 必须先冻结的任务定义

在实现真实预测入口前，完成 `TASK_DECLARATION.md`，至少固定：

- 输入模态和单样本定义；
- 参数、特征和预处理；
- 主报告时间窗；
- 正负类或多分类到业务二分类的映射；
- 输出类别、概率或等级分数；
- 阈值策略；
- train/validation/test 数据边界；
- TSS/HSS 等指标定义；
- 外部数据、检索语料和许可证。

现有研究口径 `SHRGT45 + 未来 3-6h M+` 与 JW-FD 累计窗口标签不等价。当前采用 Research/Benchmark 双任务，禁止静默映射，详见 `TASK_DECLARATION.md` 和 `docs/decisions/ADR-0001-task-mapping.md`。

## 8. 稳定复现策略

1. 固定 Prompt、工具清单、检索语料、依赖和模型 ID；
2. 固定 temperature 和 seed（API 支持时）；
3. 所有输出经过 Schema Validator；
4. 引用必须逐字验证，无法验证就输出 `NOT_FOUND`；
5. 数据计算只由确定性 Skill 执行；
6. 工具调用幂等，Artifact 使用内容哈希；
7. 每阶段设置最大轮数、超时、重试和 token 预算；
8. 运行日志脱敏并记录失败原因；
9. Checkpoint 只保存引用，不保存大段原文；
10. 同一 Fixture 重放必须通过结构化结果、阶段状态和血缘校验。

## 9. 阶段计划与验收门

### P0：赛事与科学任务冻结

产出：`TASK_DECLARATION.md`、`docs/MODEL_COMPLIANCE.md`、`docs/DATA_GOVERNANCE.md`、赛事核验和决策记录。

验收：输入、标签、时间窗、输出和指标无歧义；研究入口与评测入口关系明确。

### P1：MVP 内核收尾

产出：T006 独立提交、完整测试报告、更新后的 README 和任务状态。

验收：单元、集成、契约、冒烟测试通过；中断恢复和重试测试通过；原有冻结契约未被破坏。

### P2：Qwen Adapter

产出：`src/agent/llm/`、`config.example.yaml`、模型调用测试、脱敏日志。

验收：Qwen API 可调用；结构化输出、超时、重试、限流、预算记录均可测试；不再依赖 DeepSeek 配置。

### P3：文献研究 Skills

产出：`paper_search`、`paper_fetch`、`quote_verifier`、`MechanismBrief` Provider 和固定语料快照。

验收：SHRGT45 基准研究可以从参数定义走到证据表；引用逐字校验通过；网络失败可恢复或明确降级。

### P4：假设与数据验证闭环

产出：Hypothesis/DataPlan Schema、特征计算、统计验证、反例审查和磁图 QA Provider。

验收：每个假设都能映射到指标、数据、时间窗、检验和证伪条件；统计结果可独立重算；没有数据泄漏。

### P5：Benchmark 入口

产出：`src/infer_batch.py`、公开预测文件、公开指标、运行日志摘要。

验收：仅凭 `data_root` 和配置生成标准 CSV；无 test 标签、人工点击或私有 Prompt 依赖；公开数据可复现。

### P6：API、前端与演示包

产出：测试 API、交互前端、端到端验收、30 页以内技术方案 PDF、可选演示视频。

验收：前端可查看阶段状态、证据、反例、质量问题和报告；比赛材料从带版本 Artifact 生成。官网 2026-08-25 当前口径将前端列为选交，但项目仍保留该产品目标。

## 10. 评测清单

- Schema 合法率；
- 引用逐字准确率和来源覆盖率；
- 假设可操作化率；
- 数据计划可执行率；
- 统计结果重算一致性；
- 反例识别覆盖率；
- 磁图 QA 失败检测率；
- 公开数据 TSS/HSS 等指标；
- API 失败恢复率和平均调用预算；
- 中断恢复成功率；
- 公开数据和私有数据均不读取标签的审计结果。

## 11. 当前 session 的下一步

下一个 session 默认从 `TODO.md` 中第一个未完成且无阻塞项的任务开始。每完成一项：

1. 更新 `TODO.md` 的状态和完成日期；
2. 更新本文档中对应阶段的产出或决策；
3. 运行最小相关测试；
4. 在 session 交接信息中记录修改文件、测试结果和下一个任务。
