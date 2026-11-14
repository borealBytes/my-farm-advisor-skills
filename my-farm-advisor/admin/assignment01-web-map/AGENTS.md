# Local Instructions

## Purpose

This folder owns the Assignment 1 grower-level interactive web-map subskill.  It
documents how to generate a lightweight, self-contained HTML map for each grower
using actual field boundary GeoJSON produced by the data-pipeline runtime.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change.  Do not change parent `SKILL.md`, sibling
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first, then review the runnable script at
`../../data-pipeline/src/scripts/admin/generate_grower_webmap.py`.  If routing
context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local validation

Run the script from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/admin/generate_grower_webmap.py --grower-slug <slug>
```

After structural changes to this subskill, run `./scripts/validate.sh` from the
repository root.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files.  Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../../AGENTS.md`.
