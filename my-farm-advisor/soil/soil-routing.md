# Soil source routing by field location

`ingest/download_soil.py` (and `ingest/download_soilgrids.py`) route each field
by the `country` property written on its boundary at ingestion time, falling
back to US when absent (historic default). Every soil artifact carries a
`soil_source` column so mixed-country farms stay honest.

## Decision table

| Field location | Primary source | Analog role | Fallback |
|---|---|---|---|
| `US` | SSURGO via NRCS SDA (`ssurgo-soil`) | mapped soil polygons + profile/lab tables | gNATSGO (parallel never fill; tested/method flags honored) → SoilGrids |
| `CA` | Ontario Detailed Soil Survey (`ontario-soil-survey`) | SSURGO analog, ON only (30-report scope, tested/method flags) | SoilGrids global grid |
| `AU` | SLGA/ASF national soil attribute grids (`australia-soil`), streamed **keyless** via the CSIRO DAP public mirror | wall-to-wall property rasters (~1 km), CC-BY, DOIs pinned | ANSIS site index (profile/site records, ASRIS successor); SoilGrids global grid |
| any other country | **SoilGrids 250 m** (`soilgrids-global`) | global property grid, 9+ bands × depth slabs | — (this is the floor) |

## Hard rules

- **No silent cross-border fills.** A field outside SSURGO coverage gets
  `soil_source = soilgrids_250m` (or the national layer), never SSURGO rows
  interpolated from a neighbouring country.
- **Grid rasters are estimates, not surveys.** SoilGrids/ASF clips carry full
  provenance (`source_url`, `accessed_at`, DOIs) in their stats tables; they
  ground decisions but do not replace a soil test. Ontario/ASRIS profile rows
  carry lab `tested`/`method` flags and keep the SSURGO discipline (never
  fill untested numerics).
- **ASF/SLGA COGs stream keyless** from the CSIRO DAP mirror (default); the
  canonical TERN store adds the free `SLGA_TERN_API_KEY` env as an optional
  faster route (account.tern.org.au). ANSIS site catalogues are keyless;
  horizon/lab detail needs an ANSIS account token. Without them all, the AU
  route warns and drops to SoilGrids.
- `download_soilgrids.py` is safe to run everywhere: it keys off the field
  bbox, clips only the tiles it needs from the public ISRIC VRTs, and is
  idempotent via the shared/soilgrids manifest journal.

## Boundary property contract

Boundary GeoJSON features must carry `country` (ISO-3166 alpha-2, e.g. `US`,
`CA`, `AU`) — written by the boundary ingestion/converter step at farm setup.
Missing property ⇒ `US` behavior + warning line, never a guess from centroid.
Where real field polygons come from per country (CSB hosted GeoParquet,
OSM/Overpass farmland, new-country checklist):
[../data-pipeline/references/field-boundary-sources.md](../data-pipeline/references/field-boundary-sources.md).
