# TASK-P4-02：SHARP 参数注册、公式、单位与别名校验

> 状态：`COMPLETED`
>
> 所属阶段：P4-02
>
> 授权依据：项目所有者要求持续按根目录 `TODO.md` 推进，直到需要外部决策时停止。

## Goal

建立系统无关、确定性、可扩展的 SHARP 参数注册表。第一版只登记已经由冻结 SHRGT45
Fixture 和当前移交材料共同核实的 `SHRGT45`，不猜测未核实参数的公式或单位。

注册表必须：

- 固定 canonical keyword、英文全称、定义、公式 ID、公式、单位、范围和观测层级；
- 记录数据系列、cadence、像素选择口径、审计字段和来源；
- 只接受不会改变语义的别名；
- 显式拒绝 `MEANSHR`、平均剪切角、0–1 fraction 等易混语义；
- 校验数值有限性、范围、单位和公式 ID，不做静默单位转换。

## Allowed changes

```text
src/ai_scientist_mvp/skills/parameter_registry.py
src/ai_scientist_mvp/skills/__init__.py
tests/unit/test_parameter_registry.py
tests/smoke/test_project_structure.py（仅源码白名单）
docs/PARAMETER_REGISTRY.md
tasks/TASK-P4-02.md
../TODO.md
../docs/AI_SCIENTIST_IMPLEMENTATION_PLAN.md（仅 P4-02 证据说明）
```

## Forbidden changes

- `contracts/**`、`docs/contracts/**`、`docs/adr/**`、`governance/**`、`fixtures/**`；
- 数据读取、特征计算、正式统计执行或科学结论；
- `.env`、网络访问、机器绝对路径；
- 修改、执行、导入或提交解压材料目录。

## Acceptance

1. `SHRGT45` 定义固定为有效像素中 `phi_i > 45°` 的面积百分比；
2. 原始单位固定为 percent，范围为闭区间 0–100；
3. canonical keyword 大小写可规范化，安全描述别名可解析；
4. `MEANSHR`、平均剪切角和含 mean-shear 的历史错误表述显式报歧义；
5. fraction、度、NaN、无穷、布尔值和越界值 Fail Closed；
6. 注册项、别名和拒绝别名之间不得碰撞；
7. Ruff、mypy、专项测试和全量测试通过。
