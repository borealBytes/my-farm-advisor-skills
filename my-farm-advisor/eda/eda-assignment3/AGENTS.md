# Local Instructions

## Purpose

Generates field-season weather and NDVI storyline dashboards for individual fields. Each storyline combines Sentinel-2 NDVI scene values, daily weather time series, GDD accumulation, and crop type data into a single multi-panel PNG per field covering the full 2021–2025 record.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change.

## Read nearby docs first

Read `README.md` first. Review `src/weather_ndvi_storylines.py` for core processing functions.

## Runbook

From the runtime source copy after install:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_storylines.py \
  --grower-slug il-grower \
  --farm-slug il-grower-illinois \
  --field-id osm-1499627257
```

Output:

```
fields/<field>/derived/storylines/field_season_storyline.png
```

## Local validation

Open the output PNG and verify four panels render correctly with NDVI scatter, weather fill, GDD/precip lines, and year summary table.
