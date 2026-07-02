# Local Instructions

## Purpose

This folder owns the Assignment 2 field-level EDA subskill. It runs a
standardised batch analysis comparing field boundaries, CDL cropland
composition, and weather data across the seeded Illinois, Iowa, and
Nebraska growers.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`.

## Runtime contract

- Requires `DATA_PIPELINE_DATA_ROOT` exported to an absolute path.
- Reads boundary GeoJSON, weather CSV, CDL composition CSV, and crop rotation
  CSV from the canonical runtime tree.
- Writes outputs to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda-assignment2/`.
- No interactive or GUI dependencies; uses `matplotlib.use("Agg")`.

## Local validation

Run the script against one grower first to confirm output integrity:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-assignment2
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_assignment2_eda.py --grower-slug ne-grower
```

Then run `./scripts/validate.sh` from the repository root after structural
changes.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent
or root files. Do not duplicate root-wide asset, vendor, or validation policy
here except this pointer to `../../../AGENTS.md`.
