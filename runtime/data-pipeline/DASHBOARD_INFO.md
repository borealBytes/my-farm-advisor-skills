# Row Crop Intelligence Dashboard — Supplementary Documentation

## Project Overview

The **Row Crop Intelligence Dashboard** is a Streamlit-based interactive dashboard for precision agriculture analysis. It provides farm managers, agronomists, and researchers with integrated insights into soil health, crop vegetation (NDVI), weather patterns, and sustainability metrics across agricultural fields.

### Dashboard Story

**"Integrated Field Intelligence: Soil-Crop-Weather Interactions at Iowa Corn Farm"**

The dashboard tells a data-driven story about how soil variability — organic matter, pH, drainage class, and water-holding capacity — drives crop health outcomes (measured by NDVI) and informs rotation and management decisions across 4 fields totaling 430 acres in north-central Iowa.

---

## Dataset Description

All data is sourced from the My Farm Advisor runtime data pipeline.

| Dataset | Source | Period | Fields | Key Columns |
|---|---|---|---|---|
| **SSURGO Soil Summary** | USDA NRCS | — | 4 | `avg_om_pct`, `avg_ph`, `total_aws_inches`, `avg_cec`, `avg_clay_pct`, `avg_sand_pct`, `drainage_class` |
| **Full Soil Horizons** | USDA NRCS | — | 4 (73 horizons) | `hzdept_r`, `hzdepb_r`, `om_r`, `ph1to1h2o_r`, `awc_r`, `claytotal_r`, `sandtotal_r`, `silttotal_r`, `cec7_r` |
| **Daily Weather** | NASA POWER | 2021–2025 | 4 (7,304 days) | `T2M`, `T2M_MAX`, `T2M_MIN`, `PRECTOTCORR`, `ALLSKY_SFC_SW_DWN`, `RH2M`, `WS10M` |
| **NDVI Summaries** | Sentinel-2 / Landsat | 2021–2025 | 4 | `mean_ndvi` (corn/soybean), `peak_95_ndvi` (corn/soybean) |
| **CDL Crop History** | USDA NASS | 2021–2025 | 4 (38 records) | `crop_name`, `pixel_count`, `pct` |
| **Crop Rotation** | Derived | 2021–2025 | 4 | `rotation_sequence`, `crop_diversity`, `predicted_next_crop` |
| **Field Boundaries** | OSM / manual | — | 4 | Polygon geometry (EPSG:4326) |

### Data Location (Runtime Pipeline)

```
data-pipeline/
  growers/
    iowa-grower/
      farms/
        iowa-grower-iowa/
          boundary/field_boundaries.geojson
          derived/
            tables/
              iowa_grower_iowa_ssurgo_summary.csv
              iowa_grower_iowa_fields_soil.csv
              iowa_grower_iowa_weather_2021_2025.csv
              iowa_grower_iowa_cdl_2021_2025_full_composition.csv
              iowa_grower_iowa_crop_rotation.csv
          fields/
            osm-*/derived/summaries/ndvi_card_summary.json
```

---

## Dashboard Explanation

### Architecture

- **Framework**: Streamlit (Python)
- **Visualization**: Plotly (interactive charts and maps)
- **Data Layer**: Pandas + GeoPandas reading from parquet/CSV/GeoJSON
- **Styling**: Custom CSS theme

### Dashboard Sections

#### 1. Key Performance Indicators (KPI Row)
Six metric cards at the top showing: field count, total acreage, average peak NDVI, average annual precipitation, composite Soil Health Score, and dominant drainage class.

#### 2. Overview & Map Tab
- Interactive geospatial map with toggleable layers (Soil Health, NDVI Peak, Drainage Class, Organic Matter %)
- Field boundaries colored by selected metric with hover tooltips
- Farm summary text with contextual interpretation

#### 3. Soil & Vegetation Tab
- **Box plots**: Soil pH and Organic Matter distribution by field
- **NDVI bar chart**: Corn and soybean NDVI comparison across fields
- **Soil Health Score breakdown**: Stacked contribution of OM, pH, AWC, CEC, drainage
- **Sustainability Index**: Composite metric combining soil health, NDVI, and crop diversity

#### 4. Weather & Climate Tab
- Monthly precipitation grouped bar chart by year
- Temperature range (min/mean/max) with growing season overlay
- Cumulative Growing Degree Days (base 10°C) by field
- Year-over-year precipitation anomaly bars

#### 5. Field Comparison Tab
- Radar chart comparing normalized soil properties between fields
- NDVI trend overlay (side-by-side line chart)
- Crop rotation comparison with outlook text

#### 6. Recommendations Tab
- Per-field action items based on threshold analysis (pH, OM, AWC, drainage, CEC, NDVI)
- Conservation priority ranking
- 2026 season outlook summary

### Metrics Created

#### Soil Health Score (0–10)
Weighted composite of five normalized factors:
- **OM (25%)**: Higher organic matter = better nutrient cycling
- **pH Fitness (20%)**: Deviation from optimal range 6.5–7.0
- **AWC (20%)**: Available water capacity for drought resilience
- **CEC (15%)**: Cation exchange capacity, moderate = balanced
- **Drainage (20%)**: Well-drained soils scored highest

#### Sustainability Index (0–10)
Combines Soil Health Score (50%), NDVI performance (30%), and crop diversity (20%).

---

## Analytical Interpretation

### Key Findings

1. **Soil variability drives NDVI outcomes**: Field A (Clarion, 38.8 ac) shows the highest peak corn NDVI (0.895) and highest organic matter (4.9%). Field D (Spillville, 25.3 ac) has the lowest NDVI (0.833) and lowest OM (3.1%) — a clear soil-health-to-vegetation gradient.

2. **Drainage as a dual factor**: Poorly drained Webster soils (Fields B, C) hold more water and OM but create trafficability constraints. Their NDVI is moderate, suggesting waterlogging during wet years offsets the OM benefit.

3. **Weather patterns are spatially consistent**: GDD accumulation is nearly identical across fields due to proximity, but precipitation anomalies create year-to-year variability. 2023 had optimal distribution; 2024 had a dry July.

4. **Conservation priority gradient**: Field D should be the top priority for conservation practices (cover crops, reduced tillage). Field A should be maintained for its high soil health baseline.

### How to Use This Dashboard

1. **Select fields** using the sidebar multi-select to filter all dashboard views
2. **Adjust year range** to focus on specific seasons
3. **Toggle map layers** to visualize different soil and vegetation metrics spatially
4. **Use the tabs** to navigate between thematic sections
5. **Review recommendations** for actionable per-field management guidance

---

## AI Usage Documentation

### AI Tools Used

This project was developed with assistance from AI coding tools for:
- **Code generation**: Streamlit app structure, Plotly chart configurations, data loading functions
- **Debugging**: Threshold values for recommendation engine, color scale selection
- **Documentation**: Markdown formatting, README structure, interpretation text

### AI Contribution Summary

| Component | AI Role | Human Role |
|---|---|---|
| Dashboard architecture | Suggested multi-tab structure | Defined requirements and layout |
| Data loading functions | Generated boilerplate with path patterns | Verified paths and data sources |
| Chart configurations | Produced initial Plotly code | Refined layouts and interactions |
| Soil Health Score formula | Generated weighted composite approach | Defined weights and validation |
| Recommendation engine | Coded threshold-based rules | Set threshold values and phrasing |
| Deployment config | Dockerfile and docker-compose | Tested and verified |
| Documentation | Initial structure and formatting | Reviewed and edited for accuracy |

### Reproducibility

All dashboard inputs are derived from the My Farm Advisor data pipeline using publicly available data sources (NASA POWER, USDA SSURGO, USDA CDL, Sentinel-2). The dashboard is fully reproducible by running the pipeline and then executing:

```bash
streamlit run build_rowcrop_dashboard.py
```
