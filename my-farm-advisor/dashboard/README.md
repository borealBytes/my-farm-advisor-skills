# Row Crop Intelligence Dashboard

A Plotly Dash application that combines exploratory analysis, geospatial mapping, weather/climate insights, and soil health/sustainability metrics into a single interactive agricultural intelligence dashboard.

## Getting Started

### From a fresh clone (local machine)

```bash
git clone https://github.com/nbmorr/my-farm-advisor-skills.git
cd my-farm-advisor-skills
git checkout final-assignment
cd my-farm-advisor/dashboard
pip install -r requirements.txt
python src/row_crop_dashboard.py --json dashboard_data.json
```

Open http://127.0.0.1:8050. No runtime tree or heavy dependencies needed.

### From an existing repo clone

```bash
cd my-farm-advisor/dashboard
pip install -r requirements.txt
python src/row_crop_dashboard.py --json dashboard_data.json
```

Open http://127.0.0.1:8050.

## Two Ways to Run

### Option A: JSON data package (no runtime tree needed, recommended for local machines)

```bash
cd src
pip install -r ../requirements.txt
python row_crop_dashboard.py --json ../dashboard_data.json
```

Open http://127.0.0.1:8050. This uses the pre-computed `dashboard_data.json` (56 KB, included in the repo) and requires no runtime tree, no heavy dependencies (geopandas/rasterio not needed).

### Option B: Runtime tree mode (when you have the full data pipeline)

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd src
python row_crop_dashboard.py --grower iowa-grower --farm iowa-farm
```

This reads from the canonical runtime tree (SSURGO CSV, weather, NDVI TIFFs, etc.).

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
- **Core packages**: plotly, dash, pandas, numpy (install via `pip install -r requirements.txt`)
- **Runtime tree mode only**: geopandas, rasterio

## Usage

```bash
# JSON mode (simplest - no runtime tree needed)
python src/row_crop_dashboard.py --json dashboard_data.json

# Runtime tree mode
python src/row_crop_dashboard.py --grower iowa-grower --farm iowa-farm

# Custom port
python src/row_crop_dashboard.py --json dashboard_data.json --port 8051

# Bind to all interfaces (for Dokploy/Cloudflare)
python src/row_crop_dashboard.py --json dashboard_data.json --host 0.0.0.0 --port 8050

# Export to static HTML
python src/row_crop_dashboard.py --json dashboard_data.json --export /tmp/dashboard.html
```

## Re-generating the Data Package

Run `export_data_package.py` on a machine with the runtime tree to refresh `dashboard_data.json`:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
python src/export_data_package.py --grower iowa-grower --farm iowa-farm
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
  requirements.txt      - Python dependencies
  dashboard_data.json   - Pre-computed data package (56 KB)
  src/
    row_crop_dashboard.py   - Main Dash application
    dashboard_utils.py      - Data loading and metric computation
    export_data_package.py  - Script to regenerate dashboard_data.json
```

## Analytics Story

**"Soil-Driven Row Crop Intelligence"**

The dashboard communicates how soil properties (organic matter, pH, drainage, CEC) interact with weather patterns (rainfall, temperature) to influence crop health (NDVI) and sustainability (rotation diversity, soil conservation) across 10 fields in Cerro Gordo County, Iowa.
