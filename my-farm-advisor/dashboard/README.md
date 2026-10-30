# Row Crop Intelligence Dashboard

A Plotly Dash application that aligns Sentinel-2 NDVI, NASA POWER daily weather,
and cumulative GDD for **Field osm-1219926116 (Field 1) — 2023 Corn** across a
shared seasonal timeline, with additional exploratory panels for all 10 fields.

## Selected Field-Year

| Attribute | Value |
|-----------|-------|
| Field ID | `osm-1219926116` (Field 1) |
| Year | **2023** |
| CDL Crop | **Corn** (95% of field area; remainder Grass/Pasture 3%, Soybeans 1%) |
| NDVI scenes | 9 (Mar 27 – Nov 12) |
| Weather coverage | 365/365 days |
| Total GDD | 1,860 °C·d |
| Seasonal precip | 634 mm (314 mm May–Sep) |
| Key event | Heat wave: 25 days >32°C, peak 41.3°C on Aug 23 |

## Key Events Detected (2023)

1. **Last spring frost** — Apr 26 (Tmin −1.3°C), visible in the Temperature panel
2. **Planting** — May 1 (DOY 121), marked with green dashed line
3. **Rapid green-up** — NDVI rose 0.311 between May 4 and Jun 20 during vegetative growth
4. **Peak NDVI** — 0.602 on Jul 10, canopy at full closure
5. **Heat wave** — 41.3°C on Aug 23; 25 days exceeded 32°C, annotated in Temperature panel
6. **Heaviest rain** — 35.5 mm on Sep 22, annotated in Precipitation panel
7. **Final GDD** — 1,860 °C·d, within typical range for Corn RM 94

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

Open http://127.0.0.1:8050. This uses the pre-computed `dashboard_data.json` (6.2 MB, included in the repo) and requires no runtime tree, no heavy dependencies (geopandas/rasterio not needed).

### Option B: Runtime tree mode (when you have the full data pipeline)

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd src
python row_crop_dashboard.py --grower iowa-grower --farm iowa-farm
```

This reads from the canonical runtime tree at `$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/{grower}/farms/{farm}/` (SSURGO CSV, weather, NDVI TIFFs, CDL tables, etc.).

## What It Does

The dashboard's primary deliverable is the **focused year timeline** — a four-panel
figure with a shared date axis showing NDVI, precipitation, temperature, and cumulative
GDD for the selected field-year. A reader can scan vertically across the same dates
to compare vegetation changes, rainfall, temperature events, and accumulated growing
degree days. Additional panels explore all 10 fields across 5 seasons.

### Primary Panel

**Focused Year Timeline (Field 1, 2023 Corn)**
- 4 panels: NDVI → Daily Precipitation → Temperature → Cumulative GDD
- Shared date axis with cross-panel hover
- 6 event annotations embedded in the plot
- Strategy guide card with CDL crop confirmation and season summary

### Additional Sections

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

The dashboard serves as a web application on `http://127.0.0.1:8050`. The primary
output is the **focused year timeline** — a four-panel Plotly figure with a shared
date axis for the selected field-year (Field 1, 2023 Corn). Optionally, it can export
a static HTML file with `--export`.

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
    row_crop_dashboard.py   - Main Dash application (aligned timeline, focused year panel, all charts)
    dashboard_utils.py      - Data loading and metric computation (DashboardData class)
    export_data_package.py  - Script to regenerate dashboard_data.json from runtime tree
```

## Analytics Story

**"2023 Corn Season: From Planting to 1,860 GDD"**

The focused year timeline tracks Field 1 through the 2023 growing season. NDVI rose
from 0.110 (May 4) to a peak of 0.602 (Jul 10), driven by adequate June rainfall
and warm temperatures. A heat wave in late July–August brought 25 days above
32°C (peak 41.3°C on Aug 23) but did not suppress NDVI, which held above 0.5
through late August. Seasonal precipitation totaled 634 mm, with 314 mm falling
during the May–September growing window. The season accumulated 1,860 °C·d GDD,
consistent with the Corn RM 94 maturity target for Cerro Gordo County, IA.
