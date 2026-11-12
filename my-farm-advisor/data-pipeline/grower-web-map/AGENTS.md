# Local Instructions

## Purpose

This folder owns the grower-level interactive HTML field map for My Farm Advisor. It
reads installed runtime boundaries and writes one self-contained page per grower.

## Safe edit scope

Edits stay in this folder and its children unless the user explicitly asks for a
broader skill change. Do not change parent `SKILL.md`, sibling workflows, or root
policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `README.md` first, then `references/web-map-contract.md` before changing output
shape, popup fields, or basemap behavior. If routing context is needed, read
`../README.md` and `../../SKILL.md`.

## Non-negotiables

- **Hectares only.** Every displayed area is converted from the source `area_acres`
  with `1 acre = 4046.8564224 m²`. Never relabel a number without converting it, and
  never emit a source `area_acres` value into the HTML or manifest.
- **Keep the page small.** Embed geometry and scalar attributes only. No imagery, no
  rasters, no base64 tiles, no per-year data bundles.
- **Pin browser dependencies.** Leaflet stays version-pinned from a CDN. Do not move
  the map to an unpinned `latest` URL.
- **Stay standard-library only.** The generator must import nothing outside the Python
  standard library so runtime numpy/pandas pins are never at risk.
- **Write only under the runtime tree.** HTML and manifests belong in
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/maps/`.
- **Deterministic output.** Sort growers, farms, and fields by slug; sort JSON keys;
  write no timestamps into the HTML or manifest.

## Validation

```bash
bash scripts/validate.sh
```

Then install into a runtime and render every grower; confirm field counts, hectares,
and HTML size against the manifest.
