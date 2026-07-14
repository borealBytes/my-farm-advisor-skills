# Assignment: ndvi-weather-dashboard

## Skill / Workflow Name

ndvi-weather-dashboard

## Input Files Used from data-pipeline

| File | Path (relative to field root) |
|------|-------------------------------|
| CDL crop join | `derived/tables/ndvi_year_crop_join.csv` |
| Sentinel scene manifest | `satellite/sentinel/manifest.json` |
| Per-scene NDVI rasters | `satellite/sentinel/{year}/sentinel_{date}/*_ndvi.tif` |
| Field boundary | `boundary/field_boundary.geojson` |
| Daily weather | `weather/daily_weather.csv` |
| Field metadata | `field.json` |

## Weather Metrics Calculated

- **Precipitation**: daily total (PRECTOTCORR, mm), Mar–Nov mean, heavy rain detection (>= 25 mm)
- **Temperature**: daily max (T2M_MAX), min (T2M_MIN), mean (T2M) — in °C
- **Growing Degree Days (GDD)**: cumulative sum from DOY 60 (Mar 1), base 10°C, cap 30°C
- **Event detection**: heavy rain, hot days (>= 35°C), cool periods (3+ consecutive cold days)

## Dashboard Image Path (relative to data-pipeline root)

```
growers/<grower>/farms/<farm>/fields/<field>/derived/dashboards/ndvi_weather_dashboard_<year>.html
```

### Example

```
growers/il-grower/farms/il-grower-illinois/fields/osm-1499317763/derived/dashboards/ndvi_weather_dashboard_2023.html
```

## How to Rerun the Workflow

### CLI

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  my-farm-advisor-skills/my-farm-advisor/eda/ndvi-weather-dashboard/src/ndvi_weather_dashboard.py \
  <field_slug> \
  --year <year>
```

### Python API

```python
from ndvi_weather_dashboard import generate_dashboard

generate_dashboard("osm-1499317763", year=2023)
```

## Known Data Limitations

- **CDL coverage**: only years present in `ndvi_year_crop_join.csv` are available
- **Sentinel scenes**: scenes with cloud cover > 70% are excluded; sparse years (< 2 usable scenes) skip the NDVI panel
- **Weather gaps**: missing weather days > 10% in Mar–Nov trigger a warning; > 30% may produce a degraded dashboard
- **GDD parameters**: base/cap temperatures are fixed at corn defaults (10/30 °C); crop-specific stages adjust for corn vs. soybeans only
- **Cool period detection**: uses 10th percentile of T2M_MIN and sub-zero thresholds; may miss mild cool spells
- **Field boundary**: must be present in `boundary/field_boundary.geojson` for NDVI zonal statistics
