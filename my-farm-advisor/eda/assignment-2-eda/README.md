# Assignment 2 EDA: Three-Grower Corn Belt Comparison

Compares Illinois (DeKalb), Iowa (Cerro Gordo), and Nebraska (Merrick) growers across field boundaries, CDL cropland data, and NASA POWER weather. Each grower has 10 fields.

## Overview

| Detail | Value |
|---|---|
| **Location** | `my-farm-advisor/eda/assignment-2-eda/` |
| **Scripts** | `boundaries.py`, `cdl.py`, `weather.py`, `geospatial.py`, `build_report.py` |
| **Generates** | 12 static PNGs (boundary metrics, CDL composition/rotations, weather summaries, satellite basemap) + 1 DocX report |
| **Output path** | `~/my-farm-advisor-runtime/eda-outputs/` |
| **Report** | `assignment-2-eda-report.docx` (8 sections, 12 embedded figures) |

## Data source

```
~/my-farm-advisor-runtime/data-pipeline/growers/{grower}/farms/{farm}/...
```

## Outputs

```
~/my-farm-advisor-runtime/eda-outputs/
  boundaries/    — 3 plots
  cdl/           — 4 plots
  weather/       — 4 plots
  geospatial/    — 1 map
  assignment-2-eda-report.docx  — 8 sections, 12 figures
```

## Story

Three growers spanning the Corn Belt climate gradient — from humid Illinois through northern Iowa to semi-arid irrigated Nebraska. Each category reveals how farming system and environment shift along that transect.

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime/data-pipeline
source ~/my-farm-advisor-runtime/data-pipeline/.venv/bin/activate
cd my-farm-advisor/eda/assignment-2-eda/scripts
python3 boundaries.py
python3 cdl.py
python3 weather.py
```

Report assembly is a separate step and not included here.
