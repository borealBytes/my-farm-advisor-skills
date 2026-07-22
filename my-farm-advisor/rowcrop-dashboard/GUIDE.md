# Row Crop Intelligence Dashboard — User Guide

## Prerequisites

- Python 3.10+ installed
- My Farm Advisor runtime pipeline populated with data
- Required Python packages installed

## Quick Start

### 1. Locate the Dashboard Script

The dashboard script lives in this repo at:
```
runtime/data-pipeline/src/scripts/dashboard/build_rowcrop_dashboard.py
```

You can run it from here directly, or copy the `runtime/` directory to your runtime data pipeline location.

### 2. Install Dependencies

```bash
cd /path/to/your-runtime-data-pipeline
source .venv/bin/activate  # or create a new venv
pip install streamlit plotly pandas geopandas numpy
```

### 3. Verify Data

Ensure your runtime pipeline has data for the target grower:

```bash
ls $DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/
```

Expected files:
- `*_ssurgo_summary.csv`
- `*_fields_soil.csv`
- `*_weather_<start>_<end>.csv`
- `*_cdl_<start>_<end>_full_composition.csv`
- `*_crop_rotation.csv`

And per-field NDVI summaries:
```bash
ls $DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/farms/<farm>/fields/*/derived/summaries/ndvi_card_summary.json
```

### 4. Set Environment Variables

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/your-runtime-root
export AG_WEATHER_START_YEAR=2021
export AG_WEATHER_END_YEAR=2025
```

`DATA_PIPELINE_DATA_ROOT` is the parent directory that contains `data-pipeline/growers/`, `data-pipeline/shared/`, etc.

### 5. Launch the Dashboard

```bash
streamlit run /path/to/build_rowcrop_dashboard.py
```

Or if you copied `runtime/` to your pipeline directory:

```bash
cd $DATA_PIPELINE_DATA_ROOT/data-pipeline
streamlit run src/scripts/dashboard/build_rowcrop_dashboard.py
```

Open your browser to `http://localhost:8501`.

## Customizing for a Different Grower

Edit these variables at the top of `build_rowcrop_dashboard.py`:

```python
DEFAULT_GROWER = "your-grower-slug"
DEFAULT_FARM = "your-farm-slug"
FIELD_NAMES = {
    "field-id-1": "Display Name 1",
    "field-id-2": "Display Name 2",
}
```

Or pass via environment variables (advanced — requires modifying the script to read them).

## Using the Dashboard

### Sidebar Controls
- **Fields**: Multi-select to filter which fields appear in all tabs
- **Year Range**: Slider to focus on specific years for weather data
- **Map Layer**: Dropdown to toggle between Soil Health, NDVI, Drainage, and OM layers

### Tabs

| Tab | What to look for |
|---|---|
| **Overview & Map** | Field boundaries colored by selected metric. Hover for values. |
| **Soil & Vegetation** | Box plots show distribution; bars compare NDVI across fields. |
| **Weather & Climate** | Monthly precip, temperature range, GDD accumulation, anomalies. |
| **Field Comparison** | Radar chart and NDVI overlay for 2+ selected fields. |
| **Recommendations** | Actionable per-field management tips and sustainability scores. |

## Deployment

### Local Server

```bash
streamlit run src/scripts/dashboard/build_rowcrop_dashboard.py --server.port=8501
```

### Docker Deployment

```bash
# From the runtime/ directory in this repo:
cd runtime/data-pipeline
docker compose up -d
```

Or copy the `Dockerfile` and `docker-compose.yml` to your runtime data pipeline:

```bash
cp runtime/data-pipeline/Dockerfile $DATA_PIPELINE_DATA_ROOT/data-pipeline/
cp runtime/data-pipeline/docker-compose.yml $DATA_PIPELINE_DATA_ROOT/data-pipeline/
cd $DATA_PIPELINE_DATA_ROOT/data-pipeline
docker compose up -d
```

This serves the dashboard on port 8501. Data is mounted as a volume so pipeline updates are reflected on restart.

### VPS Deployment (with nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

| Problem | Solution |
|---|---|
| Dashboard shows "No data" | Run `run_farm_pipeline.py` first to generate derived tables |
| Map is blank | Check field boundary GeoJSON exists and has valid geometry |
| NDVI bars missing | Verify ndvi_card_summary.json exists for each field |
| Streamlit not found | Activate venv: `source .venv/bin/activate` |
