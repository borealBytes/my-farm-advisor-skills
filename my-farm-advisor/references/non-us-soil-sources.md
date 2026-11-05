# Non-US soil/crop data sources (Canada-first, verified endpoints)

SSURGO/gNATSGO, CDL, and 3DEP are US-only. Canada has **no single SSURGO clone** — the role
(polygons + measured horizons + attributes joined to map units) splits across a source ladder.
Always carry `soil_source` / `soil_flags` provenance columns and keep the hierarchy explicit
(never silent fill — same rule as gNATSGO).

## Ontario / Canada soil ladder (primary → fallback)

| Tier | Source | Endpoint (access-verified 2026-11-02) | Notes |
|---|---|---|---|
| 1. ON polygons + attribute tables (closest SSURGO analog) | Ontario Detailed Soil Survey (AAFC, dataset `a75c3d6c-354d-436d-999d-431fb3a9de79`) | `agriculture.canada.ca/atlas/data_donnees/detailedSoilSurvey/data_donnees/{geoPackage/on_dtl_soil.gpkg (329 MB),csv/on_dtl_soil_sol/,fgdb/on_dtl_soil_sol.zip}` | 1:20–50k polygons linked to Component (CMP) files; covers southern ON incl. Ottawa. Attribute depth thinner than SSURGO — flag as derived. |
| 2. ON current stitched layer | OMAFRA Soil Survey Complex | ontario.ca/page/soil-data → GeoHub item `ontarioca11::soil-survey-complex` | 48 survey reports merged; attrs: soil type, surface texture, slope, CLI class, stoniness, drainage. Resolve FeatureServer REST path via hub API at build time. |
| 3. Canada-wide gridded, SSURGO-shaped | Gridded SLC (GlobalSoilMap Canada node, dataset `cb29b370-3639-4645-9ef9-b1ef131837b7`) | `.../atlas/data_donnees/soilLandscapesOfCanada90mGrid/data_donnees/tif/gridded_slc_90m.zip` (97 MB) | Fixed GlobalSoilMap depth increments: sand/silt/clay, pH, SOC, CEC, WHC, bulk density over Canadian farmland. Cell values are areal-weighted means; min/max also shipped — carry spread as uncertainty feature. |
| 4. Measured point data (national) | CanSIS National Pedon Database v3 (dataset `6457fad6-...`) | `.../atlas/data_donnees/nationalPedonDatabase/data_donnees/{csv/npdb_v3_csv.zip,geoJSON/npdb_info_v3_geojson.zip}` | 100+ vetted properties/pedon. Geojoin to fields for the 'measured' tier under polygon-derived values. |
| 5. Coarse national polygons | SLC V3.1/V2.2 cartographic 1:1M (dataset `51e7677b-...`) | GPKG/FGDB on open.canada.ca + live FeatureServer `services.arcgis.com/lGOekm0RsNxYnT3j/ArcGIS/rest/services/Soil_landscapes_of_Canada/FeatureServer` | Fallback outside surveyed areas (northern ON). |
| 6. Global wall-to-wall fallback | SoilGrids250m (ISRIC) | WCS at `data.isric.org/geoserver/soilgrids` (OWSLib) = pipeline path; `rest.isric.org/soilgrids/latest` (beta) for spot checks only | ~250 m, ~9 depths + uncertainty. SOC under-predicted in high-clay glacial till (= Ontario grey luvisols); texture RMSE ~5–8 pp. Fallback + ML covariates, never primary where tiers 1–3 exist. Services intermittently 503 from datacenter IPs — retry, don't abandon. |

Hierarchy for fills: ON-Detailed > gridded-SLC > SLC-1M > SoilGrids, each recorded in `soil_source`.

## CDL / terrain gaps (Canada)

- **Crop history**: AAFC **Annual Crop Inventory** — per-year 30 m crop rasters 2009–2025
  (open.canada.ca, org `aafc-aac`). Verify *initial-publication* dates against any data-cutoff
  rule (dataset `metadata_modified` reflects re-issue, not first publication). Alternative:
  Canadian Cropland Atlas 2017–2022 (30 m, peer-reviewed).
- **Terrain**: NRCan CTR/ECTR (2–10 m) replaces 3DEP.
- **Weather**: none needed — NASA POWER path is global.

## CKAN open-data access pitfalls

- open.canada.ca dataset pages render resources via JS — query the API instead:
  `https://open.canada.ca/data/en/api/3/action/package_show?id=<uuid>` (same pattern on
  `data.ontario.ca/api/3/action/package_show?id=<slug>`) to get resource URLs + formats.
- CKAN resource URLs go stale: on a 404 from an `agriculture.canada.ca/atlas/...` link, GET the
  parent directory autoindex and pin the real filename (folder name in the CKAN record may be wrong).
- `web_extract` may be search-backend-only and refuse URL fetches; fall back to `curl -sL -A 'Mozilla/5.0'`
  and parse HTML locally, or use the CKAN API for datasets.
