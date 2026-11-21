---
name: field-eda
description: >
  Cross-grower field-level exploratory analysis for My Farm Advisor runtime data.
  Compares field boundaries, CDL/cropland history, weather, and county maturity
  fit across fields and growers, and writes static PNG figures, CSV tables,
  caption sidecars, and a manifest. Use when someone asks for field-level EDA,
  grower comparisons, field shape and area statistics, rotation patterns,
  seasonal weather contrasts, or whether the local season supports the
  recommended corn maturity.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.2.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.2.0"
---

# Field EDA

Use this nested skill when someone asks for **field-level exploratory analysis**
across one or more growers: how fields are shaped and sized, what the cropland
history says, how the seasons compare, and whether the county-recommended corn
maturity fits the heat each season delivers. It produces static artifacts only —
PNG figures, CSV tables, caption sidecars, and a manifest. It never writes a
report, an HTML page, or an interactive dashboard.

Four categories. Boundaries, CDL, and weather each carry two figures, one
analysis table, and one map. Signals carries one figure and one table, because
its inputs are already mapped:

| Category | Figures | Analysis | Map |
| --- | --- | --- | --- |
| Boundaries | area distribution, shape vs area | source/size geometry test | fields by boundary source |
| CDL | crop composition, rotation timeline | rotation and corn-after-corn | 2023 crop map |
| Weather | cumulative GDD, monthly precipitation | variance attribution | seasonal precipitation |
| Signals | maturity fit | rotation continuity, maturity fit, weather risk | — |

Soil is not read. Discovery selects boundary, weather, CDL, and county maturity
tables; a soil-named path is rejected if one is ever supplied.

## Start Here

- Read [README.md](README.md) for inputs, outputs, runbook, and limits.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Read [references/figure-catalog.md](references/figure-catalog.md) for the question, story, and caveat behind each output.
- Read [references/metric-definitions.md](references/metric-definitions.md) before changing any derived measure.
- Open [`src/field_eda/discover.py`](src/field_eda/discover.py) for runtime discovery and schema validation.
- Open [`src/field_eda/metrics.py`](src/field_eda/metrics.py) for geometry, crop, and weather measures.
- Open [`src/field_eda/maturity.py`](src/field_eda/maturity.py) for the county relative-maturity target and maturity fit.
- Open [`scripts/run_field_eda.py`](scripts/run_field_eda.py) for the CLI.
- Run [`scripts/install.sh`](scripts/install.sh) to copy this subskill into an installed runtime.
- Read [PROVENANCE.md](PROVENANCE.md) for data attribution and analytical decisions.

## Routing Notes

- Invoke for requests such as "compare my fields", "field-level EDA", "how do the
  growers differ", "rotation patterns", "growing season comparison", "is the
  recommended maturity right for this farm", or "static charts of boundaries,
  CDL, weather, and maturity fit".
- Do not invoke for a single-farm soil or imagery analysis; use the sibling EDA
  guides or the data-pipeline subskills instead.
- Do not generate a yield, cost, or profit analysis here. The runtime carries no
  yield, as-applied, or economics data; maturity fit is a heat test, not a
  performance test.
- Do not generate reports here. Callers consume `manifest.json` and the caption
  sidecars to assemble a report elsewhere.
- Run only against an installed runtime (`DATA_PIPELINE_DATA_ROOT`).
- Not wired into `run_farm_pipeline.py`; run it explicitly after the farms have
  boundaries, CDL tables, weather tables, and the shared county maturity tables.
