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
        yref="paper", y=1.0,
        text="Optimal max (7.0)",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color=THEME["ok"]),
    )
    fig.add_annotation(
        xref="paper", x=1.0,
        yref="paper", y=0.95,
        text="Optimal min (6.0)",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=10, color=THEME["ok"]),
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
            fillcolor="rgba(0,0,0,0)",
            line=dict(width=2, color="orange"),
            name=gdf_web.iloc[i]["short_id"] if i < len(gdf_web) else f"Field {i}",
            hovertext=text[i] if i < len(text) else "",
            hoverinfo="text",
            showlegend=False,
        ))

    scatter_lons = []
    scatter_lats = []
    scatter_colors = []
    scatter_text = []
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

    fig.add_trace(go.Scattermap(
        lon=scatter_lons,
        lat=scatter_lats,
        mode="markers",
        marker=dict(
            size=30,
            color=scatter_colors,
            colorscale="Greens",
            cmin=40,
            cmax=100,
            colorbar=dict(title="Soil<br>Health<br>Score", thickness=15, len=0.5),
        ),
        text=scatter_text,
        hoverinfo="text",
        showlegend=False,
    ))

    bounds = gdf_web.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    fig.update_layout(
        title="Field Boundaries by Soil Health Score",
        map=dict(
            style="open-street-map",
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
