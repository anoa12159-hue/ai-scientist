# AI Scientist 实施 TODO

> 使用规则：每个 session 开始先读本文件和 `docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md`，从第一个未完成且无阻塞项的任务开始。完成任务后更新勾选状态、日期、证据和下一步。不要跳过任务定义冻结直接开发 Agent。

状态：`[ ]` 未完成，`[x]` 已完成，`[!]` 阻塞，`[-]` 明确取消。

## P0｜任务与赛事冻结

- [!] P0-01 已核对阿里云赛事页并记录 2026-08-25 口径；钉钉答疑正文需团队导出后完成逐条复核。证据：`docs/evidence/competition/VERIFICATION_2026-08-25.md`。
- [x] P0-02 冻结 `TASK_DECLARATION_JWSSD_MW5CLASS.md`：官方 `20260826.zip` 评测集、输入模态、单样本、类别、输出和指标。（2026-08-26）
- [-] P0-03 原 JW-FD Research/Benchmark 映射已取代；历史记录保留于 `docs/decisions/ADR-0001-task-mapping.md`。
- [x] P0-04 冻结 `qwen-plus`、百炼 OpenAI-compatible API、预算和额外数值模型边界。证据：`docs/MODEL_COMPLIANCE.md`。（2026-08-25）
- [x] P0-05 建立数据字典、外部数据/许可证清单和血缘边界。证据：`docs/DATA_GOVERNANCE.md`。（2026-08-25）
- [x] P0-06 冻结评测集版本与 SHA256；评测集不得进入训练、调参、阈值选择或模型选择链。（2026-08-26；`db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4`）

## P1｜现有 MVP 收尾

- [!] P1-01 原始 `langgraph-pyagent-ai-scientist-agent-agent` Git 历史仍未随移交材料提供；已基于现有 `ai_scientist-main` 初始化项目根 Git（`main`），但无法确认移交报告所述原始提交与脏工作区。（2026-08-25）
- [x] P1-02 完成 T006 主审修正的完整回归测试并清理临时产物。（2026-08-25；专项 25 passed，全量 217 passed；Ruff/mypy/import 检查通过；已清理 `.pytest_cache`）
- [x] P1-03 检查并保护冻结契约、Fixture 原始字节、CompletionRecord 和治理语义。（2026-08-25；Smoke/Fixture/Contract 审计 131 passed；冻结基线、哈希、Fixture 字节和治理记录未漂移）
- [x] P1-04 更新 README、任务状态和移交说明，形成 T006 独立提交。（2026-08-25；README、`docs/TASK_BACKLOG.md` 和版本化 T006 交接附录已同步；基线提交 `010b6dc`，T006 独立提交已创建）
- [x] P1-05 验证中断、恢复、重试、并行分支和幂等写入。（2026-08-25；T006 专项回归 25 passed，覆盖真实 interrupt、跨进程恢复、有限重试、S05/S06 并行 Join、分支失败 Fail Closed 和重复运行幂等）

## P2｜Qwen 统一模型层

- [x] P2-01 实现统一 `QwenChatModel`/OpenAI-compatible Adapter。（2026-08-25；无第三方 SDK 的适配器、离线请求注入测试；专项 5 passed，全量 222 passed；Ruff/mypy 通过）
- [x] P2-02 将模型名、temperature、seed、超时、轮数和预算移入配置。（2026-08-25；新增 `config.example.toml`、不可变 `QwenRuntimeConfig`/`ModelBudget` 和 TOML 校验；专项 8 passed，全量 225 passed；Ruff/mypy 通过）
- [x] P2-03 实现结构化输出、Schema 校验和有限修复循环。（2026-08-25；`StructuredQwenChatModel` 使用 Draft 2020-12 校验、最多配置轮数修复并聚合 token 用量；专项 3 passed，全量 228 passed；Ruff/mypy 通过）
- [x] P2-04 实现 API 重试、退避、限流、超时和错误 Artifact。（2026-08-25；`ResilientChatModel` 支持 429/5xx/网络错误分类、指数退避抖动、最小间隔限流和 `ModelErrorArtifact`；专项 8 passed，全量 233 passed；Ruff/mypy 通过）
- [x] P2-05 增加脱敏调用日志、模型版本记录和 token 统计。（2026-08-25；`LoggingModelCallObserver` 与 `ModelCallRecord` 仅记录 provider、配置/响应模型、响应 ID、尝试次数、耗时、结果、错误码和 token 用量；遥测/重试专项 6 passed；全量测试 235 passed；Ruff/mypy 通过）
- [!] P2-06 `deep_research_agent_v13.zip` 内含非占位 `S2_API_KEY`，且该值已在沟通渠道直接披露；按 v13 上下文它是 Semantic Scholar（S2）检索/引用服务凭证，不是 Qwen/DashScope 密钥。需密钥所有者吊销/轮换并确认旧密钥失效；主仓库补齐后再清除 DeepSeek 专用依赖。（2026-08-25）

## P3｜文献与证据 Skills

- [x] P3-01 将文献检索能力拆为安全的 `paper_search` Skill。（2026-08-25；新增注入式 Provider、离线内存索引、查询规范化、年份/领域过滤、稳定排序、去重和多角度合并；专项 22 passed；全量测试 241 passed；Ruff/mypy 通过；未读取历史压缩包、未访问网络或凭证）
- [x] P3-02 接入论文全文获取、缓存版本和引用链扩展。（2026-08-25；新增 `PaperFetchSkill`、显式 Fetcher/Cache/Citation Provider 边界、SHA-256/字节上限校验、版本化缓存键和有界确定性 BFS；专项 27 passed；全量测试 246 passed；Ruff/mypy 通过；未访问网络或凭证）
- [x] P3-03 实现逐字引用、数字和位置校验。（2026-08-25；新增 `QuoteVerifier`，支持精确位置、唯一匹配、数字 token（小数/科学计数法/百分号）校验和 Fail Closed 的 `NOT_FOUND`；专项 32 passed；全量测试 251 passed；Ruff/mypy 通过；原文不进入结果）
- [x] P3-04 将 Phase 1/Phase 2 输出映射到 `EvidenceTable`/`MechanismBrief`。（2026-08-25；经用户明确授权，从 v13 ZIP 仅选择性提取 `template.py`、`phase2_system.py` 和两份实际输出到 `/tmp`，未提取 `.env`；实现 `Phase1EvidencePlan`、V2.2 `EvidenceTable`/`MechanismBriefV22` 解析校验及现有 `MechanismSnapshot` 投影；V2.3 禁止静默冒充 V2.2；专项 21 passed；全量测试 261 passed；Ruff/mypy 通过）
- [x] P3-05 提供固定语料快照和离线检索回退方案。（2026-08-25；新增 `literature/shrgt45.snapshot.json`，引用四份已哈希锁定的 S02 Fixture 来源；`SnapshotPaperSearchProvider` 校验路径、字节数、SHA-256 和 UTF-8；仅在 `PaperSearchUnavailableError` 时确定性回退；专项 27 passed；全量测试 256 passed；Ruff/mypy 通过）
- [x] P3-06 用 SHRGT45 Fixture 完成一条可审计的文献研究 Replay。（2026-08-25；`LiteratureReplayService` 串联固定快照检索、V2.2 来源哈希、15 条逐字证据校验、`MechanismSnapshot` 投影与 ArtifactStore 血缘；重复运行幂等，独立 `audit_hash` 可重算；专项 11 passed；全量测试 262 passed；Ruff/mypy 通过；无网络、未读取凭证，科学状态保持 `NOT_EVALUATED / DEVELOPMENTAL`）

## P4｜假设、数据与反例闭环

- [x] P4-01 固化 `Hypothesis`、`DataPlan`、`ValidationReport` 和 `CounterexampleReport` 契约。（2026-08-25；完整解压材料确认流程 03 为 V2.1 内部 JSON DTO + 手写 Validator，流程 04/05 为 Markdown/表格而非正式 JSON Schema；新增严格内部 DTO、八层 DataPlan 提取、五类反例分层和现有冻结 Snapshot/ValidationReport 投影，不修改公共契约；专项 10 passed，相关回归 108 passed，全量 272 passed；Ruff/mypy/导入/基线复核通过）
- [x] P4-02 实现 SHARP 参数注册、公式、单位和别名校验。（2026-08-25；新增系统无关 `SharpParameterRegistry`，先登记已由 Bobra 2014 Table 3 与冻结 Fixture 核实的 SHRGT45：有效像素剪切角 >45° 面积百分比、percent/0–100、HARP patch、12 分钟 cadence、CMASK/像素选择口径和定义哈希；安全别名可解析，MEANSHR/平均剪切角、fraction、错误公式、NaN/Inf/布尔/越界值 Fail Closed；专项 29 passed，相关回归 138 passed，全量 301 passed；Ruff/mypy/导入/基线复核通过）
- [x] P4-03 实现 FITS/CSV 读取、质量门、缺失值、投影和时间一致性检查。（2026-08-25；严格 UTF-8 CSV 与 Astropy FITS 边界、Br/Bp/Bt 同记录/shape/WCS/CEA 审计、NaN/Inf/QUALITY 与 14/16 cadence 门；专项 21 passed，相关回归 165 passed，全量 322 passed；Ruff/mypy/导入/冻结基线复核通过）
- [x] P4-04 实现磁场特征计算、时间窗切分和标签构造。（2026-08-25；同 HARP `[T0-3h,T0]` 切片、真实 T_REC OLS/首末差、TAI→UTC 与同单位 `[T0+3h,T0+6h)` M1.0+ onset 标签；拒绝未冻结 Theil–Sen、隐式 HARP/NOAA 映射和不完整目录负标签；专项 16 passed，相关回归 66 passed，全量 338 passed；Ruff/mypy/导入/冻结基线复核通过）
- [x] P4-05 实现 JW-SSD 五分类统计、macro/micro-F1、balanced accuracy、每类 Recall 置信区间和 HARPNUM 数据泄漏检查。（2026-08-26；`ai_scientist-main/tests/unit/test_jwssd_evaluation.py`；真实 ZIP 审计 195 组/780 模态文件，类别 `50/50/25/50/20`，SHA256 与冻结声明一致；当前环境未安装 pytest，已完成 Python 3.11 静态编译与真实 ZIP 离线审计）
- [x] P4-06 实现五分类混淆样本、少数类漏报/误报挖掘、反例解释和下一步计划生成。（2026-08-26；新增 `mine_confusion_cases`，仅消费独立评测结果，不触发批量推理）
- [x] P4-07 实现连续谱/磁图四模态 QA 和代表性视觉证据 Artifact。（2026-08-26；`build_magnetogram_qa_snapshot`/`create_visual_evidence_artifact` 标签盲读四个 ZIP 成员，写入四个不可变 `SourceDocument` 父 Artifact 与 `MagnetogramQASnapshot`；真实样本 QA、内容哈希、血缘和幂等复核通过；专项 10 passed，Ruff/mypy 通过；未触发批量评测）
- [x] P4-08 完成基于冻结 JW-SSD 评测集的端到端分类闭环，并验证每条结论都可追溯到数据或代码版本。（2026-08-26；`PilotAuditRecord`/`persist_pilot_audit_artifact` 绑定独立评测 JSON、预测 CSV SHA256、四模态 QA Artifact 与错分反例；明确 pilot-only 和非正式全量结果；专项 11 passed，Ruff/mypy 通过；未触发批量评测）

## P5｜JW-SSD 五分类批量评测入口

- [x] P5-01 实现唯一 `src/infer_batch.py` 入口。（2026-08-26；标签隔离读取 `load_unlabeled_jwssd_samples`、冻结 ZIP SHA256 校验和标准预测 CSV；正式模式为 Qwen-VL，均匀概率仅作 smoke baseline）
- [ ] P5-02 在冻结评测集上生成五分类预测 CSV；推理进程不得读取标签。
- [x] P5-03 由独立评测进程读取标签，生成混淆矩阵、macro/micro-F1、balanced accuracy、每类召回率和置信区间。（2026-08-26；`ai_scientist-main/src/evaluate_jwssd.py`；预测 CSV 样本 ID、概率和五分类标签均有 Fail Closed 校验）
- [x] P5-04 验证推理不读取评测标签、不依赖人工点击、不依赖本机路径，并校验输入 ZIP SHA256。（2026-08-26；`audit_inference_source_isolation` 静态审计 `src/infer_batch.py`：标签盲 loader、冻结 Archive SHA256、无评测器引用、无机器绝对路径；专项 12 passed，Ruff/mypy 通过；未触发批量评测）
- [ ] P5-05 固定依赖、Prompt、工具、语料、配置和 commit hash。（部分完成；`docs/JWSSD_REPRODUCIBILITY.md` 已固定评测集、依赖、配置、Prompt、入口/API/前端/质量门文件哈希和当前基线 commit；最终 commit hash 需代码冻结后补齐，不自动提交）
- [x] P5-06 添加预算、限流、失败重试、超时和批量推理耗时说明。（2026-08-27；新增 `docs/JWSSD_BATCH_RUNBOOK.md` 与 `--confirm-batch` 显式批量闸门；配置固定 195 请求、token/cost 上限、180s 超时、3 次重试、退避和限流；实际批量耗时/费用待授权执行后记录；当前未启动批量评测）

## P6｜API、前端与评测交付

- [x] P6-01 实现 Run、Stage、Artifact、Finding、报告和审核查询 API。（2026-08-27；新增无第三方依赖的 `RunReadModel` 投影和 HTTP 路由，支持 health、RunReadModel、Stage、Artifact、Finding、Report/Review 查询，并提供受控 Replay `start`/`approve` 操作；对绝对路径做响应脱敏；API 专项、Ruff/mypy 通过）
- [x] P6-02 实现研究运行、状态查看、证据链、反例和报告前端。（2026-08-27；静态前端支持启动离线回放、人工导入闸门审批、状态刷新和 Artifact/Finding/报告展示；不推导科学结论；前端契约测试通过）
- [ ] P6-03 完成离线端到端验收和浏览器验收。（部分完成；`scripts/offline_acceptance.py`、API ReadModel 路由、静态前端契约和 Replay 集成回归已通过；当前环境无浏览器运行时，真实浏览器验收待后续环境执行）
- [ ] P6-04 添加 `LICENSE`、第三方依赖许可证和源码发布说明。（部分准备；新增 `docs/THIRD_PARTY_LICENSES.md` 记录依赖版本和待核验许可；项目许可证及官方数据再分发条款需项目负责人/组委会确认，未擅自添加法律文件）
- [ ] P6-05 从版本化系统结果生成不超过 30 页的技术方案 PDF（官网 2026-08-25 当前口径）。（部分准备；交付源稿已写入 `docs/TECHNICAL_PROPOSAL.md`；当前环境未安装 PDF 渲染器，且正式结果/许可证尚未冻结）
- [ ] P6-06 准备可调用 API、前端链接、代表性案例和可选演示视频。（部分准备；本地 API/前端启动和 pilot 演示步骤已写入 `docs/DEMO_RUNBOOK.md`；外部部署链接和视频需项目负责人/环境提供）

## 评测与质量门

- [x] Q-01 建立 Schema 合法率、引用准确率、假设可操作化率和数据重算一致性指标。（2026-08-27；新增 `quality.gates`，支持 PASS/FAIL/NOT_EVALUABLE 与内容哈希；专项质量门测试通过）
- [x] Q-02 建立中断恢复、重复运行、网络失败和模型 API 失败测试。（2026-08-27；既有 Replay/存储/模型重试专项覆盖中断恢复、幂等、网络错误、429/5xx 和结构化失败；本次相关回归通过）
- [ ] Q-03 建立冻结 JW-SSD 评测集的五分类基线、少数类指标和置信区间报告。（模板已准备于 `docs/JWSSD_METRICS_REPORT_TEMPLATE.md`；完整数值必须等待 P5-02 授权执行，当前不运行批量评测）
- [x] Q-04 完成评测集复现演练、标签隔离审计和模型/代码版本自查。（2026-08-27；复现清单、源码隔离审计、Archive SHA256 和 pilot Artifact 哈希链已验证；未执行批量评测）
- [x] Q-05 完成最终源码、配置、Prompt、工具、语料和日志清单审计。（2026-08-27；复现清单固定入口/配置/Prompt/评测契约/质量门哈希；密钥和 `.env` 明确排除；最终 commit 仍待代码冻结）

## Session 交接记录

| 日期 | 完成任务 | 测试/证据 | 阻塞项 | 下一任务 |
|---|---|---|---|---|
| 2026-08-25 | 创建实施方案与 TODO | 文档已写入本地 | 主仓库代码尚未解压/确认 | P0-01 |
| 2026-08-25 | 完成 P0-02～P0-05；核验官网并发现提交口径更新 | 任务声明、ADR、模型合规、数据治理、官网响应哈希 | 钉钉答疑正文未导出；LangGraph 主仓库缺失；研究压缩包凭证需轮换 | 补齐答疑导出和主仓库，吊销旧 S2 密钥 |
| 2026-08-25 | 完成 P1-02：T006 回归与临时产物清理 | `tests/unit/test_replay_graph.py tests/integration/test_replay_workflow.py -q`：25 passed；全量 `tests/unit tests/integration tests/smoke tests/fixtures tests/contract -q`：217 passed；`ruff check .`、`mypy src`、导入检查通过；项目目标为系统无关运行，Windows 残留 `verify_project.ps1` 不作为 Linux 验收项 | T006 未发现范围内失败；仓库仍无可用 Git 元数据，无法形成提交 | P1-03 |
| 2026-08-25 | 初始化项目根 Git 并完成 P1-03 冻结项审计 | 根仓库 `main` 已初始化；Smoke/Fixture/Contract：131 passed；冻结基线、Fixture 原始字节、CompletionRecord 和治理语义未漂移 | 原始移交 Git 历史缺失；新仓库尚未创建提交 | P1-04 |
| 2026-08-25 | 完成 P1-04 文档同步并建立 Git 基线 | README、任务队列、T006 交接附录已更新；安全项目基线提交 `010b6dc`；外部压缩包、PDF、DOCX 和只读移交源未纳入 | T006 正式 closeout/CompletionRecord 仍待后续批准 | P1-05 |
| 2026-08-25 | 完成 P1-05：T006 中断/恢复/重试/并行/幂等验证 | `tests/unit/test_replay_graph.py tests/integration/test_replay_workflow.py -q`：25 passed（63.63s） | T006 正式 closeout/CompletionRecord 仍待后续批准 | P2-01 |
| 2026-08-25 | 完成 P2-01：Qwen/OpenAI-compatible 统一适配器 | `tests/unit/test_qwen_adapter.py`：5 passed；全量测试：222 passed；Ruff/mypy 通过；未访问网络、未使用 API Key | P2-02 尚未完成；真实百炼调用需后续配置和密钥 | P2-02 |
| 2026-08-25 | 完成 P2-02：模型运行参数与预算配置化 | `tests/unit/test_llm_config.py tests/unit/test_qwen_adapter.py -q`：8 passed；全量测试：225 passed；Ruff/mypy 通过；配置解析不访问网络 | P2-03 结构化输出尚未实现 | P2-03 |
| 2026-08-25 | 完成 P2-03：结构化输出与有限 Schema 修复 | `tests/unit/test_structured_output.py`：3 passed；全量测试：228 passed；Ruff/mypy 通过；无网络调用 | P2-04 API 重试/退避/限流/超时和错误 Artifact 尚未实现 | P2-04 |
| 2026-08-25 | 完成 P2-04：模型请求重试、退避、限流和错误 Artifact | `tests/unit/test_resilient_model.py tests/unit/test_llm_config.py -q`：8 passed；全量测试：233 passed；Ruff/mypy 通过；错误路径无网络凭证泄露 | P2-05 脱敏日志、模型版本和 token 统计尚未实现 | P2-05 |
| 2026-08-25 | 完成 P2-05：脱敏模型调用遥测 | `tests/unit/test_telemetry.py tests/unit/test_resilient_model.py -q`：6 passed；全量测试：235 passed；Ruff/mypy 通过；Smoke 白名单已同步；提示词、响应正文和凭证不进入记录 | P2-06 历史压缩包含真实 `S2_API_KEY`，需密钥所有者轮换后才能处理 | P2-06 |
| 2026-08-25 | 完成 P3-01：离线 `paper_search` Skill | 专项 22 passed；全量测试 241 passed；Ruff/mypy 通过；新增 `docs/PAPER_SEARCH.md`；Provider 不访问网络和凭证 | P2-06 仍阻塞；全文获取/缓存/引用链属于 P3-02 | P3-02 |
| 2026-08-25 | 完成 P3-02：全文缓存与引用链扩展边界 | 专项 27 passed；全量测试 246 passed；Ruff/mypy 通过；缓存身份、哈希、大小和 BFS 上限均有测试 | P2-06 仍阻塞；在线 Provider、版权授权和逐字引用校验需后续明确 | P3-03 |
| 2026-08-25 | 完成 P3-03：逐字引用与数字位置校验 | 专项 32 passed；全量测试 251 passed；Ruff/mypy 通过；结果仅保存引用哈希、位置和原因 | P2-06 仍阻塞；EvidenceTable/MechanismBrief 契约映射属于 P3-04 | P3-04 |
| 2026-08-25 | 修正 P3-04 类型边界 | 已由材料知情人确认：V2.2 定义是 `template.py` 的 Python DTO 与 `phase2_system.py` 的 Markdown 模板，不是 JSON Schema；持久层继续使用现有 `MechanismSnapshot` 和来源引用 | 等待脱敏的两个源文件及两处验收样例；`S2_API_KEY` 必须吊销/轮换 | P3-04（等待脱敏材料） |
| 2026-08-25 | 完成 P3-05：固定语料快照与离线回退 | 专项 27 passed；全量测试 256 passed；Ruff/mypy 通过；四份来源逐项校验哈希和大小，回退只处理显式不可用错误 | 当时 P3-04 尚待 v13 模板；现已在后续完成 | P3-04 |
| 2026-08-25 | 完成 P3-04：v13 V2.2 Phase 1/2 DTO 与 Markdown 映射 | 专项 21 passed；全量测试 261 passed；Ruff/mypy 通过；实际 V2.2 Fixture 可解析，V2.3 冒充、重复证据和缺字段均 Fail Closed | P2-06 凭证轮换仍未确认；P3-06 尚未串联 Replay | P3-06 |
| 2026-08-25 | 完成 P3-06：SHRGT45 可审计离线文献 Replay | 专项 11 passed；全量测试 262 passed；Ruff/mypy 通过；15 条证据逐字校验，Artifact 血缘、审计哈希和幂等已验证 | P2-06 旧凭证处置仍未确认；P4-01 涉及冻结契约变更 | P4-01（需先核对契约） |
| 2026-08-25 | 完成 P4-01：假设、DataPlan、验证与反例内部契约 | 完整解压材料静态核对；专项 10 passed，相关回归 108 passed，全量 272 passed；Ruff/mypy/导入/基线复核通过；未修改冻结 Schema 或解压材料 | P2-06 旧凭证处置仍未确认；正式公共 Schema 变更仍需独立 CCR | P4-02 |
| 2026-08-25 | 完成 P4-02：SHARP 参数注册与校验 | SHRGT45 权威定义、公式 ID、percent/0–100、别名歧义和确定性定义哈希已固化；专项 29 passed，相关回归 138 passed，全量 301 passed；Ruff/mypy/导入/基线复核通过 | 当前只登记已核实的 SHRGT45；其他 SHARP 参数不得猜测补录 | P4-03 |
| 2026-08-25 | 完成 P4-03：系统无关 FITS/CSV 读取与质量审计 | 专项 21 passed，相关回归 165 passed，全量 322 passed；Ruff/mypy/导入/冻结基线复核通过；真实冻结 CSV 通过 16 帧窗口审计，FITS 用 Astropy 生成最小离线样例 | 移交材料没有实际 FITS 文件，Live 数据获取与正式科学执行仍未授权 | P4-04 |
| 2026-08-25 | 完成 P4-04：SHRGT45 特征、时间窗与标签构造 | 专项 16 passed，相关回归 66 passed，全量 338 passed；真实 Fixture OLS/首末差与 0814 一致；`+3h`/`+6h`、早发事件、M1.0 阈值和目录完整性均有边界测试 | 当前事件 seed provenance 仍待核实；模块只接受调用方提供的已核实同单位完整事件目录 | P4-05 |
| 2026-08-26 | 冻结 JW-SSD 官方五分类评测集 | `SHRGT45_官方五分类四模态扩展样本_20260826.zip`；195 组、780 文件；SHA256 已记录；内部目录名保留 20260825 2 | 四模态 loader、训练/验证隔离和五分类评测尚未实现 | P4-05 |
| 2026-08-26 | 完成 P4-05：JW-SSD manifest、四模态完整性、指标和泄漏审计 | `ai_scientist-main/docs/JWSSD_EVALUATION.md`、`ai_scientist-main/src/ai_scientist_mvp/skills/jwssd_evaluation.py`；真实 ZIP 离线审计通过：195 组、780 文件、783 个逻辑成员，类别 `50/50/25/50/20`；Python 3.11 `py_compile` 通过 | pytest/ruff/mypy 未安装；P5 推理入口尚未实现 | P5-01 |
| 2026-08-26 | 完成 P5-01：唯一标签隔离批量推理入口 | `ai_scientist-main/src/infer_batch.py`、`ai_scientist-main/tasks/TASK-P5-01.md`；真实 ZIP 无标签读取 195 组通过，Python 3.11 `py_compile` 通过；默认均匀 predictor 明确标为 smoke baseline | 真实训练模型、独立评测进程和公开预测报告尚未接入 | P5-02 |
| 2026-08-26 | 完成 P5-03：独立五分类评测进程 | `ai_scientist-main/src/evaluate_jwssd.py`、`ai_scientist-main/tasks/TASK-P5-03.md`；评测端独占标签读取，校验 195 个样本 ID、概率范围、混淆矩阵、F1、balanced accuracy 和 Recall Wilson 区间；Python 3.11 `py_compile` 通过 | P5-02 真实训练模型/预测器尚未确定 | P5-02 |
| 2026-08-26 | 接入 Qwen-VL 评测模式 | `config.qwen_jwssd.toml`、`src/infer_batch.py` 支持 `qwen-vl-max`、视觉 PNG、FITS 数值摘要和本地 `.env`；Qwen 适配器支持多模态 content parts；14 项相关测试通过，Ruff 通过 | `.env` 当前仅有 `S2_API_KEY`，缺少 `DASHSCOPE_API_KEY`，真实调用暂未发出 | 配置 `DASHSCOPE_API_KEY` 后验证单样本，再运行 P5-02 |
| 2026-08-26 | 完成 Qwen-VL 单样本 agent smoke | 仅调用 `JWSSD_alpha_HARP7211_20171228_000000_TAI`；DashScope 返回结构化五分类概率，预测 `alpha`；未启动批量评测 | 模型效果尚未由评测集统计验证，等待项目负责人确认 | 保持暂停，待确认后再决定 P5-02 |
| 2026-08-26 | 完成 4 样本 agent 端到端试运行 | `infer_batch --mode qwen --limit 4` → `/tmp/jwssd-pilot-4.predictions.csv` → 独立 `evaluate_jwssd`；4 条 Qwen-VL 请求成功，评测报告 `sample_count=4`、accuracy `0.75`、macro-F1 `0.1714`；四条恰好均为 `alpha`，结果仅验证流程，不代表五分类效果；15 项相关测试通过，Ruff 通过 | 按要求未启动 195 条批量评测；P5-02 保持暂停 | 等待项目负责人确认 agent 输出后再决定是否继续 |
| 2026-08-26 | 继续非批量开发：完成 P4-06 混淆反例清单 | 新增 `mine_confusion_cases`，对独立评测结果生成逐样本错分、少数类漏报标记和复核建议；未触发 Qwen 或批量评测；16 项相关测试通过，Ruff 通过 | P4-07 四模态 QA 与 P4-08 闭环仍待实现；P5-02 继续暂停 | 继续实现四模态 QA |
| 2026-08-26 | 完成 P4-07：四模态 QA 与视觉证据 Artifact | `create_visual_evidence_artifact` 标签盲读四个成员，写入四个 `SourceDocument` 父 Artifact 和不可变 `MagnetogramQASnapshot`；真实 alpha 样本通过；`tests/unit/test_jwssd_evaluation.py`：10 passed；Ruff/mypy 通过；未触发 Qwen 或批量评测 | P4-08 闭环、P5-04～P5-06 和 P6/Q 仍待实现；P5-02 批量推理继续暂停 | 开始 P4-08 pilot 可审计分类闭环 |
| 2026-08-26 | 完成 P4-08：pilot 分类闭环 Artifact | `persist_pilot_audit_artifact` 绑定独立评测报告、预测 CSV 源字节、QA Artifact 和混淆反例；Archive/预测 SHA256 与样本 ID 有校验；仅 pilot，不触发批量评测 | P5-04～P5-06、P6/Q 仍待实现；P5-02 批量推理继续暂停 | 开始 P5-04 标签隔离、路径无关和复现审计 |
| 2026-08-26 | 完成 P5-04：标签隔离、路径无关和 SHA256 静态审计 | `audit_inference_source_isolation` 检查 `infer_batch.py` 未引用评测标签/评测器/机器绝对路径，并固定官方 ZIP SHA256；专项 12 passed，Ruff/mypy 通过；未触发批量评测 | P5-02 批量推理继续暂停；P5-05/P5-06、P6/Q 仍待实现 | 固定当前依赖、Prompt、配置和复现清单 |
| 2026-08-26 | 补充 P5-05 复现清单并演练真实 pilot Artifact 链 | `docs/JWSSD_REPRODUCIBILITY.md` 固定输入、配置、Prompt 和入口哈希；使用现有 4 条 pilot 预测/指标生成 4 个源 Artifact + QA + `JWSSDPilotAudit`，`artifact_count=7`，内容哈希复核通过；未调用 API、未批量评测 | 最终 commit hash 需代码冻结后补齐；P5-02/P6/Q 仍待实现 | 等项目负责人确认 pilot 后再决定批量评测 |
| 2026-08-27 | 完成 P5-06、P6-01、P6-02；补齐 Q-01/Q-02/Q-04/Q-05 | `--confirm-batch` 闸门、预算 runbook、只读 RunReadModel API、静态前端、质量门与离线验收脚本已完成；Ruff/mypy 通过；离线验收真实 ZIP 通过；未启动批量评测 | P5-05 最终 commit hash、P6-03 浏览器运行、P6-04 法律许可、P6-05 PDF、P6-06 外部演示、Q-03 全量指标仍待外部条件或批量授权 | 由项目负责人确认代码冻结/许可证，之后再决定批量评测 |
| 2026-08-27 | 完成阶段回归与交付源稿 | 单元/契约/Fixture/Smoke：325 passed；集成：31 passed；Ruff、mypy、`git diff --check` 通过；批量闸门拒绝未确认的全量 Qwen 命令；未启动批量评测 | 仍需最终 commit、浏览器实际运行、许可证/数据再分发确认、PDF 渲染、外部演示部署和完整 Q-03 指标 | 等项目负责人确认外部依赖或明确授权 |
