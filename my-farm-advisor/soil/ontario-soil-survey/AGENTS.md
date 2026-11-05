# Ontario Soil Survey Local Instructions

## Purpose

Owns the Ontario Detailed Soil Survey provider (Canadian SSURGO counterpart)
used by `data-pipeline/src/scripts/ingest/download_soil.py` for fields inside
southern/surveyed Ontario. See `GUIDE.md` for schema mapping and caveats.

## Safe edit scope

Edits stay in this folder plus the routing hooks in
`../data-pipeline/src/scripts/ingest/download_soil.py` and the path helpers in
`../data-pipeline/src/scripts/lib/paths.py`.

## Runtime contract

- Payload cache lives at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/soil_ontario/`
  (gitignored). Pinned URLs + sha256 live in `RESOURCES` in
  `src/ontario_soil_survey.py`; update them together after reviewing the
  AAFC dataset page (checksum drift must be a conscious re-pin, never a
  silent pass).
- Routing is spatial (field ∩ survey polygons), never by a country/state
  string table.

## Local-delta-only reminder

Only records differences from parent AGENTS.md files.
