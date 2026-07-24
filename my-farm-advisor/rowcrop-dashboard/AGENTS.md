# Agent Instructions — Row Crop Intelligence Dashboard

## Purpose

This folder owns the Row Crop Intelligence Dashboard — a Streamlit-based interactive dashboard for analyzing soil, vegetation, weather, and sustainability data across a grower's fields.

## Safe Edit Scope

Edits should stay within `rowcrop-dashboard/` unless the user explicitly asks for changes to the dashboard skill or its runtime script in the data pipeline.

## Key Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill routing entrypoint |
| `GUIDE.md` | Step-by-step dashboard creation guide |
| `runtime/data-pipeline/src/scripts/dashboard/build_rowcrop_dashboard.py` | Main Streamlit app script |
| `runtime/data-pipeline/src/scripts/dashboard/assets/style.css` | Custom CSS theme |
| `runtime/data-pipeline/DASHBOARD_INFO.md` | Supplementary project documentation |
| `runtime/data-pipeline/Dockerfile` | Containerized deployment |
| `runtime/data-pipeline/docker-compose.yml` | One-command VPS deploy |

## Data Sources

The dashboard reads from these runtime pipeline paths:

- `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
- `growers/<grower>/farms/<farm>/derived/tables/` — SSURGO, weather, CDL, rotation CSVs
- `growers/<grower>/farms/<farm>/fields/<field>/derived/summaries/ndvi_card_summary.json`
- `growers/<grower>/farms/<farm>/manifests/field-inventory.csv`

## Data Dependencies

The pipeline must have been run at least once to produce the derived tables and NDVI summaries. Run `run_farm_pipeline.py` first if data is missing.

## Local Workflow Notes

- The dashboard is reusable at grower level — change `DEFAULT_GROWER` and `DEFAULT_FARM` in the script, or set via env vars
- Streamlit caches data with `@st.cache_data` — clear cache via Streamlit menu when data refreshes
- For deployment, use the Dockerfile or run: `streamlit run runtime/data-pipeline/src/scripts/dashboard/build_rowcrop_dashboard.py`
