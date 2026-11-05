# SoilGrids Global Local Instructions

## Purpose

Owns the ISRIC SoilGrids 250 m global provider — the always-available modelled
soil-property floor used by the pipeline for every country and as primary for
locations with no national survey coverage. See `GUIDE.md` for band specs,
scale factors, and the retired-band (phhcl/awchc) substitution notes.

## Safe edit scope

Edits stay in this folder plus `../data-pipeline/src/scripts/ingest/download_soilgrids.py`
and the `shared_soilgrids*` path helpers in `../data-pipeline/src/scripts/lib/paths.py`.

## Runtime contract

- No local tile cache: clips stream range-only from the public ISRIC VRTs at
  `files.isric.org/soilgrids/latest/data/...`; outputs land under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/soilgrids/` (gitignored).
- Rasters stay raw Int16; scaling happens ONLY via `BAND_SPECS` in
  `src/soilgrids_global.py`. The empirical re-pin procedure (texture-sum
  check, per-band physical ranges) is documented in `GUIDE.md` — scale-factor
  drift must be a conscious re-pin, never a silent pass.
- VRT CRS is Interrupted Goode Homolosine: every clip must reproject
  (dense-grid rule in GUIDE); never assume 4326 grid alignment.

## Local-delta-only reminder

Only records differences from parent AGENTS.md files.
