---
name: australia-soil
description: Acquire Australian national soil data — SLGA/ASF attribute grids (SSURGO counterpart) and ANSIS soil profile sites (ASRIS successor)
version: 1.0.0
author: Boreal Bytes
tags: [tern, slga, asf, ansis, asris, soil, geospatial, download, australia]
---

# Workflow: australia-soil

Australian national soil raster + profile access: the Soil and Landscape Grid
of Australia (SLGA) / Australian Soil Fabric (ASF) attribute grids are the
SSURGO counterpart, and ANSIS site catalogues replace the retired ASRIS map
tool. Every URL below was probed live on **2026-11-03** with the HTTP status
shown; nothing here is second-hand.

Module: `src/australia_soil.py` (`SOURCE_NAME = "slga_asf"`,
`ACCESS_DATE = "2026-11-03"`). License CC BY 4.0 (DAP record `licence` field
and the SLGA site footer).

## TL;DR access matrix (verified 2026-11-03)

| Path | Keyless? | Evidence (all 2026-11-03) |
|---|---|---|
| `esoil.io/TERNLandscapes/RasterProductsAPI/ProductInfo?format=json&product=SLGA&isCurrentVersion=1` | **yes — HTTP 200** (324 current records, incl. `Units`, `UpperDepth_m`, `COGsPath`) | canonical metadata + COG URLs |
| `.../QueryParameterValues?format=json&parameter=Attribute|Product|Component|Resolution` | **yes — HTTP 200** each | filter vocabulary |
| `data.tern.org.au/model-derived/slga/NationalMaps/SoilAndLandscapeGrid/CLY/v2/CLY_000_005_EV_N_P_AU_TRN_N_20210902.tif` | **no — HTTP 401** keyless (HTML login page, 20 KB; directory listing browsable but file GETs gated) | canonical COG store; needs free TERN key (`x-api-key`) |
| `https://esoil.io/TERNLandscapes/RasterProductsAPI/Drill?...` (server-side point sample) | **no — HTTP 400** `{"error":"You now need to supply a TERN API Key with this endpoint. TERN API Keys can be generated at https://account.tern.org.au/authenticated_user/apikeys"}` | same key as the store |
| CSIRO DAP per-file GeoTIFFs, e.g. `https://data.csiro.au/dap/ws/v2/collections/63379/data/63820524` (CLY 0-5 cm EV R2) | **yes — HTTP 302** → presigned `s3.data.csiro.au` URL (48 h expiry) that answers Range probes with **HTTP 206** (`II+` BigTIFF magic) | keyless raster mirror, range-read → stream-clippable |
| `https://apim-ansis-app-prod-ac.azure-api.net/site-catalogue/v1/catalogue-summary` | **yes — HTTP 200** (13 provider catalogues) | profile/site inventory |
| `.../site-catalogue/v1/provider/NewSouthWales` | **yes — HTTP 200** GeoJSON FeatureCollection, 61,106 site points | keyless profile sites |
| `.../site-catalogue/v1/definitions` | **yes — HTTP 200** (242 property codes) | ANSIS code glossary |
| ANSIS `sdrpublic/v1/SingleSite` + `ansis-external-api/queryrequests/v2/*` | **needs free ANSIS login** — token via `Authorise` endpoint, username/password as HTTP *headers* | full horizon/lab JSON |
| `www.asris.csiro.au` (root, `/arcgis/rest/services?f=json`, `/mapping/view_au.php`) | **dead — HTTP 500** ×3 retries ("Proxy Error … Error during SSL Handshake with remote server"); `/cgi-bin/nph-wcs-1.0.0.cgi` → HTTP 403 | ASRIS retired June 2024 |
| `esoil.io/TERNLandscapes/Public/Products/TERN/…` (old `storeRoot`) | **gone — HTTP 404** (tried `…/Covariates/Mosaics/90m/Veg_Landsat8Bare2.tif`, `…/SLGA/30m/SOC/SOC_000_005_…_30m.tif`, `…/SLGA/90m/CLY/…`, `…/SLGA/CLY/v2/…`) | store moved to data.tern.org.au only |
| `esoil.io/TERNLandscapes/Public/Pages/SLGA/GetData-GIS.html` | **yes — HTTP 200**, and states verbatim: "The SLGA no longer supports OGC WCS GIS web services" | WCS/WMS era over for SLGA |
| `esoil.io/TERNLandscapes/Public/Pages/SLGA/GetData-COGSDataStore.html` | **yes — HTTP 200**, states verbatim: "To access the SLGA data products you need to generate an API key." | key requirement is official |
| `geoserver.tern.org.au/geoserver/slga/ows?service=WCS&…` | **broken — HTTP 200 ServiceExceptionReport** (`Capabilities document generation failed on coverage slga:nto_ext_n_p_au_nat_c_20231101 … date must not be null`); `…/slga/ECE_v1/ows?service=WMS&request=GetCapabilities` → HTTP 200 (image-only) | do not build on it |
| DAP legacy `data.csiro.au/dap/ws2/...` | **gone — HTTP 404** (Spring error JSON); use `/dap/ws/v2/` | API re-versioned |
| `data.gov.au/api/3/action/package_search` | **gone — HTTP 404** (HTML); `/data/api/3/action/package_search?q=…` → **HTTP 200** (74 SLGA packages) | if you harvest metadata |

Key signup (free): `https://account.tern.org.au/authenticated_user/apikeys`;
instruction page linked from the SLGA site:
`https://ternaus.atlassian.net/wiki/spaces/TERNSup/pages/2353496065/Creating+API+Keys`.

The R client (`https://github.com/AusSoilsDSM/SLGACloud`, raw `main` fetched
2026-11-03 with HTTP 200 each: `R/config.R`, `R/websites.R`, `R/COGsUtils.R`,
`R/Metadata.R`, `R/rasterMethods.R`) confirms there are exactly three API
endpoints — `QueryParameterValues`, `ProductInfo`, `Drill` — and that COGs
are consumed as `/vsicurl/` + the `COGsPath` from `ProductInfo` (no extra
signing step). It also confirms the 401 is recent: `config.R` still names
`storeRoot='https://esoil.io/TERNLandscapes/Public/Products/TERN'`, which now
404s, while `ProductInfo` serves `data.tern.org.au` paths.

## ASF COG URL scheme + naming

```
https://data.tern.org.au/model-derived/slga/NationalMaps/SoilAndLandscapeGrid/{CODE}/{vN}/{CODE}_{upper}_{lower}_{COMPONENT}_F_AU_{TRN|NAT}_{N|C}_{date}.tif
```

`{CODE}` ∈ CLY, SLT, SND, CEC, PHC (directory `pHc`, filename case varies
between the store and the DAP mirror — keep the exact string from each
endpoint), SOC (extra `90m|30m` path level), BDW, AWC, ECE, NTO, PTO, AVP,
CFG, DUL, L15, DER, DES, SOF. `{COMPONENT}`: `EV` modelled value,
`05`/`95` confidence bounds, `EXT` extrapolation risk (PHC R2 has EXT).
Depths: `000_005, 005_015, 015_030, 030_060, 060_100, 100_200` cm — the same
six slabs SSURGO horizons rarely match, so treat as fixed depth intervals
(gNATSGO-style: never interpolate silently across slabs).

## Per-property units & storage (verified 2026-11-03 by opening each grid
through `clip_field(source="dap")`, keyless)

Units come from the keyless `ProductInfo` `Units` field; dtype/nodata/scale
from the opened raster (never assumed). Pixel value == physical unit: no
scale factor is used anywhere (all `scale=(1.0,) offset=(0.0,)`).

| Property (contract key) | Code | Units (ProductInfo) | storage as clipped | DOI (DAP record) |
|---|---|---|---|---|
| CLAY | CLY | % | float32, nodata NaN, tiled COG | https://doi.org/10.25919/hc4s-3130 |
| SILT | SLT | % | float32, nodata NaN, tiled COG (`Units` image tag: "Percent") | https://doi.org/10.25919/2ew1-0w57 |
| SAND | SND | % | float32, nodata NaN, tiled COG | https://doi.org/10.25919/rjmy-pa10 |
| CEC | CEC | meq/100g | **uint16, nodata 65535** (integer-valued meq/100g) | https://doi.org/10.25919/pkva-gf85 |
| PHCALCIUMCHLORIDE | PHC | pH (1:5 CaCl2, dimensionless — `Units` empty in ProductInfo) | float32, nodata NaN, tiled COG | https://doi.org/10.25919/7320-hw30 |
| CARBON | SOC | % | float32, nodata NaN, tiled COG | https://doi.org/10.25919/ejhm-c070 |
| BULKDENSITY | BDW | g/cm3 (whole-earth) | float32, nodata NaN, tiled COG | https://doi.org/10.25919/gxyn-pd07 |

Release-1 (2014-08-01 "NAT_C") national files on the DAP mirror are *striped*
float32, nodata `-9999.0`, 4.3 GB — they stream too (one full row per read),
just slower (~52 s for a 0.3°×0.2° window; typical field windows are a few
rows, so this stays minutes). Release-2 grids are tiled 256×256 and clip in
~3-9 s. The DAP `CARBON` mirror is the same-date `NAT_N` build (0.5 %C
offset vs the store's `TRN_N`), so for CARBON prefer the keyed COG when the
exact published product matters; `clip_field` reports the URL it used.

## Module contract (`src/australia_soil.py`)

- `PROPERTY_URLS` — dict keyed by the seven contract names (CLAY, SILT, SAND,
  CEC, PHCALCIUMCHLORIDE, CARBON, BULKDENSITY), each with `units`, `doi`, and
  `depths` → `0-5cm`/`5-15cm` entries carrying `cog` (canonical, keyed),
  `dap` (keyless), `dap_collection`, `dap_file_id`.
- `clip_field(bbox, out_path, prop, depth, api_key=None, source=None)` —
  `/vsicurl/` + `WarpedVRT` (output always EPSG:4326), tiled GeoTIFF out,
  returns the provenance dict: `source, property, code, attribute, depth,
  depth_m, units, source_kind, url, accessed_at, license, doi, dtype, nodata,
  scale, offset, res_deg, out_path, out_bytes, window, bbox, stats[]`.
  `api_key=None` falls back to `SLGA_TERN_API_KEY` env; `source` auto-picks
  `dap` (keyless) without a key, `cog` with one. With `source="cog"` and no
  key the raised `RuntimeError` quotes the live 401 probe + signup URL.
  With a key the header goes through GDAL's `GDAL_HTTP_HEADER_FILE` (mode
  0600 temp file), never in the URL.
- `asris_profiles_near(bbox, radius_km, cache_dir=None, providers=ANSIS_PROVIDERS)`
  — keyless ANSIS site catalogues (per-provider JSON cached; byte cost per
  provider in `_CATALOGUE_SIZES`, default providers ≈ 119 MB first run),
  returns a site-level `GeoDataFrame` in EPSG:4326 with columns `provider,
  site, project, state, first_year, last_year, entry_count, is_restricted,
  is_hydrated, property_codes, geometry`. These are the site *index*; full
  horizon/lab JSON needs an ANSIS account token (`Authorise` with
  username/password headers).
- `product_metadata(...)`, `ansis_catalogue_summary()`, `resolve_entry(...)`,
  `ANSIS_PROVIDERS`, `SOURCE_NAME`, `ACCESS_DATE` — constants/discovery
  helpers.

## Demo results (this machine, 2026-11-03, keyless, `source="dap"`)

Narrabri NSW bbox `(149.40, -31.10, 149.70, -30.90)` (360×240 px at 3"):

| Prop | mean | min–max | out bytes |
|---|---|---|---|
| CLAY 0-5 cm | 17.184 % | 10–48 | 524,694 |
| SILT 0-5 cm | 10.977 % | 7–23 | 524,694 |
| SAND 0-5 cm | 71.839 % | 35–83 | 524,694 |
| CEC 0-5 cm | 10.641 meq/100g | 5–42 | 262,556 |
| pH(CaCl2) 0-5 cm | 5.255 | 4.79–6.70 | 524,694 |
| CARBON 0-5 cm | 2.446 % | 1.27–3.86 | 524,694 |
| BULKDENSITY 0-5 cm | 1.316 g/cm3 | 1.20–1.47 | 524,694 |

Texture triad sums to 100.0 % (mean) — internal cross-check passes; values
plausible for the Narrabri red-earth/sandplain mosaic. Written clips
re-opened and means re-verified. A keyed store clip was impossible here
(no key present): the exact blocker is the documented store 401, surfaced as
a one-line error by `clip_field(source="cog")`.

`asris_profiles_near` near the same bbox (25 km): **626 site rows** (608
`NewSouthWales`, 18 `CSIRO_CSIS`) — matching an independent raw-JSON count.

## Gotchas

- The store gates *bytes* but not *listings*: HTML directory pages under
  `data.tern.org.au/model-derived/slga/...` browse keyless (HTTP 200) — do
  not mistake that for open data; every `.tif` GET is HTTP 401.
- `landscapes/slga/...` paths HTTP 301 → `model-derived/slga/...` — pin the
  final form (as in `PROPERTY_URLS`).
- DAP presigned links expire in 48 h and the `X-Amz-Signature` covers no
  Range, so `/vsicurl/` range-clipping works through them; re-resolve the
  `/data/{fileId}` URL whenever the cache is stale rather than pinning the
  presigned URL.
- `ProductInfo` `COGsPath` is canonical but `StagingPath` is absent in the
  current payload (all `None`) — older examples that drill via
  `StagingPath` pass `COGsPath` instead today (HTTP 400 error observed).
- PHC COG URLs: store path segment `pHc`, filename `PHC_*`; DAP mirror
  filename lowercase `pHc_*` — quote each list verbatim, they disagree by
  case (checked against both endpoints 2026-11-03).
- ASRIS-era profile data: the DAP collection `csiro:62790` ("Australian Soil
  Resource Information System Website", HTTP 200) contains **only** flyers,
  a .ppt, tech-spec PDFs, screenshots and .wmv demos — no profile dump. The
  collection description points to ANSIS (`http://ansis.net`) for the
  profile-level detail, which is why `asris_profiles_near` goes there.
- data.gov.au mirrors harvest metadata only; the one ZIP there for Clay R1
  (datagovau.s3.amazonaws.com/bioregionalassessments/… `OtherAUS_Soil_and_Landscape_Grid_National_Soil_Att…`)
  is the 4.3 GB R1 striped family — prefer the DAP file list for the same
  content with DOIs and per-band granularity.
- R2 grids quantize texture/CEC to whole numbers (min/max are integers):
  model skill, not a scale bug — documented by the product paper
  (https://doi.org/10.1071/SR20283).
- Rate limits are unpublished; keep one stream at a time when clipping many
  fields from the DAP mirror.

## Sources

- SLGA pages: https://esoil.io/TERNLandscapes/Public/Pages/SLGA/index.html (HTTP 200)
- API root & endpoints: as above, `RasterProductsAPI/{ProductInfo,QueryParameterValues,Drill}`
- R client (endpoint authority): https://github.com/AusSoilsDSM/SLGACloud (raw files HTTP 200)
- Product docs: https://aussoilsdsm.esoil.io/slga-version-2-products (HTTP 200; per-attribute pages HTTP 200)
- Covariate metadata DOI: https://doi.org/10.25919/jr32-yq58
- ANSIS API guide: https://ansis.net/wp-content/uploads/2026/06/ANSIS-API-guide-1.0.pdf (HTTP 200, read 2026-11-03)
- ASRIS retirement: https://data.csiro.au/collection/csiro:62790 (HTTP 200; "broke at the end of 2023 … June 2024")
