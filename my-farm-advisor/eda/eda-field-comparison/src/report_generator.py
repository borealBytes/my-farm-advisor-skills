#!/usr/bin/env python3
"""One-time EDA report generator — creates DocX and HTML from field comparison outputs.

Usage:
    export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
    python src/report_generator.py

Generates:
    ${OUTPUT_DIR}/eda_report.docx
    ${OUTPUT_DIR}/eda_report.html
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FIGURES = [
    ("01_boundary_size_distribution.png", "Figure 1", "Field size distribution by state (2021–2025 average)."),
    ("02_boundary_count_vs_acreage.png", "Figure 2", "Field count vs total acreage by state."),
    ("03_cdl_dominant_crop_share.png", "Figure 3", "Dominant crop share by state."),
    ("04_cdl_crop_diversity.png", "Figure 4", "Crop diversity index by field and state."),
    ("05_cdl_corn_vs_soy.png", "Figure 5", "Corn vs soybean acreage correlation (2025)."),
    ("06_weather_gdd_distribution.png", "Figure 6", "Growing Degree Days (GDD) distribution by state."),
    ("07_weather_precip_variability.png", "Figure 7", "Precipitation variability (CV) by state."),
    ("08_weather_temp_precip_correlation.png", "Figure 8", "Monthly temperature vs precipitation correlation."),
    ("09_synthesis_three_farms.png", "Figure 9", "Cross-grower synthesis: six metrics side-by-side."),
    ("10A_geospatial_fields_only.png", "Figure 10A", "Geospatial field boundary map."),
    ("12_dominant_crop_share_trend.png", "Figure 12", "Dominant crop share trend over time (2021–2025)."),
    ("14_crop_composition_by_state.png", "Figure 14", "Crop composition by state (mean pct)."),
    ("15_crop_acreage_share_trend.png", "Figure 15", "Crop acreage share by year (2021–2025)."),
    ("16_crop_acreage_by_state.png", "Figure 16", "Crop total acreage by state (2021–2025 sum)."),
]

REPORT_TITLE = "My Farm Advisor — Field-Level Exploratory Data Analysis Report"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _img_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _img_size(path: Path) -> tuple[int, int]:
    img = Image.open(path)
    return img.size


# ---------------------------------------------------------------------------
# HTML Report
# ---------------------------------------------------------------------------
def build_html(output_dir: Path) -> Path:
    out = output_dir / "eda_report.html"
    
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="UTF-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>{REPORT_TITLE}</title>",
        "  <style>",
        "    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; color: #333; }",
        "    h1 { font-size: 24px; border-bottom: 3px solid #2ca02c; padding-bottom: 8px; }",
        "    h2 { font-size: 18px; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 4px; color: #1a1a1a; }",
        "    h3 { font-size: 15px; margin-top: 20px; color: #444; }",
        "    .figure { margin: 16px 0; text-align: center; }",
        "    .figure img { max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; }",
        "    .caption { font-size: 12px; color: #666; margin-top: 4px; }",
        "    .highlight { background-color: #f0f8ff; padding: 12px; border-left: 4px solid #1E90FF; margin: 12px 0; }",
        "    .note { background-color: #fff8dc; padding: 12px; border-left: 4px solid #FFB90F; margin: 12px 0; font-size: 13px; }",
        "    table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }",
        "    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
        "    th { background-color: #f5f5f5; }",
        "    @media print { .page-break { page-break-after: always; } }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>{REPORT_TITLE}</h1>",
        f"  <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
    ]
    
    # Page 1 content
    html_parts.extend(_page1_html(output_dir))
    html_parts.append('  <div class="page-break"></div>')
    
    # Page 2 content
    html_parts.extend(_page2_html(output_dir))
    
    html_parts.extend([
        "</body>",
        "</html>",
    ])
    
    out.write_text("\n".join(html_parts))
    print(f"  Saved: {out.name}")
    return out


def _page1_html(output_dir: Path) -> list[str]:
    parts = []
    parts.append("  <h2>1. Dataset Scope & Grower Locations</h2>")
    parts.append("  <p>This analysis covers three growers across the US Corn Belt, each with 10 fields tracked from 2021 to 2025:</p>")
    parts.append("  <table>")
    parts.append("    <tr><th>Grower</th><th>State</th><th>County</th><th>Fields</th><th>Primary Crops</th></tr>")
    parts.append("    <tr><td>northern-illinois-grower</td><td>Illinois</td><td>DeKalb</td><td>10</td><td>Corn, Soybeans, Alfalfa</td></tr>")
    parts.append("    <tr><td>northern-iowa-grower</td><td>Iowa</td><td>Floyd</td><td>10</td><td>Corn, Soybeans, Grass/Pasture</td></tr>")
    parts.append("    <tr><td>nebraska-grower</td><td>Nebraska</td><td>Hamilton</td><td>10</td><td>Corn, Soybeans (highly dominant)</td></tr>")
    parts.append("  </table>")
    
    parts.append("  <h2>2. Data Layers Used</h2>")
    parts.append("  <ul>")
    parts.append("    <li><strong>Field boundaries:</strong> GeoJSON polygons from OpenStreetMap-derived field definitions</li>")
    parts.append("    <li><strong>Cropland Data Layer (CDL):</strong> USDA NASS crop composition tables per field per year (crop_code, crop_name, pct, acreage)</li>")
    parts.append("    <li><strong>Crop rotation:</strong> 5-year rotation sequences, diversity index, predicted next crop</li>")
    parts.append("    <li><strong>Weather:</strong> NASA POWER daily weather (T2M, T2M_MIN, T2M_MAX, PRECTOTCORR, GDD) per field</li>")
    parts.append("    <li><strong>GDD reference:</strong> County-level Growing Degree Day parquet files (2021–2025)</li>")
    parts.append("  </ul>")
    
    parts.append("  <h2>3. Comparison Levels</h2>")
    parts.append("  <p>Four analytical levels were used:</p>")
    parts.append("  <ul>")
    parts.append("    <li><strong>Field:</strong> Per-field boundary size, crop composition, and acreage stability</li>")
    parts.append("    <li><strong>Field-year:</strong> Year-over-year changes in dominant crop share, crop composition, and field size</li>")
    parts.append("    <li><strong>Grower (state-level):</strong> Aggregated metrics per farm (mean field size, crop diversity, GDD, precip CV)</li>")
    parts.append("    <li><strong>Across-grower:</strong> Side-by-side comparison of Illinois, Iowa, and Nebraska farms</li>")
    parts.append("  </ul>")
    
    parts.append("  <h2>4. Category A: Field Boundary Analysis</h2>")
    parts.append("  <p>Figures 1–2 compare field size distributions and operational scale across states.</p>")
    parts.extend(_embed_figure(output_dir, "01_boundary_size_distribution.png", "Figure 1", "Field size distribution by state (2021–2025 average)."))
    parts.extend(_embed_figure(output_dir, "02_boundary_count_vs_acreage.png", "Figure 2", "Field count vs total acreage by state."))
    parts.append("  <div class='highlight'>")
    parts.append("    <strong>Key finding:</strong> Nebraska fields are smaller (~265 ac avg) and more uniform. Illinois fields are largest (~387 ac) with wider spread. All three growers have 10 fields, but total acreage differs sharply (IL ~3,871 ac, IA ~3,696 ac, NE ~2,652 ac).")
    parts.append("  </div>")
    
    parts.append("  <h2>5. Category B: CDL / Cropland Analysis</h2>")
    parts.append("  <p>Figures 3–5 examine crop dominance, diversity, and the corn-soybean trade-off.</p>")
    parts.extend(_embed_figure(output_dir, "03_cdl_dominant_crop_share.png", "Figure 3", "Dominant crop share by state."))
    parts.extend(_embed_figure(output_dir, "04_cdl_crop_diversity.png", "Figure 4", "Crop diversity index by field and state."))
    parts.extend(_embed_figure(output_dir, "05_cdl_corn_vs_soy.png", "Figure 5", "Corn vs soybean acreage correlation (2025)."))
    parts.append("  <div class='highlight'>")
    parts.append("    <strong>Key findings:</strong> (1) Nebraska is the most monoculture — dominant crop share ~76%. Iowa is most diverse at ~53%. (2) Crop diversity index: IL ~2.0, IA ~1.8, NE ~1.7 unique crops. (3) Corn vs soy correlation is weakly positive (r=0.38, p=0.049, R²=14%) — larger fields grow more of both crops rather than trading off.")
    parts.append("  </div>")
    
    return parts


def _page2_html(output_dir: Path) -> list[str]:
    parts = []
    parts.append("  <h2>6. Category C: Weather Analysis</h2>")
    parts.append("  <p>Figures 6–8 compare thermal regimes, rainfall reliability, and temperature-precipitation relationships.</p>")
    parts.extend(_embed_figure(output_dir, "06_weather_gdd_distribution.png", "Figure 6", "GDD distribution by state."))
    parts.extend(_embed_figure(output_dir, "07_weather_precip_variability.png", "Figure 7", "Precipitation variability (CV) by state."))
    parts.extend(_embed_figure(output_dir, "08_weather_temp_precip_correlation.png", "Figure 8", "Monthly temperature vs precipitation correlation."))
    parts.append("  <div class='highlight'>")
    parts.append("    <strong>Key findings:</strong> (1) GDD differs massively by state — NE ~11,206°C vs IA ~8,694°C (ANOVA F=525, p<0.0001, η²=0.975). (2) Precipitation CV is highest in Nebraska (~274%) and lowest in Illinois (~231%) (Kruskal-Wallis H=27.1, p<0.0001). (3) All states show strong positive temp-precip correlation (r=0.73–0.83) — warmer months are reliably wetter.")
    parts.append("  </div>")
    
    parts.append("  <h2>7. Cross-Grower Synthesis</h2>")
    parts.extend(_embed_figure(output_dir, "09_synthesis_three_farms.png", "Figure 9", "Six-metric side-by-side comparison."))
    parts.append("  <p>The synthesis panel confirms Nebraska as the outlier: smaller fields, higher dominant crop share, lower diversity, dramatically higher GDD, more variable rainfall, and the highest corn/soy ratio (~3.4 vs 1.2 for IL). Illinois and Iowa are more similar to each other than to Nebraska.</p>")
    
    parts.append("  <h2>8. Crop Composition & Acreage</h2>")
    parts.append("  <p>Figures 14–16 show the full crop mix per state, both as percentages and total acreage.</p>")
    parts.extend(_embed_figure(output_dir, "14_crop_composition_by_state.png", "Figure 14", "Crop composition by state (mean pct)."))
    parts.extend(_embed_figure(output_dir, "15_crop_acreage_share_trend.png", "Figure 15", "Crop acreage share by year (2021–2025)."))
    parts.extend(_embed_figure(output_dir, "16_crop_acreage_by_state.png", "Figure 16", "Crop total acreage by state (2021–2025 sum)."))
    parts.append("  <div class='highlight'>")
    parts.append("    <strong>Key findings:</strong> Nebraska is corn-dominant (65% of crop mix). Illinois has the most balanced portfolio with notable alfalfa and wheat. Iowa has significant grass/pasture acreage (~19%). Absolute acreage tells a different story than percentages — Illinois grows more total corn acres (~9,500) than Nebraska (~7,800) despite a lower corn percentage.")
    parts.append("  </div>")
    
    parts.append("  <h2>9. Geospatial Map</h2>")
    parts.extend(_embed_figure(output_dir, "10A_geospatial_fields_only.png", "Figure 10A", "Geospatial field boundary map."))
    parts.append("  <p>The three farm clusters are spatially distinct: Illinois (DeKalb County, ~42°N 89°W), Iowa (Floyd County, ~43°N 93°W), and Nebraska (Hamilton County, ~41°N 98°W). The east-west transect spans 9° of longitude, representing a genuine climate gradient across the Corn Belt.</p>")
    
    parts.append("  <h2>10. Dominant Crop Share Trend</h2>")
    parts.extend(_embed_figure(output_dir, "12_dominant_crop_share_trend.png", "Figure 12", "Dominant crop share trend (2021–2025)."))
    parts.append("  <p>Dominant crop share is relatively stable over time. Nebraska maintains the highest share (~70–76%) across all 5 years, confirming that monoculture is an entrenched operating model, not a one-year artifact.</p>")
    
    parts.append("  <h2>11. Limitations & Assumptions</h2>")
    parts.append("  <ul>")
    parts.append("    <li><strong>Sample size:</strong> 30 fields (10 per state) — sufficient for EDA but small for robust statistical inference. The boundary-diversity correlation (r=-0.32, p=0.085) is not significant with n=30.</li>")
    parts.append("    <li><strong>Single farm per state:</strong> Each state is represented by one grower/farm. Results may not generalize to all farms in DeKalb, Floyd, or Hamilton counties.</li>")
    parts.append("    <li><strong>Corn vs soy correlation:</strong> The weak positive relationship (R²=14%) is likely driven by field size rather than agronomic trade-offs.</li>")
    parts.append("    <li><strong>GDD computation:</strong> Per-field GDD was computed from daily T2M_MIN/T2M_MAX with base 10°C as a fallback when county-level GDD parquet files were unavailable.</li>")
    parts.append("    <li><strong>Soil analysis:</strong> Intentionally excluded per assignment requirements. No soil data (SSURGO, texture, pH, organic matter) was analyzed or reported.</li>")
    parts.append("  </ul>")
    
    parts.append("  <div class='note'>")
    parts.append("    <strong>Note on excluded figures:</strong> Figures 10B (map with US inset), 11A (crop rotation heatmap), 11B (stacked acreage), and 13 (field size stability) were generated during the EDA pipeline but are not included in this report per the assignment requirements.")
    parts.append("  </div>")
    
    return parts


def _embed_figure(output_dir: Path, filename: str, label: str, caption: str) -> list[str]:
    path = output_dir / filename
    if not path.exists():
        return [f"  <p><em>{label}: {filename} not found</em></p>"]
    b64 = _img_to_base64(path)
    return [
        f'  <div class="figure">',
        f'    <img src="data:image/png;base64,{b64}" alt="{label}">',
        f'    <div class="caption"><strong>{label}:</strong> {caption}</div>',
        f'  </div>',
    ]


# ---------------------------------------------------------------------------
# DocX Report
# ---------------------------------------------------------------------------
def build_docx(output_dir: Path) -> Path:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    out = output_dir / "eda_report.docx"
    doc = Document()
    
    # Title
    title = doc.add_heading(REPORT_TITLE, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Page 1
    _add_page1_docx(doc, output_dir)
    
    # Page 2
    doc.add_page_break()
    _add_page2_docx(doc, output_dir)
    
    doc.save(out)
    print(f"  Saved: {out.name}")
    return out


def _add_page1_docx(doc, output_dir: Path):
    doc.add_heading("1. Dataset Scope & Grower Locations", level=1)
    doc.add_paragraph("This analysis covers three growers across the US Corn Belt, each with 10 fields tracked from 2021 to 2025:")
    
    table = doc.add_table(rows=4, cols=5)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text, hdr[4].text = "Grower", "State", "County", "Fields", "Primary Crops"
    data = [
        ("northern-illinois-grower", "Illinois", "DeKalb", "10", "Corn, Soybeans, Alfalfa"),
        ("northern-iowa-grower", "Iowa", "Floyd", "10", "Corn, Soybeans, Grass/Pasture"),
        ("nebraska-grower", "Nebraska", "Hamilton", "10", "Corn, Soybeans (highly dominant)"),
    ]
    for i, row_data in enumerate(data, 1):
        row = table.rows[i].cells
        for j, val in enumerate(row_data):
            row[j].text = val
    
    doc.add_heading("2. Data Layers Used", level=1)
    layers = [
        "Field boundaries: GeoJSON polygons from OpenStreetMap-derived field definitions",
        "Cropland Data Layer (CDL): USDA NASS crop composition tables per field per year (crop_code, crop_name, pct, acreage)",
        "Crop rotation: 5-year rotation sequences, diversity index, predicted next crop",
        "Weather: NASA POWER daily weather (T2M, T2M_MIN, T2M_MAX, PRECTOTCORR, GDD) per field",
        "GDD reference: County-level Growing Degree Day parquet files (2021–2025)",
    ]
    for layer in layers:
        doc.add_paragraph(layer, style='List Bullet')
    
    doc.add_heading("3. Comparison Levels", level=1)
    doc.add_paragraph("Four analytical levels were used:")
    levels = [
        "Field: Per-field boundary size, crop composition, and acreage stability",
        "Field-year: Year-over-year changes in dominant crop share, crop composition, and field size",
        "Grower (state-level): Aggregated metrics per farm (mean field size, crop diversity, GDD, precip CV)",
        "Across-grower: Side-by-side comparison of Illinois, Iowa, and Nebraska farms",
    ]
    for level in levels:
        doc.add_paragraph(level, style='List Bullet')
    
    doc.add_heading("4. Category A: Field Boundary Analysis", level=1)
    doc.add_paragraph("Figures 1–2 compare field size distributions and operational scale across states.")
    _add_figure_docx(doc, output_dir, "01_boundary_size_distribution.png", "Figure 1: Field size distribution by state (2021–2025 average).")
    _add_figure_docx(doc, output_dir, "02_boundary_count_vs_acreage.png", "Figure 2: Field count vs total acreage by state.")
    _add_highlight(doc, "Key finding: Nebraska fields are smaller (~265 ac avg) and more uniform. Illinois fields are largest (~387 ac) with wider spread. All three growers have 10 fields, but total acreage differs sharply (IL ~3,871 ac, IA ~3,696 ac, NE ~2,652 ac).")
    
    doc.add_heading("5. Category B: CDL / Cropland Analysis", level=1)
    doc.add_paragraph("Figures 3–5 examine crop dominance, diversity, and the corn-soybean trade-off.")
    _add_figure_docx(doc, output_dir, "03_cdl_dominant_crop_share.png", "Figure 3: Dominant crop share by state.")
    _add_figure_docx(doc, output_dir, "04_cdl_crop_diversity.png", "Figure 4: Crop diversity index by field and state.")
    _add_figure_docx(doc, output_dir, "05_cdl_corn_vs_soy.png", "Figure 5: Corn vs soybean acreage correlation (2025).")
    _add_highlight(doc, "Key findings: (1) Nebraska is the most monoculture — dominant crop share ~76%. Iowa is most diverse at ~53%. (2) Crop diversity index: IL ~2.0, IA ~1.8, NE ~1.7 unique crops. (3) Corn vs soy correlation is weakly positive (r=0.38, p=0.049, R²=14%) — larger fields grow more of both crops rather than trading off.")


def _add_page2_docx(doc, output_dir: Path):
    doc.add_heading("6. Category C: Weather Analysis", level=1)
    doc.add_paragraph("Figures 6–8 compare thermal regimes, rainfall reliability, and temperature-precipitation relationships.")
    _add_figure_docx(doc, output_dir, "06_weather_gdd_distribution.png", "Figure 6: GDD distribution by state.")
    _add_figure_docx(doc, output_dir, "07_weather_precip_variability.png", "Figure 7: Precipitation variability (CV) by state.")
    _add_figure_docx(doc, output_dir, "08_weather_temp_precip_correlation.png", "Figure 8: Monthly temperature vs precipitation correlation.")
    _add_highlight(doc, "Key findings: (1) GDD differs massively by state — NE ~11,206°C vs IA ~8,694°C (ANOVA F=525, p<0.0001, η²=0.975). (2) Precipitation CV is highest in Nebraska (~274%) and lowest in Illinois (~231%) (Kruskal-Wallis H=27.1, p<0.0001). (3) All states show strong positive temp-precip correlation (r=0.73–0.83) — warmer months are reliably wetter.")
    
    doc.add_heading("7. Cross-Grower Synthesis", level=1)
    _add_figure_docx(doc, output_dir, "09_synthesis_three_farms.png", "Figure 9: Six-metric side-by-side comparison.")
    doc.add_paragraph("The synthesis panel confirms Nebraska as the outlier: smaller fields, higher dominant crop share, lower diversity, dramatically higher GDD, more variable rainfall, and the highest corn/soy ratio (~3.4 vs 1.2 for IL). Illinois and Iowa are more similar to each other than to Nebraska.")
    
    doc.add_heading("8. Crop Composition & Acreage", level=1)
    doc.add_paragraph("Figures 14–16 show the full crop mix per state, both as percentages and total acreage.")
    _add_figure_docx(doc, output_dir, "14_crop_composition_by_state.png", "Figure 14: Crop composition by state (mean pct).")
    _add_figure_docx(doc, output_dir, "15_crop_acreage_share_trend.png", "Figure 15: Crop acreage share by year (2021–2025).")
    _add_figure_docx(doc, output_dir, "16_crop_acreage_by_state.png", "Figure 16: Crop total acreage by state (2021–2025 sum).")
    _add_highlight(doc, "Key findings: Nebraska is corn-dominant (65% of crop mix). Illinois has the most balanced portfolio with notable alfalfa and wheat. Iowa has significant grass/pasture acreage (~19%). Absolute acreage tells a different story than percentages — Illinois grows more total corn acres (~9,500) than Nebraska (~7,800) despite a lower corn percentage.")
    
    doc.add_heading("9. Geospatial Map", level=1)
    _add_figure_docx(doc, output_dir, "10A_geospatial_fields_only.png", "Figure 10A: Geospatial field boundary map.")
    doc.add_paragraph("The three farm clusters are spatially distinct: Illinois (DeKalb County, ~42°N 89°W), Iowa (Floyd County, ~43°N 93°W), and Nebraska (Hamilton County, ~41°N 98°W). The east-west transect spans 9° of longitude, representing a genuine climate gradient across the Corn Belt.")
    
    doc.add_heading("10. Dominant Crop Share Trend", level=1)
    _add_figure_docx(doc, output_dir, "12_dominant_crop_share_trend.png", "Figure 12: Dominant crop share trend (2021–2025).")
    doc.add_paragraph("Dominant crop share is relatively stable over time. Nebraska maintains the highest share (~70–76%) across all 5 years, confirming that monoculture is an entrenched operating model, not a one-year artifact.")
    
    doc.add_heading("11. Limitations & Assumptions", level=1)
    limitations = [
        "Sample size: 30 fields (10 per state) — sufficient for EDA but small for robust statistical inference. The boundary-diversity correlation (r=-0.32, p=0.085) is not significant with n=30.",
        "Single farm per state: Each state is represented by one grower/farm. Results may not generalize to all farms in DeKalb, Floyd, or Hamilton counties.",
        "Corn vs soy correlation: The weak positive relationship (R²=14%) is likely driven by field size rather than agronomic trade-offs.",
        "GDD computation: Per-field GDD was computed from daily T2M_MIN/T2M_MAX with base 10°C as a fallback when county-level GDD parquet files were unavailable.",
        "Soil analysis: Intentionally excluded per assignment requirements. No soil data (SSURGO, texture, pH, organic matter) was analyzed or reported.",
    ]
    for lim in limitations:
        doc.add_paragraph(lim, style='List Bullet')
    
    doc.add_paragraph("").add_run("Note on excluded figures: Figures 10B (map with US inset), 11A (crop rotation heatmap), 11B (stacked acreage), and 13 (field size stability) were generated during the EDA pipeline but are not included in this report per the assignment requirements.").italic = True


def _add_figure_docx(doc, output_dir: Path, filename: str, caption: str):
    from docx.shared import Inches, Pt
    path = output_dir / filename
    if path.exists():
        # Resize to fit page width (~6 inches at 300dpi)
        img = Image.open(path)
        width_in = min(5.5, img.width / 300)
        doc.add_picture(str(path), width=Inches(width_in))
        cap = doc.add_paragraph(caption)
        cap.runs[0].font.italic = True
        cap.runs[0].font.size = Pt(10)


def _add_highlight(doc, text: str):
    from docx.shared import RGBColor
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.color.rgb = RGBColor(0x1E, 0x90, 0xFF)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not root:
        print("ERROR: DATA_PIPELINE_DATA_ROOT is required.")
        sys.exit(1)
    
    # Use most recent output directory
    output_base = Path(root) / "data-pipeline" / "eda" / "field-comparison" / "output"
    subdirs = sorted([d for d in output_base.iterdir() if d.is_dir()], reverse=True)
    if not subdirs:
        print("ERROR: No output directory found.")
        sys.exit(1)
    
    output_dir = subdirs[0]
    print(f"Output directory: {output_dir}")
    
    print("\nGenerating HTML report...")
    build_html(output_dir)
    
    print("\nGenerating DocX report...")
    build_docx(output_dir)
    
    print(f"\nAll reports saved to: {output_dir}")


if __name__ == "__main__":
    import sys
    main()
