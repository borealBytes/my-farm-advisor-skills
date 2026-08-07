# Dashboard Index

Use this index to navigate dashboard-related workflows and documentation.

## Entry Points

- [SKILL.md](SKILL.md) — Skill routing and quick-start
- [README.md](README.md) — Full usage instructions, interpretation guide, and data sources
- [AGENTS.md](AGENTS.md) — Agent runtime rules and command runbook

## Source Code

- [`src/grower_dashboard.py`](src/grower_dashboard.py) — Main CLI entrypoint that orchestrates all dashboard sections
- [`src/lib/data_loader.py`](src/lib/data_loader.py) — Loads and merges field boundaries, soil, weather, CDL, and NDVI data
- [`src/lib/metrics.py`](src/lib/metrics.py) — Computes Soil Health Score, Sustainability Index, and Conservation Priority
- [`src/lib/ndvi_extractor.py`](src/lib/ndvi_extractor.py) — Extracts NDVI statistics from composite TIFFs using `rasterstats`
- [`src/lib/geospatial.py`](src/lib/geospatial.py) — Builds the interactive Plotly choropleth map

## Documentation

- [AI_DOCUMENTATION.md](AI_DOCUMENTATION.md) — Transparent record of AI-assisted development
