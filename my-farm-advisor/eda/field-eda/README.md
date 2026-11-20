# Field EDA

Cross-grower, field-level exploratory analysis over an installed My Farm Advisor
runtime. Reads the pipeline's own boundary, CDL, and weather outputs, and writes
static figures and tables. No soil, no report, no dashboard.

## What it answers

- **Boundaries** — How large are the fields, and does the boundary source show
  through in their shape? Are the growers running one field population or two?
- **CDL** — What does each field grow across 2019–2023, how do the rotations
  differ, and how often does corn follow corn?
- **Weather** — How do the growing seasons compare between growers, and can
  weather actually distinguish fields inside a grower?

## Inputs

Everything is read from the runtime under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`:

| Input | Path | Used by |
| --- | --- | --- |
| Field boundaries | `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` | boundaries, CDL map, weather map |
| Farm metadata | `growers/<grower>/farms/<farm>/farm.json` | labels and state code |
| Weather table | `growers/<grower>/farms/<farm>/derived/tables/<prefix>_weather_<start>_<end>.csv` | weather |
| CDL composition | `growers/<grower>/farms/<farm>/derived/tables/<prefix>_cdl_<start>_<end>_full_composition.csv` | CDL |

`<prefix>` is the farm slug with a trailing `-farm` removed and hyphens turned
into underscores, matching `data-pipeline/src/scripts/lib/paths.py`.

Required columns are asserted at discovery time; a missing column fails the run
with the file name and the column name. Soil is never read: discovery selects
only weather and CDL file patterns, and `assert_schema` rejects a soil-named
path outright if one is ever passed in.

## Outputs

Written to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda` by default
(override with `--out`):

```text
manifest.json                 inputs, hashes, row counts, grid cells, parameters
tables/
  field_metrics.csv           one row per field: geometry, crop history, season
  boundary_analysis.csv       geometry tests by grower and by boundary source
  cdl_analysis.csv            rotation, corn-after-corn, crop-mix test
  weather_analysis.csv        variance attribution and GDD/precipitation coupling
figures/
  01_boundary_area.png        + 01_boundary_area.caption.md
  02_boundary_shape.png       + caption
  03_cdl_composition.png      + caption
  04_cdl_rotation.png         + caption
  05_weather_gdd.png          + caption
  06_weather_precip.png       + caption
maps/
  01_boundary_sources.png     + caption
  02_cdl_2023.png             + caption
  03_weather_precip.png       + caption
```

Each caption sidecar records the question, what to look at, the caveat that must
travel with the figure, and the input files. Captions are inputs to a later
report, not a report.

## Runbook

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/eda/field-eda
./scripts/install.sh

# validate inputs without writing anything
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/field-eda/scripts/run_field_eda.py" \
  --check-only

# full run over every discovered grower
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/field-eda/scripts/run_field_eda.py"

# one category, one grower
... run_field_eda.py --grower ne-york-grower --category cdl
```

`--grower` is repeatable. Without it, every grower with a boundary, a weather
table, and a CDL composition table is included. A grower with some but not all
inputs fails loudly rather than being skipped.

## Output rules

- Static only: PNG figures and CSV tables. No HTML, no JavaScript, no server.
- Deterministic: growers and fields are sorted, palettes are fixed, no figure
  embeds a timestamp. Two consecutive runs produce identical tables.
- Runtime-only: nothing is written inside the skill checkout or under Git.
- Captions carry the caveat mechanically. Weather captions must state the
  NASA POWER grid-cell count; CDL captions must state the minimum pixel count.

## Limits to state, not hide

- **Weather is a grid, not a field measurement.** Fields inside a grower often
  share two to four NASA POWER cells, so within-grower weather differences are
  mostly sampling noise. The analysis reports this as a null result and the map
  shows it.
- **CDL is 30 m raster.** A 1.3 ha field is about 14 pixels, so crop shares are
  quantised and can sum below 100% when coverage is partial.
- **Boundary source is confounded with size.** CSB fields in this dataset are
  large and irregular; OSM parcels are small and more compact. The analysis
  reports the confound instead of attributing it to management.
- **Small n.** Thirty fields and fifteen grower-years support effect sizes and
  confidence intervals, not population-level claims about "growers".

## Maps and the frame contract

Maps are farm overviews, not single-field footprints, so they use a local UTM
frame pinned to the south-west corner of the farm extent with kilometre ticks, a
4% viewport pad (`field_frame.view_extent`), a boxed north arrow, and a scale
bar. Auto-rotation is not applied: rotating a multi-field farm to a single long
axis would misrepresent layout. Single-field renderers keep the full field-local
rotation contract.

## Related material

- Sibling EDA guides: [`../eda-explore`](../eda-explore/GUIDE.md),
  [`../eda-compare`](../eda-compare/GUIDE.md),
  [`../eda-correlate`](../eda-correlate/GUIDE.md),
  [`../eda-visualize`](../eda-visualize/GUIDE.md).
- Farm-scoped, soil-facing EDA scripts already live in
  `data-pipeline/src/scripts/eda/`; this subskill is deliberately separate
  because it is cross-grower and reads boundaries, CDL, and weather only.
