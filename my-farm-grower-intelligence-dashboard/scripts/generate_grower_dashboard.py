#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
"""Generate an interactive grower-level intelligence dashboard.

Output: a self-contained HTML file with 5 interactive Plotly panels.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Bootstrap runtime paths ──────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base

# Import shared helpers *after* path bootstrap
from lib.paths import (  # noqa: E402
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    farm_derived_dir,
    farm_soil_sample_path,
    farm_table_path,
    farm_weather_path,
    field_boundary_path,
    field_satellite_dir,
)

# ── Third-party imports (may require plotly install) ─────────────────────
try:
    import geopandas as gpd
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import rasterio
    from rasterstats import zonal_stats
except ImportError as exc:
    print(
        f"Missing dependency: {exc.name}. Install with:\n"
        f'  {_RUNTIME_PATHS.runtime_scripts.parent / ".venv/bin/pip"} install plotly rasterstats'
    )
    raise

# ── Named constants ─────────────────────────────────────────────────────
SHI_WEIGHT_OM = 0.30
SHI_WEIGHT_CEC = 0.30
SHI_WEIGHT_PH = 0.20
SHI_WEIGHT_EROSION = 0.20

GROWING_SEASON_MONTHS = list(range(4, 11))  # Apr–Oct
HOT_DAY_THRESHOLD_C = 32.0
NDVI_ZONAL_NODATA = -9999

# ── Data loaders ─────────────────────────────────────────────────────────


def load_field_boundaries(grower: str, farm: str) -> gpd.GeoDataFrame:
    path = farm_boundary_path(grower, farm)
    gdf = gpd.read_file(path)
    if "area_acres" not in gdf.columns:
        # Compute area in acres if missing (EPSG:4326 → Albers approx)
        gdf = gdf.to_crs(epsg=5070)
        gdf["area_acres"] = gdf.geometry.area * 0.000247105
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def load_soil_summary(grower: str, farm: str) -> pd.DataFrame:
    path = farm_soil_sample_path(grower, farm)
    raw = pd.read_csv(path)
    # Farm-level CSV has one row per horizon; aggregate to field level
    agg = raw.groupby("field_id").agg(
        avg_om_pct=("om_r", "mean"),
        avg_ph=("ph1to1h2o_r", "mean"),
        avg_cec=("cec7_r", "mean"),
        dominant_soil=("compname", lambda s: s.mode()[0] if not s.mode().empty else s.iloc[0]),
        drainage_class=("drainagecl", lambda s: s.mode()[0] if not s.mode().empty else s.iloc[0]),
    ).reset_index()
    # Erosion risk not present in raw horizon CSV; default to moderate
    agg["erosion_risk"] = "moderate"
    return agg


def load_weather(grower: str, farm: str) -> pd.DataFrame:
    path = farm_weather_path(grower, farm)
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    return df


def load_cdl(grower: str, farm: str) -> pd.DataFrame:
    path = farm_cdl_preferred_full_composition_path(grower, farm)
    df = pd.read_csv(path)
    # Keep dominant crop per field-year (highest pct)
    dominant = (
        df.sort_values("pct", ascending=False)
        .groupby(["field_id", "year"])
        .first()
        .reset_index()
    )
    return dominant


# ── NDVI zonal stats with cache ─────────────────────────────────────────


def _ndvi_cache_path(grower: str, farm: str, year: int) -> Path:
    return farm_table_path(grower, farm, f"ndvi_field_summary_{year}.csv")


def _parse_date_from_tif(tif_path: Path) -> pd.Timestamp | None:
    """Extract YYYYMMDD from sentinel_YYYYMMDD_ndvi.tif"""
    stem = tif_path.stem  # sentinel_20250703_ndvi
    parts = stem.split("_")
    if len(parts) >= 2:
        date_str = parts[1]
        try:
            return pd.to_datetime(date_str, format="%Y%m%d")
        except ValueError:
            pass
    return None


def compute_ndvi_summary(
    grower: str,
    farm: str,
    year: int,
    field_slugs: list[str],
    force_refresh: bool = False,
) -> pd.DataFrame:
    cache_path = _ndvi_cache_path(grower, farm, year)

    if not force_refresh and cache_path.exists():
        print(f"[NDVI] Loading cached summary from {cache_path}")
        return pd.read_csv(cache_path, parse_dates=["peak_date"])

    print(f"[NDVI] Computing zonal stats for {len(field_slugs)} fields, year {year} ...")
    records: list[dict[str, Any]] = []
    any_fallback_used = False

    for field_slug in field_slugs:
        boundary_path = field_boundary_path(grower, farm, field_slug)
        if not boundary_path.exists():
            print(f"  [WARN] Boundary missing for {field_slug}, skipping.")
            continue

        boundary_gdf = gpd.read_file(boundary_path)
        if boundary_gdf.empty:
            continue

        sentinel_base = field_satellite_dir(grower, farm, field_slug) / "sentinel"
        sentinel_dir = sentinel_base / str(year)

        # If target year missing, check manifest for fallback years
        use_year = year
        if not sentinel_dir.exists() or not sorted(sentinel_dir.glob("sentinel_*/sentinel_*_ndvi.tif")):
            manifest_path = sentinel_base / "manifest.json"
            fallback_year = None
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    available_years = [int(y["year"]) for y in manifest.get("years", [])]
                    if available_years:
                        fallback_year = max(available_years)
                except Exception:
                    pass
            if fallback_year is not None:
                sentinel_dir = sentinel_base / str(fallback_year)
                use_year = fallback_year
                any_fallback_used = True
                print(f"  [INFO] Target year {year} missing for {field_slug}; falling back to {fallback_year}.")
            else:
                print(f"  [WARN] No sentinel data for {field_slug} year {year} (no fallback), skipping.")
                continue

        ndvi_tifs = sorted(sentinel_dir.glob("sentinel_*/sentinel_*_ndvi.tif"))
        if not ndvi_tifs:
            print(f"  [WARN] No NDVI tifs for {field_slug} year {use_year}, skipping.")
            continue

        scene_means: list[float] = []
        scene_dates: list[pd.Timestamp] = []

        for tif in ndvi_tifs:
            parsed_date = _parse_date_from_tif(tif)
            try:
                stats = zonal_stats(
                    boundary_gdf,
                    str(tif),
                    stats=["mean"],
                    nodata=NDVI_ZONAL_NODATA,
                    geojson_out=False,
                )
                if not stats:
                    continue
                mean_val = stats[0]["mean"]
                if mean_val is not None and not np.isnan(mean_val):
                    scene_means.append(float(mean_val))
                    if parsed_date is not None:
                        scene_dates.append(parsed_date)
            except Exception as exc:
                print(f"  [WARN] Zonal stats failed for {tif.name}: {exc}")
                continue

        if not scene_means:
            print(f"  [WARN] No valid NDVI scenes for {field_slug}, skipping.")
            continue

        peak_idx = int(np.argmax(scene_means))
        records.append(
            {
                "field_id": field_slug,
                "mean_ndvi": round(float(np.mean(scene_means)), 4),
                "peak_ndvi": round(float(scene_means[peak_idx]), 4),
                "peak_date": scene_dates[peak_idx] if peak_idx < len(scene_dates) else pd.NaT,
                "scene_count": len(scene_means),
            }
        )

    ndvi_df = pd.DataFrame(records)
    if ndvi_df.empty:
        print("[NDVI] No valid NDVI data found for any field.")
        return ndvi_df

    # Merge with dominant crop for target year
    cdl_df = load_cdl(grower, farm)
    year_crops = cdl_df[cdl_df["year"] == year][["field_id", "crop_name"]]
    ndvi_df = ndvi_df.merge(year_crops, on="field_id", how="left")
    ndvi_df["crop_name"] = ndvi_df["crop_name"].fillna("Unknown")

    # Write cache only when all fields used the target year (avoid misleading caches)
    if not any_fallback_used:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        ndvi_df.to_csv(cache_path, index=False)
        print(f"[NDVI] Cached summary written to {cache_path}")
    else:
        print("[NDVI] Fallback data used; skipping cache write to avoid misleading target-year cache.")
    return ndvi_df


# ── Chart builders ─────────────────────────────────────────────────────


def build_rotation_heatmap(cdl_df: pd.DataFrame) -> go.Figure:
    """Panel 1: Crop rotation stability matrix."""
    # Pivot to wide format: field_id × year → crop_name
    pivot = cdl_df.pivot(index="field_id", columns="year", values="crop_name")
    pivot = pivot.fillna("Unknown")

    # Build heatmap
    years = list(pivot.columns)
    fields = list(pivot.index)
    z = []
    unique_crops = sorted(set(pivot.values.flatten()))
    crop_to_num = {crop: i for i, crop in enumerate(unique_crops)}
    for field in fields:
        row = [crop_to_num.get(pivot.loc[field, y], -1) for y in years]
        z.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=years,
            y=fields,
            colorscale="Viridis",
            showscale=False,
            text=pivot.values,
            hovertemplate="Field: %{y}<br>Year: %{x}<br>Crop: %{text}<extra></extra>",
        )
    )

    # Add a discrete legend for each crop using invisible scatter traces
    crop_color_map = {
        "Corn": "#F1C40F",
        "Soybeans": "#2ECC71",
        "Forest": "#27AE60",
        "Grass/Pasture": "#8E44AD",
        "Winter Wheat": "#E67E22",
        "Unknown": "#95A5A6",
    }
    for crop in unique_crops:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=10, color=crop_color_map.get(crop, "#95A5A6")),
                name=crop,
                showlegend=True,
            )
        )

    fig.update_layout(
        title="Crop Rotation Stability (2021–2025)",
        xaxis_title="Year",
        yaxis_title="Field ID",
        height=max(400, 30 * len(fields)),
    )
    return fig


def build_ndvi_boxplot(ndvi_df: pd.DataFrame) -> go.Figure:
    """Panel 2: Peak-season NDVI distribution by crop type."""
    # Filter to corn/soybean for clarity
    filtered = ndvi_df[ndvi_df["crop_name"].isin(["Corn", "Soybeans"])].copy()
    if filtered.empty:
        fig = go.Figure()
        fig.add_annotation(text="No Corn/Soybean NDVI data available", showarrow=False)
        return fig

    fig = px.box(
        filtered,
        x="crop_name",
        y="peak_ndvi",
        color="crop_name",
        points="all",
        hover_data=["field_id", "mean_ndvi", "scene_count"],
        title="Peak-Season NDVI by Crop Type",
        labels={"crop_name": "Crop", "peak_ndvi": "Peak NDVI"},
    )
    fig.update_layout(showlegend=False, height=450)
    fig.update_yaxes(range=[0, 1], title_text="Peak NDVI (0–1 scale)")
    return fig


def build_field_choropleth(
    fields_gdf: gpd.GeoDataFrame,
    soil_df: pd.DataFrame,
    cdl_df: pd.DataFrame,
    year: int,
) -> go.Figure:
    """Panel 3: Geospatial field choropleth (crop + soil overlay)."""
    # Merge crop label for target year
    year_crops = cdl_df[cdl_df["year"] == year][["field_id", "crop_name"]].copy()
    merged = fields_gdf.drop(columns=["crop_name"], errors="ignore").merge(year_crops, on="field_id", how="left")
    merged["crop_name"] = merged["crop_name"].fillna("Unknown")

    # Merge soil summary
    soil_cols = ["field_id", "avg_om_pct", "avg_ph", "dominant_soil", "drainage_class", "erosion_risk"]
    soil_sub = soil_df[[c for c in soil_cols if c in soil_df.columns]].copy()
    merged = merged.merge(soil_sub, on="field_id", how="left")

    # Build one trace per crop so each geojson only contains matching features
    color_map = {
        "Corn": "#F1C40F",
        "Soybeans": "#2ECC71",
        "Forest": "#27AE60",
        "Grass/Pasture": "#8E44AD",
        "Unknown": "#95A5A6",
    }

    fig = go.Figure()
    for crop, group in merged.groupby("crop_name", sort=False):
        geojson = group.__geo_interface__
        fig.add_trace(
            go.Choroplethmap(
                geojson=geojson,
                locations=group["field_id"].tolist(),
                z=[1] * len(group),
                colorscale=[[0, color_map.get(crop, "#95A5A6")], [1, color_map.get(crop, "#95A5A6")]],
                showscale=False,
                name=crop,
                featureidkey="properties.field_id",
                marker=dict(opacity=0.7, line=dict(width=1, color="#333")),
                customdata=group[["area_acres", "avg_om_pct", "dominant_soil", "drainage_class", "erosion_risk"]].values.tolist(),
                hovertemplate=(
                    "<b>%{location}</b><br>"
                    "Crop: " + crop + "<br>"
                    "Area: %{customdata[0]:.1f} ac<br>"
                    "OM: %{customdata[1]:.1f}%<br>"
                    "Soil: %{customdata[2]}<br>"
                    "Drainage: %{customdata[3]}<br>"
                    "Erosion: %{customdata[4]}<extra></extra>"
                ),
            )
        )

    # Compute map viewport from actual bounding box so all fields are visible
    bounds = merged.total_bounds  # (minx, miny, maxx, maxy)
    center_lon = (bounds[0] + bounds[2]) / 2.0
    center_lat = (bounds[1] + bounds[3]) / 2.0
    lon_range = bounds[2] - bounds[0]
    lat_range = bounds[3] - bounds[1]
    max_range = max(lon_range, lat_range)
    zoom = 10  # default fallback
    if max_range > 0:
        zoom = int(math.log2(360.0 / max_range)) + 1
        zoom = max(min(zoom, 14), 6)

    fig.update_layout(
        title=f"Field Map — Crop & Soil Overlay ({year})",
        height=550,
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        map=dict(
            style="carto-positron",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=zoom,
        ),
    )
    return fig


def build_weather_stress_bars(weather_df: pd.DataFrame, year: int) -> go.Figure:
    """Panel 4: Growing-season weather stress by field."""
    # Target year growing season
    target = weather_df[
        (weather_df["year"] == year) & (weather_df["month"].isin(GROWING_SEASON_MONTHS))
    ].copy()

    # 5-year average reference
    full = weather_df[weather_df["month"].isin(GROWING_SEASON_MONTHS)].copy()

    if target.empty:
        fig = go.Figure()
        fig.add_annotation(text="No weather data for target year", showarrow=False)
        return fig

    # Aggregations
    target_agg = target.groupby("field_id").agg(
        total_precip=("PRECTOTCORR", "sum"),
        hot_days=("T2M_MAX", lambda s: (s > HOT_DAY_THRESHOLD_C).sum()),
    ).reset_index()

    ref_agg = full.groupby(["field_id", "year"]).agg(
        precip=("PRECTOTCORR", "sum"),
        hot=("T2M_MAX", lambda s: (s > HOT_DAY_THRESHOLD_C).sum()),
    ).groupby("field_id").mean().reset_index()
    ref_agg = ref_agg.rename(columns={"precip": "avg_precip", "hot": "avg_hot_days"})

    merged = target_agg.merge(ref_agg, on="field_id", how="left")
    merged = merged.sort_values("total_precip", ascending=True)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Total Precipitation (mm)", f"Hot Days (Tmax > {HOT_DAY_THRESHOLD_C}°C)"),
        shared_yaxes=True,
    )

    fig.add_trace(
        go.Bar(
            x=merged["total_precip"],
            y=merged["field_id"],
            orientation="h",
            name=f"{year} Precip",
            marker_color="#3498db",
            hovertemplate="%{y}<br>Precip: %{x:.1f} mm<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=merged["avg_precip"],
            y=merged["field_id"],
            mode="markers",
            name="5-yr Avg",
            marker=dict(color="#e74c3c", symbol="line-ns", size=12, line=dict(width=2)),
            hovertemplate="%{y}<br>5-yr Avg: %{x:.1f} mm<extra></extra>",
        ),
        row=1, col=1,
    )

    fig.add_trace(
        go.Bar(
            x=merged["hot_days"],
            y=merged["field_id"],
            orientation="h",
            name=f"{year} Hot Days",
            marker_color="#e67e22",
            hovertemplate="%{y}<br>Hot Days: %{x}<extra></extra>",
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=merged["avg_hot_days"],
            y=merged["field_id"],
            mode="markers",
            name="5-yr Avg",
            marker=dict(color="#e74c3c", symbol="line-ns", size=12, line=dict(width=2)),
            showlegend=False,
            hovertemplate="%{y}<br>5-yr Avg: %{x:.1f}<extra></extra>",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title_text=f"Growing-Season Weather Stress ({year} vs 5-Year Avg)",
        height=max(400, 25 * len(merged)),
        barmode="overlay",
    )
    fig.update_xaxes(title_text="mm", row=1, col=1)
    fig.update_xaxes(title_text="Days", row=1, col=2)
    return fig


def _compute_soil_health_index(row: pd.Series) -> float:
    """Compute composite Soil Health Index (0–1 scale)."""
    om_score = min(float(row.get("avg_om_pct", 0)) / 5.0, 1.0)
    cec_score = min(float(row.get("avg_cec", 0)) / 30.0, 1.0)
    ph = float(row.get("avg_ph", 7.0))
    ph_score = max(0.0, 1.0 - abs(ph - 6.5) / 1.5)
    erosion = str(row.get("erosion_risk", "low")).lower()
    erosion_penalty = {"low": 0.0, "moderate": -0.2, "severe": -0.4}.get(erosion, 0.0)
    shi = (
        SHI_WEIGHT_OM * om_score
        + SHI_WEIGHT_CEC * cec_score
        + SHI_WEIGHT_PH * ph_score
        + SHI_WEIGHT_EROSION * (1.0 + erosion_penalty)
    )
    return round(max(0.0, min(1.0, shi)), 3)


def build_soil_scorecard(soil_df: pd.DataFrame) -> go.Figure:
    """Panel 5: Soil Health Scorecard."""
    df = soil_df.copy()
    df["shi"] = df.apply(_compute_soil_health_index, axis=1)
    df = df.sort_values("shi", ascending=True)

    # Color by drainage class
    color_map = {
        "Well drained": "#2ecc71",
        "Moderately well drained": "#f1c40f",
        "Somewhat poorly drained": "#e67e22",
        "Poorly drained": "#e74c3c",
        "Very poorly drained": "#8e44ad",
    }
    df["color"] = df["drainage_class"].map(color_map).fillna("#95a5a6")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["shi"],
            y=df["field_id"],
            mode="markers",
            marker=dict(size=12, color=df["color"]),
            text=df["drainage_class"],
            hovertemplate="<b>%{y}</b><br>SHI: %{x}<br>Drainage: %{text}<extra></extra>",
            name="Fields",
        )
    )

    # Add grower average line
    avg_shi = df["shi"].mean()
    fig.add_vline(
        x=avg_shi,
        line_dash="dash",
        line_color="#2c3e50",
        annotation_text=f"Grower Avg: {avg_shi:.2f}",
        annotation_position="top",
    )

    fig.update_layout(
        title="Soil Health Scorecard (Composite Index)",
        xaxis_title="Soil Health Index (0 = poor, 1 = excellent)",
        yaxis_title="Field ID",
        height=max(400, 30 * len(df)),
        showlegend=False,
    )
    fig.update_xaxes(range=[0, 1])
    return fig


# ── Summary table builder ────────────────────────────────────────────────


def build_summary_table(
    fields_gdf: gpd.GeoDataFrame,
    soil_df: pd.DataFrame,
    cdl_df: pd.DataFrame,
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    """Build a master summary DataFrame for the raw-data appendix."""
    # Start with field list + area
    summary = fields_gdf[["field_id", "area_acres"]].copy()

    # Merge latest crop
    latest_crop = cdl_df[cdl_df["year"] == year][["field_id", "crop_name", "pct"]].copy()
    latest_crop = latest_crop.rename(columns={"crop_name": f"crop_{year}", "pct": f"crop_pct_{year}"})
    summary = summary.merge(latest_crop, on="field_id", how="left")

    # Merge soil
    soil_sub = soil_df[
        ["field_id", "avg_om_pct", "avg_ph", "avg_cec", "dominant_soil", "drainage_class", "erosion_risk"]
    ].copy()
    summary = summary.merge(soil_sub, on="field_id", how="left")
    summary["shi"] = summary.apply(_compute_soil_health_index, axis=1)

    # Merge NDVI
    if not ndvi_df.empty:
        ndvi_sub = ndvi_df[["field_id", "mean_ndvi", "peak_ndvi", "scene_count"]].copy()
        summary = summary.merge(ndvi_sub, on="field_id", how="left")

    # Merge weather (target year growing season)
    w = weather_df[
        (weather_df["year"] == year) & (weather_df["month"].isin(GROWING_SEASON_MONTHS))
    ]
    if not w.empty:
        wagg = w.groupby("field_id").agg(
            total_precip=("PRECTOTCORR", "sum"),
            hot_days=("T2M_MAX", lambda s: (s > HOT_DAY_THRESHOLD_C).sum()),
            avg_temp=("T2M", "mean"),
        ).reset_index()
        summary = summary.merge(wagg, on="field_id", how="left")

    summary = summary.fillna("N/A")
    return summary


# ── HTML assembler ───────────────────────────────────────────────────────


def assemble_dashboard_html(
    grower: str,
    farm: str,
    year: int,
    figures: dict[str, go.Figure],
    summary_df: pd.DataFrame,
    output_path: Path,
) -> None:
    chart_html: dict[str, str] = {}
    for name, fig in figures.items():
        chart_html[name] = fig.to_html(full_html=False, include_plotlyjs=False)

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{grower} — Field Intelligence Dashboard ({year})</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
  .header {{ background: #f0f4f8; padding: 20px; border-radius: 8px; margin-bottom: 30px; border-left: 5px solid #3498db; }}
  .header h1 {{ margin: 0 0 8px 0; color: #2c3e50; }}
  .header p {{ margin: 0; color: #555; }}
  .chart-container {{ margin-bottom: 40px; border: 1px solid #e1e4e8; border-radius: 8px; padding: 15px; background: #fff; }}
  .chart-container h2 {{ margin-top: 0; color: #2980b9; font-size: 1.3em; border-bottom: 2px solid #3498db; padding-bottom: 6px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 15px; font-size: 0.9em; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #3498db; color: white; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.85em; color: #888; text-align: center; }}
</style>
</head>
<body>
  <div class="header">
    <h1>{grower} — Row Crop Intelligence Dashboard</h1>
    <p>Farm: <strong>{farm}</strong> &nbsp;|&nbsp; Season: <strong>{year}</strong> &nbsp;|&nbsp; Fields: <strong>{len(summary_df)}</strong> &nbsp;|&nbsp; Total Area: <strong>{summary_df["area_acres"].apply(lambda x: float(x) if x != "N/A" else 0).sum():.1f}</strong> acres</p>
  </div>

  <div class="chart-container">
    <h2>1. Crop Rotation Stability Matrix</h2>
    {chart_html.get("rotation", "")}
  </div>

  <div class="chart-container">
    <h2>2. Peak-Season NDVI by Crop Type</h2>
    {chart_html.get("ndvi", "")}
  </div>

  <div class="chart-container">
    <h2>3. Field Map — Crop &amp; Soil Overlay</h2>
    {chart_html.get("choropleth", "")}
  </div>

  <div class="chart-container">
    <h2>4. Growing-Season Weather Stress ({year} vs 5-Year Average)</h2>
    {chart_html.get("weather", "")}
  </div>

  <div class="chart-container">
    <h2>5. Soil Health Scorecard</h2>
    {chart_html.get("soil", "")}
  </div>

  <div class="chart-container">
    <h2>Raw Data Summary</h2>
    {summary_df.to_html(index=False, classes="summary-table", border=0)}
  </div>

  <div class="footer">
    Generated by my-farm-grower-intelligence-dashboard &nbsp;|&nbsp; {pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
  </div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template, encoding="utf-8")
    print(f"[Dashboard] HTML written to: {output_path}")


# ── Orchestrator ────────────────────────────────────────────────────────


def run_dashboard_pipeline(
    grower: str,
    farm: str,
    year: int,
    output_dir: Path | None = None,
    force_refresh_ndvi: bool = False,
    fields_filter: list[str] | None = None,
) -> Path:
    # Resolve output
    if output_dir is None:
        output_dir = _RUNTIME_BASE / "growers" / grower / "derived" / "dashboards"
    output_path = output_dir / "grower_intelligence_dashboard.html"

    print("=" * 60)
    print("Grower Intelligence Dashboard")
    print(f"Grower: {grower} | Farm: {farm} | Year: {year}")
    if fields_filter:
        print(f"Fields filter: {fields_filter}")
    print("=" * 60)

    # Load data
    print("[Load] Reading field boundaries ...")
    fields_gdf = load_field_boundaries(grower, farm)
    if fields_filter:
        fields_gdf = fields_gdf[fields_gdf["field_id"].isin(fields_filter)].copy()
        if fields_gdf.empty:
            raise ValueError(f"None of the requested fields {fields_filter} found in boundary file.")
        print(f"  Filtered to {len(fields_gdf)} fields.")
    field_slugs = fields_gdf["field_id"].tolist()

    print("[Load] Reading soil summary ...")
    soil_df = load_soil_summary(grower, farm)

    print("[Load] Reading weather ...")
    weather_df = load_weather(grower, farm)

    print("[Load] Reading CDL composition ...")
    cdl_df = load_cdl(grower, farm)

    # Compute / load NDVI
    print("[Load] Resolving NDVI summary ...")
    ndvi_df = compute_ndvi_summary(grower, farm, year, field_slugs, force_refresh=force_refresh_ndvi)

    # Build summary table
    print("[Build] Assembling summary table ...")
    summary_df = build_summary_table(fields_gdf, soil_df, cdl_df, ndvi_df, weather_df, year)

    # Build charts
    print("[Build] Building charts ...")
    figures: dict[str, go.Figure] = {}
    figures["rotation"] = build_rotation_heatmap(cdl_df)
    figures["ndvi"] = build_ndvi_boxplot(ndvi_df)
    figures["choropleth"] = build_field_choropleth(fields_gdf, soil_df, cdl_df, year)
    figures["weather"] = build_weather_stress_bars(weather_df, year)
    figures["soil"] = build_soil_scorecard(soil_df)

    # Assemble HTML
    print("[Build] Rendering HTML ...")
    assemble_dashboard_html(grower, farm, year, figures, summary_df, output_path)

    # Write manifest
    manifest = {
        "step_name": "grower_intelligence_dashboard",
        "grower_slug": grower,
        "farm_slug": farm,
        "year": year,
        "output_path": str(output_path.relative_to(_RUNTIME_BASE)),
        "status": "complete",
        "chart_count": len(figures),
        "field_count": len(fields_gdf),
        "total_acres": float(summary_df["area_acres"].apply(lambda x: float(x) if x != "N/A" else 0).sum()),
        "generated_at": pd.Timestamp.now().isoformat(),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[Manifest] Written to: {manifest_path}")

    print("=" * 60)
    print("Done.")
    return output_path


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an interactive grower-level intelligence dashboard."
    )
    parser.add_argument(
        "--grower-slug",
        default="northern-il-grower",
        help="Grower slug (default: northern-il-grower)",
    )
    parser.add_argument(
        "--farm-slug",
        default="northern-il-farm",
        help="Farm slug (default: northern-il-farm)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Target season year (default: 2025)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override default output directory",
    )
    parser.add_argument(
        "--force-refresh-ndvi",
        action="store_true",
        help="Recompute NDVI zonal stats and ignore cache",
    )
    parser.add_argument(
        "--fields",
        type=str,
        default=None,
        help="Comma-separated list of field slugs to include (default: all)",
    )
    args = parser.parse_args()

    fields_filter = None
    if args.fields:
        fields_filter = [f.strip() for f in args.fields.split(",")]

    run_dashboard_pipeline(
        grower=args.grower_slug,
        farm=args.farm_slug,
        year=args.year,
        output_dir=args.output_dir,
        force_refresh_ndvi=args.force_refresh_ndvi,
        fields_filter=fields_filter,
    )


if __name__ == "__main__":
    main()
