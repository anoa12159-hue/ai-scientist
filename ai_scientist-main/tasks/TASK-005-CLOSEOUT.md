# TASK-005-CLOSEOUT：T005 正式关闭收尾

> 状态：`COMPLETED`
>
> 所属阶段：T005 收尾（治理动作，非业务实现）
>
> 授权人：`actor_id=project_owner_01`

## Goal

依据执行同事的 T005 首次构建和主 Agent 随后的独立排查、直接修正、反例补充与全仓验证，
正式接受 T005，登记不可变 CompletionRecord，并生成 T006 LangGraph Replay 工作流任务卡。
T006 只生成任务卡，不在本次收尾中执行。

## Review disposition

本次遵循项目所有者冻结的协作方式：执行同事只负责板块第一次构建，主 Agent 收到报告后
自行审查和修改，不将修正返回执行同事。

```text
T005_INITIAL_BUILD = COMPLETE
T005_PRIMARY_REVIEW = APPROVED
T005_CORRECTION = COMPLETE
T005_FORMAL_CLOSEOUT = COMPLETED
T006_EXECUTION = NOT_STARTED
```

## Depends on

- T004 `governance/completions/TASK-004.completion.json`（ACCEPTED）；
- T005 首次构建提交 `9bef2c5cc1de68b87dc33d28a8eb335c417a3feb`；
- T005 主 Agent 修正提交 `cac55a90a7aff0b0fd17bb5f61a1b5b5c2225d1a`；
- 冻结 baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- 修正后 T005 聚焦测试 `19 passed`、全仓测试 `191 passed` 及静态检查证据。

## Allowed changes

```text
tasks/TASK-005-CLOSEOUT.md
governance/completions/TASK-005.completion.json
tasks/TASK-006.md
docs/TASK_BACKLOG.md
tests/smoke/test_project_structure.py
.git 本地索引及一个新的 closeout commit
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`tasks/TASK-005.md`、`governance/baseline.lock.json`、
  `governance/decisions/**`、`docs/contracts/**`、`docs/adr/**`、`contracts/**`、
  `fixtures/**`、T001-T004 CompletionRecord、`src/**`、`tests/unit/**`、
  `tests/integration/**`、`tests/contract/**` 或 `pyproject.toml`。
- 不得在本次收尾中实现 LangGraph、API、前端或新的科学分析逻辑。
- 不得 amend 既有提交；不得创建 remote、push 或 PR。
- 不得启动 T006；T006 只登记为 `READY_NOT_STARTED`。

## Acceptance criteria

1. T005 CompletionRecord 的 `content_hash` 可复算，且被 smoke test 校验；
2. CompletionRecord 登记首次构建、主 Agent 修正、验证证据和 T006 任务卡哈希；
3. `tasks/TASK-006.md` 存在、状态为 `READY`，并明确执行同事只做首次构建；
4. backlog 入口推进到 T006，T005 标记为 COMPLETED 并引用 CompletionRecord；
5. T001-T004 冻结基线、契约和 Fixture 字节保持不变；
6. 全套测试、ruff、mypy、import 和统一验证入口通过；
7. 本地存在独立 closeout commit，工作区干净，remote 仍为 0。

## Accepted T005 outcome

T005 已把冻结 Fixture 转换为可恢复的运行事实：完整 Fixture 预检、81 个运行时来源
Artifact、S01-S06 六个 DERIVED Snapshot、六份 ValidationReport、10 个可审核 Finding、
2 个信息 Gap、六个 StageRun、一个精确绑定的 `FIXTURE_IMPORT_REVIEW` DecisionRequest，
以及 `WAITING_HUMAN` RunRecord。报告 Renderer 已具备，但不会在人工 Gate 前自动调用。

结构校验成功没有改变科学状态；系统仍保持 `NOT_EVALUATED / DEVELOPMENTAL /
NOT_AUTHORIZED / NOT_READY`。

## Verification evidence

```text
focused replay tests: 19 passed
full suite before closeout: 191 passed
ruff: All checks passed
mypy: Success: no issues found in 20 source files
import: ai_scientist_mvp import OK 0.1.0
verify_project.ps1: ALL CHECKS PASSED (project .venv on child PowerShell PATH)
baseline and Fixture identity: 0 failures
git diff --check: clean
```

## Handoff

T005 已正式关闭。下一工作项为 `tasks/TASK-006.md`，状态为 `READY_NOT_STARTED`。
执行同事收到的下一条指令只能启动 T006 的第一次构建；交回后由主 Agent独立审查、直接
修正并完成最终验证。
