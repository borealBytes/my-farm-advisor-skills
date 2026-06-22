# Grower Web Map

Generates a self-contained HTML interactive map of farm field boundaries
using [Leaflet.js](https://leafletjs.com/). The map loads in any browser
and shows field polygons on an OpenStreetMap basemap with clickable popups
and a sidebar field list.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower \
  --farm-slug il-grower-illinois
```

To run for every farm under a grower:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower
```

## Output

A single HTML file at:

```
growers/<grower>/farms/<farm>/derived/dashboards/grower_web_map.html
```

The file is roughly 30–50 KB (boundary GeoJSON + light JS/CSS). No
imagery, rasters, or data tables are embedded.

## Requirements

- Runtime venv already installed (data-pipeline)
- At least one seeded farm with `field_boundaries.geojson`
- Internet access for the Leaflet and OSM tile CDNs at runtime
