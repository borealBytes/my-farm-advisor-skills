# Supplementary Dashboard Information

## Project Overview

The Row Crop Intelligence Dashboard is a portfolio-ready agricultural data product that integrates multiple data sources into a single analytical experience. It demonstrates proficiency in:

- **Data integration**: Combining geospatial, tabular, and raster data from multiple federal and commercial sources
- **Geospatial analysis**: Working with field boundaries, coordinate systems, and spatial joins
- **Environmental data science**: Processing weather, soil, and vegetation index data
- **Data visualization**: Building interactive, multi-panel dashboards with Plotly Dash
- **Agricultural domain knowledge**: Interpreting crop health, soil quality, and sustainability metrics

## Dataset Description

### 1. Field Boundaries (OpenStreetMap)
- **Source**: OpenStreetMap via Overpass API
- **Type**: GeoJSON polygons
- **Coverage**: 10 fields in Cerro Gordo County, Iowa
- **Attributes**: field_id, area_acres, county FIPS codes

### 2. Soil Data (USDA NRCS SSURGO)
- **Source**: Soil Data Access (SDA) REST API
- **Type**: CSV tables + GeoJSON polygons
- **Variables**: organic matter %, pH, cation exchange capacity (CEC), available water capacity (AWC), clay %, sand %, drainage class, erosion risk
- **Processing**: Aggregated from map unit components and horizons to field-level averages

### 3. Weather Data (NASA POWER)
- **Source**: NASA POWER S3 Zarr stores
- **Period**: 2021-2025 (daily)
- **Variables**: temperature (T2M, T2M_MAX, T2M_MIN), precipitation (PRECTOTCORR), solar radiation, relative humidity, wind speed

### 4. NDVI Composites (Sentinel-2)
- **Source**: Microsoft Planetary Computer
- **Product**: Annual median NDVI composites per field
- **Resolution**: 10m (Sentinel-2)
- **Processing**: Cloud-masked, clipped to field boundaries, median composite per year

### 5. Crop Classification (USDA NASS CDL)
- **Source**: Cropland Data Layer
- **Coverage**: 2021-2025
- **Resolution**: 30m
- **Classes**: Corn, Soybeans, Grass/Pasture, Alfalfa, and others

## Dashboard Explanation

### Section A: KPI Summary
Six key performance indicators provide an at-a-glance overview of farm status. The Soil Health Score is a composite of organic matter (30%), pH proximity to 6.5 (25%), CEC (25%), and available water capacity (20%). The Sustainability Index weights soil health (40%), crop rotation diversity (30%), and NDVI performance (30%).

### Section B: Exploratory Visualizations
- **Soil pH Distribution**: Bar chart comparing field pH with optimal range (6.0-7.0) highlighted. Fields outside this range may face nutrient availability constraints.
- **NDVI Comparison**: Bar chart colored by drainage class to reveal the relationship between soil drainage and vegetation health.
- **Correlation Matrix**: Heatmap showing relationships between soil properties, NDVI, and derived indices.

### Section C: Geospatial Map
Field boundaries rendered on a geographic map with centroid markers colored by Soil Health Score. Darker green indicates healthier soils. Hover tooltips show field name, soil health score, NDVI, drainage class, dominant soil type, organic matter, and pH.

### Section D: Weather/Climate
Grouped bar chart showing monthly precipitation across 5 years, with an overlaid temperature line. The growing season (April-September) is highlighted to show the critical window for corn and soybean development.

### Section E: Soil Health & Sustainability
Grouped bar chart comparing Soil Health Score and Sustainability Index across fields. Higher bars indicate better performing fields. The interpretation text highlights key findings.

## Analytical Interpretation

### Key Findings

1. **Soil Organic Matter Drives Health**: Fields with the highest organic matter (6.6-7.7%) achieve the top soil health scores. These fields are in poorly-drained landscape positions where organic matter accumulation is favored.

2. **Drainage Class Gradient**: A clear west-to-east gradient exists across the farm, with somewhat poorly drained and moderately well drained fields showing different soil properties. This affects planting timing and crop management.

3. **NDVI Correlates with Soil Properties**: Fields with better soil health scores tend to show higher NDVI values, though the relationship is moderated by crop type and management.

4. **Rainfall Adequacy**: Average annual precipitation of approximately 854 mm supports rainfed production, with the majority falling during the growing season.

5. **Rotation Diversity**: Most fields follow a 2-crop corn-soybean rotation, with one field in continuous grass/pasture. This limits the sustainability index for some fields despite good soil health.

### Limitations
- NDVI values are extracted from annual composites and may not capture within-season variability
- Soil data represents map unit averages, not in-situ measurements
- The sustainability index is a heuristic and should be validated with field-level management records

## AI Usage Documentation

This dashboard and its supporting documentation were developed with assistance from AI coding tools:

### Tools Used
- **Code generation**: The dashboard script (`row_crop_dashboard.py`) and data utilities (`dashboard_utils.py`) were developed with AI assistance for boilerplate code, Plotly/Dash patterns, and data loading logic
- **Documentation**: README, SKILL.md, AGENTS.md, and SUPPLEMENTARY.md were drafted with AI assistance

### Human Oversight
- All data loading and computation logic was reviewed for correctness
- Dashboard layout and visualization choices were guided by agricultural domain knowledge
- The interpretation text reflects real patterns in the underlying data
- Metric formulas (soil health score, sustainability index) were designed by the human developer

### Data Integrity
- All source data comes from authoritative federal sources (USDA, NASA, USGS)
- The dashboard reads directly from the canonical My Farm Advisor runtime tree
- No synthetic or fabricated data was used in any visualization
