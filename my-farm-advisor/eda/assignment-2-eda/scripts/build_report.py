import os
import sys
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

OUTPUT_ROOT = Path(os.environ.get(
    "DATA_PIPELINE_DATA_ROOT",
    os.path.expanduser("~/my-farm-advisor-runtime/data-pipeline"),
)).parent / "eda-outputs"

REPORT_PATH = OUTPUT_ROOT / "assignment-2-eda-report.docx"

FIG_WIDTH = Inches(5.8)


def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def add_body(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(6)
    return p


def add_figure(doc, rel_path, caption):
    path = OUTPUT_ROOT / rel_path
    if not path.exists():
        add_body(doc, f"[Image not found: {rel_path}]")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=FIG_WIDTH)
    c = doc.add_paragraph(caption)
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c.runs[0].font.size = Pt(9)
    c.runs[0].font.italic = True
    c.paragraph_format.space_after = Pt(12)


def add_bullet(doc, text):
    p = doc.add_paragraph(text, style="List Bullet")
    p.paragraph_format.space_after = Pt(2)


def build():
    doc = Document()

    # ── Title ──
    title = doc.add_heading("Assignment 2 — Three-Grower Corn Belt EDA Report", level=0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1a, 0x47, 0x27)

    add_body(doc, (
        "Prepared from the reusable eda subskill at "
        "my-farm-advisor/eda/assignment-2-eda/."
        "  All figures generated from field boundaries, CDL cropland data layer (2021–2025), "
        "and NASA POWER weather (2021–2025) — no soil analysis involved."
    ))

    # ════════════════════════════════════════
    # 1  DATASET SCOPE
    # ════════════════════════════════════════
    add_heading(doc, "1  Dataset Scope", level=1)
    add_body(doc, (
        "Three growers across the U.S. Corn Belt, each operating a single farm with 10 fields:"
    ))
    add_bullet(doc, "Illinois — Northern Illinois Farm, DeKalb County (FIPS 17037)")
    add_bullet(doc, "Iowa — Northern Iowa Farm, Cerro Gordo County (FIPS 19033)")
    add_bullet(doc, "Nebraska — Platte River Farm, Merrick County (FIPS 31121)")
    add_body(doc, "Total: 30 fields across 3 states. Data layers used:")
    add_bullet(doc, "Field boundaries: GeoJSON (EPSG:4326), OSM-sourced polygons with area_acres")
    add_bullet(doc, "CDL cropland data layer: 30 m resolution, 5 years (2021–2025), pixel-level and aggregated composition + crop rotation tables")
    add_bullet(doc, "NASA POWER weather: Daily T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, RH2M, WS10M (2021–2025)")
    add_bullet(doc, "Geospatial basemap: ESRI World Imagery satellite tiles via contextily")

    # ════════════════════════════════════════
    # 2  COMPARISON LEVELS
    # ════════════════════════════════════════
    add_heading(doc, "2  Comparison Levels", level=1)
    add_body(doc, "Analyses were performed at four levels:")
    add_bullet(doc, "Within-field: Year-over-year crop rotation sequences for individual fields (CDL rotation heatmap). Multi-year weather variability at single fields (seasonal temperature ±1σ).")
    add_bullet(doc, "Across-fields (within grower): Field size distributions, CDL composition and diversity per grower. Within-grower multi-variable weather cycle (temperature, precipitation, solar radiation co-variation).")
    add_bullet(doc, "Across-growers (between states): Field acreage comparison, crop composition stacked bars, annual precipitation grouped bars, growing-season climate space scatter.")
    add_bullet(doc, "Cross-domain correlation: Corn planting percentage vs. field size with Spearman rank correlation per grower.")

    # ════════════════════════════════════════
    # 3  FIELD BOUNDARIES
    # ════════════════════════════════════════
    add_heading(doc, "3  Field Boundaries", level=1)
    add_body(doc, "Field size distribution across the three growers reveals the farming system gradient.")

    add_figure(doc, "boundaries/field_size_distribution.png",
               "Kernel density estimate of field acreage by grower. "
               "Nebraska fields are compact (20–152 ac, peak ~50 ac), consistent with center-pivot irrigation quarter-sections. "
               "Illinois and Iowa have long tails exceeding 1,000 ac (glacial-till row-crop operations).")

    add_figure(doc, "boundaries/field_size_boxplot.png",
               "Boxplot with jittered points confirms Nebraska's tight interquartile range (30–80 ac) "
               "vs. wide IL/IA spreads including >1,000 ac outliers.")

    add_figure(doc, "boundaries/field_centroids.png",
               "Geographic scatter of field centroids sized by acreage. "
               "Each grower's fields cluster within their county, with Nebraska's Merrick County fields "
               "concentrated along the Platte River corridor.")

    # ════════════════════════════════════════
    # 4  CDL / CROPLAND DATA LAYER
    # ════════════════════════════════════════
    add_heading(doc, "4  CDL / Cropland Data Layer", level=1)
    add_body(doc, "Crop choice and rotation intensity across the transect.")

    add_figure(doc, "cdl/crop_composition.png",
               "5-year aggregate crop composition. Corn + soybeans account for ~99% of Illinois pixels, "
               "~96% of Iowa, and ~90% of Nebraska. Nebraska shows measurable winter wheat, "
               "grass/pasture, and alfalfa — reflecting the transition to semi-arid, irrigated systems "
               "where continuous corn and alternative crops are more common.")

    add_figure(doc, "cdl/crop_diversity.png",
               "Histogram of unique crop species per field over 5 years (from rotation tables). "
               "Illinois and Iowa fields are overwhelmingly 2-crop rotations (corn/soybean alternating). "
               "Nebraska has multiple fields with 3+ crop types, including grass/pasture transitions.")

    add_figure(doc, "cdl/rotation_heatmap.png",
               "Tile grid of dominant crop per field per year. Each row is one field, "
               "grouped by grower. Illinois and Iowa show classic alternating corn–soybean "
               "checkerboards. Nebraska shows longer runs of continuous corn and more "
               "grass/pasture/winter wheat transitions.")

    add_figure(doc, "cdl/crop_vs_fieldsize.png",
               "Corn percentage vs. field size with Spearman rank correlations. "
               "The relationship differs by state: in Illinois and Iowa there is a mild negative "
               "trend (smaller fields are more corn-heavy), while Nebraska shows no significant "
               "correlation — likely because all fields are irrigated pivots managed similarly "
               "regardless of size. Annotated ρ-values and p-values are shown per grower.")

    # ════════════════════════════════════════
    # 5  WEATHER
    # ════════════════════════════════════════
    add_heading(doc, "5  Weather", level=1)
    add_body(doc, "NASA POWER daily data (2021–2025) reveals the climate gradient driving farming differences.")

    add_figure(doc, "weather/seasonal_temperature.png",
               "Monthly mean temperature ±1σ. Nebraska is 2–3 °C hotter in summer and 4–5 °C colder in winter "
               "than Illinois — the continental gradient. Iowa sits between the two. "
               "The wider Nebraska winter envelope reflects greater interannual variability.")

    add_figure(doc, "weather/annual_precipitation.png",
               "Total annual precipitation by grower. Illinois consistently receives ~1,000 mm/yr, "
               "Iowa ~850 mm/yr, and Nebraska ~600 mm/yr. This 400 mm deficit is why Nebraska "
               "fields depend on center-pivot irrigation.")

    add_figure(doc, "weather/growing_season_climate.png",
               "Growing-season (Apr–Sep) climate space: mean temperature vs. total precipitation "
               "for each field-year. Illinois clusters in the cool-wet quadrant, Nebraska in the "
               "hot-dry quadrant, and Iowa in between. This single scatter plot captures the "
               "defining environmental gradient of the U.S. Corn Belt.")

    add_figure(doc, "weather/within_grower_weather_cycle.png",
               "Within-grower multi-variable comparison: monthly means of temperature (solid line), "
               "solar radiation (dashed), and daily precipitation (bars). Shows how each region's "
               "growing season unfolds — Nebraska's solar radiation peaks higher and persists longer "
               "(more cloud-free days), while precipitation is more concentrated in spring/early summer.")

    # ════════════════════════════════════════
    # 6  GEOSPATIAL MAP
    # ════════════════════════════════════════
    add_heading(doc, "6  Geospatial Map", level=1)
    add_body(doc, (
        "A 3-panel satellite basemap (ESRI World Imagery) showing all 30 field boundaries "
        "at the same scale with fields numbered 1–10 per grower."
    ))

    add_figure(doc, "geospatial/field_boundaries_map.png",
               "Left: Illinois (DeKalb Co.) — large, irregular field polygons typical of glacial-till "
               "row-crop agriculture. Center: Iowa (Cerro Gordo Co.) — medium-sized fields with mixed "
               "shapes. Right: Nebraska (Merrick Co.) — compact fields, many with visible circular "
               "center-pivot irrigation patterns in the Platte River valley. Total acreage per grower "
               "is annotated (IL: 1,798 ac, IA: 2,347 ac, NE: 654 ac).")

    # ════════════════════════════════════════
    # 7  LIMITATIONS
    # ════════════════════════════════════════
    add_heading(doc, "7  Limitations & Assumptions", level=1)
    add_bullet(doc, "NASA POWER weather is gridded at ~0.5° × 0.625° resolution. Multiple fields within the same county share the same grid cell(s) and thus have nearly identical daily weather values. Within-county weather variability is not captured.")
    add_bullet(doc, "CDL data is 30 m resolution. The smallest Illinois field is ~2.5 acres; at that size, edge effects and mixed pixels can reduce classification accuracy.")
    add_bullet(doc, "Field boundaries were sourced from OpenStreetMap, which may not perfectly align with official field parcel records or FSA CLU boundaries.")
    add_bullet(doc, "The 5-year weather window (2021–2025) is too short for robust climate normals. Long-term averages would require 30 years of data.")
    add_bullet(doc, "Crop rotation analysis relies on CDL dominant crop per field-year. Fields with mixed cropping (e.g., strips) may be assigned a single dominant class that masks sub-field diversity.")
    add_bullet(doc, "All comparisons are observational. Causation (e.g., climate → crop choice → field size) cannot be established from this dataset alone.")

    # ════════════════════════════════════════
    # 8  SOIL DISCLAIMER
    # ════════════════════════════════════════
    add_heading(doc, "8  Soil Disclaimer", level=1)
    add_body(doc, (
        "Soil analysis (SSURGO) is not part of this EDA. The data pipeline does generate "
        "soil tables and SSURGO summary statistics for all 30 fields, but the assignment-2-eda "
        "subskill explicitly excludes soil analysis by design. "
        "All comparisons in this report are based solely on field boundaries, "
        "CDL/cropland data layer, and NASA POWER weather data."
    ))

    # ── Save ──
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(REPORT_PATH))
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    build()
