---
name: ndvi-weather-dashboard
description: Generate an HTML dashboard combining Sentinel-2 NDVI, NASA POWER weather, and cumulative GDD for a single field-year. Includes event detection (heavy rain, hot days, cool periods, NDVI dips, rapid NDVI increases) and annotated 4-panel chart.
version: 1.0.0
author: Boreal Bytes
tags: [ndvi, sentinel, weather, gdd, dashboard, html, visualization]
---

# Workflow: ndvi-weather-dashboard

## Description

Generate a self-contained HTML dashboard for any field-year in the data-pipeline runtime. The dashboard combines four aligned panels (NDVI, precipitation, temperature, cumulative GDD) on a shared date axis, with automatic event detection and styled callout cards.

## When to Use This Workflow

- **Season review**: Review a field's NDVI trajectory alongside weather and GDD accumulation
- **Event spotting**: Identify heavy rain, heat stress, cool periods, NDVI anomalies
- **Crop stage tracking**: Overlay GDD-based growth stage benchmarks on observed conditions
- **Field reports**: Embed the self-contained HTML in field summaries or farm reports

## Prerequisites

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
```

The runtime must have processed the target field through the data pipeline (satellite imagery, weather, CDL crop join).

## Quick Start

### Python API

```python
from ndvi_weather_dashboard import generate_dashboard

path = generate_dashboard(
    field_slug="osm-1499317763",
    year=2023,
    grower_slug="il-grower",
    farm_slug="il-grower-illinois",
)
print(f"Dashboard: {path}")
```

### CLI

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor-skills/my-farm-advisor/eda/ndvi-weather-dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  ndvi_weather_dashboard.py osm-1499317763 --year 2023
```

## Dashboard Layout

```
Panel 1: Sentinel-2 NDVI
  Per-scene field-mean NDVI scatter + connecting curve
  Annotations: dips, rapid rises

Panel 2: Precipitation
  Daily PRECTOTCORR bars (mm)
  Heavy rain callouts (>= 25 mm)

Panel 3: Temperature
  T2M_MAX / T2M_MIN ribbon with mean overlay
  Hot day (>= 35 C) and cool-period annotations

Panel 4: Cumulative GDD
  Running GDD sum (base 10 C, cap 30 C) from DOY 60
  Crop-stage reference lines (VE, V6, V12, R1, R6)
```

## Event Detection

| Event | Threshold | Source |
|-------|-----------|--------|
| Heavy Rain | PRECTOTCORR >= 25 mm | NASA POWER |
| Hot Day | T2M_MAX >= 35 C | NASA POWER |
| Cool Period | 3+ days below 10th percentile T2M_MIN | NASA POWER |
| NDVI Dip | Local minimum 0.05 below both neighbors | Sentinel-2 |
| Rapid NDVI Rise | Day-over-day delta >= 0.10 | Sentinel-2 |

## Input Data

| Asset | Path (relative to field root) |
|-------|-------------------------------|
| CDL crop join | `derived/tables/ndvi_year_crop_join.csv` |
| Sentinel manifest | `satellite/sentinel/manifest.json` |
| Scene NDVI rasters | `satellite/sentinel/{year}/sentinel_{date}/sentinel_{date}_ndvi.tif` |
| Field boundary | `boundary/field_boundary.geojson` |
| Daily weather | `weather/daily_weather.csv` |

## Output

- Self-contained HTML file at `<field>/derived/dashboards/ndvi_weather_dashboard_<year>.html`
- Opens in any browser with no external dependencies
- Chart is embedded as base64 PNG, styling is inline CSS

## Data Quality Checks

The dashboard checks for and reports:

- Fewer than 2 usable Sentinel scenes for the target year
- Scenes excluded due to cloud cover > 70%
- More than 10% missing weather days in the Mar-Nov window
- Missing CDL crop entry, Sentinel manifest, or field boundary

Warnings appear as colored banners above the chart.

## Customization

### GDD Parameters

```python
from ndvi_weather_dashboard import generate_dashboard
from ndvi_weather_dashboard import GDD_BASE_TEMP, GDD_CAP_TEMP, GDD_START_DOY

# These defaults match corn:
print(f"Base: {GDD_BASE_TEMP} C, Cap: {GDD_CAP_TEMP} C, Start DOY: {GDD_START_DOY}")
```

### Event Thresholds

```python
from ndvi_weather_dashboard import HEAVY_RAIN_THRESHOLD_MM, HOT_DAY_THRESHOLD_C
```

## GDD Calculation

Daily GDD = max(0, (T2M_MAX + T2M_MIN) / 2 - 10 C), capped at 30 C

Accumulation starts March 1 (DOY 60). Stage-reference lines are crop-specific:

**Corn**: VE (120), V6 (250), V12 (550), R1 (1100), R3 (1700), R6 (2500)

**Soybeans**: VE (130), V6 (350), R1 (750), R5 (1400), R8 (2100)

## Notes

- Sentinel-2 scenes with cloud cover > 70% are excluded from the NDVI time series
- The chart focuses on the growing season (March 1 - November 30)
- Event callout cards show the top events per type, sorted chronologically
- The NDVI dip/surge detection requires at least 3 valid scenes
- Run from the data-pipeline `.venv` for geospatial dependency support

## Example Output

The generated HTML contains:

```
ndvi_weather_dashboard_2023.html
├── Header bar (field, crop, year, county, acres)
├── Warning banners (if any)
├── 4-panel chart (embedded PNG)
├── Event callout cards (styled grid)
└── Footer
```
