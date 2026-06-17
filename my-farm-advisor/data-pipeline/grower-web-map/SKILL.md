---
name: grower-web-map
description: Generate lightweight interactive Leaflet HTML maps per grower from field boundary data in the My Farm Advisor data pipeline runtime.
version: 1.0.0
tags: [web-map, leaflet, grower, field-boundaries, html, interactive]
---

# Skill: grower-web-map

Generate a self-contained interactive HTML web map for each grower in the data-pipeline runtime.

## Routing

- [GUIDE.md](GUIDE.md) — usage, options, and examples
- [AGENTS.md](AGENTS.md) — agent instructions for map generation
- [generate_grower_web_map.py](src/generate_grower_web_map.py) — the generator script

## When to use

- The user wants an interactive browser-based map of their grower's fields.
- The data pipeline has already populated growers and farms with field boundaries.
- The user needs a lightweight map they can open in any browser without a server.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py
```
