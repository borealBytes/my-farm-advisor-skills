# My Farm Advisor Skills

This repository is the My Farm Advisor skill catalog: three portable agent
skills that turn farm, field, trial, and genotype data into decisions —
analyses a peer could re-run, maps a scout could trust, plans a season could
execute. It contains the skills, their local instructions, examples, scripts,
and validation checks that make the workflows discoverable by agents and
readable by humans. The catalog is harness-neutral: any agent runtime that can
read `SKILL.md` / `AGENTS.md` files can use it.

| Skill | Status | Scope | Start here |
| --- | --- | --- | --- |
| 🌾 `my-farm-advisor` | **Active focus** | Field management, soil, weather, imagery, terrain, EDA, strategy, admin maps, farm-data pipelines and reporting | [`SKILL.md`](my-farm-advisor/SKILL.md) |
| 🌱 `my-farm-breeding-trial-management` | Initial stab — expanding | Trial design, fieldbooks, germplasm, selection, crossing, field-boundary-aware trial placement | [`SKILL.md`](my-farm-breeding-trial-management/SKILL.md) |
| 🧬 `my-farm-qtl-analysis` | Initial stab — expanding | GWAS, eQTL, classical QTL, VCF/SNP QC, population structure, genomic prediction, genetics reporting | [`SKILL.md`](my-farm-qtl-analysis/SKILL.md) |

**Why this ordering is deliberate:** the data pipeline is the keystone — you
need trustworthy field data before trial analytics or genotype-by-phenotype
analysis can say anything. The advisor skill and its pipelines get built out
first so the breeding and QTL skills can grow into that foundation later with
more power behind them. Expect the 🌱 and 🧬 trees to expand the most over the
coming releases; their current examples are real and runnable, just fewer than
what's coming.

## What the output looks like

Every figure below was rendered by a script in this repository from public,
keyless data sources (verification fixtures; regenerate them with the
commands in each example's README).

### The images are the demo; the raw data is the product

**Download once, keep forever.** Everything you see rendered below is a thin
matplotlib drawing over a private, growing local archive: GeoTIFFs (terrain,
soil rasters, per-year crop classification, imagery), parquet tables (weather,
admin lookups, maturity grids), and GeoJSON polygons (boundaries, soil survey
map units) — one folder tree per field under `$DATA_PIPELINE_DATA_ROOT`. The
figures are the *simple* presentation format so examples can be committed and
verified offline; they are emphatically not the final form. Your agent knows
where every raw artifact lives, what produced it, and how to traverse the tree
(manifests and provenance JSON sit next to every output), so your actual
deliverable — a web map, a dashboard, an app, a slide, a scouting tool — reads
those same sources and draws them the way *you* need. The pipeline's unit of
value is the durable raw layer, not the PNG.

### Ready-to-use layers, not downloads you still have to process

The ingest scripts don't stop at "here's your raster." Take terrain: one call
clips the best-resolution DEM to your boundary, hydrologically conditions it,
and emits the **full derivative stack as GeoTIFFs with previews** — slope
(degrees and percent), aspect, hillshade, D8 flow direction and accumulation,
profile and planform curvature, topographic wetness index, TPI, TRI, relative
elevation, depression depth, and an erosion proxy — plus per-field summary
tables. Every layer carries the same provenance record, so a drainage or
erosion conversation downstream starts from computed rasters, not a raw DEM
and a to-do list. Same pattern across the archive: soil comes as rasters *and*
survey polygons with attribute tables, weather as daily-parquet plus computed
GDD, crop classification as per-year class grids *and* per-class probability
bands. It's a ready-to-use data pipeline for any purpose here — the processing
is the product; the download is just step one.

### Farm data stacks — terrain, soil, and crop type for one field boundary

Rendered by [`render_field_maps.py`](my-farm-advisor/data-pipeline/src/scripts/render_field_maps.py)
from a demo grower's runtime data: auto-resolved DEM hillshade (1 m LiDAR
where the resolver finds it, global 30 m elsewhere — each panel names the
source the manifest actually recorded), national soil surveys, and per-year
WorldCereal crop inference, co-registered to the field boundary (red).

| Iowa, US — 172 ha | Ontario, CA — 593 ha | Namoi Valley, AU — 44 ha pivot | Goiás, BR — 103 ha (global floor) |
| --- | --- | --- | --- |
| ![Iowa field stack](my-farm-advisor/data-pipeline/examples/field-maps/output/ia-r1_field_map.png) | ![Ontario field stack](my-farm-advisor/data-pipeline/examples/field-maps/output/on-r1_field_map.png) | ![Australia field stack](my-farm-advisor/data-pipeline/examples/field-maps/output/au-r4_field_map.png) | ![Brazil field stack](my-farm-advisor/data-pipeline/examples/field-maps/output/br-r1_field_map.png) |
| SSURGO map units; terrain auto-resolved to USGS 3DEP **1 m LiDAR**; WorldCereal independently called **soybean** on a documented 2023 soy field | Ontario soil survey components (Brookston/Perth/Normandale); winter-window inference | Soil Atlas of Australia clay % (SLGA/ASF, real values); WorldCereal called **rapeseed on 93 %** of this irrigated pivot — near-complete field coverage at 384 px | No Brazilian fine-coverage source exists in the registry, so the resolver fell back to NASADEM 30 m + SoilGrids 250 m: the **global floor** demo — the pipeline still delivers the full stack; whole 103-ha field ingest cost 1.4 MB |

### Soil intelligence at three resolution tiers

Same renderer, three provenance levels — survey polygons where they exist,
national atlases where they do, and the global 250 m floor everywhere:

| US — SSURGO survey polygons | Canada — Ontario Detailed Soil Survey (polygon) | Australia — national Soil Atlas | Global floor — SoilGrids 250 m (Brazil) |
| --- | --- | --- | --- |
| ![SSURGO components](my-farm-advisor/data-pipeline/examples/soil-maps/output/ia-r1_ssurgo_component_map.png) | ![Canada survey polygons](my-farm-advisor/data-pipeline/examples/soil-maps/output/on-r1_canada_survey_polygons.png) | ![AU Soil Atlas panels](my-farm-advisor/data-pipeline/examples/soil-maps/output/au-r3_soil_atlas_maps.png) | ![SoilGrids panels](my-farm-advisor/data-pipeline/examples/soil-maps/output/br-r1_soilgrids_maps.png) |
| 16 mapped components inside one boundary, one color per soil map | The same polygon treatment where SSURGO doesn't reach: ON-DSS components (Brookston/Perth/Normandale) from the cached national survey | The continent's official soil map as the survey tier — raster clip inside the field | Anywhere no national layer exists: 6 properties + relief at 250 m, the universal floor |

**Texture triangles — field-area weighted, one per provenance ([`generate_soil_texture_triangles.py`](my-farm-advisor/data-pipeline/src/scripts/reporting/generate_soil_texture_triangles.py)):**

| SSURGO (US) | Ontario DSS (CA) | Soil Atlas raster cells (AU) | SoilGrids 250 m cells (BR) |
| --- | --- | --- | --- |
| ![ia triangle](my-farm-advisor/data-pipeline/examples/soil-maps/output/ia-r1_texture_triangle.png) | ![on triangle](my-farm-advisor/data-pipeline/examples/soil-maps/output/on-r1_texture_triangle.png) | ![au triangle](my-farm-advisor/data-pipeline/examples/soil-maps/output/au-r4_texture_triangle.png) | ![br triangle](my-farm-advisor/data-pipeline/examples/soil-maps/output/br-r1_texture_triangle.png) |
| Every pin = one mukey×component: **series name + % of the field** (map-unit polygon area × within-unit component share), exact-class duplicates merged, labels collision-placed, star = the area-weighted field mean (loam, clay 26 / silt 40 / sand 33). Full percent ladders on **all three edges** — % SAND under the base, % CLAY up the right, % SILT down the left — each with its own bold titled axis. Canonical 12-class geometry from the CRAN `soiltexture` package | The Ontario survey speaks the same schema — same renderer, same triangle | The triangle as a **derivation** for gridded sources: every 100 m atlas cell inside the boundary is one point (30 displayed max), star = cell-weighted mean | The global floor too: SoilGrids sand/silt/clay cells of a Cerrado field → sandy clay loam mean. Four provenance levels, one classifier |

**Whole-field weighted property maps — the area-weighted field number, drawn as a surface:**

| Iowa (SSURGO) | Ontario (DSS) |
| --- | --- |
| ![ia weighted](my-farm-advisor/data-pipeline/examples/soil-maps/output/ia-r1_weighted_property_map.png) | ![on weighted](my-farm-advisor/data-pipeline/examples/soil-maps/output/on-r1_weighted_property_map.png) |
| 8 attributes — OM, pH, AWC, clay, silt, sand, CEC, bulk density — each map-unit polygon colored by **its component mix's topsoil value** (comppct-weighted within the unit), weighted mean printed per panel; below them a **100 % sand+silt+clay strip** across map units ordered north → south, width ∝ field share — watch the texture trade off as you walk down the field | Same schema, same math: Ontario census of Brookston/Perth/Kintyre, eight surfaces + the same texture strip |

**Horizon detail — the rows behind every map, triangle and weighted panel above.**
All of it — property maps, triangles, horizon tables, interpolated profiles — fires
automatically for **every field** in `run_farm_pipeline.py` (`--all-fields` mode:
survey triangle + horizon table + weighted map where polygons exist, the grid
triangle for raster providers):

| US — SSURGO horizons | Canada — ON-DSS horizons |
| --- | --- |
| ![Iowa horizon table](my-farm-advisor/data-pipeline/examples/soil-maps/output/ia-r1_horizon_table.png) | ![Ontario horizon table](my-farm-advisor/data-pipeline/examples/soil-maps/output/on-r1_horizon_table.png) |
| Left: the field itself — map units colored by **dominant component**, legend lists every series with its % of field area (sums to 100) — so the table rows tie straight to where they sit. Middle: color-coded horizon table. Right: the same table **interpolated to continuous depth** (piecewise-linear across horizon midpoints, comppct-weighted, 5 cm bins, starting at 0 cm) — the classic SSURGO interval interpolation, honest about being constant beyond measured | Same schema, same renderer: Ontario series (Brookston 82.8 %, Perth 13.2 %, Normandale 3.9 % of field) with real horizon splits, the same map, and profiles from the surface down |

### Terrain derivatives — ready the moment the DEM lands

The ingest computes the full derivative stack beside the raw DEM; here is the
same 9-layer view for each demo field, masked to the boundary. Iowa is the
**USGS 3DEP 1 m LiDAR** payoff; the others show the global 30 m floor:

| Iowa (≈1 m LiDAR) | Ontario (≈25 m) | Australia (≈28 m) |
| --- | --- | --- |
| ![Iowa terrain derivatives](my-farm-advisor/data-pipeline/examples/terrain-derivatives/output/ia-r1_terrain_derivatives.png) | ![Ontario terrain derivatives](my-farm-advisor/data-pipeline/examples/terrain-derivatives/output/on-r1_terrain_derivatives.png) | ![Australia terrain derivatives](my-farm-advisor/data-pipeline/examples/terrain-derivatives/output/au-r3_terrain_derivatives.png) |
| Elevation, hillshade, slope, aspect, D8 flow accumulation, wetness index, TPI, relative elevation, erosion proxy — rendered by [`render_terrain_derivatives.py`](my-farm-advisor/data-pipeline/src/scripts/reporting/render_terrain_derivatives.py) | Same nine layers at global resolution — the pipeline degrades resolution, never layers | Flow channels and terrace-like TWI bands visible even at 30 m |

### Derived planning layers — computed from our own weather, not licensed

| Corn relative maturity (model-derived) | Soybean MG (model-derived) |
| --- | --- |
| ![Corn RM North America](my-farm-advisor/data-pipeline/examples/maturity/output/corn_rm_northamerica_2023.png) | ![Soybean MG North America](my-farm-advisor/data-pipeline/examples/maturity/output/soybean_mg_northamerica_2023.png) |
| County GDD from our POWER pipeline → RM surface; recomputed per year; white L0/L1 borders with dark casing drawn from the cached admin layers (legible on the dark-green south); subtitle states its own limits | Latitude + heat-unit heuristic; planning layer, not a prescription — the caption says so |

Both maps are the admin-geometry demo at every level: **L0 countries, L1
states/provinces, L2 counties and Canadian census divisions** feed the
choropleth, and the cached Natural Earth lakes layer paints water over the
grid so the maps read like maps. Canada is capped ~250 mi (400 km) north of
the border — the Prairie corn/soy belt is in, the boreal void isn't, so the
picture stays about what actually grows. US-only, Canada-only, and combined
views all render from one flag (`--country usa|canada|north-america`).

### Field intelligence, component by component

Every panel below stands alone at readable size — identity, rotation, soil,
frost windows, five-season weather, five-season NDVI (86 keyless
Sentinel-2/Landsat scenes behind it), every number traceable to its cached
source layer. The whole-page poster assembler
([`generate_field_posters.py`](my-farm-advisor/data-pipeline/src/scripts/reporting/generate_field_posters.py))
still ships for dashboards; the gallery shows its components, not the poster.

**Weather — [`generate_weather_charts.py`](my-farm-advisor/data-pipeline/src/scripts/reporting/generate_weather_charts.py), every title derived from the data it plots:**

| Daily temperature + frost windows | Cumulative GDD (base 10) | Monthly precipitation |
| --- | --- | --- |
| ![Temperature](my-farm-advisor/data-pipeline/examples/weather-eda/output/ia_daily_temperature_frost.png) | ![GDD](my-farm-advisor/data-pipeline/examples/weather-eda/output/ia_weather_gdd.png) | ![Precip](my-farm-advisor/data-pipeline/examples/weather-eda/output/ia_monthly_precip.png) |
| Raw daily + 7-day mean, frost windows computed from the same CSV | Per-season curves + totals, one call | Last two complete years, every bar recomputable |

**Canopy — NDVI by crop and year, from the cached imagery archive:**

| Cumulative NDVI by crop and year | Crop-average NDVI | Peak NDVI (95th pct) |
| --- | --- | --- |
| ![Cumulative NDVI](my-farm-advisor/data-pipeline/examples/field-components/output/ia-r1_ndvi_cumulative.png) | ![Average NDVI](my-farm-advisor/data-pipeline/examples/field-components/output/ia-r1_ndvi_crop_average.png) | ![Peak NDVI](my-farm-advisor/data-pipeline/examples/field-components/output/ia-r1_ndvi_peak95_corn.png) |
| Per-crop subplots, mean lines with 5th–95th percentile envelopes, only years whose CDL crop-year label matches | Field-masked mean over all crop-year scenes | Mid-season peak window — the biomass ceiling |

The soil card generator ([`generate_ssurgo_cards.py`](my-farm-advisor/data-pipeline/src/scripts/reporting/generate_ssurgo_cards.py))
still feeds the compact soil panel of the full-season field report; the standalone
per-field soil figure is the USDA **texture triangle** above — sand/silt/clay lives in
the triangle, not in bar charts of unrelated numbers side by side.

### Per-year crop classification anywhere — keyless satellite imagery

Rendered by [`render_worldcereal.py`](my-farm-advisor/data-pipeline/src/scripts/render_worldcereal.py) and [`render_worldcereal_cdl.py`](my-farm-advisor/data-pipeline/src/scripts/render_worldcereal_cdl.py)
using the open WorldCereal default models on Microsoft Planetary Computer
Sentinel-2 (no accounts, no keys), cross-checked against the USDA CDL.

| Iowa — WorldCereal vs USDA CDL, side by side | Narrabri, dry season | Narrabri, summer season |
| --- | --- | --- |
| ![Iowa CDL comparator](my-farm-advisor/data-pipeline/examples/worldcereal/output/wc_verify_ia_soy_cdl.png) | ![Narrabri tc-s2](my-farm-advisor/data-pipeline/examples/worldcereal/output/wc_verify_au_tc2.png) | ![Narrabri tc-s1](my-farm-advisor/data-pipeline/examples/worldcereal/output/wc_verify_au_tc1.png) |
| Six panels: imagery, NDVI, cropland mask, WorldCereal crop type **and USDA CDL 2023** on identical extents — in-field shares printed, verdict **AGREE** (CDL 96.7% soybeans vs WorldCereal 98.9%) | Correctly sees the fallow dry-season window (La Niña 2023) | Honest caveat: un-fine-tuned model mislabels cotton as oilseed — regional accuracy stated, not oversold |

### Breeding operations — designs, fieldbooks, and selection

| Boundary-aware trial placement | RCBD layout | Alpha-lattice design |
| --- | --- | --- |
| ![Trial placement](my-farm-breeding-trial-management/examples/field-trial-placement/output/trial_map_maximized.png) | ![RCBD](my-farm-breeding-trial-management/examples/rcbd-design/output/rcbd_layout.png) | ![Alpha lattice](my-farm-breeding-trial-management/examples/alpha-lattice/output/alpha_lattice_field_map.png) |
| Maximized 6-var × 4-block RCBD rotated into one lobe of an irregular field, 9 m headlands respected — trial geometry planned against the real boundary | Randomized complete blocks, four reps across twelve treatments | 24 treatments × 3 reps, blocks of 4, checks woven through entries |

| Field-book plot map | Pedigree lineage | Selection index ranking |
| --- | --- | --- |
| ![Field book](my-farm-breeding-trial-management/examples/field-book/output/fieldbook_plot_map.png) | ![Pedigree](my-farm-breeding-trial-management/examples/pedigree-management/output/pedigree_lineage.png) | ![Selection index](my-farm-breeding-trial-management/examples/selection-index/output/selection_index_top15.png) |
| Grower-view plot layout straight from a generated fieldbook | Backcross lineage P → F1 → BC1–BC3 as a directed graph | Top-15 genotypes by weighted multi-trait index |

| Multi-year genomic values | Trial site footprint (BMS) |
| --- | --- |
| ![GEBV ranking](my-farm-breeding-trial-management/examples/breeding-value-ranking/output/gebv_top15_ci_plot.png) | ![BMS sites](my-farm-breeding-trial-management/examples/bms-client/output/bms_trial_site_map.png) |
| Top-15 genotypes with 95 % CIs after BLUP | Trial sites on a real satellite basemap — green = read from the client, orange = written through it |

### Quantitative genetics — mapping and diagnostics

| QTL ideogram + aligned Manhattan | Genomic-control QQ | Pedigree relationship matrix |
| --- | --- | --- |
| ![QMapper ideogram](my-farm-qtl-analysis/examples/qmapper-ideogram/output/qmapper_combined.png) | ![QQ before/after GC](my-farm-qtl-analysis/examples/genomic-control/output/qq_before_after_gc.png) | ![NRM heatmap](my-farm-qtl-analysis/examples/pedigree-kinship/output/pedigree_nrm_heatmap.png) |
| Significant QTL flagged per chromosome, thresholds documented | Inflation before correction, realigned after — the QC story in one panel | Inbreeding visible on the diagonal; relatedness blocks from a demo pedigree |

| Classical interval mapping | LD decay | eQTL locus detail |
| --- | --- | --- |
| ![LOD curve](my-farm-qtl-analysis/examples/classical-qtl/output/qtl_lod_example.png) | ![LD decay](my-farm-qtl-analysis/examples/ld-decay/output/ld_analysis.png) | ![eQTL locuszoom](my-farm-qtl-analysis/examples/eqtl-cis/output/eqtl_locuszoom_example.png) |
| Peak LOD 6.2 against a LOD-3 threshold — the 1990s method, fully reproducible | Exponential r² decay fit + 20-SNP pairwise heatmap | Lead SNP at p=2e-15 next to the gene TSS — the regulatory-QTL view |

| Population structure + admixture | Genomic prediction accuracy |
| --- | --- |
| ![Admixture](my-farm-qtl-analysis/examples/admixture/output/admixture_plot.png) | ![Genomic prediction](my-farm-qtl-analysis/examples/genomic-prediction/output/genomic_prediction.png) |
| PCA clusters, K=3 ancestry bars, sorted panel, variance explained | True vs predicted GEBV (r=0.56), distributions, top-rank selection — the breeding-value payoff |

## Global data coverage — the best available data for your location

"Global" here does not mean one flattened global layer everywhere. It means a
**ladder**: the highest-resolution authoritative source that covers the field's
country, with a verified global wall underneath so *no location ever falls
through*. Ingest scripts pick the top of the ladder automatically (the terrain
resolver ranks adapters by measured resolution and provenance and warns above
its 30 m coarseness threshold), and every run records which source won. No API
keys, logins, or paid services anywhere in the default path.

| Capability | Regional / national tier (best available) | Global floor (always works) |
| --- | --- | --- |
| **Terrain** | USGS The National Map — 3DEP DEM at 1 m / 1/9° / 1/3° / 2 m / 10 m where mapped (US); ILHMP LiDAR (Illinois, sub-metre) | Copernicus DEM GLO-30 (COG), NASADEM 1″, ALOS AW3D30 — resolution-ranked auto-selection with full derivative suite (slope, aspect, hillshade, D8 flow, contours) |
| **Field boundaries** | USDA Crop Sequence Boundaries (US, field-level polygons every year) | OSM/Overpass farm rules (CA, AU, anywhere) + new-country checklist in [`field-boundary-sources.md`](my-farm-advisor/data-pipeline/references/field-boundary-sources.md) |
| **Soil** | SSURGO (US, tested/method flags); Ontario detailed soil survey (CA); Soil Atlas of Australia via Gaia-DAP (AU) | SoilGrids 250 m with verified scale table; country-aware routing in [`soil-routing.md`](my-farm-advisor/soil/soil-routing.md) |
| **Crop rotation history** | USDA CDL, 2008→ (US); AAFC ACI, 2017→ (CA) | Per-year WorldCereal default-model inference on keyless Sentinel-2 (any country) — see below |
| **Imagery** | Sentinel-2 L2A (10 m, ~5-day revisit) + Landsat Collection 2 L2 (30 m; collection back to 1982 — pipeline defaults to Landsat 8+9 for the combined 8-day window) | Same archives are global via keyless Planetary Computer STAC; Sentinel-1 C-band SAR (VV/VH) is wired into the WorldCereal input cube — real radar via the free optional CDSE backend, constant NODATA in the keyless default (documented trade-off) |
| **Weather** | NASA POWER field-centroid Zarr (station-assimilated, any coordinate) | Same |
| **Admin & context** | geoadmin + combined FIPS (US) | L0 every country (Natural Earth); L1/L2 **any** ISO3 via `--gadm-iso` (GADM 4.1, one-key-free download, merged into the same combined lookup) |
| Small-footprint site maps | `lib/geoadmin_context.py` on cached layers | L0/L1/L2 borders + county names drawn around plotted points — any client map locates itself |
| **Maturity zones (derived, not licensed)** | Corn RM / soybean MG computed **in-house per year** for US FIPS counties + provincial analog (CA) | No open official source exists — every seed company keeps proprietary maps; we rebuild ours from literature-based heat-unit models driven by our own NASA POWER weather (default 2021–2025 window, annual parquets you can re-run). More crops and regions are on the roadmap |

**Rotation history for any country, any year.** Where no national map exists,
[`apply_worldcereal.py`](my-farm-advisor/data-pipeline/src/scripts/ingest/apply_worldcereal.py)
runs the open [WorldCereal default models](https://github.com/WorldCereal/worldcereal-classification)
(MIT) per year on Planetary Computer Sentinel-2 — zero accounts, 12 monthly
composites from the crop-calendar season window (Southern-Hemisphere cross-year
correct), provenance + honest regional-accuracy caveats with every output. The
routing order and the fine-tuning upgrade path are in
[`crop-rotation-sources.md`](my-farm-advisor/data-pipeline/references/crop-rotation-sources.md).
Capability matrix details in
[`my-farm-advisor/README.md`](my-farm-advisor/README.md#global-data-coverage-any-country-zero-accounts).

### Regional elevation extras beyond the global floor

The terrain tier is where "best available for your location" matters most,
because the gap between sources is 30 m vs sub-metre. The resolver registry
takes regional adapters the same way the boundary playbook takes new countries
— one module, provenance, license check — so extras are additive, never
forking:

| Status | Country | Better-than-global source |
| --- | --- | --- |
| ✅ Wired | US | USGS 3DEP (1 m / 1/9° / 1/3° / 2 m / 10 m, auto-resolved per field) |
| ✅ Wired | Illinois | ILHMP LiDAR (sub-metre) |
| 🔜 Next | Canada | NRCan **CanElevation** series: HRDEM/HRDEM Mosaic 10 m LiDAR-derived (186,000+ km² released), CCO 10 m, and open-licensed point clouds — Open Government Licence (Canada), attribution-required, account-free |
| 🔜 Next | Australia | **ELVIS** (Geoscience Australia's free national elevation portal: state LiDAR + DEMs under ICSM), Vicmap 10 m + LiDAR DEM collections (Victoria), GA SRTM 1″ national DEM-H/DEM-S |
| 📋 Catalogued | Europe / Japan / NZ | UK Environment Agency LiDAR (2/5 m), Netherlands AHN, Japan GSI 5 m, NZ LINZ — mostly open national programs; onboarding follows the same adapter checklist |

Wiring a national source changes nothing downstream: same contract, same
derivatives, and the resolver's provenance record shows which source won for
each field (e.g. the Iowa demo field resolves to USGS **1 m** with NASADEM and
ALOS 30 m logged as ranked alternatives).

## How the catalog is organized

Three skills, each a routed family of workflow areas. The router stays small;
the knowledge lives close to the work.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#e8f5e9","primaryTextColor":"#1b5e20","primaryBorderColor":"#81c784","lineColor":"#90a4ae","secondaryColor":"#e3f2fd","tertiaryColor":"#fff8e1"}}}%%
mindmap
  root((🌾 My Farm Advisor Skills))
    🌾 my-farm-advisor
      Admin · geoadmin, interactive maps
      Data sources · rebuilds, reporting
      EDA · explore, correlate, visualize
      Field management · boundaries, headlands
      Imagery · Landsat, Sentinel-2
      Soil · SSURGO, CDL, routing
      Strategy · maturity, planning
      Weather · NASA POWER
      Data pipeline · ingest, render, runtime
    🌱 breeding-trial-management
      Design · RCBD, alpha-lattice, augmented
      Fieldbook · sheets, labels, sync
      Placement · boundary-aware siting
      Germplasm · accessions, pedigrees
      Selection · indexes, ranking, simulation
      Crossing · mate pairing
    🧬 qtl-analysis
      Mapping · GWAS, eQTL, QTL, GxE
      QC · VCF, filtering, imputation
      Structure · PCA, admixture, kinship
      Prediction · BLUP, Bayesian GP, CV
      Reporting · ideograms, reports
```

## How a request flows

The routing hierarchy is a contract: `SKILL.md` → `INDEX.md` → subtree
`AGENTS.md` → matching guide/script/example. Never skip levels.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#e3f2fd","primaryTextColor":"#0d47a1","primaryBorderColor":"#64b5f6","lineColor":"#90a4ae","secondaryColor":"#e8f5e9","tertiaryColor":"#fff8e1"}}}%%
sequenceDiagram
    autonumber
    participant User as 🌿 User
    participant Skill as 🧭 SKILL.md
    participant Index as 📚 INDEX.md
    participant Rules as 📝 AGENTS.md
    participant Script as 🧩 Guide / script / example
    participant Data as 💾 Runtime data root
    User->>Skill: Farm, breeding, or QTL question
    Skill->>Index: Choose the workflow family
    Index->>Rules: Load local operating rules
    Rules->>Script: Run the matching workflow
    Script->>Data: Read/write under DATA_PIPELINE_DATA_ROOT
    Script-->>User: Answer with provenance + caveats
```

## Progressive disclosure — why the catalog is split this way

A large skill tree can quietly destroy an agent: if everything loads into the
prompt, a 656-file / 18 MB catalog becomes context-window tax on every session,
and the model drowns in instructions it doesn't need. This repo is structured
the opposite way — **only the routing surface is resident; knowledge loads on
demand as the request earns it**:

| Level | Files | Size in this catalog | When it enters context |
| --- | --- | --- | --- |
| L0 — discovery | `SKILL.md` frontmatter (name + trigger description) | a few lines each | always; it's what the harness matches the request against |
| L1 — router | 4 × `SKILL.md` bodies | 13.7 KB total | when a request matches a skill |
| L2 — family map | 13 × `INDEX.md` | 12.8 KB total | after routing picks the workflow family |
| L3 — operating rules | 29 × subtree `AGENTS.md` | 47.3 KB total | only for the subtree being edited or run |
| L4 — depth | 200+ guides, scripts, examples (≈750 KB of docs) | ~97 % of all bytes | only the one or two files the task actually needs |

A typical Ontario soil question touches roughly **3–8 KB of instructions** —
the SKILL.md router line, the soil INDEX row, the soil-subtree AGENTS.md, and
`soil-routing.md` — while the GWAS, breeding-design, and imagery manuals stay
on disk costing nothing. Routing itself is automatic: the L0 descriptions are
written as triggers ("use when…"), the L1/L2 tables map intents to files, and
the validator fails the build if any of those links rot, so an agent can trust
the ladder instead of reading the whole tree to find things.

**Harness portability.** Every level is a Markdown file with a stable name, and
nothing above L0 assumes a particular agent framework. **Hermes and OpenCode
are the first-class, continuously tested harnesses**; OpenClaw (this catalog's
birthplace), Pi, Claude-style skill runtimes, and Codex should work through the
same plain-file contract, and plain `grep` always does.

**Frontier models are not required.** The progressive-disclosure design exists
so that modest models can drive big workflows: the router files are small, the
scripts are deterministic, and provenance is in the data rather than in the
model's head. A lot of this catalog was built and is tested daily against
inexpensive models — Qwen 3.8 Flash Next and DeepSeek 4.1 Flash, including
locally served — and it began life on frontier GPT/Claude models back when the
cheap options couldn't hold a multi-step pipeline. They can now; the ecosystem
is moving fast, and this catalog is written to ride that curve rather than pay
a token tax to it.

## How data-source routing decides

Country-aware tiering (soil shown; the same ladder governs boundaries and
rotation history, documented in `soil/soil-routing.md`):

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#e8f5e9","primaryTextColor":"#1b5e20","primaryBorderColor":"#81c784","lineColor":"#90a4ae","secondaryColor":"#e3f2fd","tertiaryColor":"#fff8e1"}}}%%
flowchart TD
    field([🚜 Field with boundary]) --> q{Country?}
    q -- US --> us[Tier 1 · SSURGO + CDL]
    q -- CA --> ca[Tier 1 · Ontario DSS / AAFC ACI]
    q -- AU --> au[Tier 1 · Soil Atlas via Gaia-DAP]
    q -- otherwise --> glob{WorldCereal model applicable?}
    us --> stack[💾 Per-field runtime data stack]
    ca --> stack
    au --> stack
    glob -- yes --> wc[Tier 2 · WorldCereal per-year inference + caveat]
    glob -- no --> sg[Tier 3 · SoilGrids 250 m floor]
    wc --> stack
    sg --> stack
    stack --> out[📈 Maps, EDA, reports, plans]

    classDef tier fill:#e3f2fd,stroke:#64b5f6,color:#0d47a1
    classDef gate fill:#fff8e1,stroke:#ffcc80,color:#5d4037
    class us,ca,au,wc,sg tier
    class q,glob gate
```

## Runtime and output rules

| Rule | Why |
| --- | --- |
| Runtime data lives outside Git, under `${DATA_PIPELINE_DATA_ROOT}` (default `./data`) | Farm data grows roughly linearly with monitored acreage — the clone must stay small for any deployment |
| Generated outputs are committed at exactly one place: `examples/**/output/*.png` | Small deterministic fixtures let examples verify offline; everywhere else, regenerate at runtime (see [`ASSET_POLICY.md`](ASSET_POLICY.md)) |
| Pinned URLs + sha256 journals for downloads | Checksum drift fails closed; a run is reproducible months later |
| Commit metadata and source records, not payloads | Provenance without repository bloat |
| Run `./scripts/validate.sh` after structural changes | Catches missing routers, stale links, and policy regressions |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#e8f5e9","primaryTextColor":"#1b5e20","primaryBorderColor":"#81c784","lineColor":"#90a4ae","secondaryColor":"#e3f2fd","tertiaryColor":"#ffebee"}}}%%
flowchart LR
    start([🧪 scripts/validate.sh]) --> roots[🧭 Three skill roots present]
    roots --> meta[📄 SKILL.md frontmatter valid]
    meta --> links[🔗 Links and anchors resolve]
    links --> stale[🧹 No stale routing refs]
    stale --> assets[📦 Asset-policy exclusions honored]
    assets --> pass([✅ Catalog is ready])
    meta -. failure .-> fail([🚧 Fix and rerun])
    links -. failure .-> fail
    stale -. failure .-> fail
    assets -. failure .-> fail

    classDef check fill:#e3f2fd,stroke:#64b5f6,color:#0d47a1
    classDef ok fill:#e8f5e9,stroke:#66bb6a,color:#1b5e20
    classDef bad fill:#ffebee,stroke:#ef9a9a,color:#b71c1c
    class roots,meta,links,stale,assets check
    class pass ok
    class fail bad
```

## Strategy playbooks — the interpretation layer over the raw data

Data without context is a liability. The strategy sub-skill
([`strategy/INDEX.md`](my-farm-advisor/strategy/INDEX.md)) ships
**crop-specific, region-specific, year-stamped playbooks** — currently
2026-season guides for corn, soybean, cotton, wheat, and grain sorghum, each
with regional decision bands, planning windows, maturity frames, risk
watchouts, and citations to extension/economics sources (farmdoc, ISU AgDM,
Crop Protection Network…). A small recommendation engine
(`generate_farm_recommendations` / `generate_field_recommendations`) feeds
those guides with *your measured field attributes* — soil pH, water-holding,
drainage class, erosion risk, rotation history, GDD — into the farm and field
reports, under a hard rule: never invent field facts the data doesn't carry;
say "scout this" instead.

This is an explicitly growing layer: the goal is playbooks for more regions,
more crops, every year — so your agent can tell you what the raw data *means*
for your location and operation, not just plot it. Playbooks are Markdown by
design: fork the format, write yours for your ground, and the same engine
consumes them.

## Your own boundaries are the seed of everything

The field-boundary layers above (CSB, OSM) are **starting material**: great for
experimenting, benchmarking, and coverage demos, and honestly useful for some
tasks even for real operations. But if you farm or trial ground, the pipeline
was built to run against *your* polygons:

1. Drop your field boundaries in — shapefile, KML/KMZ, GeoPackage, GeoJSON,
   Google-Earth export, whatever fell off the cab monitor. Any format works
   because the agent converts it; the pipeline canonical form is per-field
   boundary GeoJSON in WGS84.
2. Tell the agent: *"initialize the data pipeline against these boundaries."*
3. Everything downstream fills out **in the context of your fields**: FIPS /
   province scoping, SSURGO or SoilGrids soils under each polygon, Copernicus
   and (where mapped) 3DEP terrain, NASA POWER weather at each centroid,
   Sentinel-2/Landsat scenes clipped to the boundary, per-year crop-type
   inference, and the reports and dashboards on top.

Your boundaries stay **yours**: they live in your runtime data root
(`$DATA_PIPELINE_DATA_ROOT`, gitignored) and never need to leave your machine —
the skill author never sees them. That's what makes this a private analytics
base rather than someone else's web app: the published catalog is the
methodology, and your farm folder is the instantiation. For quick exploration
without your own polygons, `bootstrap_farm_from_county.py` samples deterministic
public fields from any county and runs the whole pipeline on them.

## Built to be extended — your crop, your region, your operation

This catalog is a **base**, not a finished product. Every capability is a
pattern with a seam: the country-aware soil router takes the provider you
write for your province or parish; the maturity machinery takes the phenology
model for the crop you actually grow; the design library takes your plot
constraints; the reporting templates take the metrics your organization buys.
The three per-domain playbooks in
[`data-pipeline/references/`](my-farm-advisor/data-pipeline/references/)
(boundaries, rotation, soil) document exactly how a new country or provider
gets onboarded — discover, license-check, ingest module, provenance, validator.

Illustrative examples — not a checklist — of what different operators do with
the base, all of it decision support grounded in their own data:

| Reader | Might extend it for |
| --- | --- |
| Grower / farm manager | Field-by-field decision support on their own ground: planting windows, drainage and erosion calls, rotation planning, scouting priorities |
| Grain buyer / processor | Supply-origin risk: contract-area delivery planning, quality and acreage signals near each intake point |
| Insurance / investment | Field-level risk selection and index products, claims triage with damage-evidence imagery, region benchmarks |
| Extension agent | Local variety-trial analytics and advisory dashboards for the counties they serve |
| Research / breeding company | Their trial designs and germplasm pipelines wired to real field conditions |
| Seed company | Maturity models and placement zones for their genetics specifically |

The point of publishing it as skills rather than an application: the analysis
interface is natural language ("show me last week's canopy for the home field"),
the reproducibility layer is scripts + provenance, and anyone — farmer or
geneticist — gets both without us choosing their agent harness for them.

## The three skills in detail

### 🌾 My Farm Advisor

| Area | Index | Examples of work |
| --- | --- | --- |
| Admin | [`admin/INDEX.md`](my-farm-advisor/admin/INDEX.md) | Geoadmin workflows and interactive maps |
| Data sources | [`data-sources/INDEX.md`](my-farm-advisor/data-sources/INDEX.md) | Data rebuilds, deterministic pipeline runs, intelligence reporting |
| EDA | [`eda/INDEX.md`](my-farm-advisor/eda/INDEX.md) | Exploration, comparisons, correlations, visualization, time series |
| Field management | [`field-management/INDEX.md`](my-farm-advisor/field-management/INDEX.md) | Boundaries, CSB sampling, headlands |
| Imagery | [`imagery/INDEX.md`](my-farm-advisor/imagery/INDEX.md) | Landsat and Sentinel-2 workflows |
| Soil | [`soil/INDEX.md`](my-farm-advisor/soil/INDEX.md) | SSURGO, CDL, country routing, poster cards |
| Strategy | [`strategy/INDEX.md`](my-farm-advisor/strategy/INDEX.md) | Crop strategy and maturity planning |
| Weather | [`weather/INDEX.md`](my-farm-advisor/weather/INDEX.md) | NASA POWER weather and derived analysis |
| Data pipeline | [`data-pipeline/README.md`](my-farm-advisor/data-pipeline/README.md) | Country-aware ingest, per-field rendering, runtime management |

### 🌱 My Farm Breeding Trial Management

| Area | Examples of work |
| --- | --- |
| Design | RCBD, alpha-lattice, augmented designs (with committed layout fixtures) |
| Fieldbook | Plot sheets, labels, imports, IoT field sync |
| Placement | Field-boundary-aware trial siting |
| Germplasm | Accessions, pedigrees, mock breeding-system integrations |
| Selection | Selection indexes, GEBV ranking, cycle simulation |
| Crossing | Mate pairing, coancestry-aware crossing plans |

### 🧬 My Farm QTL Analysis

| Area | Examples of work |
| --- | --- |
| Mapping | GWAS (GLM/LMM), eQTL, classical QTL, GxE, covariates, rare variants |
| QC | VCF validation, SNP filtering, genomic control, imputation |
| Structure | PCA, admixture, LD decay, haplotypes, kinship |
| Prediction | Genomic prediction, BLUP, Bayesian GP, elastic net, cross-validation |
| Reporting | Ideograms, analysis reports, real-dataset packaging |

## Repository layout

```text
my-farm-advisor-skills/
├── README.md, AGENTS.md, ASSET_POLICY.md, CONTRIBUTING.md
├── scripts/validate.sh
├── my-farm-advisor/                 # SKILL.md, INDEX.md, AGENTS.md, workflow areas,
│                                    # data-pipeline (ingest scripts + example fixtures)
├── my-farm-breeding-trial-management/
└── my-farm-qtl-analysis/
```

## Working in this repo

| Task | Start here | Validate with |
| --- | --- | --- |
| Route a farm advisory request | [`my-farm-advisor/SKILL.md`](my-farm-advisor/SKILL.md) | `./scripts/validate.sh` |
| Route a breeding request | [`my-farm-breeding-trial-management/SKILL.md`](my-farm-breeding-trial-management/SKILL.md) | `./scripts/validate.sh` |
| Route a QTL request | [`my-farm-qtl-analysis/SKILL.md`](my-farm-qtl-analysis/SKILL.md) | `./scripts/validate.sh` |
| Add/refresh an example figure | The example's own README | Render, inspect, commit to `examples/**/output/` |
| Change catalog structure | Root [`AGENTS.md`](AGENTS.md) | `bash -n scripts/validate.sh && ./scripts/validate.sh` |
| Update docs with a feature change | [`CONTRIBUTING.md`](CONTRIBUTING.md) (doc-sync rule) | `./scripts/validate.sh` |

Keep edits focused, keep operational data in the runtime root, and route
through the nearest `INDEX.md` before opening detailed workflow docs.
