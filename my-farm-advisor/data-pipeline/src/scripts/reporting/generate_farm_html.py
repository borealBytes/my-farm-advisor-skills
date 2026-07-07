#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate self-contained single-page HTML farm intelligence report with embedded posters and soil profile cards."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import cast

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
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


_FARM_INTEL_SKILL = ensure_skill_path("farm-intelligence-reporting")
_HEADLANDS_SKILL = ensure_skill_path("headlands-ring")
_CDL_SKILL = ensure_skill_path("cdl-cropland")
_CROP_STRATEGY_SKILL = ensure_skill_path("crop-strategy")
_WEATHER_SKILL = ensure_skill_path("nasa-power-weather")

from cdl_reporting import plot_crop_mix_stacked_100, summarize_crop_history
from crop_strategy import generate_farm_recommendations, generate_field_recommendations
from headlands_ring import split_headlands_and_interior, summarize_headlands
from paths import (
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    farm_manifest_dir,
    farm_report_asset_path,
    farm_ssurgo_summary_path,
    farm_summary_path,
    farm_weather_path,
    field_dir,
    field_feature_path,
    field_report_path,
    field_summary_path,
    shared_cdl_preferred_full_composition_path,
    shared_geoadmin_dir,
)
from pipeline import (
    STEP_FARM_HTML_RENDER,
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
from weather_reporting import (
    plot_gdd_doy_overlay,
    plot_precip_boxplot,
    plot_temperature_doy_overlay,
    summarize_weather_variability,
)

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


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _img_to_b64(img_path: Path) -> str:
    """Convert image file to base64 string."""
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _weather_b64(field_weather: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(18, 4))
    fig.patch.set_facecolor("#fafaf9")
    plot_temperature_doy_overlay(axes[0], field_weather)
    plot_gdd_doy_overlay(axes[1], field_weather)
    plot_precip_boxplot(axes[2], field_weather)
    plt.tight_layout()
    return _fig_to_b64(fig)


def _cdl_b64(field_cdl: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#fafaf9")
    plot_crop_mix_stacked_100(ax, field_cdl)
    plt.tight_layout()
    return _fig_to_b64(fig)


def _farm_map_b64(fields: gpd.GeoDataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#fafaf9")
    fields_wgs84 = fields.to_crs("EPSG:4326")
    mean_longitude = float(
        (fields_wgs84.total_bounds[0] + fields_wgs84.total_bounds[2]) / 2
    )
    centroid_crs = "EPSG:32615" if mean_longitude < -90 else "EPSG:32616"
    centroids_projected = fields.to_crs(centroid_crs).geometry.centroid

    def _overlay_geoadmin(target_ax, use_webmercator: bool) -> None:
        geoadmin_root = shared_geoadmin_dir()
        states_path = geoadmin_root / "l1_states" / "states_usa.geojson"
        counties_path = geoadmin_root / "l2_counties" / "counties_usa.geojson"
        if not states_path.exists() or not counties_path.exists():
            return

        farm_shape = fields_wgs84.union_all()
        states = gpd.read_file(states_path)
        counties = gpd.read_file(counties_path)

        state_subset = states[states.intersects(farm_shape)]
        county_subset = counties[counties.intersects(farm_shape)]

        if use_webmercator:
            if not state_subset.empty:
                state_subset = state_subset.to_crs(epsg=3857)
            if not county_subset.empty:
                county_subset = county_subset.to_crs(epsg=3857)

        if not county_subset.empty:
            county_subset.boundary.plot(
                ax=target_ax,
                color="#f59e0b",
                linewidth=1.2,
                alpha=0.95,
                zorder=7,
            )
        if not state_subset.empty:
            state_subset.boundary.plot(
                ax=target_ax,
                color="#ef4444",
                linewidth=2.0,
                alpha=0.95,
                zorder=8,
            )

    use_basemap = False
    try:
        import contextily as ctx

        fields_web = fields.to_crs(epsg=3857)
        centroids = gpd.GeoSeries(centroids_projected, crs=centroid_crs).to_crs(
            epsg=3857
        )
        fields_web.plot(
            ax=ax, facecolor="#22c55e33", edgecolor="#166534", linewidth=1.6, zorder=4
        )
        sz = (
            fields["area_acres"].fillna(30).astype(float) * 5
            if "area_acres" in fields.columns
            else 60
        )
        ax.scatter(centroids.x, centroids.y, s=sz, color="#2563eb", alpha=0.8, zorder=5)
        for idx, r in fields.iterrows():
            c = centroids.iloc[idx]
            ax.annotate(
                str(r["field_id"])[-5:],
                (c.x, c.y),
                fontsize=7,
                ha="center",
                color="white",
                fontweight="bold",
                zorder=6,
            )
        xmin, ymin, xmax, ymax = fields_web.total_bounds
        pad_x = (xmax - xmin) * 0.15
        pad_y = (ymax - ymin) * 0.15
        ax.set_xlim(xmin - pad_x, xmax + pad_x)
        ax.set_ylim(ymin - pad_y, ymax + pad_y)
        _overlay_geoadmin(ax, use_webmercator=True)
        ctx.add_basemap(
            ax, source=ctx.providers.Esri.WorldImagery, alpha=0.55, attribution=False
        )
        use_basemap = True
    except Exception:
        field_crs = fields.crs or "EPSG:4326"
        centroids = gpd.GeoSeries(centroids_projected, crs=centroid_crs).to_crs(
            field_crs
        )
        fields.boundary.plot(ax=ax, color="#166534", linewidth=1.5)
        sz = (
            fields["area_acres"].fillna(30).astype(float) * 5
            if "area_acres" in fields.columns
            else 60
        )
        ax.scatter(
            centroids.x, centroids.y, s=sz, color="#2563eb", alpha=0.75, zorder=5
        )
        for idx, r in fields.iterrows():
            c = centroids.iloc[idx]
            ax.annotate(
                str(r["field_id"])[-5:],
                (c.x, c.y),
                fontsize=7,
                ha="center",
                color="white",
                fontweight="bold",
                zorder=6,
            )
        _overlay_geoadmin(ax, use_webmercator=False)
    ax.set_title("Farm field map", fontsize=12, fontweight="bold")
    if not use_basemap:
        ax.set_facecolor("#f1f5f9")
    ax.set_axis_off()
    plt.tight_layout()
    return _fig_to_b64(fig)


def _farm_crop_outlook_notes(cdl: pd.DataFrame) -> list[str]:
    notes: list[str] = []
    required = {"year", "crop_name", "pct"}
    if not required.issubset(set(cdl.columns)):
        return notes

    cdl_valid = cdl.dropna(subset=["year", "crop_name", "pct"]).copy()
    if cdl_valid.empty:
        return notes

    cdl_valid["year"] = cdl_valid["year"].astype(int)
    cdl_valid["pct"] = cdl_valid["pct"].astype(float)
    latest_year = int(cdl_valid["year"].max())
    latest = cdl_valid[cdl_valid["year"] == latest_year]
    if latest.empty:
        return notes

    crop_avg_pairs = sorted(
        (
            (str(crop_name), float(avg_pct))
            for crop_name, avg_pct in latest.groupby("crop_name")["pct"].mean().items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    if crop_avg_pairs:
        top_str = ", ".join(
            f"{crop_name} ({avg_pct:.0f}%)" for crop_name, avg_pct in crop_avg_pairs
        )
        notes.append(
            f"{latest_year} crop mix is led by {top_str}; align 2026 input planning around this distribution."
        )

    prior_year = latest_year - 1
    prior = cdl_valid[cdl_valid["year"] == prior_year]
    if not prior.empty:
        latest_by_crop = latest.groupby("crop_name")["pct"].mean()
        prior_by_crop = prior.groupby("crop_name")["pct"].mean()
        for crop_name in ("Corn", "Soybeans"):
            if crop_name in latest_by_crop.index and crop_name in prior_by_crop.index:
                delta = latest_by_crop[crop_name] - prior_by_crop[crop_name]
                if abs(delta) >= 5:
                    direction = "up" if delta > 0 else "down"
                    notes.append(
                        f"{crop_name} share is {direction} {abs(delta):.0f} points vs {prior_year}; tune hybrid/variety and protection plans accordingly."
                    )

    return notes[:3]


def _safe(v) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


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


def _canonical_field_root(field_slug: str | None) -> Path | None:
    if not field_slug:
        return None
    return field_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)


def _load_ndvi_cards(field_slug: str | None) -> dict[str, str]:
    field_root = _canonical_field_root(field_slug)
    if field_root is None:
        return {
            "corn": "",
            "corn_peak_95": "",
            "soybean": "",
            "soybean_peak_95": "",
            "current_season_cumulative": "",
        }
    feature_dir = field_root / "derived" / "features"
    cards: dict[str, str] = {}
    for key, filename in {
        "corn": "ndvi_corn.png",
        "corn_peak_95": "ndvi_corn_peak_95.png",
        "soybean": "ndvi_soybean.png",
        "soybean_peak_95": "ndvi_soybean_peak_95.png",
        "current_season_cumulative": "ndvi_current_season_cumulative.png",
    }.items():
        path = feature_dir / filename
        cards[key] = _img_to_b64(path) if path.exists() else ""
    return cards


def _cdl_csv_path() -> Path | None:
    if _CDL_PRIMARY.exists():
        return _CDL_PRIMARY
    if _CDL_FALLBACK.exists():
        return _CDL_FALLBACK
    return None


def _soil_card_specs() -> list[tuple[str, str, Path]]:
    return [
        ("properties", "Soil Properties", Path("summaries") / "soil_properties.png"),
        ("texture", "Texture RGB", Path("summaries") / "soil_texture.png"),
        ("overview", "Soil Overview Map", Path("summaries") / "soil_map.png"),
        (
            "component",
            "Soil Component Map",
            Path("features") / "soil_component_map.png",
        ),
        (
            "component_pct",
            "Component Share Map",
            Path("features") / "soil_component_pct_map.png",
        ),
        ("om", "Organic Matter Map", Path("features") / "soil_organic_matter_map.png"),
        ("ph", "Soil pH Map", Path("features") / "soil_ph_map.png"),
        ("awc", "Available Water Capacity Map", Path("features") / "soil_awc_map.png"),
        ("cec", "CEC Map", Path("features") / "soil_cec_map.png"),
        (
            "bulk_density",
            "Bulk Density Map",
            Path("features") / "soil_bulk_density_map.png",
        ),
        ("clay", "Clay Map", Path("features") / "soil_clay_map.png"),
        ("sand", "Sand Map", Path("features") / "soil_sand_map.png"),
        ("silt", "Silt Map", Path("features") / "soil_silt_map.png"),
    ]


def _load_soil_cards(field_slug: str | None) -> list[tuple[str, str, str]]:
    """Load unique soil summary and feature cards for a field."""
    if not field_slug:
        return []
    cards: list[tuple[str, str, str]] = []
    seen_paths: set[Path] = set()
    for key, label, relative_path in _soil_card_specs():
        if relative_path.parts[0] == "summaries":
            card_path = field_summary_path(
                _DEFAULT_GROWER,
                _DEFAULT_FARM,
                field_slug,
                relative_path.name,
            )
        else:
            card_path = field_feature_path(
                _DEFAULT_GROWER,
                _DEFAULT_FARM,
                field_slug,
                relative_path.name,
            )
        if card_path.exists() and card_path not in seen_paths:
            cards.append((key, label, _img_to_b64(card_path)))
            seen_paths.add(card_path)
    return cards


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


def _field_card(
    frow,
    df_row,
    field_weather,
    poster_b64: str,
    soil_cards: list[tuple[str, str, str]],
    ndvi_cards: dict,
    strategy: dict[str, object],
    idx: int,
) -> str:
    fid = str(frow["field_id"])
    acres = float(frow.get("area_acres", 0))
    row_dict = df_row.to_dict() if hasattr(df_row, "to_dict") else dict(df_row)
    implications = compute_management_implications(row_dict)
    bullets_html = "".join(f"<li>{b}</li>" for b in implications)
    strategy_recommendations = cast(list[str], strategy.get("recommendations", []))
    strategy_monitoring = cast(list[str], strategy.get("monitoring", []))
    strategy_actions = cast(
        list[str], strategy.get("action_plan", strategy_recommendations)
    )
    strategy_watchouts = cast(list[str], strategy.get("watchouts", strategy_monitoring))
    strategy_optimize = cast(list[str], strategy.get("optimize_for_success", []))
    monitoring_html = "".join(f"<li>{item}</li>" for item in strategy_monitoring)
    strategy_action_html = "".join(f"<li>{item}</li>" for item in strategy_actions)
    strategy_watchout_html = "".join(f"<li>{item}</li>" for item in strategy_watchouts)
    strategy_optimize_html = "".join(f"<li>{item}</li>" for item in strategy_optimize)

    soil_rows = ""
    for col, label in [
        ("avg_om_pct", "Avg OM (%)"),
        ("avg_ph", "Avg pH"),
        ("total_aws_inches", "Total AWS (in)"),
        ("avg_cec", "Avg CEC"),
        ("drainage_class", "Drainage class"),
        ("dominant_soil", "Dominant soil"),
        ("n_components", "Soil components"),
        ("n_horizons", "Horizons sampled"),
        ("headlands_pct", "Headlands (%)"),
        ("headlands_area_acres", "Headlands (ac)"),
    ]:
        soil_rows += (
            f"<tr><td><b>{label}</b></td><td>{_safe(row_dict.get(col))}</td></tr>"
        )

    wx_b64 = _weather_b64(field_weather) if not field_weather.empty else ""
    wx_img = (
        f'<img src="data:image/png;base64,{wx_b64}" style="width:100%" alt="Weather">'
        if wx_b64
        else "<p>No weather data</p>"
    )
    ndvi_blocks = []
    for key, label in [
        ("corn", "Corn average NDVI"),
        ("corn_peak_95", "Corn 95th %ile peak NDVI"),
        ("soybean", "Soybean average NDVI"),
        ("soybean_peak_95", "Soybean 95th %ile peak NDVI"),
        ("current_season_cumulative", "Cumulative NDVI by crop and year"),
    ]:
        payload = ndvi_cards.get(key, "")
        if payload:
            ndvi_blocks.append(
                f'<div><h4>{label}</h4><img src="data:image/png;base64,{payload}" style="width:100%" alt="{label}"></div>'
            )
        else:
            ndvi_blocks.append(
                f'<div><h4>{label}</h4><p class="note">{textwrap.fill("Cached NDVI asset unavailable. Refresh the satellite card build for this field.", width=48)}</p></div>'
            )
    ndvi_html = f'<div class="grid-ndvi">{"".join(ndvi_blocks)}</div>'

    rank_html = ""
    rank_cols = sorted([k for k in row_dict if k.endswith("_pct_rank")])
    if rank_cols:
        rank_html = "<table class='data-table'><tbody>"
        for k in rank_cols[:8]:
            base = k.replace("_pct_rank", "").replace("_", " ")
            v = row_dict.get(k)
            pct = (
                float(v)
                if v is not None and not (isinstance(v, float) and pd.isna(v))
                else 50.0
            )
            color = "#22c55e" if pct >= 66 else "#f59e0b" if pct >= 33 else "#ef4444"
            bar = f'<span style="display:inline-block;width:{pct:.0f}%;height:10px;background:{color};border-radius:3px"></span>'
            rank_html += (
                f"<tr><td><b>{base}</b></td><td>{bar} {pct:.0f}th pctile</td></tr>"
            )
        rank_html += "</tbody></table>"

    clean_dict = {
        k: _safe(v) for k, v in row_dict.items() if not k.endswith("_pct_rank")
    }

    field_anchor = f"field-{fid[-6:]}"

    # Build soil profile thumbnails
    soil_thumbs = []
    soil_modals = []

    for card_type, card_label, b64_data in soil_cards:
        if b64_data:
            modal_id = f"soil-modal-{idx}-{card_type}"
            soil_thumbs.append(f'''
                <a href="#{modal_id}" class="soil-thumb">
                    <img src="data:image/png;base64,{b64_data}" alt="{card_label}">
                    <span class="soil-label">{card_label}</span>
                </a>
            ''')
            soil_modals.append(f'''
<div id="{modal_id}" class="modal">
  <div class="modal-content">
    <a href="#{field_anchor}" class="modal-close">&times; Close</a>
    <h2>Field {fid[-8:]} — {card_label}</h2>
    <img src="data:image/png;base64,{b64_data}" style="width:100%;max-width:1200px;" alt="{card_label}">
  </div>
</div>
            ''')

    soil_section = ""
    if soil_thumbs:
        soil_section = f"""
  <details open><summary><strong>SSURGO soil cards and maps (click thumbnails to enlarge)</strong></summary>
    <div class="soil-gallery">
      {"".join(soil_thumbs)}
    </div>
  </details><hr>
        """

    return f"""
<section class="field-card" id="{field_anchor}">
  <h2>Field {fid[-8:]} <span class="badge">{acres:.1f} ac</span></h2>

  <div class="poster-preview">
    <h3>Field Poster</h3>
    <a href="#poster-modal-{idx}" class="poster-thumb">
      <img src="data:image/png;base64,{poster_b64}" style="max-width:300px;border:2px solid #2563eb;border-radius:8px;cursor:pointer;" alt="Field poster thumbnail">
      <p style="font-size:0.85rem;color:#2563eb;margin-top:0.5rem;">Click to view full poster</p>
    </a>
  </div>

  <div class="grid-2">
    <div class="strategy-panel">
      <h3>2026 crop strategy</h3>
      <p><strong>Focus:</strong> {_safe(strategy.get("crop_focus"))} &middot; <strong>Region:</strong> {_safe(strategy.get("region"))} &middot; <strong>Planting window:</strong> {_safe(strategy.get("planting_window"))}</p>
      <h4>Action plan</h4>
      <ul class="implications">{strategy_action_html}</ul>
    </div>
    <div class="strategy-panel">
      <h4>Watchouts</h4>
      <ul class="implications">{strategy_watchout_html if strategy_watchout_html else monitoring_html}</ul>
      <h4>Optimize for success</h4>
      <ul class="implications">{strategy_optimize_html if strategy_optimize_html else "<li>Use field rankings and NDVI trend consistency to sequence higher-intensity management where response potential is strongest.</li>"}</ul>
    </div>
  </div>

  {soil_section}

  <div class="grid-2">
    <div>
      <h3>Soil and operations summary</h3>
      <table class="data-table"><tbody>{soil_rows}</tbody></table>
    </div>
    <div>
      <h3>Management implications</h3>
      <ul class="implications">{bullets_html}</ul>
    </div>
  </div>
  <details open><summary><strong>Weather context (temperature, GDD, precipitation)</strong></summary>
    {wx_img}
  </details><hr>
  <details open><summary><strong>Crop rotation outlook</strong></summary>
    <p><strong>History:</strong> {_safe(row_dict.get("rotation_sequence"))}</p>
    <p><strong>Heuristic outlook:</strong> {_safe(row_dict.get("rotation_outlook"))}</p>
    <p><strong>Confidence:</strong> {_safe(row_dict.get("rotation_confidence"))} &middot; <strong>Window:</strong> {_safe(row_dict.get("history_start_year"))}-{_safe(row_dict.get("history_end_year"))}</p>
  </details><hr>
  <details><summary><strong>Farm-relative standing</strong></summary>
    {rank_html if rank_html else "<p>No ranking data available</p>"}
  </details><hr>
  <details open><summary><strong>Remote sensing NDVI</strong></summary>
    {ndvi_html}
  </details><hr>
  <details><summary><strong>Full field metrics</strong></summary>
    <pre class="raw-data">{json.dumps(clean_dict, indent=2)}</pre>
  </details>
</section>

<div id="poster-modal-{idx}" class="modal">
  <div class="modal-content">
    <a href="#{field_anchor}" class="modal-close">&times; Close</a>
    <h2>Field {fid[-8:]} Poster</h2>
    <img src="data:image/png;base64,{poster_b64}" style="width:100%;max-width:1200px;" alt="Full field poster">
  </div>
</div>
{"".join(soil_modals)}
"""


def main() -> None:
    print("=" * 60)
    print("Farm HTML report — self-contained with embedded posters")
    print("=" * 60)

    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
        grower_slug=_DEFAULT_GROWER,
        farm_slug=_DEFAULT_FARM,
    )
    manifest_dir = farm_manifest_dir(_DEFAULT_GROWER, _DEFAULT_FARM)
    output_path = farm_report_asset_path(_DEFAULT_GROWER, _DEFAULT_FARM, "html")
    field_slug_lookup = _field_slug_lookup()
    ndvi_input_paths = []
    field_poster_input_paths = []
    soil_input_paths = []
    for field_slug in field_slug_lookup.values():
        field_root = _canonical_field_root(field_slug)
        if field_root is None:
            continue
        poster_path = field_report_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "field_report.png"
        )
        if poster_path.exists():
            field_poster_input_paths.append(str(poster_path.relative_to(_REPO)))
        for filename in (
            "ndvi_corn.png",
            "ndvi_corn_peak_95.png",
            "ndvi_soybean.png",
            "ndvi_soybean_peak_95.png",
            "ndvi_current_season_cumulative.png",
        ):
            path = field_root / "derived" / "features" / filename
            if path.exists():
                ndvi_input_paths.append(str(path.relative_to(_REPO)))
        for _, _, relative_path in _soil_card_specs():
            path = field_root / "derived" / relative_path
            if path.exists():
                soil_input_paths.append(str(path.relative_to(_REPO)))

    prior = load_manifest(manifest_dir / f"{STEP_FARM_HTML_RENDER}.json")
    _html_cdl_path = _cdl_csv_path()
    manifest = build_step_manifest(
        step_name=STEP_FARM_HTML_RENDER,
        input_paths=[
            config.field_boundary_path,
            str(farm_ssurgo_summary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            str(farm_weather_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
            *([str(_html_cdl_path.relative_to(_REPO))] if _html_cdl_path is not None else []),
            str(farm_report_asset_path(_DEFAULT_GROWER, _DEFAULT_FARM, "png")),
            str(
                farm_summary_path(
                    _DEFAULT_GROWER, _DEFAULT_FARM, "soil_cards/farm_comparison.png"
                )
            ),
            *field_poster_input_paths,
            *ndvi_input_paths,
            *soil_input_paths,
        ],
        output_paths=[output_path],
        code_paths=_CODE_PATHS,
        config=config,
    )
    force = os.environ.get("AG_FORCE") == "1"
    if not force and not step_is_stale(manifest, prior):
        print("skip  HTML (current)")
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
    print("  Rendering farm map and crop portfolio charts...")
    farm_map_b64 = _farm_map_b64(fields)
    farm_crop_b64 = _cdl_b64(cdl)
    farm_poster_path = farm_report_asset_path(_DEFAULT_GROWER, _DEFAULT_FARM, "png")
    farm_poster_b64 = _img_to_b64(farm_poster_path) if farm_poster_path.exists() else ""
    farm_soil_compare_path = farm_summary_path(
        _DEFAULT_GROWER, _DEFAULT_FARM, "soil_cards/farm_comparison.png"
    )
    farm_soil_compare_b64 = (
        _img_to_b64(farm_soil_compare_path) if farm_soil_compare_path.exists() else ""
    )

    print("  Loading and embedding field posters...")
    field_cards = []
    for idx_num in range(len(fields)):
        frow = fields.iloc[idx_num]
        fid = frow["field_id"]
        print(f"    Loading poster for field {fid[-6:]}...")
        field_slug = field_slug_lookup.get(str(fid))
        poster_path = (
            field_report_path(
                _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "field_report.png"
            )
            if field_slug
            else _REPO / ".missing-field-report.png"
        )
        poster_b64 = _img_to_b64(poster_path) if poster_path.exists() else ""

        # Load soil cards
        soil_cards = _load_soil_cards(field_slug)

        fw = weather[weather["field_id"] == fid].copy()
        fw["date"] = pd.to_datetime(fw["date"])
        df_row_matches = field_df[field_df["field_id"] == fid]
        df_row = df_row_matches.iloc[0] if not df_row_matches.empty else pd.Series(frow)
        ndvi_cards = _load_ndvi_cards(field_slug_lookup.get(str(fid)))
        strategy = generate_field_recommendations(
            df_row.to_dict() if hasattr(df_row, "to_dict") else dict(df_row),
            centroid_lat=_field_centroid_latitude(fields, idx_num),
        )
        field_cards.append(
            _field_card(
                frow, df_row, fw, poster_b64, soil_cards, ndvi_cards, strategy, idx_num
            )
        )

    nav = " | ".join(
        f'<a href="#field-{str(r["field_id"])[-6:]}">{str(r["field_id"])[-6:]}</a>'
        for _, r in fields.iterrows()
    )

    outlook_notes = _farm_crop_outlook_notes(cdl)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_DEFAULT_FARM_NAME} Intelligence Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: Georgia, serif; margin: 0; background: #f8f7f1; color: #1e293b; line-height: 1.6; }}
    header {{ padding: 2rem 2.5rem; background: linear-gradient(135deg, #e0f2fe, #fef3c7); border-bottom: 2px solid #bfdbfe; }}
    header h1 {{ margin: 0 0 0.25rem; font-size: 1.75rem; color: #1e3a5f; }}
    header p {{ margin: 0; color: #475569; }}
     .farm-overview {{ padding: 1.5rem 2.5rem; background: white; border-bottom: 1px solid #e2e8f0; }}
     .farm-overview h2 {{ margin: 0 0 0.8rem; font-size: 1.3rem; color: #1e3a5f; }}
     .farm-overview img {{ width: 100%; border-radius: 8px; border: 1px solid #e2e8f0; }}
     .farm-hero {{ display: grid; grid-template-columns: 1.3fr 1fr; gap: 1rem; align-items: stretch; margin-bottom: 1rem; }}
     .farm-panel {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.85rem; }}
     .farm-assets {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }}
     .farm-assets h3 {{ margin-top: 0; }}
     .farm-poster-thumb {{ text-decoration: none; display: inline-block; }}
     .farm-poster-thumb:hover img {{ box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }}
     .farm-outlook {{ background: #f4f8ec; border: 1px solid #c7dc94; border-left: 6px solid #65a30d; border-radius: 10px; padding: 1rem 1.1rem; }}
     .farm-outlook h3 {{ margin: 0 0 0.4rem; color: #355e3b; font-size: 1.08rem; }}
     .farm-outlook .lead {{ margin: 0.2rem 0 0.75rem; color: #355e3b; font-weight: 700; font-size: 0.95rem; }}
     .spotlight-section {{ padding: 1.5rem 2.5rem; background: white; border-bottom: 1px solid #e2e8f0; }}
     .spotlight-section h2 {{ margin: 0 0 1rem; font-size: 1.3rem; color: #1e3a5f; }}
    nav.field-nav {{ padding: 0.75rem 2.5rem; background: #1e3a5f; color: white; font-size: 0.85rem; }}
    nav.field-nav a {{ color: #93c5fd; text-decoration: none; margin: 0 0.25rem; }}
    nav.field-nav a:hover {{ color: white; }}
    main {{ padding: 1.5rem 2.5rem; }}
    .field-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 4px 16px rgba(15,23,42,0.07); }}
    .field-card h2 {{ margin: 0 0 1rem; font-size: 1.3rem; color: #1e3a5f; border-bottom: 2px solid #bfdbfe; padding-bottom: 0.5rem; }}
    .field-card h3 {{ font-size: 1rem; margin: 0.75rem 0 0.4rem; color: #374151; }}
    .badge {{ background: #dbeafe; color: #1e40af; font-size: 0.8rem; padding: 0.15rem 0.5rem; border-radius: 999px; font-family: sans-serif; font-weight: 600; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1rem; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    .data-table td {{ padding: 0.28rem 0.5rem; border-bottom: 1px solid #f1f5f9; }}
    .data-table tr:last-child td {{ border: none; }}
    .implications {{ margin: 0; padding-left: 1.2rem; font-size: 0.88rem; }}
    .implications li {{ margin-bottom: 0.35rem; }}
    details {{ margin: 0.75rem 0; }}
    details summary {{ cursor: pointer; font-weight: 600; padding: 0.5rem 0; color: #374151; font-family: sans-serif; font-size: 0.95rem; }}
    details summary:hover {{ color: #2563eb; }}
    details img {{ margin-top: 0.5rem; }}
    .note {{ color: #6b7280; font-style: italic; font-size: 0.88rem; }}
    .raw-data {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem; font-size: 0.72rem; overflow-x: auto; max-height: 280px; overflow-y: scroll; }}
    hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 0; }}
    footer {{ padding: 1.5rem 2.5rem; text-align: center; font-size: 0.8rem; color: #94a3b8; font-family: sans-serif; border-top: 1px solid #e2e8f0; }}

    .poster-preview {{ margin: 1rem 0; padding: 1rem; background: #f8fafc; border-radius: 8px; text-align: center; }}
    .poster-thumb {{ text-decoration: none; display: inline-block; }}
    .poster-thumb:hover img {{ box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }}

    /* Soil profile gallery styles */
    .soil-gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin: 1rem 0; padding: 1rem; background: #fafaf9; border-radius: 8px; }}
    .soil-thumb {{ text-decoration: none; display: flex; flex-direction: column; align-items: center; background: white; padding: 0.75rem; border-radius: 8px; border: 2px solid #e5e7eb; transition: all 0.2s; }}
    .soil-thumb:hover {{ border-color: #8b5cf6; box-shadow: 0 4px 12px rgba(139, 92, 246, 0.2); }}
    .soil-thumb img {{ width: 100%; max-width: 120px; height: auto; border-radius: 4px; margin-bottom: 0.5rem; }}
    .soil-label {{ font-size: 0.8rem; color: #4b5563; font-weight: 600; font-family: sans-serif; }}
    .soil-thumb:hover .soil-label {{ color: #8b5cf6; }}
     .strategy-panel {{ background: #f4f8ec; border: 1px solid #d9e7bf; border-radius: 10px; padding: 1rem 1.1rem; }}
     .strategy-panel h3 {{ color: #355e3b; }}

    /* Modal styles with 2026 best practices */
    .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); overflow: auto; backdrop-filter: blur(4px); }}
    .modal:target {{ display: block; }}
    .modal-content {{ background: white; margin: 2% auto; padding: 2rem; width: 95%; max-width: 1400px; border-radius: 12px; position: relative; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); animation: modalFadeIn 0.3s ease-out; }}
    @keyframes modalFadeIn {{ from {{ opacity: 0; transform: translateY(-20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .modal-close {{ position: absolute; top: 1rem; right: 1rem; font-size: 1.5rem; color: #64748b; text-decoration: none; background: #f1f5f9; padding: 0.5rem 1rem; border-radius: 6px; font-family: sans-serif; font-weight: 600; transition: all 0.2s; }}
    .modal-close:hover {{ color: #1e293b; background: #e2e8f0; }}

     .grid-ndvi {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }}
     .grid-ndvi h4 {{ margin: 0 0 0.4rem; font-size: 0.9rem; color: #475569; }}
     .grid-ndvi img {{ border: 1px solid #e2e8f0; border-radius: 8px; background: white; }}
     .spotlight-section .grid-ndvi > div:last-child {{ grid-column: 1 / -1; }}
      @media (max-width: 980px) {{ .farm-hero, .farm-assets {{ grid-template-columns: 1fr; }} }}
      @media (max-width: 768px) {{ .grid-2, .grid-ndvi {{ grid-template-columns: 1fr; }} .soil-gallery {{ grid-template-columns: repeat(2, 1fr); }} }}
  </style>
</head>
<body>
  <header>
    <h1>{_DEFAULT_FARM_NAME} Intelligence Report</h1>
    <p>{n_fields} fields &middot; {total_ac:.0f} total acres &middot; Data years 2021–2025 &middot; Soil, weather, crop history, headlands</p>
  </header>
  <div class="farm-overview" id="farm-overview">
    <h2>Farm overview</h2>
    <div class="farm-hero">
      <div class="farm-panel">
        <h3>Farm field map</h3>
      <img src="data:image/png;base64,{farm_map_b64}" alt="Farm field map">
      </div>
      <div class="farm-outlook">
        <h3>{_safe(farm_strategy.get("title"))}</h3>
        <p class="lead">Primary 2026 outlook</p>
        <ul class="implications">{"".join(f"<li>{bullet}</li>" for bullet in cast(list[str], farm_strategy.get("bullets", [])))}</ul>
        {f'<hr><ul class="implications">{"".join(f"<li>{note}</li>" for note in outlook_notes)}</ul>' if outlook_notes else ""}
      </div>
    </div>

    <div class="farm-assets">
      <div class="farm-panel">
        <h3>Farm crop portfolio</h3>
        <img src="data:image/png;base64,{farm_crop_b64}" alt="Farm CDL crop composition">
      </div>
      <div class="farm-panel">
        <h3>Farm summary poster</h3>
        {f'<a href="#farm-poster-modal" class="farm-poster-thumb"><img src="data:image/png;base64,{farm_poster_b64}" alt="Farm summary poster thumbnail" style="max-width:300px;cursor:pointer;"><p style="font-size:0.85rem;color:#2563eb;margin-top:0.5rem;">Click to view full poster</p></a>' if farm_poster_b64 else "<p>Farm summary poster unavailable</p>"}
      </div>
      <div class="farm-panel">
        <h3>Farm soil comparison</h3>
        {f'<img src="data:image/png;base64,{farm_soil_compare_b64}" alt="Farm soil comparison">' if farm_soil_compare_b64 else "<p>Farm soil comparison unavailable</p>"}
      </div>
    </div>
  </div>
  <nav class="field-nav">Jump to field: {nav}</nav>
  <main>{"".join(field_cards)}</main>

  <div id="farm-poster-modal" class="modal">
    <div class="modal-content">
      <a href="#farm-overview" class="modal-close">&times; Close</a>
      <h2>{_DEFAULT_FARM_NAME} - Farm Poster</h2>
      {f'<img src="data:image/png;base64,{farm_poster_b64}" style="width:100%;max-width:1200px;" alt="Full farm poster">' if farm_poster_b64 else "<p>Farm summary poster unavailable</p>"}
    </div>
  </div>

  <footer>Generated by farm-intelligence-reporting &mdash; self-contained, no external dependencies required at runtime.</footer>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    manifest.status = "complete"
    manifest.write(manifest_dir / f"{STEP_FARM_HTML_RENDER}.json")
    print(f"✓ HTML report saved → {output_path}")
    print(f"  Size: {output_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
