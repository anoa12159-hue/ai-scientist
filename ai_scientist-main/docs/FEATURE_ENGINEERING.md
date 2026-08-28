# SHRGT45 Feature and Research Label Engineering

`ai_scientist_mvp.skills.feature_engineering` implements the frozen Research Mode transform
without network access, label inference, interpolation, or formal scientific execution.

The history window is the closed interval `[T0-3h,T0]`. Input remains in source order; duplicate
or decreasing `T_REC_TAI` values and mixed HARP rows fail closed. P4-03 quality rules are applied
before the feature is produced. The current formula is `OLS_TRUE_T_REC`: ordinary least squares
on actual elapsed hours and SHARP `SHRGT45` percent values. Outputs include the slope in percentage
points per hour, observed valid-endpoint difference, three-hour OLS-equivalent change, valid-frame
count, quality audit, and parameter-definition hash.

This OLS rule comes from the current P4-04 implementation contract and the 0814 Demo. The
historical Theil–Sen proposal is not silently substituted. Pixel-level SHRGT45 is also not rebuilt
from Br/Bp/Bt because the transferred inputs do not freeze a potential-field solver and all
measurement choices needed for a scientifically equivalent reconstruction.

Research labels require an explicitly same-unit, verified-complete event catalog covering the
whole `[T0,T0+6h)` horizon. GOES onset determines window membership and peak class determines the
M1.0+ threshold. `[T0,T0+3h)` M1.0+ events are recorded as early events; the target uses only
`[T0+3h,T0+6h)`, including `+3h` and excluding `+6h`. No HARP/NOAA mapping or cumulative-label
subtraction is performed implicitly.

All results remain `NOT_EVALUATED / DEVELOPMENTAL / NOT_AUTHORIZED`. A complete structural result
does not authorize formal statistics or establish support for the hypothesis.
