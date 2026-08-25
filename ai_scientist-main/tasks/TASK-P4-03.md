# TASK-P4-03：FITS/CSV 读取与质量、投影、时间一致性

> 状态：`COMPLETED`
>
> 所属阶段：P4-03
>
> 授权依据：项目所有者要求持续按根目录 `TODO.md` 推进，直到需要外部决策时停止。

## Goal

实现系统无关的确定性数据读取与质量审计 Skill：

- 使用标准库严格读取 UTF-8/UTF-8-BOM CSV，保留缺失值，不依赖 Pandas；
- 使用固定版 Astropy/NumPy 读取 FITS，不自行实现 FITS 标准；
- 校验 `DATE-OBS/T_REC/HARPNUM/NOAA_AR/BUNIT/WCS/shape/NaN/Inf`；
- 校验 Br/Bp/Bt 同记录、同 shape、同 CEA WCS；
- 按历史开发性规则审计 QUALITY 致命位与 3h cadence 窗；
- 不插值、不压缩缺帧、不把数据失败转成科学结论。

## Allowed changes

```text
src/ai_scientist_mvp/skills/data_loader.py
src/ai_scientist_mvp/skills/__init__.py
tests/unit/test_data_loader.py
tests/smoke/test_project_structure.py（仅源码与固定依赖白名单）
docs/DATA_LOADER.md
tasks/TASK-P4-03.md
pyproject.toml（仅固定 Astropy/NumPy 依赖及 Astropy 缺少类型标记的 mypy 边界）
../TODO.md
../docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md（仅 P4-03 证据说明）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`；
- 执行历史脚本、访问 JSOC/NCEI/网络、读取 `.env`；
- 修改历史数据、插值缺帧、邻帧替换、正式统计或科学结论；
- 提交任何解压材料目录或测试运行产物。

## Acceptance

1. CSV 重复列、错行宽、缺必需列、非 UTF-8 和必填缺失值 Fail Closed；
2. FITS 只接受二维数值 image HDU，必需 header 完整且 BUNIT 为 Gauss；
3. Br/Bp/Bt 必须来自同一 HARP/T_REC，shape、WCS 与 CEA 投影一致；
4. NaN 比例受显式阈值约束，Inf 一律拒绝；
5. QUALITY `0x80000000/0x40000000` 帧排除，其他非零位不擅自解释；
6. 3h 窗至少 14/16 有效帧、跨度至少 160 分钟、最大 gap 不超过 24 分钟；
7. Ruff、mypy、专项和全量离线测试通过。

## Completion evidence

- 专项：`tests/unit/test_data_loader.py`，21 passed；
- 相关回归：165 passed；
- 全量离线测试：322 passed；
- `ruff check .`、`mypy src`、公开 API 导入与冻结基线复核通过；
- 未访问网络或凭证，未执行或修改解压材料中的历史脚本与数据。
