# Supplementary Dashboard Information

## Project Overview

The My Farm Advisor Dashboard is a reusable skill that generates interactive, self-contained HTML dashboards from the My Farm Advisor data pipeline. It analyzes all fields for all growers in the runtime dataset and produces a single-page decision-support tool that can be opened in any browser without a web server.

### Design Goals

1. **Reusable at the grower level** — Works for a single grower or aggregates across all growers
2. **Self-contained output** — Single HTML file with embedded charts and maps
3. **Decision-oriented** — Not just data display; includes analytical interpretation and actionable recommendations
4. **Interactive where it matters** — The geospatial map is interactive (zoom, pan, layer toggling, click popups); all other charts are static PNG for guaranteed rendering

---

## Dataset Description

### What Data Is Analyzed

The dashboard processes data for **30 fields across 3 growers**:

| Grower | State | Fields | Total Acres |
|--------|-------|--------|-------------|
| Iowa | Iowa | 10 | ~389 ac |
| Illinois | Illinois | 10 | ~1,158 ac |
| Nebraska | Nebraska | 10 | ~1,142 ac |
| **Total** | | **30** | **~2,689 ac** |

### Data Sources

| Layer | Source | Temporal Coverage | Spatial Resolution |
|-------|--------|-------------------|-------------------|
| Field Boundaries | OpenStreetMap / farm pipeline | Static | Vector polygons |
| Soil | NRCS SSURGO | Static (soil survey) | 1:24,000 scale |
| Weather | NASA POWER | Daily, 2021–2025 | 0.5° × 0.5° |
| Crop / Rotation | USDA NASS CDL | Annual, 2021–2025 | 30m |
| NDVI | Sentinel-2 composites | Annual composites, 2021–2025 | 10m |

### Key Derived Metrics

| Metric | Data Used | Calculation |
|--------|-----------|-------------|
| Soil Health Score (SHS) | SSURGO pH, OM, drainage, AWC, texture | Weighted sum: pH(25) + OM(25) + drainage(20) + AWC(20) + texture(10) |
| Sustainability Index (SI) | SHS + rotation + weather + NDVI | SHS×0.40 + rotation_score + weather_resilience + ndvi_stability_score |
| NDVI Stability | Multi-year NDVI composites | (1 - CV/max_CV) × 20 |
| Weather Resilience | NASA POWER daily | Drought score + heat stress score |
| Rotation Score | 5-year CDL history | Shannon diversity / 2.0 × 20 |

---

## Dashboard Explanation

### Layout (Top to Bottom)

1. **Header** — Title, field count, acreage, focus year
2. **KPI Cards** — 6 summary metrics at a glance
3. **Interactive Map** — Folium/Leaflet with 5 toggleable variable layers:
   - Soil Health Score (default)
   - Sustainability Index
   - NDVI Stability
   - Weather Resilience
   - Rotation Score
   
   Click any field to see a popup with all 5 variables, their values, 5-tier status labels, grower name, acreage, and predicted crop.

4. **Soil Texture + NDVI** — Side-by-side: grouped soil particle bars + NDVI ranking
5. **Weather + GDD** — Side-by-side: precipitation/temperature by DOY + cumulative GDD with multi-year average
6. **Sustainability Metrics Table** — Metrics as rows, growers as columns, formulas inline
7. **Field Data Summary** — 30-row table with all per-field data
8. **Key Highlights** — 5 analytical bullets for decision-making

### Interactive Map Controls

- **Layer control (top-right)** — Toggle which variable colors the field polygons
- **Zoom (top-left)** — Mouse wheel or +/- buttons
- **Click popup** — Shows full field profile with status labels
- **Legend (bottom-left)** — Color scale for the active variable

---

## Analytical Interpretation

### What the Data Shows

1. **Geographic Gradient** — Nebraska dominates soil health (85.0 avg SHS), Illinois lags (71.8), Iowa sits in between (83.4). This is driven by texture: Illinois fields are sandier (lower water/nutrient retention).

2. **Rainfall-Soil Inverse Relationship** — Illinois gets the most rain (10,157mm) but has the worst soil. Nebraska is driest (6,847mm) but has the best soil. This suggests rainfall alone does not build soil health; texture and organic matter matter more.

3. **NDVI Compensates** — Illinois shows the highest NDVI (0.381) despite poor soil, indicating that abundant rainfall can produce vigorous crop biomass even on marginal soil.

4. **Weather Resilience is a Drag** — Nebraska's excellent soil (SHS 85.0) is undermined by poor weather resilience (1.0), dropping its SI below Iowa's. This means drought/heat stress is Nebraska's biggest risk.

5. **Internal Heterogeneity** — Within Illinois alone, SHS ranges 59.2–83.6 (a 24-point spread), showing that even within one state, field conditions vary dramatically.

### Recommended Actions

| Issue | Target | Action |
|-------|--------|--------|
| Low SHS (< 65) | Illinois sandy fields | Lime + organic matter programs |
| Drought risk | Nebraska | Irrigation investment, cover cropping |
| Balanced profile | Iowa | Maintain with precision variable-rate fertilizer |
| NDVI instability | Fields with high CV | Cover cropping to reduce year-to-year variation |
| Poor rotation | Mono-culture fields | Diversify to corn-soybean rotation |

---

## AI Usage Documentation

See [`AI_DOCUMENTATION.md`](AI_DOCUMENTATION.md) for a detailed record of how AI tools were used during development.

### Summary of AI Assistance

- **Architecture & design** — AI suggested the Folium interactive map approach and the variable-layer toggling concept
- **Debugging** — AI helped diagnose the empty plot issue (Plotly JSON `bdata` format not rendering) and recommended switching to matplotlib PNG
- **Code generation** — AI wrote the Folium map builder, status label logic, popup HTML, and transposed metrics table
- **Visualization improvement** — AI suggested actual data-range color normalization for the map, multi-year average GDD lines, and value labels on bars
- **Documentation** — AI drafted README updates and this supplementary document

All AI-generated code was reviewed line-by-line, tested against real data, and adjusted to match repository conventions.
