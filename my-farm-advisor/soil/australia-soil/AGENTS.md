# Australia Soil Local Instructions

## Purpose

Owns the Australian national soil providers: SLGA/ASF attribute grids (the
~1 km SSURGO analog, streamed keyless through the CSIRO DAP mirror; canonical
TERN COG store needs the free `SLGA_TERN_API_KEY`) and the ANSIS site
catalogue (successor of the retired ASRIS map tool) as the profile/site index.
Used by `data-pipeline/src/scripts/ingest/download_soil.py` for fields whose
boundary carries `country == "AU"`. See `GUIDE.md` for the HTTP evidence log.

## Safe edit scope

Edits stay in this folder plus the AU routing hooks in
`../data-pipeline/src/scripts/ingest/download_soil.py`.

## Runtime contract

- `PROPERTY_URLS` pins both `cog` (TERN) and `dap` (CSIRO) URLs + DOIs per
  property; all were live-probed on 2026-11-03. Drift must be a conscious
  re-pin against `RasterProductsAPI/ProductInfo`, never a silent pass.
- ASF grids carry NO scale/offset (values already in %/meq/100g/pH units);
  provenance dicts record dtype + nodata per clip.
- ANSIS catalogues are cached per provider under the farm manifest dir;
  site rows are an index (custodian/project/year metadata), not lab tables —
  horizon/lab detail needs an ANSIS account token (documented in GUIDE).

## Local-delta-only reminder

Only records differences from parent AGENTS.md files.
