# AI Scientist MVP 项目章程

> 文档状态：`ACCEPTED`
>
> 版本：`0.1.0`
>
> 冻结依据：项目所有者 `project_owner_01` 已确认 `D-001=A` 至 `D-008=A`；后续语义变更必须走独立 Contract Change Request。

## 1. 项目使命

把现有 SHRGT45 研究 Demo 推广为一个可扩展、可审计、可人工介入的 AI Scientist 系统框架。首版先证明系统能够可靠接住已有研究产物、保持血缘和科学边界，并按规定流程回放；它不假装重新完成了一次端到端科学研究。

## 2. 固定研究问题

首个案例研究的问题为：

> 在同一空间分析单位内，过去 3 小时的 `SHRGT45` 演化，能否为未来 `[t+3h, t+6h)` 内发生的 `M1.0+` 太阳耀斑提供可检验的信息？

当前已知语义：

- 参数：`SHRGT45`；
- 历史窗口：过去 3 小时；
- 预测窗口：未来 `[t+3h, t+6h)`；
- 同单位规则：研究问题要求同一空间分析单位；Replay 按 D-004=A 分开记录 HARP patch 测量空间、HARP-timepoint 观测行、依赖分组和 NOAA AR 事件归属；
- Target：`M1.0+`；
- 事件是否落窗以 onset 为准，等级以 peak flux 定级；
- 该关系属于待检验的项目/专家先验，不是已经由文献直接证明的事实。

## 3. 科学主张上限

二维 `SHRGT45` 最多可解释为光球非势性或自由能状态的代理量。系统不得据此声称已经证明：

- 磁重联机制；
- MHD 失稳；
- 三维磁拓扑；
- 完整因果链；
- 对新样本具有已验证的预测能力。

程序失败、网络失败、数据不可用、Schema 校验失败或授权不足，均不得被转换为“科学上不支持”。结构校验通过也不等于科学结论正确。

## 4. 首个 MVP 范围（D-001 已确认）

项目所有者已选择 `D-001=A` 的“忠实历史回放”，并通过 D-002 至 D-008 冻结闸门、Fixture、单位、Read Model 与 Finding 处置边界。

### 4.1 包含

- 一个固定的 SHRGT45 `ResearchTask`；
- 一个历史 `StudyRun`，运行模式为 `REPLAY`；
- 流程 01–07 的可视化回放，其中流程 01 明确为专家预选种子而非系统排名，流程 05 与 06 并列；
- 精选历史 Fixture 的导入、哈希、来源、版本和已知缺口记录；
- 按 `D-003=A` 建立精选只读 Fixture 快照并保存原路径、字节数和 SHA256；`D-005=A` 已批准 171 文件、9,725,849 B 的精确逻辑范围，实际复制和逐文件 Manifest 留在 T003；
- Artifact 不可变存储、运行台账、Checkpoint、验证报告和失败记录；
- 历史产物格式与系统公共契约之间的 Replay Adapter；
- LangGraph 顶层编排；
- 后端 API；
- 完整但逻辑较薄的前端：通过聚合 `RunReadModel` 查看运行概览、阶段状态、产物详情、血缘、兼容性问题、人工审核和报告；前端不自行拼装工作流状态；
- 至少一次中断后恢复演示；
- 按 `D-002=A` 和 `D-007=A` 实现两个 Replay 闸门：`FIXTURE_IMPORT_REVIEW` 位于 S01-S06 完成后、S07 前并阻塞回放；`FINAL_REPLAY_REVIEW` 位于不可变 ReportManifest 生成后，仅记录非阻塞的项目报告查看确认；
- 自动化契约测试、哈希测试、路由测试和端到端 Replay 测试。

### 4.2 不包含

- 在线文献检索；
- 在线 LLM/Qwen/百炼调用；
- JSOC 或竞赛数据实时获取；
- 正式重新计算 TSS、HSS、AUC 等统计指标；
- 正式独立阴性 control 的新设计与执行；
- 任意参数的自动泛化；
- 多租户、复杂权限或多人审批；
- Pi Agent；
- 让 LLM 生成 Python 后直接执行；
- 对历史产物进行静默补字段、补引用或改写血缘。

## 5. 当前数据与授权边界

历史 Demo 的已知计数为：

- 6 个事件种子；
- 360 条理论查询；
- JSOC 返回 333 条；
- 最终 55 行，其中 37 行事件前候选、18 行同活动区时间背景对照；
- 覆盖 4 个活动区。

55 行不是 55 个独立样本，窗口存在重叠；18 行对照不是正式独立阴性组；事件 provenance 仍有 `NEEDS_CLARIFICATION`。由于第一轮已选择 `D-001=A`，首个 MVP 固定：

```text
run_mode = REPLAY
authorization_status = NOT_AUTHORIZED
scientific_verdict = NOT_EVALUATED
result_maturity = DEVELOPMENTAL
```

D-004=A 进一步固定：每行是 `SHARP_HARP_TIMEPOINT`，SHRGT45 的测量空间是 `SHARP_HARP_PATCH`，共享 `HARP_EVENT_EPISODE` 的行属于同一依赖组。NOAA AR 是导入的事件归属字段，不能被冒充为 HARP patch，也不能把未闭合的 seed provenance 升级为已验证映射。

D-005=A 进一步固定 S04 来源边界：0808 是 90 成员的 `AUTHORITATIVE_COMPLETE_SOURCE_PACKAGE`，0814 是由其派生的 43 成员 `DERIVED_RUNTIME_FIXTURE_PROJECTION`。两包保持独立身份和 `DERIVED_FROM` / `SOURCE_OF` 血缘；Replay 默认只读 0814，0808 只供来源追溯。0808 中的脚本和嵌套 ZIP 不得执行或解压；缺失的原作者包级 hash manifest 与外层 ZIP 必须作为 Gap Finding 展示。

D-006=A 进一步固定前端边界：API 首先提供聚合 `RunReadModel`，包含运行、阶段、领域摘要、Artifact、Finding、闸门、血缘和报告摘要；全文和原始载荷通过引用式详情访问。Read Model 是查询投影，不是新的科学事实源，字段变化必须生成新的投影/Schema 版本。

D-007=A 固定 Gate Profile：`FIXTURE_IMPORT_REVIEW` 在 S01-S06 完成后、S07 前阻塞历史 Replay；`FINAL_REPLAY_REVIEW` 在不可变 ReportManifest 生成后非阻塞地记录项目查看确认，不产生发布授权。

D-008=A 固定分层 Finding 政策：已登记、精确哈希绑定的历史兼容性/来源限制可以逐项 `ACCEPTED_FOR_REPLAY`；输入、成员、哈希、Manifest、Schema、来源、配置、授权、禁止执行、必需分支和 Report Join 错误必须 Fail Closed。

现有“方向支持”“反例候选”等只能作为开发性观察展示，不得提升为正式科学结论。

## 6. 架构原则

1. 顶层编排使用 LangGraph；第一版不引入 Pi Agent。
2. Graph State 只保存 Artifact 引用、状态和小型路由字段，不保存长 Markdown 或大数据。
3. 原生系统 Artifact 以 canonical JSON 为机器真源，Markdown 是可再生成的人读视图；Replay 导入资产以原始字节为历史事实源，JSON 摘要只是派生投影。
4. Artifact 冻结后不可覆盖，只能创建新版本并标记旧版本为 `SUPERSEDED`。
5. LLM 输出在进入下一阶段前必须结构化并通过确定性验证。
6. 原子 Tool 只做通用操作；Skill 组合业务能力；Provider 隔离 Replay 与 Live 实现。
7. 任何科学计算仅通过受控 `calculator_id` 注册表调用，禁止 `eval()` 和任意代码执行。
8. 失败关闭：未知的缺输入、哈希变化、Schema/来源错误、未获批准的版本不兼容或授权不足时，停止相应路径并产生结构化记录；已登记历史接缝只有在 `FIXTURE_IMPORT_REVIEW` 绑定精确哈希批准后才可继续 Replay，且仍保持未解决/冲突标记。
9. 历史来源时间、导入时间和运行时间分别记录，不以复制时间冒充产物创建时间。
10. `D:\桌面\揭榜-移交版` 源资料库只读；所有运行输出限定在 `D:\桌面\langgraph-pyagent-ai-scientist-agent-agent\runs/<run_id>/` 范围内。

## 7. Provider 扩展边界

主图只依赖稳定 Provider 接口，不依赖某个历史目录或某个在线模型：

```text
CandidateProvider
MechanismProvider
HypothesisProvider
DataProvider
CounterexampleReviewer
MagnetogramQAProvider
ReportRenderer
```

首版使用 `Replay*Provider`。后续可以增加：

```text
CandidateRankingProvider
DeepResearchMechanismProvider
QwenHypothesisProvider
JsocDataProvider
CompetitionDataProvider
```

Replay 与 Live 实现必须输出同一种公共 Artifact Envelope；差别通过 `run_mode`、`producer`、`producer_version` 和来源记录表达，不能让主图根据具体供应商硬编码分支。

## 8. MVP 完成标准

只有同时满足下列条件，才称为首个 MVP 完成：

1. 一条命令可启动本地系统，并可在无网络、无 API Key 环境运行；
2. 能载入固定 SHRGT45 Case Manifest，验证所有选定 Fixture 的哈希；
3. 能按正确的流程顺序运行，且 05/06 为并列分支并在 07 汇合；
4. 能显示或导出每个 Artifact 的来源、父项、版本、哈希、生产者和验证状态；
5. 能显式显示所有契约预置的兼容性与缺口 Finding，不把它们自动修复或隐藏；
6. 在 `NOT_AUTHORIZED` 时拒绝任何正式执行路径；
7. 运行中断后可以从 Checkpoint 恢复，且节点重放保持幂等；
8. 前端能完成运行浏览、Artifact 详情、血缘/限制查看、审核动作和报告查看，并明确显示 SHRGT45 为专家预选种子；
9. 自动测试通过，并用 Golden Summary 核对计数和科学限制；
10. 生成的报告保持 `NOT_EVALUATED` / `DEVELOPMENTAL`，不产生未经授权的正式指标；
11. `FINAL_REPLAY_REVIEW` 不产生发布授权，只记录项目组对精确版本报告的查看确认；报告保持 `NOT_EVALUATED` / `DEVELOPMENTAL`。对外或比赛发布必须由独立的专家审核权限批准。

## 9. MVP 之后的扩展顺序

1. 将 `MechanismBrief V2.3` 转换为 canonical extract；
2. 实现真实 `QwenHypothesisProvider`，同时保留离线 Fake Provider 测试；
3. 完成主动切片：`canonical extract -> 新 Hypothesis DRAFT -> Validator -> 人工冻结`；
4. 接入流程 2 的在线机制研究 Provider；
5. 接入在线数据 Provider 和经授权的统计执行；
6. 扩展到其他候选参数和多分支 StudyRun；
7. 只有出现明确需求时再评估 Pi Agent 或更复杂的多 Agent 执行层。
