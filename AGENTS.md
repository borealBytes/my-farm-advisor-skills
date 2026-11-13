# Repository Instructions

## Purpose

This repository is the canonical My Farm Advisor skill catalog. It contains only the approved My Farm Advisor skills. Reusable Superior Byteworks skills are external dependencies, not repo content.

## In-scope skills

Only these skill roots are in scope unless the task explicitly adds a new skill:

- `my-farm-advisor/`: umbrella farm advisory, farm data pipelines, field management, imagery, soil, weather, EDA, strategy, and admin maps.
- `my-farm-breeding-trial-management/`: breeding operations, trial design, fieldbooks, germplasm, selection, crossing, and field trial placement.

Maturity: `my-farm-advisor` and its data pipeline are the active build focus — the data foundation
everything else stands on. The breeding and QTL skills are initial stabs (real, runnable examples,
fewer than coming) and will expand against that foundation.
- `my-farm-qtl-analysis/`: QTL and GWAS analysis, QC, population structure, genomic prediction, and reporting.

## Dependency boundary

Do not vendor, copy, mirror, or partially import Superior Byteworks skills into this repository. `superior-byte-works-skills` is installed separately and remains the dependency source.

Excluded legacy copies stay out of this repo:

- `superior-byte-works-wrighter`
- `superior-byte-works-google-timesfm-forecasting`

If a task needs Superior Byteworks behavior, update dependency notes or references, not copied files.

## Asset and generated output policy

Do not commit generated or downloaded runtime assets. Do not track `data/`, `.cache/`, build artifacts, `node_modules/`, generated example `output/` folders, or runtime geoadmin payloads.

Runtime geoadmin payload examples include `countries.geojson`, `states_usa.geojson`, and county GeoJSON outputs under `data/my-farm-advisor/shared/geoadmin/`.

Metadata, source URL records, downloader scripts, small JSON or GeoJSON metadata, and reproducibility docs may be committed. Binary assets over 1 MB require Git LFS and reviewer approval. Required LFS-backed formats include `.npy`, `.npz`, `.raw`, `.bin`, `.so`, `.dylib`, and `.dll`.

## Validation

Run from the repository root:

```bash
./scripts/validate.sh
```

Treat validation failure as a blocker unless the task is only drafting docs and explicitly says not to run commands. The validator checks required `SKILL.md` and `README.md` files, provenance records, forbidden paths, and asset policy compliance.

## Release boundary — consumers inherit the artifact, never this repo's project law (2026-11-14)

This repo's history is its own: project-specific rules (for example, the G2F challenge's
external-data cutoff and its backfill history) are first-class law HERE and stay first-class.
When cutting a tag or writing its release note, **a rationale citing another project's event
must carry its scope clause at the source** — consuming repos grep their law faces and
nothing else, and vendored bytes are exempt by design: a sentence whose rationale does not
travel should not be written as if it did.

## Contribution default

Branch work should create a new skill unless the user explicitly asks to add, extend, or modify an existing skill.

New skills need a skill root with `SKILL.md`, `README.md`, `PROVENANCE.md`, local examples or docs as needed, and validation compatibility. Existing skill changes should be as small as possible and stay within the requested skill tree.

## Skill layout expectations

Each top-level skill root should keep:

- `SKILL.md` as the compact routing entrypoint.
- `README.md` as the human overview.
- `PROVENANCE.md` as the source and import record.
- `INDEX.md`, `GUIDE.md`, `AGENTS.md`, examples, references, scripts, or data notes as local workflow docs when present.

Subtree docs should be loaded on demand. Avoid making `SKILL.md` a full manual.

## SKILL.md and router rules

Keep `SKILL.md` short, accurate, and route-focused. Use it to answer when to invoke the skill, where to start, and which local index, guide, AGENTS file, or example family to open next.

Do not duplicate every example or long workflow in `SKILL.md` when a local `README.md`, `INDEX.md`, `GUIDE.md`, or `AGENTS.md` already covers it. Preserve frontmatter names and metadata unless the task explicitly changes skill identity. Prefer focused references and guides that agents load only when needed.

## Figure quality gate (agents too, not just humans)

Every figure that appears in a README, gallery (`examples/**/output/`), or
demo writeup — new *or regenerated* — passes the five-point vision review in
`CONTRIBUTING.md` **before** it is committed: no empty/under-covered panels,
field-map frame contract (local-metre axes, auto-rotation, north arrow +
on every footprint incl. unrotated circles; distance from metre axes, no scale bar), halo clip
respected (polygon buffer + max(10 % of max length, 1 cell); viewport 15 %; basemap under), colorbar semantics matching continuous vs categorical,
legible labels at README size. Concretely:

- After running any rendering script that writes gallery figures, open each
  written PNG with vision and check it against the list; fix or drop, never
  commit "as-is for now".
- A change to a shared renderer (`lib/field_frame.py`, `lib/raster_rules.py`,
  any `render_*.py`/`generate_*.py` feeding the gallery) re-triggers review
  of **every** figure that renderer draws.
- Record the review verdict in the commit message.
