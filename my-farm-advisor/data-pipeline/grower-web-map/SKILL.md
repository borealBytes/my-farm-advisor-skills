---
name: grower-web-map
description: Generate lightweight interactive HTML maps for grower-level farm intelligence visualization. Use when the user wants an interactive web map with field boundaries, popup metadata, and a field list sidebar, driven by the data-pipeline grower outputs.
license: Apache-2.0
attribution: Superior Byte Works LLC / borealBytes
---

# grower-web-map

Generate a self-contained interactive HTML web map from data-pipeline grower and farm outputs.

## Start Here

- [GUIDE.md](GUIDE.md) – usage and command examples
- [AGENTS.md](AGENTS.md) – runtime conventions and local instructions

## Routing

- Use when the user wants a browser-based map of grower field boundaries from already-seeded data-pipeline farms.
- The generator lives in `data-pipeline/src/scripts/reporting/generate_grower_web_map.py`.
- Output lands under `growers/<grower>/farms/<farm>/derived/dashboards/grower_web_map.html`.
- This subskill does not rebuild farm data; it only renders a map from existing pipeline outputs.
