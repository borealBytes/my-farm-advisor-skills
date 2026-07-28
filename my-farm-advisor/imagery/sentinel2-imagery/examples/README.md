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

### Source files and outputs

Both the workflow script and generated dashboards are consolidated in `my-farm-advisor-runtime/data-pipeline/dashboard/`:
- `field_year_dashboard.py` — main runner / plotter
- `lib/align_field_year.py` — reusable alignment logic (NDVI + weather + CDL)
- `osm-1499460321_2022_dashboard.png` — prototype year
- `osm-1499460321_{2021..2025}_dashboard.png` — all years

### Rerun / review

The script is reusable for any field in the runtime pipeline. Override defaults with:
- `--field-slug <slug>`
- `--farm <farm-slug>`
- `--grower <grower-slug>`
- `--year <year>`

All parameters (event thresholds, season window, GDD base) are exposed as kwargs in `lib/align_field_year.py` for customization.

---

## Assignment 3 — Field-Year Aligned Dashboard

### Skill / workflow
`field_year_dashboard.py` — generates a 4-panel scientific figure aligning per-scene NDVI, daily weather, CDL crop confirmation, and cumulative GDD for a single field-year.

### Input files used from data-pipeline
| File | Path relative to `my-farm-advisor-runtime/data-pipeline/` |
|------|-----------------------------------------------------------|
| Field boundary | `growers/il-grower/farms/il-grower-illinois/fields/osm-1499460321/boundary/field_boundary.geojson` |
| Daily weather | `growers/il-grower/farms/il-grower-illinois/fields/osm-1499460321/weather/daily_weather.csv` |
| CDL crop table | `growers/il-grower/farms/il-grower-illinois/derived/tables/il_grower_illinois_2022_cdl.csv` |
| Per-scene NDVI | `growers/il-grower/farms/il-grower-illinois/fields/osm-1499460321/satellite/sentinel/2022/*_ndvi.tif` (+ Landsat fallback) |
| NDVI year-crop join | `growers/il-grower/farms/il-grower-illinois/fields/osm-1499460321/derived/tables/ndvi_year_crop_join.csv` |

### Weather metrics calculated
- **Daily GDD:** `max(0, (T2M_MAX + T2M_MIN)/2 − 10.0)`
- **Cumulative GDD:** seasonal running sum
- **Cumulative precipitation:** running sum of `PRECTOTCORR`
- **Temperature range:** `T2M_MAX − T2M_MIN`

### Dashboard image path in data-pipeline
Relative to `my-farm-advisor-runtime/data-pipeline/`:
- `dashboard/osm-1499460321_2022_dashboard.png` (prototype year)
- `dashboard/osm-1499460321_{2021..2025}_dashboard.png` (all years)

### How to rerun
```bash
cd my-farm-advisor/imagery/sentinel2-imagery/examples

# Single year (prototype)
python field_year_dashboard.py --year 2022

# All years for this field
python field_year_dashboard.py --all-years

# Custom output path (overrides default)
python field_year_dashboard.py --year 2022 --output /path/to/custom.png
```

### Known data limitations
- NDVI per-scene TIFFs are stored as GeoTIFFs; mean NDVI values are extracted at runtime via `rasterio.mask` against the field boundary. No pre-computed CSV of per-scene zonal statistics exists.
- Weather data spans 2021–2025 (1,826 daily rows). Dashboards for years outside this range will fail gracefully with "No weather data" panels.
- The `ndvi_year_crop_join.csv` confirms crop type per year, but only 2 of the 10 Iowa sample fields in the skills repo have CDL history. The runtime pipeline (`il-grower-illinois`) provides aligned CDL + NDVI + weather for all its fields.
- Callout box text uses matplotlib's font renderer; if `Source Sans Pro` or `Helvetica` are unavailable, `DejaVu Sans` is substituted automatically.
