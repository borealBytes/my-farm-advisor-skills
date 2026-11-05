---
name: my-farm-advisor
description: >
  Umbrella agricultural data science and farm management skill that routes requests into
  field management, imagery, soil, terrain, weather, exploratory analysis, strategy, and farm-data
  rebuild/reporting workflows.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# My Farm Advisor

**Domain:** Agricultural Data Science & Farm Management  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

---



Use My Farm Advisor as the umbrella skill for agricultural data-science and farm-management work. It routes requests into the correct operational area, then into the specific guide, AGENTS.md, or workflow doc for that task.

## Start Here

Open the subtree index that matches the request:

- [Admin](admin/INDEX.md)
- [Data Sources](data-sources/INDEX.md)
- [EDA](eda/INDEX.md)
- [Field Management](field-management/INDEX.md)
- [Imagery](imagery/INDEX.md)
- [Soil](soil/INDEX.md)
- [Terrain](terrain/INDEX.md)
- [Strategy](strategy/INDEX.md)
- [Weather](weather/INDEX.md)

## Routing Guidance

- Use **Field Management** for boundaries, deterministic field sampling, or headlands.
- Use **Imagery** for Landsat or Sentinel-2 scene acquisition and vegetation products.
- Use **Soil** for soil/crop-layer data with country-aware routing: US → SSURGO/gNATSGO, Canada →
  Ontario DSS ladder, Australia → SLGA/ASF grids + ANSIS sites, anywhere else → SoilGrids 250 m floor
  (decision table in `soil/soil-routing.md`; verified endpoints in
  [references/non-us-soil-sources.md](references/non-us-soil-sources.md)). No silent cross-border fills.
- Use **Terrain** for DEM source policy, elevation provenance, and terrain derivatives.
- Use **EDA** for exploration, comparisons, correlations, visualization, and time series.
- Use **Data Sources** for canonical data rebuilds and farm-level intelligence reporting.
- Use **Strategy** for maturity planning and crop-strategy decisions.
- Use **Weather** for NASA POWER weather acquisition and downstream farm weather analysis.
- Use **Admin** for geospatial administration and browser-based interactive map workflows.
- Use **Data Pipeline** for real field-boundary polygons when setting up demo farms or new countries:
  US → USDA CSB hosted GeoParquet (pyarrow row-group-stat pruning, no whole-file download),
  AU/CA/EU → OSM `landuse=farmland` via Overpass. The repository contract every boundary source
  must satisfy, provider quirks (mandatory User-Agent, `data=`-prefixed bodies, instance rotation,
  `--from-json` replay; Albers-meters bbox columns), and the new-country checklist live in
  `data-pipeline/references/field-boundary-sources.md`. Crop rotation / cropping-history layers per
  country (year-by-year requirement; US CDL, CA ACI, AU gap; global fallback = WorldCereal default
  models via `src/scripts/ingest/apply_worldcereal.py`) are in
  `data-pipeline/references/crop-rotation-sources.md`. **Before any satellite crop-type
  classification, look up the region×year growing-season window** (the toolbox's
  `worldcereal.seasons.get_season_dates_for_extent`, else national/state calendars — never guess
  months; SH seasons cross calendar years) and classify only imagery in that window; report
  predictions with the honest per-region quality caveat (unvalidated outside reference regions).
  Soil/weather/terrain routing then needs
  only the boundary's `country` property.

## Runtime Notes

This umbrella skill contains large supporting assets and examples. The nested farm workflows are document-routed workflows, not separate runtime-discoverable skills. Use the subtree indexes and linked guides and AGENTS.md files for progressive discovery.

## Cross-border deliverable rules

- Boundary-spanning choropleth products (corn RM, soybean MG, GDD) must be built as **one continuous
  surface across the US/Canada border** from the combined county+census-division lookup — a single
  color ramp, no per-country palettes or border gaps. The user reviews these as **rendered map images**:
  always produce and show the PNG, never just the table.
- Canadian admin/maturity/lookup generation follows
  [references/canada-shared-geodata.md](references/canada-shared-geodata.md) (GADM L1/L2, `CA`+PRUID
  FIPS-slot encoding, combined `fips_lookup.parquet` merge, PC SAS signing for NASADEM/ALOS tiles).

## Verification and sync rules

- Rendered soil-property maps need **two QC passes before shipping**: a vision pass on the PNG
  (blank panels, mask/geometry drift, colorbar plausibility) and a **numeric unit check against the
  provider module's scale factors** — gridded sources (SoilGrids Int16 raw) render physically
  impossible values (clay 262 %, pH 68) when the display rescale is skipped. Ground-truth by
  recomputing the mean through the module's `apply_scale` and comparing to the panel titles.
- Display-side rescaling must key off the **source** path/filename, never an intermediate re-clipped
  artifact — re-clip renames hide the provenance and the raw-vs-true-units decision silently reverts.
- After rsyncing a skill git branch into the deployed profile copy, diff **both directions**. The
  deployed copy can be ahead (sections authored in-place during sessions); backport those edits to
  the branch and commit before declaring sync complete.
- Inside commands sent to the terminal, a bare `&` (pandas boolean masks) trips the backgrounding
  guard — write masks as `df.query("col=='x' and other=='y'")` instead.
- Colorbar norms over masked rasters must go through `arr.compressed()` + `np.percentile`: on
  numpy ≥2 `np.nanpercentile` on a MaskedArray ignores the mask and raises a read-only-buffer
  error. Mask raster nodata before computing vmin/vmax or the elevation colorbar stretches to
  thousands of metres below ground.
- Validate every geographic window query against a human-readable attribute of the result
  (county/state names, tile ids) before accepting rows — reversed `--bbox S W N E` pairs widen
  the window silently, and projected-CRS sources compare metres not degrees with zero matches
  as the only symptom.
- Dispatched sub-agents cannot write protected instruction files (AGENTS.md) — the user-consent hook
  denies them; plan doc-writing so AGENTS.md files are applied by the parent after children return.

## Status communication

- Long-running commands (ingest sweeps, render batches, server-retry loops) are narrated as live
  background work, never silence: whenever a command is promoted to background or a multi-minute
  wait begins, send one line naming what is running and the next visible deliverable — the user
  reads an unchanged spinner as "stuck" and will ask.

## Data Notes

Some workflows require LFS-backed or runtime-downloaded assets. Keep generated outputs outside the repository and pull any required LFS assets before running data-heavy workflows. The `data-pipeline/` subskill is authoritative for runtime storage: generated farm assets live under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/...`, shared assets under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/...`, and pipeline commands run from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` after install.
