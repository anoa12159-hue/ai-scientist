# SHARP Parameter Registry

The active-research path uses `SharpParameterRegistry` as the deterministic source for SHARP
keyword identity, formulas, raw units, ranges, safe aliases, and known ambiguous names.

The initial registry intentionally contains only `SHRGT45`. Its definition is bound to Bobra et
al. (2014), Table 3 (`doi:10.1007/s11207-014-0529-3`) and the frozen SHRGT45 mechanism Fixture.
The raw value is the percentage of valid HARP pixels whose three-dimensional shear angle exceeds
45 degrees:

```text
SHRGT45 = 100 * count(phi_i > 45 deg) / CMASK
phi_i = arccos((B_obs_i dot B_pot_i) / (|B_obs_i| * |B_pot_i|))
```

The canonical unit is `percent`, with a closed valid range of `0..100`. `%`, `percentage`, and
`pct` are spelling aliases for the same scale. `fraction` or `0-1` is rejected rather than
silently multiplied by 100.

`SHRGT45` is not `MEANSHR`: the former is a thresholded area percentage, while the latter is a
mean shear angle. Generic names such as `shear angle`, and the historical phrase “percentage of
pixels with mean shear angle greater than 45 degrees”, fail as ambiguous instead of resolving to
either parameter.

New parameters must be added only after their official keyword, formula, raw unit, masks, data
series, and source citation are verified. Registration rejects accepted/rejected alias collisions,
so extending the registry cannot silently change an existing name's meaning.
