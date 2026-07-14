# Local Instructions

## Purpose

This folder owns the ndvi-weather-dashboard subskill for generating per-field-year HTML dashboards that combine Sentinel NDVI, daily weather, and cumulative GDD with event detection and annotated 4-panel charts.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `INDEX.md`, sibling EDA workflows, or root policy unless explicitly requested.

## Read nearby docs first

Read `SKILL.md` first, then `GUIDE.md`. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Runtime contract

- Uses `DATA_PIPELINE_DATA_ROOT` environment variable to resolve field paths.
- Reads from the canonical runtime tree:
  - `ndvi_year_crop_join.csv` for CDL crop identification
  - `satellite/sentinel/manifest.json` + per-scene NDVI rasters for time series
  - `weather/daily_weather.csv` for precipitation, temperature
  - `boundary/field_boundary.geojson` for zonal NDVI statistics
- Writes output to `<field>/derived/dashboards/ndvi_weather_dashboard_<year>.html`.
- The HTML is fully self-contained (inline CSS, base64-embedded chart image). No external CDN dependencies.

## Local validation

After changes, run `generate_dashboard` against osm-1499317763, year 2023. Verify the HTML opens in a browser with all 4 panels visible, event callouts populated, and warnings displayed for any sparse or missing data.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
