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
链接、引用数和来源标识等元数据。全文获取、缓存版本、引用链扩展和逐字引用校验属于 P3-02/P3-03，
不会在本 Skill 中隐式执行。
