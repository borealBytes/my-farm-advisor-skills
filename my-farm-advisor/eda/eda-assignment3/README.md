# eda-assignment3 — Field-Season Weather & NDVI Storylines

Generates multi-panel storyline dashboards for individual fields, combining Sentinel-2 NDVI scene values, daily weather (temperature, precipitation, GDD), and crop type data over the 2021–2025 record.

## Assignment: Field-Season Weather & NDVI Storylines

### Workflow name

**eda-assignment3** — CLI entrypoint: `scripts/run_storylines.py`

### Input files (from data-pipeline)

| File | Location (relative to `growers/<g>/farms/<f>/`) | Role |
|---|---|---|
| Field boundary | `fields/<field>/boundary/field_boundary.geojson` | NDVI masking + field polygon |
| Sentinel NDVI scenes | `fields/<field>/satellite/sentinel/<year>/sentinel_*/sentinel_*_ndvi.tif` | Per-scene mean NDVI values |
| Daily weather | `derived/tables/<prefix>_weather_2021_2025.csv` | T2M, T2M_MAX, T2M_MIN (°C), PRECTOTCORR (mm) |
| Crop rotation | `derived/tables/<prefix>_crop_rotation.csv` | Per-year crop label (CDL) |

### Weather metrics calculated

- **Daily precipitation** — PRECTOTCORR converted from mm to inches
- **Temperature range** — T2M_MAX / T2M_MIN converted from °C to °F, fill-between shading
- **Cumulative GDD** — daily GDD = max(0, (Tmax_F + Tmin_F) / 2 − 50°F), cumulated per year

### Dashboard panels (4×1 vertical stack)

| Panel | Title | Data |
|---|---|---|
| 1 | Mean NDVI — YYYY | Line + markers, per-scene means, crop annotations, event callouts |
| 2 | Precip. (in) | Daily bars + cumulative step line, heavy-rain callouts |
| 3 | Temp. (°F) | T2M_MAX/T2M_MIN fill range, 95°F threshold, hot-day markers |
| 4 | Cumulative GDD (°F-days) | Accumulated GDD line with NDVI scene markers |

All panels share a Mar–Nov x-axis with month tick labels and a common "Shared Growing Season Timeline" label at the base.

### Output

```
fields/<field>/derived/storylines/<year>_field_season_storyline.png
```

Generated once per year (2021–2025) by default. File size: 300–360 KB.

### How to rerun

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_storylines.py \
  --grower-slug ia-grower \
  --farm-slug ia-grower-iowa \
  --field-id osm-1360330515
```

All 5 years generate by default. Use `--years 2023` or `--years 2021,2024` for a subset.

### Known data limitations

- **NDVI scene gaps:** Sentinel-2 revisit depends on cloud cover. Max gap between consecutive scenes is 55–75 days in some years (pre-plant to canopy closure).
- **Weather source:** NASA POWER provides grid-cell estimates (~0.5° resolution), not on-site station data. Local convective precipitation events may be smoothed.
- **Coverage window:** All data covers 2021–2025. Scene counts vary by year (7–9 scenes). One or more growing-season months (Apr–Oct) may have no scenes in years with persistent cloud cover.

## Requirements

Python packages already in the pipeline venv: `rasterio`, `pandas`, `numpy`, `matplotlib`, `geopandas`.
