# Row Crop Intelligence Dashboard

**Final Project — Row Crop Intelligence Data Dashboard**

A Streamlit-based interactive dashboard for analyzing 30 row-crop fields across three Corn Belt states (Illinois, Iowa, Nebraska) using data from Assignments 1–3 of the My Farm Advisor data pipeline.

## Dashboard Sections

### KPI Section
- **Total Fields:** 30 fields across 3 growers
- **Total Acreage:** Sum of all field areas from boundary GeoJSON
- **Avg NDVI Scenes:** Mean Sentinel-2 scene count per field per year
- **Avg Daily Rainfall:** Mean daily precipitation from NASA POWER weather
- **Soil Sustainability Score:** Composite score (0–100) from SSURGO soil properties

### Exploratory Visualizations
1. **Field Sizes & Crop Composition:** Box plot of field acreage distribution and bar chart of CDL crop prevalence by state
2. **Crop Rotation Patterns:** Crop diversity metrics and most common rotation sequences

### Interactive Geospatial Map
- Folium-based map with all 30 field boundaries
- Color-coded by state (blue=IL, green=IA, red=NE)
- Clickable polygons with field metadata popups
- Satellite imagery overlay option

### Weather & Climate Analysis
- Monthly precipitation trends by year and state
- Annual temperature extremes (max/min)
- Cumulative Growing Degree Days (GDD) for the 2025 season

### Soil Health & Sustainability
- Radar chart of soil properties by state (organic matter, pH, CEC, water storage, clay %)
- Sustainability score distribution box plot
- Field-level soil summary table

## Data Sources

| Data | Source | Assignment |
|------|--------|------------|
| Field boundaries | OSM/Overpass via data pipeline | Assignment 1 |
| Weather (temperature, precipitation) | NASA POWER S3 Zarr stores | Assignment 1 |
| Soil properties | SSURGO (USDA NRCS) | Assignment 1 |
| Crop classification | USDA Cropland Data Layer (CDL) | Assignment 2 |
| NDVI imagery | Sentinel-2 via data pipeline | Assignment 3 |
| Crop rotation | Derived from CDL time series | Assignment 2 |

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline/dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  -m streamlit run app.py --server.port 8501
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit application |
| `data_loader.py` | Data loading and KPI computation module |
| `requirements.txt` | Python dependencies |
| `SKILL.md` | Reusable skill definition |
| `AI_USAGE.md` | AI usage documentation |

## Architecture

The dashboard reads runtime data directly from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/` — no data duplication. All data loading is cached with `@st.cache_data` for performance. The app uses Plotly for interactive charts and Folium for the geospatial map.

## Dependencies

- Streamlit >= 1.30.0
- Pandas >= 2.0.0
- NumPy >= 1.24.0
- Plotly >= 5.18.0
- Folium >= 0.15.0
- GeoPandas >= 0.14.0
- streamlit-folium >= 0.18.0
