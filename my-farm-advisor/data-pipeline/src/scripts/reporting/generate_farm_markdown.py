#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate markdown farm intelligence report."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from reporting_bootstrap import ensure_skill_path  # noqa: E402


_FARM_INTEL_SKILL = ensure_skill_path("farm-intelligence-reporting")
_HEADLANDS_SKILL = ensure_skill_path("headlands-ring")
_CDL_SKILL = ensure_skill_path("cdl-cropland")
_CROP_STRATEGY_SKILL = ensure_skill_path("crop-strategy")
_WEATHER_SKILL = ensure_skill_path("nasa-power-weather")

from cdl_reporting import summarize_crop_history
from crop_strategy import generate_farm_recommendations, generate_field_recommendations
from headlands_ring import split_headlands_and_interior, summarize_headlands
from paths import (
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    farm_manifest_dir,
    farm_report_asset_path,
    farm_report_basename,
    farm_ssurgo_summary_path,
    farm_weather_path,
    field_feature_path,
    shared_cdl_preferred_full_composition_path,
)
from pipeline import (
    STEP_FARM_MARKDOWN,
    FieldReportingConfig,
    build_step_manifest,
    load_manifest,
    step_is_stale,
)
from reporting import (
    build_farm_reporting_dataset,
    build_field_reporting_dataset,
    compute_management_implications,
)
from weather_reporting import summarize_weather_variability

_SCRIPT = Path(__file__)
_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
_DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
_DEFAULT_INVENTORY = _REPO / "growers" / _DEFAULT_GROWER / "farms" / _DEFAULT_FARM / "manifests" / "field-inventory.csv"
_FIELD_INVENTORY = Path(os.environ.get("AG_INVENTORY_CSV", str(_DEFAULT_INVENTORY)))
_CDL_PRIMARY = farm_cdl_preferred_full_composition_path(_DEFAULT_GROWER, _DEFAULT_FARM)
_CDL_FALLBACK = shared_cdl_preferred_full_composition_path()
_CODE_PATHS = [
    _SCRIPT,
    _CROP_STRATEGY_SKILL / "crop_strategy.py",
    _FARM_INTEL_SKILL / "reporting.py",
    _CDL_SKILL / "cdl_reporting.py",
    _HEADLANDS_SKILL / "headlands_ring.py",
    _WEATHER_SKILL / "weather_reporting.py",
    _LIB / "paths.py",
]


def _utm(frow) -> str:
    return "EPSG:32615" if frow.geometry.centroid.x < -90 else "EPSG:32616"


def _safe(val) -> str:
    if val is None or (not isinstance(val, str) and pd.isna(val)):
        return "—"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)


def _as_float(val, default: float = 0.0) -> float:
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _field_slug_lookup(inventory_path: Path = _FIELD_INVENTORY) -> dict[str, str]:
    if not inventory_path.exists():
        return {}
    inventory = pd.read_csv(inventory_path)
    if not {"field_id", "field_slug"}.issubset(inventory.columns):
        return {}
    return {
        str(row["field_id"]): str(row["field_slug"])
        for _, row in inventory[["field_id", "field_slug"]].dropna().iterrows()
    }


def _ndvi_asset_links(field_slug: str | None) -> list[str]:
    if not field_slug:
        return []
    links = []
    for filename, label in [
        ("ndvi_corn.png", "Corn average NDVI"),
        ("ndvi_corn_peak_95.png", "Corn 95th %ile peak NDVI"),
        ("ndvi_soybean.png", "Soybean average NDVI"),
        ("ndvi_soybean_peak_95.png", "Soybean 95th %ile peak NDVI"),
        ("ndvi_current_season_cumulative.png", "Cumulative NDVI by crop and year"),
    ]:
        path = field_feature_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug, filename)
        if path.exists():
            links.append(
                f"[{label}](../../fields/{field_slug}/derived/features/{filename})"
            )
    return links


def _cdl_csv_path() -> Path | None:
    if _CDL_PRIMARY.exists():
        return _CDL_PRIMARY
    if _CDL_FALLBACK.exists():
        return _CDL_FALLBACK
    return None


def _field_centroid_latitude(fields: gpd.GeoDataFrame, row_index: int) -> float:
    row = fields.iloc[[row_index]]
    if row.crs:
        projected = row.to_crs(_utm(row.iloc[0]))
        centroid = projected.geometry.centroid.iloc[0]
        centroid_wgs84 = (
            gpd.GeoSeries([centroid], crs=projected.crs).to_crs("EPSG:4326").iloc[0]
        )
        return float(centroid_wgs84.y)
    return float(row.geometry.centroid.iloc[0].y)


def main() -> None:
    print("=" * 60)
    print("Farm Markdown Report")
    print("=" * 60)
    force = os.environ.get("AG_FORCE") == "1"

    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
        grower_slug=_DEFAULT_GROWER,
        farm_slug=_DEFAULT_FARM,
    )
    manifest_dir = farm_manifest_dir(_DEFAULT_GROWER, _DEFAULT_FARM)
    output_path = farm_report_asset_path(_DEFAULT_GROWER, _DEFAULT_FARM, "md")
    field_slug_lookup = _field_slug_lookup()
    ndvi_input_paths = []
    for field_slug in field_slug_lookup.values():
        for filename in (
            "ndvi_corn.png",
            "ndvi_corn_peak_95.png",
            "ndvi_soybean.png",
            "ndvi_soybean_peak_95.png",
            "ndvi_current_season_cumulative.png",
        ):
            path = field_feature_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug, filename)
            if path.exists():
                ndvi_input_paths.append(str(path.relative_to(_REPO)))

    prior = load_manifest(manifest_dir / f"{STEP_FARM_MARKDOWN}.json")
    _md_cdl_path = _cdl_csv_path()
    manifest = build_step_manifest(
        step_name=STEP_FARM_MARKDOWN,
        input_paths=[
            config.field_boundary_path,
            str(farm_ssurgo_summary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            str(farm_weather_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            *([str(_md_cdl_path.relative_to(_REPO))] if _md_cdl_path is not None else []),
            *ndvi_input_paths,
        ],
        output_paths=[output_path],
        code_paths=_CODE_PATHS,
        config=config,
    )
    if not force and not step_is_stale(manifest, prior):
        print("skip  Markdown (current)")
        return

    fields = gpd.read_file(_REPO / config.field_boundary_path)
    soil_summary = pd.read_csv(farm_ssurgo_summary_path(_DEFAULT_GROWER, _DEFAULT_FARM))
    weather = pd.read_csv(
        farm_weather_path(_DEFAULT_GROWER, _DEFAULT_FARM),
        parse_dates=["date"],
    )
    _cdl_path = _cdl_csv_path()
    if _cdl_path is not None:
        cdl = pd.read_csv(_cdl_path)
    else:
        cdl = pd.DataFrame()
        print("  Warning: CDL composition data not available; skipping crop history")
    hl_rows = []
    for idx, frow in fields.iterrows():
        fgdf = fields.iloc[[idx]].to_crs(_utm(frow))
        ring, _ = split_headlands_and_interior(fgdf, width_m=9.0)
        s = summarize_headlands(fgdf, ring).iloc[0].to_dict()
        s["field_id"] = frow["field_id"]
        hl_rows.append(s)
    headlands_df = pd.DataFrame(hl_rows)

    wx_summary = summarize_weather_variability(weather)
    crop_sum = summarize_crop_history(cdl, window_years=5)

    field_df = build_field_reporting_dataset(
        fields,
        headlands_summary=headlands_df,
        soil_summary=soil_summary,
        weather_summary=wx_summary,
        cdl_summary=crop_sum,
    )
    farm_df = build_farm_reporting_dataset(field_df)
    farm_strategy = generate_farm_recommendations(
        field_df, farm_name=_DEFAULT_FARM_NAME
    )

    total_ac = float(farm_df.iloc[0].get("total_acres", 0))
    n_fields = int(farm_df.iloc[0].get("field_count", len(fields)))

    md_lines = []
    md_lines.append(f"# {_DEFAULT_FARM_NAME} Intelligence Report")
    md_lines.append("")
    md_lines.append(f"**Farm:** {_DEFAULT_FARM_NAME}")
    md_lines.append(f"**Fields:** {n_fields}")
    md_lines.append(f"**Total Area:** {total_ac:.1f} acres")
    md_lines.append("**Analysis Period:** 2021-2025")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Farm Overview")
    md_lines.append("")
    md_lines.append("| Metric | Value |")
    md_lines.append("|--------|-------|")
    md_lines.append(f"| Total Fields | {n_fields} |")
    md_lines.append(f"| Total Area | {total_ac:.1f} acres |")
    md_lines.append(f"| Avg Field Size | {total_ac / max(n_fields, 1):.1f} acres |")

    for col, label in [
        ("avg_avg_om_pct", "Avg Organic Matter"),
        ("avg_avg_ph", "Avg pH"),
        ("avg_total_aws_inches", "Avg Water Storage"),
    ]:
        if col in farm_df.columns and pd.notna(farm_df.iloc[0].get(col)):
            md_lines.append(f"| {label} | {float(farm_df.iloc[0][col]):.2f} |")

    md_lines.append("")
    md_lines.append("### 2026 Strategy Outlook")
    for bullet in farm_strategy.get("bullets", []):
        md_lines.append(f"- {bullet}")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Field Summary Table")
    md_lines.append("")

    cols = [
        "field_id",
        "area_acres",
        "headlands_pct",
        "dominant_soil",
        "avg_om_pct",
        "avg_ph",
        "total_aws_inches",
        "drainage_class",
        "crop_diversity",
        "corn_years",
        "soybean_years",
    ]
    display_cols = [c for c in cols if c in field_df.columns]

    header = "| " + " | ".join(display_cols) + " |"
    md_lines.append(header)
    md_lines.append("|" + "|".join([" --- " for _ in display_cols]) + "|")

    for _, row in field_df.iterrows():
        vals = [_safe(row.get(c, "—")) for c in display_cols]
        md_lines.append("| " + " | ".join(vals) + " |")

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Individual Field Reports")
    md_lines.append("")

    for idx_num, (_, frow) in enumerate(fields.iterrows()):
        fid = str(frow["field_id"])
        field_slug = field_slug_lookup.get(str(fid), "")
        acres = _as_float(frow.get("area_acres", 0), 0.0)
        row_match = field_df[field_df["field_id"] == fid]
        row_dict = row_match.iloc[0].to_dict() if not row_match.empty else {}

        md_lines.append(f"### Field {fid[-8:]} ({acres:.1f} acres)")
        md_lines.append("")
        md_lines.append(
            f"**Poster:** [field_report.png](../../fields/{field_slug}/derived/reports/field_report.png)"
        )
        md_lines.append("")

        soil_cards_exist = False
        soil_card_links = []
        for card_type, label in [
            ("properties", "Soil Properties"),
            ("texture", "Texture RGB"),
        ]:
            card_link = (
                f"../../fields/{field_slug}/derived/summaries/soil_{card_type}.png"
            )
            card_path = output_path.parent / card_link
            if card_path.exists():
                soil_cards_exist = True
                soil_card_links.append(f"[{label}]({card_link})")

        if soil_cards_exist:
            md_lines.append(f"**Soil Profile Cards:** {' | '.join(soil_card_links)}")
            md_lines.append("")

        ndvi_links = _ndvi_asset_links(field_slug_lookup.get(str(fid)))
        if ndvi_links:
            md_lines.append(f"**NDVI Cards:** {' | '.join(ndvi_links)}")
            md_lines.append("")

        if row_dict.get("rotation_sequence"):
            md_lines.append(
                f"**Crop Rotation History:** {_safe(row_dict.get('rotation_sequence'))}"
            )
            md_lines.append("")
        if row_dict.get("rotation_outlook"):
            md_lines.append(
                f"**Heuristic Crop Outlook:** {_safe(row_dict.get('rotation_outlook'))}"
            )
            md_lines.append("")

        implications = compute_management_implications(row_dict)
        md_lines.append("**Management Implications:**")
        for imp in implications:
            md_lines.append(f"- {imp}")
        md_lines.append("")

        strategy = generate_field_recommendations(
            row_dict,
            centroid_lat=_field_centroid_latitude(fields, idx_num),
        )
        md_lines.append("**2026 Crop Strategy:**")
        md_lines.append(
            f"- Focus: {_safe(strategy.get('crop_focus'))}; Region: {_safe(strategy.get('region'))}; Planting window: {_safe(strategy.get('planting_window'))}"
        )
        for recommendation in strategy.get("recommendations", []):
            md_lines.append(f"- {recommendation}")
        md_lines.append("**Monitor Closely:**")
        for item in strategy.get("monitoring", []):
            md_lines.append(f"- {item}")
        md_lines.append("")

        md_lines.append("| Property | Value |")
        md_lines.append("|----------|-------|")
        for col, label in [
            ("area_acres", "Area"),
            ("headlands_pct", "Headlands %"),
            ("total_aws_inches", "Total AWS"),
            ("avg_om_pct", "Avg OM %"),
            ("avg_ph", "Avg pH"),
            ("drainage_class", "Drainage"),
            ("dominant_soil", "Dominant Soil"),
        ]:
            if col in row_dict:
                md_lines.append(f"| {label} | {_safe(row_dict.get(col))} |")
        md_lines.append("")

        rank_cols = [c for c in row_dict if c.endswith("_pct_rank")]
        if rank_cols:
            md_lines.append("**Farm-Relative Rankings:**")
            for rc in rank_cols[:6]:
                base = rc.replace("_pct_rank", "").replace("_", " ")
                val = row_dict.get(rc)
                pct = (
                    float(val)
                    if val is not None and not (isinstance(val, float) and pd.isna(val))
                    else 50.0
                )
                md_lines.append(f"- {base}: {pct:.0f}th percentile")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_lines.append("")
    md_lines.append("## Outputs")
    md_lines.append("")
    farm_poster_name = farm_report_basename(_DEFAULT_FARM, "png")
    farm_html_name = farm_report_basename(_DEFAULT_FARM, "html")
    md_lines.append(f"- Farm Poster: [{farm_poster_name}](./{farm_poster_name})")
    md_lines.append(f"- HTML Report: [{farm_html_name}](./{farm_html_name})")
    md_lines.append("- Field Posters: [field_cards/](./field_cards/)")
    md_lines.append("- Soil Profile Cards: [soil_cards/](./soil_cards/)")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("*Generated by farm-intelligence-reporting system*")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md_lines), encoding="utf-8")

    manifest.status = "complete"
    manifest.write(manifest_dir / f"{STEP_FARM_MARKDOWN}.json")
    print(f"✓ Markdown report saved → {output_path}")
    print(f"  Size: {output_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
