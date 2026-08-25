# TASK-004：Artifact、Ledger 与 Checkpoint 运行内核

> 状态：`READY`
>
> 所属阶段：T004
>
> 执行状态：`NOT_STARTED`

## Goal

在不依赖 SHRGT45 历史业务格式、LangGraph 或 API 的前提下，实现离线、不可变、可追溯、
可恢复的本地运行内核：ArtifactStore、追加式 Ledger、RunRecord/StageRun 持久化和
CheckpointStore。T004 只建立公共运行基础设施，不读取或转换具体 Replay 载荷。

## Why

T003 已冻结真实 Fixture 身份；T005 才会把历史格式适配为公共 Artifact，T006 才会编排
LangGraph。二者都需要先有一个独立于历史目录与编排框架的可靠事实源，以确保内容哈希、
幂等重试、追加事件和中断恢复不会随 Provider 或 UI 实现漂移。

## Depends on

- T003 `COMPLETED`：`governance/completions/TASK-003.completion.json`（ACCEPTED）；
- baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- `docs/contracts/CONTRACTS.md` 0.1.0，重点为 2.5、4.0、4.1、4.4、5.1、8、10；
- `docs/adr/ADR-001-mvp-architecture.md` 第 1、4、7 节；
- T002 已机械化的 ArtifactRef、ArtifactEnvelope、ArtifactLifecycleEvent、ArtifactStateView、
  RunRecord、StageRun、StageContext、CheckpointRef、FailureRecord 与 LineageEdge Schema；
- T003 Case Manifest 与 Fixture 仅作为只读边界证据，不作为 T004 内核的格式依赖。

## Inputs（只读）

```text
governance/baseline.lock.json
governance/completions/TASK-003.completion.json
docs/contracts/CONTRACTS.md
docs/adr/ADR-001-mvp-architecture.md
contracts/artifact-runtime/*.schema.json
contracts/validation-lineage-findings/lineage-edge.schema.json
src/ai_scientist_mvp/domain/{types.py,canonical_json.py}
fixtures/shrgt45/{manifest.json,case-manifest.json,import-audit.json}
```

## Architecture boundary

依赖方向固定为：

```text
domain value/exception rules
        ^
application persistence ports and use cases
        ^
infrastructure local filesystem + SQLite implementations
```

- domain/application 不能 import `langgraph`、`fastapi` 或具体 Replay Adapter。
- ArtifactStore 与 Ledger/Checkpoint 使用端口隔离；MVP 本地实现可使用 Python 标准库
  `sqlite3`，不得因此引入在线服务或新的运行时依赖。
- Artifact authority content 使用按内容寻址的文件存储；运行事实、追加事件、幂等索引和
  Checkpoint 元数据可使用 SQLite。
- 每个 Run 只能写自己的 `runs/<run_id>/`；所有路径由受控根目录和经过校验的 ID 派生。
- Checkpoint 只保存 ArtifactRef 和小型路由/阶段字段，不复制 payload、长 Markdown、CSV、
  图片或源文件字节。

## Required behavior

### ArtifactStore

- 支持 `SOURCE_BYTES` 与 `CANONICAL_JSON` 两种 authority content；JSON 必须复用现有
  RFC8785 canonicalization，不得另写一套序列化规则。
- `content_sha256` 只覆盖 authority content：原始字节或 canonical payload。
- `artifact_id` 与 `ArtifactRef` 一经写入只能绑定一个 `content_sha256/schema_version`。
- 相同 `artifact_id` + 相同内容重复写入是幂等成功；相同 ID + 不同内容必须 Fail Closed。
- ArtifactEnvelope、payload、producer、parent/source refs 和来源字段创建后不可覆盖。
- 内容变化必须创建新 `artifact_id`/revision，并通过 `supersedes_ref`/事件保留旧链。
- 写入采用同目录临时文件、flush/fsync 与原子替换；失败不得留下可被误认成已提交 Artifact
  的半写文件。
- 拒绝绝对路径、`..` 穿越、非法 ID 及逃逸运行根目录的解析结果。

### Append-only Ledger

- 追加并读取 ArtifactEnvelope、ArtifactLifecycleEvent、LineageEdge、RunRecord、StageRun、
  CheckpointRef 和 FailureRecord 等版本化事实。
- 追加对象在写入前验证 content hash/authority hash 与关键引用；未知或冲突身份 Fail Closed。
- Ledger API 不提供原地 update/delete；本地 SQLite 实现必须以约束或触发器阻止绕过 API 的
  `UPDATE/DELETE`。
- Artifact 当前生命周期、Run/Stage 当前执行状态属于按追加记录计算的投影，不得回写旧事实。
- Ledger 提交与幂等索引在单事务内完成；重试相同事件不重复追加，冲突重试明确失败。

### Run、Stage 与 Checkpoint

- 持久化 Schema 合法、content_hash 自洽的 RunRecord 与 StageRun 快照/事实；
  `StageAttemptKey={run_id,stage_id,attempt,stage_configuration_ref}` 保持稳定。
- 同一 `run_id` 的目录和数据库命名空间隔离，绝不清理或覆盖其他 Run。
- CheckpointRef 必须绑定 `run_id` 和完整 ArtifactRef；恢复时逐一复核引用内容仍存在且哈希一致。
- 恢复只能返回最后一个完整提交的 Checkpoint；临时文件、未提交事务和无效尾记录不得被采用。
- 中断后重试同一 StageAttemptKey 和相同输入/配置必须幂等；输入、配置、Provider 版本或内容
  哈希变化时必须形成新尝试/新 Artifact，不得复用旧成功结果。

## Allowed changes

```text
src/ai_scientist_mvp/domain/**
src/ai_scientist_mvp/application/**
src/ai_scientist_mvp/infrastructure/**
tests/unit/**
tests/integration/**
tests/smoke/test_project_structure.py
```

允许修改既有 `__init__.py` 以导出本任务公共类型；不得修改 `domain/types.py` 或
`domain/canonical_json.py` 的冻结语义。若发现契约/类型缺口，停止并登记后续任务或 Contract
Change Request，不得在 T004 内扩张 Schema。

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/**`、`docs/contracts/**`、`docs/adr/**`、`contracts/**`、
  `fixtures/**`、`tasks/**`、`docs/TASK_BACKLOG.md`、`pyproject.toml`、CI 或 CompletionRecord。
- 不得实现或 import LangGraph、Provider/Replay Adapter、历史 Markdown/CSV/ZIP 解析、
  S01-S07 业务节点、人工 Gate、API、FastAPI、前端或 RunReadModel。
- 不得执行历史脚本、Notebook、嵌套 ZIP 或 LLM 生成代码。
- 不得访问网络、API Key、`.env` 或引入外部数据库/服务。
- 不得硬编码机器绝对路径，不得写入 Fixture 或源资料目录。
- 不得创建 remote、push 或 PR；不得启动 T005。

## Required outputs

1. 明确的 application persistence ports，调用方不依赖 SQLite/文件布局。
2. 本地不可变 ArtifactStore，实现 bytes/canonical JSON authority 与原子幂等写入。
3. 追加式 Ledger，实现身份约束、不可更新/删除和确定性查询。
4. RunRecord/StageRun 持久化与 StageAttemptKey 幂等索引。
5. 只含引用的小型 CheckpointStore，以及完整性复核和恢复。
6. 每 Run 隔离的目录布局与路径逃逸防护。
7. 覆盖正常、冲突、篡改、崩溃残留、事务回滚、重试和恢复的单元/集成测试。

## Acceptance criteria

1. 相同 Artifact 身份与内容重复写入不产生重复副作用；相同 ID 的不同 hash 被拒绝。
2. bytes 与 canonical JSON 的 hash authority 明确分离，读取时逐次或按可信索引复核哈希。
3. ArtifactEnvelope 和所有 Ledger 事实不可原地覆盖；直接 SQLite `UPDATE/DELETE` 也被拒绝。
4. 合法生命周期事件可投影，非法转换、过期 ArtifactRef 或缺失父项 Fail Closed。
5. 两个 Run 的目录、Ledger 记录和 Checkpoint 完全隔离。
6. Checkpoint 不含大 payload；恢复后所有 ArtifactRef、父子血缘和内容哈希保持一致。
7. 模拟临时文件、提交前异常、事务回滚和进程重开后，只恢复完整提交状态。
8. StageAttemptKey 相同且输入/配置一致时幂等；冲突输入或配置不复用旧结果。
9. 代码中无 LangGraph/FastAPI/Replay 格式依赖、机器绝对路径、网络或密钥访问。
10. 新增测试及既有 smoke/fixture/contract 全部通过，baseline/Fixture 字节无变化。

## Verification commands

在项目根目录执行：

```powershell
python -m pytest tests/unit tests/integration tests/smoke tests/fixtures tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
git remote -v
```

## Stop conditions

- 冻结契约与 Schema 无法表达实现所需身份或状态，或两者语义冲突；
- 需要修改 T003 Fixture、补造来源身份或执行历史脚本才能完成；
- 需要引入新的外部依赖、服务、网络、密钥或破坏性数据操作；
- 两种持久化解释会导致不同的 Artifact 身份、生命周期或恢复语义；
- 需要提前实现 T005+ 的 Replay、LangGraph、API 或前端内容。

## Handoff

完成时必须汇报：端口与实现文件、实际存储布局、SQLite 表/不可变约束、hash authority、
幂等键、原子写入与恢复策略、全部反例测试、每条验证命令真实结果、未运行项目及原因、
新 commit id、git status、remote 状态，并明确 T005 是否具备开始条件。不得自行关闭 T004。
