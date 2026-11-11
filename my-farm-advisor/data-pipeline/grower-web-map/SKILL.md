# Grower Web Map Subskill

**Domain:** Interactive grower-level web maps  
**Parent:** data-pipeline  

## Purpose

Generates a lightweight interactive Leaflet HTML map for each grower,
showing farm field boundaries from the canonical pipeline output.
Maps are written to `growers/<slug>/farm-web-map.html`.

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py
```

Use `--grower-slug` to target one grower:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py --grower-slug il-grower
```

## Output

- `growers/<slug>/farm-web-map.html` — self-contained Leaflet map
