# SoilGrids Global (250 m)

Use when a farm needs soil evidence and the regional providers do not
reach it: SSURGO covers the US, the Ontario Detailed Soil Survey covers
surveyed Ontario, and everything else — Australia, South America, Africa,
EU, Asia — gets SoilGrids. One global 250 m gridded product (ISRIC,
CC-BY 4.0) supplies the same per-field numeric soil evidence pipeline,
with per-band rasters and a zonal-stats table instead of horizon rows.

- Data: ISRIC SoilGrids, `https://files.isric.org/soilgrids/latest/data/`
  (property directories published today: bdod, cec, cfvo, clay, landmask,
  nitrogen, ocd, ocs, phh2o, sand, silt, soc, wrb). The release self-
  describes in its VRT metadata as code v2.0.0, output RUN10, "no WISE,
  March 2020 snapshot, NZ and Siberia gaps".
- Module: `src/soilgrids_global.py` — band/depth VRT URLs, empirically
  verified `BAND_SPECS` (unit/scale/offset), reprojected clipping
  (`clip_bbox`), cached-raster replay stats (`stats_from_raster`),
  sha256, availability probing (`probe_availability`).
- Ingest: `data-pipeline/src/scripts/ingest/download_soilgrids.py`
  (env-driven like `download_soil.py`).

## Availability caveats verified 2026-11-03

- `phhcl` (pH CaCl2), `awchc`/`awchl` (available water capacity), and
  `thickness` return HTTP 404 on the current release line — pH ships as
  **H2O only** and AWC is absent. Use `phh2o`; empirical rule of thumb
  pH(CaCl2) ≈ pH(H2O) − 0.5..1.0 for mineral soils.
- VRTs open anonymously; each ~5–6 MB VRT XML references GeoTIFF tiles
  (`./<band>_<depth>_mean/tileSG-*/…tif`) that GDAL range-fetches from
  files.isric.org on read. Only tiles intersecting the window download.
- Source CRS is Interrupted Goode Homolosine (no EPSG): a windowed read
  in geographic coordinates is meaningless. `clip_bbox` builds the source
  pixel window from a densely sampled bbox→source transform (single-corner
  transforms can flip lobes near the 40° seams) and reprojects to
  EPSG:4326 with `rasterio.warp.reproject`. Grid: Int16, nodata −32768,
  250 m pixels.

## Scale factors (empirical, verified 2026-11-03)

`physical = raw * scale + offset`. Textures verified via compositional
sum: raw clay+silt+sand means sum to exactly 1000 g/kg globally and
99.998 over the demo field — so raw is g/kg directly.

| band | unit | scale | offset | typical range | verification evidence |
|---|---|---|---|---|---|
| clay / silt / sand | % | 0.1 | 0 | 0.5–99 | Narrabri raw mean 273.6 → 27.4% (expected 20–45); Michigan UP raw mean 163.5 → 16.4% (expected 5–20); sum = 100% |
| bdod | Mg/m3 | 0.01 | 0 | 0.5–2.0 | raw 109–131 → 1.09–1.31 (expected 1.0–1.6); increases with depth ✓ |
| phh2o | pH (H2O) | 0.1 | 0 | 3.0–9.5 | Narrabri 5.1–7.4; Michigan UP 4.1–6.8 (acidic sands ✓) |
| cec | cmol(+)/kg | 0.1 | 0 | 0.5–100 | Narrabri raw 172–246 → 17.2–24.6 (vertisols ✓) |
| soc | hg/cdm3 | 0.1 | 0 | 0.1–300 | ≈ g C/kg at bd 1.0; depth decline 31→10 in demo field ✓ |
| nitrogen | g/kg | 0.01 | 0 | 0.02–30 | embedded global raw mean 376.6 → 3.8 g/kg; depth decline ✓ |
| cfvo | cm3/dm3 | 0.1 | 0 | 0–85 | embedded global raw mean 125 → 12.5 vol% |
| ocd | kg/m3 | 0.1 | 0 | 0.5–250 | global raw mean 350 → 35 kg/m3 (global-stats check only) |

`ocs`, `wrb`, `landmask` are published but unspec'd in
`BAND_SPECS` (stock units unverified; categorical layers).

## Running the ingest

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/runtime
source "${DATA_PIPELINE_VENV_DIR:-$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv}/bin/activate"
AG_GROWER_SLUG=demo-grower AG_FARM_SLUG=demo-au \
python my-farm-advisor/data-pipeline/src/scripts/ingest/download_soilgrids.py \
  --bands bdod,clay,phh2o,sand,silt,soc --depths 0-5cm,5-15cm,15-30cm
```

Reads farm boundaries from `paths.farm_boundary_path()` (or
`--boundaries`/`AG_BOUNDARIES`), field slugs from the farm
`field-inventory.csv` (or slugified `field_id`). Writes:

- `shared/soilgrids/<field_slug>/soilgrids_<band>_<depth>.tif` — raw
  Int16 clips in EPSG:4326 with unit/scale provenance tags;
- `shared/soilgrids/tables/soilgrids_field_stats.parquet` — one row per
  (field, band, depth) with zonal stats masked to the field polygon
  (clipped bbox is buffered 50 m; stats are not);
- `shared/soilgrids/manifests/sha256_journal.json` — sha256 + source URL
  per written raster, `replaced_previous_sha256` on force rewrites;
- farm `manifests/soilgrids_provenance.json` — access time,
  rasterio/GDAL versions, bands, depths, scale table.

Idempotent: existing rasters are skipped and their stats replayed from
disk (rows get `cached_replay` note) unless `--force` / `AG_FORCE=1`.

## Live verification evidence (2026-11-03, GDAL 3.12.2 / rasterio 1.5.2)

- (a) Narrabri NSW bbox (149.40, −31.10, 149.70, −30.90), 0–5 cm,
  11 926/11 926 valid px: clay 14.9–39.4%, mean 27.36% (expected
  20–45 ✓); bdod 1.09–1.31, mean 1.23 Mg/m3 (expected 1.0–1.6 ✓);
  phh2o 5.1–7.4, mean 5.99 (pH CaCl2 expected 4.5–6.5; H2O sits ~0.5–1
  higher ✓).
- (b) Michigan UP incl. Keweenaw bbox (−90.35, 46.60, −88.40, 47.90),
  0–5 cm, 129 932/502 572 valid px (74% nodata = Lake Superior):
  clay 2.9–51.1%, mean 16.35% (expected 5–20 ✓); phh2o 4.1–6.8, mean
  5.00 ✓; bdod 0.85–1.35, mean 1.12 ✓.
- (c) End-to-end run on a scratch data root with one rectangular field
  (`field_id=demo-au-field`, 149.50E/−31.00 … 149.55E/−30.96): 27 rasters
  (9 bands × 3 depths), zonal n=414 px; 0–5 cm means clay 25.6%, sand
  61.1%, silt 13.3% (sum 99.998), pH 5.76, bdod 1.25, soc 31.5,
  nitrogen 2.09, cec 20.4, cfvo 5.1. Re-run skipped all 27;
  parquet has 27 rows + provenance/journal as above.

## Re-probing before extending BAND_SPECS

```bash
curl -s https://files.isric.org/soilgrids/latest/data/ | grep -oE 'href="\./[^"]+"'
curl -s -r 0-4096 https://files.isric.org/soilgrids/latest/data/<band>/<band>_0-5cm_mean.vrt \
  | grep -E 'STATISTICS_(MEAN|MINIMUM|MAXIMUM)'
python -c "import soilgrids_global as sg; print(sg.probe_availability(['phhcl','awchc']))"
```

## Attribution and limits

ISRIC SoilGrids is CC-BY-4.0 (dataset README); cite
"contributed profiles of the ISRIC World Soil Information Service
(WoSIS)" per their data policy. The 250 m grid is coarse relative to a
single field: zonal stats on small fields rest on a handful of pixels
(the demo field: 414 at 0.05°×0.04°), and values are modelled means, not
samples — use as directional evidence beside regional surveys, never as
a lab test. Oceans, lakes, and ice read as nodata; expect partial-coverage
stats on bbox-wide queries.
