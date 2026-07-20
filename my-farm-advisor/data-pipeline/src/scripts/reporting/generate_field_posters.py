#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate large-format composable field posters."""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

matplotlib.use("Agg")

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


ensure_skill_path("farm-intelligence-reporting")
ensure_skill_path("headlands-ring")
ensure_skill_path("ssurgo-soil")
ensure_skill_path("cdl-cropland")
ensure_skill_path("nasa-power-weather")

import reporting as reporting_mod
from cdl_reporting import summarize_crop_history
from headlands_ring import split_headlands_and_interior, summarize_headlands
from paths import (
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    farm_ssurgo_full_path,
    farm_ssurgo_summary_path,
    farm_weather_path,
    field_dir,
    field_feature_path,
    field_manifest_dir,
    field_report_path,
    field_soil_polygon_path,
    shared_cdl_preferred_full_composition_path,
)
from pipeline import (
    STEP_FIELD_POSTER_RENDER,
    FieldReportingConfig,
    build_step_manifest,
    load_manifest,
    step_is_stale,
)
from ssurgo_workflows import (
    plot_headlands_om_overlay,
    plot_ssurgo_component_map,
    plot_ssurgo_property_choropleth,
    render_soil_horizon_table,
)
from weather_reporting import (
    plot_gdd_doy_overlay,
    plot_precip_boxplot,
    plot_temperature_doy_overlay,
    summarize_weather_variability,
)

_SCRIPT = Path(__file__)
_UTM_WEST = "EPSG:32615"
_UTM_EAST = "EPSG:32616"
_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
_DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
_DEFAULT_INVENTORY = _REPO / "growers" / _DEFAULT_GROWER / "farms" / _DEFAULT_FARM / "manifests" / "field-inventory.csv"
_FIELD_INVENTORY = Path(os.environ.get("AG_INVENTORY_CSV", str(_DEFAULT_INVENTORY)))
_CDL_PRIMARY = farm_cdl_preferred_full_composition_path(_DEFAULT_GROWER, _DEFAULT_FARM)
_CDL_FALLBACK = shared_cdl_preferred_full_composition_path()

PROP_MAPS = [
    ("om_r", "Organic matter (%)"),
    ("ph1to1h2o_r", "Soil pH"),
    ("awc_r", "Plant-available water (cm/cm)"),
    ("claytotal_r", "Clay (%)"),
]

_SSURGO_ATTR_AGG = {
    "compname": "first",
    "comppct_r": "first",
    "drainagecl": "first",
    "om_r": "mean",
    "ph1to1h2o_r": "mean",
    "awc_r": "mean",
    "claytotal_r": "mean",
    "sandtotal_r": "mean",
    "silttotal_r": "mean",
    "dbthirdbar_r": "mean",
    "cec7_r": "mean",
}
_SSURGO_NUMERIC_ATTRS = [
    "comppct_r",
    "om_r",
    "ph1to1h2o_r",
    "awc_r",
    "claytotal_r",
    "sandtotal_r",
    "silttotal_r",
    "dbthirdbar_r",
    "cec7_r",
]

_POSTER_TITLE_SIZE = 20
_CARD_TITLE_SIZE = 13
_PANEL_TITLE_SIZE = 11.5
_PANEL_LABEL_SIZE = 9.5
_BODY_TEXT_SIZE = 9.5


def _utm(field_row) -> str:
    return _UTM_WEST if field_row.geometry.centroid.x < -90 else _UTM_EAST


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


def _cdl_csv_path() -> Path | None:
    if _CDL_PRIMARY.exists():
        return _CDL_PRIMARY
    if _CDL_FALLBACK.exists():
        return _CDL_FALLBACK
    return None


def _canonical_field_root(field_slug: str | None) -> Path | None:
    if not field_slug:
        return None
    return field_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)


def _cached_ndvi_assets(field_slug: str | None) -> dict[str, Path | None]:
    if field_slug is None:
        return {
            "corn": None,
            "corn_peak_95": None,
            "soybean": None,
            "soybean_peak_95": None,
            "current_season_cumulative": None,
        }
    return {
        "corn": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_corn.png"
        ),
        "corn_peak_95": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_corn_peak_95.png"
        ),
        "soybean": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_soybean.png"
        ),
        "soybean_peak_95": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_soybean_peak_95.png"
        ),
        "current_season_cumulative": field_feature_path(
            _DEFAULT_GROWER,
            _DEFAULT_FARM,
            field_slug,
            "ndvi_current_season_cumulative.png",
        ),
    }


def _cached_soil_map_assets(field_slug: str | None) -> dict[str, Path | None]:
    if field_slug is None:
        return {
            "component": None,
            "organic_matter": None,
            "ph": None,
            "awc": None,
            "cec": None,
        }
    return {
        "component": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_component_map.png"
        ),
        "organic_matter": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_organic_matter_map.png"
        ),
        "ph": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_ph_map.png"
        ),
        "awc": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_awc_map.png"
        ),
        "cec": field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_cec_map.png"
        ),
    }


def _soil_attributes_by_mukey(detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df.empty or "mukey" not in detail_df.columns:
        return pd.DataFrame()
    agg_spec = {
        col: reducer for col, reducer in _SSURGO_ATTR_AGG.items() if col in detail_df.columns
    }
    if not agg_spec:
        return pd.DataFrame()
    cols = ["mukey", *agg_spec.keys()]
    soil = detail_df[cols].copy()
    soil["mukey"] = soil["mukey"].astype(str)
    for col in _SSURGO_NUMERIC_ATTRS:
        if col in soil.columns:
            soil[col] = pd.to_numeric(soil[col], errors="coerce")
    return pd.DataFrame(soil.groupby("mukey", as_index=False).agg(agg_spec))


def _ndvi_panel(ax, image_path: Path | None, title: str) -> None:
    ax.set_title(
        title, fontsize=_PANEL_TITLE_SIZE, fontweight="bold", loc="left", pad=8
    )
    if image_path is not None and image_path.exists():
        ax.imshow(mpimg.imread(image_path))
        ax.axis("off")
        return
    ax.axis("off")
    ax.text(
        0.5,
        0.54,
        "Cached NDVI card unavailable",
        ha="center",
        va="center",
        fontsize=_PANEL_LABEL_SIZE,
        fontweight="bold",
        color="#475569",
        transform=ax.transAxes,
    )
    ax.text(
        0.5,
        0.34,
        textwrap.fill(
            "Refresh Sentinel-2/Landsat assets for this field to populate the reusable NDVI panel.",
            width=28,
        ),
        ha="center",
        va="center",
        fontsize=_BODY_TEXT_SIZE,
        color="#64748b",
        transform=ax.transAxes,
    )
    ax.add_patch(
        Rectangle(
            (0.06, 0.08),
            0.88,
            0.78,
            transform=ax.transAxes,
            fill=False,
            edgecolor="#cbd5e1",
            linewidth=1.2,
            linestyle="--",
        )
    )


def _field_identity_card(
    ax, field_row, hl_summary, crop_summary, wx_row, management_bullets
):
    ax.axis("off")
    fid = str(field_row["field_id"])
    acres = float(field_row.get("area_acres", 0))
    cx = float(field_row.geometry.centroid.x)
    cy = float(field_row.geometry.centroid.y)
    hp = float(hl_summary.get("headlands_pct", 0))
    ha = float(hl_summary.get("headlands_area_acres", 0))
    lines = [
        f"Field: {fid}",
        f"Area: {acres:.1f} acres",
        f"Location: {cy:.4f} N, {abs(cx):.4f} W",
        f"Headlands: {ha:.2f} ac ({hp:.1f}% of field)",
    ]
    if crop_summary is not None and not crop_summary.empty:
        r = crop_summary.iloc[0]
        lines += [
            f"Rotation: {r.get('rotation_sequence', 'N/A')}",
            (
                f"Diversity: {r.get('crop_diversity', '?')} crop type(s); "
                f"corn {r.get('corn_years', 0)} yr; soy {r.get('soybean_years', 0)} yr"
            ),
            (
                f"Outlook: {r.get('predicted_next_crop', 'Unknown')} next -> "
                f"{r.get('predicted_following_crop', 'Unknown')} after"
            ),
            (
                f"Confidence: {str(r.get('rotation_confidence', 'unknown')).title()}; "
                f"window {r.get('history_start_year', '?')}-{r.get('history_end_year', '?')}"
            ),
        ]
    if wx_row:
        lines += [
            f"Avg temp: {wx_row.get('avg_temp_c', float('nan')):.1f} C",
            f"Avg precip: {wx_row.get('annual_precip_mm', float('nan')):.0f} mm/yr",
        ]
    if management_bullets:
        lines += ["", "Management implications:"]
        lines += [f"- {bullet}" for bullet in management_bullets[:4]]

    wrapped_lines: list[str] = []
    for line in lines:
        if not line:
            wrapped_lines.append("")
            continue
        is_bullet = line.startswith("- ")
        wrap_source = line[2:] if is_bullet else line
        initial_indent = "- " if is_bullet else ""
        subsequent_indent = "  " if is_bullet else ""
        wrapped_lines.extend(
            textwrap.wrap(
                wrap_source,
                width=40,
                initial_indent=initial_indent,
                subsequent_indent=subsequent_indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [line]
        )
    ax.text(
        0.05,
        0.95,
        "\n".join(wrapped_lines),
        va="top",
        fontsize=_BODY_TEXT_SIZE,
        transform=ax.transAxes,
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="#f0f9ff",
            edgecolor="#2563eb",
            linewidth=1.2,
        ),
    )
    ax.set_title(
        "Field identity and operations",
        fontsize=_CARD_TITLE_SIZE,
        fontweight="bold",
        loc="left",
        pad=8,
    )


def _ranking_card(ax, field_reporting_df, field_id):
    ax.axis("off")
    if field_reporting_df is None or field_reporting_df.empty:
        ax.text(0.5, 0.5, "Farm rankings unavailable", ha="center", va="center")
        return
    row = field_reporting_df[field_reporting_df["field_id"] == field_id]
    if row.empty:
        return
    r = row.iloc[0]
    rank_cols = [c for c in r.index if c.endswith("_pct_rank")][:8]
    if not rank_cols:
        ax.text(0.5, 0.5, "No ranking data", ha="center", va="center")
        return
    labels = [c.replace("_pct_rank", "").replace("_", " ") for c in rank_cols]
    values = [float(r[c]) if pd.notna(r[c]) else 50.0 for c in rank_cols]
    y_pos = np.arange(len(labels))
    colors = [
        "#22c55e" if v >= 66 else "#f59e0b" if v >= 33 else "#ef4444" for v in values
    ]
    ax_real = ax.inset_axes([0.05, 0.05, 0.90, 0.85])
    ax_real.barh(y_pos, values, color=colors, edgecolor="white", height=0.6)
    ax_real.set_yticks(y_pos)
    ax_real.set_yticklabels(labels, fontsize=_PANEL_LABEL_SIZE)
    ax_real.set_xlim(0, 100)
    ax_real.set_xlabel("Farm percentile", fontsize=_PANEL_LABEL_SIZE)
    ax_real.tick_params(axis="x", labelsize=_PANEL_LABEL_SIZE)
    ax_real.axvline(50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax_real.grid(True, axis="x", alpha=0.25)
    ax.set_title(
        "Farm-relative standing",
        fontsize=_CARD_TITLE_SIZE,
        fontweight="bold",
        loc="left",
    )


def _soil_map_panel(ax, image_path: Path | None, title: str, fallback_render) -> None:
    ax.set_title(
        title, fontsize=_PANEL_TITLE_SIZE, fontweight="bold", loc="left", pad=8
    )
    if image_path is not None and image_path.exists():
        ax.imshow(mpimg.imread(image_path))
        ax.axis("off")
        return
    fallback_render(ax)


def _render_field_poster(
    field_id,
    field_index,
    field_gdf,
    ssurgo_wgs84,
    detail_df,
    weather,
    cdl,
    field_reporting_df,
    field_slug,
    output_path,
):
    field_row = field_gdf.iloc[0]
    field_wgs84 = field_gdf.to_crs("EPSG:4326")
    field_utm = field_gdf.to_crs(_utm(field_row))
    ring_utm, _ = split_headlands_and_interior(field_utm, width_m=9.0)
    hl = summarize_headlands(field_utm, ring_utm).iloc[0].to_dict()

    fw = weather[weather["field_id"] == field_id].copy()
    fw["date"] = pd.to_datetime(fw["date"])
    if not cdl.empty and "field_id" in cdl.columns:
        fc = cdl[cdl["field_id"] == field_id].copy()
        crop_sum = summarize_crop_history(fc, window_years=5)
    else:
        fc = pd.DataFrame()
        crop_sum = pd.DataFrame()
    wx_row = None
    if not fw.empty:
        ws = summarize_weather_variability(fw)
        if not ws.empty:
            wx_row = ws.iloc[0].to_dict()

    merged_row = field_row.to_dict()
    if field_reporting_df is not None and not field_reporting_df.empty:
        match = field_reporting_df[field_reporting_df["field_id"] == field_id]
        if not match.empty:
            merged_row.update(match.iloc[0].to_dict())
    management_bullets = reporting_mod.compute_management_implications(merged_row)

    fig = plt.figure(figsize=(28, 36))
    fig.patch.set_facecolor("#fafaf9")
    fig.suptitle(
        f"Field Intelligence Report — {field_id[-8:]}  ·  {float(field_row.get('area_acres', 0)):.1f} ac  ·  Iowa Corn Belt",
        fontsize=_POSTER_TITLE_SIZE,
        fontweight="bold",
        y=0.993,
        color="#1e293b",
        fontfamily="serif",
    )
    gs = fig.add_gridspec(
        6, 4, hspace=0.42, wspace=0.28, left=0.04, right=0.97, top=0.975, bottom=0.015
    )

    ndvi_assets = _cached_ndvi_assets(field_slug)
    soil_map_assets = _cached_soil_map_assets(field_slug)

    _field_identity_card(
        fig.add_subplot(gs[0, 0]), field_row, hl, crop_sum, wx_row, management_bullets
    )
    _soil_map_panel(
        fig.add_subplot(gs[0, 1]),
        soil_map_assets["component"],
        "Soil components (SSURGO)",
        lambda ax: plot_ssurgo_component_map(
            ax, field_wgs84, ssurgo_wgs84, "Soil components (SSURGO)", ctx=True
        ),
    )
    plot_headlands_om_overlay(
        fig.add_subplot(gs[0, 2:]), field_utm, ring_utm, ssurgo_wgs84, ctx=True
    )

    poster_property_specs = [
        ("organic_matter", "Organic matter (%)", "om_r"),
        ("ph", "Soil pH", "ph1to1h2o_r"),
        ("awc", "Available water capacity", "awc_r"),
        ("cec", "CEC", "cec7_r"),
    ]
    for i, (map_slug, title, prop) in enumerate(poster_property_specs):
        _soil_map_panel(
            fig.add_subplot(gs[1, i]),
            soil_map_assets[map_slug],
            title,
            lambda ax, prop=prop, title=title: plot_ssurgo_property_choropleth(
                ax, field_wgs84, ssurgo_wgs84, prop, title, ctx=True
            ),
        )

    render_soil_horizon_table(fig.add_subplot(gs[2, 0:2]), detail_df)
    plot_temperature_doy_overlay(
        fig.add_subplot(gs[2, 2:]),
        fw,
        title="Temperature by day-of-year with frost windows",
    )

    plot_gdd_doy_overlay(
        fig.add_subplot(gs[3, 0:2]),
        fw,
        title="Cumulative GDD by day-of-year with frost windows",
    )
    plot_precip_boxplot(
        fig.add_subplot(gs[3, 2:]), fw, title="Cumulative precipitation by day-of-year"
    )

    _ndvi_panel(fig.add_subplot(gs[4, 0]), ndvi_assets["corn"], "Corn average NDVI")
    _ndvi_panel(
        fig.add_subplot(gs[4, 1]), ndvi_assets["soybean"], "Soybean average NDVI"
    )
    _ndvi_panel(
        fig.add_subplot(gs[4, 2:]),
        ndvi_assets["current_season_cumulative"],
        "Cumulative NDVI by crop and year",
    )

    _ndvi_panel(
        fig.add_subplot(gs[5, 0]),
        ndvi_assets["corn_peak_95"],
        "Corn 95th %ile peak NDVI",
    )
    _ndvi_panel(
        fig.add_subplot(gs[5, 1]),
        ndvi_assets["soybean_peak_95"],
        "Soybean 95th %ile peak NDVI",
    )
    _ranking_card(fig.add_subplot(gs[5, 2:]), field_reporting_df, field_id)

    for ax in fig.axes:
        ax.title.set_fontsize(max(ax.title.get_fontsize(), _PANEL_TITLE_SIZE))
        ax.title.set_fontweight("bold")
        if hasattr(ax, "xaxis"):
            ax.xaxis.label.set_size(max(ax.xaxis.label.get_size(), _PANEL_LABEL_SIZE))
        if hasattr(ax, "yaxis"):
            ax.yaxis.label.set_size(max(ax.yaxis.label.get_size(), _PANEL_LABEL_SIZE))
        ax.tick_params(axis="both", labelsize=_PANEL_LABEL_SIZE)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        output_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)


def main() -> None:
    print("=" * 60)
    print("Field posters — large-format composable")
    print("=" * 60)
    force = os.environ.get("AG_FORCE") == "1"

    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
        grower_slug=_DEFAULT_GROWER,
        farm_slug=_DEFAULT_FARM,
    )

    fields = gpd.read_file(_REPO / config.field_boundary_path)
    soil_full = pd.read_csv(farm_ssurgo_full_path(_DEFAULT_GROWER, _DEFAULT_FARM))
    soil_summary = pd.read_csv(farm_ssurgo_summary_path(_DEFAULT_GROWER, _DEFAULT_FARM))
    weather = pd.read_csv(
        farm_weather_path(_DEFAULT_GROWER, _DEFAULT_FARM), parse_dates=["date"]
    )
    cdl_path = _cdl_csv_path()
    if cdl_path is not None:
        cdl = pd.read_csv(cdl_path)
    else:
        cdl = pd.DataFrame()
        print("  Warning: CDL composition data not available; skipping crop history")
    field_slug_lookup = _field_slug_lookup()

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

    field_reporting_df = reporting_mod.build_field_reporting_dataset(
        fields,
        headlands_summary=headlands_df,
        soil_summary=soil_summary,
        weather_summary=wx_summary,
        cdl_summary=crop_sum,
    )

    for idx_num, frow in enumerate(fields.itertuples(index=False), start=0):
        field_id = getattr(frow, "field_id")
        field_slug = field_slug_lookup.get(str(field_id))
        if field_slug is None:
            print(f"skip  {field_id} (no field slug)")
            continue
        manifest_dir = field_manifest_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        output_path = field_report_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "field_report.png"
        )
        prior = load_manifest(
            manifest_dir / f"{STEP_FIELD_POSTER_RENDER}_{field_id}.json"
        )

        cache_path = field_soil_polygon_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        ndvi_asset_paths = [
            path
            for path in _cached_ndvi_assets(field_slug).values()
            if path is not None and path.exists()
        ]
        soil_map_asset_paths = [
            path
            for path in _cached_soil_map_assets(field_slug).values()
            if path is not None and path.exists()
        ]
        input_paths = [
            config.field_boundary_path,
            str(farm_ssurgo_full_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            str(farm_weather_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            *([str(cdl_path.relative_to(_REPO))] if cdl_path is not None else []),
            *[str(path) for path in ndvi_asset_paths],
            *[str(path) for path in soil_map_asset_paths],
        ]
        if cache_path.exists():
            input_paths.append(str(cache_path.relative_to(_REPO)))

        manifest = build_step_manifest(
            step_name=f"{STEP_FIELD_POSTER_RENDER}_{field_id}",
            input_paths=input_paths,
            output_paths=[output_path],
            code_paths=[_SCRIPT],
            config=config,
        )
        if not force and not step_is_stale(manifest, prior):
            print(f"skip  {field_id}")
            continue
        print(f"run   {field_id}")
        field_gdf = fields.iloc[[idx_num]].copy()
        if "field_id" in soil_full.columns:
            detail_df = pd.DataFrame(soil_full.loc[soil_full["field_id"] == field_id].copy())
        else:
            detail_df = pd.DataFrame()

        # Load SSURGO polygons if available
        ssurgo_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if cache_path.exists():
            try:
                ssurgo_gdf = gpd.read_file(cache_path)
                # Merge with soil data for component names
                if (
                    not detail_df.empty
                    and "mukey" in detail_df.columns
                    and "mukey" in ssurgo_gdf.columns
                ):
                    soil_agg = _soil_attributes_by_mukey(detail_df)
                    if not soil_agg.empty:
                        ssurgo_gdf["mukey"] = ssurgo_gdf["mukey"].astype(str)
                        duplicate_attrs = [
                            col
                            for col in soil_agg.columns
                            if col != "mukey" and col in ssurgo_gdf.columns
                        ]
                        if duplicate_attrs:
                            ssurgo_gdf = ssurgo_gdf.drop(columns=duplicate_attrs)
                        ssurgo_gdf = ssurgo_gdf.merge(soil_agg, on="mukey", how="left")
                try:
                    ssurgo_gdf = gpd.GeoDataFrame(
                        ssurgo_gdf, geometry="geometry", crs=ssurgo_gdf.crs
                    )
                    clip_target = field_gdf.to_crs(ssurgo_gdf.crs or field_gdf.crs)
                    ssurgo_gdf = gpd.clip(ssurgo_gdf, clip_target)
                    ssurgo_gdf = ssurgo_gdf[~ssurgo_gdf.geometry.is_empty].copy()
                except Exception:
                    pass
                print(f"    Loaded {len(ssurgo_gdf)} SSURGO polygons")
            except Exception as e:
                print(f"    Warning: Could not load SSURGO polygons: {e}")

        _render_field_poster(
            field_id=field_id,
            field_index=idx_num + 1,
            field_gdf=field_gdf,
            ssurgo_wgs84=ssurgo_gdf,
            detail_df=detail_df,
            weather=weather,
            cdl=cdl,
            field_reporting_df=field_reporting_df,
            field_slug=field_slug_lookup.get(str(field_id)),
            output_path=output_path,
        )
        manifest.status = "complete"
        manifest.write(manifest_dir / f"{STEP_FIELD_POSTER_RENDER}_{field_id}.json")
        print(f"   saved {output_path.relative_to(_REPO)}")

    print(
        f"\n✓ Field posters complete → {field_report_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug_lookup[next(iter(field_slug_lookup))], 'field_report.png').parent if field_slug_lookup else 'no-field-reports'}"
    )


if __name__ == "__main__":
    main()
