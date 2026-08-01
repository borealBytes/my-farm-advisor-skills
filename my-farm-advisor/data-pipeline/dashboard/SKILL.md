---
name: row-crop-intelligence-dashboard
description: >
  Interactive Streamlit dashboard for analyzing row-crop field data across
  Corn Belt states. Displays KPIs, exploratory visualizations, interactive
  geospatial maps, weather/climate analysis, and soil health metrics using
  data from the My Farm Advisor data pipeline Assignments 1–3.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# Row Crop Intelligence Dashboard

## Purpose

Use this skill when the request is for an interactive dashboard showing farm field KPIs, exploratory data analysis, geospatial maps, weather patterns, or soil health metrics across multiple growers or states.

## Start Here

Open the dashboard application:

- [`app.py`](app.py) — Main Streamlit application
- [`data_loader.py`](data_loader.py) — Data loading and KPI computation module
- [`README.md`](README.md) — Dashboard overview and quick start
- [`AI_USAGE.md`](AI_USAGE.md) — AI usage documentation

## Runtime Requirements

- `DATA_PIPELINE_DATA_ROOT` must be set and point to a completed runtime with grower data
- Runtime venv with: `streamlit`, `pandas`, `numpy`, `plotly`, `folium`, `geopandas`, `streamlit-folium`

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline/dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  -m streamlit run app.py --server.port 8501
```

## Dashboard Sections

| Section | Requirement Met | Description |
|---------|----------------|-------------|
| KPI Section | ✅ | Total fields, acreage, avg NDVI, avg rainfall, sustainability score |
| EDA Visualization 1 | ✅ | Field size distribution and crop composition |
| EDA Visualization 2 | ✅ | Crop rotation patterns and diversity |
| Interactive Geospatial Map | ✅ | Folium map with field boundaries, tooltips, satellite overlay |
| Weather/Climate Visualization | ✅ | Precipitation, temperature extremes, GDD accumulation |
| Soil Health/Sustainability | ✅ | Sustainability score, radar chart, field summary table |
| Written Interpretations | ✅ | Narrative text throughout all sections |
| Updated README | ✅ | Dashboard documentation |
| Supplementary Dashboard Info | ✅ | This SKILL.md serves as supplementary info |
| AI Usage Documentation | ✅ | AI_USAGE.md documents AI assistance |

## Data Flow

```
Runtime Data (Assignments 1–3)
  ├── growers/{g}/farms/{f}/boundary/field_boundaries.geojson
  ├── growers/{g}/farms/{f}/derived/tables/*_weather_2021_2025.csv
  ├── growers/{g}/farms/{f}/derived/tables/*_ssurgo_summary.csv
  ├── growers/{g}/farms/{f}/derived/tables/*_cdl_*.csv
  ├── growers/{g}/farms/{f}/derived/tables/*_crop_rotation.csv
  └── growers/{g}/farms/{f}/fields/{field}/derived/tables/ndvi_year_crop_join.csv
       ↓
  data_loader.py (cached loading)
       ↓
  app.py (Streamlit rendering)
```

## Reusability

This dashboard is designed to work with any grower data added to the runtime. To add new growers:

1. Run the data pipeline to generate grower data
2. Add the grower config to `GROWER_CONFIGS` in `data_loader.py`
3. The dashboard automatically picks up the new data

## Local Validation

Run the data loader test:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline/dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" -c "
from data_loader import *
kpis = compute_kpis()
print(kpis)
"
```
