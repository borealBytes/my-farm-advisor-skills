# Sustainability Intelligence Dashboard

## Skill Purpose

Builds a standalone HTML sustainability intelligence dashboard that combines soil health metrics, NDVI-derived productivity signals, and weather context into a single interactive visualization. Designed for grower-level analysis across all fields in a farm.

## When to Use

- When you need a portfolio-ready farm sustainability dashboard
- When integrating SSURGO soil data with Sentinel-2 NDVI composites
- When demonstrating soil health links to productivity and yield stability
- For assignment submissions requiring interactive Plotly/Folium dashboards

## How to Run

```bash
cd my-farm-advisor/dashboard/sustainability-intelligence-dashboard
pip install -r requirements.txt
export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
export AG_GROWER_SLUG=iowa-grower
export AG_FARM_SLUG=iowa-grower-iowa
export AG_FARM_NAME="Iowa Farm"
export PYTHONPATH=src
python -m dashboard_builder.app
```

Output is written to:
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/dashboards/sustainability_dashboard.html`

Open the generated HTML in any modern browser. The dashboard uses Plotly and Bootstrap CDNs, so an internet connection is required on first load.

## What You Get

- Folium hero map with field boundaries colored by Soil Health Index
- Field-level drainage class layer (toggleable)
- Esri satellite base map (toggleable)
- Plotly interactive chart carousel: SHI vs NDVI-CV scatter, SHI component heatmap, soil property boxplot, weather anomalies, NDVI time-series
- Year explorer with field-level NDVI and weather anomalies
- KPI summary cards
- Executive summary with natural-language interpretation

## Key Files

- `src/dashboard_builder/app.py` — Main dashboard generator
- `README.md` — Full setup and usage instructions
- `METHODLOGY.md` — SHI formula and data provenance
- `DASHBOARD_INFO.md` — Project overview and analytical interpretation
- `AI_USAGE.md` — Documentation of AI-assisted workflow
- `PROVENANCE.md` — Source and authorship record
