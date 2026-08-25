# ADR-001：AI Scientist Replay MVP 架构

> 状态：`ACCEPTED`
>
> 日期：2026-08-19
>
> 决策依据：D-001 至 D-008、`docs/PROJECT_CHARTER.md`、`docs/contracts/CONTRACTS.md`

## 背景

首个 MVP 必须忠实回放现有 SHRGT45 历史材料，同时为后续在线机制研究、假设生成、数据获取和正式验证保留扩展点。当前最重要的不是让一个 Agent 自由完成所有步骤，而是确保阶段边界、Artifact、血缘、Finding、人工决定和失败都可验证、可恢复。

## 决策

### 1. 分层与依赖方向

```text
Web UI
  -> API / RunReadModel projector
  -> Application services / Gate services
  -> LangGraph orchestration
  -> Provider ports
  -> Replay adapters or future Live providers

All layers
  -> Domain contracts
  -> ArtifactStore / Ledger / Checkpoint ports
```

- Domain contracts 不依赖 LangGraph、FastAPI、前端或历史文件格式。
- LangGraph 只负责编排、并行、条件路由、中断和恢复，不是 Artifact 或科学状态的事实源。
- Graph State 只保存版本化引用和小型路由字段；长文、CSV、图片与大型对象进入 ArtifactStore。
- 所有状态视图由追加式 Ledger、不可变 Artifact、ValidationReport、Finding 和 Decision 投影得到。

### 2. Agent、Tool 与 Skill

- 顶层编排使用 LangGraph；首个 MVP 不引入 Pi Agent。
- Tool 是原子操作，例如受限文件读取、内容哈希、Schema 校验和受控命令。
- Skill/Provider 组合领域能力；不得把业务流程写入通用 Tool。
- LLM 输出在成为下游输入前必须结构化并确定性校验。
- 科学计算只能通过注册的 `calculator_id` 调用；禁止 `eval()`、任意脚本执行和执行历史包内代码。

### 3. Provider 扩展边界

主图依赖稳定端口：

```text
CandidateProvider
MechanismProvider
HypothesisProvider
DataProvider
CounterexampleReviewer
MagnetogramQAProvider
ReportRenderer
```

首版使用离线 `Replay*Provider`。未来的 `DeepResearchMechanismProvider`、`QwenHypothesisProvider`、`JsocDataProvider` 等只能替换 Provider 实现，不得绕过公共契约或重写主图阶段语义。

### 4. 持久化

- Artifact 内容使用按内容寻址的文件存储，导入来源以原始字节为权威，系统原生产物以 canonical JSON 为权威。
- Ledger、运行元数据和幂等索引使用追加式本地持久化接口；MVP 默认实现可使用 SQLite。
- LangGraph Checkpoint 使用独立接口；Checkpoint 只能引用 Artifact，不复制大载荷。
- 每个 Run 写入独立的 `runs/<run_id>/`；禁止清空共享目录或覆盖其他 Run。

### 5. 工作流与人工动作

- S05 与 S06 并列，二者均满足后才能进入报告路径。
- `FIXTURE_IMPORT_REVIEW` 位于 S01-S06 完成后、S07 前，是历史 Replay 的阻塞闸门。
- `FINAL_REPLAY_REVIEW` 位于不可变 ReportManifest 生成后，是非阻塞项目查看确认，不产生 ReleaseDisposition。
- 未知输入、哈希、Schema、来源、配置、授权、禁止执行、必需分支或 Report Join 错误 Fail Closed。

### 6. API 与前端

- Python API 层采用 FastAPI，暴露版本化的命令端点和 D-006 聚合 `RunReadModel` 查询。
- 前端采用 React + TypeScript，作为逻辑较薄的客户端，只展示后端投影和提交契约允许的选项。
- 全文、CSV、图片和 provenance 通过受控详情引用访问；API 不泄露机器绝对路径。
- 前端不得计算工作流状态、Finding 阻断、S05/S06 Join、科学 verdict 或授权状态。

### 7. 工程边界

建议的实现布局为：

```text
src/ai_scientist_mvp/domain/
src/ai_scientist_mvp/application/
src/ai_scientist_mvp/infrastructure/
src/ai_scientist_mvp/providers/
src/ai_scientist_mvp/workflow/
src/ai_scientist_mvp/api/
web/
contracts/
fixtures/shrgt45/
tests/
```

T001 只建立骨架与执行护栏；T002 才机械化 Schema；T003 才导入 Fixture；后续任务按依赖顺序实现。

## 结果

优点：历史格式变化被限制在 Replay Adapter；未来 Live Provider 可以逐个替换；前后端不复制科学状态逻辑；运行可以按 Artifact、Ledger 和 Checkpoint 审计恢复。

代价：首版需要先实现契约、内容寻址、投影和适配层，代码量高于直接把历史脚本串联起来。这是保证可扩展性与不让 Vibe Coding 改乱语义的必要成本。

## 不采用

- 单一自由 Agent 持有全部上下文并直接读写所有文件；
- 前端读取 LangGraph State 或历史文件自行推断状态；
- 把历史脚本、ZIP 或 LLM 生成代码当作可执行插件；
- 为了跑通 Replay 静默修改 V2.2/V2.3、时间窗、control 或来源语义。
