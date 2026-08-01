# AI Usage Documentation

## Row Crop Intelligence Dashboard — Final Project

### AI Tools Used

**Primary AI Assistant:** OpenCode (opencode.ai) powered by the `opencode/mimo-v2-free` model.

### How AI Was Used

#### 1. Repository Inspection and Planning
- AI agents explored the entire repository structure (75+ Python scripts, 65+ README files, 5 SKILL.md files)
- Identified all reusable outputs from Assignments 1–3 across 3 growers and 30 fields
- Mapped runtime data at `/home/coder/my-farm-advisor-runtime/` (7.0 GB, 1,415 files)
- Verified file naming conventions and data schemas for CSV, GeoJSON, and Parquet files
- Compared existing work against final project requirements to identify gaps

#### 2. Architecture Design
- Designed the data loader module to read from existing runtime paths without data duplication
- Chose Streamlit as the dashboard framework for rapid interactive development
- Selected Plotly for interactive charts and Folium for geospatial mapping
- Designed a composite sustainability score from SSURGO soil properties

#### 3. Code Generation
- Generated `data_loader.py` with functions to load boundaries, weather, soil, CDL, rotation, and NDVI data
- Generated `app.py` with all dashboard sections: KPIs, EDA charts, interactive map, weather analysis, soil health
- Iteratively fixed file naming conventions based on actual runtime data (state name vs. abbreviation patterns)
- Added written interpretations throughout the dashboard explaining each visualization

#### 4. Testing and Validation
- Tested data loader module to verify all 30 fields load correctly across 3 states
- Verified KPI computation: 30 fields, 3,882 acres, 15.1 avg NDVI scenes, 1.86 mm avg rainfall, 60.8 sustainability score
- Confirmed Streamlit app imports and renders without errors

### What AI Did NOT Do
- AI did not create or modify any existing Assignment 1–3 scripts
- AI did not generate synthetic data — all data comes from the existing pipeline runtime
- AI did not make changes to the repository structure beyond the new `dashboard/` directory
- AI did not commit any changes (waiting for user approval)

### Verification Steps Taken
1. Verified runtime data exists at expected paths
2. Tested all data loading functions independently
3. Confirmed KPI values match expected ranges
4. Verified Streamlit app imports successfully
5. Checked all Plotly and Folium chart generation

### Limitations
- The dashboard relies on the existing runtime data structure; changes to file naming conventions would require updates
- Streamlit's `use_container_width` parameter is deprecated in favor of `width` — future maintenance needed
- Geographic CRS warning when computing centroids (non-blocking, cosmetic only)

### Date
July 31, 2026
