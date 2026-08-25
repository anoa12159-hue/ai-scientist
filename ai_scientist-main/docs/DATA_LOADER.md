# Deterministic Data Loader

`ai_scientist_mvp.skills.data_loader` provides strict, system-independent CSV and FITS input
boundaries for the active SHRGT45 research path. It never downloads data, interpolates missing
frames, substitutes neighboring frames, or emits a scientific verdict.

CSV uses the Python standard library and accepts UTF-8 with or without a BOM. Duplicate/empty
headers, malformed row widths, missing required columns, and missing non-nullable values fail
closed. Empty and explicit `NA`/`NaN`/`null`/`none` cells become `None`; numeric coercion belongs
to the consuming deterministic Skill.

FITS uses pinned Astropy and NumPy. A frame must be a two-dimensional numeric image with
`DATE-OBS`, `T_REC`, `HARPNUM`, `NOAA_AR`, `BUNIT`, and complete two-axis WCS headers. Br/Bp/Bt
component audits require the same record identity, shape, exact WCS, and CEA projection. `Inf` is
always invalid; the permitted NaN fraction is an explicit caller input.

The current developmental history-window policy reproduces the transferred Demo rules:

```text
fatal QUALITY mask = 0xC0000000
minimum valid frames = 14 of 16
minimum valid span = 160 minutes
maximum valid-frame gap = 24 minutes
```

The two high QUALITY bits exclude their frames. Other nonzero bits are retained and counted but
not assigned an invented meaning. A passing quality audit means only that these deterministic
checks passed; it does not authorize formal statistics or support a scientific hypothesis.
