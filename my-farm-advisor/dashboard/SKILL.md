---
name: my-farm-advisor-dashboard
description: >
  Interactive multi-grower agricultural intelligence dashboard.
  Generates a self-contained HTML file with an interactive Folium map
  (variable-layer toggling, click popups) and static matplotlib charts
  integrating soil health, NDVI, weather, and sustainability metrics.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "2.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "2.0.0"
---

# My Farm Advisor Dashboard

**Domain:** Agricultural Data Science & Farm Management — Interactive Dashboarding  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

---

## Purpose

Generate interactive, self-contained HTML dashboards that help farmers, agronomists, and agri-business stakeholders understand field-level performance and conditions across all growers. The dashboard integrates:

- Field boundaries and acreage
- SSURGO soil health metrics
- NASA POWER weather and climate summaries
- CDL crop history and rotation patterns
- Sentinel-2 NDVI crop health (computed from composite TIFFs)
- Custom sustainability, weather resilience, NDVI stability, and rotation scores

## Start Here

Open [`README.md`](README.md) for full usage instructions, or jump directly to the source:

- [`src/grower_dashboard.py`](src/grower_dashboard.py) — CLI entrypoint
- [`src/lib/`](src/lib/) — data loader, metrics, geospatial, and NDVI modules

## Routing Guidance

- Use this skill when the user asks for a **dashboard**, **interactive report**, or **grower-level summary**.
- The dashboard is a **self-contained HTML file** — no server required.
- Generated outputs belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/all/derived/reports/`.

## Quick Command

```bash
cd my-farm-advisor/dashboard
python3 src/grower_dashboard.py
```

## Runtime Notes

- Requires `DATA_PIPELINE_DATA_ROOT` to be set (absolute path to the runtime root).
- Reads field boundaries, soil, weather, rotation, and NDVI composite TIFFs from the runtime tree.
- Uses Folium for the interactive map and matplotlib for static charts.
