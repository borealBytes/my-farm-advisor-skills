#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
ensure_skill_path("cdl-cropland")
ensure_skill_path("nasa-power-weather")

from cdl_reporting import plot_crop_mix_stacked_100, summarize_crop_history
from headlands_ring import split_headlands_and_interior, summarize_headlands
from paths import (
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    farm_manifest_dir,
    farm_report_asset_path,
    farm_ssurgo_summary_path,
    farm_weather_path,
    field_feature_path,
    shared_cdl_preferred_full_composition_path,
)
from pipeline import (
    STEP_FARM_POSTER_RENDER,
    FieldReportingConfig,
    build_step_manifest,
    load_manifest,
    step_is_stale,
)
from reporting import build_farm_reporting_dataset, build_field_reporting_dataset
from weather_reporting import (
    plot_gdd_doy_overlay,
    plot_precip_boxplot,
    plot_temperature_doy_overlay,
    summarize_weather_variability,
)

_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
_DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
_SCRIPT = Path(__file__)
_CDL_PRIMARY = farm_cdl_preferred_full_composition_path(_DEFAULT_GROWER, _DEFAULT_FARM)
_CDL_FALLBACK = shared_cdl_preferred_full_composition_path()
_DEFAULT_INVENTORY = _REPO / "growers" / _DEFAULT_GROWER / "farms" / _DEFAULT_FARM / "manifests" / "field-inventory.csv"
_FIELD_INVENTORY = Path(os.environ.get("AG_INVENTORY_CSV", str(_DEFAULT_INVENTORY)))


def _utm(frow) -> str:
    return "EPSG:32615" if frow.geometry.centroid.x < -90 else "EPSG:32616"


def _ranking_bars(ax, field_df, metric_col, title):
    if field_df.empty or metric_col not in field_df.columns:
        ax.set_visible(False)
        return
    df = field_df[["field_id", metric_col]].dropna().sort_values(metric_col)
    labels = [str(f)[-6:] for f in df["field_id"]]
    values = df[metric_col].astype(float).tolist()
    y = np.arange(len(labels))
    ax.barh(y, values, color="#3b82f6", edgecolor="white", height=0.65)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.grid(True, axis="x", alpha=0.3)


def _risk_matrix(ax, field_df):
    ax.set_title(
        "Risk / opportunity matrix", fontsize=10, fontweight="bold", loc="left"
    )
    cap_col = "total_aws_inches" if "total_aws_inches" in field_df.columns else None
    risk_col = "headlands_pct" if "headlands_pct" in field_df.columns else None
    if cap_col is None or risk_col is None:
        ax.text(0.5, 0.5, "Insufficient data for matrix", ha="center", va="center")
        return
    x = field_df[cap_col].fillna(field_df[cap_col].median()).astype(float)
    y = field_df[risk_col].fillna(field_df[risk_col].median()).astype(float)
    sz = (
        field_df["area_acres"].fillna(50).astype(float) * 8
        if "area_acres" in field_df.columns
        else 60
    )
    ax.scatter(x, y, s=sz, alpha=0.7, c="#3b82f6", edgecolors="#1e40af")
    for _, r in field_df.iterrows():
        ax.annotate(
            str(r["field_id"])[-5:],
            (float(r.get(cap_col, 0) or 0), float(r.get(risk_col, 0) or 0)),
            fontsize=7,
            ha="center",
        )
    ax.set_xlabel("Water holding capacity (total AWS, in)", fontsize=8)
    ax.set_ylabel("Headlands burden (%)", fontsize=8)
    ax.grid(True, alpha=0.25)


def _cdl_csv_path() -> Path | None:
    if _CDL_PRIMARY.exists():
        return _CDL_PRIMARY
    if _CDL_FALLBACK.exists():
        return _CDL_FALLBACK
    return None


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


def _spotlight_field_slug(fields: gpd.GeoDataFrame) -> tuple[str | None, str | None]:
    if fields.empty or "field_id" not in fields.columns:
        return None, None
    field_slug_lookup = _field_slug_lookup()
    has_area = "area_acres" in fields.columns and bool(
        fields["area_acres"].notna().any()
    )
    if has_area:
        row = fields.loc[fields["area_acres"].astype(float).idxmax()]
    else:
        row = fields.iloc[0]
    field_id = str(row["field_id"])
    return field_id, field_slug_lookup.get(field_id)


def _image_panel(ax, path: Path | None, title: str, note: str | None = None) -> None:
    ax.set_title(title, fontsize=9.5, fontweight="bold", loc="left")
    if path is not None and path.exists():
        ax.imshow(mpimg.imread(path))
        ax.axis("off")
        return
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        note or "Image unavailable",
        ha="center",
        va="center",
        fontsize=8,
        color="#64748b",
        wrap=True,
        transform=ax.transAxes,
    )


def main() -> None:
    print("=" * 60)
    print("Farm portfolio poster")
    print("=" * 60)
    force = os.environ.get("AG_FORCE") == "1"

    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
        grower_slug=_DEFAULT_GROWER,
        farm_slug=_DEFAULT_FARM,
    )
    manifest_dir = farm_manifest_dir(config.grower_slug, config.farm_slug)
    output_path = farm_report_asset_path(config.grower_slug, config.farm_slug, "png")

    prior = load_manifest(manifest_dir / f"{STEP_FARM_POSTER_RENDER}.json")
    field_id, spotlight_slug = _spotlight_field_slug(
        gpd.read_file(_REPO / config.field_boundary_path)
    )
    spotlight_inputs: list[str] = []
    spotlight_assets: dict[str, Path] = {}
    if spotlight_slug:
        spotlight_assets = {
            "corn": field_feature_path(
                config.grower_slug, config.farm_slug, spotlight_slug, "ndvi_corn.png"
            ),
            "corn_peak_95": field_feature_path(
                config.grower_slug,
                config.farm_slug,
                spotlight_slug,
                "ndvi_corn_peak_95.png",
            ),
            "soybean": field_feature_path(
                config.grower_slug, config.farm_slug, spotlight_slug, "ndvi_soybean.png"
            ),
            "soybean_peak_95": field_feature_path(
                config.grower_slug,
                config.farm_slug,
                spotlight_slug,
                "ndvi_soybean_peak_95.png",
            ),
            "cumulative": field_feature_path(
                config.grower_slug,
                config.farm_slug,
                spotlight_slug,
                "ndvi_current_season_cumulative.png",
            ),
        }
        spotlight_inputs = [
            str(path.relative_to(_REPO))
            for path in spotlight_assets.values()
            if path.exists()
        ]
    _cls_cdl_path = _cdl_csv_path()
    manifest = build_step_manifest(
        step_name=STEP_FARM_POSTER_RENDER,
        input_paths=[
            config.field_boundary_path,
            str(farm_ssurgo_summary_path(config.grower_slug, config.farm_slug)),
            str(farm_weather_path(config.grower_slug, config.farm_slug)),
            *([str(_cls_cdl_path.relative_to(_REPO))] if _cls_cdl_path is not None else []),
            *spotlight_inputs,
        ],
        output_paths=[output_path],
        code_paths=[_SCRIPT],
        config=config,
    )
    if not force and not step_is_stale(manifest, prior):
        print("skip  farm poster (current)")
        return

    fields = gpd.read_file(_REPO / config.field_boundary_path)
    soil_summary = pd.read_csv(
        farm_ssurgo_summary_path(config.grower_slug, config.farm_slug)
    )
    weather = pd.read_csv(
        farm_weather_path(config.grower_slug, config.farm_slug),
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

    total_ac = float(farm_df.iloc[0].get("total_acres", 0))
    n_fields = int(farm_df.iloc[0].get("field_count", len(fields)))

    fig = plt.figure(figsize=(28, 38))
    fig.patch.set_facecolor("#fafaf9")
    fig.suptitle(
        f"Farm Intelligence Report — {_DEFAULT_FARM_NAME}  ·  {total_ac:.0f} ac  ·  {n_fields} fields",
        fontsize=16,
        fontweight="bold",
        y=0.993,
        color="#1e293b",
        fontfamily="serif",
    )
    gs = fig.add_gridspec(
        6, 4, hspace=0.40, wspace=0.28, left=0.04, right=0.97, top=0.975, bottom=0.015
    )

    ax_map = fig.add_subplot(gs[0, 0:2])
    fields.boundary.plot(ax=ax_map, color="darkgreen", linewidth=1.5)
    projected_fields = fields.to_crs("EPSG:5070") if fields.crs else fields
    centroids = gpd.GeoSeries(
        projected_fields.geometry.centroid, crs=projected_fields.crs
    ).to_crs(fields.crs or "EPSG:4326")
    sz = (
        fields["area_acres"].fillna(30).astype(float) * 6
        if "area_acres" in fields.columns
        else 100
    )
    ax_map.scatter(centroids.x, centroids.y, s=sz, color="#2563eb", alpha=0.7, zorder=5)
    for _, frow in fields.iterrows():
        c = (
            gpd.GeoSeries([frow.geometry], crs=fields.crs or "EPSG:4326")
            .to_crs("EPSG:5070")
            .centroid.to_crs(fields.crs or "EPSG:4326")
            .iloc[0]
        )
        ax_map.annotate(
            str(frow["field_id"])[-5:],
            (c.x, c.y),
            fontsize=7,
            ha="center",
            color="white",
            fontweight="bold",
            zorder=6,
        )
    ax_map.set_title("Farm field map", fontsize=11, fontweight="bold", loc="left")
    ax_map.set_axis_off()

    ax_summary = fig.add_subplot(gs[0, 2])
    ax_summary.axis("off")
    row = farm_df.iloc[0]
    summary_lines = [
        f"Farm:       {_DEFAULT_FARM_NAME}",
        f"Fields:     {n_fields}",
        f"Total area: {total_ac:.1f} acres",
        f"Avg field:  {float(row.get('avg_area_acres', total_ac / max(n_fields, 1))):.1f} acres",
    ]
    for col, label in [
        ("avg_avg_om_pct", "Avg OM"),
        ("avg_avg_ph", "Avg pH"),
        ("avg_total_aws_inches", "Avg AWS (in)"),
    ]:
        if col in row.index and pd.notna(row[col]):
            summary_lines.append(f"{label + ':':12s}{float(row[col]):.2f}")
    ax_summary.text(
        0.05,
        0.95,
        "\n".join(summary_lines),
        va="top",
        fontsize=9.5,
        transform=ax_summary.transAxes,
        fontfamily="monospace",
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="#f0f9ff",
            edgecolor="#2563eb",
            linewidth=1.2,
        ),
    )
    ax_summary.set_title("Farm overview", fontsize=11, fontweight="bold", loc="left")

    plot_crop_mix_stacked_100(
        fig.add_subplot(gs[0, 3]), cdl, title="Farm crop composition by year"
    )

    _ranking_bars(
        fig.add_subplot(gs[1, 0]), field_df, "area_acres", "Field size (acres)"
    )
    _ranking_bars(
        fig.add_subplot(gs[1, 1]), field_df, "total_aws_inches", "Total AWS (inches)"
    )
    _ranking_bars(fig.add_subplot(gs[1, 2]), field_df, "avg_om_pct", "Avg OM (%)")
    _ranking_bars(fig.add_subplot(gs[1, 3]), field_df, "headlands_pct", "Headlands (%)")

    spotlight_title = (
        f"Remote sensing spotlight — {field_id[-6:]}"
        if field_id and spotlight_slug
        else "Remote sensing spotlight"
    )
    panel = fig.add_subplot(gs[2, :])
    panel.axis("off")
    panel.set_title(spotlight_title, fontsize=11, fontweight="bold", loc="left", pad=8)
    sub = gs[2, :].subgridspec(2, 4, hspace=0.18, wspace=0.2)
    _image_panel(
        fig.add_subplot(sub[0, 0]),
        spotlight_assets.get("corn"),
        "Corn average NDVI",
        note="Generate NDVI cards to populate this panel.",
    )
    _image_panel(
        fig.add_subplot(sub[0, 1]),
        spotlight_assets.get("corn_peak_95"),
        "Corn 95th %ile peak NDVI",
        note="Generate NDVI cards to populate this panel.",
    )
    _image_panel(
        fig.add_subplot(sub[0, 2]),
        spotlight_assets.get("soybean"),
        "Soybean average NDVI",
        note="Generate NDVI cards to populate this panel.",
    )
    _image_panel(
        fig.add_subplot(sub[0, 3]),
        spotlight_assets.get("soybean_peak_95"),
        "Soybean 95th %ile peak NDVI",
        note="Generate NDVI cards to populate this panel.",
    )
    _image_panel(
        fig.add_subplot(sub[1, :]),
        spotlight_assets.get("cumulative"),
        "Cumulative NDVI by crop and year",
        note="Generate NDVI cards to populate this panel.",
    )

    plot_temperature_doy_overlay(
        fig.add_subplot(gs[3, 0:2]),
        weather,
        title="Farm temperature — all fields, by DOY",
    )
    plot_gdd_doy_overlay(
        fig.add_subplot(gs[3, 2:]),
        weather,
        title="Farm cumulative GDD — all fields, by DOY",
    )

    plot_precip_boxplot(
        fig.add_subplot(gs[4, 0:2]),
        weather,
        title="Farm monthly precipitation distribution",
    )
    _risk_matrix(fig.add_subplot(gs[4, 2:]), field_df)

    ax_table = fig.add_subplot(gs[5, :])
    ax_table.axis("off")
    table_cols = [
        c
        for c in [
            "field_id",
            "area_acres",
            "headlands_pct",
            "dominant_soil",
            "avg_om_pct",
            "avg_ph",
            "total_aws_inches",
            "drainage_class",
            "rotation_sequence",
            "crop_diversity",
        ]
        if c in field_df.columns
    ]
    if table_cols:
        tdf = field_df[table_cols].copy()
        for col in tdf.select_dtypes("float").columns:
            tdf[col] = tdf[col].round(2)
        tdf = tdf.fillna("—")
        t = ax_table.table(
            cellText=tdf.values, colLabels=tdf.columns, loc="center", cellLoc="left"
        )
        t.auto_set_font_size(False)
        t.set_fontsize(7.5)
        t.scale(1.0, 1.6)
        for col_idx in range(len(tdf.columns)):
            t[(0, col_idx)].set_facecolor("#e2e8f0")
            t[(0, col_idx)].set_text_props(weight="bold")
        for row_idx in range(1, len(tdf) + 1):
            bg = "#f8fafc" if row_idx % 2 == 0 else "#ffffff"
            for col_idx in range(len(tdf.columns)):
                t[(row_idx, col_idx)].set_facecolor(bg)
                t[(row_idx, col_idx)].set_edgecolor("#e2e8f0")
    ax_table.set_title(
        "Field comparison", fontsize=11, fontweight="bold", pad=10, loc="left"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(
        output_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)

    manifest.status = "complete"
    manifest.write(manifest_dir / f"{STEP_FARM_POSTER_RENDER}.json")
    print(f"✓ Farm poster saved → {output_path}")


if __name__ == "__main__":
    main()
