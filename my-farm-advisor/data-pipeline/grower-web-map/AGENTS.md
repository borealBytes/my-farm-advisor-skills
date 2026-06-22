# Grower Web Map Local Instructions

## Purpose

This folder owns the grower-level interactive web-map subskill for the My Farm Advisor data pipeline. It generates self-contained HTML maps that aggregate field polygon boundaries across all farms for each grower.

## Safe edit scope

Edits should stay in this folder (`grower-web-map/`) and the associated runtime script at `../src/scripts/reporting/generate_grower_web_map.py`. Do not change parent SKILL.md, sibling workflows, or root policy from this subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first for usage, customization, and quick-start examples.

## Local workflow notes

- The generator script is copied into the runtime tree by `../scripts/install.sh`.
- Run the script from the runtime source copy, not from the checkout.
- Generated HTML maps belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/reports/`.
- The HTML output is self-contained (embedded GeoJSON) and loads its basemap tiles from the internet.

## Local validation

After creating or modifying the script, refresh the runtime source and run the generator:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh --no-install-deps

cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py
```

Verify the output HTML opens in a browser and shows:
- All fields for each grower
- Clickable popups with grower, farm, field, crop, and area metadata
- A functional sidebar field list that zooms to fields

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../AGENTS.md`.
