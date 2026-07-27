#!/usr/bin/env python3
"""
Row Crop Intelligence Dashboard

Plotly Dash application that combines exploratory analysis, geospatial mapping,
weather/climate insights, and soil health/sustainability metrics into a
single interactive agricultural intelligence dashboard for a grower's farm.

Two modes:
  1. Runtime tree mode (requires DATA_PIPELINE_DATA_ROOT):
       python row_crop_dashboard.py --grower iowa-grower --farm iowa-farm

  2. JSON data package mode (no runtime tree needed):
       python row_crop_dashboard.py --json ../dashboard_data.json
"""

import os
import sys
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from dashboard_utils import DashboardData

import dash
from dash import html, dcc, Input, Output, callback

THEME = {
    "bg": "#f8f9fa",
    "card_bg": "#ffffff",
    "primary": "#2c6e49",
    "secondary": "#4c956c",
    "accent": "#fefee3",
    "text": "#1a1a2e",
    "muted": "#6c757d",
    "border": "#dee2e6",
    "ok": "#28a745",
    "warn": "#ffc107",
    "danger": "#dc3545",
    "soil_colors": {
        "Very poorly drained": "#1b4965",
        "Poorly drained": "#4682b4",
        "Somewhat poorly drained": "#89c2d9",
        "Moderately well drained": "#a7c957",
        "Well drained": "#6a994e",
        "Somewhat excessively drained": "#bc6c25",
        "Excessively drained": "#dda15e",
    },
}


def kpi_card(title, value, unit="", color=THEME["primary"], icon=""):
    return html.Div(
        className="kpi-card",
        style={
            "background": THEME["card_bg"],
            "border-radius": "8px",
            "padding": "16px",
            "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
            "text-align": "center",
            "border-left": f"4px solid {color}",
        },
        children=[
            html.Div(icon, style={"font-size": "24px", "margin-bottom": "4px"}),
            html.Div(str(value), style={"font-size": "28px", "font-weight": "700", "color": color}),
            html.Div(title, style={"font-size": "13px", "color": THEME["muted"], "margin-top": "2px"}),
            html.Div(unit, style={"font-size": "11px", "color": THEME["muted"]}) if unit else None,
        ],
    )


def build_kpi_section(kpis):
    rows = []
    if kpis.get("avg_rainfall_mm"):
        rows.append(
            html.Div(
                style={
                    "display": "grid",
                    "grid-template-columns": "repeat(6, 1fr)",
                    "gap": "12px",
                    "margin-bottom": "20px",
                },
                children=[
                    kpi_card("Fields", kpis["total_fields"], "", THEME["primary"], "\U0001f33e"),
                    kpi_card("Total Acreage", f"{kpis['total_acreage']:,.0f}", "acres", THEME["secondary"], "\U0001f3d4\ufe0f"),
                    kpi_card("Avg NDVI", f"{kpis['avg_ndvi']:.3f}", "0-1 scale", THEME["ok"], "\U0001f331"),
                    kpi_card("Avg Rainfall", f"{kpis['avg_rainfall_mm']:.0f}", "mm/yr", "#0077b6", "\U0001f327\ufe0f"),
                    kpi_card("Soil Health", f"{kpis['avg_soil_health']:.0f}", "/100", THEME["warn"], "\U0001f30d"),
                    kpi_card("Sustainability", f"{kpis['avg_sustainability']:.0f}", "/100", "#9b5de5", "\u267b\ufe0f"),
                ],
            )
        )
    return rows


def create_soil_ph_chart(data):
    metrics = data.compute_sustainability_index()
    if data.soil.empty:
        return html.Div("Soil data not available", style={"color": THEME["muted"]})

    field_soil = data.soil.groupby("field_id").agg({"avg_ph": "mean"}).reset_index()
    field_soil.columns = ["field_id", "avg_ph"]
    field_ids_sorted = field_soil.sort_values("avg_ph")["field_id"].tolist()

    fig = go.Figure()
    for i, fid in enumerate(field_ids_sorted):
        row = field_soil[field_soil["field_id"] == fid].iloc[0]
        short_id = fid.replace("osm-", "")
        fig.add_trace(go.Bar(
            x=[short_id],
            y=[row["avg_ph"]],
            name=short_id,
            marker_color=THEME["secondary"] if 6.0 <= row["avg_ph"] <= 7.0 else THEME["danger"],
            showlegend=False,
        ))

    fig.add_hline(y=6.0, line_dash="dash", line_color=THEME["ok"], opacity=0.5)
    fig.add_hline(y=7.0, line_dash="dash", line_color=THEME["ok"], opacity=0.5)

    fig.add_annotation(
        xref="paper", x=1.0,
        yref="paper", y=1.12,
        text="Optimal max (7.0)",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color="black"),
    )
    fig.add_annotation(
        xref="paper", x=1.0,
        yref="paper", y=1.06,
        text="Optimal min (6.0)",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color="black"),
    )

    fig.update_layout(
        title="Soil pH by Field",
        yaxis_title="pH",
        xaxis_title="Field",
        template="simple_white",
        height=350,
        margin=dict(l=40, r=20, t=50, b=60),
        hovermode="x unified",
    )
    return dcc.Graph(figure=fig)


def create_ndvi_comparison_chart(data):
    metrics = data.compute_sustainability_index()
    if metrics.empty or "avg_ndvi" not in metrics.columns:
        return html.Div("NDVI data not available", style={"color": THEME["muted"]})

    df = metrics[metrics["avg_ndvi"].notna()].copy()
    if df.empty:
        return html.Div("NDVI data not available", style={"color": THEME["muted"]})

    df["short_id"] = df["field_id"].str.replace("osm-", "")
    df = df.sort_values("avg_ndvi", ascending=False)

    drainage_colors = {k: v for k, v in THEME["soil_colors"].items()}
    df["color"] = df["drainage_class"].map(drainage_colors).fillna(THEME["secondary"])

    fig = go.Figure()
    for _, row in df.iterrows():
        fig.add_trace(go.Bar(
            x=[row["short_id"]],
            y=[row["avg_ndvi"]],
            marker_color=row["color"],
            name=row["drainage_class"] if pd.notna(row.get("drainage_class")) else "Unknown",
            hovertemplate=(
                f"<b>{row['short_id']}</b><br>"
                f"NDVI: {row['avg_ndvi']:.3f}<br>"
                f"Soil: {row.get('dominant_soil', 'N/A')}<br>"
                f"Drainage: {row.get('drainage_class', 'N/A')}<br>"
                f"OM%: {row.get('avg_om_pct', 'N/A')}<br>"
                f"<extra></extra>"
            ),
            showlegend=False,
        ))

    fig.add_hline(y=df["avg_ndvi"].mean(), line_dash="dot", line_color=THEME["muted"],
                  annotation_text=f"Farm avg: {df['avg_ndvi'].mean():.3f}")

    fig.update_layout(
        title="Average NDVI by Field (colored by drainage class)",
        yaxis_title="NDVI",
        xaxis_title="Field",
        template="simple_white",
        height=350,
        margin=dict(l=40, r=20, t=50, b=60),
    )
    return dcc.Graph(figure=fig)


def create_geospatial_map(data):
    metrics = data.compute_sustainability_index()
    if data.field_geojson.empty:
        return html.Div("Field boundary data not available", style={"color": THEME["muted"]})

    gdf = data.field_geojson.copy()
    if "field_id" not in gdf.columns:
        gdf["field_id"] = [f"field_{i}" for i in range(len(gdf))]

    if not metrics.empty and "soil_health_score" in metrics.columns:
        gdf = gdf.merge(
            metrics[["field_id", "soil_health_score", "sustainability_index", "avg_ndvi",
                     "avg_om_pct", "avg_ph", "drainage_class", "dominant_soil"]],
            on="field_id", how="left"
        )
    else:
        gdf["soil_health_score"] = 50

    gdf["short_id"] = gdf["field_id"].str.replace("osm-", "")

    field_numbers = {
        "osm-1219926116": 1,
        "osm-1223974574": 2,
        "osm-1330494009": 3,
        "osm-1330494051": 4,
        "osm-1330494053": 5,
        "osm-1330494055": 6,
        "osm-1330494071": 7,
        "osm-1330494087": 8,
        "osm-1330710265": 9,
        "osm-922936689": 10,
    }
    gdf["field_number"] = gdf["field_id"].map(field_numbers).fillna(0).astype(int)

    gdf_web = gdf.to_crs("EPSG:4326")

    lats = []
    lons = []
    text = []
    colors = []
    for _, row in gdf_web.iterrows():
        if row.geometry.geom_type == "Polygon":
            coords = list(row.geometry.exterior.coords)
        elif row.geometry.geom_type == "MultiPolygon":
            coords = list(row.geometry.geoms[0].exterior.coords)
        else:
            continue
        lats.append([c[1] for c in coords] + [coords[0][1]])
        lons.append([c[0] for c in coords] + [coords[0][0]])

        shs = row.get("soil_health_score", 50)
        if pd.notna(shs):
            colors.append(shs)
        else:
            colors.append(50)

        text.append(
            f"<b>{row['short_id']}</b><br>"
            f"Soil Health: {row.get('soil_health_score', 'N/A')}<br>"
            f"NDVI: {row.get('avg_ndvi', 'N/A')}<br>"
            f"Drainage: {row.get('drainage_class', 'N/A')}<br>"
            f"Soil: {row.get('dominant_soil', 'N/A')}<br>"
            f"OM%: {row.get('avg_om_pct', 'N/A')}<br>"
            f"pH: {row.get('avg_ph', 'N/A')}"
        )

    fig = go.Figure()
    for i in range(len(lats)):
        fig.add_trace(go.Scattermap(
            lon=lons[i],
            lat=lats[i],
            mode="lines",
            fill="toself",
            fillcolor="rgba(204, 85, 0, 0.3)",
            line=dict(width=2, color="white"),
            name=gdf_web.iloc[i]["short_id"] if i < len(gdf_web) else f"Field {i}",
            hovertext=text[i] if i < len(text) else "",
            hoverinfo="text",
            showlegend=False,
        ))

    scatter_lons = []
    scatter_lats = []
    scatter_colors = []
    scatter_text = []
    scatter_numbers = []
    for i, row in gdf_web.iterrows():
        centroid = row.geometry.centroid
        scatter_lons.append(centroid.x)
        scatter_lats.append(centroid.y)
        shs = row.get("soil_health_score", 50)
        scatter_colors.append(shs if pd.notna(shs) else 50)
        short_id = row.get("short_id", f"Field {i}")
        scatter_text.append(
            f"<b>{short_id}</b><br>"
            f"Soil Health: {shs if pd.notna(shs) else 'N/A'}"
        )
        scatter_numbers.append(str(row.get("field_number", "")))

    fig.add_trace(go.Scattermap(
        lon=scatter_lons,
        lat=scatter_lats,
        mode="markers+text",
        marker=dict(
            size=30,
            color=scatter_colors,
            colorscale="Greens",
            cmin=40,
            cmax=100,
            colorbar=dict(title="Soil<br>Health<br>Score", thickness=15, len=0.5),
        ),
        text=scatter_numbers,
        textposition="middle center",
        textfont=dict(size=12, color="white"),
        customdata=scatter_text,
        hovertemplate="%{customdata}<extra></extra>",
        showlegend=False,
    ))

    bounds = gdf_web.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    fig.update_layout(
        title="Field Boundaries by Soil Health Score",
        map=dict(
            style="satellite",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=13,
        ),
        height=500,
        margin=dict(l=0, r=0, t=50, b=0),
    )

    interpretation = html.Div(
        style={
            "background": "#f0f7f0",
            "border-left": "4px solid #2c6e49",
            "padding": "12px 16px",
            "margin-top": "10px",
            "border-radius": "4px",
            "font-size": "14px",
            "color": THEME["text"],
        },
        children=[
            html.Strong("\U0001f50d Key Insight: "),
            "Fields with higher drainage capacity and organic matter content "
            "show stronger soil health scores. Northern fields cluster with "
            "lower scores, suggesting a management or drainage gradient "
            "across the farm."
        ],
    )

    return html.Div([dcc.Graph(figure=fig), interpretation])


def create_weather_chart(data):
    if data.weather.empty:
        return html.Div("Weather data not available", style={"color": THEME["muted"]})

    w = data.weather.copy()
    w["month"] = w["date"].dt.month
    w["year"] = w["date"].dt.year

    monthly = w.groupby(["year", "month"]).agg(
        precip=("prectotcorr", "sum"),
        temp=("t2m", "mean"),
        tmin=("t2m_min", "mean"),
        tmax=("t2m_max", "mean"),
    ).reset_index()

    fig = go.Figure()

    years = sorted(monthly["year"].unique())
    colors = px.colors.sequential.Viridis[:len(years)]
    for i, yr in enumerate(years):
        yr_data = monthly[monthly["year"] == yr]
        fig.add_trace(go.Bar(
            x=[f"{int(m):02d}" for m in yr_data["month"]],
            y=yr_data["precip"],
            name=str(yr),
            marker_color=colors[i],
            opacity=0.7,
            yaxis="y",
            hovertemplate=f"{yr}<br>Month: %{{x}}<br>Precip: %{{y:.1f}} mm<extra></extra>",
        ))

    avg_temp = monthly.groupby("month")["temp"].mean().reset_index()
    fig.add_trace(go.Scatter(
        x=[f"{int(m):02d}" for m in avg_temp["month"]],
        y=avg_temp["temp"],
        mode="lines+markers",
        name="Avg Temp (\u00b0C)",
        line=dict(color="red", width=3),
        marker=dict(size=8, symbol="circle"),
        yaxis="y2",
        hovertemplate="Temp: %{y:.1f}\u00b0C<extra></extra>",
    ))

    fig.add_vrect(x0="03", x1="09", line_width=0,
                  fillcolor="green", opacity=0.03,
                  annotation_text="Growing Season (Apr-Sep)",
                  annotation_position="top left")

    fig.update_layout(
        title="Monthly Precipitation & Average Temperature (2021-2025)",
        xaxis_title="Month",
        yaxis=dict(title="Precipitation (mm)", side="left"),
        yaxis2=dict(
            title="Temperature (\u00b0C)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        barmode="group",
        template="simple_white",
        height=400,
        margin=dict(l=50, r=50, t=50, b=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )

    interpretation = html.Div(
        style={
            "background": "#f0f7f0",
            "border-left": "4px solid #0077b6",
            "padding": "12px 16px",
            "margin-top": "10px",
            "border-radius": "4px",
            "font-size": "14px",
            "color": THEME["text"],
        },
        children=[
            html.Strong("\U0001f50d Key Insight: "),
            f"Average annual rainfall of {data.get_kpis().get('avg_rainfall_mm', 'N/A')} mm "
            "supports rainfed corn and soybean production. The growing season "
            "(Apr-Sep) captures the majority of precipitation and warm temperatures, "
            "consistent with typical Corn Belt conditions."
        ],
    )

    return html.Div([dcc.Graph(figure=fig), interpretation])


def create_soil_health_chart(data):
    metrics = data.compute_sustainability_index()
    if metrics.empty:
        return html.Div("Soil data not available", style={"color": THEME["muted"]})

    df = metrics.copy()
    df["short_id"] = df["field_id"].str.replace("osm-", "")

    fig = go.Figure()
    for _, row in df.iterrows():
        fig.add_trace(go.Bar(
            name=row["short_id"],
            x=["Soil Health Score", "Sustainability Index"],
            y=[row.get("soil_health_score", 0), row.get("sustainability_index", 0)],
            hovertemplate=(
                f"<b>{row['short_id']}</b><br>"
                f"%{{x}}: %{{y:.1f}}<br>"
                f"OM: {row.get('avg_om_pct', 'N/A')}% | pH: {row.get('avg_ph', 'N/A')}<br>"
                f"NDVI: {row.get('avg_ndvi', 'N/A')} | Diversity: {row.get('crop_diversity', 'N/A')}<br>"
                f"<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Soil Health Score & Sustainability Index by Field",
        xaxis_title="Metric",
        yaxis_title="Score (0-100)",
        barmode="group",
        template="simple_white",
        height=550,
        margin=dict(l=40, r=20, t=60, b=120),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.12,
            x=1.0,
            xanchor="right",
            font=dict(size=9),
            traceorder="normal",
        ),
        hovermode="x unified",
    )

    interpretation = html.Div(
        style={
            "background": "#f0f7f0",
            "border-left": "4px solid #9b5de5",
            "padding": "12px 16px",
            "margin-top": "10px",
            "border-radius": "4px",
            "font-size": "14px",
            "color": THEME["text"],
        },
        children=[
            html.Strong("\U0001f50d Key Insight: "),
            "Fields osm-1219926116 and osm-1223974574 lead in soil health due to "
            "high organic matter (6.6-7.7%) and favorable drainage. Fields with "
            "lower scores tend to have sandier textures or restricted drainage, "
            "reducing their water holding capacity and nutrient retention."
        ],
    )

    return html.Div([
        dcc.Graph(figure=fig),
        interpretation,
    ])


def create_correlation_chart(data):
    metrics = data.compute_sustainability_index()
    if metrics.empty:
        return html.Div("Data not available", style={"color": THEME["muted"]})

    corr_cols = ["avg_om_pct", "avg_ph", "avg_cec", "avg_clay_pct", "avg_sand_pct",
                 "total_aws_inches", "avg_ndvi", "soil_health_score", "sustainability_index"]
    available = [c for c in corr_cols if c in metrics.columns]
    if len(available) < 3:
        return html.Div("Insufficient data for correlation", style={"color": THEME["muted"]})

    corr_df = metrics[available].dropna()
    if corr_df.empty:
        return html.Div("Insufficient data for correlation", style={"color": THEME["muted"]})

    corr_matrix = corr_df.corr()

    labels = {
        "avg_om_pct": "OM%", "avg_ph": "pH", "avg_cec": "CEC",
        "avg_clay_pct": "Clay%", "avg_sand_pct": "Sand%",
        "total_aws_inches": "AWC", "avg_ndvi": "NDVI",
        "soil_health_score": "Soil Health", "sustainability_index": "Sustainability",
    }
    short_labels = [labels.get(c, c) for c in corr_matrix.columns]

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=short_labels,
        y=short_labels,
        colorscale="RdBu_r",
        zmin=-1, zmax=1,
        text=np.round(corr_matrix.values, 2),
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="%{x} vs %{y}: %{z:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title="Correlation Matrix: Soil Properties & Crop Health",
        template="simple_white",
        height=650,
        margin=dict(l=40, r=20, t=60, b=140),
        xaxis=dict(side="bottom", tickangle=-45),
    )

    return dcc.Graph(figure=fig)


def create_aligned_timeline(data):
    target_field = "osm-1219926116"
    crop_seq = data.get_field_crop_sequence(target_field)
    year_colors = {2021: "#1b9e77", 2022: "#d95f02", 2023: "#7570b3", 2024: "#e7298a", 2025: "#66a61e"}

    scenes = data.ndvi_scenes
    ndvi_f = scenes[scenes["field_id"] == target_field].copy() if not scenes.empty else pd.DataFrame()
    if not ndvi_f.empty:
        ndvi_f["date"] = pd.to_datetime(ndvi_f["date"])
        ndvi_f = ndvi_f.sort_values("date")

    w = data.weather_daily
    w_f = w[w["field_id"] == target_field].copy() if not w.empty and "field_id" in w.columns else w.copy()
    if not w_f.empty and "date" in w_f.columns:
        w_f["date"] = pd.to_datetime(w_f["date"])
        w_f = w_f.sort_values("date")

    gdd = data.gdd_daily
    gdd_f = gdd[gdd["field_id"] == target_field].copy() if not gdd.empty and "field_id" in gdd.columns else gdd.copy()
    if not gdd_f.empty and "date" in gdd_f.columns:
        gdd_f["date"] = pd.to_datetime(gdd_f["date"])
        gdd_f = gdd_f.sort_values("date")

    has_data = not ndvi_f.empty or not w_f.empty or not gdd_f.empty
    if not has_data:
        fallback_ndvi = data.ndvi
        fallback_w = data.weather
        if fallback_ndvi.empty and fallback_w.empty:
            return html.Div()

    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=("NDVI Accumulation", "Daily Precipitation (mm)",
                        "Temperature Range (°C)", "Cumulative GDD (°C·day)",
                        "SPI (Standardized Precipitation Index)"),
        row_heights=[0.22, 0.19, 0.19, 0.20, 0.20],
    )

    max_date = None
    min_date = None

    if not ndvi_f.empty:
        for yr in sorted(ndvi_f["year"].unique()):
            yr_data = ndvi_f[ndvi_f["year"] == yr]
            crop = crop_seq.get(int(yr), f"Year {yr}")
            label = f"{yr} - {crop}"
            fig.add_trace(
                go.Scatter(
                    x=yr_data["date"], y=yr_data["ndvi"],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=year_colors.get(int(yr), "#333"), width=1.5),
                    marker=dict(size=6, color=year_colors.get(int(yr), "#333")),
                    hovertemplate="%{x|%b %d}<br>NDVI: %{y:.3f}<br>" + label + "<extra></extra>",
                ),
                row=1, col=1,
            )
            peak = yr_data.loc[yr_data["ndvi"].idxmax()]
            fig.add_annotation(
                x=peak["date"], y=peak["ndvi"],
                text=f"Peak: {peak['ndvi']:.3f}",
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                ax=30, ay=-30, font=dict(size=9, color=year_colors.get(int(yr), "#333")),
                row=1, col=1,
            )
        if not ndvi_f.empty:
            min_date = ndvi_f["date"].min()
            max_date = ndvi_f["date"].max()
    else:
        fig.add_annotation(text="No per-scene NDVI data", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=1, col=1)

    if not w_f.empty:
        fig.add_trace(
            go.Bar(
                x=w_f["date"], y=w_f["prectotcorr"],
                name="Precipitation",
                marker=dict(color="#4682b4", opacity=0.7),
                hovertemplate="%{x|%b %d, %Y}<br>Precip: %{y:.1f} mm<extra></extra>",
            ),
            row=2, col=1,
        )
        if min_date is None or w_f["date"].min() < min_date:
            min_date = w_f["date"].min()
        if max_date is None or w_f["date"].max() > max_date:
            max_date = w_f["date"].max()

        has_tmin = "t2m_min" in w_f.columns
        has_tmax = "t2m_max" in w_f.columns
        if has_tmin and has_tmax:
            fig.add_trace(
                go.Scatter(
                    x=w_f["date"], y=w_f["t2m_max"],
                    mode="lines", name="Tmax",
                    line=dict(color="#d62728", width=1.5),
                    hovertemplate="%{x|%b %d, %Y}<br>Tmax: %{y:.1f}°C<extra></extra>",
                ),
                row=3, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=w_f["date"], y=w_f["t2m_min"],
                    mode="lines", name="Tmin",
                    line=dict(color="#1f77b4", width=1.5),
                    hovertemplate="%{x|%b %d, %Y}<br>Tmin: %{y:.1f}°C<extra></extra>",
                ),
                row=3, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=pd.concat([w_f["date"], w_f["date"][::-1]]),
                    y=pd.concat([w_f["t2m_max"], w_f["t2m_min"][::-1]]),
                    fill="toself", fillcolor="rgba(214,39,40,0.15)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name="Range", hoverinfo="skip",
                    showlegend=False,
                ),
                row=3, col=1,
            )
            for yr in range(2021, 2026):
                yr_w = w_f[w_f["date"].dt.year == yr].sort_values("date")
                if yr_w.empty:
                    continue
                frost = yr_w[yr_w["t2m_min"] < 0]
                if not frost.empty:
                    last_spring = frost[frost["date"].dt.dayofyear <= 180]
                    first_fall = frost[frost["date"].dt.dayofyear > 180]
                    if not last_spring.empty:
                        ld = last_spring.iloc[-1]["date"]
                        fig.add_annotation(
                            x=ld, y=yr_w["t2m_max"].max(),
                            text=f"Last frost: {ld.strftime('%b %d')}",
                            showarrow=True, arrowhead=2, ax=0, ay=-40,
                            font=dict(size=8, color="#1f77b4"),
                            row=3, col=1,
                        )
        for yr in range(2021, 2026):
            planting = pd.Timestamp(f"{yr}-05-01")
            for panel in [2, 4]:
                fig.add_shape(
                    type="line",
                    x0=planting, y0=0, x1=planting, y1=1,
                    line=dict(color="green", width=1, dash="dot"),
                    row=panel, col=1,
                )
                fig.add_annotation(
                    x=planting, y=0.98,
                    text="Planting", showarrow=False,
                    font=dict(size=8, color="green"),
                    textangle=-90,
                    xref="x", yref="paper",
                    row=panel, col=1,
                )
    else:
        fig.add_annotation(text="No daily weather data", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=2, col=1)
        fig.add_annotation(text="", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=3, col=1)

    if not gdd_f.empty:
        for yr in sorted(gdd_f["year"].unique()):
            yr_gdd = gdd_f[gdd_f["year"] == yr]
            crop = crop_seq.get(int(yr), f"Year {yr}")
            fig.add_trace(
                go.Scatter(
                    x=yr_gdd["date"], y=yr_gdd["cumulative_gdd"],
                    mode="lines",
                    name=f"{yr} GDD ({crop})",
                    line=dict(color=year_colors.get(int(yr), "#333"), width=2),
                    hovertemplate="%{x|%b %d}<br>GDD: %{y:.0f} °C·day<extra></extra>",
                ),
                row=4, col=1,
            )
            final = yr_gdd.iloc[-1]
            fig.add_annotation(
                x=final["date"], y=final["cumulative_gdd"],
                text=f"{final['cumulative_gdd']:.0f} °C·d",
                showarrow=True, arrowhead=2, ax=30, ay=-20,
                font=dict(size=9, color=year_colors.get(int(yr), "#333")),
                row=4, col=1,
            )

    spi_f = data.get_spi_for_field(target_field)
    if not spi_f.empty:
        spi_f["date"] = pd.to_datetime(spi_f["year"].astype(str) + "-" + spi_f["month"].astype(str).str.zfill(2) + "-01")
        spi_f = spi_f.sort_values("date")
        for win, color, name in [(1, "#2c6e49", "SPI-1"), (3, "#d95f02", "SPI-3"),
                                  (6, "#7570b3", "SPI-6"), (12, "#1b9e77", "SPI-12")]:
            col = f"spi{win}"
            if col in spi_f.columns:
                fig.add_trace(
                    go.Bar(
                        x=spi_f["date"], y=spi_f[col],
                        name=name, marker=dict(color=color, opacity=0.6),
                        hovertemplate="%{x|%b %Y}<br>%{y:+.2f}<extra></extra>",
                    ),
                    row=5, col=1,
                )
        fig.add_shape(type="line", x0=spi_f["date"].min(), y0=0,
                      x1=spi_f["date"].max(), y1=0,
                      line=dict(color="#333", width=1),
                      row=5, col=1)
        fig.add_shape(type="line", x0=spi_f["date"].min(), y0=-1,
                      x1=spi_f["date"].max(), y1=-1,
                      line=dict(color="#d62728", width=1, dash="dash"),
                      row=5, col=1)
        fig.add_shape(type="line", x0=spi_f["date"].min(), y0=1,
                      x1=spi_f["date"].max(), y1=1,
                      line=dict(color="#1f77b4", width=1, dash="dash"),
                      row=5, col=1)
        fig.add_annotation(x=spi_f["date"].max(), y=1.1, text="Wet",
                           showarrow=False, font=dict(size=9, color="#1f77b4"),
                           xref="x", yref="y", row=5, col=1)
        fig.add_annotation(x=spi_f["date"].max(), y=-1.1, text="Dry",
                           showarrow=False, font=dict(size=9, color="#d62728"),
                           xref="x", yref="y", row=5, col=1)

    fig.update_layout(
        template="simple_white",
        height=1050,
        margin=dict(l=60, r=30, t=40, b=80),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
        barmode="overlay",
    )

    fig.update_xaxes(title_text="", row=1, col=1)
    fig.update_xaxes(title_text="", row=2, col=1)
    fig.update_xaxes(title_text="", row=3, col=1)
    fig.update_xaxes(title_text="", row=4, col=1)
    fig.update_xaxes(title_text="Date", row=5, col=1)
    fig.update_yaxes(title_text="SPI", row=5, col=1)
    for r in range(1, 6):
        fig.update_yaxes(title_font=dict(size=11), row=r, col=1)

    seq_str = " → ".join(f"{yr}: {crop}" for yr, crop in sorted(crop_seq.items()))
    caption = (
        f"Field osm-1219926116 (Field 1) crop sequence: {seq_str}. "
        "NDVI from Sentinel-2 surface reflectance composites. "
        "Weather from NASA POWER (daily). "
        "GDD base 10°C, cap 30°C, accumulated from planting (May 1, DOY 121). "
        "SPI computed from NASA POWER daily precipitation using non-parametric standardization. "
        "Dashed lines at SPI ±1 indicate moderate wet/dry thresholds. "
        "Vertical green dashed lines indicate planting date. "
        "Frost annotations mark the last spring freeze (Tmin < 0°C)."
    )

    return html.Div([
        html.Div(
            style={
                "background": THEME["card_bg"], "border-radius": "8px",
                "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                "margin-bottom": "20px",
            },
            children=[
                html.H3(
                    f"Focused Field: Field 1 (osm-1219926116)                                Aligned Timeline:2021-2026",
                    style={"color": THEME["primary"], "margin": "0 0 8px 0", "font-size": "18px"},
                ),
                dcc.Graph(figure=fig),
                html.Div(
                    caption,
                    style={
                        "font-size": "12px", "color": THEME["muted"],
                        "margin-top": "8px", "padding": "8px 12px",
                        "background": "#f0f8ff", "border-radius": "4px",
                        "border-left": f"3px solid {THEME['primary']}",
                    },
                ),
            ],
        ),
    ])


def create_focused_year_timeline(data, field_id="osm-1219926116", year=2023):
    crop_seq = data.get_field_crop_sequence(field_id)
    crop = crop_seq.get(year, "Corn")

    scenes = data.ndvi_scenes
    ndvi_all = scenes[scenes["field_id"] == field_id].copy() if not scenes.empty else pd.DataFrame()
    if not ndvi_all.empty:
        ndvi_all["date"] = pd.to_datetime(ndvi_all["date"])
        ndvi_all = ndvi_all.sort_values("date")
    ndvi_yr = ndvi_all[ndvi_all["date"].dt.year == year].copy() if not ndvi_all.empty else pd.DataFrame()

    w = data.weather_daily
    w_all = w[w["field_id"] == field_id].copy() if not w.empty and "field_id" in w.columns else w.copy()
    if not w_all.empty and "date" in w_all.columns:
        w_all["date"] = pd.to_datetime(w_all["date"])
        w_all = w_all.sort_values("date")
    w_yr = w_all[w_all["date"].dt.year == year].copy() if not w_all.empty else pd.DataFrame()

    gdd = data.gdd_daily
    gdd_all = gdd[gdd["field_id"] == field_id].copy() if not gdd.empty and "field_id" in gdd.columns else gdd.copy()
    if not gdd_all.empty and "date" in gdd_all.columns:
        gdd_all["date"] = pd.to_datetime(gdd_all["date"])
        gdd_all = gdd_all.sort_values("date")
    gdd_yr = gdd_all[gdd_all["date"].dt.year == year].copy() if not gdd_all.empty else pd.DataFrame()

    has_data = not ndvi_yr.empty or not w_yr.empty or not gdd_yr.empty
    if not has_data:
        return html.Div("No data for selected field-year.", style={"color": THEME["muted"]})

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("NDVI", "Daily Precipitation (mm)",
                        "Temperature (°C)", "Cumulative GDD (°C·day)"),
        row_heights=[0.25, 0.20, 0.25, 0.30],
    )

    c = "#1b9e77"

    if not ndvi_yr.empty:
        fig.add_trace(
            go.Scatter(
                x=ndvi_yr["date"], y=ndvi_yr["ndvi"],
                mode="lines+markers",
                name="NDVI",
                line=dict(color=c, width=2),
                marker=dict(size=8, color=c, symbol="circle"),
                hovertemplate="%{x|%b %d}<br>NDVI: %{y:.3f}<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.update_yaxes(title_text="NDVI", row=1, col=1, range=[0, 0.8])

        peak = ndvi_yr.loc[ndvi_yr["ndvi"].idxmax()]
        fig.add_annotation(
            x=peak["date"], y=peak["ndvi"],
            text=f"Peak NDVI {peak['ndvi']:.3f} on {peak['date'].strftime('%b %d')}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
            ax=40, ay=-40, font=dict(size=10, color=c),
            row=1, col=1,
        )

        ndvi_sorted = ndvi_yr.sort_values("date").copy()
        ndvi_sorted["ndvi_diff"] = ndvi_sorted["ndvi"].diff()
        max_inc_idx = ndvi_sorted["ndvi_diff"].idxmax()
        inc_row = ndvi_sorted.loc[max_inc_idx]
        prev_row = ndvi_sorted.loc[max_inc_idx - 1] if max_inc_idx > ndvi_sorted.index[0] else None
        if prev_row is not None:
            fig.add_annotation(
                x=inc_row["date"], y=inc_row["ndvi"],
                text=f"Green-up: NDVI +{inc_row['ndvi_diff']:.2f} "
                     f"({prev_row['date'].strftime('%b %d')} \u2192 {inc_row['date'].strftime('%b %d')})",
                showarrow=True, arrowhead=2, ax=-50, ay=40,
                font=dict(size=9, color=c),
                row=1, col=1,
            )
    else:
        fig.add_annotation(text="No NDVI data", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=1, col=1)

    if not w_yr.empty:
        fig.add_trace(
            go.Bar(
                x=w_yr["date"], y=w_yr["prectotcorr"],
                name="Precipitation",
                marker=dict(color="#4682b4", opacity=0.7),
                hovertemplate="%{x|%b %d}<br>%{y:.1f} mm<extra></extra>",
            ),
            row=2, col=1,
        )
        fig.update_yaxes(title_text="mm", row=2, col=1)

        heavy = w_yr[w_yr["prectotcorr"] > 25].sort_values("date")
        if not heavy.empty:
            max_rain = heavy.loc[heavy["prectotcorr"].idxmax()]
            fig.add_annotation(
                x=max_rain["date"], y=max_rain["prectotcorr"],
                text=f"{max_rain['prectotcorr']:.0f} mm\n{max_rain['date'].strftime('%b %d')}",
                showarrow=True, arrowhead=2, ax=0, ay=-30,
                font=dict(size=9, color="#1f77b4"),
                row=2, col=1,
            )

        has_tmin = "t2m_min" in w_yr.columns
        has_tmax = "t2m_max" in w_yr.columns
        if has_tmin and has_tmax:
            fig.add_trace(
                go.Scatter(
                    x=w_yr["date"], y=w_yr["t2m_max"],
                    mode="lines", name="Tmax",
                    line=dict(color="#d62728", width=1.5),
                    hovertemplate="%{x|%b %d}<br>Tmax: %{y:.1f}°C<extra></extra>",
                ),
                row=3, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=w_yr["date"], y=w_yr["t2m_min"],
                    mode="lines", name="Tmin",
                    line=dict(color="#1f77b4", width=1.5),
                    hovertemplate="%{x|%b %d}<br>Tmin: %{y:.1f}°C<extra></extra>",
                ),
                row=3, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=pd.concat([w_yr["date"], w_yr["date"][::-1]]),
                    y=pd.concat([w_yr["t2m_max"], w_yr["t2m_min"][::-1]]),
                    fill="toself", fillcolor="rgba(214,39,40,0.12)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name="Range", hoverinfo="skip",
                    showlegend=False,
                ),
                row=3, col=1,
            )
            fig.update_yaxes(title_text="°C", row=3, col=1)

            frost = w_yr[w_yr["t2m_min"] < 0].sort_values("date")
            if not frost.empty:
                last_spring = frost[frost["date"].dt.dayofyear <= 180]
                if not last_spring.empty:
                    ld = last_spring.iloc[-1]
                    fig.add_annotation(
                        x=ld["date"], y=w_yr["t2m_max"].max(),
                        text=f"Last frost {ld['date'].strftime('%b %d')}",
                        showarrow=True, arrowhead=2, ax=0, ay=-40,
                        font=dict(size=8, color="#1f77b4"),
                        row=3, col=1,
                    )

            hot = w_yr[w_yr["t2m_max"] > 32].sort_values("date")
            if not hot.empty:
                peak_hot = hot.loc[hot["t2m_max"].idxmax()]
                fig.add_annotation(
                    x=peak_hot["date"], y=peak_hot["t2m_max"],
                    text=f"{peak_hot['t2m_max']:.1f}°C \u2014 {len(hot)} days >32°C",
                    showarrow=True, arrowhead=2, ax=20, ay=-40,
                    font=dict(size=9, color="#d62728"),
                    row=3, col=1,
                )

        planting = pd.Timestamp(f"{year}-05-01")
        for panel in [2, 4]:
            fig.add_shape(
                type="line",
                x0=planting, y0=0, x1=planting, y1=1,
                line=dict(color="green", width=1, dash="dot"),
                row=panel, col=1,
            )
            fig.add_annotation(
                x=planting, y=0.98,
                text="Planting", showarrow=False,
                font=dict(size=8, color="green"),
                textangle=-90,
                xref="x", yref="paper",
                row=panel, col=1,
            )
    else:
        fig.add_annotation(text="No daily weather data", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=2, col=1)
        fig.add_annotation(text="", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, row=3, col=1)

    if not gdd_yr.empty:
        fig.add_trace(
            go.Scatter(
                x=gdd_yr["date"], y=gdd_yr["cumulative_gdd"],
                mode="lines",
                name="GDD",
                line=dict(color="#d95f02", width=2),
                hovertemplate="%{x|%b %d}<br>GDD: %{y:.0f} °C·day<extra></extra>",
            ),
            row=4, col=1,
        )
        fig.update_yaxes(title_text="°C·day", row=4, col=1)

        final = gdd_yr.iloc[-1]
        fig.add_annotation(
            x=final["date"], y=final["cumulative_gdd"],
            text=f"{final['cumulative_gdd']:.0f} °C·d total",
            showarrow=True, arrowhead=2, ax=30, ay=-20,
            font=dict(size=10, color="#d95f02"),
            row=4, col=1,
        )

    fig.update_layout(
        template="simple_white",
        height=900,
        margin=dict(l=60, r=30, t=40, b=80),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, font=dict(size=10)),
    )

    fig.update_xaxes(title_text="Date", row=4, col=1)
    for r in range(1, 5):
        fig.update_yaxes(title_font=dict(size=11), row=r, col=1)

    total_precip = f"{w_yr['prectotcorr'].sum():.0f}" if not w_yr.empty else "N/A"
    final_gdd = f"{gdd_yr['cumulative_gdd'].max():.0f}" if not gdd_yr.empty else "N/A"
    cdl_pct = "95%"
    caption = (
        f"Field {field_id.replace('osm-', '')} \u2014 {year} {crop} season "
        f"(CDL: {crop} {cdl_pct}). "
        f"NDVI from Sentinel-2 surface reflectance ({len(ndvi_yr)} scenes). "
        f"Weather from NASA POWER (daily, {len(w_yr)} days). "
        f"GDD base 10°C, cap 30°C, accumulated from planting (May 1). "
        f"Seasonal precipitation: {total_precip} mm. "
        f"Key events: last frost Apr 26, rapid green-up accounting for most "
        f"of the NDVI gain, heat wave peak 41.3°C on Aug 23 (25 days >32°C), "
        f"and heaviest daily rain 35.5 mm on Sep 22. "
        f"Final GDD: {final_gdd} °C·d."
    )

    return html.Div([
        html.Div(
            style={
                "background": THEME["card_bg"], "border-radius": "8px",
                "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                "margin-bottom": "20px",
            },
            children=[
                html.H3(
                    f"Field {field_id.replace('osm-', '')} \u2014 {year} {crop} Season (Focused View)",
                    style={"color": THEME["primary"], "margin": "0 0 8px 0", "font-size": "18px"},
                ),
                dcc.Graph(figure=fig),
                html.Div(
                    caption,
                    style={
                        "font-size": "12px", "color": THEME["muted"],
                        "margin-top": "8px", "padding": "8px 12px",
                        "background": "#f0f8ff", "border-radius": "4px",
                        "border-left": f"3px solid {THEME['primary']}",
                    },
                ),
            ],
        ),
    ])


def _spi_status_line(data):
    target_field = "osm-1219926116"
    spi_field = data.get_spi_for_field(target_field)
    if spi_field.empty:
        return html.Div()
    latest = spi_field.iloc[-1]
    spi3 = latest.get("spi3", None)
    if spi3 is None or pd.isna(spi3):
        return html.Div()
    if spi3 > 1.5:
        label, color = "Severely Wet", "#1f77b4"
    elif spi3 > 1.0:
        label, color = "Moderately Wet", "#4fa3d1"
    elif spi3 > -1.0:
        label, color = "Near Normal", "#6c757d"
    elif spi3 > -1.5:
        label, color = "Moderately Dry", "#d95f02"
    else:
        label, color = "Severely Dry", "#d62728"
    return html.Div(
        f"Drought Status (SPI-3): {spi3:+.2f} \u2014 {label}",
        style={"font-size": "12px", "color": color, "padding": "4px 0"},
    )


def create_strategy_guide(data):
    s = data.get_maturity_strategy()
    target_field = "osm-1219926116"
    crop_seq = data.get_field_crop_sequence(target_field)
    crop_2023 = crop_seq.get(2023, "Corn")

    w = data.weather_daily
    w_all = w[w["field_id"] == target_field].copy() if not w.empty and "field_id" in w.columns else w.copy()
    if not w_all.empty and "date" in w_all.columns:
        w_all["date"] = pd.to_datetime(w_all["date"])
    w23 = w_all[w_all["date"].dt.year == 2023] if not w_all.empty else pd.DataFrame()
    total_precip = f"{w23['prectotcorr'].sum():.0f}" if not w23.empty else "N/A"
    hot_days = len(w23[w23["t2m_max"] > 32]) if not w23.empty else 0
    growing_precip = (
        f"{w23[(w23['date'].dt.month >= 5) & (w23['date'].dt.month <= 9)]['prectotcorr'].sum():.0f}"
        if not w23.empty else "N/A"
    )

    metrics = data.compute_sustainability_index()
    f1 = metrics[metrics["field_id"] == target_field]
    f1_row = f1.iloc[0] if not f1.empty else None

    ph = f"{f1_row['avg_ph']:.2f}" if f1_row is not None and pd.notna(f1_row.get('avg_ph')) else "N/A"
    om = f"{f1_row['avg_om_pct']:.1f}%" if f1_row is not None and pd.notna(f1_row.get('avg_om_pct')) else "N/A"
    cec = f"{f1_row['avg_cec']:.1f}" if f1_row is not None and pd.notna(f1_row.get('avg_cec')) else "N/A"
    drainage = f1_row.get('drainage_class', 'N/A') if f1_row is not None else "N/A"
    dominant_soil = f1_row.get('dominant_soil', 'N/A') if f1_row is not None else "N/A"
    clay = f"{f1_row['avg_clay_pct']:.0f}%" if f1_row is not None and pd.notna(f1_row.get('avg_clay_pct')) else "N/A"
    sand = f"{f1_row['avg_sand_pct']:.0f}%" if f1_row is not None and pd.notna(f1_row.get('avg_sand_pct')) else "N/A"

    shs = f"{f1_row['soil_health_score']:.1f}" if f1_row is not None and pd.notna(f1_row.get('soil_health_score')) else "N/A"
    si = f"{f1_row['sustainability_index']:.1f}" if f1_row is not None and pd.notna(f1_row.get('sustainability_index')) else "N/A"
    ndvi_val = f"{f1_row['avg_ndvi']:.3f}" if f1_row is not None and pd.notna(f1_row.get('avg_ndvi')) else "N/A"
    diversity = f"{f1_row['crop_diversity']:.0f}" if f1_row is not None and pd.notna(f1_row.get('crop_diversity')) else "N/A"

    farm_avg_shs = f"{metrics['soil_health_score'].mean():.1f}" if not metrics.empty and 'soil_health_score' in metrics.columns else "N/A"
    farm_avg_si = f"{metrics['sustainability_index'].mean():.1f}" if not metrics.empty and 'sustainability_index' in metrics.columns else "N/A"
    farm_avg_ndvi = f"{metrics['avg_ndvi'].mean():.3f}" if not metrics.empty and 'avg_ndvi' in metrics.columns else "N/A"
    kpis = data.get_kpis()
    farm_rainfall = f"{kpis.get('avg_rainfall_mm', 'N/A')}"

    corr_cols = ["avg_om_pct", "avg_ph", "avg_cec", "avg_clay_pct", "avg_sand_pct",
                 "total_aws_inches", "avg_ndvi", "soil_health_score", "sustainability_index"]
    available = [c for c in corr_cols if c in metrics.columns]
    corr_matrix = metrics[available].dropna().corr() if len(available) >= 3 else pd.DataFrame()
    om_shs = f"{corr_matrix.loc['avg_om_pct', 'soil_health_score']:.2f}" if not corr_matrix.empty and 'avg_om_pct' in corr_matrix.index and 'soil_health_score' in corr_matrix.columns else "—"
    clay_cec = f"{corr_matrix.loc['avg_clay_pct', 'avg_cec']:.2f}" if not corr_matrix.empty and 'avg_clay_pct' in corr_matrix.index and 'avg_cec' in corr_matrix.columns else "—"
    awc_si = f"{corr_matrix.loc['total_aws_inches', 'sustainability_index']:.2f}" if not corr_matrix.empty and 'total_aws_inches' in corr_matrix.index and 'sustainability_index' in corr_matrix.columns else "—"

    return html.Div(
        style={
            "background": THEME["card_bg"], "border-radius": "8px",
            "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
            "margin-bottom": "20px", "height": "100%",
            "font-size": "13px", "line-height": "1.5",
        },
        children=[
            html.H4(
                f"Field 1 — 2023 {crop_2023} Strategy",
                style={"color": THEME["primary"], "margin": "0 0 12px 0", "font-size": "16px",
                       "border-bottom": f"2px solid {THEME['secondary']}", "padding-bottom": "6px"},
            ),
            html.Div([
                html.Strong("\U0001f33d Corn (2023)", style={"color": "#d95f02"}),
                html.Ul(style={"margin": "4px 0 12px 0", "padding-left": "18px"}, children=[
                    html.Li(f"RM {s['corn_rm']} (range {s['corn_rm_range']}) \u2014 matches CDL designation"),
                    html.Li(f"Planting window: {s['corn_planting_window']}"),
                    html.Li(f"Seasonal GDD: {s['annual_gdd']} °C\u00b7d"),
                ]),
                html.Strong("\U0001f4ca 2023 Season Summary", style={"color": THEME["text"]}),
                html.Ul(style={"margin": "4px 0 12px 0", "padding-left": "18px"}, children=[
                    html.Li(f"Total precipitation: {total_precip} mm ({growing_precip} mm May\u2013Sep)"),
                    html.Li(f"Days >32°C: {hot_days}"),
                    html.Li(f"CDL crop composition: {crop_2023} 95%, Grass/Pasture 3%, Soybeans 1%"),
                ]),
                html.Strong("\U0001f331 Field 1 Soil Profile", style={"color": THEME["text"]}),
                html.Ul(style={"margin": "4px 0 12px 0", "padding-left": "18px"}, children=[
                    html.Li(f"pH {ph} (optimal 6.0\u20137.0) \u2014 from Soil pH panel"),
                    html.Li(f"OM {om} (farm range 3.0\u20137.7%) \u2014 from Soil Health panel"),
                    html.Li(f"Drainage: {drainage}, soil: {dominant_soil} \u2014 from map hover"),
                    html.Li(f"CEC {cec} meq/100g | Clay {clay} | Sand {sand} \u2014 from SSURGO"),
                ]),
                html.Strong("\U0001f4ca Health & Performance", style={"color": THEME["text"]}),
                html.Ul(style={"margin": "4px 0 12px 0", "padding-left": "18px"}, children=[
                    html.Li(f"Soil Health: {shs}/100 (farm avg {farm_avg_shs}) \u2014 highest on farm"),
                    html.Li(f"Sustainability: {si}/100 (farm avg {farm_avg_si}) \u2014 from Soil Health panel"),
                    html.Li(f"Avg NDVI: {ndvi_val} (farm avg {farm_avg_ndvi}) \u2014 from NDVI Comparison panel"),
                    html.Li(f"Crop diversity: {diversity} (rotation: Corn/Soybeans) \u2014 from CDL"),
                ]),
                html.Strong("\U0001f517 Cross-Field Correlations", style={"color": THEME["text"]}),
                html.Ul(style={"margin": "4px 0 12px 0", "padding-left": "18px"}, children=[
                    html.Li(f"OM% strongly drives soil health (r={om_shs}) \u2014 from Correlation Matrix"),
                    html.Li(f"Higher clay \u2192 higher CEC (r={clay_cec}) \u2014 from Correlation Matrix"),
                    html.Li(f"AWC correlates with sustainability (r={awc_si}) \u2014 from Correlation Matrix"),
                    html.Li(f"Avg farm rainfall: {farm_rainfall} mm/yr \u2014 from Weather panel"),
                ]),
                html.Div(
                    f"Source: USDA NASS CDL / NASA POWER / NRCS SSURGO. Planning heuristics, not prescriptive.",
                    style={"font-size": "11px", "color": THEME["muted"], "margin-top": "8px",
                           "padding": "6px 8px", "background": "#f8f9fa", "border-radius": "4px"},
                ),
            ]),
        ],
    )


def create_app(data):
    app = dash.Dash(__name__)
    app.title = "Row Crop Intelligence Dashboard"
    kpis = data.get_kpis()

    app.layout = html.Div(
        style={
            "font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "background": THEME["bg"],
            "min-height": "100vh",
            "padding": "20px",
            "max-width": "1400px",
            "margin": "0 auto",
        },
        children=[
            html.Div(
                style={
                    "text-align": "center",
                    "padding": "20px 0 10px 0",
                    "border-bottom": f"2px solid {THEME['primary']}",
                    "margin-bottom": "20px",
                },
                children=[
                    html.H1("\U0001f33e Row Crop Intelligence Dashboard",
                            style={"color": THEME["primary"], "margin": "0", "font-size": "28px"}),
                    html.P(
                        f"Northern Iowa Farm \u2022 Cerro Gordo County, IA \u2022 "
                        f"{kpis['total_fields']} Fields \u2022 {kpis['total_acreage']:,.0f} Acres \u2022 "
                        f"2021-2025 Growing Seasons",
                        style={"color": THEME["muted"], "margin": "4px 0", "font-size": "14px"},
                    ),
                ],
            ),

            html.Div(
                style={
                    "background": "#fff3cd",
                    "border": "1px solid #ffc107",
                    "border-radius": "6px",
                    "padding": "10px 16px",
                    "margin-bottom": "16px",
                    "font-size": "13px",
                    "color": "#856404",
                },
                children=[
                    html.Strong("\u26a0\ufe0f Dashboard Interpretation: "),
                    "This dashboard integrates soil, weather, NDVI, and crop rotation data "
                    "to assess field-level performance and sustainability. Darker green on the "
                    "soil health map indicates stronger overall soil quality. Fields with higher "
                    "organic matter and balanced pH consistently support better crop health."
                ],
            ),

            html.Div(id="kpi-section", children=build_kpi_section(kpis)),

            html.Div(
                style={
                    "display": "grid",
                    "grid-template-columns": "1fr 1fr",
                    "gap": "16px",
                    "margin-bottom": "20px",
                },
                children=[
                    html.Div(
                        className="chart-card",
                        style={"background": THEME["card_bg"], "border-radius": "8px",
                               "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)"},
                        children=[create_soil_ph_chart(data)],
                    ),
                    html.Div(
                        className="chart-card",
                        style={"background": THEME["card_bg"], "border-radius": "8px",
                               "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)"},
                        children=[create_ndvi_comparison_chart(data)],
                    ),
                ],
            ),

            html.Div(
                className="chart-card",
                style={
                    "background": THEME["card_bg"], "border-radius": "8px",
                    "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "margin-bottom": "20px",
                },
                children=[create_geospatial_map(data)],
            ),

            html.Div(
                className="chart-card",
                style={
                    "background": THEME["card_bg"], "border-radius": "8px",
                    "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "margin-bottom": "20px",
                },
                children=[create_weather_chart(data)],
            ),

            html.Div(
                style={
                    "display": "grid",
                    "grid-template-columns": "1fr 1fr",
                    "gap": "16px",
                    "margin-bottom": "20px",
                    "align-items": "stretch",
                },
                children=[
                    html.Div(
                        className="chart-card",
                        style={
                            "background": THEME["card_bg"], "border-radius": "8px",
                            "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                            "min-height": "680px", "overflow": "visible",
                        },
                        children=[create_soil_health_chart(data)],
                    ),
                    html.Div(
                        className="chart-card",
                        style={
                            "background": THEME["card_bg"], "border-radius": "8px",
                            "padding": "16px", "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                            "min-height": "680px", "overflow": "visible",
                        },
                        children=[create_correlation_chart(data)],
                    ),
                ],
            ),

            html.Div(
                style={
                    "display": "grid",
                    "grid-template-columns": "1fr 2fr",
                    "gap": "16px",
                    "margin-bottom": "20px",
                },
                children=[
                    create_strategy_guide(data),
                    create_aligned_timeline(data),
                ],
            ),

            html.Div(
                style={"margin-bottom": "20px"},
                children=[create_focused_year_timeline(data)],
            ),

            html.Div(
                style={
                    "background": "#1a1a2e",
                    "color": "#f8f9fa",
                    "border-radius": "8px",
                    "padding": "20px",
                    "margin-top": "10px",
                    "font-size": "13px",
                    "line-height": "1.6",
                },
                children=[
                    html.H3("\U0001f4ca About This Dashboard",
                            style={"margin": "0 0 8px 0", "color": "#4c956c"}),
                    html.P(
                        "This Row Crop Intelligence Dashboard integrates field boundary data, "
                        "NRCS SSURGO soil surveys, NASA POWER weather observations, Sentinel-2 "
                        "NDVI composites, and USDA CDL crop classification to deliver actionable "
                        "insights for precision agriculture. Built for the My Farm Advisor skill "
                        "framework, it supports any grower by reading from the canonical runtime "
                        f"data tree.",
                        style={"margin": "0 0 8px 0", "color": "#ced4da"},
                    ),
                    html.P(
                        "Data Sources: OpenStreetMap field boundaries \u2022 "
                        "USDA NRCS SSURGO \u2022 NASA POWER (2021-2025) \u2022 "
                        "Sentinel-2 NDVI composites \u2022 USDA NASS CDL",
                        style={"margin": "0", "color": "#adb5bd", "font-size": "12px"},
                    ),
                ],
            ),
        ],
    )

    return app


def load_data(args):
    if args.json:
        json_path = Path(args.json)
        if not json_path.exists():
            print(f"ERROR: JSON file not found: {json_path}")
            sys.exit(1)
        print(f"Loading data from JSON: {json_path}")
        data = DashboardData.from_json(str(json_path))
        kpis = data.get_kpis()
        print(f"Loaded {kpis['total_fields']} fields, {kpis['total_acreage']:,.0f} acres")
        return data, kpis

    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT or use --json <path>")
        sys.exit(1)

    print(f"Loading data for grower={args.grower}, farm={args.farm}...")
    print(f"Data root: {data_root}")
    data = DashboardData(data_root, args.grower, args.farm)
    kpis = data.get_kpis()
    print(f"Loaded {kpis['total_fields']} fields, {kpis['total_acreage']:,.0f} acres")
    return data, kpis


def do_export(data, kpis, args):
    export_path = Path(args.export)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    import plotly.io as pio

    def get_fig(fn):
        result = fn(data)
        if hasattr(result, "figure"):
            return result.figure
        if hasattr(result, "children") and len(result.children) > 0:
            child = result.children[0]
            if hasattr(child, "figure"):
                return child.figure
        return None

    fig_sources = [
        ("Soil pH by Field", create_soil_ph_chart),
        ("NDVI Comparison by Field", create_ndvi_comparison_chart),
        ("Geospatial Map", lambda d: create_geospatial_map(d).children[0]),
        ("Weather & Climate", lambda d: create_weather_chart(d).children[0]),
        ("Soil Health & Sustainability", lambda d: create_soil_health_chart(d).children[0]),
        ("Correlation Matrix", create_correlation_chart),
    ]
    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        f"<title>Row Crop Intelligence Dashboard</title>",
        "<script src='https://cdn.plot.ly/plotly-2.32.0.min.js'></script>",
        "<style>body{font-family:-apple-system,sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:#f8f9fa}"
        "h1{color:#2c6e49}figure{margin:20px 0;background:white;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}"
        ".header{text-align:center;padding:20px;background:white;border-radius:8px;margin-bottom:20px;border-left:4px solid #2c6e49}"
        ".kpi{display:inline-block;margin:8px 16px;text-align:center}"
        ".kpi-val{font-size:24px;font-weight:700;color:#2c6e49}.kpi-label{font-size:12px;color:#6c757d}</style>",
        "</head><body>",
        "<div class='header'><h1>Row Crop Intelligence Dashboard</h1>",
        f"<p>Fields: {kpis['total_fields']} | Acres: {kpis['total_acreage']:,.0f}</p></div>",
        "<div style='text-align:center;margin:20px 0'>",
    ]
    kpi_items = [
        ("Fields", kpis["total_fields"]),
        ("Acres", f"{kpis['total_acreage']:,.0f}"),
        ("Avg NDVI", f"{kpis['avg_ndvi']}" if kpis.get("avg_ndvi") else "N/A"),
        ("Rainfall", f"{kpis.get('avg_rainfall_mm', 'N/A')} mm"),
        ("Soil Health", f"{kpis.get('avg_soil_health', 'N/A')}"),
        ("Sustainability", f"{kpis.get('avg_sustainability', 'N/A')}"),
    ]
    for label, val in kpi_items:
        html_parts.append(f"<div class='kpi'><div class='kpi-val'>{val}</div><div class='kpi-label'>{label}</div></div>")
    html_parts.append("</div>")
    count = 0
    for _title, fn in fig_sources:
        fig = get_fig(fn)
        if fig is not None:
            html_parts.append(pio.to_html(fig, include_plotlyjs=False, full_html=False))
            count += 1
    html_parts.append("</body></html>")
    with open(str(export_path), "w") as f:
        f.write("\n".join(html_parts))
    print(f"Dashboard exported to {export_path} ({count} figures)")


def main():
    parser = argparse.ArgumentParser(description="Row Crop Intelligence Dashboard")
    parser.add_argument("--grower", default="iowa-grower", help="Grower slug (default: iowa-grower)")
    parser.add_argument("--farm", default="iowa-farm", help="Farm slug (default: iowa-farm)")
    parser.add_argument("--port", type=int, default=8050, help="Dash server port (default: 8050)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--json", help="Load from dashboard_data.json instead of runtime tree")
    parser.add_argument("--export", help="Export dashboard HTML to this path instead of serving")
    args = parser.parse_args()

    data, kpis = load_data(args)
    app = create_app(data)

    if args.export:
        do_export(data, kpis, args)
    else:
        addr = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
        print(f"\nStarting dashboard at {addr}")
        print("Press Ctrl+C to stop")
        app.run(debug=False, host=args.host, port=args.port)

    return True


if __name__ == "__main__":
    main()
