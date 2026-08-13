# AI Usage Documentation

This project utilized AI tools (specifically, GitHub Copilot / OpenCode AI assistant) throughout the development workflow. All outputs were reviewed, verified, and modified by the human developer. This document describes how AI was used and what was verified.

## How AI Was Used

### 1. Code Architecture & Design
- **AI assisted with**: Structuring the dashboard builder into modular classes (`DataLoader`, `ChartBuilder`, `MapBuilder`, `DashboardBuilder`)
- **Human verified**: Ensured the class structure aligns with Python best practices and separation of concerns
- **Changes made**: Simplified some over-engineered suggestions; merged small helper functions

### 2. Plotly & Folium Integration
- **AI assisted with**: Writing Plotly figure code for the combined climate/NDVI/SHI chart and the dual-axis weather anomaly panel
- **Human verified**: All chart data inputs, axis labels, color schemes, and legend layout
- **Changes made**: Replaced the 5-chart carousel with a single combined two-panel chart for 2021–2025

### 3. Soil Health Index Formula
- **AI assisted with**: Researching established soil health scoring methodologies and suggesting weight distributions
- **Human verified**: Weights were cross-referenced against USDA NRCS guidelines, Cornell CASH methodology, and peer-reviewed literature
- **Changes made**: Adjusted OM weight from 35% to 30% to give more balance to AWS; added drainage adjustment based on local agronomy knowledge

### 4. Geospatial Workflow (SoilGrids)
- **AI assisted with**: Writing rasterio window-reading code for SoilGrids COG VRTs, CRS transformation from WGS84 to Interrupted Goode Homolosine
- **Human verified**: Bounding box calculations, zonal stats accuracy, and scaling factors (×0.1 for SoilGrids data units)
- **Changes made**: Added error handling for network timeouts; documented the API limitation when service proved too slow

### 5. Debugging & Troubleshooting
- **AI assisted with**: Interpreting Python tracebacks, suggesting fixes for `Path.iterdir()` sorting issues, and resolving module import errors
- **Human verified**: Each fix was tested independently before committing
- **Changes made**: Several AI-suggested fixes were rejected in favor of simpler approaches (e.g., manual manifest rebuilding vs. re-running full pipeline)

### 6. Documentation
- **AI assisted with**: Drafting README sections, methodology write-ups, and this AI usage document
- **Human verified**: All factual claims about data sources, formulas, and analytical findings
- **Changes made**: Rewrote the analytical interpretation section to accurately reflect the weak correlation finding rather than forcing a preconceived narrative

### 7. Dashboard Layout & UX
- **AI assisted with**: HTML/CSS structure for the Bootstrap grid, responsive layout suggestions, and color palette choices
- **Human verified**: Visual hierarchy, accessibility contrast ratios, and mobile responsiveness
- **Changes made**: Increased map height from 500px to 700px for better visibility; adjusted sidebar proportions

## What Was NOT AI-Generated

- The analytical hypothesis ("soil health drives yield stability") was developed by the human analyst based on coursework and literature review
- Field-level agronomic interpretations (e.g., why osm-1360394834 has low SHI) were based on direct inspection of SSURGO data
- The decision to attempt SoilGrids integration and the subsequent decision to fall back to SSURGO-only were human judgments based on timeline and API status
- The correlation summary text in the dashboard was human-written to accurately reflect the statistical finding rather than the expected result

## Verification Checklist

| Component | AI Generated | Human Verified | Tested |
|---|---|---|---|
| SHI formula weights | Yes | Yes | Yes (cross-checked with USDA/Cornell) |
| Min-max normalization | Yes | Yes | Yes (spot-checked 3 fields) |
| Drainage adjustment | Yes | Yes | Yes (manual lookup of each field) |
| NDVI zonal stats | Yes | Yes | Yes (compared with rasterio manual read) |
| Weather anomaly calc | Yes | Yes | Yes (compared with manual Excel calc) |
| Spearman correlation | Yes | Yes | Yes (scipy.stats.spearmanr) |
| Folium map colors | Yes | Yes | Yes (visual inspection in browser) |
| Plotly charts | Yes | Yes | Yes (hover data verified) |
| HTML layout | Yes | Yes | Yes (Chrome + Firefox) |
| Documentation | Yes | Yes | Yes (fact-checked all URLs) |

## Transparency Statement

AI tools were used as a coding and writing assistant, similar to an IDE with autocomplete or a grammar checker. All analytical decisions, hypothesis formulation, and final interpretations were made by the human developer. The AI did not have access to private data or make autonomous decisions about project scope.

## Tools Used

- **OpenCode AI Assistant** (powered by litellm/opencode-go/kimi-k2.6): Primary coding assistant for Python scripts, HTML/CSS, and documentation
- **GitHub Copilot** (if available in editor): Inline code completion for pandas/geopandas syntax

## Date

Project completed: 2025-07-31
Last dashboard update: 2026-08-13
