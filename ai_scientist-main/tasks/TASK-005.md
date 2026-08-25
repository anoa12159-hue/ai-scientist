# TASK-005：Replay Adapter 与确定性校验（首次构建）

> 状态：`READY`
>
> 所属阶段：T005
>
> 执行状态：`NOT_STARTED`
>
> 执行方式：执行同事只负责本任务的第一次构建；交回后由主 Agent 独立审查、直接修正、
> 补充反例测试并完成验证。执行同事不得自行关闭本任务或启动 T006。

## Goal

在 T004 已接受的 Artifact/Store/Ledger 边界之上，建立与历史目录格式隔离的 Replay Adapter
层。Adapter 将 T003 冻结的 SHRGT45 资产转换为公共 ArtifactEnvelope、领域摘要、ValidationReport、
CompatibilityFinding/GapFinding 和精确绑定的 `FIXTURE_IMPORT_REVIEW` DecisionRequest。

本任务的目标是“忠实回放和可检查的确定性输出”，不是重新训练模型、生成新的科学结论、
执行历史脚本或实现 LangGraph。

## Why

T003 只冻结了来源资产身份和运行投影，T004 只提供通用持久化内核。T005 将两者通过明确
Provider 接口接合，使 T006 可以只依赖公共 ArtifactRef 和小型状态，而不依赖 Markdown、CSV、
图片、ZIP 或历史目录布局。

## Depends on

- T004 CompletionRecord（ACCEPTED）；
- `src/ai_scientist_mvp/infrastructure/storage.py` 的四个持久化端口；
- `fixtures/shrgt45/manifest.json`、`case-manifest.json`、`import-audit.json`；
- T002 已接受的 Artifact、Finding、Validation、Decision Schema；
- `docs/contracts/CONTRACTS.md` 4.1、4.3、5、6 和 7 节；
- 默认 S04 运行输入只能是 `s04.demo0814` 的 43 个成员，`s04.source0808` 只可用于
  provenance/audit 查询。

## Architecture boundary

```text
T003 Fixture manifest / inert historical bytes
                 |
                 v
       Replay Adapter + deterministic validator
                 |
                 v
        T004 ArtifactStore / Ledger ports
                 |
                 v
        public ArtifactRef + domain summaries + Findings
```

- `providers` 可以读取 T003 登记的只读字节，但不能执行历史 `.py`、Notebook、嵌套 ZIP 或动态加载；
- Provider 不得 import `langgraph`、`fastapi`、网络客户端、LLM SDK 或读取 `.env`；
- Adapter 不得把完整长文、CSV、图片或原始字节放进 Graph State/摘要对象；大内容只能作为
  ArtifactStore 中的 authority content，通过 ArtifactRef 访问；
- 所有生成对象必须使用 T004 Store 写入，不能直接拼接 Ledger 行或绕过 Schema 校验；
- `PASS` 只表示定义的结构/一致性检查通过，不得转写成科学支持；MVP 科学状态保持
  `NOT_EVALUATED / DEVELOPMENTAL / NOT_AUTHORIZED / NOT_READY`。

## First-build scope

首次构建至少应提供以下可替换 Protocol 和离线实现（命名可等价，但职责不可减少）：

1. `ReplayAssetCatalog`：加载并校验 manifest、case-manifest、import-audit，解析
   `VersionedRef`，校验来源相对路径、字节数和 SHA256；默认 S04 只暴露 0814 的 43 个成员。
2. `ReplayCandidateProvider`：生成 S01 `CandidateSnapshot`，明确
   `selection_method=EXPERT_PRESELECTED`、`ranking_status=NOT_SYSTEM_RANKED`，不得声称系统
   完成候选排序。
3. `ReplayMechanismProvider`、`ReplayHypothesisProvider`、`ReplayDataProvider`、
   `ReplayCounterexampleProvider`、`ReplayMagnetogramQAProvider`：从已登记历史来源生成
   最小领域摘要或明确的 `NOT_IMPLEMENTED/NOT_EVALUATED` Gap，不得补造流程 2/3 缺失的
   机器五件套输入，也不得把历史结论升级为新的科学结论。
4. `ReplayArtifactImporter`：将来源字节写为 `IMPORTED + SOURCE_BYTES` Artifact，将确定性
   摘要写为 `DERIVED/NATIVE + CANONICAL_JSON` Artifact，并保存 `parent_refs`、
   `derived_from_refs`、`source_asset_refs` 和精确版本引用。
5. `DeterministicValidator`：对 Artifact/VersionedRef/来源字节/必要字段执行确定性检查，
   生成契约合法的 `ValidationReport`；检查通过只表示结构通过。
6. `ReplayFindingFactory`：根据 Case Manifest 的 declared finding specs 和实际生成的
   ArtifactRef 创建 CompatibilityFinding/GapFinding，保持 10 个可接受 Finding、2 个信息
   Gap 及所有 Fail-Closed 类别的代码和 rationale；未知哈希、未知 schema、未解析引用必须
   直接失败。
7. `FixtureImportDecisionRequestFactory`：在实际 ArtifactRef、FindingRef、必要的
   StageAttemptKey 和精确内容哈希齐备后生成 `FIXTURE_IMPORT_REVIEW` 的 DecisionRequest；
   不生成 DecisionRecord，不自动批准，不绕过人工 Gate。
8. `DevelopmentalReportRenderer`：只生成公共 `ResearchSummary`/`ReportManifest` 所需的
   小型、可追溯结构；报告必须保留开发性和未授权状态，并将长内容作为 ArtifactRef。

## Required outputs

- `src/ai_scientist_mvp/providers/replay_protocols.py`（Provider/Validator/Renderer Protocol）；
- `src/ai_scientist_mvp/providers/shrgt45_replay.py`（只读 Fixture Catalog、Importer 和各
  Replay Provider 的首次实现）；
- `src/ai_scientist_mvp/providers/replay_validation.py`（确定性校验与 Finding/DecisionRequest
  工厂；不得引入科学模型）；
- `src/ai_scientist_mvp/application/replay_service.py`（面向 T004 ports 的组装用例；不实现图）；
- `tests/unit/test_replay_adapters.py` 与 `tests/integration/test_replay_adapters.py`；
- 必要时只更新 `tests/smoke/test_project_structure.py` 的允许文件清单，不得削弱现有冻结、
  密钥、绝对路径、网络和框架依赖护栏；
- `tasks/TASK-005.md` 本身不由执行同事修改为 COMPLETED，也不生成 CompletionRecord。

## Required deterministic behavior

1. 同一 manifest、同一 RunConfiguration 和同一来源字节重复运行，ArtifactRef、
   content hash、FindingRef 和 ValidationReport 内容完全一致；
2. 0814 混入 0808、来源 SHA256 改变、manifest 路径不存在、VersionedRef 未解析、
   schema_version 不支持、未知 Finding code、Fail-Closed code 被标记为可接受时均拒绝；
3. 适配器输出的 `CandidateSnapshot` 明确是专家预选种子，不得出现系统排序字段的伪造值；
4. 历史结构 PASS、导入成功或报告渲染成功都不能改变 `scientific_verdict`；
5. DecisionRequest 必须绑定本次运行实际生成的 ArtifactRef/FindingRef/StageAttemptKey，
   不能只引用字符串 ID，也不能在 T005 自动形成授权记录；
6. 运行时默认输入只来自 0814，0808 查询必须显式标记为 provenance/audit 边界；
7. 适配器失败不得留下半提交 Artifact、伪造 Finding 或部分批准状态。

## Allowed changes for the first build

```text
src/ai_scientist_mvp/providers/**
src/ai_scientist_mvp/application/replay_service.py
tests/unit/test_replay_adapters.py
tests/integration/test_replay_adapters.py
tests/smoke/test_project_structure.py
tasks/TASK-005.md（仅在发现首次构建边界错误时登记，不得自行关闭）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`、
  `baseline.lock.json`、T001-T004 CompletionRecord、T004 源码和 T005+ 任务卡之外的治理文件；
- LangGraph 图、节点路由、人工 Gate 执行、API、FastAPI、前端、网络、LLM Provider、密钥；
- 修改、重写、规范化或删除 T003 历史字节；
- 执行历史脚本/Notebook/ZIP，或根据缺失输入补造验证通过证据；
- 通过裸路径、裸字符串 ID 或直接 SQLite 写入绕过公共 Artifact/Ref/Schema；
- 关闭 T005、创建 CompletionRecord、启动 T006、创建 remote 或 push。

## Verification commands for the first build

```powershell
python -m pytest tests/unit/test_replay_adapters.py tests/integration/test_replay_adapters.py -q
python -m pytest tests/unit tests/integration tests/smoke tests/fixtures tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
git remote -v
```

首次构建报告必须如实列出实际测试数量、未执行的历史内容、任何偏差、提交 ID、工作区和
remote 状态；报告交回后由主 Agent 负责全部修正和最终验收。

## Stop conditions

- T003 manifest 无法表达某个来源或公共 Schema 无法表达适配器身份；
- 需要修改冻结契约、Fixture 字节、baseline 或补造历史输入；
- 需要执行历史脚本、访问网络/LLM/API Key 或实现 LangGraph/API；
- 需要把 `NOT_EVALUATED`、`DEVELOPMENTAL`、`NOT_AUTHORIZED` 之外的科学/发布状态写入 MVP；
- 需要将 0808 作为默认 S04 运行输入，或将 0814/0808 合并去重；
- 需要绕过 T004 Store 或改变 Artifact/Run/Checkpoint 语义。

## Handoff

本卡只授权 T005 首次构建。执行同事完成首次实现后停止并交回报告；主 Agent 随后直接审查、
修正和验证。T006 在 T005 正式 closeout 前不得开始。
