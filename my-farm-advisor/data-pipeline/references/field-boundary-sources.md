# Field boundary sources per country (real-farm-polygon playbook)

How to give any country's demo/production farm **real field polygons** (not
synthetic rectangles), deterministically. Two providers exist; pick by
coverage, then record which one you used in the boundary properties
(`source` = `usda_csb_fiboa` | `osm_farmland`).

## Repository contract (every boundary source must satisfy this)

| Artifact | Path | Notes |
|---|---|---|
| Farm-level boundaries | `<farm>/boundary/field_boundaries.geojson` | all fields, merge by `field_id` on re-run |
| Field-level boundary | `<farm>/fields/<field_slug>/boundary/field_boundary.geojson` | single feature |
| Inventory | `<farm>/manifests/field-inventory.csv` | columns `field_id,field_slug` |
| Provenance | `<farm>/manifests/<source>_fields_provenance.json` + shared `sha256_journal.json` | query, instance, accessed_at, response hash |
| Farm manifest | `<farm>/farm.json` | `country`/`state` here is the **fallback** when a boundary lacks the property |

**Routing keys off boundary properties**: `field_id, country, state, year,
area_ha_est, crop, area_acres` (+ `source`, and source-specific ids like
`osm_way_id`/`csb_id`). `country` selects the soil tier (soil/soil-routing.md).

## US — USDA CSB via FIBOA hosted GeoParquet (`download_csb_fields.py`)

`https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet`
(16.19M fields, CC-BY-4.0 / USDA public, crop + county per field).

* **Never download the file.** Prune with **pyarrow row-group statistics**
  (648 groups → read only candidates).
* **bbox columns are in the FILE CRS (NAD83 Albers meters), not WGS84.**
  Transform the lon/lat window with pyproj (CRS read live from the GeoParquet
  `geo` key/value metadata) before comparing — degrees-vs-meters silently
  matches zero rows. Physical leaf indices for stats:
  `bbox.xmin=7, bbox.ymin=8, bbox.xmax=9, bbox.ymax=10`.
* **DuckDB cannot filter this file**: dictionary-encoded struct child +
  filter pushdown → `INTERNAL Error: Vector::Reference ... STRUCT referenced
  DOUBLE`. Don't fight it; pyarrow path is the supported one.
* Area: projected CRS is equal-area, `poly.area/10000` is directly ha.
* `--bbox` on ALL ingest scripts is `S W N E`. Getting the order wrong scans
  the whole state — sanity-check county names against the farm's state before
  accepting fields.

## AU / ON / EU / anywhere OSM maps farms — Overpass (`download_osm_fields.py`)

Overpass QL: ways filtered on `landuse=farmland` within the bbox; returned polygons are closed. Measured coverage
(2026-11-03): NSW Wee Waa cotton country 27 fields ≥20 ha up to **1,233 ha**;
Chatham-Kent ON 62 fields ≥20 ha up to **593 ha**; Ontario coverage is much
better than US-Corn-Belt OSM (there, use CSB instead).

Hard-won Overpass rules:

1. **User-Agent header is mandatory** or every instance returns 406/HTML.
2. Query body must be `--data-urlencode "data=<QL>"` (or urllib
   `data=`-prefixed). A bare urlencode of the QL without the `data=` name
   yields an XHTML error page that looks like a server failure — don't blame
   the server for it.
3. The public pool genuinely saturates (502 "at capacity" across all six
   instances simultaneously). Correct behavior: rotate the six instances,
   sleep 40–60 s, repeat up to ~15 rounds. Succeeded after ~30 min of retries.
4. **Always journal the response** (sha256 + instance + QL) and support
   `--from-json` replay: reruns then cost nothing and stay byte-identical.

## Choosing sources for NEW countries (checklist)

1. **Cadastral/agency equivalent first** (like CSB): farm-block polygons from
   a national agency (AU: no free national equivalent; EU: LPIS via agencies;
   BR: CAR). Public + pre-datable before any submission cutoff → use it.
2. **OSM farmland density probe**: one Overpass bbox query, count ways
   ≥20 ha. If ≥10 you likely have usable mapping (AU/ON/EU yes; parts of US
   no). Use `download_osm_fields.py` verbatim.
3. **Imagery-derived** (Microsoft Field Boundaries / FTW) where agencies and
   OSM both fail — bigger download, still CC-BY.
4. Whatever the source: write the full repository contract above, then
   `download_soil.py` / weather / DEM / SoilGrids run unchanged — the routing
   only needs `country` on the boundary.
5. Terrain note: `download_dem_terrain.py` gates real fetching behind
   `--allow-live-downloads` (offline default is deliberate); global COG
   sources (Copernicus/NASADEM/ALOS) already cover any latitude incl.
   southern hemisphere.
6. Renderer note (`generate_soil_grid_maps.py`): apply SoilGrids Int16 scale
   factors ONLY when the source file is a `soilgrids_*` clip; ASF/CSB-derived
   and survey values are already true units. The guard must key off the
   SOURCE filename, not the re-projected temp clip (re-clip renames).
   numpy 2 traps hit here: `np.nanpercentile` on a MaskedArray ignores the
   mask and dies with `output array is read-only` — call `.compressed()`
   first; and raster nodata must be masked before computing vmin/vmax or the
   elevation colorbar stretches to −8000 m.
7. Renderers skip bands whose clips don't exist yet (partial panel warning),
   so rendering while an ingest job is still mid-farm yields a partial figure
   on purpose — rerun after ingest completes.
