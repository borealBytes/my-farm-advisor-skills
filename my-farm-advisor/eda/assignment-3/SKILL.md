---
name: eda-assignment-3
description: >
  Assignment 3 field-season weather & NDVI storyline subskill. Generates a
  single four-panel dashboard combining NDVI, precipitation, temperature
  extremes, and cumulative GDD for one field and year using the canonical
  data-pipeline runtime.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# EDA — Assignment 3

## Purpose

Generates one aligned four-panel dashboard for a single field and growing
season. Reads CDL tables to identify the dominant crop, field daily weather,
and Sentinel NDVI rasters, then aligns them by date. The dashboard panels
show NDVI, precipitation, temperature/extremes, and cumulative GDD with
plot annotations for notable events.

## Script

| Script | Output |
|---|---|
| `eda_weather_ndvi_storyline.py` | 1 four-panel dashboard PNG |

The script accepts `--grower-slug`, `--farm-slug`, `--farm-name`,
`--field-slug`, and `--year` arguments. Run from
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` with the runtime venv Python.
