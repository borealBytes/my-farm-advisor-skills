# Row Crop Field Timeline Dashboard

Aligned four-panel dashboard for a single field: NDVI accumulation (Sentinel-2), daily precipitation, temperature extremes, and cumulative GDD — all on a shared time axis.

## Run from GitHub (local machine)

```bash
git clone https://github.com/nbmorr/my-farm-advisor-skills.git
cd my-farm-advisor-skills
git checkout final-assignment
cd my-farm-advisor/dashboard
pip install -r requirements.txt
python src/row_crop_dashboard.py --json dashboard_data.json
```

Open http://127.0.0.1:8050.

## Run from runtime tree (VM with data pipeline)

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python src/row_crop_dashboard.py --grower iowa-grower --farm iowa-farm --field osm-1219926116
```

## Export static HTML

```bash
python src/row_crop_dashboard.py --json dashboard_data.json --export /tmp/dashboard.html
```

## Regenerate data package

Run on the VM where the runtime tree lives:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python src/export_data_package.py --grower iowa-grower --farm iowa-farm --field osm-1219926116
```

## Panels

1. **NDVI Accumulation** — per-scene Sentinel-2 NDVI values, colored by year, with CDL crop label
2. **Daily Precipitation** — bars, same x-axis
3. **Temperature Extremes** — Tmin/Tavg/Tmax with range fill
4. **Cumulative GDD** — growing degree days (base 10°C, capped at 30°C, from May 1)

All four panels share a common date axis (2021-2025). Automated captions under the plot summarize key statistics.

## Requirements

- Python 3.8+, plotly, dash, pandas, numpy (`pip install -r requirements.txt`)
- Runtime tree mode only: geopandas, rasterio

## Files

```
dashboard/
  README.md
  requirements.txt
  dashboard_data.json   Pre-computed for osm-1219926116 (496 KB)
  src/
    row_crop_dashboard.py   Dash app
    dashboard_utils.py      Data loader, NDVI/GDD/weather extraction
    export_data_package.py  Regenerate dashboard_data.json
```
