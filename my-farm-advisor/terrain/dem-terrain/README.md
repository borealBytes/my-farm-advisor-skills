# DEM Terrain

This package documents the field-level DEM terrain contract for My Farm Advisor. It defines reusable routing docs, source provenance, output names, manifest fields, source resolver policy interfaces, and local raster clipping primitives. It does not discover providers, download DEM tiles, create runtime directories, or write generated assets during import.

Use it when a farm request needs elevation source selection, slope, aspect, hillshade, curvature, flow accumulation, terrain wetness, depression depth, relative elevation, erosion proxies, or DEM provenance. For quick navigation, start with [SKILL.md](SKILL.md) and [INDEX.md](INDEX.md).

## Runtime path contract

Generated and downloaded DEM assets are runtime-only and must stay out of Git. Downstream tasks should write under the external data-pipeline root, never inside this checkout:

| Purpose | Template |
| --- | --- |
| Field DEM root | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field_slug>/terrain/dem/` |
| Derived rasters | `fields/<field_slug>/derived/terrain/` |
| CSV summary | `fields/<field_slug>/derived/tables/dem_terrain_summary.csv` |
| JSON summary | `fields/<field_slug>/derived/tables/dem_terrain_summary.json` |
| Manifest | `fields/<field_slug>/manifests/dem_terrain_manifest.json` |
| Source cache | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/dem/<adapter>/` |

The contract module exposes these as string templates only. Importing `dem_terrain` is safe in a clean checkout and does not require `DATA_PIPELINE_DATA_ROOT` to exist.

## Runtime CLI

Normal farm pipeline initialization and add-field runs that invoke `scripts/run_farm_pipeline.py` include real DEM terrain by default. The data-pipeline runner calls `scripts/ingest/download_dem_terrain.py` immediately after field boundary download, passes live real-source permission through `--allow-live-downloads`, and writes runtime field terrain products before later soil, weather, CDL, satellite, and reporting steps. Use `--skip-dem-terrain` only as an explicit operator override when a run must omit DEM terrain. The `scripts/run_farm_pipeline.py --structure-test` path remains no-DEM and no-download.

The direct DEM CLI remains available for focused dry runs, package inspection, or operator-led terrain retries after `my-farm-advisor/data-pipeline/scripts/install.sh` copies the source tree into `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`. Run it from the runtime source copy, not from the skill checkout. Generated farm and field reports do not integrate terrain metrics in this change.

Temp-root install plus no-download dry run. This creates the runtime venv before invoking `.venv/bin/python`:

```bash
tmp_root="$(mktemp -d)"
export DATA_PIPELINE_DATA_ROOT="$tmp_root"
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_dem_terrain.py \
  --grower il-dekalb-grower \
  --farm dekalb-demo-farm \
  --context-meters 20 \
  --dry-run
```

Direct CLI dry-run is the safe planning path for focused checks: no raster writes, no DEM downloads, and no live provider services. Offline fixtures are a direct CLI test-only synthetic path. They are not grower validation, not real grower DEM evidence, and must not be cited in farm decisions. Synthetic fixture mode is unreachable from default farm-pipeline orchestration because `run_farm_pipeline.py` does not expose fixture flags. The CLI refuses `--offline-fixtures` unless the test operator also passes the deliberately named `--allow-synthetic-fixtures` override; fixture manifests and source references are marked with `synthetic_fixture=true`, `synthetic://...` source URLs, and warnings that the package is not real grower DEM evidence.

For a no-network full-package smoke in a temporary or otherwise disposable runtime root, use:

```bash
tmp_root="$(mktemp -d)"
export DATA_PIPELINE_DATA_ROOT="$tmp_root"
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_dem_terrain.py \
  --grower il-dekalb-grower \
  --farm dekalb-demo-farm \
  --context-meters 20 \
  --offline-fixtures \
  --allow-synthetic-fixtures \
  --limit-fields 1
```

Real grower verification must use cached real source DEM rasters or explicit live provider access. Default farm orchestration already supplies live real-source permission after field boundaries. Focused direct CLI runs still require `--allow-live-downloads`; without that flag, direct runtime mode fails safely when no cached source raster is available. Use `--dem-context-meters` and `--dem-source-policy` on `run_farm_pipeline.py` to tune the default path, or `--skip-dem-terrain` when the operator explicitly chooses to omit DEM terrain for a run.

## Raster clipping primitives

`src/dem_terrain/raster_processing.py` provides the v1 local raster primitive for already-available DEM tiles. It selects a projected analysis CRS from the field centroid, buffers the field in meters after projection, transforms the buffered bounds to source CRS for tile reads, mosaics source tiles in source CRS, reprojects once to the analysis CRS, and writes a compressed/tiled GeoTIFF through an atomic temporary file. High-latitude fields outside the UTM valid range use explicit polar stereographic fallbacks with warnings rather than silent CRS guessing.

Synthetic validation evidence for this primitive is stored as text/JSON summaries only under `.sisyphus/evidence/`; temporary GeoTIFF fixtures are written under `/tmp` or another disposable test root and should not be committed. Synthetic fixtures are test artifacts only and are never real grower DEM evidence.

## Source hierarchy

The source resolver policy prefers coverage, terrain surface quality, resolution, source precedence, date, direct no-auth access, and smaller downloads. Concrete discovery and download adapters are future work, but the documented hierarchy is already fixed for downstream tasks.

### United States

1. USGS TNMAccess 3DEP 1 meter direct GeoTIFF source.
2. Illinois Height Modernization Program and ISGS when the AOI intersects Illinois and the candidate is equal or better by resolution, recency, and surface type.
3. USGS 10 meter 3DEP fallback.
4. USGS 30 meter 3DEP fallback with a quality warning when field-level interpretation is limited.
5. Optional OpenTopography only when explicitly configured.

### Global

1. Registered national or regional provider, when configured for the AOI.
2. NASADEM global fallback.
3. Copernicus GLO-30 DSM fallback with DSM warning.
4. ALOS AW3D30 DSM fallback with DSM warning.
5. SRTM-compatible fallback when no better candidate exists.

See [PROVENANCE.md](PROVENANCE.md) for provider rationale, source notes, and Open-Elevation policy.

## Product filenames

The required runtime products are:

- `dem_source_reference.json`
- `dem_clipped.tif`
- `dem_conditioned.tif`
- `slope_degrees.tif`
- `slope_percent.tif`
- `aspect_degrees.tif`
- `hillshade.tif`
- `profile_curvature.tif`
- `planform_curvature.tif`
- `tpi.tif`
- `tri.tif`
- `flow_direction.tif`
- `flow_accumulation.tif`
- `topographic_wetness_index.tif`
- `depression_depth.tif`
- `relative_elevation.tif`
- `erosion_proxy.tif`

Summary outputs are `dem_terrain_summary.csv` and `dem_terrain_summary.json`. The manifest filename is `dem_terrain_manifest.json`.

These outputs are runtime products, not committed examples. Later raster and ingest tasks should write them under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline` using the path templates in [`src/dem_terrain/terrain_contract.py`](src/dem_terrain/terrain_contract.py).

## Manifest schema

The manifest must include these top-level fields exactly:

`run_id`, `field_id`, `field_slug`, `buffer_meters`, `analysis_crs`, `selected_source`, `candidate_sources`, `fallback_reason`, `surface_type`, `source_resolution_m`, `source_horizontal_crs`, `source_vertical_datum`, `source_urls`, `license`, `citation`, `acquisition_date`, `publication_date`, `processing_parameters`, `warnings`, `outputs`, `checksums`, `generated_at`.

The `outputs` records should be STAC-like where useful. Each asset should include an `href`, media `type`, `roles`, projection metadata such as `proj:epsg` or `proj:wkt2`, raster metadata such as nodata, data type, unit, and resolution, file size and checksum, and source/provenance links. DSM or mixed-surface fallbacks must set warning fields so farm-terrain analysis is not misrepresented as bare-earth DTM when vegetation or structures may affect elevations.

## Package invariant validation

`src/dem_terrain/package_validation.py` validates an existing runtime `dem_terrain_manifest.json` without provider access. It checks the manifest against the required fields in `terrain_contract.py`, confirms all contract products and summaries are listed and present, inspects GeoTIFF CRS/nodata ratios when `rasterio` is available, verifies `dem_clipped.tif` covers the field boundary plus the manifest buffer when `boundary/field_boundary.geojson` is available, checks DSM warning and fallback-reason consistency, and guards against tracked generated DEM assets.

Run it against a temp or external runtime package, not against committed generated outputs:

```bash
python my-farm-advisor/terrain/dem-terrain/src/dem_terrain/package_validation.py \
  /absolute/runtime/root/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/manifests/dem_terrain_manifest.json
```

## Source resolver policy

`dem_terrain.source_resolver` defines stdlib-only adapter interfaces, source candidate records, provenance records, ranking configuration, and deterministic selection helpers. The placeholder adapter classes are safe to instantiate without credentials or network access. They expose responsibilities equivalent to `discover(aoi)`, `rank(candidates)`, `download(candidate, cache)`, `prepare(candidate)`, and `provenance(candidate)`, but real provider discovery, download, and raster preparation are reserved for later adapter tasks.

Candidate provenance must preserve adapter id/name, source name, source and metadata URLs, license, citation, region policy, country/region hints, resolution in meters, surface type (`DTM`, `DEM`, `DSM`, or `unknown`), acquisition/publication dates, coverage score, direct/no-auth status, auth requirements, estimated download size, warnings, and fallback reason.

The deterministic ranking policy is:

1. Prefer candidates with valid AOI coverage.
2. Prefer bare-earth or terrain-like surfaces (`DTM`, then `DEM`) over `DSM`.
3. Prefer finer resolution.
4. Apply source precedence for equal-quality candidates.
5. Prefer newer acquisition or publication dates.
6. Prefer direct no-auth root sources.
7. Prefer smaller estimated downloads.

For U.S. fields, source precedence is USGS TNM 3DEP 1m, then Illinois ILHMP/ISGS when the AOI intersects Illinois and that candidate is equal or better by resolution, recency, and surface type, then USGS 10m, USGS 30m, and optional OpenTopography only when explicitly configured. For global fields, precedence is registered national/regional provider, NASADEM, Copernicus GLO-30 DSM, ALOS AW3D30 DSM, then SRTM-compatible fallback.

The resolver must not fail solely because only 30m coverage exists. It should still return the best raster candidate with a quality warning. If a DSM fallback wins, the selection must include a warning that elevations may include vegetation, buildings, or other above-ground objects and must not be represented as bare-earth DTM.

## Hydrology and interpretation warnings

Hydrology products need careful labeling. Raw clipped DEMs and conditioned DEMs are separate outputs, so a downstream process must not silently replace the source DEM with a filled or breached raster. Flow direction, flow accumulation, wetness index, depression depth, and erosion proxy products should record the conditioning method in the manifest.

If a hydrology backend is unavailable, downstream tasks should either skip hydrology-dependent outputs with structured warnings or generate only products that can be computed safely. DSM fallbacks need explicit warnings because vegetation, buildings, and other above-ground objects can distort slope, flow, depression, wetness, and erosion interpretation.

## Open-Elevation rule

Hosted Open-Elevation API is not used by this skill. Do not call the hosted service for discovery, ranking, or elevation sampling.

Open-Elevation GitHub materials are research-only. The bundled data acquisition is based on CGIAR SRTM 250m, which is too coarse for the field-level DEM terrain target, and the GPL-2.0 code must not be copied, vendored, or partially imported into this repository.

## Git and asset boundary

Do not commit generated DEM `.tif`, preview `.png`, downloaded DEM source tiles, cache folders, runtime manifests, or runtime summaries. This package is the schema and naming contract that later source resolvers, adapters, raster processors, and validators will consume.

## Validation

After documentation or routing changes, run from the repository root:

```bash
./scripts/validate.sh
```

For this documentation package, required files are `SKILL.md`, `README.md`, `PROVENANCE.md`, and `INDEX.md`. Keep those files present before adding adapter or raster code.
