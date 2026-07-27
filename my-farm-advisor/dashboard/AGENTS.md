# Dashboard Skill Local Instructions

## Purpose

This skill generates an interactive Plotly Dash-based Row Crop Intelligence Dashboard for any grower in the My Farm Advisor runtime tree.

## Safe edit scope

Edits should stay inside `dashboard/` unless the user explicitly asks for a broader change. Do not edit sibling skills or parent tree files from a dashboard task unless explicitly requested.

## Quick start (JSON mode - no runtime tree needed)

```bash
cd dashboard/src
pip install -r ../requirements.txt
python row_crop_dashboard.py --json ../dashboard_data.json
```

Open http://127.0.0.1:8050.

## Runtime tree mode

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd dashboard/src
python row_crop_dashboard.py --grower iowa-grower --farm iowa-farm
```

## Custom host/port (for Docker/Cloudflare)

```bash
python row_crop_dashboard.py --json ../dashboard_data.json --host 0.0.0.0 --port 8050
```

## Export static HTML

```bash
python row_crop_dashboard.py --json ../dashboard_data.json --export /tmp/dashboard.html
```

## Regenerate data package

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python src/export_data_package.py --grower iowa-grower --farm iowa-farm
```

## Dependencies

- Required: plotly, dash, pandas, numpy (`pip install -r requirements.txt`)
- Runtime tree mode only: geopandas, rasterio
