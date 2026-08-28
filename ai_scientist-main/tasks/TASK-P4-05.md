# TASK-P4-05：JW-SSD 五分类统计与评测集隔离

> 状态：`COMPLETED`
>
> 所属阶段：P4-05 / JW-SSD Evaluation Mode

## Goal

为冻结的 `SHRGT45_官方五分类四模态扩展样本_20260826.zip` 建立只读 manifest、四模态完整性门、活动区分组泄漏检查和独立的五分类指标计算边界。

## Allowed changes

```text
src/ai_scientist_mvp/skills/jwssd_evaluation.py
src/ai_scientist_mvp/skills/__init__.py
tests/unit/test_jwssd_evaluation.py
docs/JWSSD_EVALUATION.md
tasks/TASK-P4-05.md
../TODO.md
../docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md（仅 P4-05 证据说明）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`；
- 读取评测标签进入推理函数；
- 将 Mount Wilson 类别转换为 M1+ 耀斑标签或生成 TSS/HSS；
- 将评测集用于训练、调参、阈值选择或模型选择；
- 依赖网络、API key、操作系统路径或第三方统计库；
- 修改、执行、导入或提交官方数据目录与 ZIP 内容。

## Acceptance

1. ZIP SHA256、CSV 清单、类别和四模态成员均可离线、确定性审计；
2. 标签只来自 `样本清单.csv`，缺失/重复/越界成员 Fail Closed；
3. 同一 `HARPNUM` 不得跨训练/验证/评测 split；
4. 输出混淆矩阵、每类 Precision/Recall/F1、macro/micro-F1、balanced accuracy；
5. 每类 Recall 提供 Wilson 95% 置信区间，空输入和未知标签拒绝；
6. 不改变历史 SHRGT45 Research Mode 的正式契约或科学结论。

## Completion evidence

- `tests/unit/test_jwssd_evaluation.py`：5 passed；
- 真实评测 ZIP：195 组、780 个四模态文件，类别计数 `50/50/25/50/20`；
- 归档 SHA256：`db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4`。
