# Offline-fixture smoke test for ingest writer and provenance-schema changes

Use before re-syncing a skill mirror that changed raster/manifest/provenance writers (driver flips, new journal fields). Validates the full write path with zero network and zero touch on the production data root.

## Recipe

1. Interpreter: the pipeline venv `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python` — system python lacks numpy/rasterio/geopandas and the import dies misleadingly deep.
2. Synthetic root under scratch: `<root>/data-pipeline/growers/<g>/farms/<f>/` with `boundary/`, `manifests/`, and `fields/<slug>/boundary/`.
3. Three required seeds — the controlled errors name the exact expected path, read them instead of guessing:
   - farm boundary at `boundary/field_boundaries.geojson` (plural filename; a `--boundaries` CLI override does NOT substitute for the per-field canonical file),
   - per-field `fields/<slug>/boundary/field_boundary.geojson`,
   - `manifests/field-inventory.csv` with header `field_id,field_slug` (ingest of a raw boundary GeoJSON does not auto-create it).
4. Run e.g. `download_dem_terrain.py --grower <g> --farm <f> --offline-fixtures --allow-synthetic-fixtures --force`; require the final JSON `"status": "ok"` and exit 0 (run without `| tail` — the pipe's exit code is the tail's).
5. Assert every artifact class the change touched carries the new field: summary JSON, CSV header row, manifest asset records, source-reference payloads — plus side-effect markers (e.g. `synthetic_fixture=true` must survive a COG finalize, proving re-tag-after-finalize works through the real path, not just a unit probe).

GeoJSON pitfall: Polygon `coordinates` must be exactly `[[[x,y],…],…]`. One extra ring-wrap makes pyogrio warn `too many members in array` and load geometry as `None`, which surfaces layers deeper as `AttributeError: 'NoneType' object has no attribute 'is_empty'` — validate with `gpd.read_file(...).geometry.iloc[0]` before the ingest run.

## Adding serialized fields to persisted provenance

- New dataclass fields must carry a default **and** sit after every non-default field — `@dataclass(slots=True)` raises TypeError at import on non-default-after-default. Defaults also keep old JSON records loadable via `Dataclass(**json.loads(...))`: additive-with-default is the shipping path for journal schema changes.
- A `csv.DictWriter(fieldnames=list(row.keys()))` writer takes new columns from the row dict automatically — place a rel-column next to its absolute twin so column churn is adjacent, not scattered.
- Grep the module for every journaling site of the field string before patching: the same field can be written by several payload dicts in one file (both the field manifest and the source-reference writer journaled `source_paths`) — patch with unique context per site or uniform `replace_all`; a "2 matches" refusal is a hint you found a second writer, not an obstacle.
- Reporting step manifests (`*_render_*.json`) have a single chokepoint: `build_step_manifest` in `data-sources/farm-intelligence-reporting/src/pipeline.py` — an additive field there covers every farm/field render manifest at once. That package lives **inside the umbrella** (`my-farm-advisor/data-sources/...`), so payload/manifest lists must cover whole umbrella directories, not just top-level-looking skill names, or the reporting layer silently falls out of a vendored tree.
