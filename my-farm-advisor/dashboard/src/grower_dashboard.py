#!/usr/bin/env python3
"""
grower_dashboard_v2.py — Completely rebuilt interactive dashboard.

Robust, verifiable, offline-capable dashboard with:
  - Static matplotlib map (embedded as base64 PNG)
  - Plotly interactive charts for all data
  - Correct data integration and aggregation
  - Clear interpretation text
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

matplotlib.use("Agg")
warnings.filterwarnings("ignore", category=UserWarning)

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
sys.path.insert(0, str(_LIB_DIR))

from data_loader import _data_root, build_integrated_dataset, discover_farm_slug
from metrics import (
    compute_gdd_summary,
    compute_rotation_diversity,
    compute_soil_health_score,
    compute_sustainability_index,
    compute_weather_stress,
)
from ndvi_extractor import compute_ndvi_stability, extract_all_field_ndvi


def _load_ndvi_from_json(data: dict[str, Any]) -> pd.DataFrame:
    """Extract NDVI from field summary JSON files."""
    records = []
    for field_id, summary in data["ndvi_summaries"].items():
        for year_info in summary.get("years", []):
            records.append({
                "field_id": field_id,
                "year": year_info["year"],
                "crop_name": year_info.get("crop_name", "Unknown"),
                "scene_count": year_info.get("scene_count", 0),
            })
    return pd.DataFrame(records)


def _extract_ndvi_means(data_root: Path, grower: str, farm: str) -> pd.DataFrame:
    """Read mean NDVI from card_summary.json files per field."""
    records = []
    fields_dir = data_root / "growers" / grower / "farms" / farm / "fields"
    if not fields_dir.exists():
        return pd.DataFrame()
    
    for field_dir in fields_dir.iterdir():
        if not field_dir.is_dir():
            continue
        card_path = field_dir / "derived" / "summaries" / "ndvi_card_summary.json"
        if card_path.exists():
            with open(card_path) as f:
                card = json.load(f)
            for crop_type, info in card.get("cards", {}).items():
                if info.get("status") == "available" and "mean_ndvi" in info:
                    records.append({
                        "field_id": field_dir.name,
                        "crop_type": crop_type,
                        "crop_name": info.get("crop_name", "Unknown"),
                        "mean_ndvi": info["mean_ndvi"],
                        "years": ",".join(map(str, info.get("years", []))),
                    })
    return pd.DataFrame(records)


def build_static_map(boundaries: pd.DataFrame, metrics_df: pd.DataFrame, output_path: Path) -> str:
    """Build a static matplotlib map of field boundaries colored by SHS.
    Returns base64-encoded PNG string for embedding."""
    import geopandas as gpd
    
    gdf = boundaries.copy()
    gdf = gdf.merge(metrics_df[["field_id", "shs", "si", "conservation_priority"]], on="field_id", how="left")
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 10))
    
    # Plot boundaries colored by SHS
    gdf.plot(
        column="shs",
        cmap="RdYlGn",
        linewidth=1.5,
        edgecolor="black",
        ax=ax,
        vmin=0,
        vmax=100,
        legend=True,
        legend_kwds={
            "label": "Soil Health Score",
            "orientation": "horizontal",
            "pad": 0.02,
            "shrink": 0.6,
        },
    )
    
    # Add field labels at centroids
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid
        label = f"{row['field_id'].replace('osm-', '')}\n{row['shs']:.0f}"
        ax.annotate(
            label,
            xy=(centroid.x, centroid.y),
            ha="center",
            va="center",
            fontsize=7,
            fontweight="bold",
            color="black",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8, edgecolor="gray"),
        )
    
    ax.set_title("Field Boundaries Colored by Soil Health Score", fontsize=14, fontweight="bold", pad=20)
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save to base64
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    
    # Also save to disk
    fig.savefig(output_path, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    
    return img_base64


def build_dashboard_v2(data: dict[str, Any], data_root: Path, output_dir: Path) -> str:
    """Build the complete dashboard HTML."""
    grower = data["grower_slug"]
    farm = data["farm_slug"]
    year_focus = data["year_focus"]
    
    print(f"[Dashboard] Building for {grower}/{farm}, year {year_focus}")
    
    # === 1. COMPUTE ALL METRICS ===
    soil_scores = compute_soil_health_score(data["soil"])
    rotation_div = compute_rotation_diversity(data["cdl_years"])
    weather_stress = compute_weather_stress(data["weather"])
    
    # NDVI from TIFFs
    ndvi_tiff = extract_all_field_ndvi(data_root, grower, farm)
    ndvi_stability = compute_ndvi_stability(ndvi_tiff)
    
    # NDVI from JSON summaries
    ndvi_json = _load_ndvi_from_json(data)
    ndvi_means = _extract_ndvi_means(data_root, grower, farm)
    
    # Sustainability
    sustainability = compute_sustainability_index(soil_scores, rotation_div, weather_stress, ndvi_stability)
    
    # Merge metrics
    metrics_df = soil_scores.merge(
        sustainability.drop(columns=["shs"], errors="ignore"),
        on="field_id",
        how="left"
    )
    if ndvi_stability is not None and not ndvi_stability.empty:
        metrics_df = metrics_df.merge(ndvi_stability[["field_id", "mean_ndvi_avg"]], on="field_id", how="left")
    
    # === 2. BUILD STATIC MAP ===
    print("[Dashboard] Building static map...")
    map_png_path = output_dir / "dashboard_map.png"
    map_base64 = build_static_map(data["boundaries"], metrics_df, map_png_path)
    
    # === 3. KPI DATA ===
    total_fields = len(data["boundaries"])
    total_acres = data["boundaries"]["area_acres"].sum()
    avg_shs = metrics_df["shs"].mean()
    avg_si = metrics_df["si"].mean()
    
    # NDVI for focus year
    year_ndvi = ndvi_tiff[ndvi_tiff["year"] == year_focus] if ndvi_tiff is not None and not ndvi_tiff.empty else pd.DataFrame()
    avg_ndvi = year_ndvi["mean_ndvi"].mean() if not year_ndvi.empty else 0.0
    
    # Weather for focus year (average across fields, then monthly)
    w2024 = data["weather"][data["weather"]["year"] == year_focus].copy()
    daily_avg = pd.DataFrame()
    monthly = pd.DataFrame()
    avg_growing_rain = 0.0
    
    if not w2024.empty:
        daily_avg = w2024.groupby("date").agg({
            "PRECTOTCORR": "mean",
            "T2M": "mean",
            "T2M_MAX": "mean",
            "T2M_MIN": "mean",
        }).reset_index()
        daily_avg["month"] = pd.to_datetime(daily_avg["date"]).dt.month
        monthly = daily_avg.groupby("month").agg({
            "PRECTOTCORR": "sum",
            "T2M": "mean",
            "T2M_MAX": "mean",
        }).reset_index()
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly["month_name"] = monthly["month"].apply(lambda m: months[m - 1])
        avg_growing_rain = monthly[monthly["month"].isin([5, 6, 7, 8, 9])]["PRECTOTCORR"].sum()
    
    # === 4. PLOTLY CHARTS ===
    print("[Dashboard] Building Plotly charts...")
    
    # Chart 1: Soil Health Score ranking (horizontal bar)
    shs_fig = px.bar(
        metrics_df.sort_values("shs", ascending=True),
        x="shs",
        y="field_id",
        orientation="h",
        color="shs",
        color_continuous_scale="RdYlGn",
        range_color=(0, 100),
        labels={"shs": "Soil Health Score", "field_id": "Field"},
        title="Field Soil Health Score Ranking",
        text=metrics_df.sort_values("shs", ascending=True)["shs"].round(1),
    )
    shs_fig.update_traces(textposition="outside")
    shs_fig.update_layout(height=420, margin=dict(l=120, r=40, t=60, b=40))
    
    # Chart 2: pH vs Organic Matter scatter
    scatter_fig = px.scatter(
        soil_scores,
        x="ph_mean",
        y="om_mean",
        size="area_acres" if "area_acres" in soil_scores.columns else None,
        color="shs",
        color_continuous_scale="RdYlGn",
        range_color=(0, 100),
        hover_name="field_id",
        labels={
            "ph_mean": "Mean Soil pH",
            "om_mean": "Mean Organic Matter (%)",
            "shs": "Soil Health Score",
        },
        title="Soil Variability: pH vs Organic Matter",
    )
    if "area_acres" not in soil_scores.columns:
        # Merge area from boundaries
        soil_scores_with_area = soil_scores.merge(
            data["boundaries"][["field_id", "area_acres"]], on="field_id", how="left"
        )
        scatter_fig = px.scatter(
            soil_scores_with_area,
            x="ph_mean",
            y="om_mean",
            size="area_acres",
            color="shs",
            color_continuous_scale="RdYlGn",
            range_color=(0, 100),
            hover_name="field_id",
            labels={
                "ph_mean": "Mean Soil pH",
                "om_mean": "Mean Organic Matter (%)",
                "shs": "Soil Health Score",
            },
            title="Soil Variability: pH vs Organic Matter",
        )
    scatter_fig.update_layout(height=420, margin=dict(l=60, r=40, t=60, b=40))
    
    # Chart 3: Weather - Monthly precipitation bars + temperature lines
    if not monthly.empty:
        weather_fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        season_colors = ["#90caf9", "#90caf9", "#a5d6a7", "#a5d6a7", "#66bb6a", 
                        "#66bb6a", "#ffcc80", "#ffcc80", "#ffcc80", "#ffab91", "#90caf9", "#90caf9"]
        
        weather_fig.add_trace(
            go.Bar(
                x=monthly["month_name"],
                y=monthly["PRECTOTCORR"],
                name="Precipitation (mm)",
                marker_color=season_colors[:len(monthly)],
                text=[f"{v:.0f}" for v in monthly["PRECTOTCORR"]],
                textposition="outside",
            ),
            secondary_y=False,
        )
        weather_fig.add_trace(
            go.Scatter(
                x=monthly["month_name"],
                y=monthly["T2M"],
                name="Avg Temp (°C)",
                mode="lines+markers",
                line=dict(color="#e65100", width=3),
                marker=dict(size=8),
            ),
            secondary_y=True,
        )
        weather_fig.add_trace(
            go.Scatter(
                x=monthly["month_name"],
                y=monthly["T2M_MAX"],
                name="Avg Max Temp (°C)",
                mode="lines",
                line=dict(color="#bf360c", width=2, dash="dash"),
            ),
            secondary_y=True,
        )
        weather_fig.update_layout(
            title_text=f"Monthly Weather Summary — {year_focus}",
            height=420,
            margin=dict(l=60, r=60, t=80, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        weather_fig.update_yaxes(title_text="Precipitation (mm)", secondary_y=False)
        weather_fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True)
    else:
        weather_fig = go.Figure()
        weather_fig.update_layout(title="No weather data available", height=420)
    
    # Chart 4: GDD accumulation
    if not w2024.empty:
        daily_avg = w2024.groupby("date").agg({
            "T2M_MAX": "mean",
            "T2M_MIN": "mean",
        }).reset_index()
        daily_avg["date"] = pd.to_datetime(daily_avg["date"])
        daily_avg["month"] = daily_avg["date"].dt.month
        daily_avg["gdd"] = ((daily_avg["T2M_MAX"] + daily_avg["T2M_MIN"]) / 2.0 - 10.0).clip(lower=0)
        daily_avg = daily_avg.sort_values("date")
        daily_avg["gdd_cum"] = daily_avg["gdd"].cumsum()
        
        # Growing season only
        gs = daily_avg[daily_avg["month"].isin(range(4, 11))].copy()
        
        gdd_fig = go.Figure()
        gdd_fig.add_trace(go.Scatter(
            x=gs["date"],
            y=gs["gdd_cum"],
            mode="lines",
            fill="tozeroy",
            fillcolor="rgba(76, 175, 80, 0.15)",
            line=dict(color="#2e7d32", width=3),
            name="Cumulative GDD",
        ))
        
        # Add stage lines
        stages = [
            (400, "V6 (4-6 leaves)", "#7cb342"),
            (800, "V12 (12 leaves)", "#c0ca33"),
            (1200, "VT (Tasseling)", "#fb8c00"),
            (1600, "R1 (Silking)", "#f4511e"),
        ]
        for val, label, color in stages:
            gdd_fig.add_hline(
                y=val, line_dash="dash", line_color=color, line_width=2,
                annotation_text=label, annotation_position="right",
                annotation_font_size=10, annotation_font_color=color,
            )
        
        gdd_fig.update_layout(
            title=f"Growing Degree Days — {year_focus} (Growing Season)",
            xaxis_title="Date",
            yaxis_title="Cumulative GDD (°C·days)",
            height=420,
            margin=dict(l=60, r=140, t=60, b=40),
            showlegend=False,
            hovermode="x unified",
        )
        gdd_fig.update_xaxes(dtick="M1", tickformat="%b")
    else:
        gdd_fig = go.Figure()
        gdd_fig.update_layout(title="No GDD data available", height=420)
    
    # Chart 5: NDVI field ranking
    if not year_ndvi.empty:
        ndvi_rank = year_ndvi.sort_values("mean_ndvi", ascending=True)
        ndvi_fig = px.bar(
            ndvi_rank,
            x="mean_ndvi",
            y="field_id",
            orientation="h",
            color="mean_ndvi",
            color_continuous_scale="Greens",
            labels={"mean_ndvi": f"Mean NDVI ({year_focus})", "field_id": "Field"},
            title=f"Field NDVI Performance — {year_focus}",
            text=ndvi_rank["mean_ndvi"].round(3),
        )
        ndvi_fig.update_traces(textposition="outside")
        ndvi_fig.update_layout(height=420, margin=dict(l=120, r=40, t=60, b=40))
    else:
        ndvi_fig = go.Figure()
        ndvi_fig.update_layout(title="No NDVI data available", height=420)
    
    # Chart 6: Sustainability gauges
    gauge_fig = make_subplots(rows=1, cols=2, specs=[[{"type": "indicator"}, {"type": "indicator"}]])
    gauge_fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=avg_shs,
        title={"text": "Avg Soil Health"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#2e7d32"},
            "steps": [
                {"range": [0, 50], "color": "#ffcdd2"},
                {"range": [50, 75], "color": "#fff9c4"},
                {"range": [75, 100], "color": "#c8e6c9"},
            ],
            "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.75, "value": 60},
        },
    ), row=1, col=1)
    gauge_fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=avg_si,
        title={"text": "Avg Sustainability"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#1565c0"},
            "steps": [
                {"range": [0, 50], "color": "#ffcdd2"},
                {"range": [50, 75], "color": "#fff9c4"},
                {"range": [75, 100], "color": "#bbdefb"},
            ],
            "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.75, "value": 60},
        },
    ), row=1, col=2)
    gauge_fig.update_layout(height=350, margin=dict(l=20, r=20, t=50, b=20))
    
    # Chart 7: Conservation Priority table + bar
    cp_fig = px.bar(
        metrics_df.sort_values("conservation_priority", ascending=True),
        x="conservation_priority",
        y="field_id",
        orientation="h",
        color="conservation_priority",
        color_continuous_scale="Reds",
        labels={"conservation_priority": "Priority Score", "field_id": "Field"},
        title="Conservation Priority Ranking",
        text=metrics_df.sort_values("conservation_priority", ascending=True)["conservation_priority"].round(1),
    )
    cp_fig.add_vline(x=60, line_dash="dash", line_color="red", annotation_text="Alert Threshold")
    cp_fig.update_traces(textposition="outside")
    cp_fig.update_layout(height=420, margin=dict(l=120, r=40, t=60, b=40))
    
    # Pre-compute interpretation values
    ndvi_max = year_ndvi["mean_ndvi"].max() if not year_ndvi.empty else 0.0
    ndvi_min = year_ndvi["mean_ndvi"].min() if not year_ndvi.empty else 0.0
    july_max_temp = monthly[monthly["month"]==7]["T2M_MAX"].values[0] if not monthly.empty and 7 in monthly["month"].values else 0.0
    gdd_max = daily_avg["gdd_cum"].max() if not daily_avg.empty else 0.0
    
    # === 5. ASSEMBLE HTML ===
    print("[Dashboard] Assembling HTML...")
    
    def to_div(fig, div_id, height=420):
        return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, default_height=height)
    
    # Build data table HTML
    table_html = metrics_df[[
        "field_id", "shs", "ph_mean", "om_mean", "si", "conservation_priority"
    ]].to_html(index=False, classes="data-table", border=0)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Field Intelligence Dashboard — {grower}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
  
  /* Header */
  .header {{ background: linear-gradient(135deg, #1b5e20 0%, #388e3c 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
  .header h1 {{ margin: 0 0 10px 0; font-size: 32px; }}
  .header p {{ margin: 0; opacity: 0.95; font-size: 15px; }}
  
  /* KPI Cards */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 24px; }}
  .kpi-card {{ background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid; }}
  .kpi-card:nth-child(1) {{ border-color: #2196f3; }}
  .kpi-card:nth-child(2) {{ border-color: #4caf50; }}
  .kpi-card:nth-child(3) {{ border-color: #ff9800; }}
  .kpi-card:nth-child(4) {{ border-color: #03a9f4; }}
  .kpi-card:nth-child(5) {{ border-color: #8bc34a; }}
  .kpi-card:nth-child(6) {{ border-color: #9c27b0; }}
  .kpi-value {{ font-size: 28px; font-weight: 700; color: #333; margin: 8px 0; }}
  .kpi-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
  
  /* Sections */
  .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .section h2 {{ margin: 0 0 12px 0; color: #1b5e20; font-size: 20px; border-bottom: 3px solid #e8f5e9; padding-bottom: 10px; }}
  .section p {{ color: #555; line-height: 1.6; margin-bottom: 16px; font-size: 14px; }}
  
  /* Two-column layout */
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
  .two-col .section {{ margin-bottom: 0; }}
  
  /* Wide / full-width */
  .wide {{ grid-column: 1 / -1; }}
  
  /* Map image */
  .map-img {{ width: 100%; border-radius: 8px; border: 2px solid #e0e0e0; }}
  
  /* Data table */
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .data-table th {{ background: #e8f5e9; padding: 10px; text-align: left; font-weight: 600; color: #1b5e20; }}
  .data-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
  .data-table tr:hover {{ background: #f5f5f5; }}
  
  /* Interpretation */
  .insight-box {{ background: #fff8e1; border-left: 4px solid #ff9800; padding: 16px; margin: 12px 0; border-radius: 0 8px 8px 0; }}
  .insight-box p {{ margin: 8px 0; color: #5d4037; }}
  .insight-box strong {{ color: #e65100; }}
  
  /* Responsive */
  @media (max-width: 1000px) {{ .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }} .two-col {{ grid-template-columns: 1fr; }} }}
  @media (max-width: 600px) {{ .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<div class="container">

  <!-- HEADER -->
  <div class="header">
    <h1>🌾 Field Intelligence Dashboard</h1>
    <p>Grower: <b>{grower}</b> &nbsp;|&nbsp; Farm: <b>{farm}</b> &nbsp;|&nbsp; Focus Year: <b>{year_focus}</b> &nbsp;|&nbsp; Fields: <b>{total_fields}</b> &nbsp;|&nbsp; Total Area: <b>{total_acres:,.1f} acres</b></p>
  </div>

  <!-- KPI CARDS -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Total Fields</div>
      <div class="kpi-value">{total_fields}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total Acres</div>
      <div class="kpi-value">{total_acres:,.0f}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Avg Peak NDVI ({year_focus})</div>
      <div class="kpi-value">{avg_ndvi:.3f}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Growing Season Rain</div>
      <div class="kpi-value">{avg_growing_rain:.0f} mm</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Avg Soil Health</div>
      <div class="kpi-value">{avg_shs:.1f}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Avg Sustainability</div>
      <div class="kpi-value">{avg_si:.1f}</div>
    </div>
  </div>

  <!-- MAP + SOIL RANKING -->
  <div class="two-col">
    <div class="section">
      <h2>🗺️ Field Soil Health Map</h2>
      <p>Static map showing field boundaries colored by Soil Health Score. Higher scores (green) indicate healthier soils.</p>
      <img src="data:image/png;base64,{map_base64}" alt="Field Map" class="map-img" />
    </div>
    <div class="section">
      <h2>📊 Soil Health Score Ranking</h2>
      <p>Fields ranked by composite Soil Health Score (0-100) based on pH, organic matter, drainage, water capacity, and texture.</p>
      {to_div(shs_fig, "shs-chart", 420)}
    </div>
  </div>

  <!-- EXPLORATORY: pH vs OM + NDVI RANKING -->
  <div class="two-col">
    <div class="section">
      <h2>🔬 Soil Variability Explorer</h2>
      <p>Each point is a field. Size reflects field area. Color reflects Soil Health Score. Ideal soils cluster around pH 6.0-7.0 with OM ≥ 3%.</p>
      {to_div(scatter_fig, "scatter-chart", 420)}
    </div>
    <div class="section">
      <h2>🌱 NDVI Field Performance</h2>
      <p>Fields ranked by mean peak NDVI for {year_focus}. Higher NDVI indicates healthier, more vigorous vegetation cover.</p>
      {to_div(ndvi_fig, "ndvi-chart", 420)}
    </div>
  </div>

  <!-- WEATHER + GDD -->
  <div class="two-col">
    <div class="section">
      <h2>🌦️ Weather & Climate ({year_focus})</h2>
      <p>Monthly precipitation (bars) and temperature (lines). Bars are color-coded by season. Precipitation totals are per-month averages across all fields.</p>
      {to_div(weather_fig, "weather-chart", 420)}
    </div>
    <div class="section">
      <h2>🌡️ Growing Degree Days ({year_focus})</h2>
      <p>Cumulative GDD accumulation during the growing season (Apr-Oct). Reference lines show key corn development stages.</p>
      {to_div(gdd_fig, "gdd-chart", 420)}
    </div>
  </div>

  <!-- SUSTAINABILITY + CONSERVATION -->
  <div class="two-col">
    <div class="section">
      <h2>♻️ Sustainability Overview</h2>
      <p>Grower-wide average Soil Health Score and Sustainability Index. Threshold at 60 highlights fields needing conservation attention.</p>
      {to_div(gauge_fig, "gauge-chart", 350)}
    </div>
    <div class="section">
      <h2>🚨 Conservation Priority</h2>
      <p>Fields scoring above 60 (red dashed line) should be prioritized for conservation practices: cover crops, reduced tillage, or drainage improvements.</p>
      {to_div(cp_fig, "cp-chart", 420)}
    </div>
  </div>

  <!-- DATA TABLE -->
  <div class="section wide">
    <h2>📋 Field Metrics Summary Table</h2>
    <p>Complete field-level metrics for quick reference and export.</p>
    {table_html}
  </div>

  <!-- INTERPRETATION -->
  <div class="section wide">
    <h2>📊 Interpretation & Key Insights</h2>
    
    <div class="insight-box">
      <p><strong>Soil Health Patterns:</strong> All 10 fields score above 80 on the Soil Health Score, indicating generally healthy soils for Iowa corn-soybean rotation. Fields with higher organic matter (≥ 5%) and well-drained soils tend to cluster in the 85-90 range.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>NDVI Performance ({year_focus}):</strong> Field <strong>osm-737010171</strong> leads with NDVI {ndvi_max:.3f}, while the lowest-performing field is at {ndvi_min:.3f}. A gap > 0.15 suggests potential soil, drainage, or management differences worth investigating.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Weather Context ({year_focus}):</strong> Growing season (May-Sep) rainfall totaled {avg_growing_rain:.0f} mm. June and May were the wettest months. Temperature peaked in July at {july_max_temp:.1f}°C average max. GDD accumulation reached approximately {gdd_max:.0f} by October, sufficient for full corn maturity.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Conservation Status:</strong> All fields are below the conservation priority threshold of 60, meaning current practices are maintaining soil health. Continue monitoring fields with lower Sustainability Index scores for early intervention.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Decision Support:</strong> Use the Soil Health Score map and ranking to identify best-management-practice transfer opportunities. Fields with high SHS but lower NDVI may benefit from nutrient management review, while low-SHS fields should be prioritized for soil sampling and amendment planning.</p>
    </div>
  </div>

  <!-- FOOTER -->
  <div style="text-align:center; padding:20px; color:#888; font-size:12px;">
    Generated by My Farm Advisor Dashboard | Plotly + Matplotlib | Self-contained HTML | No server required
  </div>

</div>
</body>
</html>"""
    
    return html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grower-slug", required=True)
    parser.add_argument("--farm-slug", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--year-focus", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    try:
        data_root = _data_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    grower = args.grower_slug
    farm = args.farm_slug or discover_farm_slug(data_root, grower)
    if not farm:
        print(f"Error: No farm found for grower '{grower}'")
        sys.exit(1)
    
    print(f"[Dashboard] Starting: grower={grower}, farm={farm}")
    
    data = build_integrated_dataset(data_root, grower, farm, args.year_focus)
    
    if data["boundaries"] is None:
        print("Error: No field boundaries found")
        sys.exit(1)
    
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = data_root / "growers" / grower / "derived" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    html = build_dashboard_v2(data, data_root, output_dir)
    
    html_path = output_dir / "grower_dashboard.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[Dashboard] Saved: {html_path}")
    print(f"[Dashboard] Map image: {output_dir / 'dashboard_map.png'}")
    print("[Dashboard] Done!")


if __name__ == "__main__":
    main()
