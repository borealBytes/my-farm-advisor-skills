# Local Instructions

## Purpose

This folder owns Assignment 3 field-season weather & NDVI storyline scripts
and their documentation.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling
EDA workflows, or root policy from a subskill task unless explicitly
requested.

## Read nearby docs first

Read `GUIDE.md` first. For routing context, read `../INDEX.md` and
`../../SKILL.md`. The canonical runtime lives under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline`; scripts are in
`src/scripts/eda/assignment_3/`.

## Local validation

Run the storyline script against the Nebraska test field:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/assignment_3/eda_weather_ndvi_storyline.py \
  --grower-slug ne-grower \
  --farm-slug ne-grower-nebraska \
  --farm-name "Nebraska Farm" \
  --field-slug osm-549149202 \
  --year 2023
```

Verify `derived/reports/osm-549149202_2023_storyline.png` was created in the
field directory.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent
or root files. Do not duplicate root-wide policy here.
