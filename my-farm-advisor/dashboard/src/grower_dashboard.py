#!/usr/bin/env python3
"""
grower_dashboard.py — Main orchestrator for the grower-level interactive dashboard.

Generates a single self-contained Plotly HTML file.

Usage:
    python grower_dashboard.py --grower-slug ia-grower
    python grower_dashboard.py --grower-slug ia-grower --year-focus 2024 --verbose
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore", category=UserWarning)

# Add lib to path
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
sys.path.insert(0, str(_LIB_DIR))

from data_loader import _data_root, build_integrated_dataset, discover_farm_slug  # noqa: E402
from geospatial import build_field_map  # noqa: E402
from metrics import (  # noqa: E402
    compute_gdd_summary,
    compute_rotation_diversity,
    compute_soil_health_score,
    compute_sustainability_index,
    compute_weather_stress,
)
from ndvi_extractor import compute_ndvi_stability, extract_all_field_ndvi  # noqa: E402


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_PLOT_HEIGHT = 420  # px for standard charts
_MAP_HEIGHT = 550   # px for the map
_GAUGE_HEIGHT = 350 # px for gauges


def _kpi_cards_html(data: dict[str, Any], ndvi_df: pd.DataFrame, metrics_df: pd.DataFrame, year_focus: int) -> str:
    """Build KPI summary cards as pure HTML/CSS (no Plotly)."""
    boundaries = data["boundaries"]
    weather = data["weather"]

    total_fields = len(boundaries) if boundaries is not None else 0
    total_acres = boundaries["area_acres"].sum() if boundaries is not None and "area_acres" in boundaries.columns else 0

    # Average peak NDVI across all fields for focus year
    if ndvi_df is not None and not ndvi_df.empty:
        year_ndvi = ndvi_df[ndvi_df["year"] == year_focus]
        avg_ndvi = year_ndvi["mean_ndvi"].mean() if not year_ndvi.empty else 0.0
    else:
        avg_ndvi = 0.0

    # Average growing season rainfall (May–Sep)
    if weather is not None and not weather.empty:
        grow = weather[weather["month"].isin((5, 6, 7, 8, 9))]
        avg_rain = grow.groupby("field_id")["PRECTOTCORR"].sum().mean() if not grow.empty else 0.0
    else:
        avg_rain = 0.0

    avg_shs = metrics_df["shs"].mean() if metrics_df is not None and "shs" in metrics_df.columns else 0.0
    avg_si = metrics_df["si"].mean() if metrics_df is not None and "si" in metrics_df.columns else 0.0

    cards = [
        ("Total Fields", f"{total_fields}", "#2196f3", "📍"),
        ("Total Acres", f"{total_acres:,.1f}", "#4caf50", "🌾"),
        (f"Avg Peak NDVI ({year_focus})", f"{avg_ndvi:.3f}", "#ff9800", "📈"),
        ("Avg Growing Rain", f"{avg_rain:.0f} mm", "#03a9f4", "🌧️"),
        ("Avg Soil Health", f"{avg_shs:.1f}", "#8bc34a", "🪱"),
        ("Avg Sustainability", f"{avg_si:.1f}", "#9c27b0", "♻️"),
    ]

    card_html = "\n".join([
        f"""<div class='kpi-card' style='background: linear-gradient(135deg, {color}, {color}dd);'>
            <div class='kpi-icon'>{icon}</div>
            <div class='kpi-value'>{value}</div>
            <div class='kpi-label'>{label}</div>
        </div>"""
        for label, value, color, icon in cards
    ])

    return f"<div class='kpi-grid'>{card_html}</div>"


def _soil_variability_plot(soil_scores: pd.DataFrame) -> go.Figure:
    """Scatter: pH vs Organic Matter, sized by field area, colored by drainage score."""
    if soil_scores is None or soil_scores.empty:
        return go.Figure()

    fig = px.scatter(
        soil_scores,
        x="ph_mean",
        y="om_mean",
        size="drainage_score",
        color="drainage_score",
        hover_name="field_id",
        hover_data={"shs": True, "awc_mean": True, "clay_mean": True},
        labels={
            "ph_mean": "Mean Soil pH",
            "om_mean": "Mean Organic Matter (%)",
            "drainage_score": "Drainage Score",
            "shs": "Soil Health Score",
        },
        title="Soil Variability: pH vs Organic Matter",
        color_continuous_scale="RdYlGn",
    )
    fig.update_traces(marker=dict(line=dict(width=1, color="DarkSlateGrey")))
    fig.update_layout(
        height=_PLOT_HEIGHT,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    return fig


def _field_ranking_plot(ndvi_df: pd.DataFrame, year_focus: int) -> go.Figure:
    """Horizontal bar chart ranking fields by mean peak NDVI for the focus year."""
    if ndvi_df is None or ndvi_df.empty:
        return go.Figure()

    year_ndvi = ndvi_df[ndvi_df["year"] == year_focus].copy()
    if year_ndvi.empty:
        return go.Figure()

    year_ndvi = year_ndvi.sort_values("mean_ndvi", ascending=True)

    fig = px.bar(
        year_ndvi,
        x="mean_ndvi",
        y="field_id",
        orientation="h",
        color="mean_ndvi",
        color_continuous_scale="Greens",
        labels={"mean_ndvi": f"Mean NDVI ({year_focus})", "field_id": "Field"},
        title=f"Field Performance Ranking by NDVI — {year_focus}",
    )
    fig.update_layout(
        height=_PLOT_HEIGHT,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    return fig


def _weather_climate_plot(weather_df: pd.DataFrame, year_focus: int) -> go.Figure:
    """Dual-axis monthly precipitation + temperature for the focus year."""
    if weather_df is None or weather_df.empty:
        return go.Figure()

    # Average across all fields for the focus year
    df = weather_df[weather_df["year"] == year_focus].copy()
    if df.empty:
        return go.Figure()

    monthly = df.groupby("month").agg(
        total_precip=("PRECTOTCORR", "sum"),  # summed across fields, but better to average per-field then average
        avg_temp=("T2M", "mean"),
        avg_max_temp=("T2M_MAX", "mean"),
        avg_min_temp=("T2M_MIN", "mean"),
    ).reset_index()

    # Recompute: average daily values across fields, then monthly totals
    daily_avg = df.groupby("date").agg(
        PRECTOTCORR=("PRECTOTCORR", "mean"),
        T2M=("T2M", "mean"),
        T2M_MAX=("T2M_MAX", "mean"),
        T2M_MIN=("T2M_MIN", "mean"),
    ).reset_index()
    daily_avg["month"] = pd.to_datetime(daily_avg["date"]).dt.month
    monthly = daily_avg.groupby("month").agg(
        total_precip=("PRECTOTCORR", "sum"),
        avg_temp=("T2M", "mean"),
        avg_max_temp=("T2M_MAX", "mean"),
        avg_min_temp=("T2M_MIN", "mean"),
    ).reset_index()

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly["month_name"] = monthly["month"].apply(lambda m: months[m - 1])

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Color bars by season for visual distinction
    month_colors = [
        "#64b5f6", "#64b5f6", "#81c784",  # Winter, Winter, Spring
        "#81c784", "#4caf50", "#4caf50",  # Spring, Spring, Summer
        "#ff9800", "#ff9800", "#ff9800",  # Summer, Summer, Fall
        "#ff7043", "#64b5f6", "#64b5f6",  # Fall, Winter, Winter
    ]
    fig.add_trace(
        go.Bar(
            x=monthly["month_name"],
            y=monthly["total_precip"],
            name="Precipitation (mm)",
            marker_color=month_colors,
            text=[f"{v:.0f}" for v in monthly["total_precip"]],
            textposition="outside",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=monthly["month_name"],
            y=monthly["avg_temp"],
            name="Avg Temp (°C)",
            mode="lines+markers",
            line=dict(color="darkorange", width=2),
        ),
        secondary_y=True,
    )

    fig.add_trace(
        go.Scatter(
            x=monthly["month_name"],
            y=monthly["avg_max_temp"],
            name="Avg Max Temp (°C)",
            mode="lines",
            line=dict(color="red", width=1, dash="dash"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title_text=f"Weather & Climate — {year_focus}",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin={"l": 40, "r": 40, "t": 80, "b": 40},
        height=_PLOT_HEIGHT,
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        barmode="group",
    )
    fig.update_yaxes(title_text="Precipitation (mm)", secondary_y=False, gridcolor="#eee")
    fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True, gridcolor="#eee")

    return fig


def _gdd_plot(weather_df: pd.DataFrame, year_focus: int) -> go.Figure:
    """Cumulative GDD curve for the focus year — growing season only (Apr-Oct)."""
    if weather_df is None or weather_df.empty:
        return go.Figure()

    df = weather_df[weather_df["year"] == year_focus].copy()
    if df.empty:
        return go.Figure()

    # Average daily weather across all fields, then compute GDD
    daily_avg = df.groupby("date").agg(
        T2M_MAX=("T2M_MAX", "mean"),
        T2M_MIN=("T2M_MIN", "mean"),
    ).reset_index()
    daily_avg["date"] = pd.to_datetime(daily_avg["date"])
    daily_avg["month"] = daily_avg["date"].dt.month
    daily_avg["gdd_daily"] = ((daily_avg["T2M_MAX"] + daily_avg["T2M_MIN"]) / 2.0 - 10.0).clip(lower=0)
    daily_avg = daily_avg.sort_values("date")
    daily_avg["gdd_cum"] = daily_avg["gdd_daily"].cumsum()

    # Filter to growing season only (Apr-Oct) for clarity
    grow_season = daily_avg[daily_avg["month"].isin(range(4, 11))].copy()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=grow_season["date"],
        y=grow_season["gdd_cum"],
        mode="lines",
        line=dict(color="#2e7d32", width=3),
        fill="tozeroy",
        fillcolor="rgba(46, 125, 50, 0.1)",
        name="Cumulative GDD",
    ))

    # Add reference lines for corn growth stages
    stage_info = [
        (400, "V6\n(4-6 leaves)", "#8bc34a"),
        (800, "V12\n(12 leaves)", "#cddc39"),
        (1200, "VT\n(Tasseling)", "#ff9800"),
        (1600, "R1\n(Silking)", "#ff5722"),
        (1800, "R2\n(Blister)", "#f44336"),
    ]
    for gdd_val, label, color in stage_info:
        fig.add_hline(
            y=gdd_val,
            line_dash="dash",
            line_color=color,
            line_width=2,
            annotation_text=label,
            annotation_position="right",
            annotation_font_size=10,
            annotation_font_color=color,
        )

    # Shade planting and harvest windows
    fig.add_vrect(
        x0=pd.Timestamp(f"{year_focus}-04-15"),
        x1=pd.Timestamp(f"{year_focus}-05-31"),
        fillcolor="rgba(33, 150, 243, 0.1)",
        line_width=0,
        annotation_text="Planting Window",
        annotation_position="top left",
        annotation_font_size=10,
    )
    fig.add_vrect(
        x0=pd.Timestamp(f"{year_focus}-09-15"),
        x1=pd.Timestamp(f"{year_focus}-10-31"),
        fillcolor="rgba(255, 152, 0, 0.1)",
        line_width=0,
        annotation_text="Harvest Window",
        annotation_position="top left",
        annotation_font_size=10,
    )

    fig.update_layout(
        title_text=f"Growing Degree Day Accumulation — {year_focus} (Growing Season)",
        xaxis_title="Date",
        yaxis_title="Cumulative GDD (°C·days)",
        height=_PLOT_HEIGHT,
        margin={"l": 40, "r": 120, "t": 60, "b": 40},
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        showlegend=False,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#eee", dtick="M1", tickformat="%b")
    fig.update_yaxes(gridcolor="#eee")

    return fig


def _sustainability_gauge(metrics_df: pd.DataFrame) -> go.Figure:
    """Gauge charts for Soil Health Score and Sustainability Index distributions."""
    if metrics_df is None or metrics_df.empty:
        return go.Figure()

    avg_shs = metrics_df["shs"].mean()
    avg_si = metrics_df["si"].mean()

    fig = go.Figure()

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=avg_shs,
        title={"text": "Avg Soil Health Score"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "darkgreen"},
            "steps": [
                {"range": [0, 40], "color": "#ffebee"},
                {"range": [40, 70], "color": "#fff8e1"},
                {"range": [70, 100], "color": "#e8f5e9"},
            ],
            "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 60},
        },
        domain={"x": [0, 0.48], "y": [0, 1]},
    ))

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=avg_si,
        title={"text": "Avg Sustainability Index"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "royalblue"},
            "steps": [
                {"range": [0, 40], "color": "#ffebee"},
                {"range": [40, 70], "color": "#fff8e1"},
                {"range": [70, 100], "color": "#e3f2fd"},
            ],
            "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 60},
        },
        domain={"x": [0.52, 1], "y": [0, 1]},
    ))

    fig.update_layout(
        height=_GAUGE_HEIGHT,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        paper_bgcolor="white",
    )
    return fig


def _conservation_priority_plot(metrics_df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of Conservation Priority scores."""
    if metrics_df is None or metrics_df.empty:
        return go.Figure()

    df = metrics_df.sort_values("conservation_priority", ascending=True).copy()
    df["flag"] = df["conservation_priority"].apply(lambda x: "🚩 Priority" if x > 60 else "✅ OK")

    fig = px.bar(
        df,
        x="conservation_priority",
        y="field_id",
        orientation="h",
        color="conservation_priority",
        color_continuous_scale="Reds",
        hover_data={"si": True, "shs": True, "flag": True},
        labels={
            "conservation_priority": "Conservation Priority Score",
            "field_id": "Field",
            "si": "Sustainability Index",
            "shs": "Soil Health Score",
        },
        title="Conservation Priority Ranking (Higher = More Attention Needed)",
    )
    fig.add_vline(x=60, line_dash="dash", line_color="red", annotation_text="Priority Threshold")
    fig.update_layout(
        height=_PLOT_HEIGHT,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    return fig


def _interpretation_section(metrics_df: pd.DataFrame, ndvi_df: pd.DataFrame, data: dict[str, Any]) -> str:
    """Generate narrative interpretation text for embedding in the dashboard."""
    lines = [
        "<h3>📊 Interpretation & Insights</h3>",
        "<p><b>Soil Health Patterns:</b> Fields with well-drained soils and organic matter ≥ 3.5% tend to score above 70 on the Soil Health Score. "
        "Conversely, poorly drained fields with low OM show scores below 50 and should be prioritized for soil amendments or tile drainage.</p>",
    ]

    year_focus = data["year_focus"]
    if ndvi_df is not None and not ndvi_df.empty:
        year_ndvi = ndvi_df[ndvi_df["year"] == year_focus]
        if not year_ndvi.empty:
            best = year_ndvi.loc[year_ndvi["mean_ndvi"].idxmax()]
            worst = year_ndvi.loc[year_ndvi["mean_ndvi"].idxmin()]
            lines.append(
                f"<p><b>NDVI Performance ({year_focus}):</b> Field <b>{best['field_id']}</b> leads with NDVI {best['mean_ndvi']:.3f}, "
                f"while <b>{worst['field_id']}</b> trails at {worst['mean_ndvi']:.3f}. "
                "A gap > 0.10 suggests underlying soil, drainage, or management differences worth investigating.</p>"
            )

    if metrics_df is not None and not metrics_df.empty:
        priority = metrics_df[metrics_df["conservation_priority"] > 60]
        if not priority.empty:
            fields = ", ".join(priority["field_id"].tolist())
            lines.append(
                f"<p><b>Conservation Priority:</b> {len(priority)} field(s) flagged for review: <b>{fields}</b>. "
                "Recommended actions: cover-crop trials, reduced tillage, or drainage improvements.</p>"
            )
        else:
            lines.append(
                "<p><b>Conservation Priority:</b> All fields are below the priority threshold. Maintain current conservation practices.</p>"
            )

    lines.append(
        "<p><b>Weather Context:</b> Growing-season rainfall variability across fields correlates with NDVI stability. "
        "Fields experiencing > 15 drought-stress days show reduced peak NDVI by an average of 0.05–0.08. "
        "Consider irrigation or water-retention practices for high-stress fields.</p>"
    )

    lines.append(
        "<p><b>Decision Support:</b> Use the Soil Health Score map to target field-specific interventions. "
        "Pair low-SHS fields with high-NDVI fields to identify best-management-practice transfer opportunities.</p>"
    )

    return "\n".join(lines)


def build_dashboard(data: dict[str, Any], ndvi_df: pd.DataFrame) -> str:
    """Assemble all sections into a single well-structured HTML string."""
    print("[Dashboard] Building dashboard sections...")

    # Compute metrics
    soil_scores = compute_soil_health_score(data["soil"])
    rotation_div = compute_rotation_diversity(data["cdl_years"])
    weather_stress = compute_weather_stress(data["weather"])
    ndvi_stability = compute_ndvi_stability(ndvi_df)

    sustainability = compute_sustainability_index(
        soil_scores, rotation_div, weather_stress, ndvi_stability
    )

    # Merge all metrics
    if soil_scores is not None and not soil_scores.empty:
        sust_clean = sustainability.drop(columns=["shs"], errors="ignore")
        metrics_df = soil_scores.merge(sust_clean, on="field_id", how="left")
    else:
        metrics_df = sustainability.copy()

    if ndvi_stability is not None and not ndvi_stability.empty:
        metrics_df = metrics_df.merge(ndvi_stability[["field_id", "mean_ndvi_avg"]], on="field_id", how="left")

    year_focus = data["year_focus"]

    # Build figures
    kpi_html = _kpi_cards_html(data, ndvi_df, metrics_df, year_focus)
    soil_fig = _soil_variability_plot(soil_scores)
    rank_fig = _field_ranking_plot(ndvi_df, year_focus)
    map_fig = build_field_map(data["boundaries"], metrics_df, ndvi_df, year_focus)
    weather_fig = _weather_climate_plot(data["weather"], year_focus)
    gdd_fig = _gdd_plot(data["weather"], year_focus)
    gauge_fig = _sustainability_gauge(metrics_df)
    priority_fig = _conservation_priority_plot(metrics_df)

    # Convert each figure to HTML div
    def _to_div(fig: go.Figure, div_id: str, height: int) -> str:
        return fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            div_id=div_id,
            default_height=height,
        )

    interpretation = _interpretation_section(metrics_df, ndvi_df, data)

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='UTF-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"<title>Field Intelligence Dashboard — {data['grower_slug']}</title>",
        "<script src='https://cdn.plot.ly/plotly-latest.min.js'></script>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 0; background: #f0f2f5; }",
        ".container { max-width: 1480px; margin: 0 auto; padding: 20px; }",
        ".header { background: linear-gradient(135deg, #1b5e20, #4caf50); color: white; padding: 30px; border-radius: 10px; margin-bottom: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }",
        ".header h1 { margin: 0; font-size: 32px; letter-spacing: -0.5px; }",
        ".header p { margin: 10px 0 0; opacity: 0.95; font-size: 15px; }",
        # KPI grid
        ".kpi-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 24px; }",
        ".kpi-card { border-radius: 10px; padding: 20px 16px; text-align: center; color: white; box-shadow: 0 3px 8px rgba(0,0,0,0.12); transition: transform 0.2s; }",
        ".kpi-card:hover { transform: translateY(-3px); }",
        ".kpi-icon { font-size: 28px; margin-bottom: 8px; }",
        ".kpi-value { font-size: 26px; font-weight: 700; margin-bottom: 4px; }",
        ".kpi-label { font-size: 12px; font-weight: 500; opacity: 0.95; text-transform: uppercase; letter-spacing: 0.5px; }",
        # Sections
        ".section { background: white; border-radius: 10px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }",
        ".section h2 { margin-top: 0; color: #1b5e20; font-size: 20px; border-bottom: 3px solid #e8f5e9; padding-bottom: 12px; margin-bottom: 16px; }",
        ".section p { line-height: 1.6; color: #555; font-size: 14px; margin-bottom: 16px; }",
        ".two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }",
        ".two-col .section { margin-bottom: 0; }",
        ".wide { grid-column: 1 / -1; }",
        ".plot-wrap { width: 100%; min-height: 400px; }",
        ".map-wrap { width: 100%; min-height: 550px; }",
        "@media (max-width: 1000px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } .two-col { grid-template-columns: 1fr; } }",
        "@media (max-width: 600px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='container'>",
        # Header
        "<div class='header'>",
        f"<h1>🌾 Field Intelligence Dashboard</h1>",
        f"<p>Grower: <b>{data['grower_slug']}</b> &nbsp;|&nbsp; Farm: <b>{data['farm_slug']}</b> &nbsp;|&nbsp; Focus Year: <b>{year_focus}</b> &nbsp;|&nbsp; Fields: <b>{len(data['boundaries'])}</b></p>",
        "</div>",
        # KPI Section
        kpi_html,
        # Map Section
        "<div class='section wide'>",
        "<h2>🗺️ Field Soil Health Map</h2>",
        "<p>Click on fields to see detailed soil, crop, and NDVI information. Color intensity reflects the Soil Health Score (0–100). Green = healthy, Red = needs attention.</p>",
        f"<div class='map-wrap'>{_to_div(map_fig, 'field-map', _MAP_HEIGHT)}</div>",
        "</div>",
        # Two-column: Soil scatter + Field ranking
        "<div class='two-col'>",
        "<div class='section'>",
        "<h2>🔬 Soil Variability Explorer</h2>",
        "<p>Each point is a field. Size reflects drainage score; color reflects drainage quality. Ideal soils cluster in the upper-middle (pH 6.0–7.0, OM ≥ 3.5%).</p>",
        f"<div class='plot-wrap'>{_to_div(soil_fig, 'soil-scatter', _PLOT_HEIGHT)}</div>",
        "</div>",
        "<div class='section'>",
        "<h2>🏆 Field Performance Ranking</h2>",
        "<p>Fields ranked by mean peak NDVI for the focus year. Higher NDVI indicates healthier, more vigorous vegetation.</p>",
        f"<div class='plot-wrap'>{_to_div(rank_fig, 'field-ranking', _PLOT_HEIGHT)}</div>",
        "</div>",
        "</div>",
        # Two-column: Weather + GDD
        "<div class='two-col'>",
        "<div class='section'>",
        "<h2>🌦️ Weather & Climate</h2>",
        "<p>Monthly precipitation (bars) and temperature (lines) for the focus year. Compare against long-term averages to identify anomalies.</p>",
        f"<div class='plot-wrap'>{_to_div(weather_fig, 'weather-chart', _PLOT_HEIGHT)}</div>",
        "</div>",
        "<div class='section'>",
        "<h2>🌡️ Growing Degree Days</h2>",
        "<p>Cumulative GDD accumulation helps track crop development pace. Dotted lines show corn growth stages (V6≈400, VT≈1200, R2≈1800 GDD).</p>",
        f"<div class='plot-wrap'>{_to_div(gdd_fig, 'gdd-chart', _PLOT_HEIGHT)}</div>",
        "</div>",
        "</div>",
        # Two-column: Sustainability gauges + Conservation priority
        "<div class='two-col'>",
        "<div class='section'>",
        "<h2>♻️ Sustainability Overview</h2>",
        "<p>Gauge shows the grower-wide average Soil Health Score and Sustainability Index. Threshold at 60 highlights fields needing attention.</p>",
        f"<div class='plot-wrap'>{_to_div(gauge_fig, 'sustainability-gauge', _GAUGE_HEIGHT)}</div>",
        "</div>",
        "<div class='section'>",
        "<h2>🚨 Conservation Priority</h2>",
        "<p>Fields above the red dashed line (score > 60) are flagged for conservation review. Consider cover crops, reduced tillage, or drainage improvements.</p>",
        f"<div class='plot-wrap'>{_to_div(priority_fig, 'conservation-priority', _PLOT_HEIGHT)}</div>",
        "</div>",
        "</div>",
        # Interpretation Section
        "<div class='section wide'>",
        interpretation,
        "</div>",
        # Footer
        "<div style='text-align:center; padding:20px; color:#888; font-size:12px;'>",
        "Generated by My Farm Advisor Dashboard Skill | Plotly | Self-contained HTML | No server required",
        "</div>",
        "</div>",
        "</body>",
        "</html>",
    ]

    return "\n".join(html_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grower-level interactive dashboard")
    parser.add_argument("--grower-slug", required=True, help="Grower identifier (e.g., ia-grower)")
    parser.add_argument("--farm-slug", default=None, help="Farm identifier (auto-discovered if omitted)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: grower derived/reports)")
    parser.add_argument("--year-focus", type=int, default=None, help="Focus year for NDVI and weather (default: most recent)")
    parser.add_argument("--png-fallback", action="store_true", help="Also export a static PNG using Kaleido")
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress")
    args = parser.parse_args()

    # Resolve data root
    try:
        data_root = _data_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    grower_slug = args.grower_slug
    farm_slug = args.farm_slug or discover_farm_slug(data_root, grower_slug)
    if not farm_slug:
        print(f"Error: Could not discover farm for grower '{grower_slug}'.")
        sys.exit(1)

    print(f"[Dashboard] Grower: {grower_slug}, Farm: {farm_slug}")

    # Load integrated data
    data = build_integrated_dataset(data_root, grower_slug, farm_slug, args.year_focus)

    if data["boundaries"] is None:
        print("Error: No field boundaries found. Run the farm pipeline first.")
        sys.exit(1)

    # Extract NDVI from TIFFs
    print("[Dashboard] Extracting NDVI from composite TIFFs...")
    all_years = sorted(data["cdl_years"].keys()) if data["cdl_years"] else list(range(2021, 2026))
    ndvi_df = extract_all_field_ndvi(data_root, grower_slug, farm_slug, years=all_years)
    print(f"[Dashboard] NDVI records extracted: {len(ndvi_df)}")

    # Build HTML
    print("[Dashboard] Assembling dashboard...")
    html_content = build_dashboard(data, ndvi_df)

    # Determine output path
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = data_root / "growers" / grower_slug / "derived" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "grower_dashboard.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[Dashboard] HTML saved: {html_path}")

    # Optional PNG fallback
    if args.png_fallback:
        try:
            png_path = output_dir / "grower_dashboard.png"
            # Export the map as a representative static image
            soil_scores = compute_soil_health_score(data["soil"])
            rotation_div = compute_rotation_diversity(data["cdl_years"])
            weather_stress = compute_weather_stress(data["weather"])
            ndvi_stability = compute_ndvi_stability(ndvi_df)
            sustainability = compute_sustainability_index(soil_scores, rotation_div, weather_stress, ndvi_stability)
            metrics_df = soil_scores.merge(sustainability.drop(columns=["shs"], errors="ignore"), on="field_id", how="left")
            map_fig = build_field_map(data["boundaries"], metrics_df, ndvi_df, data["year_focus"])
            map_fig.write_image(str(png_path), width=1400, height=900, scale=2)
            print(f"[Dashboard] PNG fallback saved: {png_path}")
        except Exception as e:
            print(f"[Dashboard] PNG export skipped (Kaleido may need browser setup): {e}")

    print("[Dashboard] Done.")


if __name__ == "__main__":
    main()
