# Grower Web Map Local Instructions

## Purpose

Lightweight grower-level interactive web map generator that consumes pipeline-produced field boundary GeoJSON and emits a single HTML file per grower.

## Safe edit scope

Keep changes inside `grower-web-map/` and the matching runtime script path `src/scripts/web_maps/`.

## Read nearby docs first

Read `README.md` for the CLI run pattern.

## Runtime contract

- Requires `DATA_PIPELINE_DATA_ROOT` exported.
- Runs from the runtime source copy, not the checkout `src/`.
- Writes outputs into `growers/<grower-slug>/derived/reports/`.
- No extra Python dependencies; uses stdlib `json` and the existing runtime tree.

## Local validation

After changes, run the generator from the runtime copy and verify HTML output size and structure:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/web_maps/generate_grower_web_map.py
```
