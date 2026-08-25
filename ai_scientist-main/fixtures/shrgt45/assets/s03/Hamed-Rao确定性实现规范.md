# Hamed–Rao 修正 Mann–Kendall 检验确定性实现规范

> 版本：V0.2（2026-07-30）  
> 状态：当前全信息基准提案，等待团队冻结；未查看正式科学结果  
> 用途：仅用于 C 敏感性分析“显著正单调趋势”，不替代主分析的连续真实时间斜率 `beta_TS`。

## 1. 软件、版本和函数

拟冻结的参考环境：

| 组件 | 版本 |
|---|---:|
| Python | `3.11.9` |
| NumPy | `1.26.4` |
| SciPy | `1.13.1` |
| pyMannKendall | `1.4.3` |

调用函数：

```python
import pymannkendall as mk

result = mk.hamed_rao_modification_test(
    x,
    alpha=0.05,
    lag=3,
)
```

其中 `x` 是按时间升序排列、等间隔 12 min 的 SHRGT45 数值序列。

该函数返回的 `result.p` 是**双侧 p 值**，本项目不直接使用它生成正向标签。本项目使用 `result.z` 另算正向单侧 p：

```python
from scipy.stats import norm

p_positive = norm.sf(result.z)
```

包内 `result.slope` 按观测序号计算，不使用真实时间戳，因此不得替代本项目的 `beta_TS`。`beta_TS` 仍按真实小时差另行计算。

## 2. 确定性计算规则

设通过资格检查的等间隔序列为 `x_1,...,x_n`，其中 `n=14/15/16`。

### 2.1 Mann–Kendall 统计量

```text
S = sum_{i<j} sign(x_j-x_i)
```

`S>0` 表示总体方向偏上升，`S<0` 表示偏下降。

### 2.2 detrending

先按观测序号计算 Sen 斜率：

```text
beta_index = median_{i<j} [(x_j-x_i)/(j-i)]
```

再去趋势：

```text
r_i = x_i - i*beta_index,  i=1,...,n
```

这里的 `beta_index` 只用于估计自相关；C 标签的方向仍由真实时间戳计算的 `beta_TS>0` 判断。

### 2.3 rank ACF

对去趋势残差 `r_i` 取平均秩；并列残差使用平均名次：

```python
R = scipy.stats.rankdata(r, method="average")
```

令 `R_bar` 为秩均值，rank ACF 定义为：

```text
rho_k = sum_{i=1}^{n-k}[(R_i-R_bar)(R_{i+k}-R_bar)]
        / sum_{i=1}^{n}(R_i-R_bar)^2
```

### 2.4 进入修正的 lag

只检查 `lag-1`、`lag-2`、`lag-3`，不检查更长 lag。显著界限为：

```text
B = Phi^(-1)(0.975)/sqrt(n)
```

对 `k=1,2,3`：

```text
rho_k_used = rho_k,  当 abs(rho_k) > B
rho_k_used = 0,      当 abs(rho_k) <= B
```

因此只让显著的 rank ACF 进入修正；等于边界时不进入。正、负显著自相关都保留。

### 2.5 Hamed–Rao 方差修正

先计算含并列值修正的原始 MK 方差：

```text
Var0(S) = [n(n-1)(2n+5)
           - sum_g t_g(t_g-1)(2t_g+5)] / 18
```

其中 `t_g` 是第 `g` 组相同 SHRGT45 数值的个数。

方差修正因子为：

```text
CF = 1 + 2/[n(n-1)(n-2)]
         * sum_{k=1}^{3}[(n-k)(n-k-1)(n-k-2)*rho_k_used]
```

修正后方差：

```text
Var_HR(S) = Var0(S)*CF
```

如果三个 lag 均不显著，则 `CF=1`。

## 3. tie、continuity correction 和单侧 p

### 3.1 tie correction

原始 SHRGT45 中的相同值不删除，按上式中的 `t_g` 修正 `Var0(S)`。相同值按输入数值精确相等判断，检验前不额外四舍五入。

### 3.2 continuity correction

固定使用连续性校正：

```text
Z_HR = (S-1)/sqrt(Var_HR),  当 S>0
Z_HR = 0,                   当 S=0
Z_HR = (S+1)/sqrt(Var_HR),  当 S<0
```

不得随软件默认设置关闭。

### 3.3 正向单侧 p

本项目检验的是正向趋势，因此使用：

```text
p_positive = 1-Phi(Z_HR) = scipy.stats.norm.sf(Z_HR)
```

不能直接使用包返回的双侧 `result.p`，也不能无条件把双侧 p 除以 2；当 `Z_HR<0` 时，正向单侧 p 应大于 0.5。

C 标签定义为：

```text
TrendUp_C = 1  iff  beta_TS > 0 and p_positive < 0.05
TrendUp_C = 0  otherwise, provided the test is computable
TrendUp_C = NA if the test is not computable
```

`beta_TS>0` 和 `p_positive<0.05` 均采用严格不等式。

## 4. 特殊序列和异常返回

| 情况 | 确定性处理 |
|---|---|
| 原始序列全部相同 | 返回 `status=CONSTANT_NO_TREND`、`S=0`、`Z_HR=0`、`p_positive=1`、`TrendUp_C=0`；不计算 ACF |
| 有效点数少于14 | 返回 `status=NA_INSUFFICIENT_POINTS`，统计量、p 和标签均为 `NA` |
| 有效点数多于16 | 返回 `status=NA_INVALID_WINDOW`，检查重复记录或窗口生成错误 |
| 非常数序列去趋势后 rank 方差为0 | 返回 `status=NA_ZERO_RESIDUAL_VARIANCE`，p 和标签为 `NA` |
| `CF` 非有限或 `CF<=0` | 返回 `status=NA_INVALID_CORRECTION_FACTOR`，p 和标签为 `NA` |
| `Var_HR` 非有限或 `Var_HR<=0` | 返回 `status=NA_INVALID_VARIANCE`，p 和标签为 `NA` |
| 输入含 `NaN`、无穷大或非法值 | 先按缺帧处理；若仍无法满足第5节资格，返回相应 `NA` |
| 其他程序异常 | 返回 `status=NA_RUNTIME_ERROR` 并保存错误信息 |

所有不可计算窗口必须保留 `status`，不得改记为 `TrendUp_C=0`，也不得自动回退到普通 MK、预白化或其他修正方法。

## 5. 缺帧和不等间隔序列

`[t-3h,t]` 为闭区间，标称 12 min 节拍下共有16个预期时隙。先按真实时间戳把观测映射到这些时隙，再执行以下规则：

1. 有效点数必须为14、15或16；少于14返回 `NA_INSUFFICIENT_POINTS`。
2. 剩余有效观测必须保持连续的12 min间隔。
3. 缺帧只出现在窗口边缘，且剩余14–15帧仍连续等间隔时，可以执行 Hamed–Rao。
4. 内部缺帧造成任意相邻有效点相隔24 min或更长时，返回 `NA_IRREGULAR_GAP`。
5. 不得删除内部缺帧后把剩余点重新编号为连续序列，因为这会使同一个 `lag-1` 在不同窗口分别代表12 min或24 min。
6. 不做插值、前向填充、后向填充或平滑后再执行 Hamed–Rao。
7. 时间戳重复或无法唯一映射到12 min时隙时，返回 `NA_INVALID_TIME_GRID`。

真实时间戳 Theil–Sen 主分析与此分开：若其自身质量门允许，缺帧窗口仍可使用真实时间差计算连续 `beta_TS`；只是 Hamed–Rao 的 C 敏感性标签记为 `NA`。

## 6. 最小保存结果

每个窗口至少保存：

- `n_valid`：实际进入检验的有效观测点数。
- `missing_pattern`：16 个预期时隙中缺失的位置，用于判断是否存在内部缺帧。
- `actual_span_min`：首末有效观测之间的实际分钟跨度。
- `status`：本窗口的计算状态或不可计算原因。
- `beta_TS`：使用真实时间戳计算的 Theil–Sen 斜率，单位为百分点/小时。
- `S`：Mann–Kendall 趋势统计量，正值偏上升、负值偏下降。
- `Var0(S)`：仅经并列值修正的原始 MK 方差。
- `rho_1`：去趋势秩序列在 lag-1 的自相关系数。
- `rho_2`：去趋势秩序列在 lag-2 的自相关系数。
- `rho_3`：去趋势秩序列在 lag-3 的自相关系数。
- `lag_1_used`：lag-1 是否达到显著 ACF 界限并进入方差修正。
- `lag_2_used`：lag-2 是否达到显著 ACF 界限并进入方差修正。
- `lag_3_used`：lag-3 是否达到显著 ACF 界限并进入方差修正。
- `CF`：Hamed–Rao 方差修正因子。
- `Var_HR(S)`：经 Hamed–Rao 修正后的 MK 方差。
- `Z_HR`：使用 continuity correction 后的修正趋势统计量。
- `p_positive`：针对正向趋势的单侧 p 值。
- `TrendUp_C`：C 敏感性标签；1 为显著正单调趋势，0 为可计算但不满足条件，`NA` 为不可计算。

以上规则如在第三次会议被修改，应形成新版本并在查看正式科学结果前重新冻结。
