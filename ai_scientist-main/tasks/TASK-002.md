# TASK-002：Schema 与状态契约机械化

> 状态：`READY`
>
> 所属阶段：T002

## Goal

把已冻结的公共语义契约机械化：以 JSON Schema 2020-12 作为机器可执行规范源，
共享定义通过 `$ref` 复用；Python 类型由 Schema 生成，或由 CI 一致性测试证明无漂移。
不得让手写 Python 类型反向、静默改变 Schema 语义。

## Why

T001 已建立骨架与护栏。在写入任何 Fixture、Artifact、Provider 或工作流代码之前，
必须先有可执行的契约：内容身份（RFC8785 JCS + UTF-8 + SHA256）、正交状态枚举、
Finding 处置边界与 Golden Fixture，否则后续任务无法做确定性校验与 Fail Closed。

## Depends on

- T001 `COMPLETED`：`governance/completions/TASK-001.completion.json`（ACCEPTED）
- `docs/contracts/CONTRACTS.md` 版本 `0.1.0`（冻结语义规范源）
- `docs/contracts/SCHEMA_CATALOG.md`（`ACCEPTED_INPUT`）
- `governance/baseline.lock.json` content_hash：`55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`
- T001 smoke guardrail（`tests/smoke/test_project_structure.py`）不得回归

## Inputs

- `docs/contracts/CONTRACTS.md`
- `docs/contracts/SCHEMA_CATALOG.md`
- `docs/adr/ADR-001-mvp-architecture.md`
- `governance/workflow.json`
- `governance/research-question.json`
- `tests/smoke/test_project_structure.py`

所有输入在本任务中只读。

## Allowed changes

允许新增或修改：

```text
contracts/                              （新增 SCHEMA_CATALOG 所列 *.schema.json 与共享定义）
contracts/README.md                     （更新为 Schema 索引说明）
src/ai_scientist_mvp/domain/            （Schema 派生或经一致性测试约束的 Python 类型）
tests/contract/                         （契约与 Golden Fixture 测试）
pyproject.toml                          （仅新增契约测试所需依赖，如 jsonschema）
tests/smoke/test_project_structure.py   （仅在 T002 合法引入 Schema 后更新相应 guardrail 断言）
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/**`、`docs/contracts/CONTRACTS.md`、
  `docs/contracts/SCHEMA_CATALOG.md`、`docs/adr/**`、`tasks/**`。
- 不得导入或复制任何 Fixture；T003 才负责 Fixture Manifest 与快照。
- 不得实现 LangGraph 节点、Provider、ArtifactStore、Ledger、Checkpoint、API 路由或前端页面。
- 不得安装或调用 LangGraph、在线模型、JSOC、数据库服务或前端包。
- 不得把机器绝对路径写入 Python、Schema、配置、CI 或测试。
- 不得把 T001 smoke test 中的简化 JCS 函数提升为生产哈希函数；T002 必须引入
  经验证的 RFC 8785 实现，并以跨语言 Golden Fixture 验证（与 T000 已锁定
  content_hash 对照一致）。
- 不得以手写 Python 类型扩大或缩小冻结契约语义；语义冲突必须停止并报告。

## Required outputs

- `contracts/` 下按 `SCHEMA_CATALOG.md` 分组的 JSON Schema 2020-12：
  - Foundation：`versioned-ref`、`research-question`、`run-configuration-snapshot`、
    `source-asset-ref`、`source-package-ref`、`replay-case-manifest`；
  - Artifact And Runtime：`artifact-ref`、`artifact-envelope`、`artifact-lifecycle-event`、
    `artifact-state-view`、`run-record`、`stage-run`、`stage-context`、`checkpoint-ref`、
    `failure-record`；
  - Validation, Lineage And Findings：`validation-report`、`lineage-edge`、
    `compatibility-finding`、`gap-finding`、`finding-disposition`、`finding-state-view`；
  - Governance And Release：`decision-option`、`decision-request`、`decision-record`、
    `authorization-record`、`project-review-ack`、`release-disposition`、`release-state-view`；
  - Domain And Query Projections：`candidate-snapshot`、`mechanism-snapshot`、
    `hypothesis-snapshot`、`verification-snapshot`、`counterexample-snapshot`、
    `magnetogram-qa-snapshot`、`research-summary`、`report-manifest`、`run-read-model`；
- 集中定义的正交状态枚举、D-008 可接受 Finding code 与 Fail Closed 类别
  （共享定义经 `$ref` 复用，不得复制后漂移）；
- `src/ai_scientist_mvp/domain/` 中由 Schema 生成或经 CI 一致性测试约束的 Python 类型；
- Golden Contract Fixture：每个 Schema 的最小合法样例、关键非法样例、
  RFC8785 跨语言 Golden Hash；
- 契约测试：
  - 正交状态不能混用；
  - V2.2 不得静默冒充 V2.3；
  - Finding/Artifact/配置哈希变化后旧决定不适用；
  - `FINAL_REPLAY_REVIEW` 不得产生 ReleaseDisposition；
  - S05/S06 任一必需分支失败时不得生成最终 ReportManifest。

## Acceptance criteria

1. `SCHEMA_CATALOG.md` 列出的每个 Schema 均存在且通过 2020-12 meta 校验。
2. 共享定义通过 `$ref` 复用，没有复制后漂移的重复定义。
3. 契约测试证明正交状态不能混用；`scientific_verdict`、`result_maturity`、
   `authorization_status` 等保持契约规定枚举与 MVP 当前值。
4. 内容身份按 `RFC8785-JCS + UTF-8 + SHA256` 验证，并与 T000 已锁定的治理哈希
   （如 D-001..D-008 content_hash）一致。
5. Python 类型由 Schema 生成，或由 CI 一致性测试证明与 Schema 无漂移。
6. Golden Fixture 覆盖合法、非法与关键边界（V2.2/V2.3、旧决定失效、
   ReleaseDisposition 边界、S05/S06 Join）。
7. `python -m pytest tests/smoke tests/contract -q` 通过；`ruff`、`mypy`、import 检查
   与 `verify_project.ps1` 不回归。
8. Git diff 不包含密钥、`.env`、虚拟环境、缓存、运行产物或机器特定绝对路径。

## Verification commands

在项目根目录执行（使用 T001 建立的独立 venv，不提交）：

```powershell
python -m pytest tests/smoke tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
```

若 `python` 不是 Python 3.11+，必须停止并报告环境要求，不得静默改用来源项目的
解释器或 `.venv`。

## Stop conditions

- 需要修改冻结契约、ADR、governance 或 T001 CompletionRecord 才能通过验收；
- RFC8785 实现与 T000 已锁定 content_hash 无法一致；
- Schema 之间或 Schema 与冻结契约语义冲突，且无法在任务范围内解决；
- 需要 Fixture、业务运行时、联网服务或密钥才能完成测试；
- Python 3.11+ 或独立 venv 不可用。

## Handoff

完成时必须汇报：

- 实际新增/修改文件；
- 每条 Verification command 的真实结果；
- RFC8785 实现/验证方式与跨语言 Golden Hash 证据；
- Python 类型与 Schema 的一致性证据；
- T001 guardrail（smoke）是否回归；
- 未运行检查及原因；
- T003 是否具备开始条件。
