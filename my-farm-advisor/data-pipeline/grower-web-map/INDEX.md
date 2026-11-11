# Grower Web Map Index

Small subskill for per-farm interactive HTML field maps. Start with the file that matches the task.

## Human and Routing Docs

- [SKILL.md](SKILL.md) - compact routing entrypoint for agents.
- [README.md](README.md) - install/seeding, CLI, output contract, map behavior, viewing, and attribution.
- [PROVENANCE.md](PROVENANCE.md) - data lineage, basemap/library sources, licenses, and runtime policy.

## Code

- [`src/grower_web_map/builder.py`](src/grower_web_map/builder.py) - boundary discovery, soil and NDVI payloads, metadata formatting, HTML/CSS/JS template, and CLI.
- [`src/grower_web_map/__main__.py`](src/grower_web_map/__main__.py) - `python -m grower_web_map` entry point.
- [`src/grower_web_map/__init__.py`](src/grower_web_map/__init__.py) - package exports.

## Contract Summary

- Inputs: `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` (or per-field fallbacks).
- Optional inputs: `fields/<field>/soil/ssurgo_soil_types.geojson` + `ssurgo_full.csv`, and `fields/<field>/derived/features/ndvi_year_<year>_composite.tif`.
- Output: `growers/<grower>/farms/<farm>/derived/dashboards/<farm>_fields_map.html`.
- Layers: field boundaries (on), SSURGO soils (off), NDVI with 2021–2025 year chips (off).
- Runtime only: generated maps are never committed.
