---
name: eda-assignment-2-guide
description: How to generate all Assignment 2 field-level EDA outputs
version: "1.0.0"
author: Boreal Bytes
tags: [eda, assignment-2, visualization, python, static]
---

# EDA — Assignment 2 Guide

## Description

Runs the five Assignment 2 EDA scripts against all three growers (IL, IA, NE). Each script reads canonical data-pipeline outputs from the runtime and writes PNG visualizations to each grower's `derived/reports/` directory.

## Prerequisites

- `DATA_PIPELINE_DATA_ROOT` must be set and point to a completed Assignment 2 runtime
- Runtime venv with: `matplotlib`, `pandas`, `geopandas`, `numpy`, `seaborn`, `scipy`

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"

RUNTIME_PY="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python"
EDA_DIR="scripts/eda/assignment_2"

# Run all 5 scripts for Illinois
for script in eda_boundaries.py eda_weather.py eda_cdl.py eda_field_map.py; do
  "${RUNTIME_PY}" "${EDA_DIR}/${script}" \
    --grower-slug il-grower --farm-slug il-grower-illinois --farm-name "Illinois Farm"
done

# Run cross-state comparison once (reads all growers)
"${RUNTIME_PY}" "${EDA_DIR}/eda_cross_state.py"

# Repeat for Iowa and Nebraska (skip cross-state)
for grower in ia-grower ne-grower; do
  slug="${grower}"
  farm="${grower}-${grower%%-*}"
  # fix: use correct farm slugs
done
```

## Script Reference

| Script | Args | Outputs |
|--------|------|---------|
| `eda_boundaries.py` | `--grower-slug`, `--farm-slug`, `--farm-name` | `{prefix}_field_sizes.png`, `{prefix}_boundary_stats.png` |
| `eda_weather.py` | same | `{prefix}_weather_timeseries.png`, `{prefix}_weather_seasonal.png` |
| `eda_cdl.py` | same | `{prefix}_cdl_distribution.png`, `{prefix}_cdl_rotation.png` |
| `eda_cross_state.py` | (reads all 3) | `cross_state_comparison.png` in IL reports dir |
| `eda_field_map.py` | `--grower-slug`, `--farm-slug`, `--farm-name` | `{prefix}_field_overview_map.png` |

## Output locations

- Per-grower: `growers/{grower}/farms/{farm}/derived/reports/`
- Cross-state: `growers/il-grower/farms/il-grower-illinois/derived/reports/`
