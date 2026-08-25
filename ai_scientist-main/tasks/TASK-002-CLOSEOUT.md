# TASK-002-CLOSEOUT：T002 正式关闭收尾

> 状态：`COMPLETED`
>
> 所属阶段：T002 收尾（治理动作，非业务实现）
>
> 授权人：`actor_id=project_owner_01`

## Goal

在项目所有者接受 T002 独立复核结论后，完成治理收尾：追加不可变 T002 CompletionRecord、
生成 T003 任务卡（不执行）、同步 backlog 导航、更新 smoke guardrail，并建立本地 closeout commit。

## Why

独立复核结论为 `T002_INDEPENDENT_REVIEW = APPROVED`、`READY_FOR_PROJECT_OWNER_CLOSEOUT`。
后续任务不得依赖聊天记忆，必须把验收结果、偏差与哈希落成项目内不可变记录，并把仓库
导航推进到 T003。

## Depends on

- 验收实现 HEAD `167725a231a7db88f421d44a06bcad8351b198db`；
- 冻结 baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- `tasks/TASK-002.md` SHA256 `E4E1D99F6FCFB062178643E09C421E2C86DF8085667EA28054AED26A81863149`；
- T002 完整测试 `96 passed`。

## Allowed changes

```text
tasks/TASK-002-CLOSEOUT.md
governance/completions/TASK-002.completion.json
tasks/TASK-003.md
docs/TASK_BACKLOG.md
tests/smoke/test_project_structure.py
.git 本地索引及一个新的 closeout commit
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`tasks/TASK-001.md`、`tasks/TASK-002.md`、
  `tasks/TASK-001-CLOSEOUT.md`、`tasks/TASK-001-BACKLOG-SYNC.md`、
  `governance/completions/TASK-001.completion.json`、`governance/baseline.lock.json`、
  `governance/decisions/**`、`docs/contracts/**`、`docs/adr/**`、`contracts/**`、
  `src/**`、`tests/contract/**`、`pyproject.toml`、`fixtures/**`、任何 T003 实现文件。
- 不得 amend `167725a`、`2b18095`、`6d9aa28`；不得创建 remote、push 或 PR。
- 不得执行 T003。

## Required outputs

1. `tasks/TASK-002-CLOSEOUT.md`（本卡，状态 COMPLETED）。
2. `governance/completions/TASK-002.completion.json`（ACCEPTED、content_hash 自洽，
   登记实现提交链、独立复核证据、两个非阻断观察项）。
3. `tasks/TASK-003.md`（READY，不执行）。
4. `docs/TASK_BACKLOG.md` 同步（入口 T003、T002 COMPLETED、T003 READY）。
5. `tests/smoke/test_project_structure.py` 更新（T002 CompletionRecord 自洽校验 + 新冻结树 pin）。

## Acceptance criteria

1. T002 CompletionRecord content_hash 可复算一致且被 smoke test 校验；
2. T003 任务卡存在且 READY_NOT_STARTED；
3. backlog 导航指向 T003，T002 标 COMPLETED 并引用完成记录；
4. 全部验证命令通过；baseline 全量哈希复核 0 failures；
5. 本地存在 closeout commit（非 amend），git status 干净，remote 仍为 0。

## Verification commands

```powershell
python -m pytest tests/smoke tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git diff --cached --check
git status --short
git remote -v
```

（本机执行 verify_project.ps1 时如执行策略允许，可省略 Bypass 旗标；如实记录执行方式。）

## Handoff

完成时必须汇报：实际修改文件、CompletionRecord content_hash、TASK-003.md SHA256、
新冻结树 pin、完整测试真实数量、ruff/mypy/import/verify 结果、baseline 复核结果、
新 commit id、git status、remote 状态、未运行项目及原因、T003 是否仍为 READY_NOT_STARTED。
