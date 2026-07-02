# Grower Web Map

## Description

Generate lightweight, self-contained interactive HTML web maps for each grower in the My Farm Advisor data pipeline. The map aggregates field polygon boundaries across all farms belonging to a grower and presents them in a single HTML file that can be opened directly in any modern web browser.

**Key Features:**

- **Self-contained**: Single HTML file with embedded GeoJSON data
- **Interactive**: Click any field polygon to view metadata popup
- **Field list sidebar**: Click a field name to zoom to it and open its popup
- **Farm coloring**: Fields are colored by farm to visually distinguish ownership
- **Lightweight**: No embedded imagery or rasters; basemap loads from the internet
- **Responsive**: Works on desktop and tablet

## When to Use This Workflow

- **Sharing grower portfolios**: Send a complete interactive map showing all grower fields
- **Field verification**: Quickly visualize downloaded field boundaries
- **Reporting**: Include interactive maps in grower-level reports
- **Assignment 1**: This is the canonical Assignment 1 grower web-map deliverable

## Output Example

A single `{grower_slug}_web_map.html` file (typically 50-200 KB for 3-12 fields) that:

- Opens in any modern web browser
- Requires no installation or server
- Can be emailed as an attachment
- Loads OpenStreetMap basemap tiles from the internet

## Prerequisites

The script runs from the data-pipeline runtime virtualenv, which already includes `geopandas`:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
```

To view maps: **Any modern web browser** (Chrome, Firefox, Safari, Edge)

## Quick Start: Generate Maps for All Growers

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py
```

## Generate for a Specific Grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower
```

## Generate for a Specific Farm

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower \
  --farm-slug il-grower-illinois
```

## Output Location

Maps are written to:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/<grower>_web_map.html
```

Examples:
- `growers/il-grower/derived/reports/il-grower_web_map.html`
- `growers/ia-grower/derived/reports/ia-grower_web_map.html`

## Map Controls

| Control | Action |
|---------|--------|
| Mouse wheel / pinch | Zoom in/out |
| Click and drag | Pan the map |
| Click field polygon | Open popup with grower, farm, field, crop, area, and location |
| Click field in sidebar | Zoom to field and open popup |

## Customization

### Change Basemap

Edit the tile layer URL in `generate_grower_web_map.py`:

```javascript
// OpenStreetMap (default)
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', ...)

// Esri World Imagery (satellite)
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', ...)

// CartoDB Positron (light)
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', ...)
```

### Adjust Geometry Simplification

Use `--simplify-tolerance` to trade fidelity for file size (units are degrees):

```bash
python scripts/reporting/generate_grower_web_map.py --simplify-tolerance 0.00005
```

Lower values preserve more detail but increase file size.

## Performance Notes

- The script uses Leaflet's Canvas renderer for smooth handling of many polygons
- GeoJSON geometries are simplified before embedding to keep HTML small
- For 200+ fields, consider increasing simplification tolerance or filtering by farm

## Resources

- [Leaflet Documentation](https://leafletjs.com/)
- [OpenStreetMap](https://www.openstreetmap.org/)
