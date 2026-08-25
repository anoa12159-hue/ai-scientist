# AI Scientist 实施 TODO

> 使用规则：每个 session 开始先读本文件和 `docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md`，从第一个未完成且无阻塞项的任务开始。完成任务后更新勾选状态、日期、证据和下一步。不要跳过任务定义冻结直接开发 Agent。

状态：`[ ]` 未完成，`[x]` 已完成，`[!]` 阻塞，`[-]` 明确取消。

## P0｜任务与赛事冻结

- [!] P0-01 已核对阿里云赛事页并记录 2026-08-25 口径；钉钉答疑正文需团队导出后完成逐条复核。证据：`docs/evidence/competition/VERIFICATION_2026-08-25.md`。
- [x] P0-02 完成 `TASK_DECLARATION.md`：输入模态、单样本、预处理、时间窗、标签和输出。（2026-08-25）
- [x] P0-03 冻结 Research/Benchmark 双任务，禁止把累计窗口静默映射为非重叠 3-6h。证据：`docs/decisions/ADR-0001-task-mapping.md`。（2026-08-25）
- [x] P0-04 冻结 `qwen-plus`、百炼 OpenAI-compatible API、预算和额外数值模型边界。证据：`docs/MODEL_COMPLIANCE.md`。（2026-08-25）
- [x] P0-05 建立数据字典、外部数据/许可证清单和血缘边界。证据：`docs/DATA_GOVERNANCE.md`。（2026-08-25）

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
- [!] P2-06 `deep_research_agent_v13.zip` 内含非占位 `S2_API_KEY`；已禁止交付并记录于 `SECURITY_NOTICE.md`，需密钥所有者吊销/轮换；主仓库补齐后再清除 DeepSeek 专用依赖。（2026-08-25）

## P3｜文献与证据 Skills

- [x] P3-01 将文献检索能力拆为安全的 `paper_search` Skill。（2026-08-25；新增注入式 Provider、离线内存索引、查询规范化、年份/领域过滤、稳定排序、去重和多角度合并；专项 22 passed；全量测试 241 passed；Ruff/mypy 通过；未读取历史压缩包、未访问网络或凭证）
- [x] P3-02 接入论文全文获取、缓存版本和引用链扩展。（2026-08-25；新增 `PaperFetchSkill`、显式 Fetcher/Cache/Citation Provider 边界、SHA-256/字节上限校验、版本化缓存键和有界确定性 BFS；专项 27 passed；全量测试 246 passed；Ruff/mypy 通过；未访问网络或凭证）
- [x] P3-03 实现逐字引用、数字和位置校验。（2026-08-25；新增 `QuoteVerifier`，支持精确位置、唯一匹配、数字 token（小数/科学计数法/百分号）校验和 Fail Closed 的 `NOT_FOUND`；专项 32 passed；全量测试 251 passed；Ruff/mypy 通过；原文不进入结果）
- [!] P3-04 将 Phase 1/Phase 2 输出映射到 `EvidenceTable`/`MechanismBrief` 契约：当前冻结 `contracts/` 没有这两个 Schema，且章程要求保留 MechanismBrief 原始版本化来源、首版不统一其全文语义；需要项目所有者先批准独立 Contract Change Request 后才能实现。（2026-08-25）
- [ ] P3-05 提供固定语料快照和离线检索回退方案。
- [ ] P3-06 用 SHRGT45 Fixture 完成一条可审计的文献研究 Replay。

## P4｜假设、数据与反例闭环

- [ ] P4-01 固化 `Hypothesis`、`DataPlan`、`ValidationReport` 和 `CounterexampleReport` 契约。
- [ ] P4-02 实现 SHARP 参数注册、公式、单位和别名校验。
- [ ] P4-03 实现 FITS/CSV 读取、质量门、缺失值、投影和时间一致性检查。
- [ ] P4-04 实现磁场特征计算、时间窗切分和标签构造。
- [ ] P4-05 实现统计检验、TSS/HSS、置信区间和数据泄漏检查。
- [ ] P4-06 实现假阳性/假阴性挖掘、反例解释和下一步计划生成。
- [ ] P4-07 实现磁图 QA 和代表性视觉证据 Artifact。
- [ ] P4-08 完成端到端研究闭环，并验证每条结论都可追溯到数据或文献。

## P5｜比赛批量评测入口

- [ ] P5-01 实现唯一 `src/infer_batch.py` 入口。
- [ ] P5-02 在无标签 test-like 数据上生成官方标准预测 CSV。
- [ ] P5-03 生成公开 test 预测、指标表和脱敏运行日志摘要。
- [ ] P5-04 验证推理不读取 test 标签、不依赖人工点击、不依赖本机路径。
- [ ] P5-05 固定依赖、Prompt、工具、语料、配置和 commit hash。
- [ ] P5-06 添加预算、限流、失败重试、超时和批量推理耗时说明。

## P6｜API、前端与比赛交付

- [ ] P6-01 实现 Run、Stage、Artifact、Finding、报告和审核查询 API。
- [ ] P6-02 实现研究运行、状态查看、证据链、反例和报告前端。
- [ ] P6-03 完成离线端到端验收和浏览器验收。
- [ ] P6-04 添加 `LICENSE`、第三方依赖许可证和源码发布说明。
- [ ] P6-05 从版本化系统结果生成不超过 30 页的技术方案 PDF（官网 2026-08-25 当前口径）。
- [ ] P6-06 准备可调用 API、前端链接、代表性案例和可选演示视频。

## 评测与质量门

- [ ] Q-01 建立 Schema 合法率、引用准确率、假设可操作化率和数据重算一致性指标。
- [ ] Q-02 建立中断恢复、重复运行、网络失败和模型 API 失败测试。
- [ ] Q-03 建立公开数据基线和 TSS/HSS 等指标报告。
- [ ] Q-04 完成公开数据复现演练和私有评测自查。
- [ ] Q-05 完成最终源码、配置、Prompt、工具、语料和日志清单审计。

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
| 2026-08-25 | P3-04 阻塞登记 | 冻结契约没有 `EvidenceTable`/`MechanismBrief` Schema；`docs/contracts/CONTRACTS.md` 要求原始 MechanismBrief 保持版本化来源，不能在实现任务中自行统一语义 | 需要项目所有者批准独立 Contract Change Request；P2-06 密钥轮换阻塞仍在 | P3-04（等待批准） |
