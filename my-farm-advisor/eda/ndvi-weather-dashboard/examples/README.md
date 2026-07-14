# ndvi-weather-dashboard Examples

## Example: osm-1499317763, 2023 Corn Season

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  /home/coder/my-farm-advisor-skills/my-farm-advisor/eda/ndvi-weather-dashboard/src/ndvi_weather_dashboard.py \
  osm-1499317763 \
  --year 2023 \
  --grower il-grower \
  --farm il-grower-illinois
```

Output: `<field>/derived/dashboards/ndvi_weather_dashboard_2023.html`

### Expected inputs for osm-1499317763

| Asset | Status |
|-------|--------|
| CDL crop join (2023 = Corn) | Available |
| Sentinel scenes (8 scenes, 2023) | Available |
| Field boundary (260 ac, Iroquois County, IL) | Available |
| Daily weather (2023 full year) | Available |

## Example: Custom Output Directory

```python
from ndvi_weather_dashboard import generate_dashboard

generate_dashboard(
    field_slug="osm-1499317763",
    year=2023,
    output_dir="/home/coder/output",
)
```

## Example: Other Field or Year

```python
generate_dashboard(
    field_slug="osm-1499317763",
    year=2022,
    grower_slug="il-grower",
    farm_slug="il-grower-illinois",
)
```
