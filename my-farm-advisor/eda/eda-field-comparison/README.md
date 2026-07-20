# EDA Field Comparison

A reusable subskill under the My Farm Advisor EDA skill tree for comparing field boundaries, CDL/cropland data, and weather across fields, growers, and states.

## What It Does

- **Boundary analysis**: Compare field sizes, shapes, and compactness within and across growers.
- **CDL analysis**: Compare crop dominance, diversity, and corn/soy trade-offs.
- **Weather analysis**: Compare GDD, precipitation variability, and temperature-precipitation relationships.
- **Cross-grower synthesis**: A single multi-panel figure summarizing all three growers side by side.
- **Report generation**: One-time script (`src/report_generator.py`) that assembles findings into a DocX and HTML report.

## When to Use

- Assignment 2 field-level EDA
- Any farm dataset with multiple growers and time-series weather/CDL data
- When you need static PNG outputs, not interactive dashboards

## Entrypoint

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
python src/field_comparison.py
```

Outputs are written to:
```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/output/YYYY-MM-DD/
```

## Outputs

18 static PNG files, 2 summary files, and a report generator:

### Statistical Visualizations
1. `01_boundary_size_distribution.png` — Field size distribution by state
2. `02_boundary_count_vs_acreage.png` — Field count vs total acreage
3. `03_cdl_dominant_crop_share.png` — Dominant crop share by state
4. `04_cdl_crop_diversity.png` — Crop diversity index by field
5. `06_weather_gdd_distribution.png` — GDD distribution by state
6. `07_weather_precip_variability.png` — Precipitation variability by state

### Comparison / Correlation Analysis
7. `05_cdl_corn_vs_soy.png` — Corn vs soybean acreage correlation
8. `08_weather_temp_precip_correlation.png` — Monthly temperature vs precipitation correlation

### Geospatial
9. `10A_geospatial_fields_only.png` — Field boundaries by state

### Synthesis & Time-Series
10. `09_synthesis_three_farms.png` — Six-metric side-by-side comparison
11. `12_dominant_crop_share_trend.png` — Dominant crop share trend (2021–2025)

### Crop Composition
12. `14_crop_composition_by_state.png` — Crop composition by state (mean pct)
13. `15_crop_acreage_share_trend.png` — Crop acreage share by year
14. `16_crop_acreage_by_state.png` — Crop total acreage by state

### Summary Files
15. `stats_summary.txt` — Plain text statistical results
16. `stats_summary.md` — Markdown formatted statistical results

### Reports (via `src/report_generator.py`)
17. `eda_report.docx` — Word document report
18. `eda_report.html` — Self-contained HTML report (base64 embedded images)
