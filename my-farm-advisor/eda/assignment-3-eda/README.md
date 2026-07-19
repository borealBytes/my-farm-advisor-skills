# Assignment 3 — Aligned Field-Year EDA Dashboard

## Selected Field-Year

| Field | osm-1467726055 |
|---|---|
| Farm | Platte River Farm (Merrick County, NE) |
| Year | 2024 |
| CDL Crop | Corn (99.41%, code 1) |
| Acres | 75.7 |
| Soil | Leshara, Somewhat poorly drained, OM 2.0%, pH 7.6, CEC 16.25, Clay 21% |

## Dashboard Output

File: `~/my-farm-advisor-runtime/eda-outputs/assignment-3/dashboard_osm-1467726055_2024.png`

Four aligned panels sharing a single date axis (Jan–Dec 2024):

1. **NDVI** — 9 Sentinel-2 scene means with ±1σ, growth stage markers (VT, R1, R5, R6), gap annotations
2. **Precipitation** — Daily bars with cumulative overlay, annotated top-3 heaviest events
3. **Temperature Extremes** — Tmax/Tmin/Tavg with heat wave and late frost annotations
4. **Cumulative GDD** — Base 50°F accumulation with all 9 growth stage markers

## Data Sources (from runtime)

| Source | Path under `$DATA_PIPELINE_DATA_ROOT/data-pipeline/` |
|---|---|
| Field boundary | `growers/nebraska-grower/farms/nebraska-farm/fields/osm-1467726055/boundary/field_boundary.geojson` |
| Weather | `...fields/osm-1467726055/weather/daily_weather.csv` (2024: 366 days, no nulls) |
| Sentinel NDVI | `...fields/osm-1467726055/satellite/sentinel/2024/` (9 scenes, Mar 17–Nov 12) |
| CDL crop | `...farms/nebraska-farm/derived/tables/nebraska_2024_cdl.csv` |
| Soil | `...fields/osm-1467726055/soil/ssurgo_summary.csv` |

## Notable Events

- **Jun 5 → Jul 25**: NDVI +0.47 in 50 days — rapid canopy closure from V12 through tassel
- **Jul 25**: 43mm — heaviest single-day rainfall
- **Late Jul / early Aug**: Multiple 4-day heat waves (≥35°C max) during pollination window
- **Aug 4 → Sep 28**: 55-day NDVI scene gap — grain fill period unobserved by Sentinel-2
- **Aug 25**: 39.4°C — hottest day of the season
- **Sep 28**: NDVI −0.38 in 55 days — late-season senescence

## Requirements

- `DATA_PIPELINE_DATA_ROOT` env var pointing to the pipeline runtime
- Python packages: rasterio, matplotlib, numpy, pandas, pyproj, Pillow, shapely

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/eda/assignment-3-eda/scripts
python3 build_dashboard.py
```

## Reusability

Change the constants at the top of `build_dashboard.py` to target a different field, farm, grower, or year:

```python
FIELD_SLUG = "osm-1467726055"
YEAR = 2024
GROWER_SLUG = "nebraska-grower"
FARM_SLUG = "nebraska-farm"
```

## Assignment Summary

| Item | Value |
|---|---|
| **Workflow** | `my-farm-advisor/eda/assignment-3-eda/scripts/build_dashboard.py` |
| **Field** | `osm-1467726055` — Platte River Farm, Merrick County, NE |
| **Year** | 2024 |
| **CDL Crop** | Corn (99.41%) |

### Input Files (from data-pipeline runtime)

| File | Path relative to `$DATA_PIPELINE_DATA_ROOT/data-pipeline/` |
|---|---|
| Field boundary | `growers/nebraska-grower/farms/nebraska-farm/fields/osm-1467726055/boundary/field_boundary.geojson` |
| Daily weather | `growers/nebraska-grower/farms/nebraska-farm/fields/osm-1467726055/weather/daily_weather.csv` |
| Sentinel-2 NDVI | `growers/nebraska-grower/farms/nebraska-farm/fields/osm-1467726055/satellite/sentinel/2024/` (9 scenes) |
| CDL crop table | `growers/nebraska-grower/farms/nebraska-farm/derived/tables/nebraska_2024_cdl.csv` |
| Soil summary | `growers/nebraska-grower/farms/nebraska-farm/fields/osm-1467726055/soil/ssurgo_summary.csv` |

### Weather Metrics Calculated

- Daily: T2M (avg), T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, RH2M, WS10M
- Derived: GDD base 50°F, cumulative GDD, cumulative precipitation, 7-day rolling precip

### Dashboard Output

Relative to data-pipeline runtime root:
```
../eda-outputs/assignment-3/dashboard_osm-1467726055_2024.png
```
Four aligned panels (NDVI → Precip → Temperature → Cumulative GDD) on a shared date axis.

### How to Rerun

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd my-farm-advisor/eda/assignment-3-eda/scripts
python3 build_dashboard.py
```

Requires: `rasterio`, `matplotlib`, `numpy`, `pandas`, `pyproj`, `Pillow`, `shapely`.

### Known Data Limitations

- **NDVI scene gap**: 55 days (Aug 4 → Sep 28) — the grain fill / early dent period has no Sentinel-2 observations
- **50-day scene gap** (Jun 5 → Jul 25) — misses the V12–VT transition
- **Single field**: Dashboard covers one field only; not representative of whole-farm or regional patterns
- **GDD stages**: Approximate dates based on field-average weather; actual phenology varies within field
- **CDL**: 30 m resolution; small features (grassed waterways, field edges) may be misclassified
