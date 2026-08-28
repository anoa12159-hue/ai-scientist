# TASK-P4-04：SHRGT45 特征、时间窗与研究标签构造

> 状态：`COMPLETED`
>
> 所属阶段：P4-04
>
> 授权依据：项目所有者要求持续按根目录 `TODO.md` 推进，直到需要外部决策时停止。

## Goal

实现 Research Mode 的系统无关、确定性特征与标签边界：

- 从同一 HARP 的 SHARP `SHRGT45` 关键词序列切出闭区间 `[T0-3h,T0]`；
- 复用 P4-03 质量门，在真实 `T_REC` 时间轴上计算 OLS 斜率与实际首末差；
- 按 GOES onset 和 peak class 构造同单位 `[T0+3h,T0+6h)` M1.0+ 标签；
- 单独记录 `[T0,T0+3h)` 早发 M1.0+，不得据此改写主标签；
- 保持 `NOT_EVALUATED / DEVELOPMENTAL / NOT_AUTHORIZED`。

冻结实现口径以 P4-04 实现契约与 0814 当前 Demo 为准。历史 Hypothesis
中的 Theil–Sen 是未冻结提案，不得静默替换已冻结 OLS。当前材料也不足以从 Br/Bp/Bt
安全重建势场和像素级 SHRGT45，本任务只处理已注册、已校验的 SHARP keyword。

## Allowed changes

```text
src/ai_scientist_mvp/skills/feature_engineering.py
src/ai_scientist_mvp/skills/__init__.py
tests/unit/test_feature_engineering.py
tests/smoke/test_project_structure.py（仅源码白名单）
docs/FEATURE_ENGINEERING.md
tasks/TASK-P4-04.md
../TODO.md
../docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md（仅 P4-04 证据说明）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`；
- 像素级势场求解、Theil–Sen/Mann–Kendall、正式统计或科学结论；
- 隐式 HARP/NOAA 映射、从累计标签推导非重叠 3–6h 标签；
- 未完整覆盖事件目录时生成负标签；
- `.env`、网络访问、机器绝对路径；
- 修改、执行、导入或提交解压材料目录。

## Acceptance

1. 历史窗严格使用 `[T0-3h,T0]`，输入乱序、重复时刻或混合 HARP Fail Closed；
2. OLS 使用真实 TAI 时间差，质量不合格或锚点无有效观测时不输出特征；
3. 输出百分点/小时斜率、实际首末差、有效帧和参数定义哈希；
4. 真实冻结 SHRGT45 Fixture 重算结果与 0814 OLS/差值一致；
5. Target 严格使用同单位、onset 和 `[T0+3h,T0+6h)`；
6. `+3h` 计正例、`+6h` 不计，0–3h 事件只记录早发状态；
7. 事件目录范围不完整、单位不一致、级别/时间非法时 Fail Closed；
8. Ruff、mypy、专项和全量离线测试通过。

## Completion evidence

- 专项：`tests/unit/test_feature_engineering.py`，16 passed；
- 相关回归：特征、P4-03 数据读取和 P4-02 参数注册共 66 passed；
- 全量离线测试：338 passed；
- 真实冻结 SHRGT45 Fixture 重算得到 OLS `0.078529` 百分点/小时、首末差 `0.033`，与 0814 当前结果一致；
- `ruff check .`、`mypy src`、公开 API 导入与冻结基线复核通过；
- 未访问网络或凭证，未执行或修改解压材料中的历史脚本与数据。
