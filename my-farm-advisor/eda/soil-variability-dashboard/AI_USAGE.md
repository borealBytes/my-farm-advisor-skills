# AI Usage in This Project

This document records how AI tools (the opencode agent) were used during
development of the Soil Variability Dashboard.

## Debugging Python Errors

- **Relative import error**: Running `src/dashboard.py` directly failed with
  `ImportError: attempted relative import with no known parent package`. Fixed
  by adding `sys.path.insert(0, ...)` to allow sibling module imports when the
  script is invoked as `python src/dashboard.py`.
- **`gpd.pd.concat` typo**: Incorrectly chained `gpd.pd.concat` instead of
  `pd.concat` in `data_loader.py`. Caught at generation time and corrected.
- **CRS centroid warning**: GeoPandas warned that centroid calculation in a
  geographic CRS (EPSG:4326) may produce incorrect results. Identified the root
  cause and documented it as a pre-existing accuracy note.

## Improving Visualizations

- **Clipped bar values**: Several charts used `textposition="outside"` but
  Plotly's default autoscale ignored the labels. Added dynamic y-axis padding
  (15% headroom) to NDVI, soil health score, and soil properties subplots so
  values are always visible.
- **pH target line hidden**: The pH 6.5 reference line sat above the visible
  area when all fields were below target. Added dynamic range computation that
  always includes the target line with configurable padding.
- **Raw column names on radar**: Replaced internal column names (`avg_om_pct`,
  `avg_cec`, etc.) with human-readable labels (`OM (%)`, `CEC (meq/100g)`, etc.)
  on the field variability radar chart.
- **Removed fixed ranges**: NDVI `yaxis_range=[0,1]` and soil health map
  `zmin=0, zmax=100` were removed to let auto-scaling adapt to actual data.

## Explaining Geospatial Workflows

- Clarified why `GeoSeries.centroid` produces warnings for geographic CRS and
  how the SSURGO-to-boundary merge feeds the choropleth map.
- Documented the grower-level data flow: `data_loader.py` iterates all farms
  under `farms/*`, concatenates SSURGO summaries, boundaries, and NDVI joins
  across farms, and takes weather from the first available farm.

## Generating Alternative Analytical Ideas

- Proposed the **Decision Support Summary** section in the HTML dashboard to
  frame the analysis as actionable guidance rather than raw charts.
- Suggested insight annotations for every chart (e.g., "Most fields fall near
  the optimal target of pH 6.5") to provide immediate interpretive context.
- Recommended the KPI card layout with gradient backgrounds and colour-coded
  soil health thresholds (green/amber/red).

## Improving Dashboard Layout Structure

- **Restructured to proper subskill layout**: Moved source files from a flat
  directory into `src/` with `__init__.py` for clean package organisation.
- **Created skill documentation**: Added `AGENTS.md` (local agent instructions)
  and `GUIDE.md` (comprehensive usage guide) for discoverability through the
  EDA index.
- **Grower-level refactor**: Rewrote `data_loader.py` to iterate **all** farms
  under a grower instead of picking only the first farm, enabling cross-farm
  analysis.
- **CLI improvement**: Changed entry point from `--data-root <path>` to
  `--grower-slug <slug>` with automatic path resolution via
  `DATA_PIPELINE_DATA_ROOT`, matching the runtime contract.
