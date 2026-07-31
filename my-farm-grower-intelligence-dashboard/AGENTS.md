# Local Instructions

## Purpose

This folder owns the grower-level interactive intelligence dashboard workflow.
It produces a single self-contained HTML report combining crop rotation,
NDVI, geospatial, weather, and soil visualizations for all fields under one
grower.

## Safe Edit Scope

Edits should stay inside `my-farm-grower-intelligence-dashboard/` unless the
user explicitly asks for a broader skill change. Do not change parent
`SKILL.md`, sibling workflows, or root policy from a subskill task unless
explicitly requested.

## Read Nearby Docs First

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`.

## Local Validation

After structural changes, run `./scripts/validate.sh` from the repository root.

When runtime scripts are available, validate by running the dashboard script
against the canonical test case and verifying the HTML output:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
python scripts/generate_grower_dashboard.py \
  --grower-slug northern-il-grower \
  --farm-slug northern-il-farm \
  --year 2025

# Verify output exists
ls -la "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/northern-il-grower/derived/dashboards/grower_intelligence_dashboard.html"
```

## Local-Delta-Only Reminder

This nested `AGENTS.md` only records instructions that differ from the parent
or root files. Do not duplicate root-wide asset, vendor, or validation policy
here except this pointer to `../../../AGENTS.md`.
