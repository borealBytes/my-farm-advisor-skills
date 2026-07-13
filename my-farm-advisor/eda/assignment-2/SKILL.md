---
name: eda-assignment-2
description: >
  Assignment 2 field-level EDA subskill. Generates static Python visualizations,
  comparison analyses, and geospatial maps for field boundaries, weather, and CDL
  across 3 growers (IL, IA, NE) using the canonical data-pipeline runtime.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# EDA — Assignment 2

## Purpose

Field-level exploratory data analysis for all three Assignment 2 growers (Illinois, Iowa, Nebraska). Generates static Python PNG outputs covering field-boundary statistics, weather time series, CDL crop distribution, cross-state comparisons, and a geospatial field overview map.

## Scripts

| Script | Category | Output per grower |
|---|---|---|
| `eda_boundaries.py` | Field boundaries | 2 statistical viz PNGs |
| `eda_weather.py` | Weather | 2 statistical viz PNGs |
| `eda_cdl.py` | CDL/cropland | 2 statistical viz PNGs |
| `eda_cross_state.py` | Comparison | 1 cross-state analysis PNG |
| `eda_field_map.py` | Geospatial | 1 geospatial map PNG |

All scripts accept `--grower-slug`, `--farm-slug`, `--farm-name` arguments. Run from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` with the runtime venv Python.
