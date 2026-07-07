---
name: assignment-2-field-eda
description: Generate static EDA artifacts for field-level weather, CDL/cropland, and boundary data across multiple growers. Supports field, field-year, grower, and across-grower comparisons.
version: 1.0.0
author: Boreal Bytes
tags: [eda, assignment, weather, cdl, boundaries, geospatial, comparison]
---

# Workflow: assignment-2-field-eda

## Description

This workflow generates a comprehensive set of static visualizations and statistical summaries for Assignment 2 field-level exploratory data analysis. It works with the My Farm Advisor data-pipeline runtime outputs to produce publication-quality charts and an interactive geospatial map.

## When to Use This Workflow

- **Multi-grower comparison**: Compare weather, crops, and field characteristics across Illinois, Iowa, and Nebraska
- **Field-level profiling**: Understand per-field patterns in temperature, precipitation, and crop rotation
- **Cross-state analysis**: Identify differences in growing conditions and crop distributions
- **Assignment deliverables**: Generate the required 2 visualizations per category + 1 map

## Prerequisites

```bash
pip install pandas numpy matplotlib seaborn geopandas folium scipy
```

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python my-farm-advisor/eda/assignment-2-field-eda/scripts/run_assignment2_eda.py \
  --output-dir "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2"
```

## Output Structure

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2/
├── weather/
│   ├── growing_season_temp_boxplot.png
│   ├── annual_precip_by_field.png
│   └── gdd_comparison.png
├── cdl/
│   ├── crop_distribution_stacked.png
│   ├── rotation_diversity_hist.png
│   └── corn_vs_soy_area_trend.png
├── boundaries/
│   ├── field_size_distribution.png
│   ├── total_acreage_by_grower.png
│   ├── size_vs_dominant_crop.png
│   └── all_fields_map.html
└── cross_grower/
    └── statistical_tests.csv
```

## Analysis Categories

### Weather
- **Growing season temperature boxplot**: Compare May–September daily mean temperatures across growers
- **Annual precipitation by field**: Total annual precipitation per field, faceted by grower
- **GDD comparison**: Cumulative Growing Degree Days curves per field, with crop-specific parameters

### CDL / Cropland
- **Crop distribution stacked bar**: 100% stacked crop composition per grower × year
- **Rotation diversity histogram**: Distribution of crop-diversity counts per field
- **Corn vs. soybean area trend**: Estimated acreage trends across years per grower

### Boundaries
- **Field size distribution**: Histogram of field sizes (acres) by grower with KDE
- **Total acreage by grower**: Farm-level acreage and field count summary
- **Size vs. dominant crop**: Scatter plot of field area vs. 2025 dominant crop

### Geospatial
- **Interactive Folium map**: All 30 field boundaries colored by grower, with county overlays and popup information

### Statistical Tests
- **Kruskal-Wallis tests**: For growing-season temperature and precipitation differences across states
- Results saved to CSV with interpretation

## Resources

- [NASA POWER Weather Guide](../../weather/nasa-power-weather/GUIDE.md)
- [CDL Cropland Guide](../../soil/cdl-cropland/GUIDE.md)
- [Field Boundaries Guide](../../field-management/field-boundaries/GUIDE.md)
- [EDA Visualize Guide](../eda-visualize/GUIDE.md)
