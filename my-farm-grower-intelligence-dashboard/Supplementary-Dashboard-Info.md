# Supplementary Dashboard Info — Row Crop Intelligence Data Dashboard

## Project Overview

This project delivers a **Grower Field Intelligence & Sustainability
Dashboard** — a reusable skill that gives a farmer, agronomist, or
agri-business stakeholder a single-page view of how all fields under one
grower's operation are performing, combining crop history, vegetation
health, soil health, and weather stress.

The narrative was chosen deliberately to build on, not repeat, earlier
coursework: Assignment #02/#03 already covered single-field-season
analysis in depth, so this project levels up to the **grower-operation
view** — comparing all of a grower's fields side by side to answer
operational questions like "which fields are healthiest, which are at
risk, and where should I look next?"

## Dataset Description

The dashboard integrates four data sources already built during earlier
assignments:

| Dataset | Source | What it provides |
|---|---|---|
| Field boundaries | Assignment #01 | Per-field geometry, acreage |
| Soil (SSURGO) | Assignment #01 | Organic matter %, pH, CEC, drainage, erosion risk |
| Weather | NASA POWER, Assignment #03 | Daily precipitation and temperature, 2021–2025 |
| Crop history | USDA CDL, Assignment #03 | Per-field, per-year dominant crop composition |
| Vegetation health | Sentinel-2 NDVI, Assignment #03 | Peak and mean NDVI, computed via zonal statistics at runtime |

**A note on data scope:** the full `northern-il-grower` dataset as
downloaded includes 10 fields, but investigation during this project
found that 7 of those 10 are demo/sample fields from an upstream
`download_fields(regions=["corn_belt"])` step that pulls fields from
across the entire corn belt region — not a real, contiguous farm. The
final dashboard is scoped to the **3 fields (367.3 acres) that the
existing farm report identifies as the real operation**, in DeKalb
County, IL. This filtering happens entirely within this skill (via a
`--fields` option) and does not modify any upstream pipeline data. Full
detail is in `PROVENANCE.md`.

## Dashboard Explanation

The dashboard is a single self-contained HTML file with five sections:

1. **Crop Rotation Stability Matrix** — a heatmap showing each field's
   crop, year by year, 2021–2025, with a legend covering every crop
   category present in the full (unfiltered) dataset.
2. **Peak-Season NDVI by Crop Type** — boxplots comparing vegetation
   vigor across crop types, axis-locked to the real 0–1 NDVI range.
3. **Field Map — Crop & Soil Overlay** — an interactive choropleth of
   field boundaries, colored by 2025 crop, dynamically zoomed to fit the
   actual fields being shown.
4. **Growing-Season Weather Stress** — 2025 precipitation totals and
   hot-day counts per field, compared against each field's own 5-year
   average.
5. **Soil Health Scorecard** — a composite Soil Health Index (weighted:
   organic matter 0.3, CEC 0.3, pH-in-range 0.2, erosion-risk penalty
   0.2) per field, plotted against the grower-wide average.

A raw data table at the bottom exposes every underlying value so a
reviewer can verify the charts against source numbers directly.

## Analytical Interpretation

*(See `interpretation-draft.md` — the full write-up. Summary below.)*

- All three fields are in corn for 2025; most show a standard corn-soy
  rotation, but the operation's largest field (245 acres) has stayed in
  continuous corn through 2024–2025 — a monoculture stretch worth
  flagging given its size.
- Soil Health Index ranges 0.673–0.869 across the three fields; notably,
  the largest and most rotation-stressed field does not have the best
  soil health, which is the clearest signal in this dataset for where to
  focus follow-up.
- Peak-season NDVI is consistent (0.57–0.63) across all three fields —
  no acute vegetation-stress outliers this season.

## AI Usage Documentation

See `AI-usage.md` for the full account of how AI tools were used
throughout this project, including debugging and a data-quality
discovery that shaped a key project decision.
