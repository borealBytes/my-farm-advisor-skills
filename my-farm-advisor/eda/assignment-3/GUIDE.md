---
name: eda-assignment-3-guide
description: How to generate the field-season weather & NDVI storyline dashboard
version: "1.0.0"
author: Boreal Bytes
tags: [eda, assignment-3, weather, ndvi, gdd, dashboard, storyline]
---

# EDA — Assignment 3 Guide

## Description

Runs the field-season storyline script for one field and year. The script
reads farm-level CDL tables to identify the dominant crop, field daily
weather, and Sentinel-2 NDVI rasters, aligns them by date, and produces a
four-panel dashboard with:

1. **NDVI** — per-scene mean NDVI with annotations for notable changes.
2. **Precipitation** — daily and cumulative with heavy-rain markers (≥1 in).
3. **Temperature/Extremes** — daily T2M, T2M_MAX, T2M_MIN with hot-day
   markers (T2M_MAX ≥ 95°F).
4. **Cumulative GDD** — growing degree days (base 10°C) running sum.

Notable events detected and annotated:
- Heavy rainfall days (≥1 inch precipitation).
- Hot days (max temperature ≥ 95°F).
- Large single-scan NDVI changes (absolute delta ≥ 0.15).

## Prerequisites

- `DATA_PIPELINE_DATA_ROOT` must be set and point to a completed Assignment 3
  runtime with Sentinel NDVI data.
- Runtime venv with: `matplotlib`, `pandas`, `numpy`, `rasterio`, `seaborn`,
  `scipy`, `geopandas`.

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"

RUNTIME_PY="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python"
EDA_DIR="scripts/eda/assignment_3"

"${RUNTIME_PY}" "${EDA_DIR}/eda_weather_ndvi_storyline.py" \
  --grower-slug ne-grower \
  --farm-slug ne-grower-nebraska \
  --farm-name "Nebraska Farm" \
  --field-slug osm-549149202 \
  --year 2023
```

## Script Reference

| Argument | Required | Description |
|---|---|---|
| `--grower-slug` | yes | Grower directory slug |
| `--farm-slug` | yes | Farm directory slug |
| `--farm-name` | yes | Human-readable farm name (for plot title) |
| `--field-slug` | yes | Field directory slug |
| `--year` | yes | Target growing season year |

## Output Locations

- Per-field dashboard: `<runtime>/growers/<grower>/farms/<farm>/fields/<field>/derived/reports/<field>_<year>_storyline.png`

## Output Example

A single 20×16 inch PNG with four vertically-stacked panels sharing the
x-axis date range (Mar–Nov), each with annotations, a figure-level title
showing farm and field info, and a crop label caption.
