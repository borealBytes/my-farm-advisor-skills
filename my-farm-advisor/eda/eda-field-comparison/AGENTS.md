# Local Instructions

## Purpose

This folder owns cross-field and cross-grower comparison workflows for field boundaries, CDL crop history, and NASA POWER weather. It produces static PNG visualizations and CSV summary tables for downstream reporting.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local workflow notes

- The entrypoint is `scripts/run_field_comparison.py`. It expects `DATA_PIPELINE_DATA_ROOT` to be set and readable.
- Outputs are written to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/` (plots/ and tables/).
- Keep the script dependency-only: geopandas, pandas, matplotlib, seaborn, scipy, shapely. All are present in the runtime venv.
- Report assembly is out of scope for this subskill; it produces raw artifacts only.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. If the guide names a local command, run it against the smallest available sample when dependencies are available.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
