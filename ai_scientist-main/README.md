# AI Scientist MVP

SHRGT45 历史研究回放系统的工程仓库。本仓库受根目录 `AGENTS.md` 与冻结契约
（`docs/PROJECT_CHARTER.md`、`docs/contracts/CONTRACTS.md` 版本 `0.1.0`）约束：
一次只执行一张任务卡；科学状态保持 `NOT_EVALUATED` / `DEVELOPMENTAL`，
正式数据执行 `NOT_AUTHORIZED`。

## 当前状态

- T000 共同决策与契约冻结：`COMPLETED`
- T001–T005 契约、Fixture、存储内核和 Replay Provider：`COMPLETED`
- T006 LangGraph Replay 首次构建：`IMPLEMENTED_PENDING_CLOSEOUT`
- T006 已实现 S01–S07、S05/S06 并行、人工中断、跨进程恢复、有限重试和离线 CLI；正式
  CompletionRecord 尚未创建，科学状态仍为 `NOT_EVALUATED` / `DEVELOPMENTAL`
- T007 API、T008 前端、T009 端到端验收和 T010 演示包：尚未开始

## 目录布局

```text
src/ai_scientist_mvp/    Python 包（src 布局）
  domain/                  领域契约（T002+）
  application/             应用服务（T004+）
  infrastructure/          存储 / 台账基础设施（T004+）
  providers/               回放与未来在线 Provider（T005+）
  workflow/                工作流编排（T006，首次构建完成）
  api/                     后端 API（T007+）
web/                        薄前端（T008+）
contracts/                  JSON Schema 等机器契约（T002+）
fixtures/shrgt45/           Fixture 清单与快照（T003+）
tests/                      自动化测试
governance/                 冻结治理与基线（只读）
docs/                       章程、契约、ADR（只读）
tasks/                      任务卡（一次执行一张）
```

## 本地校验（离线，无需 API Key）

需要 Python 3.11+。虚拟环境目录（如 `.venv`）不提交。下面命令使用 POSIX shell；Windows
只需将虚拟环境激活命令替换为对应 shell 语法。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest tests/smoke -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
```

以上命令是系统无关的最小校验入口。`scripts/verify_project.ps1` 是历史 Windows 辅助脚本，
不属于 Replay 运行时依赖，也不是 Linux 验收阻塞项；CI 可直接执行同等的 pytest、Ruff、mypy
和导入检查。

## 数据与安全边界

- 回放完全离线运行，无需任何 API Key；`.env.example` 只含变量名和安全占位值。
- 不提交密钥、`.env`、虚拟环境、缓存、运行产物或机器绝对路径。
- 移交资料库只读；Fixture 由 T003 按已批准白名单导入，T001 不导入。

## T006 Replay 演示

工作流入口为 `ai-scientist-replay`，只接受离线 `REPLAY` 运行。首次执行在
`FIXTURE_IMPORT_REVIEW` 等待人工 DecisionRecord，批准后才会生成绑定 S05/S06 的报告。
运行目录位于 `runs/<run-id>/`，不会写入 Graph State 之外的大型载荷，也不会产生科学支持或发布授权。
