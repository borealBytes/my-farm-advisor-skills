---
name: eda-field-comparison
description: Compare field boundaries, CDL crop history, and NASA POWER weather across fields and growers. Produces static visualizations and summary tables for FP2-style multi-grower datasets.
version: 1.0.0
author: Boreal Bytes
tags: [eda, comparison, boundaries, cdl, weather, cross-field, cross-grower]
---

# Workflow: eda-field-comparison

## Description

Compare field boundaries, CDL (Cropland Data Layer) crop history, and NASA POWER weather across fields and growers. This workflow generates static PNG plots and CSV summary tables that answer:

- How do field sizes and shapes differ across growers and regions?
- What are the crop rotation and diversity patterns?
- How do temperature and precipitation regimes differ?

## When to Use This Workflow

- **Multi-grower dataset review**: After expanding a dataset to multiple growers (e.g., FP2 expansion)
- **Boundary comparison**: Compare field sizes and shapes across regions
- **Crop history analysis**: Analyze CDL crop composition and rotation diversity
- **Weather comparison**: Compare growing-season climate across states

## Prerequisites

The script runs in the data-pipeline runtime venv:

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
source "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/activate"
```

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline/src"
python scripts/eda/run_field_comparison.py
```

## Analysis Categories

### A. Field Boundaries

| Output | Plot Type | Story It Tells |
|--------|-----------|----------------|
| `A1_field_area_by_grower.png` | Box plot | Field size distributions reveal different agricultural scales |
| `A2_circularity_vs_area.png` | Scatter plot | NE fields cluster near perfect circularity (center-pivot); IL/IA are more irregular |
| `A3_size_statistical_test.csv` | Kruskal-Wallis + Dunn post-hoc | Statistical confirmation of size differences across growers |

### B. CDL / Cropland Data Layer

| Output | Plot Type | Story It Tells |
|--------|-----------|----------------|
| `B1_crop_composition_by_grower_year.png` | Stacked bar chart | Crop mix shifts over time; NE is corn-dominant, IL/IA show more rotation |
| `B2_crop_diversity_by_grower.png` | Box plot | Rotation intensity varies by region |
| `B3_cdl_statistical_tests.csv` | Chi-square + ANOVA | Statistical evidence that crop composition is not independent of grower |

### C. Weather (NASA POWER 2021-2025)

| Output | Plot Type | Story It Tells |
|--------|-----------|----------------|
| `C1_growing_season_temperature.png` | Box plot (grower x year) | Temperature regimes differ across the Corn Belt |
| `C2_growing_season_precipitation.png` | Box plot (grower x year) | Rainfall patterns explain irrigation vs. rainfed practices |
| `C3_temp_precip_correlation.csv` | Pearson correlation + scatter | Warmer years tend to be drier in NE |

## Output Directory Structure

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/
├── plots/
│   ├── A1_field_area_by_grower.png
│   ├── A2_circularity_vs_area.png
│   ├── B1_crop_composition_by_grower_year.png
│   ├── B2_crop_diversity_by_grower.png
│   ├── C1_growing_season_temperature.png
│   ├── C2_growing_season_precipitation.png
│   └── C3_temp_vs_precip_scatter.png
└── tables/
    ├── A3_size_statistical_test.csv
    ├── B3_cdl_statistical_tests.csv
    └── C3_temp_precip_correlation.csv
```

## Shape Metric

Field circularity is computed with the simple formula:

```
circularity = (4 * π * area) / (perimeter²)
```

A perfect circle has circularity = 1.0. Rectilinear fields have values closer to 0.

## Weather Scope

Growing season is fixed at **May 1 - September 30** for all growers to ensure comparability.

## Resources

- [Scipy Statistics](https://docs.scipy.org/doc/scipy/reference/stats.html)
- [Seaborn Documentation](https://seaborn.pydata.org/)
