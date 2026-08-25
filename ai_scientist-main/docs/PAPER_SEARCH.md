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
