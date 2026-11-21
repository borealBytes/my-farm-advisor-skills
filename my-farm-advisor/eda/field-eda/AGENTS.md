# Field EDA — Local Instructions

## Purpose

Static, cross-grower field-level EDA for boundary, CDL, weather, and county
maturity data. It is an analysis consumer of the data pipeline, not part of it.

## Boundary of this subskill

- In scope: discovery, derived metrics, statistical tests, static PNG figures,
  CSV tables, caption sidecars, and a manifest.
- Out of scope: report or HTML generation, interactive dashboards, data ingest,
  soil, imagery, terrain, and yield, cost, or profit modelling, plus any change
  to pipeline data.
- Never wire this into `run_farm_pipeline.py`. It is explicit-invocation only.
- Never write outputs inside the skill checkout. Runtime outputs belong under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/`.

## Analytical rules

- No soil input. Discovery selects boundary, weather, CDL, and shared county
  maturity files only, and a soil-named path is rejected outright. Do not add a
  soil loader.
- Totals and shares must be computed per field, then aggregated. Summing a
  per-field weather table across fields multiplies precipitation by the field
  count — a real bug this rule exists to prevent.
- Report effect sizes and confidence intervals alongside any p-value, and state
  the sample size in the caption.
- Weather caveats are mechanical, not editorial: the grid-cell count comes from
  `discover.py` and is injected into the caption. Do not hand-write a caption
  that omits it.
- The within-grower weather result is a null result. If a future change makes it
  look like fields differ meaningfully, suspect the aggregation before believing
  the plot.
- Two GDD definitions are deliberate and must never be mixed: April–September
  with no cap for the weather category, and the whole calendar year with a 30 °C
  cap for maturity fit. Comparing one against the other manufactures a shortfall.
- Maturity fit is a county-level verdict. Do not rank fields on it: field spread
  is NASA POWER grid spread, and the county target is not derived from these
  fields.

## Figure rules

- Every figure follows the repository figure gate in `../../../CONTRIBUTING.md`.
- Farm overview maps: local UTM frame pinned to the farm extent's south-west
  corner, kilometre ticks, `field_frame.view_extent` padding, boxed north arrow,
  scale bar, shared legend. Auto-rotation is for single-field footprints only.
- Categorical palettes must match between a map and any bar chart of the same
  classes. A crop colour means the same crop everywhere.
- Every figure writes a `*.caption.md` sidecar. A figure without a caption is
  incomplete.

## Build and review

- After any change, run `--check-only`, then a full run, then confirm the tables
  are byte-identical across two runs.
- Vision-review every figure that will be committed under `examples/output/`,
  and record the verdict in the commit message.
- Run `../../../scripts/validate.sh` from the repository root before committing.
