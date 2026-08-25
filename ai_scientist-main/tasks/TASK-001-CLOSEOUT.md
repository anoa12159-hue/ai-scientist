# TASK-001-CLOSEOUT：T001 正式关闭收尾

> 状态：`COMPLETED`
>
> 所属阶段：T001 收尾（治理动作，非新业务实现）
>
> 依据：项目所有者对 T001 独立复验后的验收意见。

## Goal

在不返工 T001 的前提下补齐可复现性与任务治理收尾：

- 固定 Git 行尾策略，防止其他 Windows 环境 CRLF checkout 破坏冻结基线原始字节哈希；
- 追加不可变的 T001 CompletionRecord，登记验收结果、偏差与哈希；
- 登记“离线”范围偏差（运行时离线，不包含首次开发工具安装）；
- 复跑全部检查与 baseline 哈希；
- 创建本地 T000+T001 checkpoint commit；
- 生成 TASK-002 任务卡（不执行 T002）。

## Why

独立复验结论为 `T001_IMPLEMENTATION = ACCEPTED`、`T001_FORMAL_CLOSEOUT = REQUIRED`。
聊天中的完成报告不能作为后续任务的依据来源，必须落成项目内不可变记录；
同时冻结基线以原始字节 SHA256 为身份，Git 行尾转换会让同一份内容在不同机器上
复算出不同哈希。

## Depends on

- T001 实现已通过项目所有者独立复验；
- `governance/baseline.lock.json` content_hash 保持 `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- 当前工作目录为桌面 canonical 项目根目录。

## Allowed changes

```text
.gitattributes                                        （新增，行尾/字节完整性策略）
tests/smoke/test_project_structure.py                 （更新 T001 guardrail：允许 .gitattributes、
                                                       CRLF 检查、CompletionRecord 校验、
                                                       冻结树 pin 更新）
governance/completions/TASK-001.completion.json       （新增，不可变完成记录，含偏差登记）
tasks/TASK-001-CLOSEOUT.md                            （本卡）
tasks/TASK-002.md                                     （新增，READY，不执行）
.git 本地索引与 checkpoint commit                     （本地 commit，无 remote、无推送）
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/**` 既有文件、`docs/contracts/**`、`docs/adr/**`、
  `tasks/TASK-001.md`、`docs/TASK_BACKLOG.md`（本次未获授权）。
- 不得实现任何 T002+ 业务内容（Schema、类型、Fixture、LangGraph、API、前端）。
- 不得初始化或修改远程仓库、推送、创建 PR。
- 不得修改冻结文件中的历史行尾空白（保持哈希锁定内容原样）。

## Required outputs

- `.gitattributes`：`* -text` 字节完整性策略（checkout 不转换，冻结字节哈希跨平台一致；
  LF 由 `.editorconfig` 与 smoke CRLF 检查强制）；
- 更新后的 T001 smoke guardrail 全绿；
- `governance/completions/TASK-001.completion.json`（ACCEPTED、content_hash 自洽、
  含 `T001-DEV-01` 离线安装偏差等登记）；
- `tasks/TASK-002.md`（READY）；
- 本地 checkpoint commit 包含 T000 基线 + T001 白名单 + 本收尾文件；
- 全部 Verification commands 复跑结果。

## Acceptance criteria

1. `.gitattributes` 存在且 smoke test 验证其字节完整性 pin；
2. 冻结文件与 T001 文件无 CRLF；
3. CompletionRecord content_hash 可复算一致且被 smoke test 校验；
4. 全部检查（pytest/ruff/mypy/import/verify_project.ps1/git）复跑通过；
5. baseline 46 项哈希复核仍全部一致；冻结树 pin 按本次治理变更同步更新；
6. 本地存在 T000+T001 checkpoint commit，无 remote；
7. `tasks/TASK-002.md` 存在且状态 `READY`，T002 未开始。

## Verification commands

```powershell
python -m pytest tests/smoke -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
```

（本机执行 verify_project.ps1 时如执行策略允许，可省略 Bypass 旗标；CI 保留任务卡原始命令。）

## Handoff

完成时必须汇报：

- 实际新增/修改文件；
- 每条 Verification command 的真实结果；
- CompletionRecord 的 content_hash 与冻结树新 pin；
- checkpoint commit 的 id；
- 未运行检查及原因（如 backlog 状态行未更新）；
- T002 开始条件。
