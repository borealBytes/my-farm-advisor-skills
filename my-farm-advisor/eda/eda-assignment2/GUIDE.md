---
name: eda-assignment2
description: Assignment 2 field-level EDA comparing boundaries, CDL cropland data, and weather across Illinois, Iowa, and Nebraska growers
version: 1.0.0
author: Boreal Bytes
tags: [eda, assignment, boundaries, cdl, cropland, weather, comparison]
---

> **eda-assignment2** — lives at `my-farm-advisor/eda/eda-assignment2/`.
> Generates 10 statistical charts (PNG), 1 geospatial map (HTML), and
> 1 integrated report (HTML). All outputs land in
> `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda-assignment2/`.

# Workflow: eda-assignment2

## Description

Runs a multi-grower exploratory analysis across field boundaries, CDL cropland
composition, and NASA POWER weather data. Produces 10 PNG charts, 1 HTML
geospatial map, and 1 HTML report for 3 growers (Illinois, Iowa, Nebraska)
with 10 fields each.

Comparisons cover:
- **Within field** — crop changes year-over-year, growing-season temperature profiles
- **Across fields within a grower** — area per field, precipitation per field
- **Across growers** — color-coded bar charts, latitudinal spread tables

## When to Use

Run this subskill when you need a standardized batch of EDA outputs across
multiple growers and farms — e.g. for an assignment submission, sprint
deliverable, or one-time analytical snapshot.

## Prerequisites

- Runtime data at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline` seeded with
  `il-grower`, `ia-grower`, and `ne-grower` (10 fields each)
- Python venv with `geopandas`, `pandas`, `matplotlib`, `numpy`

## Quick Start

Export the data root and run the script:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-assignment2
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_assignment2_eda.py
```

To scope to a single grower:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_assignment2_eda.py --grower-slug ne-grower
```

## Outputs

All outputs land under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda-assignment2/`:

| File | Category | Type |
|------|----------|------|
| `field_area_comparison.png` | Boundaries | Grouped bar chart |
| `field_latitude_extents.png` | Boundaries | Vertical range chart |
| `estimated_corn_acres.png` | CDL | Corn acreage line graph |
| `estimated_soybean_acres.png` | CDL | Soybean acreage line graph |
| `field_plant_harvest_timeline.png` | CDL | Gantt timeline |
| `precip_offseason_cumulative.png` | Weather | Cumulative line chart |
| `temperature_growing_season.png` | Weather | Daily temperature chart |
| `field_area_boxplot.png` | Boundaries | Five-number summary box plot |
| `crop_area_comparison.png` | CDL | Corn/soy vs total area stacked bars |
| `growing_degree_days.png` | Weather | Cumulative GDD line chart |
| `all_farms_map.html` | Boundaries | Combined all-farms geospatial map |

## Dependencies

- `geopandas` / `shapely` — boundary geometry
- `pandas` — data loading and aggregation
- `matplotlib` — chart rendering (Agg backend)
- `numpy` — numerical helpers
- `crop_calendars` — local reference module

## Notes

- Planting and harvest dates are **estimated** from USDA NASS typical crop
  progress calendars per state. They are not observed on-farm dates.
- The CDL composition table uses pixel classification percentages scaled to
  field area as a **crop coverage proxy** — it does not represent measured
  yield (bushels/acre).
- Report assembly is performed outside this subskill. This subskill only
  produces the 6 raw analytical outputs.
