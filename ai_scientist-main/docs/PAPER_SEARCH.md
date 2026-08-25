# `paper_search` Skill

`ai_scientist_mvp.skills.paper_search` 提供文献检索的最小、可替换边界。Skill 负责查询规范化、
年份/领域过滤、结果去重和结果数量上限；Provider 负责从指定语料返回论文元数据。

首版内置 `InMemoryPaperSearchProvider`，只接受调用方注入的 `PaperSearchHit` 序列，不访问网络、
不读取环境变量，也不保存论文全文。`corpus_version` 必须由调用方显式固定，便于后续把离线
语料快照的版本和哈希绑定到 Artifact。在线 Semantic Scholar 或其他服务只能作为后续经授权的
Provider 接入，不得绕过 Skill 边界。

```python
from ai_scientist_mvp.skills.paper_search import (
    InMemoryPaperSearchProvider,
    PaperSearchQuery,
    PaperSearchSkill,
)

skill = PaperSearchSkill(InMemoryPaperSearchProvider(papers, corpus_version="fixture-v1"))
result = skill.search(PaperSearchQuery("magnetic complexity", limit=10))
```

`PaperSearchResult.as_dict()` 只包含论文 ID、标题、作者、摘要（若 Provider 提供）、年份、期刊、
链接、引用数和来源标识等元数据。全文获取、缓存版本、引用链扩展和逐字引用校验不会在
`paper_search` 中隐式执行。

## 全文与引用链

P3-02 的 `PaperFetchSkill` 接收显式注入的 `PaperContentFetcher` 和 `PaperDocumentCache`。它按
`cache_version + paper_id + source_uri + expected_sha256` 计算缓存身份，限制最大字节数，校验
SHA-256，并返回是否命中缓存；内置的 `InMemoryPaperDocumentCache` 只用于离线测试和小型
Fixture。缓存记录的元数据可通过 `PaperDocument.metadata()` 投影到 Artifact，全文本身不进入
Graph State。

`expand_citations()` 对注入的 `CitationProvider` 做有界 BFS，按 ID 稳定排序、去重并输出边，
通过 `max_depth` 和 `max_nodes` 防止无限扩展。网络全文 Provider、版权授权、持久化缓存和逐字
引用校验仍需后续任务明确数据来源与授权后接入；当前实现不会访问网络或凭证。

## 逐字引用校验

`QuoteVerifier` 接收论文 ID、原文快照、逐字引用和可选的字符位置/预期数字。只有原文中恰好
一个位置与引用完全相同、位置绑定有效且数字 token（支持小数、科学计数法和百分号）一致时，
结果才是 `VERIFIED`；缺失、重复、位置错误或数字不一致统一返回 `NOT_FOUND`，并只保留引用
SHA-256、位置和失败原因。返回对象不包含原文，便于把结果安全投影到 `EvidenceTable`。

## 固定语料与离线回退

`literature/shrgt45.snapshot.json` 是首个固定语料身份清单，只引用已纳入 SHRGT45 Fixture 的
四份 S02 Markdown 来源，不复制或改写来源字节。`SnapshotPaperSearchProvider` 启动时逐项校验
相对路径、字节数、SHA-256 和 UTF-8，任何漂移都 Fail Closed；检索结果只返回来源 ID、标题、
版本和相对路径，不把全文放入结果。

`FallbackPaperSearchProvider` 仅在主 Provider 明确抛出 `PaperSearchUnavailableError` 时使用
固定快照。程序错误、无效结果或其他异常不会被静默吞掉，从而区分“网络不可用降级”和实现
缺陷。离线 Replay 可直接绑定快照 Provider，不读取 `.env` 或任何 API Key。

## V13 Phase 1/Phase 2 映射

`parse_phase1_output()` 将 v13 Phase 1 Markdown 映射为 `Phase1EvidencePlan`：参数、论文候选、
DOI/arXiv 元数据和 P1–P5 覆盖状态。`parse_mechanism_brief()` 按 v13 `template.py` 与
`phase2_system.py` 的 V2.2 定义校验六个章节、全部必填字段、五张八列证据表、唯一证据编号、
候选假设和引用文献，生成 `MechanismBriefV22`/`EvidenceTable` DTO。

内部 DTO 不是新的 JSON Schema。持久化时由 `project_mechanism_snapshot()` 抽取参数、科学声称
上限、禁止表述和来源引用，生成现有冻结 `MechanismSnapshot`。V2.3 输入不会静默冒充 V2.2；
V2.3 仍作为独立版本化来源处理。
