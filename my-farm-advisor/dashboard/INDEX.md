# Dashboard Index

Use this index to navigate dashboard-related workflows and documentation.

## Entry Points

- [SKILL.md](SKILL.md) — Skill routing and quick-start
- [README.md](README.md) — Full usage instructions, runtime paths, dependencies, and data sources
- [AGENTS.md](AGENTS.md) — Agent runtime rules and command runbook
- [DASHBOARD_INFO.md](DASHBOARD_INFO.md) — Supplementary: project overview, dataset description, analytical interpretation

## Source Code

- [`src/grower_dashboard.py`](src/grower_dashboard.py) — Main CLI entrypoint (v6: multi-grower, interactive Folium map with variable toggling, click popups, matplotlib static charts)
- [`src/lib/data_loader.py`](src/lib/data_loader.py) — Loads and merges field boundaries, soil, weather, rotation, and NDVI data
- [`src/lib/metrics.py`](src/lib/metrics.py) — Computes SHS, SI, weather resilience, NDVI stability, rotation score
- [`src/lib/ndvi_extractor.py`](src/lib/ndvi_extractor.py) — Extracts NDVI statistics from composite TIFFs using `rasterstats`
- [`src/lib/geospatial.py`](src/lib/geospatial.py) — Geospatial helpers

## Documentation

- [AI_DOCUMENTATION.md](AI_DOCUMENTATION.md) — Transparent record of AI-assisted development
