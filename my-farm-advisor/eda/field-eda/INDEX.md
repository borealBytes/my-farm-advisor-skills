# Field EDA Index

## Start

- [SKILL.md](SKILL.md) — when to invoke, routing rules, category summary.
- [README.md](README.md) — inputs, outputs, runbook, limits.
- [AGENTS.md](AGENTS.md) — local build and review rules.
- [PROVENANCE.md](PROVENANCE.md) — data sources, attribution, analytical decisions.

## References

- [references/figure-catalog.md](references/figure-catalog.md) — every figure and table: question, story, caveat, inputs.
- [references/metric-definitions.md](references/metric-definitions.md) — formulas and thresholds used by the analysis.

## Code

- [`src/field_eda/discover.py`](src/field_eda/discover.py) — runtime discovery, schema validation, grid-cell counting, soil rejection.
- [`src/field_eda/context.py`](src/field_eda/context.py) — lazily loaded analysis context and output locations.
- [`src/field_eda/metrics.py`](src/field_eda/metrics.py) — geometry, crop, weather, and statistical measures.
- [`src/field_eda/maturity.py`](src/field_eda/maturity.py) — county RM/MG targets and the per-field maturity fit.
- [`src/field_eda/style.py`](src/field_eda/style.py) — palettes, matplotlib defaults, captions, map furniture.
- [`src/field_eda/maps.py`](src/field_eda/maps.py) — farm-overview UTM kilometre frame and map decoration.
- [`src/field_eda/boundaries.py`](src/field_eda/boundaries.py) — figures F1, F2; analysis A1; map M1.
- [`src/field_eda/cdl.py`](src/field_eda/cdl.py) — figures F3, F4; analysis A2; map M2.
- [`src/field_eda/weather.py`](src/field_eda/weather.py) — figures F5, F6; analysis A3; map M3.
- [`src/field_eda/signals.py`](src/field_eda/signals.py) — figure F7; analysis A4.
- [`scripts/run_field_eda.py`](scripts/run_field_eda.py) — CLI entry point.
- [`scripts/install.sh`](scripts/install.sh) — copy into an installed runtime.

## Examples

- [examples/README.md](examples/README.md) — the five reviewed anchor figures and how to regenerate them.
