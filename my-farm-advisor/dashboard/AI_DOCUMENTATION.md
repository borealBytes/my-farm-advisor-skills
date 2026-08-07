# AI Assistance Documentation

## Overview

This document provides a transparent record of how AI tools assisted in the development of the My Farm Advisor Dashboard skill. AI was used as a collaborative development partner — all outputs were reviewed, validated, and adjusted by the human author.

---

## Areas Where AI Was Used

### 1. Architecture & Design (Significant AI Input)

**What AI did:**
- Suggested Plotly as the dashboard framework based on the requirement for a self-contained HTML output that requires no server.
- Proposed the six-section dashboard layout (KPI cards, soil scatter, field ranking, geospatial map, weather analysis, sustainability gauges) aligned with the assignment rubric.
- Recommended Option B (TIFF-based NDVI extraction via `rasterstats`) for accuracy and variability metrics.

**Human verification & changes:**
- Verified that Plotly was not already in the runtime venv; confirmed it could be installed cleanly.
- Adjusted the section order to prioritize the geospatial map as the centerpiece.
- Added the Conservation Priority Score as an inverse metric for actionable decision-making.

### 2. Metric Formulas (AI-Assisted, Human-Validated)

**What AI did:**
- Drafted the Soil Health Score formula with component weights (pH 25%, OM 25%, drainage 20%, AWC 20%, texture 10%).
- Proposed the Sustainability Index weighting scheme (SHS 40%, rotation 20%, weather 20%, NDVI stability 20%).

**Human verification & changes:**
- Validated scoring functions against real SSURGO data from `ia-grower` (pH ranges 5.5–8.0, OM 1.5–8.0%).
- Adjusted pH scoring curve: changed linear penalty from 10× to 8× per unit outside optimal to avoid over-penalizing slightly acidic Iowa soils.
- Verified that drainage class strings in the runtime data match the scoring logic (e.g., "Moderately well drained" vs "Poorly drained").

### 3. Python Code Generation (AI-Written, Human-Reviewed)

**What AI did:**
- Generated the full module structure (`data_loader.py`, `metrics.py`, `ndvi_extractor.py`, `geospatial.py`).
- Wrote `rasterstats.zonal_stats()` integration for TIFF-based NDVI extraction.
- Built Plotly figure constructors for all six dashboard sections.
- Drafted CLI argument parsing and orchestration logic in `grower_dashboard.py`.

**Human verification & changes:**
- Tested `data_loader.py` against real runtime paths; added column-name fallback logic for `field_id` inference.
- Fixed `ndvi_extractor.py` to handle missing TIFFs gracefully with warning logs instead of crashes.
- Adjusted Plotly map centering to use centroid mean for auto-zoom.
- Added Kaleido PNG fallback export option.

### 4. Data Integration Debugging (AI-Assisted)

**What AI did:**
- Suggested using `ndvi_yearly_summary.json` as a fallback when TIFF extraction fails.
- Recommended pandas merge strategies for joining soil, weather, CDL, and NDVI data on `field_id`.

**Human verification & changes:**
- Confirmed that all runtime tables use `field_id` as the common key.
- Verified GeoJSON CRS handling (WGS84 → Albers → WGS84) for accurate acreage computation.

### 5. Documentation (AI-Drafted, Human-Edited)

**What AI did:**
- Drafted `README.md` with usage examples, interpretation guide, and data source table.
- Generated `SKILL.md`, `AGENTS.md`, and `INDEX.md` following the repository's established metadata patterns.

**Human verification & changes:**
- Verified that all markdown links are relative and valid.
- Ensured the README includes explicit `DATA_PIPELINE_DATA_ROOT` export instructions.
- Added the AI documentation section to the README referencing this file.

### 6. Narrative & Interpretation (Human-Led, AI-Enhanced)

**What AI did:**
- Suggested example interpretation sentences for the dashboard.
- Proposed phrasing for metric explanations in the sustainability section.

**Human verification & changes:**
- Rewrote interpretations to be specific to the Iowa grower dataset (e.g., referencing corn-soybean rotation, tile drainage).
- Ensured interpretations are embedded both in the README and as HTML text blocks inside the dashboard.

---

## What Was NOT AI-Assisted

- **Repository structure decisions** (skill placement under `my-farm-advisor/dashboard/`) were human-made based on existing INDEX.md routing.
- **Validation and testing** against real `ia-grower` data was performed manually by the human author.
- **Git branching** (`Final` branch) and commit decisions were human-driven.
- **Final metric thresholds** (e.g., Conservation Priority > 60 as a flag) were set by the author based on domain knowledge.

---

## Responsible Use Statement

All AI-generated code was:
1. **Reviewed line-by-line** for correctness and safety.
2. **Tested against real data** from the My Farm Advisor runtime.
3. **Adjusted** to match the repository's coding style and conventions.
4. **Verified** that no secrets, API keys, or private data were included in generated outputs.

The human author takes full responsibility for the accuracy and functionality of this dashboard skill.
