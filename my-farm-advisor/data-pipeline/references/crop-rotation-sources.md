# Crop rotation / cropping-history sources by country

Purpose: reconstruct **what crop was on this field in each previous year**.
The layer must be a **year-by-year, per-pixel crop-type map**. Single-year
snapshots — even a beautiful global one — cannot answer a rotation question
and are rejected for this use. Per-country status as of 2026-11-03;
live-verified endpoints; sources released before the 2026-02 data cutoff.

| Country / scope | Source | Per-year crop type? | Years | Access |
|---|---|---|---|---|
| US | USDA NASS **CDL** (pipeline provider `soil/cdl-cropland`) | **yes** | 2008→ | keyless, public domain |
| Canada | **AAFC AGCAP Crops (ACI)** (see `references/canada-shared-geodata.md`) | **yes** | 2017→ | keyless, free custom licence |
| Australia | *no source map* — classify with WorldCereal default models (see below) | model-derived | any w/ imagery | **keyless** (Planetary Computer); MIT weights |
| Global (any country, no fine-tuning) | **WorldCereal default models** via `worldcereal-classification` toolbox | **yes** (apply per year) | any w/ imagery (2017→) | **keyless** (PC; CDSE optional), MIT, torch |
| Global maps (context only) | ESA WorldCereal v100 official product | no — single year | 2021 only | keyless (Zenodo 7875105) |
| ~~Global~~ | ~~Google TEIO~~ — dropped: Earth Engine only, no keyless mirror | — | — | — |

## Routing rule (any country)
1. National by-year crop layer exists (US CDL, CA ACI, future others) → use it.
2. Else, apply the **WorldCereal default models** (`worldcereal-classification`
   toolbox, MIT) to the field's AOI and year — global-trained, no fine-tuning
   required, any year the imagery exists for. Quality is region-dependent and
   unvalidated for places like Australia: report predictions WITH that caveat,
   never as ground truth. See section below.
3. Else/if better local accuracy matters: fine-tune a regional model on local
   labels (model-derived section) and run that instead.
4. Else → state honestly that field-level rotation history is not publicly
   mapped for that country. Region crop-mix profiles (AU: ABS DBR; snapshots:
   CSCLUM) may be attached as *context*, labeled as such — never silently
   substituted for a rotation answer, and never a single-year global map.

**Mandatory before any satellite crop classification:** resolve the crop
**growing-season window for that region AND year** and subset imagery to the
season (plus ~30–45 d buffer on each side). Never classify a whole-year
stack. Preferred lookup: the WorldCereal seasonality table (built into the
toolbox, `get_season_dates_for_extent`, dekads on a 3-year scale so
cross-calendar-year Southern-Hemisphere seasons resolve correctly); fallback:
national/state calendars (e.g. NSW winter cropping May–Oct; US Corn Belt
plant–harvest by state). Record the resolved window in the provenance JSON.
Mechanical note: the Presto encoder consumes a FIXED number of monthly
composites (12), so the *imagery fetch* spans the full calendar year while the
*season window* masks classification and provenance — season-focused
inference, not a whole-year-labels average.

## Australia — the honest picture (searched 2026-11-03)
There is **no parcel-level annual crop-type dataset** for Australia equivalent
to CDL/ACI. GA's NLWRS **NAIS/NALUI** (annual land use on ag parcels) is
retired — the GA portal itself returns zero records for it. What exists
instead is context, not history:

### Region profile — ABS "Data by Region" LGA crop areas (live-proven)
- ArcGIS FeatureServer, keyless:
  `https://geo.abs.gov.au/arcgis/rest/services/Hosted/LGA_econ_ind_DbR_Nov24/FeatureServer/0`
  (Nov_25 siblings exist; older `ABS_Economy_and_industry_*` is token-gated.)
- Query: `where=UPPER(lga_name_2021) LIKE 'NARRABRI%'&f=json`.
- Carries (2021 data year, per LGA polygon): area of holding, **area of
  broadacre crops (ha)**, vegetables, orchard/nut, irrigated area, water
  applied, livestock counts, gross value. Verified for Narrabri LGA `15750`:
  605,530 ha holdings, 285,203 ha broadacre crops, $414 M crop GVP.
- Per-crop split by LGA × year: the DBR **Agriculture & fisheries** topic cube
  (`dbr.abs.gov.au`, Excel/CSV, CC-BY 4.0; bare curl gets HTML — use the
  documented API base or the download cube). Crop mix by region by year —
  a rotation *profile*, not per pixel.
- Deterministic ingest recipe if wired: point-in-polygon the FeatureServer
  from the field centroid, cache attributes + `lga_code_2021`, journal the
  service epoch.

### Snapshot context — ACLUMP / CSCLUM (ABARES)
- Catchment Scale Land Use of Australia, Dec-2023 update (released Feb 2024,
  pre-cutoff): DOI `10.25814/2w2p-ph98`; companion **Commodities** dataset
  DOI `10.25814/zfjz-jt75` — polygon commodity classes incl. cotton, rice,
  sugarcane (stated-complete). 50 m raster + per-state vectors, CC-BY 4.0.
- It is a current-land-use snapshot refreshed ~biennially: successive releases
  diff into coarse land-use *change*, not annual crop sequence. Use it as
  "what is there now / what was there in 2018/2020/2023 snapshots", especially
  for **cotton**, which neither TEIO nor WorldCereal classes at all.
- Portal <https://www.agriculture.gov.au/abares/aclump/land-use/data-download>
  (TLS-blocks curl; use a browser session or the DOIs). National v7.1
  published Aug 2026 = post-cutoff; cite v6 (2022) instead.

## ~~TEIO~~ — dropped (2026-11-03)
Google TEIO (`GOOGLE/TEIO/_crop_type/v1`, annual 2017–2023, CC-BY 4.0) was the
only other global by-year product, but it is Earth Engine-only: no keyless
mirror exists (Zenodo/figshare/source.coop verified empty) and no Google/GCP
project is in use. Excluded from the routing table; the one-line export recipe
lives in session history if a GEE account ever appears.

## Model-derived crop type (derive-it-ourselves route)
When no by-year source map exists for a region, classify open imagery directly.
Verified landscape (2026-11-03, live-checked licenses/dates):

| Asset | What | Licence | Notes |
|---|---|---|---|
| `yichiac/crop-type-transfer-learning` (IGARSS 2025, arXiv 2409.09451) | torchgeo training recipes: SSL4EO-S12/SatlasPretrain backbones fine-tuned for crop type; ~100–few-hundred labels enough to transfer | Apache-2.0, pushed 2026-03 | The practical open recipe |
| `torchgeo/harmonized_global_crops` (HF dataset) | 6 harmonized crop-label datasets, 5 continents | CC-BY-SA-4.0 | Training labels to seed a regional model |
| `x-ytong/CropNet` + `x-ytong/CropGlobe` (HF) | cross-region AND cross-hemisphere crop transfer study; >300k samples incl. **Australia** | MIT, pushed 2026-04 | Directly addresses AU hemispheric-shift risk |
| `allenai/rslearn_projects` (OlmoEarth) | rslearn framework: define space-time windows + labels, fine-tune S2/S1 backbones, apply anywhere; actively maintained (pushed 2026-11) | Apache-2.0 | Long-term home for "model-derived geodata" |
| `agroimpacts/croptypemapper` | RNN crop-type mapper with pre-trained parameter files, S1+S2 inputs | no license file (all-inclusive) | Trained on African (Mergdata) labels — legend mismatch for AU/US |
| IGNF FLAIR-HUB (HF: `IGNF/FLAIR-HUB_LPIS-F_*`) | crop-type (23-class) + land-cover segmentation weights, S1/S2 yearly timeseries | Etalab 2.0 | France legend |
| WorldCereal classification module v2.8.2 (Zenodo 23368212) | the consortium's open inference module | see record | Pairs with their system |

Imagery to feed it (free, keyless where noted):
- **AU/NZ + SE Pacific**: Copernicus Australasia Hub (SARA) — Sentinel-1/2,
  free Python API, no key. Best imagery access of any region.
- Global: Copernicus Data Space Ecosystem (free account); US: USGS Landsat
  M2M (free Earthdata login); Sentinel-2 also on Microsoft Planetary Computer.

Pipeline shape (when wired): `derive_crop_type.py` — collect per-field
year-of-interest S1/S2 collection (SARA/CDSE) → assemble image stacks aligned
to field boundary → apply fine-tuned backbone → per-year class raster +
per-field class histograms → same stats/journal/provenance contract as
`download_soilgrids.py`. Compute is laptop-GPU scale (ViT-L inference over
one field-season ≈ minutes on a 12 GB card).

Honest caveat: **no open pre-trained model classifies Australian crops
out-of-the-box** — every ready legend is regional (France LPIS, Africa
Mergdata, US CDL few-shot). The derive route means (1) pick a backbone
recipe above, (2) assemble a modest AU label set (CropGlobe AU samples,
state agDept declarations, or the grower's own trial fields), (3) fine-tune
per region per season. That yields a *region model* in the skill, versioned
like any other provider, replacing "not publicly mapped" with our own
by-year map.

## WorldCereal default models — the global no-fine-tuning layer (wired 2026-11-03)
**Status: WIRED, LIVE-VERIFIED KEYLESS (2026-11-03).** `src/scripts/ingest/apply_worldcereal.py`
runs the full chain — crop-calendar window lookup → keyless Microsoft
**Planetary Computer** STAC fetch (same anonymous-SAS access the NDVI products
already use; **no account**) → 12 monthly Sentinel-2 composites → seasonal
heads → GeoTIFF + sha256 + provenance. Verified on real fields:
- **ia-r1 (Iowa, documented soybeans, 2023, tc-s2)**: cropland dominant,
  crop class **13 = soy** (0-indexed CROPTYPE24 legend confirmed empirically;
  neighbor corn pixels also detected) — keyless end-to-end.
- **au-r1 (Narrabri cotton, 2023)**: both seasons run keyless; SH tc-s1 window
  auto-resolved to Dec 2022–May 2023. Class results carry the AU caveat below.

`--backend cdse` (openEO, free **account**, full S1+S2) is an optional
upgrade; Sentinel-1 is fed as constant NODATA in the default PC mode —
documented accuracy trade-off, printed in every provenance record.
Verified Dataset layout (both backends): one uint16 variable per band, dims
t/y/x, short names B2..B12, VV, VH, SCL, dataMask; **exactly 12 monthly
slots** starting at the season-start month (SH cross-year handled), so the
fetch window is derived from the calendar, not the calendar year.

```bash
export DATA_PIPELINE_DATA_ROOT=... AG_GROWER_SLUG=... AG_FARM_SLUG=...
python src/scripts/ingest/apply_worldcereal.py --field au-r1 --year 2023 \
    --season tc-s2            # window auto-resolved via crop calendar
# --season tc-s1|tc-s2|tc-annual; --start/--end override; --netcdf for a
# pre-built patch; --device cuda for GPU; outputs land in
# fields/<id>/worldcereal/*.tif + manifests/worldcereal_provenance.json
```

Two distinct things, one distinction that matters here:
- The official **global MAPS** (Zenodo record 7875105, v100, CC-BY 4.0,
  ~15–25 GB seasonal zips of COG tiles — range-slicing verified working) cover
  **2021 only** → useless alone for rotation history.
- The **default MODELS** that produced them are open (MIT): the
  `worldcereal-classification` toolbox (Zenodo-archived v2.8.2,
  DOI `10.5281/zenodo.23368212`) ships seasonal classifiers on a Presto
  backbone (`WorldCereal/presto-worldcereal`, NASA Harvest Presto,
  arXiv 2304.14065) and applies them to **any region and any year with
  imagery** — in-process via `worldcereal.local_inference.run_seasonal_inference`
  (no openEO needed) or on CDSE via openEO batch.

First-run requirements (default PC path = **zero accounts**):
- Install from git, version-pinned (NOT on PyPI):
  `pip install 'worldcereal @ git+https://github.com/WorldCereal/worldcereal-classification.git@v2.8.2'`
  (pulls torch, prometheo, openeo, openeo_gfmap…).
- No credentials for the default path: Planetary Computer STAC + anonymous
  SAS tokens (see `lib/satellite_imagery.py`). Only `--backend cdse` needs a
  free Copernicus Data Space API key+secret.
- Model artifacts download from the public artifact URLs pinned in
  `worldcereal.openeo.parameters` (journal the URL+sha256 like any grid).

Legend (v100-era default classes): temporary crops (fractional cover),
**winter cereals**, **spring cereals**, **maize**, active cropland, active
irrigation. **No cotton, no soybean, no sorghum class.** For an AU cotton
field the model gives seasonal-cereal/other-temp-crop/irrigation labels plus
the general temporary-crops mask — informative, but the crop *identity*
resolution is legend-limited by design.

Honest quality statement (what the skill must always report): default models
were trained on a global reference DB (2017–2023, heavily EU/US-biased) and
the Phase-1 paper (ESSD 15:5491, 2023) reports overall crop-type accuracy
~70% that is **strongly region-dependent**. Australia has no published
validation; treat AU predictions as experimental until spot-checked against
known fields (our demo farms double as the first validation set). If local
accuracy matters, fine-tune (next section) — the transfer studies show a few
hundred AU labels close the gap.

