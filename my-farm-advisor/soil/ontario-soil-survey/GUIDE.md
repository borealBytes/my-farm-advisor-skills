# Ontario Detailed Soil Survey

Use when a farm's fields fall in southern (or surveyed northern) Ontario and
SSURGO does not reach them. Provides the Ontario Detailed Soil Survey as the
Canadian counterpart of the SSURGO step: same per-field soil sample/summary
schema, same per-field polygon caches, plus Ontario-native context (CLI class,
Canadian soil order, parent material, artificial-drainage flag) and explicit
`soil_source`/`soil_flags` provenance.

- Data: AAFC open data "Ontario Detailed Soil Survey" (1:20k–1:50k polygons +
  component/criteria/parent-material/series/horizon tables), dataset
  `a75c3d6c-354d-436d-999d-431fb3a9de79`, metadata updated 2026-01-06.
  https://open.canada.ca/data/en/dataset/a75c3d6c-354d-436d-999d-431fb3a9de79
- Module: `src/ontario_soil_survey.py` — pinned URL + sha256 per file in
  `RESOURCES`; `ensure_payload()` caches all seven files under
  `shared/soil_ontario/` and writes `metadata.json` provenance.
- Entry points used by `ingest/download_soil.py`:
  `fields_with_survey_coverage(fields)`, `download_soil_ontario(...)`,
  `field_polygon_intersections(fields, cache_dir)`.
- Routing: `ingest/download_soil.py` splits fields by spatial intersection with
  the survey layer itself — no country lookup table needed. Canadian fields
  outside survey coverage get no soil rows (flagged, not filled from US data).

## SSURGO-schema mapping

| SSURGO column | Ontario source | Flag when derived |
|---|---|---|
| mukey | POLY_ID (mapunit polygon) | |
| compname | SOILNAME via on_dtl_snt (fallback SOIL_ID) | |
| comppct_r | on_dtl_cmp.PERCENT | |
| drainagecl | on_dtl_crt.DRAINAGE decoded (R/W/MW/I/P/VP) | |
| hzdept_r / hzdepb_r | on_dtl_slt.UDEPTH / LDEPTH (cm) | |
| om_r | ORGCARB × 1.724 | `om_r=ORGCARB*1.724` |
| ph1to1h2o_r | PH2 (pH in H2O) | |
| awc_r | (KP33 − KP1500)/100 | `awc_r=(kPa33-kPa1500)/100` |
| claytotal/sandtotal/silttotal_r | TCLAY / TSAND / TSILT (%) | |
| dbthirdbar_r | BD (not 1/3-bar-specific) | |
| cec7_r | CEC (buffering pH not documented) | |

Raw values (org_carbon_pct, ph_cacl2, kpa_*, ksat, co_fragments_pct, BD in
`dbthirdbar_r` raw, CLI codes, stoniness, slope) are carried as separate
columns; sentinel −9/−99 are coerced to NaN.

## Caveats

- Coverage is *surveyed* Ontario only (~48 survey report areas, southern +
  parts of northern). Uncovered Canadian fields: no rows — never borrow
  SSURGO values across the border.
- Horizon data is per soil series+profile (on_dtl_slt), a many-to-one
  generalization: components sharing a SOIL_ID share horizon rows. Weighting
  to the field is via polygon-area fraction × component PERCENT
  (`polygon_area_frac_field`, `weight_field_pct`).
- pH, CEC, texture are legacy lab/estimate compilations; treat as
  method-uncertain (consistent with the gNATSGO tested/method discipline).
- ORG/R/GRAV/VA texture codes are intentionally undecoded; raw kept.
- Payload ~329 MB (GPKG) + ~31 MB CSV; cached under
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/soil_ontario/`, gitignored.
- GPKG geometry CRS is EPSG:4269 (NAD83 geographic); everything downstream
  reprojects to EPSG:4326.
