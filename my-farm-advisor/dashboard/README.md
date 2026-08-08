# My Farm Advisor Dashboard

Interactive multi-grower agricultural intelligence dashboard. Generates a single self-contained `.html` file integrating field boundaries, soil health, weather, NDVI, and sustainability metrics across all growers in the runtime dataset.

## What It Does

This skill generates a single, self-contained `grower_dashboard.html` file that integrates all field-level data from the My Farm Advisor data pipeline into an interactive decision-support dashboard. No web server is required — open the file in any browser.

### Dashboard Sections

1. **KPI Summary Cards** — Total fields, total acres, average NDVI, average growing-season rainfall, average Soil Health Score, and Sustainability Index.
2. **Interactive Geospatial Map** — Field boundaries colored by selectable variable (Soil Health Score, Sustainability Index, NDVI Stability, Weather Resilience, or Rotation Score). Click any field polygon to open a popup showing all 5 variables with 5-tier status labels, plus grower name, acreage, and predicted crop.
3. **Soil Particle Size Distribution** — Grouped bar chart showing clay/sand/silt percentages for each grower, with value labels.
4. **NDVI Performance Ranking** — Horizontal bar chart ranking all 30 fields by mean NDVI, color-coded by grower, with value labels.
5. **Weather & Climate Analysis** — Dual-axis chart of daily precipitation (7-day rolling average) and temperature by Day of Year for all 3 growers.
6. **Growing Degree Days** — Cumulative GDD curves for 2024 vs. multi-year average (2021–2025), with climate anomaly context.
7. **Sustainability Metrics by Grower** — Table showing each metric with its exact calculation formula, plus grower averages.
8. **Field Data Summary** — 30-row table with all per-field metrics.
9. **Key Highlights** — 5 analytical bullets covering patterns, health assessment, environmental variation, actionable insights, and key drivers.

### Custom Metrics

| Metric | Range | Description |
|--------|-------|-------------|
| **Soil Health Score (SHS)** | 0–100 | Composite of pH balance (25 pts), organic matter (25 pts), drainage class (20 pts), available water capacity (20 pts), and texture balance (10 pts) |
| **Sustainability Index (SI)** | 0–100 | Weighted composite: SHS (40%) + rotation diversity score (20%) + weather stress resilience (20%) + NDVI stability score (20%) |
| **NDVI Stability Score** | 0–20 | Based on coefficient of variation of mean NDVI across years; lower variability = higher score |
| **Weather Resilience** | 0–20 | Drought score + heat stress score; fewer stress days = higher resilience |
| **Rotation Score** | 0–20 | Shannon diversity index of crop types across 5 years of CDL data, scaled to 0–20 |

## Prerequisites

1. The My Farm Advisor data pipeline must be installed and populated:
   ```bash
   export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
   cd my-farm-advisor/data-pipeline
   ./scripts/install.sh
   ```
2. Install dependencies in the pipeline venv or system Python:
   ```bash
   pip install pandas numpy matplotlib plotly geopandas folium branca rasterio rasterstats
   ```

## Running the Dashboard

### Multi-Grower Dashboard (Default)

Generate the combined dashboard for all 3 growers (Iowa, Illinois, Nebraska):

```bash
cd my-farm-advisor/dashboard
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python3 src/grower_dashboard.py
```

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `--data-root` | Path to data-pipeline root | `/home/coder/my-farm-advisor-runtime/data-pipeline` |
| `--output-dir` | Directory to write the HTML output | `.../growers/all/derived/reports` |
| `--year` | Focus year for analysis | `2024` |

### Example: Generate with specific year

```bash
python3 src/grower_dashboard.py --year 2023
```

## Output Files

| File | Location | Description |
|------|----------|-------------|
| `grower_dashboard.html` | `growers/all/derived/reports/` | Interactive dashboard (map + static PNG charts) |

The dashboard is self-contained — all charts are embedded as base64 PNG or inline Folium/Leaflet JavaScript. No external server needed.

## Where to Find the Dashboard in Runtime

After generation, the dashboard HTML is written to:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/all/derived/reports/grower_dashboard.html
```

Example full path:
```
/home/coder/my-farm-advisor-runtime/data-pipeline/growers/all/derived/reports/grower_dashboard.html
```

## Interpretation Guide

The dashboard includes inline interpretive text to help users turn data into decisions:

- **Soil Health patterns:** Nebraska fields dominate soil health (avg 85.0) while Illinois trails (71.8), driven by texture differences (high sand = low SHS).
- **NDVI trends:** Illinois shows highest vegetation vigor (NDVI 0.381) despite lowest soil health, suggesting rainfall compensates for poorer soil.
- **Weather stress:** Illinois received the most rainfall (10,157mm) but Nebraska is driest (6,847mm); Nebraska's poor weather resilience (1.0) drags its SI below Iowa's despite higher SHS.
- **Actionable insights:** Lime and organic matter programs should target Illinois sandy fields (SHS < 65); irrigation may benefit Nebraska; Iowa's balanced profile supports precision fertilizer.

## Data Sources Integrated

| Data | Source | Files Used |
|------|--------|------------|
| Field Boundaries | OpenStreetMap / Farm pipeline | `boundary/field_boundaries.geojson` |
| Soil | NRCS SSURGO | `derived/tables/*_fields_soil.csv` |
| Weather | NASA POWER | `derived/tables/*_weather_YYYY_YYYY.csv` |
| Crops / Rotation | USDA NASS CDL | `derived/tables/*_crop_rotation.csv` |
| NDVI | Sentinel-2 composites | `fields/<field>/derived/features/ndvi_year_YYYY_composite.tif` |

## Dependencies

| Package | Purpose |
|---------|---------|
| `pandas` | Data loading, merging, aggregation |
| `numpy` | Numerical operations, score computation |
| `matplotlib` | Static chart rendering (soil texture, NDVI, weather, GDD) |
| `plotly` | (Available but not used in current version; kept for compatibility) |
| `geopandas` | GeoJSON boundary handling for Folium map |
| `folium` | Interactive Leaflet map with layer control |
| `branca` | Color ramps for Folium |
| `rasterio` | TIFF reading for NDVI extraction |
| `rasterstats` | Zonal statistics on NDVI composite TIFFs |

## File Structure

```
dashboard/
├── SKILL.md                  # Skill routing entrypoint
├── README.md                 # This file
├── AGENTS.md                 # Agent runtime instructions
├── INDEX.md                  # Subtree navigation
├── requirements.txt          # Python dependencies
├── AI_DOCUMENTATION.md       # AI usage log
├── DASHBOARD_INFO.md         # Supplementary: project overview, dataset, interpretation
└── src/
    ├── grower_dashboard.py     # Main orchestrator (v6: multi-grower, interactive Folium map)
    └── lib/
        ├── data_loader.py    # Load & merge all data sources
        ├── metrics.py        # Compute SHS, SI, weather resilience, NDVI stability, rotation score
        ├── ndvi_extractor.py # rasterstats zonal stats on composite TIFFs
        └── geospatial.py     # Geospatial helpers
```

## License

Apache-2.0 — See root repository LICENSE.
