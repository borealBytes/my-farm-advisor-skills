# Local Instructions

## Purpose

This folder owns Assignment 2 field-level EDA scripts and their documentation.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. For routing context, read `../INDEX.md` and `../../SKILL.md`. The canonical runtime lives under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`; scripts are in `src/scripts/eda/assignment_2/`.

## Local validation

Run all 5 scripts against each grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
for grower in il-grower ia-grower ne-grower; do
  slug="${grower}"
  farm="${grower}-${grower%%-*}"  # transforms il-grower -> il-grower-illinois
  # Actually use the correct farm slug per grower
done
```

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide policy here.
