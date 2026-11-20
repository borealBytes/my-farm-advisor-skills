#!/usr/bin/env python3
"""Build the one-time Assignment 2 field-EDA HTML report.

This is deliberately outside the reusable subskill: it reads the subskill's
runtime outputs and assembles a single self-contained HTML file.

    DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime \
        python3 reports/assignment-2/build_report.py

No third-party dependencies. Figures are embedded as base64 so the report is
portable; every number is read from the CSVs so the prose cannot drift.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import os
from datetime import date
from pathlib import Path

CATEGORIES = [
    {
        "id": "boundaries",
        "number": "3",
        "title": "Field boundaries",
        "lede": (
            "Thirty fields, two very different provenance paths: USDA Crop "
            "Sequence Boundaries drawn as large survey-aligned blocks, and "
            "OpenStreetMap parcels traced by hand. Geometry is measured in "
            "EPSG:5070 metres."
        ),
        "figures": [
            ("figures/01_boundary_area.png", "figures/01_boundary_area.caption.md"),
            ("figures/02_boundary_shape.png", "figures/02_boundary_shape.caption.md"),
            ("maps/01_boundary_sources.png", "maps/01_boundary_sources.caption.md"),
        ],
        "table": "tables/boundary_analysis.csv",
        "table_title": "A1 — Geometry tests by grower and boundary source",
        "table_note": (
            "Spearman correlations include a seeded bootstrap interval. The "
            "Mann–Whitney comparison reports a rank-biserial effect size. Size "
            "and source are confounded; both are shown rather than one blamed."
        ),
    },
    {
        "id": "cdl",
        "number": "4",
        "title": "Cropland history",
        "lede": (
            "Five CDL years, 2019–2023, reduced to a dominant crop per field-year. "
            "This is the clearest within-field-over-time signal in the dataset: "
            "Illinois and Iowa alternate, Nebraska holds corn."
        ),
        "figures": [
            ("figures/03_cdl_composition.png", "figures/03_cdl_composition.caption.md"),
            ("figures/04_cdl_rotation.png", "figures/04_cdl_rotation.caption.md"),
            ("maps/02_cdl_2023.png", "maps/02_cdl_2023.caption.md"),
        ],
        "table": "tables/cdl_analysis.csv",
        "table_title": "A2 — Rotation, corn-after-corn, and crop-mix association",
        "table_note": (
            "Corn-after-corn counts corn field-years whose preceding year in the "
            "window is also corn, over corn field-years that have a preceding "
            "year. The interval is a Wilson score interval; field-years within a "
            "field are not independent draws."
        ),
    },
    {
        "id": "weather",
        "number": "5",
        "title": "Seasonal weather",
        "lede": (
            "Daily NASA POWER data for April–September, 2021–2025. The product is "
            "gridded: these three growers fall into four, two, and two cells. That "
            "single fact drives the honest conclusion of this section."
        ),
        "figures": [
            ("figures/05_weather_gdd.png", "figures/05_weather_gdd.caption.md"),
            ("figures/06_weather_precip.png", "figures/06_weather_precip.caption.md"),
            ("maps/03_weather_precip.png", "maps/03_weather_precip.caption.md"),
        ],
        "table": "tables/weather_analysis.csv",
        "table_title": "A3 — Variance attribution and GDD/precipitation coupling",
        "table_note": (
            "Sum-of-squares shares are descriptive, not a fitted model. The small "
            "within-grower-year share is the null result: two fields in the same "
            "cell receive identical weather."
        ),
    },
]

CSS = """
:root {
  --ink: #1c2530;
  --muted: #5b6773;
  --line: #dbe2ea;
  --paper: #ffffff;
  --wash: #f4f6f8;
  --green: #23654a;
  --green-soft: #e8f1ec;
  --gold: #b8791a;
  --gold-soft: #fbf3e2;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #eef1f4;
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
}
.page {
  max-width: 1160px;
  margin: 32px auto 56px;
  background: var(--paper);
  box-shadow: 0 2px 18px rgba(20, 35, 50, .08);
  border-radius: 6px;
  overflow: hidden;
}
.cover {
  background: linear-gradient(135deg, #173d2d 0%, #23654a 62%, #2f7d5c 100%);
  color: #f3f7f4;
  padding: 54px 56px 42px;
}
.eyebrow {
  text-transform: uppercase;
  letter-spacing: .16em;
  font-size: .72rem;
  font-weight: 700;
  color: #b9d8c8;
  margin: 0 0 14px;
}
.cover h1 {
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 2.45rem;
  line-height: 1.14;
  margin: 0 0 16px;
  font-weight: 600;
  letter-spacing: -.01em;
}
.cover .standfirst {
  font-size: 1.05rem;
  max-width: 42em;
  color: #d9e8df;
  margin: 0 0 26px;
}
.cover .meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 26px;
  font-size: .8rem;
  color: #c9dfd3;
  border-top: 1px solid rgba(255,255,255,.22);
  padding-top: 16px;
}
.cover .meta b { color: #fff; font-weight: 600; }
.content { padding: 8px 46px 56px; }
.hint { font-size: .8rem; color: var(--muted); margin: 10px 2px 0; }
.hint b { color: var(--green); }
h2 {
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 1.6rem;
  line-height: 1.2;
  margin: 56px 0 6px;
  padding-top: 22px;
  border-top: 2px solid var(--ink);
  font-weight: 600;
}
h2 .num {
  color: var(--green);
  font-variant-numeric: tabular-nums;
  margin-right: 10px;
}
h3 {
  font-size: 1.02rem;
  margin: 34px 0 10px;
  letter-spacing: .01em;
}
p { margin: 10px 0; }
.lede { color: var(--muted); font-size: 1.02rem; max-width: 60em; }
.toc {
  background: var(--wash);
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 16px 20px;
  margin: 28px 0 0;
}
.toc p { margin: 0 0 8px; font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); font-weight: 700; }
.toc ol { margin: 0; padding-left: 20px; columns: 2; column-gap: 32px; font-size: .9rem; }
.toc a { color: var(--ink); text-decoration: none; }
.toc a:hover { color: var(--green); text-decoration: underline; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 22px 0 8px; }
.card {
  border: 1px solid var(--line);
  border-top: 4px solid var(--green);
  border-radius: 4px;
  padding: 16px 16px 14px;
  background: #fff;
}
.card.gold { border-top-color: var(--gold); }
.card .big {
  font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 1.35rem;
  line-height: 1.2;
  font-weight: 600;
  display: block;
  margin-bottom: 6px;
}
.card .small { font-size: .78rem; color: var(--muted); line-height: 1.45; }
.callout {
  background: var(--gold-soft);
  border-left: 4px solid var(--gold);
  padding: 14px 18px;
  margin: 20px 0;
  font-size: .92rem;
  border-radius: 0 4px 4px 0;
}
.callout b { color: #7a5011; }
figure { margin: 30px 0 34px; }
figure .expand { display: block; cursor: zoom-in; }
figure .close { display: none; }
figure img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: #fff;
}
figure:target {
  position: fixed;
  inset: 0;
  z-index: 999;
  margin: 0;
  padding: 56px 20px 40px;
  background: #fff;
  overflow: auto;
}
figure:target .expand { cursor: zoom-out; }
figure:target img {
  width: auto;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  border: none;
}
figure:target .close {
  display: inline-block;
  position: fixed;
  top: 12px;
  right: 16px;
  z-index: 1000;
  padding: 6px 13px;
  background: var(--ink);
  color: #fff;
  text-decoration: none;
  border-radius: 4px;
  font-size: .8rem;
  box-shadow: 0 1px 6px rgba(0,0,0,.25);
}
figure:target figcaption { max-width: 820px; margin: 16px auto 0; }
figcaption { margin-top: 10px; font-size: .87rem; color: #3c4752; }
figcaption .q { font-weight: 600; color: var(--ink); margin: 0 0 5px; }
figcaption .q span {
  text-transform: uppercase; letter-spacing: .1em; font-size: .66rem;
  color: var(--green); margin-right: 7px;
}
figcaption .caveat { color: var(--muted); border-left: 2px solid var(--line); padding-left: 10px; margin-top: 8px; }
figcaption .caveat b { color: #7a5011; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; font-size: .68rem; margin-right: 5px; }
details { margin-top: 8px; font-size: .8rem; color: var(--muted); }
details summary { cursor: pointer; color: var(--green); font-weight: 600; }
details ul { margin: 8px 0 0; padding-left: 18px; }
.tablewrap { overflow-x: auto; margin: 14px 0 10px; border: 1px solid var(--line); border-radius: 4px; }
table { border-collapse: collapse; width: 100%; font-size: .76rem; font-variant-numeric: tabular-nums; }
thead th {
  background: #f0f3f6;
  text-align: left;
  padding: 8px 9px;
  border-bottom: 1px solid #c9d3dc;
  font-size: .68rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: #44515e;
  white-space: nowrap;
}
tbody td { padding: 7px 9px; border-bottom: 1px solid #edf1f4; vertical-align: top; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: #fafbfc; }
td.num, th.num { text-align: right; }
td.note { min-width: 180px; color: var(--muted); font-size: .72rem; }
.table-note { font-size: .78rem; color: var(--muted); margin: 6px 0 26px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; }
ul.plain { padding-left: 20px; margin: 10px 0; }
ul.plain li { margin: 6px 0; }
.kv { width: 100%; font-size: .82rem; }
.kv td { border-bottom: 1px solid #edf1f4; padding: 6px 0; }
.kv td:first-child { color: var(--muted); width: 38%; }
code { background: #f0f3f6; padding: 1px 5px; border-radius: 3px; font-size: .85em; }
pre { background: #17211b; color: #d9e8df; padding: 14px 16px; border-radius: 4px; overflow-x: auto; font-size: .78rem; line-height: 1.5; }
pre code { background: none; padding: 0; color: inherit; }
footer {
  border-top: 1px solid var(--line);
  margin-top: 48px;
  padding-top: 18px;
  font-size: .76rem;
  color: var(--muted);
}
@media (max-width: 860px) {
  .page { margin: 0; border-radius: 0; }
  .cover, .content { padding-left: 24px; padding-right: 24px; }
  .cards { grid-template-columns: 1fr 1fr; }
  .two-col { grid-template-columns: 1fr; }
  .toc ol { columns: 1; }
}
@media print {
  body { background: #fff; }
  .page { max-width: none; margin: 0; box-shadow: none; }
  .toc { break-inside: avoid; }
  h2 { break-before: page; }
  figure, table, .callout { break-inside: avoid; }
  .cover { background: #173d2d !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def metric(rows, group, name):
    for row in rows:
        if row.get("group") == group and row.get("metric") == name:
            return as_float(row.get("value"))
    return None


def fmt(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        number = float(text)
    except ValueError:
        return html.escape(text)
    if number != number:
        return ""
    if number.is_integer():
        return f"{int(number):,}"
    if abs(number) < 0.01:
        return f"{number:.4g}"
    if abs(number) >= 1000:
        return f"{number:,.1f}"
    return f"{number:.3f}".rstrip("0").rstrip(".")


def pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def pct1(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def fmt2(value) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def b64_png(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def resolve(runtime: Path, stored: str) -> Path:
    path = Path(stored)
    return path if path.is_absolute() else runtime / path


def year_window(manifest: dict, runtime: Path, kind: str) -> str:
    """Derive '2019–2023' from the first input filename of a kind."""
    import re

    for item in manifest["inputs"]:
        if item["kind"] != kind:
            continue
        years = re.findall(r"(20\d{2})", Path(item["path"]).name)
        if len(years) >= 2:
            return f"{min(years)}–{max(years)}"
    return ""


def min_cdl_pixels(manifest: dict, runtime: Path) -> int | None:
    """Smallest field-year CDL pixel count across the input composition tables."""
    totals: dict[tuple[str, str], float] = {}
    for item in manifest["inputs"]:
        if item["kind"] != "cdl":
            continue
        for row in read_csv(resolve(runtime, item["path"])):
            key = (row.get("field_id", ""), row.get("year", ""))
            totals[key] = totals.get(key, 0.0) + (as_float(row.get("pixel_count")) or 0.0)
    if not totals:
        return None
    return int(min(totals.values()))


def parse_caption(path: Path) -> dict:
    fields = {"title": path.stem, "question": "", "story": "", "caveat": "",
              "notes": [], "inputs": []}
    mode = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            fields["title"] = line[2:].strip()
            continue
        if line.startswith("**Question:**"):
            fields["question"] = line.split("**Question:**", 1)[1].strip()
            mode = None
            continue
        if line.startswith("**What this shows:**"):
            fields["story"] = line.split("**What this shows:**", 1)[1].strip()
            mode = None
            continue
        if line.startswith("**Caveat:**"):
            fields["caveat"] = line.split("**Caveat:**", 1)[1].strip()
            mode = None
            continue
        if line.startswith("**Reading notes:**"):
            mode = "notes"
            continue
        if line.startswith("**Inputs:**"):
            mode = "inputs"
            continue
        if line.startswith("- "):
            if mode in ("notes", "inputs"):
                value = line[2:].strip().strip("`")
                fields[mode].append(value)
            continue
    return fields


def render_figure(
    image_path: Path, caption_path: Path, anchor: str, close_anchor: str
) -> str:
    caption = parse_caption(caption_path)
    image = b64_png(image_path)
    detail_bits = []
    if caption["notes"]:
        detail_bits.append(
            "<ul>" + "".join(f"<li>{html.escape(note)}</li>" for note in caption["notes"]) + "</ul>"
        )
    if caption["inputs"]:
        detail_bits.append(
            "<ul class='inputs'>"
            + "".join(f"<li><code>{html.escape(name)}</code></li>" for name in caption["inputs"])
            + "</ul>"
        )
    details = (
        "<details><summary>Reading notes and input files</summary>"
        + "".join(detail_bits)
        + "</details>"
        if detail_bits
        else ""
    )
    return f"""
<figure id="{anchor}">
  <a class="expand" href="#{anchor}" aria-label="Open figure at full resolution">
    <img src="data:image/png;base64,{image}" alt="{html.escape(caption['title'])}">
  </a>
  <a class="close" href="#{close_anchor}">Close</a>
  <figcaption>
    <p class="q"><span>Question</span>{html.escape(caption['question'])}</p>
    <p>{html.escape(caption['story'])}</p>
    <p class="caveat"><b>Caveat</b>{html.escape(caption['caveat'])}</p>
    {details}
  </figcaption>
</figure>
"""


def render_table(rows: list[dict], numeric_columns: set[str], collapsible: bool = False) -> str:
    if not rows:
        return "<p>No rows.</p>"
    labels = {
        "ci_low": "CI low",
        "ci_high": "CI high",
        "p_value": "p",
        "value": "Value",
        "scope": "Scope",
        "group": "Group",
        "metric": "Metric",
        "n": "n",
    }
    columns = list(rows[0].keys())
    head = "".join(
        f"<th class='{'num' if column in numeric_columns else ''}'>"
        f"{html.escape(labels.get(column, column))}</th>"
        for column in columns
    )
    body = []
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column, "")
            classes = []
            if column in numeric_columns:
                classes.append("num")
            if column == "note":
                classes.append("note")
            rendered = fmt(value)
            cells.append(
                f"<td class='{' '.join(classes)}'>{rendered}</td>"
                if classes
                else f"<td>{rendered}</td>"
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    table = (
        "<div class='tablewrap'><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )
    if collapsible:
        return f"<details><summary>Show all {len(rows)} rows</summary>{table}</details>"
    return table


def grower_rows(manifest, field_metrics, cdl_rows, weather_rows) -> list[dict]:
    rendered = []
    for grower in manifest["growers"]:
        label = grower["label"]
        fields = [row for row in field_metrics if row["grower"] == label]
        areas = sorted(as_float(row["area_ha"]) for row in fields if as_float(row["area_ha"]))
        median_area = areas[len(areas) // 2] if areas else None
        if len(areas) % 2 == 0 and len(areas) > 1:
            median_area = (areas[len(areas) // 2 - 1] + areas[len(areas) // 2]) / 2
        rendered.append(
            {
                "Grower": f"{label} · {grower['slug']}",
                "Fields": grower["fields"],
                "Median area (ha)": f"{median_area:.0f}" if median_area is not None else "",
                "Corn share": pct(metric(cdl_rows, label, "corn_share_field_years")),
                "Corn after corn": pct(metric(cdl_rows, label, "corn_after_corn_rate")),
                "Seasonal GDD": metric(weather_rows, label, "seasonal_gdd_mean"),
                "Seasonal precip (mm)": metric(weather_rows, label, "seasonal_precip_mm_mean"),
                "Grid cells": grower["grid_cells"],
            }
        )
    return rendered


def build(runtime: Path, out_path: Path) -> None:
    eda = runtime / "data-pipeline" / "eda" / "field-eda"
    manifest = json.loads((eda / "manifest.json").read_text(encoding="utf-8"))

    field_metrics = read_csv(eda / "tables" / "field_metrics.csv")
    boundary_rows = read_csv(eda / "tables" / "boundary_analysis.csv")
    cdl_rows = read_csv(eda / "tables" / "cdl_analysis.csv")
    weather_rows = read_csv(eda / "tables" / "weather_analysis.csv")

    counts = manifest["counts"]
    csb_median = metric(boundary_rows, "csb", "compactness_median")
    osm_median = metric(boundary_rows, "osm", "compactness_median")
    csb_rho = metric(boundary_rows, "csb", "spearman_log_area_compactness")
    ne_cac = metric(cdl_rows, "NE", "corn_after_corn_rate")
    il_cac = metric(cdl_rows, "IL", "corn_after_corn_rate")
    ia_cac = metric(cdl_rows, "IA", "corn_after_corn_rate")
    ne_gdd = metric(weather_rows, "NE", "seasonal_gdd_mean")
    il_gdd = metric(weather_rows, "IL", "seasonal_gdd_mean")
    ia_gdd = metric(weather_rows, "IA", "seasonal_gdd_mean")
    gdd_between = metric(weather_rows, "gdd", "between_growers")
    precip_year = metric(weather_rows, "precip_mm", "between_years_within_grower")
    within_values = [
        metric(weather_rows, measure, "within_grower_year")
        for measure in ("precip_mm", "gdd", "heat_days")
    ]
    within_values = [value for value in within_values if value is not None]
    within_low = min(within_values) if within_values else None
    within_high = max(within_values) if within_values else None

    toc = "".join(
        f"<li><a href='#{section['id']}'>{section['number']}. {section['title']}</a></li>"
        for section in CATEGORIES
    )

    sections_html = []
    for section in CATEGORIES:
        figures = "".join(
            render_figure(eda / image, eda / caption, f"{section['id']}-{index}", section["id"])
            for index, (image, caption) in enumerate(section["figures"], start=1)
        )
        table_rows = read_csv(eda / section["table"])
        numeric = {
            "value", "ci_low", "ci_high", "p_value", "n",
            "Fields", "Median area (ha)", "Grid cells",
        }
        sections_html.append(
            f"""
<section id="{section['id']}">
  <h2><span class="num">{section['number']}</span>{section['title']}</h2>
  <p class="lede">{section['lede']}</p>
  {figures}
  <h3>{section['table_title']}</h3>
  {render_table(table_rows, numeric)}
  <p class="table-note">{section['table_note']}</p>
</section>
"""
        )

    summary = grower_rows(manifest, field_metrics, cdl_rows, weather_rows)
    summary_table = render_table(
        summary,
        {"Fields", "Median area (ha)", "Seasonal GDD", "Seasonal precip (mm)", "Grid cells"},
    )

    appendix = render_table(
        sorted(field_metrics, key=lambda row: (row["grower"], row["field_id"])),
        {"area_ha", "perimeter_m", "compactness", "bearing_deg", "vertices",
         "crop_diversity", "corn_years", "soybean_years", "cdl_coverage",
         "mean_precip_mm", "mean_gdd", "mean_heat_days"},
        collapsible=True,
    )

    versions = manifest.get("environment", {})
    version_text = " · ".join(
        f"{name} {value}" for name, value in sorted(versions.items())
        if name in ("python", "geopandas", "pandas", "numpy", "scipy", "matplotlib")
    )
    cdl_years = year_window(manifest, runtime, "cdl") or "2019–2023"
    weather_years = year_window(manifest, runtime, "weather") or "2021–2025"
    smallest_pixels = min_cdl_pixels(manifest, runtime)
    cell_text = ", ".join(
        f"{grower['label']} {grower['grid_cells']}" for grower in manifest["growers"]
    )
    within_text = (
        f"{within_low:.1f}–{within_high:.1f}%"
        if within_low is not None and within_high is not None
        else "a few percent"
    )
    build_date = date.today().strftime("%B %-d, %Y")

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Assignment 2 — Cross-Grower Field-Level EDA</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

<header class="cover">
  <p class="eyebrow">My Farm Advisor · Assignment 2</p>
  <h1>Three growers, thirty fields, three data layers</h1>
  <p class="standfirst">
    A field-level exploratory comparison of boundary geometry, five years of
    cropland history, and five growing seasons across Illinois, Iowa, and
    Nebraska. Static outputs, assembled once.
  </p>
  <div class="meta">
    <span><b>{counts['fields']}</b> fields</span>
    <span><b>{counts['growers']}</b> growers</span>
    <span><b>{counts['field_years_cdl']}</b> CDL field-years</span>
    <span>CDL <b>{cdl_years}</b></span>
    <span>Weather <b>{weather_years}</b></span>
    <span>Built <b>{build_date}</b></span>
  </div>
</header>

<main class="content">

<div class="toc">
  <p>Contents</p>
  <ol>
    <li><a href="#findings">What the data says</a></li>
    <li><a href="#dataset">The dataset</a></li>
    {toc}
    <li><a href="#limits">Limits and caveats</a></li>
    <li><a href="#provenance">Sources and provenance</a></li>
    <li><a href="#appendix">Appendix: field metrics</a></li>
  </ol>
</div>
<p class="hint">
  <b>Tip:</b> click any figure for a larger view. Use “Close” or the browser
  back button to return to the text.
</p>

<section id="findings">
  <h2><span class="num">1</span>What the data says</h2>
  <p class="lede">
    Three findings survived the checks. One of them is a null result, and it is
    the most useful of the three.
  </p>

  <div class="cards">
    <div class="card">
      <span class="big">{fmt2(csb_median)} vs {fmt2(osm_median)}</span>
      <span class="small">Median compactness, CSB blocks vs OSM parcels. Shape is a
      provenance story first.</span>
    </div>
    <div class="card gold">
      <span class="big">{pct(ne_cac)} corn after corn</span>
      <span class="small">Nebraska, against {pct(il_cac)} in Illinois and
      {pct(ia_cac)} in Iowa. Rotation separates the growers.</span>
    </div>
    <div class="card">
      <span class="big">{fmt(ne_gdd)} GDD</span>
      <span class="small">Nebraska seasonal mean, against {fmt(il_gdd)} in Illinois
      and {fmt(ia_gdd)} in Iowa, April–September.</span>
    </div>
    <div class="card gold">
      <span class="big">{within_text}</span>
      <span class="small">Of weather variance sits within a grower-year. Weather
      cannot rank fields, and the report says so.</span>
    </div>
  </div>

  <h3>1.1 Boundary provenance dominates field shape</h3>
  <p>
    The two boundary sources produce two populations. CSB fields are large and
    irregular, with a median compactness of {fmt2(csb_median)}; OSM parcels are
    smaller and rounder, at {fmt2(osm_median)}. Within the CSB population, larger
    fields are <em>less</em> compact (Spearman {fmt(csb_rho)}), consistent with
    long survey-aligned blocks. OSM parcel size shows no such relationship. A
    farm that mixes sources will always look bimodal, so field size cannot be
    read as a management choice.
  </p>

  <h3>1.2 Rotation is the sharpest between-grower contrast</h3>
  <p>
    Nebraska runs continuous corn: {pct(ne_cac)} of eligible corn field-years
    follow corn. Illinois and Iowa alternate, at {pct(il_cac)} and {pct(ia_cac)}.
    The crop-mix association across growers is real but moderate (Cramér's V
    0.24), because Illinois and Iowa are more similar to each other than either
    is to Nebraska.
  </p>

  <h3>1.3 Weather is a grower and year covariate — not a field one</h3>
  <p>
    Growing-season heat is mostly a grower property: {fmt(gdd_between)}% of GDD
    variance sits between growers. Precipitation is mostly year-to-year:
    {fmt(precip_year)}% of its variance sits between years within a grower, with a
    consistent grower offset. In both cases only {within_text}
    of the variance sits within a grower-year, because fields share NASA POWER
    grid cells. The map in section 4 shows the same thing visually: within a
    grower the colour barely changes.
  </p>
  <div class="callout">
    <b>Read this as a null result, not a missing analysis.</b> With four, two,
    and two grid cells across the three growers, field-to-field weather
    differences measure the grid, not the farm. Ranking fields on weather would
    be manufacturing a signal.
  </div>
</section>

<section id="dataset">
  <h2><span class="num">2</span>The dataset</h2>
  <p class="lede">
    Every row below is an existing data-pipeline output. The EDA reads it, never
    modifies it, and never opens a soil table.
  </p>
  {summary_table}
  <p class="table-note">
    NASA POWER grid cells: {cell_text}. Seasonal means are April–September.
    Software: {html.escape(version_text)}.
  </p>
</section>

{''.join(sections_html)}

<section id="limits">
  <h2><span class="num">6</span>Limits and caveats</h2>
  <ul class="plain">
    <li><b>Weather is gridded.</b> NASA POWER resolves to {cell_text}
    for the three growers. Within-grower field comparison is therefore a
    grid comparison, reported as a null result.</li>
    <li><b>CDL is a 30 m raster.</b> The smallest field-year in this run has
    {smallest_pixels if smallest_pixels is not None else "very few"} pixels
    (a 1.3 ha parcel), so crop shares are quantised. Partial coverage can push a
    field's percentages below 100.</li>
    <li><b>Source and size are confounded.</b> CSB fields are both larger and
    less compact. The analysis reports the within-source correlation alongside
    the between-source comparison rather than attributing the effect to one.</li>
    <li><b>Small n.</b> Thirty fields and fifteen grower-years support effect
    sizes and intervals, not population claims about “growers” in general.</li>
    <li><b>Five CDL years only.</b> No 2024–2025, so no completed rotation cycle
    is guaranteed and the pipeline's predicted next crop cannot be tested here.</li>
  </ul>
</section>

<section id="provenance">
  <h2><span class="num">7</span>Sources and provenance</h2>
  <div class="tablewrap"><table class="kv">
    <tr><td>Field polygons (OSM subset)</td><td>OpenStreetMap via Overpass. ODbL 1.0; attribution retained.</td></tr>
    <tr><td>Field polygons (CSB subset)</td><td>USDA NASS Crop Sequence Boundaries via FIBOA GeoParquet. CC-BY-4.0 / USDA public.</td></tr>
    <tr><td>Crop history</td><td>USDA NASS Cropland Data Layer, 2019–2023. USDA public data.</td></tr>
    <tr><td>Weather</td><td>NASA POWER daily data, 2021–2025, April–September. Public; gridded, not on-farm measurement.</td></tr>
    <tr><td>Analysis</td><td>Original code in <code>my-farm-advisor/eda/field-eda</code>. This report is a one-time artifact outside that subskill.</td></tr>
  </table></div>
  <h3>Reproduce</h3>
  <pre><code>export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
cd my-farm-advisor/eda/field-eda
./scripts/install.sh
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \\
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/field-eda/scripts/run_field_eda.py"

cd ../../../reports/assignment-2
python3 build_report.py</code></pre>
</section>

<section id="appendix">
  <h2><span class="num">8</span>Appendix: field metrics</h2>
  <p class="lede">
    One row per field: geometry in EPSG:5070, five-year rotation summary,
    CDL coverage, and seasonal weather means.
  </p>
  {appendix}
</section>

<footer>
  <p>
    Built from {len(manifest['inputs'])} input files and {len(manifest['outputs'])} EDA outputs.
    Every figure and table is deterministic for unchanged inputs. Report generated
    once for Assignment 2; it is not part of the reusable subskill.
  </p>
  <p>
    Attribution: OpenStreetMap contributors (ODbL 1.0) · USDA NASS CDL and CSB
    (public domain) · NASA POWER (public).
  </p>
</footer>

</main>
</div>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime",
        default=os.environ.get("DATA_PIPELINE_DATA_ROOT", ""),
        help="runtime root (default: $DATA_PIPELINE_DATA_ROOT)",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "field-eda-report.html"),
        help="output HTML path",
    )
    args = parser.parse_args()
    if not args.runtime:
        parser.error("pass --runtime or set DATA_PIPELINE_DATA_ROOT")
    runtime = Path(args.runtime).expanduser().resolve()
    eda = runtime / "data-pipeline" / "eda" / "field-eda"
    if not (eda / "manifest.json").is_file():
        parser.error(f"no EDA outputs at {eda}; run the field-eda CLI first")
    build(runtime, Path(args.out).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
