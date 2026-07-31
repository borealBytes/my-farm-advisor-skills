# Provenance

## Data Sources & Attribution

This dashboard skill synthesizes datasets produced by the upstream
`my-farm-advisor` data pipeline. The provenance of each input layer is
listed below.

### 1. Field Boundaries

- **Source:** OpenStreetMap (OSM) polygon features
- **Tool:** Overpass API queries within farm bounding boxes
- **License:** OpenStreetMap — ODbL 1.0
- **Pipeline Stage:** `run_farm_pipeline.py` boundary extraction

### 2. SSURGO Soil Data

- **Source:** USDA NRCS Soil Survey Geographic Database (SSURGO)
- **Tool:** USDA Soil Data Access (SDA) spatial/tabular queries
- **License:** Public Domain (US Federal Government)
- **Pipeline Stage:** `run_farm_pipeline.py` soil query
- **Derived Metrics:** `avg_om_pct`, `avg_ph`, `avg_cec`, `total_aws_inches`,
  `dominant_soil`, `drainage_class`, `erosion_risk`

### 3. NASA POWER Weather

- **Source:** NASA Prediction of Worldwide Energy Resources (POWER)
- **Dataset:** Daily AG meteorology (T2M, PRECTOTCORR, ALLSKY_SFC_SW_DWN,
  RH2M, WS10M, T2M_MAX, T2M_MIN)
- **Backend:** NASA POWER S3 Zarr archive (preferred) or point API
- **License:** Public Domain (NASA)
- **Pipeline Stage:** `run_farm_pipeline.py` weather backend
- **Time Standard:** Local Solar Time (LST)

### 4. USDA Cropland Data Layer (CDL)

- **Source:** USDA NASS Cropland Data Layer
- **Years:** 2021–2025 (CONUS coverage)
- **License:** Public Domain (US Federal Government)
- **Pipeline Stage:** `run_farm_pipeline.py` CDL composition
- **Derived Output:** Per-field pixel counts and percentages per crop code

### 5. Sentinel-2 NDVI

- **Source:** ESA Copernicus Sentinel-2 Level-2A (MSIL2A)
- **Bands:** Red (B04) + NIR (B08)
- **Derived Product:** NDVI = (NIR − Red) / (NIR + Red)
- **License:** Copernicus Open Access — free and open use
- **Pipeline Stage:** `run_farm_pipeline.py` satellite acquisition
- **Reprojection:** EPSG:4326 for boundary masking

## Code Provenance

The `generate_grower_dashboard.py` script reuses patterns established in:

- `my-farm-advisor/data-pipeline/src/scripts/eda/eda_field_season_dashboard.py`
  (NDVI zonal stats via `rasterstats.zonal_stats`)
- `my-farm-advisor/data-pipeline/src/scripts/eda/eda_summary_dashboard.py`
  (multi-panel figure assembly)
- `my-farm-advisor/data-pipeline/src/scripts/reporting/generate_ndvi_composites.py`
  (Sentinel manifest parsing)

## License

Apache-2.0 — see parent repository `LICENSE` file.
