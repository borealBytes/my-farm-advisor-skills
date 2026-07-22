# Local Instructions — Soil Variability Dashboard

## Purpose

This folder owns the soil variability analysis dashboard subskill. It generates a
standalone HTML dashboard that aggregates SSURGO soil summaries, weather, NDVI,
and field boundaries across **all farms for a grower**.

## Entry point

```
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/runtime
python src/dashboard.py --grower-slug <grower_slug> --output output/dashboard.html
```

## Safe edit scope

Edits should stay in this folder and its children. Do not change parent
`INDEX.md`, sibling EDA workflows, or root policy from a subskill task unless
explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`.

## File structure

| Path | Purpose |
|------|---------|
| `src/dashboard.py` | Entry point — CLI, HTML assembly, KPI cards |
| `src/data_loader.py` | Grower-level data loading across all farms |
| `src/figures.py` | One function per Plotly chart + KPI helpers |
| `output/` | Generated HTML (gitignored) |
| `requirements.txt` | Python dependencies |
| `app.py` | Dash stub for live-server migration |

## Local workflow notes

- The entry point resolves the grower path via `DATA_PIPELINE_DATA_ROOT`.
- All farms under the grower are aggregated: SSURGO summaries and boundaries
  are concatenated; weather is taken from the first available farm.
- Each `fig_*` function in `figures.py` accepts the full data dict and returns a
  standalone Plotly figure.
- Keep figure functions stateless (no module globals).
- The `make_kpi_indicators` function in `figures.py` is unused by the HTML
  pipeline (KPI cards are built inline in `dashboard.py`). It exists for Dash
  migration.

## Local validation

Run from this directory:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python src/dashboard.py --grower-slug il-northern-grower --output output/dashboard.html
```

Verify the generated HTML renders without error. Run `./scripts/validate.sh`
from the repository root after structural changes.
