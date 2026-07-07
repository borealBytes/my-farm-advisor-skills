# Assignment 3: Field-Year Dashboard

## Selected Field-Year
- **Field:** `osm-1263365647`
- **Year:** `2023`
- **CDL Crop:** **Corn** (99.35% field purity, 154 of 155 pixels)
- **Location:** `il-grower-illinois` (Adams County, IL)

## Workflow

**Script:** `scripts/build_field_year_dashboard.py`

### Inputs Used
- `growers/il-grower/farms/il-grower-illinois/fields/osm-1263365647/weather/daily_weather.csv` — 365 daily records (2023)
- `growers/il-grower/farms/il-grower-illinois/fields/osm-1263365647/satellite/sentinel/2023/*/sentinel_*_ndvi.tif` — 9 Sentinel-2 scenes
- `growers/il-grower/farms/il-grower-illinois/derived/tables/il_grower_illinois_cdl_2021_2025_full_composition.csv` — CDL crop classification

### Weather Metrics Calculated
- Daily GDD: `max(0, min((T2M_MAX + T2M_MIN)/2, 30) - 10)`
- Cumulative GDD: running sum from DOY 1
- Event detection: heavy rain (≥25 mm), hot days (≥35°C), cool periods (3-day mean <10°C)

### Output
- `field_year_dashboard_2023_annotated.png` — Annotated dashboard with concise captions and summary box
- See `examples/field_year_dashboard_2023_annotated.png` for a committed reference output

### Rerun
```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python \
  scripts/eda/build_field_year_dashboard.py \
  --grower il-grower --farm il-grower-illinois \
  --field osm-1263365647 --year 2023 --sensor sentinel --annotated
```

### Known Data Limitations
- NDVI `crop_name` in `ndvi_year_crop_join.csv` shows "Unknown" because the table was not joined to CDL at generation time; authoritative crop is read from the standalone CDL composition table.
- `ndvi_card_summary.json` shows `"status": "unavailable"` for crop-specific cards because it relies on the same unjoined crop labels; underlying scene files and composites are physically present.
- No per-scene tabular NDVI summary exists; values are computed on-the-fly from `.tif` rasters.

## Dashboard Panels
1. **P1 — NDVI Time-Series** — Sentinel-2 mean field NDVI per acquisition date
2. **P2 — Daily Precipitation** — Daily totals with heavy-rain annotations (≥ 25 mm)
3. **P3 — Temperature Range** — Min/max envelope and mean temperature with hot-day and cool-period annotations
4. **P4 — Cumulative Growing Degree Days** — Base 10°C, cap 30°C, with planting-window annotation

## Event Annotations (Auto-Detected)
| Event | Rule | Count |
|-------|------|-------|
| Heavy rain | `PRECTOTCORR >= 25 mm` | 2 |
| Hot day | `T2M_MAX >= 35°C` | 5 |
| Cool period | 3-day mean `T2M < 10°C` (DOY 120–270) | 3 |
| NDVI dip | Consecutive scene delta `< -0.10` | 2 |
| NDVI surge | Consecutive scene delta `> +0.15` | 2 |
| Planting window | First sustained GDD accumulation `> 50` after DOY 90 | 1 |
| Peak NDVI | Maximum NDVI value in season | 1 |
