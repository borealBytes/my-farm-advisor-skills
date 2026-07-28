# Sentinel-2 Imagery Example Data

This directory contains sample data and metadata for Sentinel-2 imagery processing.

## Files

- **iowa_10_fields_aoi.geojson** - AOI around current Iowa field-boundaries examples
- **sample_ndvi_metadata.json** - Metadata for a sample NDVI calculation
- **sample_field_stats.csv** - Example field-level NDVI statistics (time series across 4 dates)
- **sample_ndvi_pixels.csv** - Tiny sample of per-pixel NDVI values (for demos/tests; not a real raster)

## Data Source

- **Provider**: ESA Copernicus Sentinel-2
- **Satellite**: Sentinel-2A/2B
- **Product Type**: S2MSI2A (Level-2A, atmospherically corrected)
- **Resolution**: 10m (RGB + NIR bands)
- **AOI CRS**: EPSG:4326 (GeoJSON / CRS84)
- **Imagery CRS**: Sentinel-2 band rasters are typically delivered in a UTM CRS per tile (your NDVI output will inherit the band CRS)

## Relationship to field-boundaries Skill

The AOI and field IDs in these examples are derived from the `field-boundaries` skill:

- `iowa_10_fields_aoi.geojson` is an AOI for `my-farm-advisor/field-management/field-boundaries/examples/real_10_fields_iowa.geojson`
- Field IDs in `sample_field_stats.csv` match those in the field-boundaries examples
- Use both skills together: field-boundaries for AOI, sentinel2-imagery for satellite data

## Sample Acquisition

The sample files represent an illustrative Sentinel-2 NDVI workflow:

- **Location**: Corn Belt region, Minnesota (from field-boundaries sample fields)
- **Dates**: 2024-06-15 through 2024-08-01 (4 acquisitions)
- **Cloud Cover**: 8-20%
- **Fields**: 2 agricultural fields (from field-boundaries examples)

## Usage

```python
import json
import pandas as pd
from sentinelsat import read_geojson, geojson_to_wkt

# Load AOI for Sentinel-2 search
aoi = read_geojson('iowa_10_fields_aoi.geojson')
footprint = geojson_to_wkt(aoi)
print(f"Search footprint: {footprint[:60]}...")

# Load NDVI metadata
with open('sample_ndvi_metadata.json') as f:
    metadata = json.load(f)
print(f"Acquisition: {metadata['acquisition_date']}")
print(f"Cloud cover: {metadata['cloud_cover']}%")

# Load field statistics time series
stats = pd.read_csv('sample_field_stats.csv')
print(stats[['field_id', 'acquisition_date', 'mean_ndvi', 'crop_name']])
```

## Notes

- These are small example metadata and stat files for testing and development
- Actual Sentinel-2 imagery must be downloaded from Copernicus
- Use the main guide for complete download instructions
- Field IDs correspond to the field-boundaries skill examples
- The AOI geometry covers ~2km x 2km around field 271623002471299 in Minnesota

## Field-Year Dashboard

### Selected field, year, and CDL crop

- **Field:** `osm-1499460321`
- **Prototype year:** `2022`
- **CDL crop:** **Corn** (98.48% purity, 325 of 330 pixels)
- **Location:** Iroquois County, Illinois (~40.57°N, 87.81°W)
- **Data source:** `my-farm-advisor-runtime/data-pipeline` (previously run farm pipeline)

### Run the dashboard

```bash
cd my-farm-advisor/imagery/sentinel2-imagery/examples

# Single year (prototype)
python field_year_dashboard.py --year 2022

# All years for this field
python field_year_dashboard.py --all-years

# Custom output path
python field_year_dashboard.py --year 2022 --output ./my_dashboard.png
```

### What it does

1. Loads the field boundary, CDL crop table, daily weather CSV, and per-scene Sentinel NDVI TIFFs from the runtime data-pipeline.
2. Aligns NDVI and weather on a shared Day-of-Year axis (DOY 60–320).
3. Computes cumulative GDD (base 10 °C), cumulative precipitation, and daily temperature bands.
4. Detects notable events: heavy rain, hot days, cool periods, dry spells, NDVI rapid increases, and NDVI dips.
5. Generates a 4-panel PNG dashboard:
   - NDVI time series with scene-level std
   - Temperature band (min/mean/max) with extremes annotated
   - Daily precipitation + cumulative precip
   - Cumulative GDD with Corn growth-stage reference bands (V6, V12, VT, R2)

### Outputs

Dashboard PNGs are written to `output/` next to the script:
- `output/osm-1499460321_2022_dashboard.png`
- `output/osm-1499460321_2021_dashboard.png` … through `2025` when using `--all-years`

### Rerun / review

The script is reusable for any field in the runtime pipeline. Override defaults with:
- `--field-slug <slug>`
- `--farm <farm-slug>`
- `--grower <grower-slug>`
- `--year <year>`

All parameters (event thresholds, season window, GDD base) are exposed as kwargs in `lib/align_field_year.py` for customization.
