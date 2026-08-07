---
name: my-farm-advisor-dashboard
description: >
  Interactive grower-level agricultural intelligence dashboard built with Plotly.
  Connects soil health, NDVI crop performance, weather, and sustainability metrics
  into a single self-contained HTML decision-support tool.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# My Farm Advisor Dashboard

**Domain:** Agricultural Data Science & Farm Management — Interactive Dashboarding  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

---

## Purpose

Generate interactive, self-contained HTML dashboards that help farmers, agronomists, and agri-business stakeholders understand field-level performance and conditions. The dashboard integrates:

- Field boundaries and acreage
- SSURGO soil health metrics
- NASA POWER weather and climate summaries
- CDL crop history and rotation patterns
- Sentinel-2 / Landsat NDVI crop health (computed from composite TIFFs)
- Custom sustainability and conservation-priority scores

## Start Here

Open [`README.md`](README.md) for full usage instructions, or jump directly to the source:

- [`src/grower_dashboard.py`](src/grower_dashboard.py) — CLI entrypoint
- [`src/lib/`](src/lib/) — data loader, metrics, geospatial, and NDVI modules

## Routing Guidance

- Use this skill when the user asks for a **dashboard**, **interactive report**, or **grower-level summary**.
- The dashboard is a **Plotly standalone HTML file** — no server required.
- Generated outputs belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/`.

## Quick Command

```bash
cd my-farm-advisor/dashboard
python src/grower_dashboard.py --grower-slug ia-grower
```

## Runtime Notes

- Requires `DATA_PIPELINE_DATA_ROOT` to be set (absolute path to the runtime root).
- Uses the existing data-pipeline venv at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv`.
- Reads field boundaries, soil, weather, CDL, and NDVI composite TIFFs from the runtime tree.
