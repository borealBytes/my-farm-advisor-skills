# DEM Terrain Index

Use this package for field-level DEM source policy, terrain product contracts, provenance, and later runtime pipeline integration. Start with the file that matches the task.

## Human and Routing Docs

- [SKILL.md](SKILL.md) - compact routing entrypoint for agents.
- [README.md](README.md) - full human guide covering sources, outputs, runtime policy, hydrology warnings, validation, and Open-Elevation limits.
- [PROVENANCE.md](PROVENANCE.md) - source records, provider rationale, license notes, and policy decisions.

## Contract and Resolver Code

- [`src/dem_terrain/terrain_contract.py`](src/dem_terrain/terrain_contract.py) - import-safe constants for runtime paths, product filenames, summary filenames, and manifest fields.
- [`src/dem_terrain/source_resolver.py`](src/dem_terrain/source_resolver.py) - import-safe source candidate records, adapter placeholders, ranking policy, DSM warnings, and coarse-resolution warnings.
- [`src/dem_terrain/package_validation.py`](src/dem_terrain/package_validation.py) - offline runtime package invariant checker for manifests, expected products, raster CRS/nodata/coverage, DSM warnings, fallback reasons, and tracked generated asset guardrails.
- [`src/dem_terrain/__init__.py`](src/dem_terrain/__init__.py) - package exports for contract and resolver consumers.

## Future Integration Points

- Runtime CLI: `data-pipeline/src/scripts/ingest/download_dem_terrain.py`, run from the installed data-pipeline source copy with `--context-meters 20` and explicit `--allow-live-downloads` only when live provider access is intended.
- Source adapters should implement discovery, download, cache, prepare, and provenance behavior without changing the documented source hierarchy.
- Raster processors should write runtime products named by `terrain_contract.py` and record source warnings from `source_resolver.py`.
- Ingest CLI work should write under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`, not inside this checkout.
- Validation should include the root repository command: `./scripts/validate.sh`.

## Output Boundary

Do not commit DEM `.tif` files, preview `.png` files, runtime manifests, runtime summaries, downloaded tiles, source caches, or example `output/` folders. Keep this package focused on reusable documentation, source policy, and import-safe contracts.
