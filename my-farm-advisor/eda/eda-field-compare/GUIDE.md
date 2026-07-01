---
name: eda-field-compare
description: Compare field boundaries, CDL/cropland data, and weather across multiple growers and states using static Python visualizations. Generates 9 publication-ready PNGs for cross-grower EDA.
version: 1.0.0
author: Boreal Bytes
tags: [eda, comparison, boundaries, cdl, weather, cross-grower]
---

# Workflow: eda-field-compare

## Description

Compare field boundaries, CDL/cropland data, and weather across multiple growers using a single Python script. The workflow produces 9 static visualizations organized into 3 categories (boundaries, CDL, weather), each with 2 statistical plots and 1 comparison analysis.

Comparisons span three dimensions:
- **Within-field**: year-over-year CDL and weather variation
- **Across fields within a grower**: field size, crop diversity, and microclimate spread
- **Across growers**: IL, IA, and NE differences in acreage, cropping practices, and climate

## When to Use This Workflow

- **Multi-grower analysis**: Compare farm characteristics across states
- **Crop rotation study**: Examine corn/soy dominance and diversity by region
- **Climate context**: Understand temperature and precipitation differences that drive management
- **First-look report**: Generate a comprehensive set of static PNGs for review before deeper analysis

## Prerequisites

```bash
pip install pandas numpy matplotlib seaborn geopandas
```

## Script Usage

```bash
python src/field_compare_eda.py \
  --data-root ${DATA_PIPELINE_DATA_ROOT}/data-pipeline \
  --output-dir ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-compare/output
```

Without arguments the script reads `DATA_PIPELINE_DATA_ROOT` from the environment and writes to `{data-root}/eda/field-compare/output/`.

## Outputs

### Category 1: Field Boundaries

| File | Type | Story |
|------|------|-------|
| `field_size_distribution.png` | Histogram (faceted by grower) | How do field sizes differ? NE center-pivot fields vs IL/IA grid patterns. |
| `field_area_by_grower.png` | Box plot | Median field sizes, spread, and outliers per state. |
| `field_size_stats_table.png` | Stats table + bar chart | Quantified mean, median, std per grower with annotated bar chart. |

### Category 2: CDL / Cropland

| File | Type | Story |
|------|------|-------|
| `crop_composition_by_grower.png` | 100% stacked horizontal bar | Dominant crop shares across all fields and years per grower. |
| `crop_diversity_by_grower.png` | Histogram (faceted by grower) | How many distinct crops per field? Monoculture vs diverse rotation. |
| `corn_soybean_tradeoff.png` | Scatter with Pearson r | Corn years vs soybean years per field. Inverse slope shows rotation tightness per grower. |

### Category 3: Weather

| File | Type | Story |
|------|------|-------|
| `monthly_temperature_profile.png` | Line + ribbon (faceted by grower) | Mean monthly temperature with across-field spread. Growing season length differences. |
| `annual_precipitation.png` | Grouped bar chart | Year-by-year total precipitation comparison across growers. Wet/dry year identification. |
| `growing_season_climate.png` | Scatter with Pearson r | Mean temperature vs total precipitation for Apr-Oct growing season. NE warmer/drier than IL/IA. |

## Complete Example

```python
import subprocess
import sys
from pathlib import Path

script = Path(__file__).parent / "src" / "field_compare_eda.py"
subprocess.run([sys.executable, str(script)], check=True)
```

## Data Sources

- **Field boundaries**: OSM farmland polygons via Overpass API, stored as GeoJSON
- **CDL crop data**: USDA NASS Cropland Data Layer, year-by-year composition and rotation summary
- **Weather**: NASA POWER daily records (2021-2025): temperature, precipitation, solar radiation, humidity, wind

## Resources

- [Matplotlib Documentation](https://matplotlib.org/stable/contents.html)
- [Seaborn Documentation](https://seaborn.pydata.org/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Geopandas Documentation](https://geopandas.org/en/stable/)
