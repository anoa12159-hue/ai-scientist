# TASK-006：LangGraph Replay 工作流（首次构建）

> 状态：`READY`
>
> 所属阶段：T006
>
> 执行状态：`NOT_STARTED`
>
> 执行方式：执行同事只负责本任务的第一次构建；交回后由主 Agent 独立审查、直接修正、
> 补充反例测试并完成验证。执行同事不得自行关闭本任务或启动 T007。

## Goal

使用 LangGraph 把 T005 已接受的离线 Replay 能力编排成真正可运行、可中断、可恢复的
S01-S07 工作流。图只传递 ArtifactRef、VersionedRef、StageAttemptKey 和小型路由字段；
真实载荷、运行事实和 Checkpoint 继续由 T004 持久化端口负责。

本任务提供命令行可观察的完整工作流行为，但不实现 HTTP API 或前端。第一次可点击界面仍
属于 T008。

## Depends on

- T005 CompletionRecord（ACCEPTED）；
- T004 `ArtifactStore / Ledger / RunStore / CheckpointStore` 端口；
- T005 `ReplayService`、Replay Provider、Validator、Finding/DecisionRequest 工厂与报告
  Renderer；
- `governance/workflow.json`，workflow_version=`0.1.0`；
- `docs/contracts/CONTRACTS.md` 2.5、2.6、4、5、6、7 节；
- ADR-001 中“LangGraph 只负责编排、Graph State 不保存大载荷”的边界；
- `FIXTURE_IMPORT_REVIEW` 是阻塞 Gate，`FINAL_REPLAY_REVIEW` 是非阻塞项目查看确认。

## Required graph

```text
START
  -> S01_CANDIDATE
  -> S02_MECHANISM
  -> S03_HYPOTHESIS
  -> S04_DATA_AND_VERIFICATION
  -> [S05_COUNTEREXAMPLE || S06_MAGNETOGRAM_QA]
  -> JOIN_REQUIRE_S05_AND_S06
  -> FIXTURE_IMPORT_REVIEW (LangGraph interrupt, WAITING_HUMAN)
  -> S07_REPORT
  -> FINAL_REPLAY_REVIEW (non-blocking acknowledgement state)
  -> END
```

S05 与 S06 必须是实际并列分支，只有两者都成功并提供正确 Artifact 类型时才能进入 S07。
任一分支失败时可以形成诊断状态，但不得生成可进入最终查看确认的 ReportManifest。

## First-build scope

1. 定义小型 `ReplayGraphState`：只包含 run/task/workflow/configuration 身份、阶段状态、
   ArtifactRef/VersionedRef、FindingRef、StageAttemptKey、Gate 路由、有限重试计数和失败引用；
   禁止原始字节、Markdown、CSV、图片、完整 Fixture 对象或大字典进入 State。
2. 建立 S01-S07 LangGraph 节点、边和条件路由。节点必须驱动对应阶段的幂等应用服务，
   不能在首个节点预先完成 S01-S06 后再用空节点模拟流程。
3. 如 T005 `ReplayService` 粒度不足，可在不改变 Provider/契约语义的前提下，将其拆分为
   可逐阶段调用、可重试的应用服务；既有 `prepare()` 行为和 T005 测试必须保持兼容。
4. 在 S05/S06 Join 后调用 LangGraph `interrupt()` 产生真实
   `FIXTURE_IMPORT_REVIEW` 中断，并将 Run 投影为 `WAITING_HUMAN`。
5. 恢复时校验 DecisionRecord：必须为 HUMAN_SELECTED、RUN_GATE、正确 gate_id，且绑定
   本次 DecisionRequest、Run、workflow_version、RunConfigurationSnapshot、全部精确
   ArtifactRef、FindingRef 和六个 StageAttemptKey。缺失、多余、陈旧或跨 Run 引用均
   Fail Closed；不得自动生成 DecisionRecord 或默认批准。
6. 通过 T004 ArtifactStore + CheckpointStore 保存引用式恢复点，并验证 Artifact 内容身份。
   LangGraph 的内部恢复状态也必须可跨进程重开恢复，不能只依赖进程内 MemorySaver。
7. 节点重试必须有限、分类明确且幂等。系统/数据/Schema/授权失败产生结构化失败路由，
   不能转成“科学上不支持”。
8. Gate 接受后执行 S07，调用 T005 Renderer 持久化 ResearchSummary 与 ReportManifest；
   ReportManifest 必须同时绑定 S05 CounterexampleSnapshot 与 S06 MagnetogramQASnapshot。
9. ReportManifest 生成后进入 `FINAL_REPLAY_REVIEW` 可见状态。该步骤不阻塞报告可见性，
   只允许追加绑定精确报告版本的 ProjectReviewAck；不得创建 ReleaseDisposition 或改变
   `NOT_AUTHORIZED / NOT_READY`。
10. 提供离线命令行演示入口，至少能显示阶段推进、并行分支、人工中断、恢复和最终报告
    ArtifactRef；输出不得泄露机器绝对路径或把 PASS 表述成科学支持。

## Required outputs

命名可以遵循现有风格做等价调整，但职责不得减少：

```text
src/ai_scientist_mvp/workflow/state.py
src/ai_scientist_mvp/workflow/replay_graph.py
src/ai_scientist_mvp/workflow/checkpoint.py
src/ai_scientist_mvp/workflow/replay_cli.py
src/ai_scientist_mvp/application/replay_workflow_service.py
tests/unit/test_replay_graph.py
tests/integration/test_replay_workflow.py
pyproject.toml（仅增加并精确锁定 T006 所需 LangGraph 依赖及 CLI 入口）
tests/smoke/test_project_structure.py（仅更新 T006 合法模块/依赖清单）
```

必要时可最小修改 `src/ai_scientist_mvp/application/replay_service.py` 和对应 T005 测试，以
暴露逐阶段幂等边界，但不得修改 Replay 科学语义、Fixture 身份或已接受输出计数。

## Required tests

- 正常路径在 Join 后真实 interrupt，持久化状态为 `WAITING_HUMAN`；
- S05/S06 的执行和完成顺序可互换，但 S07 必须等待两者；
- 只有 S05 或只有 S06、错误 Artifact 类型、分支失败时禁止生成 ReportManifest；
- 精确 DecisionRecord 可恢复；陈旧 request、错误 Run/workflow/configuration、缺失或多余
  Artifact/Finding/StageAttemptKey、跨 Run 引用均拒绝；
- 节点重复调用不产生重复 Artifact、StageRun、Finding 或 Ledger 冲突；
- 进程重开后从最后完整 Checkpoint 恢复，篡改或缺失 Artifact 时 Fail Closed；
- 重试次数有限，系统失败不改变 scientific_verdict；
- Graph State 大小和键集合受测试约束，禁止嵌入大载荷；
- `FINAL_REPLAY_REVIEW` 不阻塞报告读取，不产生 ReleaseDisposition；
- `run_mode != REPLAY`、正式科学执行或未经授权的发布路径被拒绝；
- 全流程保持 `NOT_EVALUATED / DEVELOPMENTAL / NOT_AUTHORIZED / NOT_READY`。

## Allowed changes for the first build

```text
src/ai_scientist_mvp/workflow/**
src/ai_scientist_mvp/application/replay_workflow_service.py
src/ai_scientist_mvp/application/replay_service.py（仅逐阶段幂等拆分）
tests/unit/test_replay_graph.py
tests/integration/test_replay_workflow.py
tests/unit/test_replay_adapters.py（仅兼容拆分）
tests/integration/test_replay_adapters.py（仅兼容拆分）
tests/smoke/test_project_structure.py
pyproject.toml
tasks/TASK-006.md（仅在首次构建边界确有错误时登记，不得自行关闭）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`、
  `baseline.lock.json`、T001-T005 CompletionRecord、T004 存储语义或 T005 Provider 输出语义；
- API、FastAPI、Web 前端、网络、LLM Provider、Pi Agent、密钥或 `.env`；
- 修改历史 Fixture 字节，执行历史脚本/Notebook/ZIP，或补造缺失科学证据；
- 把完整载荷放进 Graph State、绕过 ArtifactStore/Ledger/RunStore/CheckpointStore，或用
  MemorySaver 冒充持久恢复；
- 自动形成 Gate 批准、ReleaseDisposition、科学支持结论或对外/比赛授权；
- 关闭 T006、创建 T006 CompletionRecord、启动 T007、创建 remote、push 或 PR。

## Verification commands for the first build

```powershell
python -m pytest tests/unit/test_replay_graph.py tests/integration/test_replay_workflow.py -q
python -m pytest tests/unit tests/integration tests/smoke tests/fixtures tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
git remote -v
```

统一脚本应在项目 `.venv` 可见的子 PowerShell 中执行。首次安装 LangGraph 依赖若需要网络，
必须如实登记；Replay 运行和全部测试本身必须保持离线、无 API Key。

## Stop conditions

- LangGraph 的持久恢复接口无法在不改变 T004 公共持久化语义的情况下实现；
- DecisionRecord 现有 Schema 无法表达冻结的精确 Gate 绑定，且需要修改契约；
- 实现要求把大载荷放进 State、绕过 Store、执行历史代码或访问在线服务；
- S05/S06 无法保持真实并列 Join，或恢复无法证明节点幂等；
- 需要改变研究问题、Fixture、Finding 政策、科学状态或授权边界。

## Handoff

本卡只授权 T006 第一次构建。执行同事完成首次实现后停止并交回报告；主 Agent随后直接
审查、修正和验证。T007 在 T006 正式 closeout 前不得开始。
