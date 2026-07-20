# EDA Field Comparison

Cross-field, cross-grower comparison of boundaries, CDL crop history, and NASA POWER weather.

## Prototype Field-Year Selection

For FP3 dashboard prototyping, the following field-year was selected based on data completeness and CDL purity:

| Property | Value |
|----------|-------|
| **Field ID** | `osm-1157043055` |
| **Grower** | `ia-northern-grower` (Iowa) |
| **Year** | `2023` |
| **CDL Crop** | **Soybeans** (100% purity) |
| **Field Size** | ~55 acres |
| **Sentinel Scenes** | 18 (highest coverage among FP1 fields) |
| **Weather** | Complete daily records |
| **NDVI Composite** | Available |

**Rationale:** This field-year offers the cleanest data coverage of all FP1 fields — 100% pure soybean classification, 18 Sentinel scenes for dense NDVI time-series, and complete NASA POWER weather. It is representative of a typical Iowa row-crop field without edge-case complications.

## Multi-Year Path

After the 2023 prototype is validated, the skill will generate plots for all years (2021–2025):

| Year | Crop |
|------|------|
| 2021 | Soybeans |
| 2022 | Corn |
| 2023 | Soybeans (prototype) |
| 2024 | Corn |
| 2025 | Soybeans |

## Outputs

Static PNG plots and CSV tables are written to:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/
├── plots/
└── tables/
```

## Entrypoint

```bash
python scripts/run_field_comparison.py
```

See [GUIDE.md](GUIDE.md) for full workflow documentation.

## Assignment: Field-Year Dashboard

**Workflow:** `scripts/generate_field_year_dashboard.py`

**Input files (from `data-pipeline/growers/ia-northern-grower/farms/ia-northern-grower-farm/fields/osm-1157043055/`):**

| Input | Path (relative to `data-pipeline/`) |
|-------|------|
| Weather | `weather/daily_weather.csv` (columns: `date, T2M, T2M_MAX, T2M_MIN, PRECTOTCORR`) |
| Sentinel manifest | `satellite/sentinel/manifest.json` |
| NDVI rasters | `satellite/sentinel/2023/sentinel_*/sentinel_*_ndvi.tif` |

**Weather metrics:** Daily precipitation, max/min/mean temperature, cumulative GDD (base 10°C), cumulative precipitation, heavy rain events (&gt;25 mm/day), heat waves (max &gt;35°C), cool periods (min &lt;5°C).

**Dashboard output (relative to `data-pipeline/`):**
```
eda/field-comparison/plots/field_year_dashboard_osm-1157043055_2023.png
```
A reference copy of the dashboard image is also committed at `eda/eda-field-comparison/plots/` in this repository.

**How to rerun:**
```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
source "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/activate"
python scripts/generate_field_year_dashboard.py \
  --field-id osm-1157043055 --year 2023 \
  --grower ia-northern-grower --farm ia-northern-grower-farm \
  --crop Soybeans
```
The script is reusable for any field-year by changing the `--field-id` and `--year` arguments.

**Known limitations:**
- NDVI time series has gaps due to cloud cover and Sentinel-2 revisit interval (5-day theoretical, but effective coverage is ~1 scene per 3-4 weeks after filtering). Nine scenes were available for 2023 with a 50-day gap between May 1 and Jun 20.
- Individual scene NDVI uses field-average from raw GeoTIFF rasters; no cloud-masking beyond the `nodata` value in the NDVI product.
- GDD base temperature is fixed at 10°C (configurable via `--gdd-base`); no differentiation between corn and soybean requirements.
- Cool-period detection may include pre-planting spring dates (April) that are less relevant to crop phenology.
