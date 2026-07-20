---
name: eda-field-comparison
description: Compare field boundaries, CDL/cropland data, and weather across fields, growers, and states. Produces static PNG visualizations for EDA workflows.
version: 1.0.0
author: Student / Assignment 2
tags: [eda, comparison, field-level, boundaries, cdl, weather, assignment]
---

# Workflow: eda-field-comparison

## Description

Compare agricultural field data across three comparison levels:

1. **Within-field**: How one field changed over 2021–2025
2. **Across fields (within grower)**: How 10 fields in the same state differ
3. **Across growers**: How Illinois, Iowa, and Nebraska farms differ

## When to Use

- Assignment 2 EDA requiring field boundary, CDL, and weather comparisons
- Any multi-grower farm dataset analysis
- When static PNG outputs are preferred over interactive dashboards

## Prerequisites

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-comparison
python src/field_comparison.py
```

## Output Files

All PNGs are written to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/output/YYYY-MM-DD/`:

| # | File | Category | Story |
|---|---|---|---|
| 1 | `01_boundary_size_distribution.png` | Boundaries | Are Nebraska fields larger/more uniform? |
| 2 | `02_boundary_count_vs_acreage.png` | Boundaries | Operational scale differences |
| 3 | `03_cdl_dominant_crop_share.png` | CDL | Which grower is most monoculture? |
| 4 | `04_cdl_crop_diversity.png` | CDL | Which grower has most diverse rotation? |
| 5 | `05_cdl_corn_vs_soy.png` | CDL | Corn/soy trade-off by state |
| 6 | `06_weather_gdd_distribution.png` | Weather | Thermal regime differences |
| 7 | `07_weather_precip_variability.png` | Weather | Rainfall reliability by region |
| 8 | `08_weather_temp_precip_correlation.png` | Weather | Are hot years also dry years? |
| 9 | `09_synthesis_three_farms.png` | Synthesis | The "three farms" side-by-side |

## Categories

### A. Field Boundaries

**Two visualizations + one correlation:**

- **A1**: Histogram + KDE of field acreage by state
- **A2**: Bar chart of field count vs total acreage by grower
- **A3**: Pearson correlation between boundary area and crop diversity

### B. CDL / Cropland Data

**Two visualizations + one correlation:**

- **B1**: Box plot of dominant crop share (`pct`) by state
- **B2**: Bar chart of crop diversity index by field, grouped by state
- **B3**: Scatter + regression of corn acreage vs soybean acreage (2025)

### C. Weather

**Two visualizations + one correlation:**

- **C1**: Violin plot of cumulative GDD by state (uses pipeline GDD parquet)
- **C2**: Box plot of precipitation coefficient of variation by state
- **C3**: Heatmap of monthly T2M_MAX vs PRECTOTCORR correlation by state

### Synthesis

- **S1**: 2×3 multi-panel grid summarizing all key metrics for IL, IA, NE

## Best Practices

- Always set `DATA_PIPELINE_DATA_ROOT` before running
- Output directory is auto-created with today's date
- Soil analysis is intentionally excluded per assignment requirements
- Report assembly is out of scope; use the PNGs in a later report step

## Resources

- Parent index: `../INDEX.md`
- Skill router: `../../SKILL.md`
