---
name: eda-field-comparison
description: Compare field boundaries, CDL crops, and weather across multiple growers for cross-state agricultural analysis. Generates static PNGs and CSVs.
version: 1.0.0
author: Boreal Bytes
tags: [eda, comparison, fields, boundaries, cdl, weather, cross-state]
---

# Workflow: eda-field-comparison

## Description

Compare field boundaries, CDL (Cropland Data Layer) crops, and weather across multiple growers to reveal state-level agricultural patterns. This workflow is designed for Assignment 2 and generates static PNG visualizations and CSV summary tables.

## When to Use This Workflow

- **Cross-state field comparison**: Compare field sizes, shapes, and locations across growers in different states
- **Crop pattern analysis**: Analyze dominant crops and crop diversity across regions
- **Climate comparison**: Compare temperature and growing degree days across states
- **Assignment 2 EDA**: Generate the required static outputs for field-level exploratory analysis

## Prerequisites

```bash
pip install pandas numpy matplotlib seaborn geopandas scipy
```

## Quick Start

```bash
cd data-pipeline/src
python scripts/eda/field_level_eda.py
```

The script auto-discovers all growers under `growers/` and generates outputs to `eda/field-comparison/output/`.

## Outputs

### Boundary Analysis
- `boundary_violin_area.png` — Field area distribution by grower
- `boundary_area_vs_longitude.png` — Field area vs. longitude scatter
- `map_all_fields.png` — Geospatial map of all fields colored by grower
- `summary/boundary_kruskal_wallis.csv` — Statistical test results

### CDL Analysis
- `cdl_crop_composition.png` — Dominant crop composition by grower
- `cdl_diversity_boxplot.png` — Shannon diversity index by grower
- `summary/cdl_chi_square.csv` — Chi-square test + Cramer's V
- `summary/cdl_diversity_summary.csv` — Diversity statistics

### Weather Analysis
- `weather_temp_violin.png` — Growing-season temperature distribution
- `weather_gdd_cumulative.png` — Cumulative GDD trajectories
- `weather_within_field_timeseries.png` — Representative field time series
- `summary/weather_kruskal_wallis.csv` — Statistical test results

## Stories Each Output Tells

| Output | Story |
|--------|-------|
| **boundary_violin_area** | Do fields in different states have different size distributions? Iowa fields span a much wider range. |
| **boundary_area_vs_longitude** | As we move west, do fields get larger? Tests the "bigger fields in the Plains" hypothesis. |
| **map_all_fields** | Where do these samples sit? Are they clustered or spread across counties? |
| **cdl_crop_composition** | Iowa is corn-dominated; Illinois is soybean-heavy; Nebraska is mixed. Real state-level signatures. |
| **cdl_diversity_boxplot** | Are some states' fields pure monoculture while others have mixed edges? |
| **weather_temp_violin** | Nebraska is warmest, Iowa coolest. Do thermal differences align with geography? |
| **weather_gdd_cumulative** | Which state accumulates growing heat fastest? Nebraska's warmth gives it a head start. |
| **weather_within_field_timeseries** | What does one field's year look like in each climate? |

## Data Gap Handling

The script gracefully handles incomplete weather data:
- Reports coverage per grower (e.g., "IL: 7/10 fields")
- Uses only fields with data for weather analyses
- Includes sample size annotations on weather plots

## No Soil Analysis

This workflow intentionally excludes soil analysis as per assignment requirements.

## Report Assembly

This subskill produces only raw plots and tables. A one-time report should be assembled separately from these artifacts.
