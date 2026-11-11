# Contributing

This catalog is read by both humans and agents, in many harnesses. Docs are
load-bearing: the routers (`SKILL.md` → `INDEX.md` → subtree `AGENTS.md`) are
how an agent navigates, so documentation drift is a functional bug.

## The doc-sync rule (the one that matters)

**When a feature changes, every document that describes it changes in the same
commit.** Concretely:

| Changed | Also update |
| --- | --- |
| A script's behavior, flags, or outputs | Its workflow `README.md`/`GUIDE.md`, the skill `INDEX.md` row if the description shifts, and the root `README.md` if the capability story changed |
| A data source (added, removed, tier changed) | The coverage ladders in root `README.md` **and** `my-farm-advisor/README.md`, plus the relevant playbook in `data-pipeline/references/` |
| A router (`SKILL.md`, `INDEX.md`, `AGENTS.md`) | Any cross-references from sibling routers; run the validator |
| Example figures | Only under `examples/**/output/` (see [`ASSET_POLICY.md`](ASSET_POLICY.md)); regenerate, vision/human-inspect, then commit |

## Editing discipline

- **Surgical edits, not wholesale rewrites.** These READMEs carry hard-won
  caveats, provenance notes, and measured numbers; a rewrite silently loses
  them. Patch the affected paragraphs, keep the structure, and preserve every
  claim that is still true.
- **No information loss.** If text is removed, it should be because the feature
  it described is gone — not because a rewriter forgot it.
- The root `README.md` must keep **all key information** (coverage ladder,
  gallery, progressive-disclosure rationale, harness/model posture, asset
  policy); sub-skill READMEs may go deeper but must not contradict it.
- Harness-neutral language: Hermes and OpenCode are the tested first-class
  harnesses; never make docs *require* a specific one above the L0 contract.
- No G2F-2026 (or any competition) data or absolute machine paths in the skill
  tree — env-var paths (`DATA_PIPELINE_DATA_ROOT`) and relative links only.

## Every feature ships with a vision-reviewed demo figure

New capabilities are not "done" until there is a rendered example someone can
understand at a glance:

- **One figure per output type, per relevant geography.** Country-specific data
  (US SSURGO, Canada ACI/SoilGrids, Australia SLGA/ASF, …) gets its own example,
  **plus** at least one figure from a country with no specialized source so the
  global floor is visible. Same for breeding and QTL: every workflow family
  (design, placement, fieldbook, selection, mapping, QC diagnostics, terrain
  derivatives, planning layers) must have at least one plotted demo under
  `examples/**/output/`.
- **Vision review before commit — a gate, not a courtesy.** Render the figure,
  then inspect it with a vision model (and your own eyes) against this
  checklist; record the verdict in the commit message:
  1. no empty/blank or half-covered panels — if a panel is *supposed* to be
     sparse (cloud gap, no-data), the caption/title must say so with a number;
  2. **field maps**: axes in the field-local metre frame with the published
     affine note, auto-rotation applied (footprints with no meaningful
     orientation — center-pivot circles — stay unrotated but STILL get the
     boxed true-north arrow), a small viewport margin
     (`field_frame.view_extent()`, ~4%) so the boundary never touches a panel
     edge, and north arrow/callout free of collisions with titles,
     boundaries, and each other;
  3. rasters masked to the field: off-field fragments rendered as neutral
     gray, never as apparent field data; halo clip rule respected (10 % polygon buffer ≥1 cell; 15 % viewport; basemap under)
     (`lib/raster_rules.py` — clip extends > 1 full source cell);
  4. colorbar semantics match the feature: categorical → official discrete
     palettes/legend bands (ISRIC `soil.legends`, WorldCereal classes),
     continuous → sequential/diverging with units, log scales labeled as
     log, cyclic (aspect) on a hue wheel — see the standard table in
     `my-farm-advisor/data-pipeline/references/field-map-frame.md` and
     `my-farm-advisor/data-pipeline/references/basemap.md`;
  5. legends/labels legible at README size; numbers consistent with source.
  A figure that fails review gets fixed or dropped — never committed
  "as-is for now". A change to ANY renderer re-triggers review for every
  gallery figure that renderer draws, not just the one you meant to change.
- Figures must be the **best available version** of the view (overlays on,
  labels de-cluttered, honest caveats in the caption — caveats yes, bugs no).

## Before pushing

```bash
bash scripts/validate.sh          # must pass (routers, links, anchors, asset policy)
```

Then: commit with a message naming both the code and the docs touched; push to
`origin` (the skills repo) and mirror the same skill-tree changes into the
monorepo `skills/` folder so the two trees stay byte-identical.
