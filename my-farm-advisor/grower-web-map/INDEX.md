# Grower Web Map Index

Generate interactive HTML web maps from real data-pipeline field boundary polygons.

- [Generate Map Script](scripts/generate_map.py) — runnable Python script that builds a Leaflet map from a grower's field boundaries
- [Examples](examples/README.md) — usage examples

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
python scripts/generate_map.py --grower-slug il-grower
```

The script reads the grower's farm-level `field_boundaries.geojson`, loads field display names from the canonical data tree, and writes a self-contained HTML file to `growers/<grower>/farms/<farm>/derived/reports/`.
