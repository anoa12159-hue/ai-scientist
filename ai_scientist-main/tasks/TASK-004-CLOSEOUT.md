# TASK-004-CLOSEOUT：T004 正式关闭收尾

> 状态：`COMPLETED`
>
> 所属阶段：T004 收尾（治理动作，非业务实现）
>
> 授权人：`actor_id=project_owner_01`

## Goal

依据执行同事的 T004 首次构建、项目所有者授权的修正范围、主 Agent 的直接审查与修正，
正式接受 T004，登记不可变 CompletionRecord，并生成 T005 首次构建任务卡。T005 只生成
任务卡，不在本次收尾中执行。

## Review disposition

本次由主 Agent 完成独立审查、直接修正、反例补充和全仓验证：

```text
T004_INITIAL_BUILD = COMPLETE
T004_PRIMARY_REVIEW = APPROVED
T004_CORRECTION = COMPLETE
T004_FORMAL_CLOSEOUT = COMPLETED
T005_EXECUTION = NOT_STARTED
```

修正没有返回执行同事；执行同事只负责了 T004 的第一次构建。

## Depends on

- T003 `governance/completions/TASK-003.completion.json`（ACCEPTED）；
- T004 首次构建提交 `3b0304ca1ebff7eb3915a2f392608df162d3647b`；
- T004 主 Agent 修正提交 `3143649b11b2ad4b01d7047734d0c9e03554d24b`；
- T004 修正卡 `tasks/TASK-004-CORRECTION-1.md`（COMPLETED）；
- 冻结 baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`。

## Allowed changes

```text
tasks/TASK-004-CLOSEOUT.md
governance/completions/TASK-004.completion.json
tasks/TASK-005.md
docs/TASK_BACKLOG.md
tests/smoke/test_project_structure.py
.git 本地索引及一个新的 closeout commit
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/baseline.lock.json`、`governance/decisions/**`、
  `docs/contracts/**`、`docs/adr/**`、`contracts/**`、`fixtures/**`、T001-T003 已接受产物、
  `src/**`、`tests/unit/**`、`tests/integration/**`、`tests/contract/**`、`pyproject.toml`。
- 不得在本次收尾中实现 T005 Adapter、LangGraph、API、前端或科学分析逻辑。
- 不得 amend 既有提交；不得创建 remote、push 或 PR。
- 不得启动 T005；T005 仅登记为 `READY_NOT_STARTED`。

## Acceptance criteria

1. T004 CompletionRecord 的 `content_hash` 可复算，且被 smoke test 校验；
2. CompletionRecord 登记首次构建、主 Agent 修正、验证证据和 T005 任务卡哈希；
3. `tasks/TASK-005.md` 存在、状态为 `READY`，并明确执行同事只做首次构建；
4. backlog 入口推进到 T005，T004 标记为 COMPLETED 并引用 CompletionRecord；
5. T001-T003 冻结基线、契约和 Fixture 字节保持不变；
6. 全套测试、ruff、mypy、import 和统一验证入口通过；
7. 本地存在独立 closeout commit，工作区干净，remote 仍为 0。

## Verification evidence

```text
focused storage tests: 42 passed
full suite (unit/integration/smoke/fixtures/contract): 171 passed
ruff: All checks passed
mypy: Success: no issues found in 16 source files
import: ai_scientist_mvp import OK 0.1.0
verify_project.ps1: ALL CHECKS PASSED (venv activated in child PowerShell)
baseline and Fixture identity: 0 failures
git diff --check: clean
```

## Handoff

T004 已正式关闭。下一工作项为 `tasks/TASK-005.md`，状态为 `READY_NOT_STARTED`。
执行同事收到的下一条指令只能启动 T005 的首次构建；首次构建交回后由主 Agent 直接审查和修正。
