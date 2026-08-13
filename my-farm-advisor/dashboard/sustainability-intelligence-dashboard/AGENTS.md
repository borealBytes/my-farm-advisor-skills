# Sustainability Intelligence Dashboard — Local Instructions

## Purpose

This folder contains the standalone HTML dashboard builder for the Iowa Farm sustainability analysis. It generates a single-file interactive dashboard from pre-computed pipeline outputs.

## Safe Edit Scope

Edits should stay within this folder. Do not modify parent skill structures or sibling workflows unless explicitly requested.

## Runtime Contract

- Reads data from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/...`
- Writes output to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/dashboards/`
- Requires `DATA_PIPELINE_DATA_ROOT` environment variable
- No large datasets committed to Git — only skill scripts and documentation

## Local Workflow

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Dashboard

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
export AG_GROWER_SLUG=iowa-grower
export AG_FARM_SLUG=iowa-grower-iowa
export AG_FARM_NAME="Iowa Farm"
export PYTHONPATH=src
python -m dashboard_builder.app
```

### Open Output

Open the generated HTML in any browser:
```bash
open ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/iowa-grower/farms/iowa-grower-iowa/derived/dashboards/sustainability_dashboard.html
```

## Validation

Before committing changes:
1. Run the dashboard builder successfully
2. Open the HTML in Chrome/Firefox and verify all sections render
3. Check that the file size is reasonable (< 500 KB for standalone HTML; the dashboard is typically 150–200 KB)
4. Review `DASHBOARD_INFO.md` for analytical accuracy

## Notes

- The builder is designed for grower-level analysis (all fields for a grower)
- NDVI coverage is partial for some fields — the dashboard gracefully handles missing data
- The map uses a lightweight field-level drainage layer instead of full SSURGO polygons to keep the standalone HTML small
- SoilGrids integration was attempted but deferred due to API performance
