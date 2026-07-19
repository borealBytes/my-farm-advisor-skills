# Dashboard Skill Local Instructions

## Purpose

This skill generates an interactive Plotly Dash-based Row Crop Intelligence Dashboard for any grower in the My Farm Advisor runtime tree.

## Safe edit scope

Edits should stay inside `dashboard/` unless the user explicitly asks for a broader change. Do not edit sibling skills or parent tree files from a dashboard task unless explicitly requested.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" row_crop_dashboard.py
```

Open http://127.0.0.1:8050 in a browser.

## Custom grower or farm

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" row_crop_dashboard.py \
  --grower nebraska-grower --farm nebraska-farm --port 8050
```

## Export static HTML

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" row_crop_dashboard.py \
  --grower iowa-grower --farm iowa-farm \
  --export /tmp/row_crop_dashboard.html
```

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required.
- The script reads from the canonical farm data tree under `growers/<grower>/farms/<farm>/`.
- The dashboard serves on the specified port (default 8050).

## Dependencies

- plotly, dash, pandas, geopandas, numpy, rasterio
- Install: `"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/pip" install plotly dash`
