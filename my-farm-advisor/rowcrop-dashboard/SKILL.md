# Row Crop Intelligence Dashboard

Build interactive Streamlit dashboards for precision agriculture analysis — soil health, NDVI, weather, sustainability, and field comparisons — from the My Farm Advisor data pipeline.

## When to Use

Use this skill when the user wants to:
- Create an interactive dashboard for a grower's farm
- Visualize soil health metrics across fields
- Compare NDVI, weather, and crop rotation data between fields
- Generate per-field management recommendations
- Deploy a dashboard to a server or VPS

## Start Here

1. Read `GUIDE.md` for step-by-step dashboard creation instructions
2. Read `AGENTS.md` for agent routing details
3. The dashboard script lives at: `runtime/data-pipeline/src/scripts/dashboard/build_rowcrop_dashboard.py`
4. Data is read from your runtime pipeline under `$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/farms/<farm>/derived/`

## Requirements

- Python 3.10+
- streamlit, plotly, pandas, geopandas, numpy
- A populated My Farm Advisor runtime data pipeline for the target grower
