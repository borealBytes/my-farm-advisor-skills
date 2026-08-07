# My Farm Advisor Dashboard

Interactive grower-level agricultural intelligence dashboard built with **Plotly**.

## What It Does

This skill generates a single, self-contained `.html` file that integrates all field-level data from the My Farm Advisor data pipeline into an interactive decision-support dashboard. No web server is required — open the file in any browser.

### Dashboard Sections

1. **KPI Summary Cards** — Total fields, total acres, average peak NDVI, average growing-season rainfall, average Soil Health Score, and Sustainability Index.
2. **Soil Variability Explorer** — Scatter plot of pH vs. Organic Matter, sized by field area, colored by drainage class.
3. **Field Performance Ranking** — Horizontal bar chart ranking fields by mean peak NDVI (computed from composite TIFFs via `rasterstats`).
4. **Interactive Geospatial Map** — Field boundaries colored by Soil Health Score with click popups showing acres, crop, pH, OM, drainage, and NDVI.
5. **Weather & Climate Analysis** — Dual-axis chart of monthly precipitation and temperature, plus Growing Degree Day (GDD) accumulation curves.
6. **Soil Health & Sustainability** — Gauge charts, distribution histograms, Conservation Priority ranking, and metric explanations.

### Custom Metrics

| Metric | Range | Description |
|--------|-------|-------------|
| **Soil Health Score (SHS)** | 0–100 | Composite of pH balance, organic matter, drainage quality, water holding capacity, and texture balance |
| **Sustainability Index (SI)** | 0–100 | Weighted composite: SHS (40%) + rotation diversity (20%) + weather stress resilience (20%) + NDVI stability (20%) |
| **Conservation Priority** | 0–100 | Inverse of SI; fields > 60 flagged for conservation review |

## Prerequisites

1. The My Farm Advisor data pipeline must be installed and populated:
   ```bash
   export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
   cd my-farm-advisor/data-pipeline
   ./scripts/install.sh
   ```
2. Plotly and Kaleido must be installed in the pipeline venv:
   ```bash
   "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/pip" install plotly kaleido
   ```

## Running the Dashboard

### Basic Usage

Generate the dashboard for a specific grower:

```bash
cd my-farm-advisor/dashboard
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" src/grower_dashboard.py --grower-slug ia-grower
```

### Command-Line Options

| Flag | Description | Default |
|------|-------------|---------|
| `--grower-slug` | Grower identifier (required) | — |
| `--farm-slug` | Farm identifier (auto-discovered if omitted) | first farm under grower |
| `--output-dir` | Directory to write the HTML output | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports` |
| `--year-focus` | Focus year for NDVI and weather analysis | most recent year with data |
| `--png-fallback` | Also export a static PNG using Kaleido | False |
| `--verbose` | Print detailed progress | False |

### Example: Generate with PNG fallback

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" src/grower_dashboard.py \
  --grower-slug ia-grower \
  --year-focus 2024 \
  --png-fallback \
  --verbose
```

## Output Files

| File | Location | Description |
|------|----------|-------------|
| `grower_dashboard.html` | `growers/<grower>/derived/reports/` | Interactive Plotly dashboard |
| `grower_dashboard.png` | `growers/<grower>/derived/reports/` | Static PNG fallback (if `--png-fallback`) |

## Interpretation Guide

The dashboard includes inline interpretive text to help users turn data into decisions:

- **Soil Health patterns:** "Fields with higher organic matter and well-drained soils show consistently higher NDVI values."
- **NDVI trends:** "Declining NDVI across multiple years may signal compaction, nutrient depletion, or drainage issues."
- **Weather stress:** "Fields experiencing > 15 drought-stress days during the growing season show reduced peak NDVI by an average of 0.08."
- **Conservation priority:** "Fields flagged as Conservation Priority should be prioritized for cover-crop trials, reduced tillage, or tile-drainage evaluation."

## Data Sources Integrated

| Data | Source | Files Used |
|------|--------|------------|
| Field Boundaries | OpenStreetMap / Farm pipeline | `boundary/field_boundaries.geojson` |
| Soil | NRCS SSURGO | `derived/tables/*_fields_soil.csv`, `soil/ssurgo_summary.csv` |
| Weather | NASA POWER | `derived/tables/*_weather_YYYY_YYYY.csv` |
| Crops | USDA NASS CDL | `derived/tables/*_YYYY_cdl.csv`, `*_crop_rotation.csv` |
| NDVI | Sentinel-2 / Landsat composites | `derived/features/ndvi_year_YYYY_composite.tif` |

## AI Assistance Documentation

See [`AI_DOCUMENTATION.md`](AI_DOCUMENTATION.md) for a transparent record of how AI tools assisted in the design, coding, and debugging of this dashboard.

## File Structure

```
dashboard/
├── SKILL.md                  # Skill routing entrypoint
├── README.md                 # This file
├── AGENTS.md                 # Agent runtime instructions
├── INDEX.md                  # Subtree navigation
├── requirements.txt          # plotly, kaleido
├── AI_DOCUMENTATION.md       # AI usage log
└── src/
    ├── grower_dashboard.py     # Main orchestrator
    └── lib/
        ├── data_loader.py    # Load & merge all data sources
        ├── metrics.py        # Compute SHS, SI, conservation priority
        ├── ndvi_extractor.py # rasterstats zonal stats on composite TIFFs
        └── geospatial.py     # Build Plotly choropleth map
```

## License

Apache-2.0 — See root repository LICENSE.
