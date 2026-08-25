# T002 JSON Schema 实现清单

> 状态：`ACCEPTED_INPUT`
>
> 语义规范源：`docs/contracts/CONTRACTS.md` 版本 `0.1.0`

本清单定义 T002 必须机械化的边界，不在 T000 提前生成 Schema。所有 Schema 使用 JSON Schema 2020-12；内容身份使用 RFC8785 JCS、UTF-8 和 SHA256。共享定义必须通过 `$ref` 复用，不得复制后漂移。

## Foundation

| Schema | 主要责任 |
|---|---|
| `versioned-ref.schema.json` | `id + schema_version + content_hash` 引用 |
| `research-question.schema.json` | 固定研究问题、窗口、Target 与分析单位策略 |
| `run-configuration-snapshot.schema.json` | 本次运行的冻结配置和 Provider/Workflow 版本 |
| `source-asset-ref.schema.json` | 原来源、相对路径、字节数、SHA256、时间和用途 |
| `source-package-ref.schema.json` | 0808/0814 独立包身份、成员和包级边界 |
| `replay-case-manifest.schema.json` | Case、资产白名单、阶段映射、Join 与 acceptance profile |

## Artifact And Runtime

| Schema | 主要责任 |
|---|---|
| `artifact-ref.schema.json` | 不可变 Artifact 引用 |
| `artifact-envelope.schema.json` | authority、origin、payload、Producer、父项和哈希 |
| `artifact-lifecycle-event.schema.json` | FROZEN/SUPERSEDED/REJECTED 等追加事件 |
| `artifact-state-view.schema.json` | 从事件和验证报告派生的当前视图 |
| `run-record.schema.json` | StudyRun 持久化事实 |
| `stage-run.schema.json` | StageAttemptKey、输入输出、状态与重试 |
| `stage-context.schema.json` | Provider 的版本化最小上下文 |
| `checkpoint-ref.schema.json` | LangGraph 恢复点及所引用 Artifact |
| `failure-record.schema.json` | 系统、数据、网络、授权和契约失败，不承载科学结论 |

## Validation, Lineage And Findings

| Schema | 主要责任 |
|---|---|
| `validation-report.schema.json` | 结构/哈希/业务规则校验结果 |
| `lineage-edge.schema.json` | DERIVED_FROM、SOURCE_OF 等不可变血缘 |
| `compatibility-finding.schema.json` | 版本、方法和历史实现接缝 |
| `gap-finding.schema.json` | 缺输入、能力或 provenance 证据 |
| `finding-disposition.schema.json` | ACCEPT_FOR_REPLAY/RESOLVE/REOPEN 追加处置 |
| `finding-state-view.schema.json` | OPEN/ACCEPTED_FOR_REPLAY/RESOLVED 派生状态 |

## Governance And Release

| Schema | 主要责任 |
|---|---|
| `decision-option.schema.json` | 人工可选择的冻结 Option |
| `decision-request.schema.json` | 治理或运行闸门请求及精确上下文 |
| `decision-record.schema.json` | HUMAN_SELECTED/SYSTEM_DELEGATED 决定 |
| `authorization-record.schema.json` | capability、范围、Artifact 与有效期 |
| `project-review-ack.schema.json` | 非阻塞 `ACKNOWLEDGED_FOR_PROJECT_REVIEW` |
| `release-disposition.schema.json` | 独立发布范围，不由 FINAL_REPLAY_REVIEW 产生 |
| `release-state-view.schema.json` | 对精确报告的发布状态投影 |

## Domain And Query Projections

| Schema | 主要责任 |
|---|---|
| `candidate-snapshot.schema.json` | 专家预选种子，不伪装成系统排名 |
| `mechanism-snapshot.schema.json` | 机制证据最小摘要与来源引用 |
| `hypothesis-snapshot.schema.json` | 历史假设摘要、版本和可验证性边界 |
| `verification-snapshot.schema.json` | 历史导入结果，不伪装为新正式执行 |
| `counterexample-snapshot.schema.json` | 反例与下一步计划摘要 |
| `magnetogram-qa-snapshot.schema.json` | 图像/provenance QA，不提升科学主张 |
| `research-summary.schema.json` | 开发性结论、限制、状态和引用 |
| `report-manifest.schema.json` | S05/S06 Join 后不可变报告清单 |
| `run-read-model.schema.json` | D-006 聚合查询投影 |

## Shared Enums And Golden Tests

T002 必须集中定义正交状态枚举、D-008 可接受 Finding code 与 Fail Closed 类别，并提供：

- 每个 Schema 的最小合法 Fixture；
- 关键非法 Fixture；
- RFC8785 跨语言 Golden Hash；
- V2.2 不得静默冒充 V2.3 的测试；
- Finding/Artifact/配置哈希变化后旧决定不适用的测试；
- `FINAL_REPLAY_REVIEW` 不得产生 ReleaseDisposition 的测试；
- S05/S06 任一必需分支失败时不得生成最终 ReportManifest 的测试。
