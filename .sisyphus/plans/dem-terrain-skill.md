# My Farm Advisor DEM Terrain Skill

## TL;DR
> **Summary**: Build a reusable My Farm Advisor DEM terrain skill and data-pipeline integration that retrieves the best available root DEM/lidar source for each field, clips at least 20m beyond the field in projected meters, generates full DEM-derived agriculture products, and validates on the northern Illinois runtime fields.
> **Deliverables**: new `my-farm-advisor/terrain/dem-terrain` skill; DEM source resolver/adapters; runtime ingest script; path helpers; raw/clipped/conditioned DEM outputs; 10 derived terrain rasters; PNG previews; CSV/JSON summaries; provenance manifests; validation/smoke docs.
> **Effort**: XL
> **Parallel**: YES - 5 waves
> **Critical Path**: Task 1 → Task 2 → Task 3 → Task 6 → Task 10 → Final Verification

## Context
### Original Request
Create a best-in-class reusable My Farm Advisor digital elevation map skill for the data pipeline. For every field boundary, download the highest-quality available DEM, expand context by about 20m outside the field, run against the northern Illinois runtime fields, produce raw DEMs and 10 farmer-useful transformations, and make the skill reusable through the existing runtime source-copy pipeline.

### Interview Summary
- Hosted Open-Elevation API must not be used as a runtime dependency; its GitHub repo can inform upstream dataset acquisition only.
- Source priority must be best-in-class: 1m lidar where possible, then best available regional/national/global fallback.
- V1 must include all U.S. regions plus global adapters, not just northern Illinois.
- Illinois ILHMP/ISGS adapter is in v1.
- Per-field output package must be full: raw/clipped DEM, conditioned DEM, derived rasters, PNG previews, CSV/JSON summaries, and provenance.
- Hydrologic conditioning is in v1 because the outputs should support broad agricultural use.

### Metis Review (gaps addressed)
- Added exact source precedence, tie-breakers, output names, manifest schema, runtime paths, failure behavior, cache policy, CRS policy, hydrologic conditioning rules, and non-GPL guardrails.
- Defined acceptance criteria as commands and invariant checks, not visual inspection.
- Kept v1 broad but bounded: no full watershed modeling, stream burning, culvert inference, or state-by-state lidar catalogs beyond generic USGS and Illinois ILHMP.

## Work Objectives
### Core Objective
Deliver a reusable terrain/DEM data product workflow that selects the best available DEM source for each field, writes reproducible runtime-only artifacts, and gives farmers/growers terrain layers useful for drainage, erosion, machinery planning, sampling zones, and land understanding.

### Deliverables
- `my-farm-advisor/terrain/dem-terrain/SKILL.md`
- `my-farm-advisor/terrain/dem-terrain/README.md`
- `my-farm-advisor/terrain/dem-terrain/PROVENANCE.md`
- `my-farm-advisor/terrain/dem-terrain/INDEX.md`
- `my-farm-advisor/terrain/dem-terrain/src/dem_terrain/` package
- `my-farm-advisor/data-pipeline/src/scripts/ingest/download_dem_terrain.py`
- Path helper additions in `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py`
- Optional orchestration integration in `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py`
- Runtime-only outputs under each field: `terrain/dem/`, `derived/terrain/`, `derived/tables/`, `manifests/`

### Definition of Done (verifiable conditions with commands)
- `bash -n scripts/validate.sh && ./scripts/validate.sh` exits `0`.
- `git status --short` shows no generated DEM rasters, previews, runtime caches, or downloaded files.
- Python syntax check compiles all new Python files using `compile()` without writing bytecode.
- Runtime smoke against `.my-farm-advisor-runtime` processes the 10 northern Illinois fields or, if live services are unavailable, produces structured failure manifests and passes offline fallback/mock validation.
- Each successful field has one clipped DEM, one conditioned DEM, at least 10 derived rasters, PNG previews, field summary CSV/JSON, and provenance manifest.

### Must Have
- Buffer in projected meters, default `20`, configurable by CLI.
- Native/root DEM retrieval where possible; no hosted Open-Elevation dependency.
- U.S. source precedence: USGS 3DEP 1m via TNMAccess direct GeoTIFF → Illinois ILHMP/ISGS if Illinois and better/newer/resolution wins → USGS 3DEP 10m → USGS 3DEP 30m → optional OpenTopography convenience only when configured.
- Global source precedence: national/regional plugin if available → NASADEM 30m → Copernicus GLO-30 DSM → ALOS AW3D30 DSM → SRTM-compatible fallback if needed.
- Tie-breakers: bare-earth DTM/DEM beats DSM; finer resolution beats coarser; newer acquisition/publication beats older when resolution/surface type are equal; direct no-auth root source beats quota/API-key proxy when quality is equal.
- Hydrologic conditioning produces separate products and never silently replaces raw/clipped DEM.
- Provenance manifest records adapter, source URL, provider metadata, license/access note, resolution, CRS, vertical datum if known, surface type (`DTM|DEM|DSM|unknown`), fallback reason, checksums/file sizes, processing parameters, and warnings.

### Must NOT Have
- No generated/downloaded DEM artifacts committed to Git.
- No GPL-2.0 Open-Elevation code copied or vendored.
- No hosted Open-Elevation API use.
- No buffering in geographic degrees.
- No silent DSM/DTM mixing without manifest warning.
- No full hydrologic watershed modeling, culvert inference, stream burning, or drainage engineering claims in v1.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after + repo validator + syntax checks + runtime smoke; no repo-wide test framework migration.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
Wave 1: Task 1 foundation contracts; Task 2 source resolver contracts; Task 3 skill docs/provenance.
Wave 2: Task 4 USGS adapters; Task 5 Illinois adapter; Task 6 global adapters; Task 7 raster processing primitives.
Wave 3: Task 8 terrain derivatives; Task 9 runtime path/output integration; Task 10 data-pipeline ingest CLI.
Wave 4: Task 11 orchestration/docs/examples; Task 12 validation/smoke harness.
Wave 5: Task 13 northern Illinois runtime validation and fallback validation.

### Dependency Matrix (full, all tasks)
- 1 blocks 2, 7, 8, 9, 10, 12, 13.
- 2 blocks 4, 5, 6, 10, 13.
- 3 can run after 1 starts; blocks final validation.
- 4, 5, 6 block 10 and 13.
- 7 blocks 8 and 10.
- 8 blocks 10 and 13.
- 9 blocks 10 and 13.
- 10 blocks 11, 12, 13.
- 11 and 12 block 13.
- 13 blocks final verification.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → deep, deep, writing.
- Wave 2 → 4 tasks → deep, deep, deep, deep.
- Wave 3 → 3 tasks → deep, quick, deep.
- Wave 4 → 2 tasks → writing, deep.
- Wave 5 → 1 task → unspecified-high.

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Define DEM runtime contract, output schema, and manifest schema

  **What to do**: Create the canonical DEM terrain contract in the new skill docs and implementation package constants. Define exact runtime directories and filenames:
  - Field root: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field_slug>/terrain/dem/`
  - Derived rasters: `fields/<field_slug>/derived/terrain/`
  - Tables: `fields/<field_slug>/derived/tables/dem_terrain_summary.csv` and `dem_terrain_summary.json`
  - Manifest: `fields/<field_slug>/manifests/dem_terrain_manifest.json`
  - Source cache: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/dem/<adapter>/`
  - Product names: `dem_source_reference.json`, `dem_clipped.tif`, `dem_conditioned.tif`, `slope_degrees.tif`, `slope_percent.tif`, `aspect_degrees.tif`, `hillshade.tif`, `profile_curvature.tif`, `planform_curvature.tif`, `tpi.tif`, `tri.tif`, `flow_direction.tif`, `flow_accumulation.tif`, `topographic_wetness_index.tif`, `depression_depth.tif`, `relative_elevation.tif`, `erosion_proxy.tif`.
  Define the manifest schema fields exactly: `run_id`, `field_id`, `field_slug`, `buffer_meters`, `analysis_crs`, `selected_source`, `candidate_sources`, `fallback_reason`, `surface_type`, `source_resolution_m`, `source_horizontal_crs`, `source_vertical_datum`, `source_urls`, `license`, `citation`, `acquisition_date`, `publication_date`, `processing_parameters`, `warnings`, `outputs`, `checksums`, `generated_at`.
  **Must NOT do**: Do not generate actual DEM outputs; do not commit runtime data.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-cutting schema affects all later tasks.
  - Skills: [] - no extra skill needed.
  - Omitted: [`workers-best-practices`] - not a Cloudflare task.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 2,7,8,9,10,12,13 | Blocked By: none

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` - canonical farm/field path helpers.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/manifest.py` - JSON/JSONL helper conventions.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/naming.py` - slug conventions.
  - Policy: `AGENTS.md` - generated/downloaded runtime assets must not be tracked.

  **Acceptance Criteria**:
  - [ ] `python - <<'PY'
from pathlib import Path
for p in Path('my-farm-advisor/terrain/dem-terrain').rglob('*.py'):
    compile(p.read_text(), str(p), 'exec')
print('compile ok')
PY` exits `0` after created files exist.
  - [ ] Manifest schema is documented in `my-farm-advisor/terrain/dem-terrain/README.md` and implemented as a constant or typed helper.
  - [ ] No files under `.my-farm-advisor-runtime/` are modified by this task.

  **QA Scenarios**:
  ```
  Scenario: Contract names are deterministic
    Tool: Bash
    Steps: Run a Python one-liner importing the contract constants and print expected filenames.
    Expected: Output includes `dem_clipped.tif`, `dem_conditioned.tif`, and all 10+ derived product names exactly once.
    Evidence: .sisyphus/evidence/task-1-contract.txt

  Scenario: Generated asset guardrail
    Tool: Bash
    Steps: Run `git status --short` after task.
    Expected: No `.tif`, `.png`, runtime cache, or generated terrain files appear.
    Evidence: .sisyphus/evidence/task-1-git-status.txt
  ```

  **Commit**: YES | Message: `feat(dem): define terrain output contract` | Files: [`my-farm-advisor/terrain/dem-terrain/**`]

- [x] 2. Implement source resolver interfaces and ranking policy

  **What to do**: Add source adapter abstractions under `my-farm-advisor/terrain/dem-terrain/src/dem_terrain/` with methods equivalent to `discover(aoi)`, `rank(candidates)`, `download(candidate, cache)`, `prepare(candidate)`, and `provenance(candidate)`. Implement deterministic precedence:
  - U.S.: USGS TNM 1m → Illinois ILHMP/ISGS when field intersects Illinois and candidate is equal/better by resolution/recency/surface type → USGS 10m → USGS 30m → optional OpenTopography only if configured.
  - Global: registered national/regional provider → NASADEM → Copernicus GLO-30 DSM → ALOS AW3D30 DSM → SRTM-compatible fallback.
  Ranking order within candidates: valid coverage > DTM/DEM over DSM > finer resolution > newer acquisition/publication > direct no-auth root source > smaller required download. Include minimum acceptable output behavior: never fail solely because only 30m exists; produce output with `quality_warning` unless no raster source can cover AOI.
  **Must NOT do**: Do not call hosted Open-Elevation API; do not copy Open-Elevation GPL code.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core architecture and deterministic precedence.
  - Skills: [] - no extra skill needed.
  - Omitted: [`scrapling-official`] - research is complete; implementation should not scrape sites at runtime except documented APIs.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 4,5,6,10,13 | Blocked By: 1

  **References**:
  - External: `https://tnmaccess.nationalmap.gov/api/v1/products` - USGS TNMAccess product API.
  - External: `https://www.usgs.gov/3d-elevation-program/about-3dep-products-services` - USGS 3DEP product/resolution facts.
  - External: `https://clearinghouse.isgs.illinois.edu/data/elevation/illinois-height-modernization-ilhmp` - Illinois ILHMP source.
  - External: `https://registry.opendata.aws/copernicus-dem/` - Copernicus DEM COG source.
  - External: Open-Elevation GitHub is research-only; its CGIAR SRTM 250m scripts must not be copied.

  **Acceptance Criteria**:
  - [ ] Unit-like Python smoke can instantiate all adapter classes without network calls.
  - [ ] Ranking smoke with mocked candidates selects 1m DTM over 30m DSM and emits DSM warning when DSM wins by fallback.
  - [ ] Source resolver docs explicitly say hosted Open-Elevation is not used.

  **QA Scenarios**:
  ```
  Scenario: US ranking happy path
    Tool: Bash
    Steps: Run adapter ranking smoke with mocked USGS 1m, USGS 10m, Copernicus 30m candidates.
    Expected: selected_source.adapter == `usgs_tnm_3dep_1m`; no fallback warning.
    Evidence: .sisyphus/evidence/task-2-us-ranking.json

  Scenario: DSM fallback warning
    Tool: Bash
    Steps: Run adapter ranking smoke with only Copernicus and ALOS DSM candidates.
    Expected: selected candidate exists and manifest warnings include `DSM surface model may include vegetation/buildings`.
    Evidence: .sisyphus/evidence/task-2-dsm-warning.json
  ```

  **Commit**: YES | Message: `feat(dem): add source resolver policy` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`, `my-farm-advisor/terrain/dem-terrain/README.md`]

- [x] 3. Create reusable skill documentation and provenance

  **What to do**: Add route-focused `SKILL.md`, human `README.md`, `PROVENANCE.md`, and `INDEX.md` for `my-farm-advisor/terrain/dem-terrain`. Update the umbrella `my-farm-advisor/SKILL.md` and relevant README/INDEX only if existing routing requires it. Docs must explain when to invoke the DEM skill, source hierarchy, runtime-only asset policy, output products, hydrology warnings, and validation command. Record all data-provider references and Open-Elevation research decision in `PROVENANCE.md`.
  **Must NOT do**: Do not duplicate long manuals in `SKILL.md`; keep it a compact router.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation/provenance task.
  - Skills: [] - no extra skill needed.
  - Omitted: [`scientific-writing`] - this is technical repo documentation, not manuscript prose.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: final validation | Blocked By: 1

  **References**:
  - Policy: `AGENTS.md` - new skills need `SKILL.md`, `README.md`, `PROVENANCE.md`.
  - Pattern: existing `my-farm-advisor/*/SKILL.md` files - keep compact route-focused style.
  - Pattern: `my-farm-advisor/docs/GEODATA.md` - runtime payload policy.

  **Acceptance Criteria**:
  - [ ] New skill root has required docs.
  - [ ] `SKILL.md` is route-focused and references README/INDEX for details.
  - [ ] `PROVENANCE.md` lists USGS, ILHMP/ISGS, NASADEM, Copernicus, ALOS, OpenTopography optional, and Open-Elevation research-only rationale.

  **QA Scenarios**:
  ```
  Scenario: Required skill files present
    Tool: Bash
    Steps: Run `test -f` for SKILL.md, README.md, PROVENANCE.md, INDEX.md.
    Expected: all files exist.
    Evidence: .sisyphus/evidence/task-3-files.txt

  Scenario: No generated asset docs violation
    Tool: Bash
    Steps: Run `./scripts/validate.sh` after docs are added.
    Expected: validator exits 0 or only unrelated pre-existing warnings.
    Evidence: .sisyphus/evidence/task-3-validate.txt
  ```

  **Commit**: YES | Message: `docs(dem): add terrain skill documentation` | Files: [`my-farm-advisor/terrain/dem-terrain/**`, `my-farm-advisor/SKILL.md` if routed]

- [x] 4. Implement USGS TNMAccess and USGS seamless adapters

  **What to do**: Implement `usgs_tnm.py` adapter. Query TNMAccess products by buffered WGS84 bbox for datasets `Digital Elevation Model (DEM) 1 meter`, `1/3 arc-second DEM`, and `1 arc-second DEM` with GeoTIFF output. Parse `downloadURL`, title/source ID, publication/update dates, metadata URL, bbox, and resolution. Download to shared runtime cache with atomic temp file + checksum/file-size record. Implement tile mosaic/crop handoff, but keep raster processing in Task 7 helpers. Include retries/backoff, partial-download cleanup, and structured error candidates.
  **Must NOT do**: Do not hardcode northern Illinois field IDs; do not use OpenTopography as primary path.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: live API adapter with fallback and provenance.
  - Skills: [] - no extra skill needed.
  - Omitted: [`ddgs`] - no more web research required.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10,13 | Blocked By: 2

  **References**:
  - External: `https://www.usgs.gov/faqs/there-api-accessing-national-map-data` - TNM API access.
  - External: `https://data.usgs.gov/datacatalog/data/USGS:77ae0551-c61e-4979-aedd-d797abdcde0e` - USGS 1m DEM metadata.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/ingest/download_cdl.py` - download/cache pattern.

  **Acceptance Criteria**:
  - [ ] Mocked TNM JSON discovery returns ranked candidates with direct URLs and provenance.
  - [ ] Network-disabled discovery failure returns structured adapter error, not traceback.
  - [ ] Live call is optional and guarded by CLI/env flag in validation docs.

  **QA Scenarios**:
  ```
  Scenario: Mock USGS 1m discovery
    Tool: Bash
    Steps: Run adapter smoke with saved mock TNMAccess JSON for a DeKalb bbox.
    Expected: candidate includes adapter `usgs_tnm_3dep_1m`, `download_url`, `source_resolution_m <= 1.5`.
    Evidence: .sisyphus/evidence/task-4-usgs-mock.json

  Scenario: USGS outage fallback error
    Tool: Bash
    Steps: Run adapter with invalid endpoint override.
    Expected: structured error candidate contains adapter name, endpoint, and retry/failure reason; process exits controlled nonzero only if no fallback adapter is available.
    Evidence: .sisyphus/evidence/task-4-usgs-error.json
  ```

  **Commit**: YES | Message: `feat(dem): add USGS DEM adapters` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`]

- [x] 5. Implement Illinois ILHMP/ISGS adapter

  **What to do**: Implement `illinois_ilhmp.py` adapter for Illinois fields. Start with a maintained provider catalog file or metadata helper under the skill that references ISGS ILHMP county services/download metadata without vendoring large data. For v1, support discovery for northern Illinois/DeKalb via documented endpoints or metadata records; if full programmatic county download is too bulky, adapter must return `available_but_manual_or_service_limited` candidates with provenance and allow fallback to USGS. If a usable ImageServer/export or tile URL is identified, implement download/export with size guards.
  **Must NOT do**: Do not download full county archives during default validation; do not commit county data.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: source-specific integration and careful fallback.
  - Skills: [] - no extra skill needed.
  - Omitted: [`scrapling-official`] - runtime should use documented endpoints/catalog records, not scraping pages.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10,13 | Blocked By: 2

  **References**:
  - External: `https://clearinghouse.isgs.illinois.edu/data/elevation/illinois-height-modernization-ilhmp` - Illinois elevation catalog.
  - Runtime fixture: `.my-farm-advisor-runtime/data-pipeline/growers/northern-il-grower/farms/dekalb-ten-field-test/manifests/field-inventory.csv` - test fields.
  - Policy: `ASSET_POLICY.md` - no generated/downloaded assets.

  **Acceptance Criteria**:
  - [ ] Adapter identifies Illinois AOIs and DeKalb county context from geometry/bbox.
  - [ ] Adapter never downloads full county archive unless explicit flag is set.
  - [ ] If ILHMP candidate cannot be directly fetched, fallback reason is recorded and USGS remains selected.

  **QA Scenarios**:
  ```
  Scenario: Illinois AOI candidate discovery
    Tool: Bash
    Steps: Run ILHMP adapter smoke using a DeKalb bbox fixture.
    Expected: candidate list includes Illinois/DeKalb provenance or controlled service-limited candidate; no large download occurs.
    Evidence: .sisyphus/evidence/task-5-ilhmp-discovery.json

  Scenario: Size guard blocks county archive
    Tool: Bash
    Steps: Run adapter with default settings against a county-level archive candidate.
    Expected: manifest/fallback reason says blocked by size/default policy; no `.zip`, `.tif`, or archive appears in repo.
    Evidence: .sisyphus/evidence/task-5-size-guard.txt
  ```

  **Commit**: YES | Message: `feat(dem): add Illinois ILHMP adapter` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`, `my-farm-advisor/terrain/dem-terrain/PROVENANCE.md`]

- [x] 6. Implement global DEM adapters

  **What to do**: Implement adapters for NASADEM, Copernicus GLO-30, and ALOS AW3D30 using direct root datasets or STAC/COG catalogs. Adapter behavior may use provider metadata and mocked discovery in tests, but production code must support real AOI tile resolution. NASADEM is preferred over DSMs where available; Copernicus/ALOS must set `surface_type=DSM` and warnings. Include optional Planetary Computer/STAC helper only if dependency burden is acceptable; otherwise implement minimal STAC HTTP client.
  **Must NOT do**: Do not require Earthdata/JAXA auth for default smoke tests; do not commit tiles.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: multiple providers and licensing/provenance.
  - Skills: [] - no extra skill needed.
  - Omitted: [`cloudflare`] - not deployment/infrastructure.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10,13 | Blocked By: 2

  **References**:
  - External: `https://registry.opendata.aws/copernicus-dem/` - Copernicus COG bucket.
  - External: `https://copernicus-dem-30m.s3.amazonaws.com/readme.html` - tile layout.
  - External: `https://planetarycomputer.microsoft.com/api/stac/v1/collections/nasadem` - NASADEM STAC.
  - External: `https://planetarycomputer.microsoft.com/api/stac/v1/collections/alos-dem` - ALOS STAC.

  **Acceptance Criteria**:
  - [ ] Mock global AOI ranking selects NASADEM before Copernicus/ALOS when all cover the field.
  - [ ] Copernicus/ALOS candidates include DSM warnings.
  - [ ] Global adapter smoke can generate tile URLs or STAC asset references for a non-U.S. bbox without downloading large assets by default.

  **QA Scenarios**:
  ```
  Scenario: Global fallback ranking
    Tool: Bash
    Steps: Run resolver with mocked France/Brazil candidates for NASADEM, Copernicus, ALOS.
    Expected: NASADEM selected where covered; DSM warning absent for NASADEM and present when NASADEM unavailable.
    Evidence: .sisyphus/evidence/task-6-global-ranking.json

  Scenario: No-auth smoke avoids large download
    Tool: Bash
    Steps: Run adapter discovery in dry-run mode for a small non-U.S. bbox.
    Expected: prints candidate metadata and planned URLs/assets; no raster file is downloaded.
    Evidence: .sisyphus/evidence/task-6-dry-run.txt
  ```

  **Commit**: YES | Message: `feat(dem): add global DEM adapters` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`, `my-farm-advisor/terrain/dem-terrain/PROVENANCE.md`]

- [x] 7. Implement raster clipping, CRS, COG, and cache primitives

  **What to do**: Add raster utilities to project field geometries to local metric CRS, buffer by configured meters, transform bounds to source CRS, mosaic multiple tiles, clip to analysis buffer, reproject once, preserve nodata, write compressed/tiled GeoTIFF or COG-compatible output, compute checksums/file sizes, and clean partial files atomically. Analysis CRS selection: use UTM zone from field centroid unless polar/high-latitude requires documented fallback. Vertical datum is recorded but not transformed in v1 unless adapter provides safe conversion; manifest warns when datums differ.
  **Must NOT do**: Do not buffer in EPSG:4326 degrees; do not repeatedly resample.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: geospatial correctness and edge cases.
  - Skills: [] - no extra skill needed.
  - Omitted: [`pandas-pro`] - raster/geometry work, not DataFrame-heavy.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 8,10,13 | Blocked By: 1

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/satellite_imagery.py` - raster clipping/reprojection helpers.
  - Dependency: `my-farm-advisor/data-pipeline/requirements.txt` - existing rasterio/geopandas stack.
  - Pattern: `my-farm-advisor/soil/ssurgo-soil/src/ssurgo_workflows.py` - clipped field packages.

  **Acceptance Criteria**:
  - [ ] Tiny synthetic raster fixture clips to a buffered polygon and output bounds cover field + 20m.
  - [ ] CRS smoke confirms output CRS is projected, not EPSG:4326, for terrain derivatives.
  - [ ] Multi-tile synthetic mosaic produces one clipped raster with expected nodata handling.

  **QA Scenarios**:
  ```
  Scenario: 20m buffer in projected meters
    Tool: Bash
    Steps: Run synthetic raster/field clip smoke and inspect output bounds/manifest.
    Expected: manifest `buffer_meters == 20`, `analysis_crs` is projected, output covers buffered geometry.
    Evidence: .sisyphus/evidence/task-7-buffer.json

  Scenario: Tile-boundary mosaic
    Tool: Bash
    Steps: Run synthetic two-tile mosaic smoke with field crossing tile seam.
    Expected: one clipped raster is produced; nodata ratio below configured threshold; no seam exception.
    Evidence: .sisyphus/evidence/task-7-mosaic.txt
  ```

  **Commit**: YES | Message: `feat(dem): add raster processing primitives` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`]

- [x] 8. Implement hydrologic conditioning and agriculture terrain derivatives

  **What to do**: Implement derived products from `dem_clipped.tif`, writing `dem_conditioned.tif` separately. Conditioning default: breach/fill depressions with conservative parameters if dependency available; if hydrology backend is unavailable, produce unconditioned derivatives and manifest `conditioning_status=skipped_backend_unavailable`. Generate at least 10 derived rasters excluding raw/clipped DEM: slope degrees, slope percent, aspect, hillshade, profile curvature, planform curvature, TPI, TRI/roughness, flow direction, flow accumulation, TWI, depression depth, relative elevation, erosion proxy. Generate PNG previews and CSV/JSON summaries with min/max/mean/percentiles/area by risk class.
  **Must NOT do**: Do not claim engineered drainage design; label flow/wetness/ponding as advisory proxies.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: math/geospatial derivative correctness.
  - Skills: [] - no extra skill needed.
  - Omitted: [`scientific-critical-thinking`] - plan already defines limits; implementation task.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 10,13 | Blocked By: 7

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/satellite_imagery.py` - NDVI derivation/write single-band raster style.
  - External: WhiteboxTools wetness index definition `Ln(A / tan(slope))` from research.
  - Metis directive: conditioning is derived output, not raw DEM replacement.

  **Acceptance Criteria**:
  - [ ] Synthetic sloped DEM produces finite slope/aspect/hillshade outputs.
  - [ ] Flat DEM does not crash TWI/flow/depression outputs; manifest records limited terrain warning.
  - [ ] Summary JSON includes `slope_percentiles`, `elevation_range_m`, `ponding_risk_area`, `erosion_proxy_area`, and `quality_warnings`.

  **QA Scenarios**:
  ```
  Scenario: Derived products happy path
    Tool: Bash
    Steps: Run derivative smoke on a tiny synthetic sloped DEM.
    Expected: all required derived raster filenames exist in temp output and contain finite/nodata-aware values.
    Evidence: .sisyphus/evidence/task-8-derived-products.json

  Scenario: Flat DEM edge case
    Tool: Bash
    Steps: Run derivative smoke on flat synthetic DEM.
    Expected: no unhandled divide-by-zero; warnings include flat terrain/limited flow signal.
    Evidence: .sisyphus/evidence/task-8-flat-dem.json
  ```

  **Commit**: YES | Message: `feat(dem): derive terrain products` | Files: [`my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`]

- [x] 9. Add data-pipeline path helpers and runtime output integration

  **What to do**: Extend `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` with DEM/terrain path helpers mirroring soil/satellite/derived patterns. Add field terrain dir, field DEM dir, field terrain derived dir, field DEM manifest path, farm DEM summary table path, and shared DEM cache path. Ensure naming uses existing `field_slug` conventions.
  **Must NOT do**: Do not change existing weather/soil/satellite path behavior.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: focused helper addition.
  - Skills: [] - no extra skill needed.
  - Omitted: [`legacy-modernizer`] - no broad refactor.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 10,13 | Blocked By: 1

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` - field weather/soil/satellite/derived helpers.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/lib/naming.py` - field slug conventions.

  **Acceptance Criteria**:
  - [ ] Python smoke imports `paths.py` and prints DEM paths for sample grower/farm/field.
  - [ ] New paths resolve under runtime farm/field directories, not repo checkout paths.
  - [ ] Existing path helper smoke/import behavior remains intact.

  **QA Scenarios**:
  ```
  Scenario: Path helper happy path
    Tool: Bash
    Steps: Run Python one-liner building DEM paths for `northern-il-grower/dekalb-ten-field-test/osm-1024683651` with temp DATA_PIPELINE_DATA_ROOT.
    Expected: all paths are under temp runtime and include `terrain/dem` or `derived/terrain`.
    Evidence: .sisyphus/evidence/task-9-paths.txt

  Scenario: No source path leakage
    Tool: Bash
    Steps: Run path helper with temp root and grep output for repository checkout path.
    Expected: checkout path is absent.
    Evidence: .sisyphus/evidence/task-9-no-leak.txt
  ```

  **Commit**: YES | Message: `feat(pipeline): add DEM terrain paths` | Files: [`my-farm-advisor/data-pipeline/src/scripts/lib/paths.py`]

- [x] 10. Implement runtime ingest CLI `download_dem_terrain.py`

  **What to do**: Add `my-farm-advisor/data-pipeline/src/scripts/ingest/download_dem_terrain.py`. CLI must support env handoff (`AG_GROWER_SLUG`, `AG_FARM_SLUG`, `AG_INVENTORY_CSV`, `AG_BOUNDARIES`, `AG_FORCE`) and explicit flags: `--grower`, `--farm`, `--inventory-csv`, `--boundaries`, `--context-meters`, `--source-policy`, `--dry-run`, `--limit-fields`, `--force`, `--allow-live-downloads`, `--offline-fixtures`. For each field, load canonical `field_boundary.geojson`, resolve source, download/cache, clip, condition, derive outputs, write summaries/manifests, and append farm summary. Idempotency: if manifest and all expected outputs exist and force is false, skip.
  **Must NOT do**: Do not write outputs to repo checkout; do not require live network in dry-run/offline mode.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: orchestration across adapters, runtime paths, raster processing.
  - Skills: [] - no extra skill needed.
  - Omitted: [`cli-developer`] - basic argparse follows repo pattern.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 11,12,13 | Blocked By: 2,4,5,6,7,8,9

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/ingest/download_satellite_imagery.py` - per-field raster loop/manifests.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/ingest/download_cdl.py` - shared raster cache and zonal outputs.
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/ingest/download_soil.py` - per-field CSV staging and summaries.
  - Runtime: `.my-farm-advisor-runtime/data-pipeline/growers/northern-il-grower/farms/dekalb-ten-field-test/fields/osm-1024683651/field.json` - existing field metadata shape.

  **Acceptance Criteria**:
  - [ ] `--dry-run --limit-fields 1` prints selected/planned source and output paths without downloading rasters.
  - [ ] Offline fixture mode produces full artifact package in a temp runtime for one synthetic field.
  - [ ] Missing field boundary writes structured error manifest and exits with controlled status.

  **QA Scenarios**:
  ```
  Scenario: Dry-run one field
    Tool: Bash
    Steps: Run CLI with DATA_PIPELINE_DATA_ROOT pointing to temp runtime, `--dry-run --limit-fields 1`.
    Expected: planned source and output paths printed; no `.tif` generated.
    Evidence: .sisyphus/evidence/task-10-dry-run.txt

  Scenario: Missing boundary failure
    Tool: Bash
    Steps: Run CLI against temp runtime field with missing `field_boundary.geojson`.
    Expected: structured error manifest records missing boundary; no traceback.
    Evidence: .sisyphus/evidence/task-10-missing-boundary.json
  ```

  **Commit**: YES | Message: `feat(pipeline): add DEM terrain ingest` | Files: [`my-farm-advisor/data-pipeline/src/scripts/ingest/download_dem_terrain.py`, `my-farm-advisor/terrain/dem-terrain/src/dem_terrain/**`]

- [x] 11. Integrate DEM step into pipeline docs and optional orchestration

  **What to do**: Update `my-farm-advisor/data-pipeline/README.md`, `my-farm-advisor/data-pipeline/AGENTS.md` if needed, and skill docs with DEM runtime commands. Add DEM as an optional standard pipeline step in `run_farm_pipeline.py` only if it can be guarded by a flag/env so default structure tests do not perform live DEM downloads. Recommended flag: `--include-dem-terrain`; standard env handoff sets `AG_CONTEXT_METERS=20`.
  **Must NOT do**: Do not make `run_farm_pipeline.py --structure-test` require network or DEM downloads.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: docs + small orchestration guidance.
  - Skills: [] - no extra skill needed.
  - Omitted: [`document-release`] - not post-ship docs.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 13 | Blocked By: 10

  **References**:
  - Pattern: `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py` - ordered pipeline steps and env handoff.
  - Pattern: `my-farm-advisor/data-pipeline/README.md` - runtime setup docs.
  - Pattern: `my-farm-advisor/data-pipeline/AGENTS.md` - smoke-test commands and runtime copy rules.

  **Acceptance Criteria**:
  - [ ] Docs show temp-root install/run commands and live-download warning.
  - [ ] `--structure-test` remains no-download.
  - [ ] DEM step can be invoked explicitly through documented command.

  **QA Scenarios**:
  ```
  Scenario: Structure test remains safe
    Tool: Bash
    Steps: Run documented structure-test command in temp runtime.
    Expected: exits 0 and no DEM downloads occur.
    Evidence: .sisyphus/evidence/task-11-structure-test.txt

  Scenario: Docs contain explicit DEM command
    Tool: Bash
    Steps: Grep docs for `download_dem_terrain.py`, `--context-meters 20`, and `--allow-live-downloads`.
    Expected: all required command fragments are present.
    Evidence: .sisyphus/evidence/task-11-docs.txt
  ```

  **Commit**: YES | Message: `docs(pipeline): document DEM terrain runtime` | Files: [`my-farm-advisor/data-pipeline/**`, `my-farm-advisor/terrain/dem-terrain/**`]

- [x] 12. Add validation, smoke fixtures, and invariant checks

  **What to do**: Add small text/JSON/mock fixtures only (no large rasters unless tiny synthetic and safely under asset policy). Add a DEM validation helper script or documented Python one-liners that check: expected file count, CRS projected, bounds cover buffered AOI, nodata ratio threshold, manifest fields, DSM warning, fallback reason, and no tracked generated assets. Use synthetic tiny raster generation in temp directories for offline tests.
  **Must NOT do**: Do not introduce pytest unless explicitly scoped; do not commit generated outputs.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: validation design across outputs and failure cases.
  - Skills: [] - no extra skill needed.
  - Omitted: [`test-master`] - formal test framework is intentionally avoided.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 13 | Blocked By: 10

  **References**:
  - Validator: `scripts/validate.sh` - required repo gate.
  - Runtime validation pattern: `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py --structure-test`.
  - Policy: `ASSET_POLICY.md` - asset limits.

  **Acceptance Criteria**:
  - [ ] Offline smoke validates synthetic full output package without network.
  - [ ] Invariant helper fails when manifest is missing required fields.
  - [ ] `./scripts/validate.sh` passes after fixtures/docs.

  **QA Scenarios**:
  ```
  Scenario: Offline full package validation
    Tool: Bash
    Steps: Run DEM offline smoke in `/tmp` temp runtime and then invariant checker.
    Expected: checker reports all required rasters/summaries/manifests present.
    Evidence: .sisyphus/evidence/task-12-offline-smoke.txt

  Scenario: Manifest schema failure
    Tool: Bash
    Steps: Run invariant checker on a deliberately incomplete temp manifest.
    Expected: checker exits nonzero and reports missing field names.
    Evidence: .sisyphus/evidence/task-12-manifest-fail.txt
  ```

  **Commit**: YES | Message: `test(dem): add terrain smoke validation` | Files: [`my-farm-advisor/terrain/dem-terrain/**`, `my-farm-advisor/data-pipeline/**`]

- [x] 13. Validate northern Illinois runtime and fallback behavior

  **What to do**: Run the implemented pipeline against existing runtime fields at `.my-farm-advisor-runtime/data-pipeline/growers/northern-il-grower/farms/dekalb-ten-field-test` using safe runtime mode. First run `--dry-run --limit-fields 10`; then run live DEM only if required credentials/network are available and user/environment allows, otherwise run offline/source-mock mode over the 10 real field boundaries. Also explicitly test fallback branches with mocked/no-1m scenarios and DSM-only global mock scenario. Capture evidence summaries, not large outputs.
  **Must NOT do**: Do not commit runtime outputs; do not delete user runtime data; do not perform huge county downloads.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: hands-on validation and evidence gathering.
  - Skills: [] - no extra skill needed.
  - Omitted: [`browse`] - no browser UI.

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: final verification | Blocked By: 10,11,12

  **References**:
  - Runtime inventory: `.my-farm-advisor-runtime/data-pipeline/growers/northern-il-grower/farms/dekalb-ten-field-test/manifests/field-inventory.csv` - 10 fields.
  - Runtime field metadata: `.my-farm-advisor-runtime/data-pipeline/growers/northern-il-grower/farms/dekalb-ten-field-test/fields/osm-1024683651/field.json` - example field metadata.
  - Policy: `AGENTS.md` - generated runtime assets untracked.

  **Acceptance Criteria**:
  - [ ] Dry-run processes exactly 10 northern Illinois fields and selects/plans best source per field.
  - [ ] Live or offline fixture run produces full package for at least one real field boundary and invariant checks pass.
  - [ ] Mocked fallback test proves no-1m path selects USGS 10m/30m or global fallback with fallback reason.
  - [ ] `git status --short` shows no tracked generated artifacts.

  **QA Scenarios**:
  ```
  Scenario: Northern Illinois 10-field dry run
    Tool: Bash
    Steps: Run DEM CLI against `.my-farm-advisor-runtime` with `--dry-run --limit-fields 10`.
    Expected: exactly 10 fields planned; each field has selected candidate or structured source error.
    Evidence: .sisyphus/evidence/task-13-ni-dry-run.txt

  Scenario: Fallback branch validation
    Tool: Bash
    Steps: Run resolver smoke with 1m candidates disabled and with DSM-only global mock.
    Expected: fallback reason recorded; DSM warnings present for DSM-only source.
    Evidence: .sisyphus/evidence/task-13-fallbacks.json
  ```

  **Commit**: YES | Message: `test(dem): validate terrain runtime smoke` | Files: [`my-farm-advisor/terrain/dem-terrain/**`, `my-farm-advisor/data-pipeline/**`] (evidence stays under `.sisyphus/evidence/` if tracked by workflow; no DEM artifacts)

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Real Manual QA — unspecified-high
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit after each task with the specified message.
- Do not stage `.my-farm-advisor-runtime/`, DEM rasters, previews, downloaded tiles, caches, or generated runtime summaries.
- Before every commit run `git status --short` and inspect staged files.
- Final implementation branch should include docs, scripts, small fixtures/mock metadata, and validation helpers only.

## Success Criteria
- The skill catalog exposes a reusable DEM terrain skill under `my-farm-advisor/terrain/dem-terrain`.
- Pipeline runtime can copy and run DEM terrain code from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`.
- U.S. fields prefer 1m lidar/USGS 3DEP direct root data; Illinois ILHMP is available as v1 adapter; global fallback adapters are implemented.
- Each successful field receives raw/clipped DEM, conditioned DEM, 10+ derived rasters, PNG previews, summaries, and provenance.
- Northern Illinois runtime fields are used for dry-run/live-or-offline validation.
- Generated/downloaded assets remain untracked.
- `./scripts/validate.sh` passes.
