# Grower Web Map

Generates lightweight, self-contained interactive HTML maps from field-boundary
data in the My Farm Advisor data pipeline runtime.

One HTML file is produced for each grower, covering all farms and fields.
The map embeds only polygon geometry and a small set of metadata properties
(grower, farm, field ID, county, area). Leaflet.js and basemap tiles load
from CDN at view time, keeping the generated HTML file small.

## Features

- Standalone HTML — open in any browser, no server required
- OpenStreetMap basemap with ESRI Satellite toggle
- Auto-fit to field extents
- Click any field for metadata popup
- Sidebar with field list and click-to-zoom
- Grower-level output (all farms included)
- No heavy rasters or imagery embedded

## Output location

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<slug>/farms/<farm>/derived/dashboards/grower_web_map.html
```

## Dependencies

- Python packages already in the data-pipeline venv: `geopandas`
- Browser: Leaflet 1.9.4 loaded from CDN at view time

## See also

- [SKILL.md](SKILL.md) — subskill router
- [GUIDE.md](GUIDE.md) — usage guide
- [AGENTS.md](AGENTS.md) — agent instructions
- [PROVENANCE.md](PROVENANCE.md) — source provenance
