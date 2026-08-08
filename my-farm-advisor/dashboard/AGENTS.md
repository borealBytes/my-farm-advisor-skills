# Dashboard Agent Instructions

## Purpose

This folder owns the interactive dashboard generation skill for the My Farm Advisor umbrella. It produces self-contained HTML dashboards from integrated farm-pipeline data.

## Safe Edit Scope

Edits should stay inside this folder (`my-farm-advisor/dashboard/`) unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling workflows, or root policy from this subskill task unless explicitly requested.

## Read Nearby Docs First

Read `README.md` first for usage, then `SKILL.md` for routing context. Open `src/grower_dashboard.py` and `src/lib/` modules for implementation details.

## Runtime Contract

- `DATA_PIPELINE_DATA_ROOT` is required and must be an absolute writable path outside the skill checkout.
- The dashboard reads data from the runtime tree at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/`.
- Generated outputs (HTML) belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/all/derived/reports/` and must stay out of Git.
- The dashboard uses system Python (or the existing pipeline venv) with these dependencies:
  ```bash
  pip install pandas numpy matplotlib plotly geopandas folium branca rasterio rasterstats
  ```

## Command Runbook

### Generate multi-grower dashboard (default)

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/dashboard
python3 src/grower_dashboard.py
```

### Generate with specific year focus

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python3 src/grower_dashboard.py --year 2023
```

## Data Dependencies

The dashboard expects these runtime files to exist for each grower:

| File Pattern | Purpose |
|-------------|---------|
| `boundary/field_boundaries.geojson` | Field polygons + acreage |
| `derived/tables/*_fields_soil.csv` | SSURGO horizon data per field |
| `derived/tables/*_weather_YYYY_YYYY.csv` | Daily NASA POWER weather |
| `derived/tables/*_crop_rotation.csv` | 5-year rotation summary |
| `fields/<field>/derived/features/ndvi_year_YYYY_composite.tif` | Per-field-year NDVI composite |

If any file is missing, the dashboard logs a warning and continues with available data.

## Local Validation

After structural changes to this skill, run the root validator:

```bash
cd ../..
./scripts/validate.sh
```

For functional testing, run the dashboard and inspect the output HTML:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/dashboard
python3 src/grower_dashboard.py
```

## Local-Delta-Only Reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../AGENTS.md`.
