# Colormap standard — soil-property choropleths & DEM/terrain rasters

Adopted 2026-11. This is the decision table that supersedes the ad-hoc choices
in `field-map-frame.md` §"Continuous vs categorical" for the two rejected
figure families (stepped soil-attribute bins; "random" DEM colormaps).
Every URL below was fetched and verified live on 2026-11-05.

## The three rules that settle every case

1. **Scale first.** If the value can be averaged and orders spatially →
   one continuous ramp, monotonically increasing CIELAB lightness (L*) —
   the exact requirement Matplotlib states for perceptually-uniform sequential
   maps (https://matplotlib.org/stable/users/explain/colors/colormaps.html).
   If the value *names* something (map unit, WRB group, crop class) →
   discrete qualitative colors, never a ramp.
2. **Anchored breakpoints.** Use agronomic/legend breakpoints when they exist
   (pH, SOC, texture, CEC, BD, AWC below); otherwise use quantiles of the
   *field's own histogram* — ISRIC generates its own SoilGrids legends with
   natural breaks / quantiles on the global profile histogram, "by visually
   inspecting the histograms to maximize the contrast" (SoilGrids FAQ,
   https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html;
   soil.legends note, https://gsif.r-forge.r-project.org/soil.legends.html).
   Never equal-interval unless the unit itself is physical and round (m, t/ha).
3. **The ramp must pass through the data, not the outliers.** Set vmin/vmax to
   P2–P98 of the clip (never global min/max — one gravel pit or shed roof
   washes out 2 m of tile-drainage microrelief), and choose the ramp's *usable
   dynamic range* by the relief class of the DEM (table below). This is the
   "where the ramps go through" fix: a 4-hue `terrain` map spent on 1–2 m of
   Iowa relief is one muddy green; the same ramp on 10–100 m of upland
   Canadian relief reads perfectly.

## Stepped ISRIC legends vs continuous — the direct answer

Keep the ISRIC *colors and break locations*, drop the *stepping*. The official
SoilGrids SLDs (https://files.isric.org/soilgrids/latest/legends/, per-property
`clay.sld`, `soc.sld`, `phh2o.sld`, `bdod.sld`, `cec.sld`) are ~20–31 quantile
bins whose hexes are themselves sampled from a smooth monotonic pale→dark ramp
(clay: `#f2dac1→#b0773e→…` decreasing L*; SOC: white→grey→dark; pH:
yellow→green→blue at 3.4→9.2). So the stepping is a QGIS legend artifact of a
discretized continuous ramp, not a data truth — for README-quality farm figures
it just throws away contrast resolution.

**Compromise rule (ship this): render soil properties as a continuous ramp
with the ISRIC-style single-hue monotonic colors, and put colorbar TICK LABELS
at the official legend boundaries ± the agronomic breakpoints below.** The
reader gets continuous perception; the agronomist keeps the class edges.
Use stepped discrete color only where the classification is authoritative:
soil map units, WRB/Soil Taxonomy groups, texture classes, land cover.

## Master recommendation table

| Figure | Scale | Colormap (matplotlib / hex) | Break rule (with numbers) | Lightness req. | CVD note | Rationale + citation |
| --- | --- | --- | --- | --- | --- | --- |
| SOC gC/kg (0–5/5–20/20–50/50+ agronomic tiers) | continuous, right-skewed | ISRIC-style white→grey→dark brown (vendored `soil.legends` SOC colors) or `viridis` | continuous ramp; ticks at 5/20/50 g/kg + ISRIC natural-break values; else quantiles | monotone L* (ISRIC SOC ramp already is) | safe (luminance-ordered); `viridis` fully safe | soil-property ramps should be sequential with agronomic anchors; ISRIC uses quantile/natural breaks — SoilGrids FAQ + legends dir (above) |
| pH (H₂O) — diverging | continuous, signed about **7.0** | `RdBu_r` / Crameri `vik` (luminance-symmetric) / diverging ColorBrewer `BrBG` | center fixed at pH 7.0; ticks at 4.5/5.5/6.5/7.5 | L* decreases symmetrically from the neutral centre | `RdBu` uses luminance separation, survives red–green CVD; test with `vik` (Crameri maps are CVD-safe by design — https://www.fabiocrameri.ch/colourmaps/) | diverging only when a meaningful midpoint exists; pH 7 is that midpoint — ColorBrewer diverging rules https://colorbrewer2.org/ |
| Clay % (texture fraction; also silt/sand) | continuous | ISRIC pale-tan→dark-brown (clay.sld colors) or `YlBr` single-hue sequential | ticks at USDA texture-clay boundaries **20 / 27 / 40 %** (sandy-loam / loam / clay-loam / clay limits along the clay axis); else quantiles | monotone L* | single hue + luminance = safe | texture-class boundaries are the agronomic reference; Soil Texture Calculator (NRCS): https://www.nrcs.usda.gov/resources/education-and-teaching-materials/soil-texture-calculator |
| CEC cmol(c)/kg (5/10/20/30 tiers) | continuous, skew low | `viridis` or ISRIC tan-brown ramp | ticks at 5/10/20/30; else quantiles | monotone L* | viridis safe | CEC fertility tiers are agronomic, not statistical |
| Bulk density Mg/m³ (1.0/1.2/1.4/1.6) | continuous | `cividis` or single-hue `Greys`-style | ticks at 1.0/1.2/1.4/1.6 (1.4 = common compaction threshold; 1.6 sand/loam limit class) | monotone L* | cividis was built for red-green CVD — Nuñez, Anderton & Renslow 2018, PLOS ONE 13(7):e0199239, https://doi.org/10.1371/journal.pone.0199239 | BD interpretation is threshold-driven (compaction) |
| AWC mm/mm (0.08/0.12/0.16/0.20) | continuous | `YlGnBu` or `viridis` | ticks at 0.08/0.12/0.16/0.20 (soil-plant-available-water classes); else quantiles | monotone L* | `YlGnBu` luminance-ordered, safe | plant-available-water bands are agronomic classes |
| Soil map units / WRB & SoilTaxa classes / texture classes | **categorical** | ≤8 classes: Okabe–Ito (E69F00 56B4E9 009E73 F0E442 0072B2 D55E0E CC79A7 + black/grey); >8: ColorBrewer qualitative or Paul Tol / Krzywinski 12-15, plus polygon labels or hatches | discrete unique values; aggregate rare units into "miscellaneous" (NRCS generalization practice) | no ordering implied — hues may vary, lightness may vary | Okabe–Ito designed CVD-safe (Color Universal Design): https://jfly.uni-koeln.de/color/ ; Wong 2011 Nat Methods 8:441 https://doi.org/10.1038/nmeth.1618 | categorical data must not be forced onto a ramp; map-unit symbolization/generalization: USDA NRCS Soil Survey Manual (2017) ch. 4 "Soil Mapping Concepts" (connotative legends) https://www.nrcs.usda.gov/sites/default/files/2022-09/SSM-ch4.pdf ; Web Soil Survey https://websoilsurvey.nrcs.usda.gov/App/HomePage.htm |
| Global/regional soil class maps (context only) | categorical, official colors | FAO/UNESCO legend colors: Soil Map of the World legend sheet https://www.fao.org/fileadmin/user_upload/soils/docs/Soil_map_FAOUNESCO/acrobat/Africa_VI.pdf ; Soil Atlas of Africa (FAO/JRC 2015) https://www.fao.org/3/i3437e/i3437e.pdf | reuse published colors verbatim; do not re-color | n/a | legacy colors have CVD-risk pairs — label polygons | reuse-the-standard, like SoilGrids' own `wrb.qml`/`MostProbable.rat.xml` (https://files.isric.org/soilgrids/latest/data/wrb/MostProbable.rat.xml) |
| Crop / land cover (WorldCereal, ESA WorldCover, CDL) | categorical, official palette | EWOC/WorldCereal official legend CSV (already vendored): https://auxdata.terrascope.be/worldcereal/legend/WorldCereal_LC_CT_legend_latest.csv ; ESA WorldCover palette at https://esa-worldcover.org/en/data-access | discrete; unknown = white swatch + grey edge (already repo rule) | n/a | official palettes chosen for contrast; label | official product colors beat any designer ramp |
| **DEM — high relief (>50 m; 25–30 m SRTM/NASADEM/Copernicus uplands)** | continuous | hypsometric-style multi-hue OK at this range: `terrain`, Crameri `greenland`/`hawaii`, or Esri-style green→brown→white | continuous stretch P1–P99.5; manual breaks at *meaningful terrain* (thalweg, floodplain, terrace, crest elevations) — Esri's own guidance for classified/stretched raster symbology https://doc.esri.com/en/arcgis-pro/latest/help/data/imagery/symbology-pane.html | L* roughly monotone (acceptable to trade for hypsometric convention only above 50 m) | prefer Crameri/viridis if figure also needs greyscale print | multi-hue ramps "read" when the range is large; Esri: pick breaks from statistics (min/max/mean/std) — same docs |
| **DEM — low relief (<10 m; 1 m LiDAR/3DEP tile land, 1–2 m relief)** | continuous | **single-hue sequential or perceptually-uniform: `cividis`** (or `viridis`, `crameri:bilby`) — NOT `terrain`/rainbow | stretch to P2–P98 of the field clip; ticks every round metre; if signal is still flat, plot **relative elevation** (DEM − detrended median surface) diverging (`vik`/`RdBu_r`) centered at 0 | monotone L*, strict — microrelief lives in luminance differences | cividis is the CVD-optimized ramp (Nuñez 2018 above) | the ramp must spread across the *field's actual value range*; a 4-hue DEM colormap maps the whole scene into one segment and hides the signal ("where the ramp goes through") |
| Hillshade (base under any tint) | continuous | greyscale only | no breaks; **z-factor / vertical exaggeration ×2–×3 on low relief, ×1 on high relief** | — | greyscale = universally safe | Esri defaults: azimuth **315° (NW)**, altitude **45°**; grey 0–255; combine with transparency — "placing an elevation raster on top of a hillshade raster, and adjusting the transparency" https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/how-hillshade-works.html (same at pro.arcgis.com .htm) |
| **Hillshade + elevation composite (the standard terrain figure)** | two-layer | greyscale hillshade under semi-transparent elevation tint (tint **opacity ≈ 0.45–0.65**, per DEM row above) | same break rules as DEM row | tint L* monotonic; hillshade carries the relief | safe if DEM row followed | Esri's documented pattern; hue encodes elevation, luminance encodes relief, neither cancels the other |
| Slope % (0–2/2–5/5–10/10–18/18+) | continuous, positive-skew | `YlOrBr` / `Reds` / `cividis` | continuous ramp + ticks at 2/5/10/18 % (NRCS conservation slope classes); on flat fields also cap vmax at P98 so the whole ramp is used | monotone L* | luminance-ordered ramps safe | slope classes are erosion-management anchors; quantile stretch otherwise |
| Aspect (azimuth) | **cyclic** | hue wheel: `hsv` or a manual 0–360 ColorBrewer-derived wheel; multiply/blend with hillshade luminance (standard practice) | fixed 0–360, ticks at N/E/S/W; **no breaks, no sequential map** (fake seam at N) | hue varies by design; carry luminance via the hillshade blend | pure-hue wheel fails red-green CVD → the hillshade luminance modulation rescues it; label cardinal faces | cyclic quantities need cyclic colormaps (matplotlib doc, cyclic section) |
| TWI (ln(a/tanβ)) | continuous, positive-skew | blue-ordered sequential: `YlGnBu` / `crameri:oslo` / `cividis` | **quantiles** (3/5/8 classes at ~Q25/50/80) — absolute TWI scales with cell size, so classes must be field-relative, not global | monotone L* | luminance-ordered safe | TWI definition Beven & Kirkby 1979, https://doi.org/10.1080/02626667909491883; quantile practice per ISRIC/ColorBrewer sequential+quantile advice |
| Flow accumulation (D8 upstream cells) | continuous, power-law | sequential on **log₁₀**: `Blues`, `cividis`, or Crameri `bath` | transform log10(upstream cells) first, then quantiles/deciles; axis must read `log₁₀ upstream cells` (already repo rule) | monotone L* after log | safe | raw power-law under any linear ramp = one dark gully; Esri reclassifies on log — https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/how-flow-accumulation-works.html ; Strahler orders for the channel vector: https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/how-stream-order-works.html |
| NDVI / vegetation index (−1…1) | continuous | diverging brown→tan→green (`BrBG`-style) **or** `RdYlGn` with fixed bands 0.2/0.4/0.6/0.8; if CVD-critical figure use `viridis`/`cividis` + the same bands | **fixed bands 0.2 / 0.4 / 0.6 / 0.8** (soil 0–0.1, sparse 0.2, moderate 0.4, dense 0.6, vigorous 0.8); ticks on colorbar | L* monotone toward the green end | `RdYlGn` is the classic red-green trap — mitigate with the luminance peak at yellow or ship `cividis` | NDVI value→cover meaning: NASA Earth Observatory https://science.nasa.gov/earth/earth-observatory/measuring-vegetation-ndvi-evi/ and https://www.earthdata.nasa.gov/topics/land-surface/normalized-difference-vegetation-index-ndvi |

## Fixed breakpoint block (paste into the renderer config)

| Property | Unit | Ticks on continuous ramp | Source of the numbers |
| --- | --- | --- | --- |
| pH (H₂O) | pH | diverging center 7.0; ticks 4.5, 5.5, 6.5, 7.5 | agronomic; SoilGrids ×10 legend divides to 3.4–9.2 (`phh2o.sld`) |
| SOC | gC/kg | 5, 20, 50 | agronomic SOC tiers; ISRIC quantile bins for color |
| Clay | % | 20, 27, 40 (loam/clay-loam/clay texture limits) | USDA texture triangle (NRCS texture calculator) |
| Silt / Sand | % | quantiles (no standard classes) | — |
| CEC | cmol(c)/kg | 5, 10, 20, 30 | fertility classes |
| Bulk density | Mg/m³ | 1.0, 1.2, 1.4, 1.6 | compaction thresholds |
| AWC | mm/mm (v/v) | 0.08, 0.12, 0.16, 0.20 | plant-available-water classes |
| Slope | % | 2, 5, 10, 18 | NRCS-style conservation classes |
| TWI | dimensionless | field quantiles (≈Q25/50/80), NOT global | resolution-dependent index |
| Flow acc. | log₁₀ cells | deciles of log domain | power-law distribution |
| NDVI | index | 0.2, 0.4, 0.6, 0.8 | NASA EO interpretation bands |

## Relief classifier (decides the DEM row automatically)

```text
relief = P99(elev) − P1(elev) within the buffered field clip
  relief > 50 m   → high-relief row (multi-hue/hypsometric OK)
  10–50 m         → medium: single stretch P2–P98, prefer sequential
  < 10 m          → low-relief row: cividis + P2–P98 + hillshade ×2–3 z,
                    else relative-elevation diverging
```

## Corrections to my sources (for the record)

- `10.5194/gmd-11-2541-2018` exists but is **van Tongeren et al., StagLab 3.0** —
  not the Crameri colormap paper. Correct Crameri citations: **dataset**
  Crameri, Shephard & Heron 2018, *Scientific colour maps*, Zenodo,
  https://doi.org/10.5281/zenodo.1243862 + site https://www.fabiocrameri.ch/colourmaps/ ;
  **journal** Crameri, Heron & Shephard 2020, *The misuse of colour in science
  communication*, Nat. Commun. 11:5444, https://doi.org/10.1038/s41467-020-19160-7 (verified).
- "Datta (color blindness)" → the actual peer-reviewed cividis paper is
  **Nuñez, Anderton & Renslow 2018** (https://doi.org/10.1371/journal.pone.0199239).
- viridis attribution: Smith & van der Walt, matplotlib PR
  https://github.com/matplotlib/matplotlib/pull/5197 (2015; live), and the
  Matplotlib docs' "Perceptually Uniform Sequential" family (verified).
- Crameri's maps ship with GMT ("Generic Mapping Tools" colour tables) — cite
  fabiocrameri.ch rather than GMT.
- ColorBrewer scheme taxonomy: https://colorbrewer2.org/learnmore/schemes.html
  (sequential/diverging/qualitative definitions).
- The old NRCS texture-triangle URL (nrcs…cid=nrcs142p2_054253) is dead (404);
  the NRCS Soil Texture Calculator page above is live.
- Esri hillshade doc default azimuth/altitude (315°/45°) and the
  elevation-on-transparent-hillshade pattern: both quoted from the live doc.
