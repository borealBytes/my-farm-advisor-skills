---
name: assignment-2-eda
description: Three-grower Corn Belt comparison EDA — field boundaries, CDL/cropland, and weather across Illinois (DeKalb), Iowa (Cerro Gordo), and Nebraska (Merrick) — 10 fields each, 30 fields total.
version: 1.0.0
author: Boreal Bytes
tags: [eda, boundaries, cdl, weather, comparison, assignment-2]
---

# Workflow: assignment-2-eda

## Description

Static Python scripts comparing field boundaries, CDL crop data, and NASA POWER weather across three growers spanning the Corn Belt climate gradient. Each script is standalone and produces 3 PNG files (2 statistical visualizations + 1 comparison/correlation) into `$DATA_PIPELINE_DATA_ROOT/../eda-outputs/`.

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime/data-pipeline
cd "$(dirname "$0")/scripts"

# Run all four (order independent)
python3 boundaries.py
python3 cdl.py
python3 weather.py
python3 geospatial.py
```

Outputs land in `~/my-farm-advisor-runtime/eda-outputs/{boundaries,cdl,weather,geospatial}/`.

## Output Summary

| Script | Outputs |
|---|---|
| `boundaries.py` | field_size_distribution.png, field_size_boxplot.png, field_centroids.png |
| `cdl.py` | crop_composition.png, crop_diversity.png, rotation_heatmap.png, crop_vs_fieldsize.png |
| `weather.py` | seasonal_temperature.png, annual_precipitation.png, growing_season_climate.png, within_grower_weather_cycle.png |
| `geospatial.py` | field_boundaries_map.png |

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA workflows, or root policy from a subskill task unless explicitly requested.

## Local validation

Run each script from `scripts/` and confirm 3 PNGs appear per subdirectory under `~/my-farm-advisor-runtime/eda-outputs/`.
