#!/usr/bin/env python3
"""Generate a self-contained HTML report for Assignment 2 Field-Level EDA.

Embeds all PNG images as base64 data URIs for offline viewing.
"""

from __future__ import annotations

import base64
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("/home/coder/my-farm-advisor-runtime/data-pipeline/eda/assignment-2")
REPORT_PATH = OUTPUT_DIR / "assignment-2-field-eda-report.html"

# Image metadata: (relative_path, title, description)
IMAGES = [
    (
        "weather/growing_season_temp_boxplot.png",
        "Figure 1: Growing Season Temperature Distribution",
        "Box plot of daily mean temperatures (May–September) across all three states for 2021–2025. "
        "Nebraska and Illinois show similar median temperatures (~23°C), while Iowa runs slightly cooler (~22°C). "
        "All three states exhibit comparable interquartile ranges, indicating consistent seasonal heat patterns.",
    ),
    (
        "weather/annual_precip_by_field.png",
        "Figure 2: Annual Precipitation per Field",
        "Grouped bar charts showing total annual precipitation for each field, faceted by state. "
        "Nebraska fields consistently receive higher annual precipitation than Illinois and Iowa fields, "
        "reflecting the Platte River valley's moisture availability.",
    ),
    (
        "weather/gdd_comparison.png",
        "Figure 3: Cumulative Growing Degree Days (GDD)",
        "Cumulative GDD curves (base 10°C, cap 30°C) from May 1 through September 30, averaged across 2021–2025. "
        "Individual field trajectories are shown as faint lines; state mean curves are bold. "
        "Nebraska and Illinois accumulate GDD fastest; Iowa lags slightly due to cooler early-season temperatures.",
    ),
    (
        "cdl/crop_distribution_stacked.png",
        "Figure 4: Crop Composition by State and Year",
        "100% stacked bar charts showing the proportion of corn, soybeans, and other land covers "
        "(based on CDL pixel percentages) for each state across 2021–2025. "
        "Illinois is the most corn-dominant; Iowa shows the most pasture/grass; Nebraska maintains a balanced corn/soy rotation.",
    ),
    (
        "cdl/rotation_diversity_hist.png",
        "Figure 5: Crop Rotation Diversity per Field",
        "Histogram of the number of unique crops observed per field over the 2021–2025 period. "
        "Most fields show diversity of 2–3 crops, consistent with standard Corn Belt corn–soy rotations. "
        "A few fields remain single-crop or grass/pasture throughout the period.",
    ),
    (
        "cdl/corn_vs_soy_area_trend.png",
        "Figure 6: Corn vs. Soybean Area Trend",
        "Line chart of estimated corn and soybean area (CDL pixel-count proxy) from 2021–2025, by state. "
        "Illinois corn area is stable and highest; Nebraska shows the strongest soybean presence; "
        "Iowa exhibits year-to-year variability between the two crops.",
    ),
    (
        "boundaries/field_size_distribution.png",
        "Figure 7: Field Size Distribution",
        "Histogram of field sizes (acres) by state with kernel density estimate overlays. "
        "Illinois fields are largest on average (mean ~97 acres); Nebraska fields are smallest (mean ~52 acres), "
        "consistent with intensively managed center-pivot irrigation layouts.",
    ),
    (
        "boundaries/total_acreage_by_grower.png",
        "Figure 8: Total Farm Acreage and Field Count",
        "Dual-axis bar/line chart showing total acreage (bars, left axis) and field count (line, right axis) per state. "
        "Illinois leads in total acreage (~972 acres); all three growers have exactly 10 fields.",
    ),
    (
        "boundaries/size_vs_dominant_crop.png",
        "Figure 9: Field Size vs. Dominant Crop (2025)",
        "Scatter plot of field area (acres) against the dominant CDL crop classification for 2025, colored by state. "
        "No strong size–crop relationship is visible, though larger fields in Illinois tend toward corn dominance.",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def img_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# HTML Assembly
# ---------------------------------------------------------------------------

def build_html() -> str:
    css = """
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        line-height: 1.6;
        max-width: 900px;
        margin: 0 auto;
        padding: 2rem 1rem;
        color: #333;
        background: #fff;
      }
      h1 { font-size: 2rem; border-bottom: 3px solid #2ca02c; padding-bottom: 0.3rem; margin-top: 0; }
      h2 { font-size: 1.5rem; color: #1f77b4; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; margin-top: 2rem; }
      h3 { font-size: 1.15rem; color: #444; margin-top: 1.5rem; }
      table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
      th, td { border: 1px solid #ccc; padding: 0.5rem; text-align: left; }
      th { background: #f5f5f5; }
      img { max-width: 100%; height: auto; display: block; margin: 1rem 0; border: 1px solid #ddd; }
      .caption { font-size: 0.9rem; color: #555; margin-top: 0.5rem; font-style: italic; }
      .highlight { background: #fff3cd; padding: 0.8rem; border-left: 4px solid #ffc107; margin: 1rem 0; }
      .note { background: #e7f3ff; padding: 0.8rem; border-left: 4px solid #2196f3; margin: 1rem 0; }
      ul { margin: 0.5rem 0; }
      code { background: #f4f4f4; padding: 0.15rem 0.3rem; border-radius: 3px; font-size: 0.9rem; }
      a { color: #1f77b4; }
      .footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; font-size: 0.85rem; color: #777; }
    </style>
    """

    # Build image sections
    image_sections = ""
    for rel_path, title, description in IMAGES:
        img_path = OUTPUT_DIR / rel_path
        if img_path.exists():
            b64 = img_to_base64(img_path)
            image_sections += f"""
    <h3>{title}</h3>
    <img src="{b64}" alt="{title}" />
    <p class="caption">{description}</p>
    """
        else:
            image_sections += f"""
    <h3>{title}</h3>
    <p class="caption"><em>Image not found: {rel_path}</em></p>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Assignment 2: Field-Level EDA Report</title>
  {css}
</head>
<body>

<h1>Assignment 2: Field-Level Exploratory Data Analysis</h1>
<p><strong>Generated:</strong> 2026-06-24<br>
<strong>Branch:</strong> assignment-2<br>
<strong>Dataset:</strong> Illinois, Iowa, and Nebraska growers (10 fields each)</p>

<h2>1. Dataset Scope and Grower Locations</h2>
<p>This analysis covers <strong>30 agricultural fields</strong> across three Corn Belt states, representing diverse growing conditions and management practices:</p>

<table>
  <tr><th>Grower Slug</th><th>State</th><th>County</th><th>FIPS</th><th>Fields</th><th>Rationale</th></tr>
  <tr><td><code>il-grower</code></td><td>Illinois</td><td>Adams</td><td>17-001</td><td>10</td><td>Western Illinois corn/soy region</td></tr>
  <tr><td><code>ia-grower</code></td><td>Iowa</td><td>Adair</td><td>19-001</td><td>10</td><td>Southwest Iowa corn/soy belt</td></tr>
  <tr><td><code>ne-grower</code></td><td>Nebraska</td><td>York</td><td>31-167</td><td>10</td><td>Platte River valley; center-pivot irrigation common</td></tr>
</table>

<div class="highlight">
  <strong>Why York County, Nebraska?</strong> York County lies in the Platte River valley, a major corn/soy production area where center-pivot irrigation is extensively practiced. This provides a meaningful climatic and agronomic contrast to the rain-fed Illinois and Iowa fields.
</div>

<h2>2. Field Counts and Data Layers Used</h2>

<table>
  <tr><th>Data Layer</th><th>Source</th><th>Temporal Coverage</th><th>Spatial Resolution</th><th>Fields with Data</th></tr>
  <tr><td>Field Boundaries</td><td>OpenStreetMap / Overpass API</td><td>Snapshot (2026)</td><td>Vector polygons</td><td>30 / 30</td></tr>
  <tr><td>Daily Weather</td><td>NASA POWER (S3 Zarr backend)</td><td>2021-01-01 to 2025-12-31</td><td>0.5° grid, field-centroid sampling</td><td>30 / 30</td></tr>
  <tr><td>Cropland Data Layer (CDL)</td><td>USDA NASS</td><td>2021–2025 (annual)</td><td>30 m raster</td><td>30 / 30</td></tr>
  <tr><td>Crop Rotation Summary</td><td>Derived from CDL time series</td><td>2021–2025</td><td>Per-field</td><td>30 / 30</td></tr>
  <tr><td>SSURGO Soil Data</td><td>NRCS Web Soil Survey / SDA</td><td>Static snapshot</td><td>Map unit polygons</td><td>30 / 30</td></tr>
</table>

<div class="note">
  <strong>Note:</strong> Soil data was generated by the farm pipeline as a side effect but was <strong>excluded from EDA analysis</strong> per assignment instructions (see Section 8).
</div>

<h2>3. Comparison Levels Used</h2>
<p>The EDA employs four nested comparison levels, matched to the data structure and the questions being asked:</p>

<ul>
  <li><strong>Field-level:</strong> Individual field characteristics such as size (acres), dominant 2025 crop classification, and per-field daily weather time series. Example: field size histograms (Figure 7) and size-vs-crop scatter (Figure 9).</li>
  <li><strong>Field-year:</strong> Annual aggregations per field, such as total yearly precipitation (Figure 2) and yearly CDL crop composition. This level captures year-to-year variability within the same field.</li>
  <li><strong>Grower-level:</strong> Aggregations across all 10 fields within a single grower/state. Examples: state mean GDD curves (Figure 3), total farm acreage (Figure 8), and stacked crop composition by state (Figure 4).</li>
  <li><strong>Across-grower:</strong> Direct statistical comparisons among Illinois, Iowa, and Nebraska. Examples: Kruskal-Wallis tests for temperature and precipitation differences, and side-by-side faceted plots.</li>
</ul>

<h2>4. Statistical Visualizations</h2>
<p>The following nine static visualizations were generated. Each is embedded as a base64-encoded PNG for offline viewing.</p>

{image_sections}

<h2>5. Comparison and Correlation Analysis</h2>
<p>To test whether the observed climatic differences among states are statistically robust, Kruskal-Wallis non-parametric tests were performed on two key variables:</p>

<table>
  <tr><th>Test</th><th>Variable</th><th>Statistic</th><th>p-value</th><th>Significant (α=0.05)</th><th>Interpretation</th></tr>
  <tr><td>Kruskal-Wallis</td><td>Growing Season Mean Temperature (°C)</td><td>148.31</td><td>&lt; 0.000001</td><td>Yes</td><td>Highly significant difference across states. Nebraska and Illinois run warmer than Iowa.</td></tr>
  <tr><td>Kruskal-Wallis</td><td>Mean Annual Precipitation (mm)</td><td>17.24</td><td>0.000181</td><td>Yes</td><td>Significant difference across states. Nebraska receives substantially more precipitation than Illinois or Iowa.</td></tr>
</table>

<div class="highlight">
  <strong>Key finding:</strong> Both temperature and precipitation differ significantly across the three states. Nebraska's higher moisture availability (likely reflecting both natural precipitation and irrigation infrastructure in York County) is the strongest distinguishing factor.
</div>

<h2>6. Geospatial Map</h2>
<p>An <strong>interactive Folium HTML map</strong> was generated showing all 30 field boundaries:</p>

<ul>
  <li><strong>Layer control:</strong> Toggle visibility by state (Illinois, Iowa, Nebraska)</li>
  <li><strong>Field polygons:</strong> Each field is rendered as a colored polygon (blue=IL, orange=IA, green=NE)</li>
  <li><strong>Popups:</strong> Hover or click any field to see its ID, area in acres, 2025 dominant crop, and county name</li>
  <li><strong>Base map:</strong> CartoDB Positron (light, clean background emphasizing field shapes)</li>
</ul>

<p><strong>Open the interactive map:</strong> <a href="boundaries/all_fields_map.html" target="_blank">all_fields_map.html</a> (must be opened in a browser; requires internet for Leaflet CDN tiles)</p>

<h2>7. Limitations, Missing Data, and Assumptions</h2>

<ul>
  <li><strong>GDD planting date assumption:</strong> Cumulative GDD was computed from a fixed May 1 start date. Actual planting dates vary by year, state, and farmer practice, which would shift GDD curves.</li>
  <li><strong>NASA POWER grid resolution:</strong> Weather is sampled at field centroids from a 0.5° grid. Large fields may span multiple grid cells, and small fields (< 2 acres) may fall within a single cell shared with non-agricultural land covers.</li>
  <li><strong>CDL resolution:</strong> The 30-meter CDL raster means small fields have few pixels and dominant-crop classifications can be noisy for sub-5-acre parcels.</li>
  <li><strong>Missing NDVI/satellite analysis:</strong> Sentinel-2 and Landsat imagery were downloaded by the farm pipeline but were not analyzed in this EDA. Vegetation index trends were excluded from the assignment scope.</li>
  <li><strong>Mixed-crop fields:</strong> Some fields show multiple CDL crop classes within the same year. The analysis uses the <em>dominant</em> crop (highest pixel percentage), which may oversimplify field management.</li>
  <li><strong>Grass/Pasture classification:</strong> Two Iowa fields are classified as Grass/Pasture in some years. These may represent hay ground, set-aside acres, or CDL misclassification near field edges.</li>
  <li><strong>Statistical test assumptions:</strong> Kruskal-Wallis tests do not assume normality but do assume independent observations. Daily weather observations within the same field are autocorrelated, so the test results should be interpreted as exploratory rather than confirmatory.</li>
</ul>

<h2>8. Soil Analysis Confirmation</h2>
<div class="note">
  <strong>Soil analysis was explicitly excluded from this assignment per the user's instructions.</strong> SSURGO soil data (horizon-level chemistry, texture, drainage) was generated by the farm pipeline as a required side effect but was not loaded, visualized, or interpreted in any EDA output. All charts, statistical tests, and the geospatial map focus exclusively on weather, CDL/cropland, and field boundary data.
</div>

<div class="footer">
  <p>Report generated by the <code>assignment-2-field-eda</code> subskill of My Farm Advisor.<br>
  Runtime data: <code>~/my-farm-advisor-runtime/data-pipeline/eda/assignment-2/</code><br>
  Skill source: <code>my-farm-advisor/eda/assignment-2-field-eda/</code></p>
</div>

</body>
</html>
"""
    return html


def main() -> None:
    html = build_html()
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")
    size_kb = REPORT_PATH.stat().st_size / 1024
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
