---
name: eda-field-compare
description: Compare field boundaries, weather, and CDL/cropland data across multiple growers and states. Produces 10 static PNGs in a four-act story arc with a geospatial context map.
version: 1.0.0
author: Boreal Bytes
tags: [eda, comparison, boundaries, cdl, weather, terrain, cross-grower]
---

# Workflow: eda-field-compare

## Story Arc

The workflow follows a four-act narrative:

1. **Geospatial Context** — where are the fields located?
2. **Field Boundaries** — what does the physical canvas look like?
3. **Weather** — what environmental conditions drive decisions?
4. **CDL/Cropland** — how do farmers respond to those conditions?

Each act builds on the previous one to form a complete picture of three distinct growing environments.

## Outputs

### Act 1 — Geospatial Context

| File | Type | What it shows |
|------|------|---------------|
| `geospatial_context.png` | Map with basemap | All 30 field boundaries, state/county outlines, county labels, field centroids. Auto-includes mean elevation when DEM terrain data is available. |

### Act 2 — Field Boundaries (2 stat-viz + 1 compare)

| File | Type | What it shows |
|------|------|---------------|
| `field_size_distribution.png` | Faceted histogram | Distribution of field sizes per grower with KDE overlay. Annotated with median acreage. |
| `field_area_by_grower.png` | Box plot | Median, IQR, and outlier comparison across IL/IA/NE. |
| `field_size_comparison.png` | ANOVA + stats table | One-way ANOVA testing whether field sizes differ significantly by state. Stats table with count, mean, std, min, max per grower. |

### Act 3 — Weather (2 stat-viz + 1 compare)

| File | Type | What it shows |
|------|------|---------------|
| `monthly_temperature_profile.png` | Line + ribbon | Mean monthly temperature with ±1 std ribbon. Growing-season band highlighted (May–Sep). |
| `annual_precipitation.png` | Grouped bar | Year-by-year total precipitation comparison. Annotated with IL/NE rainfall ratio. |
| `growing_season_climate.png` | Scatter + Pearson r | Apr–Oct mean temperature vs total precipitation per field per year. Pearson correlation per grower. |

### Act 4 — CDL/Cropland (2 stat-viz + 1 compare)

| File | Type | What it shows |
|------|------|---------------|
| `crop_composition_by_grower.png` | 100% stacked bar | Dominant crop shares across all years. Annotated with corn/soy percentages per grower. |
| `crop_diversity_by_grower.png` | Faceted histogram | Distinct crops per field over 5 years. Monoculture fields highlighted. |
| `corn_soybean_tradeoff.png` | Scatter + Pearson r | Corn vs soybean years per field per grower. Strict rotation line annotated. |

## Terrain / DEM Support

The script automatically checks for terrain data under each field's `terrain/dem/` directory. When the `dem_terrain_summary.csv` files exist (produced by `download_dem_terrain.py` in the pipeline), the script loads mean elevation per field and includes it on the geospatial context map.

To generate terrain data:

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src
python scripts/ingest/download_dem_terrain.py \
  --grower <grower-slug> --farm <farm-slug> \
  --allow-live-downloads
```

## Usage

```bash
python src/field_compare_eda.py \
  --data-root ${DATA_PIPELINE_DATA_ROOT}/data-pipeline \
  --output-dir ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-compare/output
```

Without arguments the script reads `DATA_PIPELINE_DATA_ROOT` from the environment.

## Prerequisites

```bash
pip install pandas numpy matplotlib seaborn geopandas contextily scipy
```

## Resources

- [Matplotlib Documentation](https://matplotlib.org/stable/contents.html)
- [Seaborn Documentation](https://seaborn.pydata.org/)
- [Contextily](https://contextily.readthedocs.io/)
