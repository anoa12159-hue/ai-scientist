# TASK-001-BACKLOG-SYNC：同步 backlog 导航至 T002

> 状态：`COMPLETED`
>
> 所属阶段：T001 收尾后的治理同步（非新业务实现）
>
> 授权人：`actor_id=project_owner_01`

## Goal

修复 `docs/TASK_BACKLOG.md` 仍指向 TASK-001、仍把 T001 标为 `READY` 的状态不一致，
使仓库内正式导航与 `governance/completions/TASK-001.completion.json`、`tasks/TASK-002.md`
保持一致。

## Why

TASK-001-CLOSEOUT 已完整执行：T001 formal_closeout=COMPLETED，TASK-002.md 已生成且 READY。
但 `docs/TASK_BACKLOG.md` 顶部“当前入口”仍指向 TASK-001，T001 仍标 `READY`，
T002 尚无状态行。后续任务不得依赖聊天记忆，仓库内导航必须自洽。

## Depends on

- TASK-001-CLOSEOUT 已完成（不得重复执行）；
- checkpoint commit `bc84eb0`；
- `governance/completions/TASK-001.completion.json` ACCEPTED / formal_closeout=COMPLETED；
- `governance/baseline.lock.json` content_hash 保持
  `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`。

## Allowed changes

```text
tasks/TASK-001-BACKLOG-SYNC.md           （本卡）
docs/TASK_BACKLOG.md                     （仅同步导航与状态，保留技术内容）
.git 本地索引及一个新的本地 commit        （新 commit，不 amend bc84eb0）
```

## Forbidden changes

- 不得重复执行或修改 TASK-001-CLOSEOUT。
- 不得修改 commit `bc84eb0`，不得 amend。
- 不得修改 `.gitattributes`（继续保留 `* -text`）。
- 不得修改 `governance/completions/TASK-001.completion.json`。
- 不得修改 `tasks/TASK-002.md`。
- 不得修改 `governance/baseline.lock.json`。
- 不得修改 `docs/contracts/**`、`docs/adr/**`、DecisionRecord 或 Fixture。
- 不得实现任何 T002 Schema、Python 类型或业务代码。
- 不得创建或修改 remote，不得推送。
- 不得修改本任务 Allowed changes 之外的文件。

## Required changes（仅 `docs/TASK_BACKLOG.md`）

- 顶部“当前入口”改为 `tasks/TASK-002.md`；
- 顶部队列状态改为 `READY`；
- 项目现状说明改为：T001 已完成，T002 已生成且 READY；
- T001 状态改为 `COMPLETED`；
- T001 增加完成记录引用 `governance/completions/TASK-001.completion.json`；
- T002 明确标为 `READY`，执行入口为 `tasks/TASK-002.md`；
- 保留依赖图和各任务原有技术内容，不做无关重写。

## Acceptance criteria

1. `docs/TASK_BACKLOG.md` 顶部导航指向 T002，队列状态 READY；
2. T001 标 COMPLETED 且带完成记录引用；
3. T002 标 READY 且执行入口为 `tasks/TASK-002.md`；
4. 依赖图与各任务技术内容未做无关改写；
5. 全部验证命令通过，baseline 复核 0 failures；
6. 新 commit 存在（非 amend），git status 干净，remote 仍为 0；
7. T002 未开始。

## Verification commands

```powershell
python -m pytest tests/smoke -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
git remote -v
```

（本机执行 verify_project.ps1 时如执行策略允许，可省略 Bypass 旗标；如实记录执行方式。）

## Handoff

完成时必须汇报：实际修改文件、backlog 同步后关键状态、每条验证命令真实结果、
baseline 复核结果、新 commit id、git status 是否干净、remote 是否仍为 0、T002 未开始。
