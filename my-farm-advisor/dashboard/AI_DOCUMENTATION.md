# AI Assistance Documentation

## Overview

This document provides a transparent record of how AI tools assisted in the development of the My Farm Advisor Dashboard skill. AI was used as a collaborative development partner — all outputs were reviewed, validated, and adjusted by the human author.

---

## Areas Where AI Was Used

### 1. Architecture & Design (Significant AI Input)

**What AI did:**
- Suggested the interactive Folium/Leaflet map approach for the geospatial component, replacing the static matplotlib map that was too small to show field colors clearly.
- Proposed the variable-layer toggling concept — instead of toggling growers, toggle which metric (SHS, SI, NDVI Stability, Weather Resilience, Rotation Score) colors the field polygons.
- Recommended switching from Plotly to matplotlib PNG for all non-map charts after diagnosing the empty-plot issue caused by Plotly's binary JSON format.

**Human verification & changes:**
- Verified Folium and branca could be installed cleanly.
- Adjusted the color normalization to use actual data range (54–90) instead of 0–100, making field color variation clearly visible.
- Added the 5-tier status label system (Poor/Moderate/Good/Excellent etc.) to popups.

### 2. Metric Formulas & Status Labels (AI-Assisted, Human-Validated)

**What AI did:**
- Drafted the 5-tier status thresholds for each metric (SHS, SI, NDVI Stability, Weather Resilience, Rotation Score).
- Suggested the transposed metrics table format (metrics as rows, growers as columns, formula inline).

**Human verification & changes:**
- Validated thresholds against actual data ranges (e.g., SHS spans 59–87, so "Excellent" at ≥85 catches only the top fields).
- Adjusted NDVI Stability thresholds after seeing real values (range 2.6–11.6).
- Verified Weather Resilience thresholds against the 1.0–11.7 range.

### 3. Python Code Generation (AI-Written, Human-Reviewed)

**What AI did:**
- Generated the `build_map_interactive()` function with Folium GeoJson, FeatureGroup layer control, and click popups.
- Wrote the status helper functions (`_shs_status()`, `_si_status()`, etc.).
- Built the transposed metrics table and the 5 analytical highlight bullets.
- Created the multi-year average GDD overlay logic.

**Human verification & changes:**
- Fixed a double-merge bug in `build_map_interactive()` that caused KeyError on `shs`.
- Fixed `branca.colormap.linear.RdYlGn` → `RdYlGn_11` after import error.
- Added `predicted_next_crop` from rotation data to popups.
- Ensured all popups show grower name, acreage, and crop correctly.

### 4. Data Integration Debugging (AI-Assisted)

**What AI did:**
- Suggested loading rotation data for dominant crop display.
- Recommended using `fillna(metrics_df["shs"].mean())` to handle missing SHS values.
- Proposed the 7-day rolling average for precipitation smoothing.

**Human verification & changes:**
- Confirmed rotation data structure (`predicted_next_crop` column exists).
- Verified that `area_acres` is correctly pulled from boundaries for popup display.
- Tested that missing weather columns (T2M_MAX, T2M_MIN) are handled gracefully.

### 5. Visualization Improvement (AI-Assisted)

**What AI did:**
- Suggested adding value labels on top of bars for the soil texture and NDVI charts.
- Proposed the dual-y-axis weather chart (precipitation + temperature).
- Recommended adding multi-year average dashed lines to the GDD chart for climate anomaly context.

**Human verification & changes:**
- Adjusted bar label positions to avoid overlap.
- Set alpha values for dashed lines to 0.4 so they don't overpower 2024 solid lines.
- Added explicit legend entries for solid vs. dashed lines.

### 6. Documentation (AI-Drafted, Human-Edited)

**What AI did:**
- Drafted the updated `README.md` reflecting v6 features.
- Generated `DASHBOARD_INFO.md` with project overview, dataset description, and analytical interpretation.
- Updated `AI_DOCUMENTATION.md` with this session's usage record.

**Human verification & changes:**
- Verified all markdown links are relative and valid.
- Ensured the README includes the correct runtime path and dependency list.
- Added the `DASHBOARD_INFO.md` reference to the README.

---

## What Was NOT AI-Assisted

- **Repository structure decisions** (skill placement under `my-farm-advisor/dashboard/`) were human-made based on existing INDEX.md routing.
- **Validation and testing** against real `ia-grower`, `il-grower`, and `ne-grower` data was performed manually.
- **Git branching** (`Final` branch) and commit decisions were human-driven.
- **Final metric thresholds** and status label breakpoints were set by the author based on actual data distributions.

---

## Responsible Use Statement

All AI-generated code was:
1. **Reviewed line-by-line** for correctness and safety.
2. **Tested against real data** from the My Farm Advisor runtime (30 fields, 3 growers).
3. **Adjusted** to match the repository's coding style and conventions.
4. **Verified** that no secrets, API keys, or private data were included in generated outputs.

The human author takes full responsibility for the accuracy and functionality of this dashboard skill.
