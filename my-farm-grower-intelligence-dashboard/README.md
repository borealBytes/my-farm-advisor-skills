# Grower Field Intelligence & Sustainability Dashboard

A reusable skill in `my-farm-advisor-skills` that generates an interactive
HTML dashboard summarizing crop rotation, vegetation health, soil health,
and weather stress across all fields for a given grower.

## What it does

The dashboard operates at the **grower level** — pass in a grower and it
analyzes every field under that grower's operation, producing a single
self-contained HTML report with 5 sections:

1. **Crop Rotation Stability Matrix** — year-by-year crop history per field
   (2021–2025), with a legend for all crop categories present.
2. **Peak-Season NDVI by Crop Type** — vegetation health distribution from
   Sentinel-2 imagery, grouped by dominant crop.
3. **Field Map — Crop & Soil Overlay** — an interactive choropleth map of
   field boundaries colored by 2025 crop, with soil attributes available
   on hover.
4. **Growing-Season Weather Stress** — 2025 precipitation and hot-day
   counts per field vs. their 5-year averages.
5. **Soil Health Scorecard** — a composite Soil Health Index (0–1 scale)
   per field, ranked against the grower-wide average.

A **Raw Data Summary** table at the bottom of the report shows every
underlying metric per field for verification.

## Running the dashboard

From the repo root, with the runtime venv active:

```bash
python my-farm-grower-intelligence-dashboard/scripts/generate_grower_dashboard.py \
  --grower northern-il-grower \
  --farm northern-il-farm \
  --season 2025
```

### Filtering to a specific set of fields

Some grower datasets include demo/sample fields that aren't part of the
real operation (see `PROVENANCE.md` for why). Use `--fields` to scope the
dashboard to only the fields you want:

```bash
python my-farm-grower-intelligence-dashboard/scripts/generate_grower_dashboard.py \
  --grower northern-il-grower \
  --farm northern-il-farm \
  --season 2025 \
  --fields osm-1333296922,osm-660987142,osm-984791369
```

This filter is applied before any downstream processing (soil, weather,
NDVI, chart generation) — it does not modify any upstream pipeline data.

## Output location

Per the data-pipeline runtime contract, outputs are written under:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/dashboards/
  grower_intelligence_dashboard.html   # the dashboard itself
  manifest.json                        # generation metadata
```

NDVI zonal-stats results are cached per farm/season to avoid recomputation
on subsequent runs:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/
  ndvi_field_summary_<year>.csv
```

## Dependencies

Requires the runtime venv already used across this repo's other skills:

```
pandas
geopandas
rasterio
rasterstats
plotly
numpy
```

If `plotly` is missing from the runtime venv:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/pip" install plotly
```

## Data sources used

- Field boundaries (per-grower `field_boundaries.geojson`)
- SSURGO soil summaries (`ssurgo_summary.csv` / `*_fields_soil.csv`)
- NASA POWER daily weather (`*_weather_2021_2025.csv`)
- USDA CDL crop composition (`*_cdl_2021_2025_full_composition.csv`)
- Sentinel-2 NDVI rasters (zonal stats computed at runtime, cached after
  first run)

See `GUIDE.md` for full CLI reference and constants (e.g. Soil Health
Index weighting), and `PROVENANCE.md` for data source attribution and a
note on the grower field-count discrepancy this skill accounts for.
