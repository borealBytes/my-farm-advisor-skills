# Assignment 2 — Field EDA report

One-time HTML report assembled from the `field-eda` subskill's runtime outputs.
It is **not** part of the reusable skill: the subskill writes figures, tables,
and caption sidecars, and this directory turns them into a single document.

## View it

GitHub shows `.html` files as source, not as a rendered page. Two ways to read it:

1. **Download and open** — grab
   [`field-eda-report.html`](field-eda-report.html) (raw download, then open it in
   any browser). The file is self-contained: all ten figures are embedded, so
   there is nothing else to fetch.
2. **Render from the branch** —
   [htmlpreview link](https://htmlpreview.github.io/?https://raw.githubusercontent.com/Windfery/my-farm-advisor-skills/assignment-2/reports/assignment-2/field-eda-report.html).
   This is a third-party viewer; if it is unavailable, use option 1.

## What is inside

- Cover and dataset snapshot: 3 growers, 30 fields, 150 CDL field-years.
- Five headline numbers and the five findings that survived the checks.
- One section per category — boundaries, cropland history, seasonal weather,
  maturity fit and field signals — with every figure, its question/story/caveat,
  and the analysis table.
- Limits, sources and attribution, and a 30-row field appendix.

All statistics are read from the CSVs at build time, so the prose cannot drift
from the analysis. The open work is the analysis, not the layout.

## Rebuild

The report is deterministic for unchanged inputs (apart from the build date).

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime

# refresh the EDA outputs
cd my-farm-advisor/eda/field-eda
./scripts/install.sh
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/scripts/run_field_eda.py"

# rebuild the report
cd ../../../reports/assignment-2
python3 build_report.py
```

`build_report.py` uses only the standard library and reads
`$DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/field-eda/`. Pass `--runtime` and
`--out` to override the defaults.

## Scope note

This is an Assignment 2 deliverable, committed once so the PR is self-contained.
The reusable subskill stays at `my-farm-advisor/eda/field-eda/` and has no
report-generation code. Regenerating the report does not change the skill.

## Attribution

OpenStreetMap contributors (ODbL 1.0) · USDA NASS CDL and Crop Sequence
Boundaries (public domain) · NASA POWER (public). Figures contain no personal or
proprietary farm data.

## Labels and IDs

Every chart carries both axis labels. Figure and map captions show the subskill's
catalog ID (`F1`–`F7`, `M1`–`M3`) taken from the caption sidecar's title line, and
the four analysis tables keep their `A1`–`A4` headings. The two tables derived
for this report alone — the dataset snapshot and the field appendix — are `D1`
and `D2`; the `D` prefix marks report-derived content, not a subskill output.
