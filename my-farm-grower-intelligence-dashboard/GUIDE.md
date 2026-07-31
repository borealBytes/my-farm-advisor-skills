# Workflow: Grower Intelligence Dashboard

## Description

Generates a single interactive HTML dashboard report for all fields under a
grower. The report contains five Plotly-based visualizations plus a raw-data
summary table, all embedded in one self-contained file that opens in any browser.

## Requirements

- Python 3.9+
- pandas
- geopandas
- rasterio
- rasterstats
- plotly
- numpy

All packages except `plotly` are already installed in the My Farm Advisor
runtime venv. Install `plotly` if needed:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/pip" install plotly
```

## Data Prerequisites

The upstream `my-farm-advisor` data pipeline must have already generated:

1. **Field boundaries** — `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
2. **SSURGO soil summaries** — `growers/<grower>/farms/<farm>/derived/tables/<prefix>_fields_soil.csv`
3. **NASA POWER weather** — `growers/<grower>/farms/<farm>/derived/tables/<prefix>_weather_2021_2025.csv`
4. **USDA CDL composition** — `growers/<grower>/farms/<farm>/derived/tables/<prefix>_cdl_2021_2025_full_composition.csv`
5. **Sentinel-2 NDVI rasters** — `growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/sentinel_YYYYMMDD/sentinel_YYYYMMDD_ndvi.tif`

If any of these are missing, run the farm pipeline first:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
python scripts/run_farm_pipeline.py \
  --grower-slug <grower> \
  --farm-slug <farm> \
  --farm-name "<name>" \
  --weather-backend zarr \
  --weather-start-year 2021 \
  --weather-end-year 2025
```

## Usage

### Basic run

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
python scripts/generate_grower_dashboard.py \
  --grower-slug northern-il-grower \
  --farm-slug northern-il-farm \
  --year 2025
```

### With custom output directory

```bash
python scripts/generate_grower_dashboard.py \
  --grower-slug northern-il-grower \
  --farm-slug northern-il-farm \
  --year 2025 \
  --output-dir /tmp/dashboards
```

### Force recompute NDVI (ignore cache)

```bash
python scripts/generate_grower_dashboard.py \
  --grower-slug northern-il-grower \
  --farm-slug northern-il-farm \
  --year 2025 \
  --force-refresh-ndvi
```

## Output Files

| File | Path | Description |
|------|------|-------------|
| Dashboard HTML | `growers/<grower>/derived/dashboards/grower_intelligence_dashboard.html` | Self-contained interactive report |
| NDVI cache | `growers/<grower>/farms/<farm>/derived/tables/ndvi_field_summary_YYYY.csv` | Cached zonal-stats for reuse |
| Manifest | `growers/<grower>/derived/dashboards/manifest.json` | Pipeline tracking metadata |

## Cache Behavior

The script caches NDVI zonal statistics to avoid re-reading Sentinel rasters on
every run:

- **Cache path:** `farm_derived_dir(grower, farm) / "tables" / f"ndvi_field_summary_{year}.csv"`
- **Cache invalidation:** Use `--force-refresh-ndvi` to recompute.
- **First run:** Computes zonal stats for all fields (~30 seconds for 10 fields).
- **Subsequent runs:** Loads cached CSV instantly.

## Data Source Resolution

All input paths are resolved automatically via the shared `lib.paths` helpers:

| Data | Path Helper |
|------|-------------|
| Boundaries | `farm_boundary_path(grower, farm)` |
| Soil | `farm_soil_sample_path(grower, farm)` |
| Weather | `farm_weather_path(grower, farm)` |
| CDL | `farm_cdl_preferred_full_composition_path(grower, farm)` |
| Sentinel | `field_satellite_dir(grower, farm, field_slug) / "sentinel" / str(year)` |

## Troubleshooting

### "No Sentinel scenes found for field X"
- The field may not have satellite coverage for the target year.
- The script skips the field and continues; the NDVI panel will show fewer points.

### "plotly module not found"
- Install into the runtime venv (see Requirements above).

### "farm_cdl_preferred_full_composition_path returned None"
- The CDL pipeline step did not run. Re-run `run_farm_pipeline.py` with CDL enabled.

### "Empty zonal stats for field X scene Y"
- Usually means the field boundary and raster CRS do not overlap.
- The script skips the scene with a warning.

## Resources

- [Plotly Python Graphing Library](https://plotly.com/python/)
- [Rasterstats Zonal Stats](https://pythonhosted.org/rasterstats/)
- [Sentinel-2 NDVI](https://en.wikipedia.org/wiki/Normalized_difference_vegetation_index)
- [NASA POWER](https://power.larc.nasa.gov/)
- [USDA CDL](https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php)
