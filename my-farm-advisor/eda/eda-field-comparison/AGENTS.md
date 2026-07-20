# Local Instructions

## Purpose

This folder owns the field-level comparison EDA workflow for Assignment 2. It compares field boundaries, CDL/cropland data, and weather across fields, growers, and states using static Python visualizations.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not edit parent `SKILL.md`, sibling EDA workflows, or root policy from this subskill.

## Read nearby docs first

Read `README.md` first, then `GUIDE.md` for the full workflow. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Data contract

This subskill reads from the runtime data tree only. It does not write into the skill checkout.

Required runtime paths:
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/*_cdl_2021_2025_full_composition_updated.csv`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/*_crop_rotation.csv`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/*_weather_2021_2025.csv`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/corn_maturity/tables/gdd_by_fips_YYYY.parquet`

## Output contract

All outputs go to:
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/output/YYYY-MM-DD/`

Only static PNG files are produced. No interactive dashboards, no HTML, no commit to the skill checkout.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. To verify the subskill works:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-comparison
python src/field_comparison.py
ls ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/output/$(date +%Y-%m-%d)/
```

## Local-delta-only reminder

Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
