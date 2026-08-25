# TASK-003-CLOSEOUT：T003 正式关闭收尾

> 状态：`COMPLETED`
>
> 所属阶段：T003 收尾（治理动作，非运行时实现）
>
> 授权人：`actor_id=project_owner_01`

## Goal

在项目所有者明确豁免额外独立复核后，依据已完成的实现、修正和验证证据正式接受 T003：
追加不可变 T003 CompletionRecord、生成 T004 任务卡（不执行）、同步 backlog 导航、更新
smoke guardrail，并建立本地 closeout commit。

## Review disposition

项目所有者于 2026-08-20 明确指示“不需要再验证了，直接下一步”。因此本次关闭必须如实登记：

```text
T003_INDEPENDENT_REVIEW = WAIVED_BY_PROJECT_OWNER
```

该豁免只取消另一轮独立复核，不改变 T003 已有确定性验证证据，也不得被表述为
`T003_INDEPENDENT_REVIEW = APPROVED`。

## Depends on

- 最终验收实现 HEAD `0c4ced142e98460e903fd8c7f441c6ba888ecc93`；
- T003 实现提交链 `f32f53e -> df9ff1f -> fe9da83 -> 0c4ced1`；
- 冻结 baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- `tasks/TASK-003.md` SHA256 `C5175B84B347697B55AF21A44F8952D0D510AFE75B115301C6471040501BFBDC`；
- 最终 T003 回归证据 `128 passed`（fixture 31 + smoke 13 + contract 84）。

## Allowed changes

```text
tasks/TASK-003-CLOSEOUT.md
governance/completions/TASK-003.completion.json
tasks/TASK-004.md
docs/TASK_BACKLOG.md
tests/smoke/test_project_structure.py
.git 本地索引及一个新的 closeout commit
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`tasks/TASK-003.md`、`tasks/TASK-003-CORRECTION-1.md`、
  `governance/baseline.lock.json`、`governance/decisions/**`、`docs/contracts/**`、
  `docs/adr/**`、`contracts/**`、`src/**`、`tests/contract/**`、`tests/fixtures/**`、
  `fixtures/**` 或 `pyproject.toml`。
- 不得伪造仓库内不存在的独立复核产物，不得把豁免写成 `APPROVED`。
- 不得 amend 任何既有提交；不得创建 remote、push 或 PR。
- 不得执行 T004。

## Required outputs

1. `tasks/TASK-003-CLOSEOUT.md`（本卡，状态 COMPLETED）。
2. `governance/completions/TASK-003.completion.json`（ACCEPTED、content_hash 自洽，
   登记完整实现链、最终验证证据、Fixture 身份和独立复核豁免）。
3. `tasks/TASK-004.md`（READY，不执行）。
4. `docs/TASK_BACKLOG.md` 同步（入口 T004、T003 COMPLETED、T004 READY）。
5. `tests/smoke/test_project_structure.py` 更新（T003 CompletionRecord 自洽校验 + 新冻结树 pin）。

## Acceptance criteria

1. T003 CompletionRecord content_hash 可复算一致且被 smoke test 校验；
2. CompletionRecord 如实记录 `independent_review=WAIVED_BY_PROJECT_OWNER` 及项目所有者指令；
3. T004 任务卡存在且 `READY_NOT_STARTED`，没有 T004 业务实现；
4. backlog 导航指向 T004，T003 标 COMPLETED 并引用完成记录；
5. 全部收尾验证通过，baseline 仍为冻结哈希；
6. 本地存在独立 closeout commit，git status 干净，remote 仍为 0。

## Verification commands

```powershell
python -m pytest tests/smoke tests/fixtures tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git diff --cached --check
git status --short
git remote -v
```

## Handoff

完成时汇报实际修改文件、CompletionRecord content_hash、TASK-004.md SHA256、新冻结树 pin、
实际测试数量、ruff/mypy/import/verify 结果、新 commit id、git status、remote 状态，并明确
`T004_EXECUTION = NOT_STARTED`。
