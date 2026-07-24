# Row Crop Intelligence Dashboard — Runtime

This directory contains the dashboard scripts and sample data for the Row Crop Intelligence Dashboard.

## Quick Start (Demo Mode)

```bash
# From the repo root:
streamlit run streamlit_app.py
```

## Quick Start (Full Pipeline)

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/your-runtime-root
streamlit run runtime/data-pipeline/src/scripts/dashboard/build_rowcrop_dashboard.py
```

## Structure

| Path | Description |
|---|---|
| `src/scripts/dashboard/build_rowcrop_dashboard.py` | Main Streamlit dashboard app |
| `src/scripts/dashboard/assets/style.css` | Custom theme |
| `sample_data/` | Bundled sample data for demo mode |
| `DASHBOARD_INFO.md` | Full project documentation |
| `Dockerfile` | Containerized deployment |
| `docker-compose.yml` | Docker Compose deployment |
| `src/scripts/lib/` | Path utilities for full mode |

## Streamlit Cloud

Deploy at https://share.streamlit.io — select `streamlit_app.py` as the entry point.
