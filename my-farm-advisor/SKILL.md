---
name: my-farm-advisor
description: >
  Umbrella agricultural data science and farm management skill that routes requests into
  field management, imagery, soil, terrain, weather, exploratory analysis, strategy, and farm-data
  rebuild/reporting workflows.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# My Farm Advisor

**Domain:** Agricultural Data Science & Farm Management  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

---

## Purpose

Use My Farm Advisor as the umbrella skill for agricultural data-science and farm-management work. It routes requests into the correct operational area, then into the specific guide, AGENTS.md, or workflow doc for that task.

## Start Here

Open the subtree index that matches the request:

- [Admin](admin/INDEX.md)
- [Data Sources](data-sources/INDEX.md)
- [EDA](eda/INDEX.md)
- [Field Management](field-management/INDEX.md)
- [Imagery](imagery/INDEX.md)
- [Soil](soil/INDEX.md)
- [Terrain](terrain/INDEX.md)
- [Strategy](strategy/INDEX.md)
- [Weather](weather/INDEX.md)

## Routing Guidance

- Use **Field Management** for boundaries, deterministic field sampling, or headlands.
- Use **Imagery** for Landsat or Sentinel-2 scene acquisition and vegetation products.
- Use **Soil** for SSURGO and CDL-derived soil and crop-layer analysis.
- Use **Terrain** for DEM source policy, elevation provenance, and terrain derivatives.
- Use **EDA** for exploration, comparisons, correlations, visualization, and time series.
- Use **Data Sources** for canonical data rebuilds and farm-level intelligence reporting.
- Use **Strategy** for maturity planning and crop-strategy decisions.
- Use **Weather** for NASA POWER weather acquisition and downstream farm weather analysis.
- Use **Admin** for geospatial administration and browser-based interactive map workflows.

## Runtime Notes

This umbrella skill contains large supporting assets and examples. The nested farm workflows are document-routed workflows, not separate runtime-discoverable skills. Use the subtree indexes and linked guides and AGENTS.md files for progressive discovery.

## Data Notes

Some workflows require LFS-backed or runtime-downloaded assets. Keep generated outputs outside the repository and pull any required LFS assets before running data-heavy workflows. The `data-pipeline/` subskill is authoritative for runtime storage: generated farm assets live under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/...`, shared assets under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/...`, and pipeline commands run from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` after install.
