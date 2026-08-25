# TASK-P4-01：假设、数据计划、验证与反例内部契约

> 状态：`COMPLETED`
>
> 所属阶段：P4-01
>
> 授权依据：项目所有者要求持续按根目录 `TODO.md` 推进，直到需要外部决策时停止。

## Goal

在不修改冻结公共 JSON Schema 的前提下，固化主动研究切片所需的内部 DTO：

- `HypothesisContractV21`，对应移交材料流程 03 的 `hypothesis.contract.json` DTO；
- `DataPlan`，对应同一 DTO 的八层 DataPlan handoff；
- `CounterexampleReport`，保持科学反例、数据/标签、样本/统计、研究定义和不可评估项分层；
- 复用现有冻结 `ValidationReport`，并提供确定性构造器；
- 将内部 DTO 投影到现有 `HypothesisSnapshot` 和 `CounterexampleSnapshot`。

解压材料中的模板、脚本和报告是只读证据，不执行、不导入、不修改。内部 DTO 不是新的公共
JSON Schema；正式公共契约变更仍须独立 Contract Change Request。

## Depends on

- 冻结 baseline content hash
  `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- P3-04 的 v13 V2.2 DTO/Markdown 映射；
- 移交材料流程 03 的 `hypothesis-contract.template.json`、手写 Validator 和八层 handoff；
- 移交材料流程 04/05 的 DataPlan 与反例报告边界；
- 现有冻结 `hypothesis-snapshot`、`validation-report`、`counterexample-snapshot` Schema。

## Allowed changes

```text
src/ai_scientist_mvp/skills/research_contracts.py
src/ai_scientist_mvp/skills/__init__.py
tests/unit/test_research_contracts.py
tests/smoke/test_project_structure.py（仅秘密扫描白名单如确有需要）
tasks/TASK-P4-01.md
../TODO.md
../docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`；
- T001–T006 既有任务卡、CompletionRecord、Replay Provider 输出语义；
- `.env`、密钥、网络 Provider、正式统计执行或科学结论；
- 修改、执行、导入或提交 `deep_research_agent_v13/`、`揭榜-移交版/`、`__MACOSX/`。

## Acceptance

1. Hypothesis V2.1 DTO 校验唯一主假设、冻结项目常量、六张操作化卡、五态和八层 handoff；
2. DataPlan 从已校验 Hypothesis 确定性提取，不新增科学口径；
3. ValidationReport 使用现有冻结 Schema，PASS 只代表确定性检查通过；
4. CounterexampleReport 保持五类问题分层，公共 Snapshot 只做明确的最小投影；
5. 正式结果已看、窗口冲突、缺层、状态冒充或科学状态提升均 Fail Closed；
6. Ruff、mypy、专项测试和全量离线测试通过。
