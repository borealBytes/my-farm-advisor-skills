# Canada shared geodata: admin units, maturity parity, PC SAS tiles

How to give Canadian fields source parity with US fields in the shared data layer
(`shared/geoadmin/`, `shared/corn_maturity/`, `shared/soybean_maturity/`, `shared/weather/`).

## L1/L2 boundary source (province / census-division)

- **Primary: GADM 4.1** shapefile zip — pinned `https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_CAN_shp.zip` (~138 MB).
  `gadm41_CAN_1` = provinces/territories (matches StatCan exactly), `gadm41_CAN_2` = census divisions
  (~293 national, 53 Ontario) = the **county-role unit** for weather/maturity aggregation.
  License: free to use, redistribution restricted — cite GADM, don't rehost; determinism via pinned
  URL + sha256 journal.
- Statistics Canada standard-geography download endpoints can be unreachable (http:000 / CKAN hits 0)
  — don't burn time there; GADM is built from the same StatCan boundaries.
- geoBoundaries fallback: fetch from `media.githubusercontent.com/media/...`, **not**
  `raw.githubusercontent.com/.../raw/...` (the raw path returns LFS pointers/non-JSON).

GADM reading pitfalls (both bite silently):
- Shapefiles inside a zip can lose the `.prj` through `/vsizip` → `if frame.crs is None: frame = frame.set_crs("EPSG:4326")` before any `to_crs` (GADM ships WGS84 by definition).
- DBF name encoding disagrees between layers: 'Québec' can arrive as 'QuÃ©bec'. Never `map()` province names
  directly — run a lookup helper that tries the raw string and `s.encode('latin-1','ignore').decode('utf-8','ignore')`
  before mapping, and raise a named error listing unmapped names so builds fail closed.

## FIPS-slot encoding (so the US-keyed chain runs unchanged)

- `state_fips = "CA" + StatCan PRUID` (Ontario = `CA35`; PRUID map: ON 35, QC 24, MB 46, SK 47, AB 48, BC 59, …).
- `county_fips` = zero-padded census-division index within `GID_2`; always keep raw `gadm_gid_2` on the row.
- 4-char `CA35` codes are no-ops under the chain's `.str.zfill(2)`/`zfill(3)` normalizers, and non-contiguous
  exclusion lists (AK/HI/territories) don't touch them — that is why the weather→GDD→maturity chain needs no code change.
- **One combined `fips_lookup.parquet`**: each country layer also writes `fips_lookup_<country>.parquet`, and a
  `write_combined_fips_lookup()` merge (dedup on `fips`, keep-first) must run after any L2 build —
  `aggregate_weather_by_fips.py` and the maturity chain read the single combined file, so the last country
  built would otherwise silently overwrite and win.

## Maturity generation for Canadian units

Scope is a state-fips list in the maturity aggregation — add the CA province code(s) there
(`CA35` for Ontario; it is the corn belt's Canadian continuation, contiguous with MI/IA). Order per year:
`aggregate_weather_by_fips.py` → `calculate_gdd_by_fips.py` → `calculate_corn_rm_by_fips.py` →
`calculate_soybean_mg_by_fips.py` (~25 s/year/county-scope on the zarr backend).
Sanity anchors (verified): Ontario soy MG ~2.7–2.9 in the southwest matches OMAFRA guidance; ON corn RM
84–87 (Essex warmest, Waterloo cooler) sits below the Iowa mean (~106) — ordering must hold or the
GDD aggregation is broken.

## GDAL geojson guard

TIGER/GADM county geojsons contain multi-megabyte multipolygons that trip GDAL's single-feature object
guard on read. Set `os.environ["OGR_GEOJSON_MAX_OBJ_SIZE"] = "0"` before importing geopandas/pyogrio in
any script that reads `counties_*.geojson` (parquet side-files are the machine-read path anyway).

## Planetary Computer SAS signing (NASADEM / ALOS AW3D30 COG tiles)

PC-hosted Azure blob accounts disable anonymous container access — plain GET returns **409
`PublicAccessNotPermitted`** (not 403). Keyless fix, in this exact shape:

- `GET https://planetarycomputer.microsoft.com/api/sas/v1/sign` with query param **`href=<full tile URL>`**
  (sending `url=` returns a 422 `Field required`). Response carries the signed URL under **`href`**
  (older docs say `signed`) — accept either key.
- In a downloader: on 401/403/409 from the blob host, sign and re-request the signed URL; treat signing
  as best-effort fallback (never hard-fail a field on it — the resolver should fall through to the next
  candidate, e.g. Copernicus GLO-30).
- If the retry still logs the raw 409 after the patch is confirmed on disk, exercise the helper standalone
  (`importlib` exec_module of the script + direct call) before suspecting the wrapper — that separates
  "helper broken" from "attempt wrapper swallowed it"; the sign endpoint itself is stable.
