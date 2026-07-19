# Row Crop Intelligence Dashboard

A Plotly Dash application that combines exploratory analysis, geospatial mapping, weather/climate insights, and soil health/sustainability metrics into a single interactive agricultural intelligence dashboard.

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd /path/to/my-farm-advisor-skills/my-farm-advisor/dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" row_crop_dashboard.py
```

Open http://127.0.0.1:8050 in your browser.

## What It Does

The dashboard integrates field boundary data, NRCS SSURGO soil surveys, NASA POWER weather observations, Sentinel-2 NDVI composites, and USDA CDL crop classification into a single analytical view.

### Sections

1. **KPI Summary** - Field count, total acreage, average NDVI, average rainfall, soil health score, sustainability index
2. **Exploratory Visualizations**
   - Soil pH distribution by field with optimal range overlay
   - NDVI comparison across fields colored by drainage class
   - Correlation matrix of soil properties and crop health metrics
3. **Geospatial Map** - Field boundaries colored by soil health score with interactive hover tooltips
4. **Weather/Climate Analysis** - Monthly precipitation trends and average temperature patterns with growing season highlight
5. **Soil Health & Sustainability** - Soil health score breakdown and sustainability index by field

## Requirements

- Python 3.8+
- Packages: plotly, dash, pandas, geopandas, numpy, rasterio
- `DATA_PIPELINE_DATA_ROOT` environment variable pointing to a My Farm Advisor runtime

## Usage

```bash
# Default (Iowa grower)
python src/row_crop_dashboard.py

# Custom grower/farm
python src/row_crop_dashboard.py --grower nebraska-grower --farm nebraska-farm

# Custom port
python src/row_crop_dashboard.py --port 8051

# Export to static HTML
python src/row_crop_dashboard.py --export /tmp/dashboard.html
```

## Data Sources

- **Field Boundaries**: OpenStreetMap via Overpass API
- **Soil Data**: USDA NRCS SSURGO (Soil Survey Geographic Database)
- **Weather Data**: NASA POWER (Prediction Of Worldwide Energy Resources)
- **NDVI Composites**: Sentinel-2 satellite imagery via Microsoft Planetary Computer
- **Crop Classification**: USDA NASS Cropland Data Layer (CDL)

## Output

The dashboard serves as a web application on `http://127.0.0.1:8050`. Optionally, it can export a static HTML file with `--export`.

## File Structure

```
dashboard/
  SKILL.md              - Skill routing entrypoint
  README.md             - This file
  AGENTS.md             - Agent instructions
  SUPPLEMENTARY.md      - Project overview and documentation
  src/
    row_crop_dashboard.py   - Main Dash application
    dashboard_utils.py      - Data loading and metric computation
```

## Analytics Story

**"Soil-Driven Row Crop Intelligence"**

The dashboard communicates how soil properties (organic matter, pH, drainage, CEC) interact with weather patterns (rainfall, temperature) to influence crop health (NDVI) and sustainability (rotation diversity, soil conservation) across 10 fields in Cerro Gordo County, Iowa.
