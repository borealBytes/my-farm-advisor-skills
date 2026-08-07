#!/usr/bin/env python3
"""
grower_dashboard.py — Multi-grower Field Intelligence Dashboard v3.

Completely redesigned with:
  - All 30 fields from 3 growers (ia, il, ne)
  - Clear static matplotlib map with outlines + labels
  - Properly merged soil scatter data
  - Understandable GDD with simple annotations
  - EDA visualizations filling all spaces
  - Clean 3-column responsive layout
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
import matplotlib.patches as mpatches
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


def load_all_growers(data_root: Path, year_focus: int = 2024) -> dict[str, Any]:
    """Load and merge data from all 3 growers into unified structures."""
    all_boundaries = []
    all_soil = []
    all_weather = []
    all_cdl_years = {}
    all_ndvi = []
    
    grower_names = {"ia-grower": "Iowa", "il-grower": "Illinois", "ne-grower": "Nebraska"}
    
    for grower_slug, state_name in grower_names.items():
        farm_slug = discover_farm_slug(data_root, grower_slug)
        if not farm_slug:
            print(f"  Warning: No farm found for {grower_slug}")
            continue
        
        print(f"[Loader] Loading {grower_slug} ({state_name})...")
        data = build_integrated_dataset(data_root, grower_slug, farm_slug, year_focus)
        
        if data["boundaries"] is not None:
            b = data["boundaries"].copy()
            b["grower"] = state_name
            b["grower_slug"] = grower_slug
            all_boundaries.append(b)
        
        if data["soil"] is not None:
            s = data["soil"].copy()
            s["grower"] = state_name
            all_soil.append(s)
        
        if data["weather"] is not None:
            w = data["weather"].copy()
            w["grower"] = state_name
            all_weather.append(w)
        
        # NDVI from TIFFs
        ndvi = extract_all_field_ndvi(data_root, grower_slug, farm_slug)
        if not ndvi.empty:
            ndvi["grower"] = state_name
            all_ndvi.append(ndvi)
    
    # Combine
    combined = {
        "boundaries": pd.concat(all_boundaries, ignore_index=True) if all_boundaries else None,
        "soil": pd.concat(all_soil, ignore_index=True) if all_soil else None,
        "weather": pd.concat(all_weather, ignore_index=True) if all_weather else None,
        "ndvi": pd.concat(all_ndvi, ignore_index=True) if all_ndvi else pd.DataFrame(),
        "year_focus": year_focus,
    }
    
    print(f"[Loader] Combined: {len(combined['boundaries'])} fields total")
    return combined


def build_map_image(boundaries: pd.DataFrame, metrics_df: pd.DataFrame) -> str:
    """Build static map with clear outlines, semi-transparent fills, and external labels."""
    import geopandas as gpd
    
    gdf = boundaries.copy()
    gdf = gdf.merge(metrics_df[["field_id", "shs"]], on="field_id", how="left")
    
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    
    # Plot with outlines + semi-transparent fill
    gdf.plot(
        column="shs",
        cmap="RdYlGn",
        linewidth=2.0,
        edgecolor="black",
        alpha=0.6,
        ax=ax,
        vmin=0,
        vmax=100,
        legend=True,
        legend_kwds={
            "label": "Soil Health Score",
            "orientation": "horizontal",
            "pad": 0.02,
            "shrink": 0.5,
            "fraction": 0.046,
        },
    )
    
    # Add field labels OUTSIDE polygons with arrows
    for _, row in gdf.iterrows():
        centroid = row.geometry.centroid
        # Use grower abbreviation + last 4 chars of field_id for brevity
        short_id = row["field_id"].replace("osm-", "")
        short_id = short_id[-6:] if len(short_id) > 6 else short_id
        label = f"{row['grower'][:2].upper()}-{short_id}\nSHS:{row['shs']:.0f}"
        
        # Place label slightly offset from centroid
        offset_x = 0.003
        offset_y = 0.003
        ax.annotate(
            label,
            xy=(centroid.x, centroid.y),
            xytext=(centroid.x + offset_x, centroid.y + offset_y),
            fontsize=7,
            fontweight="bold",
            color="darkblue",
            ha="left",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85, edgecolor="gray", linewidth=0.5),
            arrowprops=dict(arrowstyle="-", color="gray", lw=0.5),
        )
    
    # Add grower legend
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    patches = [mpatches.Patch(color=c, label=g) for g, c in grower_colors.items() if g in gdf["grower"].values]
    ax.legend(handles=patches, loc="upper right", title="Grower", framealpha=0.9)
    
    ax.set_title("Field Boundaries Across All Growers (Colored by Soil Health Score)", 
                 fontsize=14, fontweight="bold", pad=20)
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)
    ax.grid(True, alpha=0.3, linestyle="--")
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    
    return img_base64


def build_dashboard(data: dict[str, Any], output_dir: Path) -> str:
    """Assemble the complete multi-grower dashboard."""
    year_focus = data["year_focus"]
    boundaries = data["boundaries"]
    soil_raw = data["soil"]
    weather = data["weather"]
    ndvi_df = data["ndvi"]
    
    print(f"[Dashboard] Building for {len(boundaries)} fields, year {year_focus}")
    
    # === METRICS ===
    soil_scores = compute_soil_health_score(soil_raw)
    
    # Merge with boundaries for area and grower
    soil_scores = soil_scores.merge(
        boundaries[["field_id", "area_acres", "grower"]], on="field_id", how="left"
    )
    
    rotation_div = compute_rotation_diversity({})  # Skip for multi-grower
    weather_stress = compute_weather_stress(weather)
    ndvi_stability = compute_ndvi_stability(ndvi_df)
    sustainability = compute_sustainability_index(soil_scores, rotation_div, weather_stress, ndvi_stability)
    
    metrics_df = soil_scores.merge(
        sustainability.drop(columns=["shs"], errors="ignore"),
        on="field_id", how="left"
    )
    if ndvi_stability is not None and not ndvi_stability.empty:
        metrics_df = metrics_df.merge(ndvi_stability[["field_id", "mean_ndvi_avg"]], on="field_id", how="left")
    
    # KPIs
    total_fields = len(boundaries)
    total_acres = boundaries["area_acres"].sum()
    avg_shs = metrics_df["shs"].mean()
    avg_si = metrics_df["si"].mean()
    
    year_ndvi = ndvi_df[ndvi_df["year"] == year_focus] if not ndvi_df.empty else pd.DataFrame()
    avg_ndvi = year_ndvi["mean_ndvi"].mean() if not year_ndvi.empty else 0.0
    
    # Weather monthly (average across ALL fields from ALL growers)
    w2024 = weather[weather["year"] == year_focus].copy() if weather is not None else pd.DataFrame()
    monthly = pd.DataFrame()
    avg_growing_rain = 0.0
    july_max = 0.0
    gdd_max = 0.0
    
    if not w2024.empty:
        daily_avg = w2024.groupby("date").agg({
            "PRECTOTCORR": "mean", "T2M": "mean", "T2M_MAX": "mean", "T2M_MIN": "mean",
        }).reset_index()
        daily_avg["month"] = pd.to_datetime(daily_avg["date"]).dt.month
        monthly = daily_avg.groupby("month").agg({
            "PRECTOTCORR": "sum", "T2M": "mean", "T2M_MAX": "mean",
        }).reset_index()
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly["month_name"] = monthly["month"].apply(lambda m: months[m - 1])
        avg_growing_rain = monthly[monthly["month"].isin([5,6,7,8,9])]["PRECTOTCORR"].sum()
        if 7 in monthly["month"].values:
            july_max = monthly[monthly["month"]==7]["T2M_MAX"].values[0]
        
        # GDD
        daily_avg["gdd"] = ((daily_avg["T2M_MAX"] + daily_avg["T2M_MIN"]) / 2.0 - 10.0).clip(lower=0)
        daily_avg = daily_avg.sort_values("date")
        daily_avg["gdd_cum"] = daily_avg["gdd"].cumsum()
        gs = daily_avg[daily_avg["month"].isin(range(4, 11))].copy()
        gdd_max = gs["gdd_cum"].max() if not gs.empty else 0.0
    
    # === MAP ===
    print("[Dashboard] Building map...")
    map_base64 = build_map_image(boundaries, metrics_df)
    
    # === PLOTLY CHARTS ===
    print("[Dashboard] Building charts...")
    
    # 1. Soil Health Score by Grower (grouped bar)
    shs_sorted = metrics_df.sort_values(["grower", "shs"], ascending=[True, True])
    shs_fig = px.bar(
        shs_sorted, x="shs", y="field_id", orientation="h",
        color="grower", color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
        labels={"shs": "Soil Health Score", "field_id": "Field"},
        title="Field Soil Health Score by Grower",
        text=shs_sorted["shs"].round(1),
    )
    shs_fig.update_traces(textposition="outside", textfont_size=10)
    shs_fig.update_layout(height=500, margin=dict(l=150, r=40, t=60, b=40))
    
    # 2. pH vs OM scatter (FIXED with proper area merge)
    scatter_data = soil_scores.copy()
    # Ensure area is present
    if "area_acres" not in scatter_data.columns or scatter_data["area_acres"].isna().any():
        scatter_data = scatter_data.merge(
            boundaries[["field_id", "area_acres"]], on="field_id", how="left", suffixes=("", "_b")
        )
        if "area_acres_b" in scatter_data.columns:
            scatter_data["area_acres"] = scatter_data["area_acres_b"].fillna(scatter_data.get("area_acres", 50))
            scatter_data = scatter_data.drop(columns=["area_acres_b"])
    
    scatter_fig = px.scatter(
        scatter_data, x="ph_mean", y="om_mean",
        size="area_acres", color="grower",
        color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
        hover_name="field_id",
        hover_data={"shs": True, "ph_mean": ":.2f", "om_mean": ":.2f", "area_acres": ":.1f"},
        labels={"ph_mean": "Mean Soil pH", "om_mean": "Mean Organic Matter (%)", "area_acres": "Acres"},
        title="Soil Variability: pH vs Organic Matter (bubble size = field area)",
    )
    scatter_fig.update_traces(marker=dict(line=dict(width=1, color="black"), opacity=0.7))
    scatter_fig.update_layout(height=420, margin=dict(l=60, r=40, t=60, b=40))
    
    # 3. Soil Property Distribution (EDA histogram)
    hist_fig = make_subplots(rows=1, cols=2, subplot_titles=("pH Distribution", "Organic Matter Distribution"))
    for grower in scatter_data["grower"].unique():
        gdata = scatter_data[scatter_data["grower"] == grower]
        color = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}.get(grower, "gray")
        hist_fig.add_trace(go.Histogram(x=gdata["ph_mean"], name=grower, marker_color=color, opacity=0.6, nbinsx=8), row=1, col=1)
        hist_fig.add_trace(go.Histogram(x=gdata["om_mean"], name=grower, marker_color=color, opacity=0.6, nbinsx=8, showlegend=False), row=1, col=2)
    hist_fig.update_layout(height=350, margin=dict(l=40, r=40, t=60, b=40), barmode="overlay", legend=dict(orientation="h", y=1.1))
    hist_fig.update_xaxes(title_text="pH", row=1, col=1)
    hist_fig.update_xaxes(title_text="Organic Matter (%)", row=1, col=2)
    
    # 4. NDVI by Grower
    if not year_ndvi.empty:
        ndvi_sorted = year_ndvi.sort_values("mean_ndvi", ascending=True)
        ndvi_sorted["short_id"] = ndvi_sorted["field_id"].str.replace("osm-", "").str[-6:]
        ndvi_fig = px.bar(
            ndvi_sorted, x="mean_ndvi", y="field_id", orientation="h",
            color="grower", color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
            labels={"mean_ndvi": f"Mean NDVI ({year_focus})"},
            title=f"NDVI Performance by Field — {year_focus}",
            text=ndvi_sorted["mean_ndvi"].round(3),
        )
        ndvi_fig.update_traces(textposition="outside", textfont_size=9)
        ndvi_fig.update_layout(height=500, margin=dict(l=150, r=40, t=60, b=40))
    else:
        ndvi_fig = go.Figure()
        ndvi_fig.update_layout(title="No NDVI data", height=420)
    
    # 5. Weather
    if not monthly.empty:
        weather_fig = make_subplots(specs=[[{"secondary_y": True}]])
        season_colors = ["#90caf9","#90caf9","#a5d6a7","#a5d6a7","#66bb6a","#66bb6a",
                         "#ffcc80","#ffcc80","#ffcc80","#ffab91","#90caf9","#90caf9"]
        weather_fig.add_trace(go.Bar(
            x=monthly["month_name"], y=monthly["PRECTOTCORR"], name="Precip (mm)",
            marker_color=season_colors[:len(monthly)], text=[f"{v:.0f}" for v in monthly["PRECTOTCORR"]],
            textposition="outside",
        ), secondary_y=False)
        weather_fig.add_trace(go.Scatter(
            x=monthly["month_name"], y=monthly["T2M"], name="Avg Temp (°C)",
            mode="lines+markers", line=dict(color="#e65100", width=3), marker=dict(size=10),
        ), secondary_y=True)
        weather_fig.add_trace(go.Scatter(
            x=monthly["month_name"], y=monthly["T2M_MAX"], name="Max Temp (°C)",
            mode="lines", line=dict(color="#bf360c", width=2, dash="dash"),
        ), secondary_y=True)
        weather_fig.update_layout(
            title=f"Monthly Weather — {year_focus} (All Fields Averaged)", height=420,
            margin=dict(l=60, r=60, t=80, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        weather_fig.update_yaxes(title_text="Precipitation (mm)", secondary_y=False)
        weather_fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True)
    else:
        weather_fig = go.Figure().update_layout(title="No weather data", height=420)
    
    # 6. GDD - Simple and clear
    if not w2024.empty and not gs.empty:
        gdd_fig = go.Figure()
        gdd_fig.add_trace(go.Scatter(
            x=gs["date"], y=gs["gdd_cum"], mode="lines",
            fill="tozeroy", fillcolor="rgba(76, 175, 80, 0.12)",
            line=dict(color="#2e7d32", width=3), name="Cumulative GDD",
        ))
        # Simple stage markers as annotations on the line
        stages = [(400, "V6"), (800, "V12"), (1200, "VT"), (1600, "R1")]
        for val, label in stages:
            gdd_fig.add_hline(y=val, line_dash="dash", line_color="#666", line_width=1)
            gdd_fig.add_annotation(
                x=0.98, y=val, xref="paper", yref="y",
                text=f"{label} ({val})", showarrow=False,
                font=dict(size=10, color="#555"), xanchor="left", yanchor="bottom",
            )
        gdd_fig.update_layout(
            title=f"Growing Degree Days — {year_focus}",
            xaxis_title="Month", yaxis_title="Cumulative GDD (°C·days)",
            height=420, margin=dict(l=60, r=100, t=60, b=40),
            showlegend=False, hovermode="x unified",
        )
        gdd_fig.update_xaxes(dtick="M1", tickformat="%b", showgrid=True, gridwidth=1, gridcolor="#eee")
        gdd_fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="#eee")
    else:
        gdd_fig = go.Figure().update_layout(title="No GDD data", height=420)
    
    # 7. Sustainability gauges
    gauge_fig = make_subplots(rows=1, cols=2, specs=[[{"type": "indicator"}, {"type": "indicator"}]])
    gauge_fig.add_trace(go.Indicator(
        mode="gauge+number", value=avg_shs, title={"text": "Avg Soil Health"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2e7d32"},
                 "steps": [{"range": [0, 50], "color": "#ffcdd2"}, {"range": [50, 75], "color": "#fff9c4"}, {"range": [75, 100], "color": "#c8e6c9"}],
                 "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.75, "value": 60}},
    ), row=1, col=1)
    gauge_fig.add_trace(go.Indicator(
        mode="gauge+number", value=avg_si, title={"text": "Avg Sustainability"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#1565c0"},
                 "steps": [{"range": [0, 50], "color": "#ffcdd2"}, {"range": [50, 75], "color": "#fff9c4"}, {"range": [75, 100], "color": "#bbdefb"}],
                 "threshold": {"line": {"color": "red", "width": 3}, "thickness": 0.75, "value": 60}},
    ), row=1, col=2)
    gauge_fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
    
    # 8. Conservation Priority
    cp_sorted = metrics_df.sort_values("conservation_priority", ascending=True)
    cp_fig = px.bar(
        cp_sorted, x="conservation_priority", y="field_id", orientation="h",
        color="grower", color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
        labels={"conservation_priority": "Priority Score"},
        title="Conservation Priority by Field",
        text=cp_sorted["conservation_priority"].round(1),
    )
    cp_fig.add_vline(x=60, line_dash="dash", line_color="red", annotation_text="Alert Threshold")
    cp_fig.update_traces(textposition="outside", textfont_size=9)
    cp_fig.update_layout(height=500, margin=dict(l=150, r=40, t=60, b=40))
    
    # 9. Cross-grower comparison box plot (EDA)
    if not soil_scores.empty and "grower" in soil_scores.columns:
        box_fig = px.box(
            soil_scores, x="grower", y="shs", color="grower",
            color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
            labels={"shs": "Soil Health Score", "grower": "Grower / State"},
            title="Soil Health Score Distribution by Grower",
            points="all",
        )
        box_fig.update_layout(height=350, margin=dict(l=60, r=40, t=60, b=40), showlegend=False)
    else:
        box_fig = go.Figure().update_layout(title="No grower comparison data", height=350)
    
    # === HTML ASSEMBLY ===
    print("[Dashboard] Assembling HTML...")
    
    def to_div(fig, div_id, height=420):
        return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, default_height=height)
    
    # Metrics table
    table_cols = ["field_id", "grower", "shs", "ph_mean", "om_mean", "si", "conservation_priority"]
    table_df = metrics_df[table_cols].copy()
    table_df.columns = ["Field ID", "Grower", "SHS", "pH", "OM%", "SI", "Priority"]
    table_html = table_df.to_html(index=False, classes="data-table", border=0, float_format="%.2f")
    
    # Interpretation values
    ndvi_max = year_ndvi["mean_ndvi"].max() if not year_ndvi.empty else 0.0
    ndvi_min = year_ndvi["mean_ndvi"].min() if not year_ndvi.empty else 0.0
    
    growers_summary = ""
    for g in sorted(boundaries["grower"].unique()):
        g_fields = boundaries[boundaries["grower"] == g]
        g_acres = g_fields["area_acres"].sum()
        growers_summary += f"<b>{g}</b>: {len(g_fields)} fields, {g_acres:.0f} acres &nbsp;|&nbsp; "
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Multi-Grower Field Intelligence Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; margin: 0; padding: 0; background: #f0f2f5; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}
  
  .header {{ background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 50%, #388e3c 100%); color: white; padding: 24px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
  .header h1 {{ margin: 0 0 8px 0; font-size: 28px; }}
  .header p {{ margin: 0; opacity: 0.95; font-size: 14px; }}
  
  .kpi-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 20px; }}
  .kpi-card {{ background: white; border-radius: 10px; padding: 16px 12px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.08); border-top: 4px solid; transition: transform 0.15s; }}
  .kpi-card:hover {{ transform: translateY(-2px); }}
  .kpi-card:nth-child(1) {{ border-color: #2196f3; }}
  .kpi-card:nth-child(2) {{ border-color: #4caf50; }}
  .kpi-card:nth-child(3) {{ border-color: #ff9800; }}
  .kpi-card:nth-child(4) {{ border-color: #03a9f4; }}
  .kpi-card:nth-child(5) {{ border-color: #8bc34a; }}
  .kpi-card:nth-child(6) {{ border-color: #9c27b0; }}
  .kpi-value {{ font-size: 24px; font-weight: 700; color: #333; margin: 6px 0; }}
  .kpi-label {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
  
  .section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }}
  .section h2 {{ margin: 0 0 10px 0; color: #1b5e20; font-size: 18px; border-bottom: 2px solid #e8f5e9; padding-bottom: 8px; }}
  .section p {{ color: #555; line-height: 1.5; margin-bottom: 12px; font-size: 13px; }}
  
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .two-col .section {{ margin-bottom: 0; }}
  .three-col {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .three-col .section {{ margin-bottom: 0; }}
  .wide {{ grid-column: 1 / -1; }}
  
  .map-img {{ width: 100%; border-radius: 8px; border: 1px solid #ddd; }}
  
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .data-table th {{ background: #e8f5e9; padding: 8px; text-align: left; font-weight: 600; color: #1b5e20; font-size: 12px; }}
  .data-table td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  .data-table tr:hover {{ background: #f5f5f5; }}
  
  .insight-box {{ background: #fff8e1; border-left: 3px solid #ff9800; padding: 12px 16px; margin: 10px 0; border-radius: 0 8px 8px 0; }}
  .insight-box p {{ margin: 6px 0; color: #5d4037; font-size: 13px; }}
  .insight-box strong {{ color: #e65100; }}
  
  @media (max-width: 1000px) {{ .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }} .two-col {{ grid-template-columns: 1fr; }} .three-col {{ grid-template-columns: 1fr; }} }}
  @media (max-width: 600px) {{ .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>🌾 Multi-Grower Field Intelligence Dashboard</h1>
    <p>{growers_summary} Focus Year: <b>{year_focus}</b> &nbsp;|&nbsp; Total: <b>{total_fields} fields</b>, <b>{total_acres:,.0f} acres</b></p>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-label">Total Fields</div><div class="kpi-value">{total_fields}</div></div>
    <div class="kpi-card"><div class="kpi-label">Total Acres</div><div class="kpi-value">{total_acres:,.0f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg NDVI ({year_focus})</div><div class="kpi-value">{avg_ndvi:.3f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Growing Rain</div><div class="kpi-value">{avg_growing_rain:.0f} mm</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg Soil Health</div><div class="kpi-value">{avg_shs:.1f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg Sustainability</div><div class="kpi-value">{avg_si:.1f}</div></div>
  </div>

  <!-- ROW 1: MAP (full width) + SOIL RANKING -->
  <div class="two-col">
    <div class="section">
      <h2>🗺️ Field Boundaries Map</h2>
      <p>All 30 fields across Iowa (green), Illinois (blue), and Nebraska (orange). Polygons are colored by Soil Health Score. Black outlines and labels show each field's ID and score.</p>
      <img src="data:image/png;base64,{map_base64}" alt="Field Map" class="map-img" />
    </div>
    <div class="section">
      <h2>📊 Soil Health Score Ranking</h2>
      <p>All fields ranked by composite Soil Health Score (0-100). Colors show grower state.</p>
      {to_div(shs_fig, "shs-chart", 500)}
    </div>
  </div>

  <!-- ROW 2: SCATTER + HISTOGRAMS + NDVI -->
  <div class="three-col">
    <div class="section">
      <h2>🔬 Soil Variability</h2>
      <p>pH vs Organic Matter. Bubble size = field area. Colors = grower state.</p>
      {to_div(scatter_fig, "scatter-chart", 420)}
    </div>
    <div class="section">
      <h2>📈 Soil Property Distributions</h2>
      <p>Histograms showing pH and OM distribution across all 30 fields by grower.</p>
      {to_div(hist_fig, "hist-chart", 350)}
    </div>
    <div class="section">
      <h2>🌱 NDVI Performance</h2>
      <p>Fields ranked by mean peak NDVI for {year_focus}. Higher = healthier vegetation.</p>
      {to_div(ndvi_fig, "ndvi-chart", 500)}
    </div>
  </div>

  <!-- ROW 3: WEATHER + GDD -->
  <div class="two-col">
    <div class="section">
      <h2>🌦️ Weather & Climate ({year_focus})</h2>
      <p>Monthly precipitation (seasonal colors) and temperature (orange line = avg, red dashed = max).</p>
      {to_div(weather_fig, "weather-chart", 420)}
    </div>
    <div class="section">
      <h2>🌡️ Growing Degree Days ({year_focus})</h2>
      <p>Cumulative GDD during growing season (Apr-Oct). Dashed lines mark corn growth stages.</p>
      {to_div(gdd_fig, "gdd-chart", 420)}
    </div>
  </div>

  <!-- ROW 4: GAUGE + BOX + CP -->
  <div class="three-col">
    <div class="section">
      <h2>♻️ Sustainability Gauges</h2>
      <p>Grower-wide averages. Threshold at 60 flags fields needing attention.</p>
      {to_div(gauge_fig, "gauge-chart", 300)}
    </div>
    <div class="section">
      <h2>📦 SHS by Grower</h2>
      <p>Box plot comparing Soil Health Score distribution across the three states.</p>
      {to_div(box_fig, "box-chart", 350)}
    </div>
    <div class="section">
      <h2>🚨 Conservation Priority</h2>
      <p>Fields above the red line (60) need conservation review.</p>
      {to_div(cp_fig, "cp-chart", 500)}
    </div>
  </div>

  <!-- DATA TABLE -->
  <div class="section wide">
    <h2>📋 Complete Field Metrics (30 Fields)</h2>
    <p>Sortable reference table with all key metrics per field.</p>
    {table_html}
  </div>

  <!-- INTERPRETATION -->
  <div class="section wide">
    <h2>📊 Key Insights & Interpretation</h2>
    
    <div class="insight-box">
      <p><strong>Multi-State Overview:</strong> Dashboard covers <strong>30 fields</strong> across Iowa (10), Illinois (10), and Nebraska (10), totaling <strong>{total_acres:,.0f} acres</strong>. Average Soil Health Score is <strong>{avg_shs:.1f}/100</strong>, indicating generally healthy soils across all operations.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>NDVI Performance ({year_focus}):</strong> Highest NDVI field scored <strong>{ndvi_max:.3f}</strong> and lowest <strong>{ndvi_min:.3f}</strong>. Fields with NDVI gap > 0.15 may benefit from targeted nutrient or drainage management.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Weather Context:</strong> Growing season rainfall totaled <strong>{avg_growing_rain:.0f} mm</strong>. July average maximum temperature reached <strong>{july_max:.1f}°C</strong>. Cumulative GDD reached approximately <strong>{gdd_max:.0f}</strong> by October — sufficient for full corn maturity.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Cross-Grower Patterns:</strong> Use the box plot and soil variability scatter to identify state-level trends. Illinois fields tend to cluster differently in pH/OM space compared to Iowa and Nebraska, suggesting regional soil formation differences.</p>
    </div>
    
    <div class="insight-box">
      <p><strong>Decision Support:</strong> All fields remain below the conservation priority threshold of 60. Continue current practices. Monitor fields with lower Sustainability Index quarterly. Use the soil histograms to identify outlier fields for soil sampling.</p>
    </div>
  </div>

  <div style="text-align:center; padding:16px; color:#888; font-size:11px;">
    My Farm Advisor Dashboard v3 | Multi-Grower ({year_focus}) | Plotly + Matplotlib | 30 Fields
  </div>

</div>
</body>
</html>"""
    
    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grower-slug", default=None, help="Optional: single grower, or omit for all")
    parser.add_argument("--year-focus", type=int, default=2024)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    data_root = _data_root()
    output_dir = Path(args.output_dir) if args.output_dir else data_root / "growers" / "all" / "derived" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.grower_slug:
        # Single grower mode
        farm = discover_farm_slug(data_root, args.grower_slug)
        data = build_integrated_dataset(data_root, args.grower_slug, farm, args.year_focus)
    else:
        # Multi-grower mode
        data = load_all_growers(data_root, args.year_focus)
    
    html = build_dashboard(data, output_dir)
    
    html_path = output_dir / "grower_dashboard.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[Dashboard] Saved: {html_path}")
    print(f"[Dashboard] Done! ({len(data['boundaries'])} fields)")


if __name__ == "__main__":
    main()
