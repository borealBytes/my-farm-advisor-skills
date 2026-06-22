# Grower Web Map – Local Instructions

## Purpose

This subskill generates lightweight interactive HTML maps from
data-pipeline grower/farm outputs.

## Safe edit scope

Edits should stay in this folder and `data-pipeline/src/scripts/reporting/generate_grower_web_map.py`.
Do not change parent `SKILL.md`, sibling workflows, or root policy
unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` for usage, then `../AGENTS.md` and `../../SKILL.md` for
routing context.

## Runtime contract

- Uses `DATA_PIPELINE_DATA_ROOT` to resolve grower/farm/field paths.
- Reads `field_boundaries.geojson`, `grower.json`, and `farm.json`
  from the canonical runtime tree.
- Writes output to `growers/<grower>/farms/<farm>/derived/dashboards/grower_web_map.html`.
- The map HTML loads Leaflet and OSM tiles from CDNs at view time
  (no local server required).
- The HTML embeds only field boundary GeoJSON and light metadata.
  It does not embed imagery, rasters, or large data tables.

## Local validation

After changes, refresh the runtime source and run the generator
against one or both seeded growers (il-grower, ia-grower). Verify
the HTML opens in a browser and all fields are visible with working
popups and sidebar controls.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the
parent or root files.
