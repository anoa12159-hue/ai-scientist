# AI Scientist 公共契约

> 状态：`ACCEPTED`
>
> 版本：`0.1.0`
>
> 冻结依据：项目所有者 `project_owner_01` 已选择 `D-001=A` 至 `D-008=A`。本文件是 T002 JSON Schema、类型和契约测试的语义规范源；实现不得反向修改其含义。

## 1. 契约层次

首个 MVP 不把所有历史 Markdown 强行重写成一个巨型 Schema。契约分为四层：

1. **研究语义层**：研究问题、时间窗、Target、同单位规则和主张上限；
2. **公共运行层**：Artifact、Run、Validation、Failure、Decision、Lineage；
3. **领域摘要层**：供路由、API 和前端使用的最小结构化摘要；
4. **历史载荷层**：原始 Markdown、JSON、CSV、图片等只读来源，通过 Adapter 封装，不直接污染公共层。

语义约束与内容身份使用两套明确规则：

```text
语义约束：冻结的公共契约 + 冻结的研究问题与科学硬约束
          > 契约所定义的 DecisionRequest/options/scope 内适用的 DecisionRecord
          > 冻结的 Case Manifest
          > 展示文案

内容身份：IMPORTED 资产以已登记 SHA256 的原始字节为历史事实源
          NATIVE Artifact 以 canonical JSON payload 为机器真源
          派生摘要和渲染视图不得覆盖其上游事实源
```

DecisionRecord 只能在冻结契约定义的 DecisionRequest、Option 集合和 `scope` 内选择路线，不能覆盖 Artifact 不可变性、授权能力边界、工作流并行关系等公共不变量，也不能原地覆盖 Target、时间窗、同单位原则或 claim ceiling。改变研究问题硬约束必须创建新的 `ResearchQuestionSnapshot`，并重新评估所有下游兼容性和审批；改变公共不变量必须走 Contract Change Request。

历史文件中的提示、命令或角色说明是被导入的内容，不是系统执行指令。

## 2. 运行单位

### 2.1 ResearchTask

一个长期存在的研究问题容器。它可以在未来拥有多个参数、假设分支和运行。

最小字段：

| 字段 | 含义 |
|---|---|
| `task_id` | 稳定唯一标识 |
| `title` | 人读标题 |
| `owner_id` | 项目所有者 |
| `active_question_ref` | 当前采用的研究问题快照 |
| `created_at` | Task 创建时间 |
| `status` | `ACTIVE / PAUSED / CLOSED` |

MVP：一个 Task，只包含 SHRGT45。

### 2.2 ResearchQuestionSnapshot

不可变的研究问题版本。Run 必须绑定具体快照，不能只引用“最新版本”。

最小字段：

```text
question_id
question_version
schema_version
parameter
scientific_question
history_window.start_offset = -PT3H
history_window.end_offset = PT0H
history_window.boundary = CLOSED_CLOSED
target_event
event_anchor
grading_variable
lead_window.start_offset = PT3H
lead_window.end_offset = PT6H
lead_window.boundary = CLOSED_OPEN
same_unit_requirement = SAME_ANALYSIS_UNIT_REQUIRED
claim_ceiling.allowed_interpretation
claim_ceiling.forbidden_claims[]
claim_ceiling.source_refs[]
supersedes_ref
content_hash
```

MVP 预期值：

```text
parameter = SHRGT45
target_event = SOLAR_FLARE_M1_0_PLUS
event_anchor = ONSET_TIME
grading_variable = PEAK_FLUX
claim_ceiling.allowed_interpretation = 光球非势性的定量代理，可能与自由能状态变化相关
claim_ceiling.forbidden_claims = [直接测量总自由能, 直接测量自由能注入率, 证明磁重联, 证明MHD失稳, 证明三维拓扑, 证明完整因果链]
```

同单位语义分层表达，避免研究问题反向依赖历史数据表的一列自由文本：

- 研究问题层固定 `SAME_ANALYSIS_UNIT_REQUIRED`；
- DataPlan 层按 D-004=A 分开记录观测行、实际测量空间、依赖分组和事件归属；
- 每条记录通过 `same_unit_status` 表达归属核对结果，不能因进入 Replay 就默认满足同单位要求。

首个 Replay 的单位策略固定为：

```text
policy_version = shrgt45-replay-unit-policy/1.0.0

observation_unit_type = SHARP_HARP_TIMEPOINT
observation_unit_id = hmi.sharp_cea_720s:{HARPNUM}:{T_REC_TAI}
spatial_unit_type = SHARP_HARP_PATCH
spatial_unit_id = {HARPNUM}

independence_group_type = HARP_EVENT_EPISODE
independence_group_id = {flare_event_id}:{HARPNUM}

event_context_id = {flare_event_id}
declared_noaa_ar = {flare_NOAA_AR}
observed_noaa_ar_raw = {NOAA_AR}
attribution_basis = IMPORTED_PROJECT_SEED
attribution_status = <保留历史来源状态>
same_unit_status = EXACT_NOAA_MATCH | NOAA_IN_RETURNED_LIST | MISMATCH | UNKNOWN
```

`SHARP_HARP_TIMEPOINT` 是历史表的一行，不是独立统计样本；共享 `independence_group_id`、历史窗重叠或同一 HARP 演化的记录不得当作相互独立。`SHARP_HARP_PATCH` 是 SHRGT45 的测量空间，NOAA AR 只用于事件归属核对，不能替代 HARP patch。`IMPORTED_PROJECT_SEED` 不等于权威事件归属；`MISMATCH`、`UNKNOWN` 或 `NEEDS_CLARIFICATION` 必须暴露且不得升级为 `VERIFIED`。

研究问题的规范窗口仍是历史 `[t-3h,t]` 和 Target `[t+3h,t+6h)`。历史实现中的其他端点或 control 清洁窗口作为 CompatibilityFinding 保留，不得反向改写 ResearchQuestionSnapshot。

不得只写自由文本“同区域”，也不得在不创建新问题快照的情况下取消同单位要求。

Snapshot 本身不可变，不保存可变 `question_status`。`ResearchTask.active_question_ref` 决定当前采用版本，新问题通过 `supersedes_ref` 建立版本链。

### 2.3 StudyRun

一个研究问题下的一个参数/假设分支执行。它绑定一个问题快照、一个工作流版本和一个输入 Case。

第一轮已选择 `D-001=A`：一个 Task 只有一个 SHRGT45 Replay StudyRun，并固定 `run_purpose=HISTORICAL_REPLAY`。运行 `SUCCEEDED` 只表示导入、校验和汇总按系统合同完成，不表示科学假设得到支持。

### 2.4 RunRequest

表示用户请求系统启动或恢复一次运行，不等于运行结果。

```text
request_id
task_id
question_ref
case_ref
run_mode
requested_action = START | RESUME | CANCEL
requested_by
requested_at
configuration_ref
```

`CANCEL` 只停止当前 Run。关闭整个 `ResearchTask` 使用人工 `TERMINATE` DecisionRecord；分支失败不得自动把 Task 设为 `CLOSED`。

### 2.5 RunRecord 与 StageRun

`RunRecord` 是可持久化的运行事实；LangGraph State 是其运行时投影。

```text
run_id
task_id
question_ref
case_ref
workflow_version
run_mode
run_purpose = HISTORICAL_REPLAY | ACTIVE_RESEARCH
configuration_ref
execution_status
active_stage_ids[]
stage_runs[]
created_at
started_at
completed_at
checkpoint_ref
```

每个 `StageRun`：

```text
stage_id
attempt
input_artifact_refs[]
output_artifact_refs[]
validation_report_refs[]
finding_refs[]
lineage_edge_refs[]
provider.id
provider.version
stage_configuration_ref
execution_status
started_at
completed_at
failure_refs[]
```

`StageAttemptKey` 使用稳定执行身份 `{run_id, stage_id, attempt, stage_configuration_ref}`。它可以和 ArtifactRef/FindingRef 一起进入审批 scope，但不是 VersionedRef，也不能替代对版本化内容哈希的绑定。

Graph State 只放 ID、引用、状态和小型路由字段，不放完整论文、长 Markdown、CSV 内容或图片字节。

### 2.6 RunConfigurationSnapshot

每个 Run 绑定不可变配置快照，而不是读取会变化的“当前配置”：

```text
configuration_id
schema_version
content_hash
provider_bindings
provider_versions
prompt_versions
calculator_registry_version
retry_policy
timeout_policy
feature_flags
created_at
```

Replay 配置不得包含 API Key，也不得启用网络或在线模型。配置内容变化必须生成新快照；旧授权不自动沿用。

## 3. Replay 输入契约

### 3.1 ReplayCaseManifest

描述一个可重复回放案例，而不是描述某次运行。

```text
case_id
manifest_version
schema_version
mode = REPLAY
research_question_ref
workflow_version
stage_asset_refs
included_asset_refs[]
excluded_assets[].origin_path
excluded_assets[].reason
excluded_assets[].known_identity
declared_finding_specs[]
workflow_graph_ref
stage_dependencies
join_policy
acceptance_profile
content_hash
```

在 `D-001=A` 下，MVP 固定 `join_policy=REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT`。任一分支失败时可生成内部诊断用 Run Summary，但不得生成可进入 `FINAL_REPLAY_REVIEW` 的最终 ReportManifest。

`stage_asset_refs` 是 `stage_id -> SourceAssetRef VersionedRef[]` 映射，`included_asset_refs` 同样绑定 SourceAssetRef 的记录哈希；`excluded_assets` 是内嵌审计项，不被运行读取。

每个内嵌 `DeclaredFindingSpec` 至少包含：

```text
code
finding_kind = COMPATIBILITY | GAP
related_stage_ids[]
related_asset_roles[]
required
expected_severity
replay_policy = MAY_ACCEPT_WITH_EXACT_HASH_REVIEW | FAIL_CLOSED
rationale_source_refs[]
```

Case Manifest 只声明预期 Finding，不提前制造绑定不存在 Artifact 的 Finding。运行时 Adapter/Graph 根据声明生成不可变 Finding 并绑定实际 ArtifactRef/StageAttemptKey。`acceptance_profile` 必须列出 D-008 允许人工接受的 Finding code、始终 Fail Closed 的错误类别和最终报告 Join 条件。

### 3.2 SourceAssetRef

记录某个源文件的身份和使用边界。

```text
asset_id
schema_version
content_hash
role
origin_path
repository_relative_path
source_version
source_authored_at
ingested_at
media_type
byte_size
asset_sha256
provenance_status
usage_boundary
```

约束：

- `origin_path` 仅用于审计，不得成为运行时唯一定位方式；
- `source_authored_at`、`ingested_at` 和 Run 的 `started_at/completed_at` 必须分开；
- 复制文件不改变来源版本或原创建时间；
- `.env`、密钥、`.venv`、缓存和共享临时输出不得成为 Fixture。

### 3.3 SourcePackageRef 与 S04 包级血缘

当来源语义依赖完整目录边界时，逐文件 `SourceAssetRef` 之外还必须建立不可变的包级引用：

```text
package_id
schema_version
content_hash
package_role
origin_path
repository_relative_root
member_asset_refs[]
member_count
total_bytes
tree_hash
tree_hash_algorithm
identity_authority
authored_package_seal_status
lineage_edges[]
runtime_usage_boundary
```

`tree_hash` 是导入审计身份，不得伪装为原作者签名。MVP 的算法固定为：规范化相对路径后按 ordinal 排序，为每个成员输出 `relative_path<TAB>bytes<TAB>sha256<LF>`，对完整 UTF-8 文本计算 SHA256。包引用的 `content_hash` 仍按本契约的 RFC 8785 JCS 规则计算。

D-005=A 固定 S04 的包级语义：

```text
0808.package_role = AUTHORITATIVE_COMPLETE_SOURCE_PACKAGE
0808.member_count = 90
0808.total_bytes = 3818486
0808.tree_hash = a45e77758ca59d98a7fb333326f5463177ad62944376a95c4880230595e6c032
0808.runtime_usage_boundary = PROVENANCE_AND_AUDIT_ONLY

0814.package_role = DERIVED_RUNTIME_FIXTURE_PROJECTION
0814.member_count = 43
0814.total_bytes = 1284797
0814.tree_hash = e577951858466b40cc001627ef27185267d9ed63e249f6ef78b500723d9c47dc
0814.runtime_usage_boundary = DEFAULT_S04_REPLAY_INPUT

0814 DERIVED_FROM 0808
0808 SOURCE_OF 0814
```

37 个映射成员即使字节相同，也必须保留两个 `SourceAssetRef`、两个包成员身份和显式 lineage edge，不得跨包合并或去重。0814 的另外 6 个本地组织/完整性成员没有虚构的 0808 父文件。

0808 内的脚本、执行入口和嵌套 ZIP 只作为不可执行来源字节保存。默认 S04 Adapter 只能读取 0814；只有 provenance/审计查询可以读取 0808。任何执行、解压或动态加载都违反 Replay 契约。

0808 的 90 路径 manifest 集合已核对完整，但移交资料缺失原作者声称的包级 `file_sha256_manifest.csv` 和外层 ZIP。因此必须声明 `S04_0808_PACKAGE_INTEGRITY_REFERENCES_MISSING_FROM_TRANSFER`，并区分：内容集合完整性 `VERIFIED`、原作者包签名证据 `PARTIAL`、37 文件派生血缘 `VERIFIED`。D-008 允许该 Finding 在实际 `FIXTURE_IMPORT_REVIEW` 精确绑定后逐项 `ACCEPTED_FOR_REPLAY`，但不得标记为已解决。

## 4. Artifact 契约

### 4.0 ArtifactRef

所有指向版本化内容、Finding、配置或审批对象的跨对象引用，都必须使用绑定 ID、内容哈希和 Schema 版本的不可变引用，禁止用并行 ID/Hash 数组或只存裸 ID：

```text
artifact_id
content_sha256
schema_version
```

ResearchQuestion、Case Manifest、Finding、配置、Decision、ValidationReport 等其他版本化对象同样使用 `{id, content_hash, schema_version}` 形式的 VersionedRef；字段名中的 `*_ref` 均表示这种绑定引用，而不是裸路径或裸 ID。`task_id`、`run_id`、`stage_id` 等稳定聚合身份允许保存裸 ID，它们不是对版本化内容的引用。

### 4.1 ArtifactEnvelope

所有领域产物共享一个小型公共封套，科学载荷保留自己的版本。

```text
artifact_id
logical_artifact_id
artifact_type
schema_version
artifact_revision
task_id
run_id
run_mode
origin_mode = IMPORTED | DERIVED | NATIVE
authority_mode = SOURCE_BYTES | CANONICAL_JSON
derivation_kind
derived_from_refs[]
payload | content_ref
content_sha256
parent_refs[]
source_asset_refs[]
producer.id
producer.version
source_authored_at
ingested_at
created_at
domain_status
supersedes_ref
```

不变量：

1. `artifact_id` 表示一个不可变内容实例，必须和唯一的 `content_sha256` 绑定；
2. 同一逻辑产物的修订共享 `logical_artifact_id`，但每次内容变化必须创建新的 `artifact_id` 和递增 revision；
3. 已冻结 Artifact 不可原地修改；新实例通过 `supersedes_ref` 指向旧实例；
4. Parent 使用完整 ArtifactRef。Parent 内容变化后，旧的下游审批和兼容性结论仍作为旧链审计记录保留，但不适用于新 revision；
5. Replay 与 Live 使用相同 Envelope，但 `run_mode`、Producer、`origin_mode` 和来源必须真实记录；
6. `IMPORTED + SOURCE_BYTES` 只用于 `SourceDocument`：`content_sha256` 覆盖原始文件字节，原字节是历史事实源；
7. `DERIVED + CANONICAL_JSON` 用于 Adapter 摘要：`content_sha256` 只覆盖 canonical 摘要 payload，必须以 `derivation_kind=EXTRACTED_FROM_IMPORTED`、抽取器版本和 `derived_from_refs` 绑定 SourceDocument 的字节哈希，并记录抽取完整性；
8. `NATIVE + CANONICAL_JSON` 用于系统原生 Artifact：canonical payload 是机器真源，Markdown/前端是可再生成视图；
9. 一个 Envelope 只能有一种 authority 组合，禁止让同一 `content_sha256` 同时代表源字节与摘要 JSON；
10. 派生摘要或展示文案不得静默覆盖任何上游事实源，也不能声称可反向重建导入全文。

Artifact 的 payload、哈希、Producer、父项和来源从创建起不可变。生命周期与验证关系不回写 ArtifactEnvelope，而由追加式 Ledger 中的不可变事件/报告计算当前 Read Model。

### 4.2 MVP Artifact 类型

公共层先支持：

```text
SourceDocument
CandidateSnapshot
MechanismSnapshot
HypothesisSnapshot
DataPlan
DatasetManifest
DataDemoSnapshot
CounterexampleReviewSnapshot
MagnetogramQASnapshot
ResearchSummary
ReportManifest
```

未来正式执行可以增加 `VerificationResult`。在当前 `NOT_AUTHORIZED` Replay 中，系统只能导入或摘要历史开发性观察，不得新建一个看似正式授权的 `VerificationResult`。

### 4.3 领域摘要原则

领域摘要只抽取前端展示、路由和验收所需字段，并始终回指 `ArtifactEnvelope` 与 `SourceAssetRef`。原始 MechanismBrief、Hypothesis Contract、CSV、QA 报告等仍保留为有版本的来源；第一版不追求把其全部语义统一化。

MVP 最小 Read Model 字段：

| 摘要 | 必须包含 |
|---|---|
| `CandidateSnapshot` | `parameter=SHRGT45`、`selection_method=EXPERT_SEED`、`ranking_status=NOT_IMPLEMENTED`、source refs、限制说明 |
| `MechanismSnapshot` | 参数、来源版本、允许解释、禁止主张、关键 source refs、抽取完整性 |
| `HypothesisSnapshot` | 上游机制版本/引用、Predictor 定义、Outcome、窗口、流程3 domain status、机器可验证性 |
| `DataPlan` | D-004 单位策略版本、观测行、HARP 测量空间、依赖分组、事件归属、规范窗口和历史窗口冲突引用 |
| `DataDemoSnapshot` | 6/360/333/55=37+18/4 AR、单位/依赖分组、窗口重叠、Estimator、control 类型、provenance 缺口、Finding refs、授权与成熟度 |
| `CounterexampleReviewSnapshot` | 科学反例候选、数据/标签问题、不可评估项、下一步动作分别列出，不合并为单一 verdict |
| `MagnetogramQASnapshot` | 文件/帧/provenance 检查、QA verdict，以及“QA PASS 不等于机制或预测证据” |
| `ResearchSummary` | 系统执行结果、验证状态、血缘、科学 verdict、成熟度、授权和发布范围分别显示 |

### 4.3.1 D-006 聚合 RunReadModel

`D-006=A` 冻结首个 MVP 的查询投影组织方式。API 提供一个聚合 `RunReadModel`，前端首屏只依赖下列摘要分区：

```text
run
stages[]
domain_snapshots[]
artifacts[]
findings[]
gates[]
lineage_summary
report
```

每个分区只包含公共契约允许的短字段和不可变 VersionedRef。Artifact、Finding、Lineage、Source 和 Report 的全文/原始载荷通过独立详情查询访问。前端不得自行计算阶段状态、S05/S06 汇合、Finding 阻断、授权或科学 verdict；这些状态由后端投影器从 Ledger、ValidationReport、Finding 和 Decision 派生。

`RunReadModel` 不是新的科学 Artifact，也不是审批绑定目标。其 `read_model_schema_version` 或字段白名单发生变化时，必须生成新的投影版本并通过契约/Golden Fixture 校验；不得回写或覆盖上游 Artifact。S04 默认详情仍只读 0814，0808 仅由 provenance/审计查询展开。

### 4.4 ArtifactLifecycleEvent 与 ArtifactStateView

Artifact 创建后的状态变化使用不可变事件：

```text
event_id
schema_version
content_hash
artifact_ref
from_lifecycle
to_lifecycle
decision_ref
reason
actor_id
created_at
```

合法生命周期由事件序列派生：

```text
DRAFT -> REVIEW_REQUIRED -> FROZEN
DRAFT | REVIEW_REQUIRED -> REJECTED
FROZEN -> SUPERSEDED
```

`ArtifactStateView` 是查询投影，可包含当前 `artifact_lifecycle` 和相关 `validation_report_refs[]`；它不是新的科学 Artifact，也不是审批绑定目标。冻结 DecisionRecord 与 LifecycleEvent 都绑定同一个不可变 ArtifactRef，因此不会因“变为 FROZEN”而生成内容副本或丢失审批。

## 5. 验证、兼容性与失败

### 5.1 LineageEdge

Artifact 之间的血缘使用不可变、可验证的边，而不是仅靠前端递归 `parent_refs` 猜测：

```text
edge_id
logical_edge_id
schema_version
revision
content_hash
upstream_artifact_ref
downstream_artifact_ref
relation_type = SOURCE_OF | DERIVED_FROM | TRANSFORMED_FROM | SUMMARIZES | VALIDATES
required
verification_status = NOT_CHECKED | VERIFIED | PARTIAL | CONFLICT
evidence_refs[]
finding_refs[]
supersedes_ref
created_at
```

`parent_refs` 是 Artifact 创建时的最小父项声明；LineageEdge 补充关系类型、核验证据和 Finding。每次重新核验必须创建新 `edge_id`/revision 并用 `supersedes_ref` 指向旧边，不得原地修改 `verification_status`。Run 级聚合按优先级计算：存在任一 `CONFLICT` 则为 `CONFLICT`；否则任一 `required=true` 的边为 `PARTIAL` 或 `NOT_CHECKED` 则为 `PARTIAL`；所有必需边均为 `VERIFIED` 才为 `VERIFIED`；尚无可核验边时为 `NOT_CHECKED`。获准 Replay 的冲突仍保持 `CONFLICT`。

### 5.2 ValidationReport

```text
report_id
schema_version
content_hash
target_artifact_ref
validator_id
validator_version
validation_status
checks[].code
checks[].severity
checks[].message
checks[].path
created_at
```

`PASS` 只表示定义过的确定性检查通过，不表示机制正确、假设真实或统计结论成立。

### 5.3 FindingRef 与 FindingDisposition

Finding 是不可变、可哈希的版本化对象。审批不得绑定可原地修改的状态文本：

```text
FindingRef = {
  finding_id,
  content_hash,
  schema_version
}

FindingDisposition = {
  disposition_id,
  schema_version,
  content_hash,
  finding_ref,
  action = ACCEPT_FOR_REPLAY | RESOLVE | REOPEN,
  decision_ref,
  resolution_refs[],
  created_at
}
```

Finding 初始状态为 `OPEN`；`ACCEPTED_FOR_REPLAY` / `RESOLVED` 是由不可变 Disposition 事件派生出的当前视图，不得在原 Finding 上改字段。Finding 的 summary、severity 或 required_action 变化时，必须创建新 Finding revision；旧审批保留用于旧 Finding，但不适用于新 revision。

通用接纳路由同时适用于 CompatibilityFinding 和 GapFinding：

- 任一标记为必需的 Finding 在未处理时都会阻止最终 ReportManifest；
- `FIXTURE_IMPORT_REVIEW` 必须绑定 FindingRef、相关 ArtifactRef；若 Finding 表示尚无上游 Artifact 的阶段能力缺口，还必须绑定对应 StageAttemptKey；
- 只有上述精确绑定的 DecisionRecord 才能产生 `ACCEPT_FOR_REPLAY` Disposition；
- `ACCEPTED_FOR_REPLAY` 只允许历史 Replay，不适用于 Live Run；
- `RESOLVE` 必须引用新 Artifact、Migration 或实现证据；
- Finding 内容、相关 Artifact 哈希或 Run 配置变化后，旧 Disposition 不再适用。

#### 5.3.1 D-008 分层 Finding 处置政策

下列已登记历史兼容性/来源限制可以进入 `FIXTURE_IMPORT_REVIEW` 的人工接受集合：

```text
MECHANISM_V23_VS_HYPOTHESIS_V22_DEPENDENCY
THEIL_SEN_VS_OLS_IMPLEMENTATION
LEAD_WINDOW_BOUNDARY_IMPLEMENTATION_MISMATCH
CONTROL_WINDOW_POLICY_MISMATCH
CONTROL_CATALOG_SPATIAL_ATTRIBUTION_UNFILTERED
HARP_NOAA_MAPPING_PARTIAL_OR_AMBIGUOUS
COUNTEREXAMPLE_INPUT_PACKAGE_IDENTITY_UNVERIFIED
EVENT_SEED_OFFICIAL_PROVENANCE_UNVERIFIED
HISTORICAL_ROWS_NOT_INDEPENDENT_SAMPLES
S04_0808_PACKAGE_INTEGRITY_REFERENCES_MISSING_FROM_TRANSFER
```

只有本次 `HISTORICAL_REPLAY` 实际生成的 Finding，并同时绑定精确 FindingRef、相关 ArtifactRef、必要的 StageAttemptKey、Run 配置和内容哈希后，项目所有者才能派生 `ACCEPTED_FOR_REPLAY`。该状态必须在报告和 `RunReadModel` 中保持可见，不适用于 Live Run、正式统计、科学结论或发布授权。

下列类别必须 Fail Closed，不得通过人工点击转换为 `ACCEPTED_FOR_REPLAY`：

```text
UNKNOWN_FIXTURE_PATH
MISSING_REQUIRED_MEMBER
SHA256_MISMATCH
MANIFEST_MISMATCH
UNKNOWN_SCHEMA_OR_VERSION
UNKNOWN_SOURCE_OR_PROVENANCE_IDENTITY
CONFIGURATION_HASH_MISMATCH
UNAUTHORIZED_FORMAL_EXECUTION
SECRET_OR_CREDENTIAL_ACCESS
FORBIDDEN_HISTORICAL_SCRIPT_EXECUTION
FORBIDDEN_NESTED_ZIP_EXTRACTION
REQUIRED_S05_OR_S06_BRANCH_FAILURE
REPORT_JOIN_FAILURE
UNBOUND_FINDING_OR_ARTIFACT
```

错误分类的具体枚举在 T002 机械化，但不得扩大人工可接受集合。新增可接受 Finding code 或改变 Fail Closed 类别必须提交 Contract Change Request。

### 5.4 CompatibilityFinding

用于区分“系统能展示两个历史产物”和“这两个产物科学及版本上相容”。

```text
finding_id
logical_finding_id
schema_version
revision
content_hash
upstream_artifact_ref
downstream_artifact_ref
code
severity = INFO | WARNING | ERROR
initial_status = OPEN
summary
evidence_refs[]
impact
required_action
supersedes_ref
created_at
```

首个 Case 至少预置：

```text
MECHANISM_V23_VS_HYPOTHESIS_V22_DEPENDENCY
THEIL_SEN_VS_OLS_IMPLEMENTATION
COUNTEREXAMPLE_INPUT_PACKAGE_IDENTITY_UNVERIFIED
LEAD_WINDOW_BOUNDARY_IMPLEMENTATION_MISMATCH
CONTROL_WINDOW_POLICY_MISMATCH
CONTROL_CATALOG_SPATIAL_ATTRIBUTION_UNFILTERED
HARP_NOAA_MAPPING_PARTIAL_OR_AMBIGUOUS
```

`ACCEPTED_FOR_REPLAY` 只表示允许忠实展示该历史接缝，不表示问题已经解决。

CompatibilityFinding 的附加路由规则：

- 未登记的哈希变化、Schema 不合法、必需来源缺失或身份错误：Fail Closed；
- 已登记的历史兼容性问题：先保持 `OPEN`；
- `ERROR` Finding 在 Live Run 中始终阻断；
- `RESOLVE` Disposition 必须引用 Migration 或新 Artifact，不得只改状态文本；
- 任一仍未获批准的必需 Finding 会阻止最终 ReportManifest。

`lineage_status` 是 Artifact 边或 Run 的派生聚合：所有必需边均核验且无冲突才为 `VERIFIED`；存在无法核验的边为 `PARTIAL`；存在版本/方法冲突为 `CONFLICT`，即使该冲突获准 Replay 也仍保持 `CONFLICT`。

### 5.5 GapFinding

表示某阶段能力尚未实现或项目材料存在缺口，不伪装成上下游兼容性问题。

```text
finding_id
logical_finding_id
schema_version
revision
content_hash
stage_id
code
severity
initial_status = OPEN
summary
evidence_refs[]
impact
required_action
supersedes_ref
```

首个 Case 必须包含：

```text
CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED
LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE
EVENT_SEED_OFFICIAL_PROVENANCE_UNVERIFIED
HISTORICAL_ROWS_NOT_INDEPENDENT_SAMPLES
```

### 5.6 FailureRecord

```text
failure_id
schema_version
content_hash
run_id
stage_id
category = DATA | NETWORK | VALIDATION | PROGRAM | QUALITY | LINEAGE | AUTHORIZATION
code
message
retryable
attempt
input_artifact_refs[]
occurred_at
```

产生 FailureRecord 时不得自动改变 `scientific_verdict`。有限重试耗尽后，阶段进入 `FAILED` 或等待人工处理；不得通过补引用、伪造默认值或删除失败数据来让流程“变绿”。

## 6. 决策与授权

### 6.1 DecisionRequest 与 DecisionOption

人工介入先产生一个可审计的选择请求，不能只有事后结果：

```text
request_id
schema_version
content_hash
decision_context = PROJECT_GOVERNANCE | RUN_GATE
governance_context_ref
gate_id
prompt
context_artifact_refs[]
context_finding_refs[]
context_stage_attempt_keys[]
options[]
recommended_option_id
recommendation_reason
risk_summary
impact_summary
allowed_scope
allowed_actor_roles[]
requested_at
expires_at
```

每个 `DecisionOption` 至少包含 `option_id`、`label`、`description`、`consequences` 和 `required_capability`。前端只提交 `option_id` 与理由，不能构造合同外动作。

`PROJECT_GOVERNANCE` 用于冻结 MVP 范围、Replay 闸门配置和 Fixture 策略，要求 `governance_context_ref` 且选项使用 `required_capability=PROJECT_OWNER_GOVERNANCE`；它不得借用 `FORMAL_DATA_EXECUTION` 或 `PUBLIC_OR_COMPETITION_RELEASE`。`RUN_GATE` 用于具体 StudyRun，要求精确的运行上下文引用。`expires_at` 对项目治理请求可省略，对有时效的运行请求按具体 Gate 契约填写。

DecisionRecord 的 `bound_artifact_refs`、`bound_finding_refs`、`bound_stage_attempt_keys` 和 `scope` 必须是对应 DecisionRequest 上下文/`allowed_scope` 的精确集合或合同明确允许的子集；API 不得接受请求上下文之外的对象，防止审批时注入新的 Finding 或 Artifact。

### 6.2 DecisionRecord

```text
decision_id
schema_version
content_hash
decision_context = PROJECT_GOVERNANCE | RUN_GATE
governance_context_ref
decision_request_ref
gate_id
action = APPROVE | REVISE | REJECT | TERMINATE
decision_mode = HUMAN_SELECTED | SYSTEM_DELEGATED
selected_option_id
actor_id
actor_role
reason
scope
bound_artifact_refs[]
bound_finding_refs[]
bound_stage_attempt_keys[]
delegated_scope
workflow_version
created_at
supersedes_ref
```

`SYSTEM_DELEGATED` 只表示人已预先授权系统在 `delegated_scope` 内从冻结的 Option 集合中选择，不等同于系统自行扩大权限。`TERMINATE` 只能由人发出并关闭 ResearchTask；系统和失败路由最多 `CANCEL` 当前 Run。

`workflow_version` 对 `RUN_GATE` 必填；对正在决定工作流形态的 `PROJECT_GOVERNANCE` 记录可省略，随后由 baseline lock 绑定最终工作流版本。`delegated_scope` 仅在 `decision_mode=SYSTEM_DELEGATED` 时必填；没有前序记录时省略 `supersedes_ref`。项目治理记录不绑定运行产物时，三个 `bound_*` 数组为空。

### 6.3 AuthorizationRecord

```text
authorization_id
schema_version
content_hash
capability = FORMAL_DATA_EXECUTION | PUBLIC_OR_COMPETITION_RELEASE
authorization_status = NOT_AUTHORIZED | AUTHORIZED | REVOKED | EXPIRED
scope
actor_id
actor_role
bound_artifact_refs[]
configuration_ref
workflow_version
created_at
expires_at
supersedes_ref
```

授权必须绑定具体 capability、ArtifactRef、范围和工作流版本。内容、配置或工作流版本变化后，旧授权不能自动沿用。

当前 `NOT_AUTHORIZED` 专指 `capability=FORMAL_DATA_EXECUTION`；它阻止正式取数/统计和正式指标，但不阻止已批准的历史文件导入与历史 Replay 项目查看。

`FINAL_REPLAY_REVIEW` 在不可变 ReportManifest 生成后执行，属于非阻塞的项目报告查看/确认动作。它只能针对精确 Report ArtifactRef 记录 `ACKNOWLEDGED_FOR_PROJECT_REVIEW`（或等价的项目审阅状态），不产生 ReleaseDisposition，也不代表科学批准、正式执行授权或对外发布授权。`PUBLIC_OR_COMPETITION_RELEASE` 必须由 `expert_reviewer` 对同一精确 Report ArtifactRef 另行授权。

MVP 允许单用户，但仍保留 `actor_id` 字符串字段，避免未来改成多人时破坏契约。

### 6.4 ReleaseDisposition 与 ReleaseStateView

ReportManifest 不可修改。发布状态通过不可变记录派生：

```text
release_disposition_id
schema_version
content_hash
report_artifact_ref
release_scope = READY_FOR_INTERNAL_DEMO | PUBLIC_OR_COMPETITION
decision_ref
authorization_ref
actor_id
actor_role
created_at
supersedes_ref
```

项目报告审阅记录必须引用 `FINAL_REPLAY_REVIEW` DecisionRecord，并只能派生项目查看确认状态；公开/答辩/比赛记录还必须引用有效的 `PUBLIC_OR_COMPETITION_RELEASE` AuthorizationRecord。`ReleaseStateView` 不得由 `FINAL_REPLAY_REVIEW` 生成，只有独立的 ReleaseDisposition/AuthorizationRecord 才能派生；报告内容哈希变化后，旧状态不适用。

## 7. 正交状态

下列状态不得合并为一个通用 `status`。第一轮已经选择 `D-001=A`，因此下表给出本 MVP 的当前约束；这些状态仍需随公共契约共同冻结：

| 维度 | 枚举 | MVP 当前值/说明 |
|---|---|---|
| `run_mode` | `REPLAY / LIVE` | `REPLAY` |
| `run_purpose` | `HISTORICAL_REPLAY / ACTIVE_RESEARCH` | `HISTORICAL_REPLAY` |
| `execution_status` | `PENDING / RUNNING / WAITING_HUMAN / SUCCEEDED / FAILED / CANCELLED / SKIPPED` | 随运行变化 |
| `validation_status` | `NOT_RUN / PASS / PASS_WITH_WARNINGS / FAIL` | 随 Artifact 变化 |
| `origin_mode` | `IMPORTED / DERIVED / NATIVE` | 随 Artifact 变化 |
| `artifact_lifecycle` | `DRAFT / REVIEW_REQUIRED / FROZEN / SUPERSEDED / REJECTED` | 由 LifecycleEvent 派生 |
| `authorization_status` | `NOT_AUTHORIZED / AUTHORIZED / REVOKED / EXPIRED` | 正式数据执行为 `NOT_AUTHORIZED` |
| `scientific_verdict` | `NOT_EVALUATED / SUPPORTED / CONDITIONALLY_SUPPORTED / NOT_SUPPORTED / INSUFFICIENT_EVIDENCE` | `NOT_EVALUATED` |
| `lineage_status` | `NOT_CHECKED / VERIFIED / PARTIAL / CONFLICT` | 逐接缝计算 |
| `result_maturity` | `DEVELOPMENTAL / CONFIRMATORY` | `DEVELOPMENTAL` |
| `release_scope` | `NOT_READY / READY_FOR_INTERNAL_DEMO / PUBLIC_OR_COMPETITION` | 默认 `NOT_READY`；项目报告查看确认不改变此值 |

状态归属：

- `execution_status` 属于 RunRecord / StageRun；
- `validation_status` 属于 ValidationReport，相关报告列表只出现在派生 ArtifactStateView；
- `origin_mode` 属于 ArtifactEnvelope，`artifact_lifecycle` 由 ArtifactLifecycleEvent 派生；
- `authorization_status` 属于带 capability 的 AuthorizationRecord；
- `lineage_status` 属于 Artifact 边，并可聚合为 Run lineage；
- `scientific_verdict`、`result_maturity` 属于 `ResearchSummary.scientific_assessment`（未来可独立为 ScientificAssessment），不是每个 Artifact 的通用状态；
- `release_scope` 属于由 ReleaseDisposition 派生的 ReleaseStateView，不写回 ReportManifest；
- 文档状态和工作项状态不进入任何科学运行对象。

流程 3 的 `DRAFT / READY_FOR_DATAPLAN / NEEDS_CLARIFICATION / PROJECT_CONFLICT` 只能放入带命名空间的 `domain_status`，不得复用为 Artifact 生命周期。

`DATA_UNAVAILABLE`、`INSUFFICIENT_SAMPLES`、`NEEDS_CLARIFICATION` 是带命名空间的数据/就绪状态或失败原因；`BLOCKED` 是工作项状态，`FAILED` 才是运行执行状态。它们都不是科学结论。

文档审阅和开发任务使用独立的项目管理状态，不得写入运行对象：

```text
document_status = DRAFT_FOR_REVIEW | AWAITING_PROJECT_OWNER | ACCEPTED | SUPERSEDED
work_item_status = BLOCKED | PENDING | IN_PROGRESS | COMPLETED | CANCELLED
blocker_code = 可选的具体阻塞原因，例如 CONTRACT_REVIEW
```

## 8. 工作流契约

规范 Stage ID：

```text
S01_CANDIDATE
S02_MECHANISM
S03_HYPOTHESIS
S04_DATA_AND_VERIFICATION
S05_COUNTEREXAMPLE
S06_MAGNETOGRAM_QA
S07_REPORT
```

规范边：

```text
S01 -> S02 -> S03 -> S04
S04 -> S05
S04 -> S06
S05 + S06 -> S07
```

S05 与 S06 没有上下游关系。任何实现把 S05 串到 S06 前后都违反工作流契约。

阶段操作语义：

- S01 在 Replay 中由固定 Case 构造 `CandidateSnapshot`，其 `selection_method=EXPERT_SEED`；不得显示为系统排名成功；
- S02–S06 导入并摘要历史资产；
- S03 历史包缺少完整机器五件套时，只做文件、哈希和最小导入校验，记录 `LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE`，不得反推补造文件后声称通过现有 Validator；
- S04 的 `SUCCEEDED` 只表示从 0814 运行投影完成 `IMPORT_AND_SUMMARIZE`；0808 只参与来源追溯，不产生正式 VerificationResult；
- S07 是系统原生生成的开发性 ResearchSummary/ReportManifest，不伪称为历史来源产物；
- S07 采用 `REQUIRE_S05_AND_S06_FOR_FINAL_REPLAY_REPORT`；支线失败时只能生成内部诊断摘要。

每个节点必须：

- 显式声明输入和输出 Artifact 类型；
- 只通过 Artifact 引用读取父项；
- 幂等：同一输入哈希、配置版本和 Provider 版本不会产生重复副作用；
- 写入自身 Stage 的运行记录；
- 失败时生成 FailureRecord；
- 不清理其他 Run 或共享目录；
- 不因展示需要而修改历史来源。

## 9. Provider 契约

目标接口：

```text
CandidateProvider
MechanismProvider
HypothesisProvider
DataProvider
CounterexampleReviewer
MagnetogramQAProvider
ReportRenderer
```

每个 Provider 接收版本化的 `StageContext` 与输入 Artifact 引用，返回领域 ArtifactRef、ValidationReport ref、LineageEdge ref 和统一的 `finding_refs[]`（可指向 CompatibilityFinding 或 GapFinding）。Provider 不直接修改 Graph State 之外的任意共享状态。

第一版实现 `ReplayCandidateProvider`（固定专家种子）、流程 2–6 的 Replay Provider 和生成开发性汇总的 ReportRenderer；接口中不得硬编码 `D:\...`、具体模型名或历史文件名。未来以 `CandidateRankingProvider` 替换候选入口，并通过依赖注入增加 Live Provider，主图结构保持不变。

## 10. 版本与哈希

- `schema_version` 使用 SemVer；
- `source_version`、`artifact_revision`、`workflow_version`、`producer.version` 分别记录；
- 原始文件使用字节级 SHA256；
- Versioned Object 的 `content_hash` 定义为：移除顶层 `content_hash` 字段后，按 RFC 8785 JSON Canonicalization Scheme（JCS）生成 UTF-8 字节，再计算 SHA256；禁止把对象自己的 Hash 字段纳入输入；
- `ArtifactEnvelope.content_sha256` 只覆盖其 authority 对应的内容：SourceDocument 为原始字节，DERIVED/NATIVE 为 canonical payload；
- `SourceAssetRef.asset_sha256` 只覆盖原始文件字节，`SourceAssetRef.content_hash` 覆盖该引用记录本身，两者不得混用；
- canonical JSON 算法已在本语义契约中固定为 `RFC8785-JCS + UTF-8 + SHA256`；T002 只负责实现并以跨语言 Golden Hash Fixture 验证，不得另选算法；
- Adapter 声明支持的 Schema 版本范围；
- 跨版本必须显式 Migration，并生成 ValidationReport；
- 禁止把 V2.2 静默改名为 V2.3；
- 人工决定绑定 Artifact 哈希和工作流版本；任一变化后，旧决定作为历史记录保留，但不适用于新内容或新工作流。

语义契约冻结后，**JSON Schema 是机器可执行规范源**。Python 类型应由 Schema 生成，或由 CI 一致性测试证明没有漂移；不得让手写 Python 类型反向、静默改变 Schema 语义。

## 11. 冻结确认

`project_owner_01` 已选择 `D-001=A` 至 `D-008=A`。D-005 固定 0808 为完整权威来源包、0814 为 43 成员 Demo 运行投影；D-006 固定聚合 `RunReadModel` 和引用式详情；D-007 固定第一闸门阻塞回放、第二闸门在报告生成后非阻塞地记录项目查看确认；D-008 固定分层 Finding 处置和 Fail Closed 边界。对应内容寻址记录位于 `governance/decisions/records/`，完整请求和回复上下文位于 `governance/decisions/requests/` 与 `governance/decisions/source/`。

## 12. 变更控制

冻结后，普通实现任务不得顺手改契约。契约变更必须单独提交：

```text
Contract Change Request
-> 影响分析
-> 版本升级
-> Migration/兼容策略
-> 契约测试
-> 项目所有者确认
-> 才能修改实现
```
