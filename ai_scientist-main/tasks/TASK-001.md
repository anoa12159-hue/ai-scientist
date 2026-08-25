# TASK-001：Repository And Execution Guardrails

> 状态：`READY`
>
> 所属阶段：T001

## Goal

在桌面 canonical 项目根目录建立最小、可测试、离线可运行的工程骨架和统一校验入口，不实现任何 S01-S07 业务流程。

## Why

T001 为后续 Schema、Fixture、Artifact、LangGraph、API 和前端任务提供稳定目录、Python 测试入口和文件边界。它必须保持足够薄，避免在公共 Schema 尚未机械化前产生业务模型。

## Depends on

- T000 `COMPLETED`
- `governance/baseline.lock.json` content hash：`55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`
- `docs/contracts/CONTRACTS.md` 版本：`0.1.0`
- `governance/workflow.json` 版本：`0.1.0`
- `D-001=A` 至 `D-008=A` DecisionRecord 全部存在且内容哈希有效
- 必须从桌面 canonical 项目目录重新打开 Codex 后执行，不得在旧 C 盘会话根目录实现

## Inputs

- `AGENTS.md`
- `governance/baseline.lock.json`
- `docs/PROJECT_CHARTER.md`
- `docs/contracts/CONTRACTS.md`
- `docs/adr/ADR-001-mvp-architecture.md`
- `docs/contracts/SCHEMA_CATALOG.md`

所有输入在本任务中只读。

## Allowed changes

允许新增或修改：

```text
.gitignore
.env.example
.editorconfig
README.md
pyproject.toml
.github/workflows/ci.yml
scripts/verify_project.ps1
src/ai_scientist_mvp/__init__.py
src/ai_scientist_mvp/py.typed
src/ai_scientist_mvp/domain/__init__.py
src/ai_scientist_mvp/application/__init__.py
src/ai_scientist_mvp/infrastructure/__init__.py
src/ai_scientist_mvp/providers/__init__.py
src/ai_scientist_mvp/workflow/__init__.py
src/ai_scientist_mvp/api/__init__.py
web/README.md
contracts/README.md
fixtures/shrgt45/README.md
tests/smoke/test_project_structure.py
```

若某个空目录需要保留，只能使用该目录的简短 `README.md` 或 Python `__init__.py`，不得添加业务实现。

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/**`、`docs/contracts/**`、`docs/adr/**`、`tasks/TASK-001.md`。
- 不得复制或导入任何 Fixture；T003 才负责实际 Fixture Manifest 和快照。
- 不得生成正式 JSON Schema 或领域 Python Model；T002 才负责。
- 不得实现 LangGraph 节点、Provider、ArtifactStore、Ledger、Checkpoint、API 路由或前端页面。
- 不得安装或调用 LangGraph、在线模型、JSOC、数据库服务或前端包。
- 不得读取源资料库中的 `.env`、`.venv`、脚本入口或嵌套 ZIP。
- 不得把机器绝对路径写入 Python、配置模板、CI 或测试。
- 不得初始化或修改远程仓库、推送代码、创建 PR 或提交凭证。

## Required outputs

- `src/` 布局的 Python 3.11+ 包骨架。
- `domain/application/infrastructure/providers/workflow/api` 清晰目录边界。
- `web/`、`contracts/`、`fixtures/shrgt45/` 占位边界说明。
- 无密钥的 `.env.example`，只允许变量名和安全占位值。
- `pyproject.toml` 中的 pytest、ruff 和静态类型检查入口；不添加业务运行依赖。
- 单个 PowerShell 统一校验入口 `scripts/verify_project.ps1`。
- Smoke test 验证必要路径存在、冻结目录未被任务改写、项目文件不含被禁止的绝对源路径或疑似密钥值。
- 基础 CI 调用与本地相同的校验命令；若当前环境无法验证 CI 服务，只验证 YAML 和本地等价命令。

## Acceptance criteria

1. 在断网、无 API Key 环境中可以创建干净虚拟环境并运行基础检查。
2. `python -m pytest tests/smoke -q` 通过。
3. `python -m ruff check .` 通过。
4. 配置的静态类型检查命令通过。
5. 将 `src` 加入导入路径后可以导入 `ai_scientist_mvp`。
6. 没有 LangGraph 业务图、API 路由、前端页面、Schema 或 Fixture 文件提前进入实现。
7. Git diff 不包含源资料字节、密钥、`.env`、虚拟环境、缓存、运行产物或机器特定绝对路径。
8. `governance/baseline.lock.json`、正式契约和 DecisionRecord 的哈希仍与 T001 开始时一致。

## Verification commands

在项目根目录执行，具体虚拟环境目录由实现选择但不得提交：

```powershell
python -m pytest tests/smoke -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
```

若 `python` 不是 Python 3.11+，必须停止并报告环境要求，不得静默改用来源项目的解释器或 `.venv`。

## Stop conditions

- baseline、契约、Workflow 或任一 D-001 至 D-008 DecisionRecord 哈希不匹配；
- 当前工作目录不是桌面 canonical 项目根目录；
- canonical 项目已有与本任务冲突的用户修改且无法保留；
- 需要修改冻结文件、扩大路径白名单或提前实现 T002+ 内容才能通过验收；
- 需要联网下载依赖但当前授权或网络策略不允许；
- Python 3.11+ 不可用，且没有独立于来源项目的可用解释器。

## Handoff

完成时必须汇报：

- 实际新增/修改文件；
- 每条 Verification command 的真实结果；
- Python 和工具版本；
- baseline/contract/decision 哈希复核结果；
- 未运行检查及原因；
- T002 是否具备开始条件。
