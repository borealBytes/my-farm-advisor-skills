#!/usr/bin/env python3
import os
import sys
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from dashboard_utils import DashboardData

import dash
from dash import html, dcc

THEME = {
    "bg": "#f8f9fa",
    "card_bg": "#ffffff",
    "primary": "#2c6e49",
    "secondary": "#4c956c",
    "accent": "#fefee3",
    "text": "#1a1a2e",
    "muted": "#6c757d",
    "border": "#dee2e6",
}

FIELD_NUMBER = "1"
FIELD_DISPLAY = f"Field {FIELD_NUMBER} (osm-1219926116)"


def annotation_box(text, color="#2c6e49"):
    return html.Div(
        style={
            "background": "#f0f7f0",
            "border-left": f"4px solid {color}",
            "padding": "10px 14px",
            "margin": "8px 0 0 0",
            "border-radius": "4px",
            "font-size": "13px",
            "color": THEME["text"],
            "line-height": "1.5",
        },
        children=[html.Span("\U0001f4ca ", style={"font-size": "14px"}), text],
    )


def build_aligned_dashboard(data):
    fid = data.field_ids[0] if data.field_ids else "osm-1219926116"
    ndvi = data.ndvi_scenes
    weather = data.weather
    gdd = data.gdd_daily
    crop_seq = data.get_field_crop_sequence(fid)

    if ndvi.empty and weather.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=600)
        return dcc.Graph(figure=fig), "No data available."

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            f"NDVI Accumulation — {FIELD_DISPLAY}",
            "Daily Precipitation",
            "Temperature Extremes (Tmin / Tavg / Tmax)",
            "Cumulative Growing Degree Days (GDD, base 10°C)",
        ),
        row_heights=[0.30, 0.20, 0.25, 0.25],
    )

    year_colors = {2021: "#1f77b4", 2022: "#ff7f0e", 2023: "#2ca02c",
                   2024: "#d62728", 2025: "#9467bd"}
    year_crop_labels = {}
    for yr_str, crop in crop_seq.items():
        year_crop_labels[int(yr_str)] = crop

    captions = []

    if not ndvi.empty:
        ndvi_fid = ndvi[ndvi["field_id"] == fid] if "field_id" in ndvi.columns else ndvi
        for yr in sorted(ndvi_fid["year"].unique()):
            sub = ndvi_fid[ndvi_fid["year"] == yr].sort_values("date")
            color = year_colors.get(yr, "#333")
            crop = year_crop_labels.get(yr, "")
            label = f"{yr} ({crop})" if crop else str(yr)
            fig.add_trace(
                go.Scatter(
                    x=sub["date"], y=sub["ndvi"],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=color, width=2),
                    marker=dict(size=6, color=color, symbol="circle"),
                    hovertemplate=f"{yr} {crop}<br>Date: %{{x|%b %d}}<br>NDVI: %{{y:.3f}}<extra></extra>",
                ),
                row=1, col=1,
            )
        all_vals = ndvi_fid["ndvi"].dropna()
        if len(all_vals) > 0:
            peak_ndvi = all_vals.max()
            peak_row = ndvi_fid.loc[ndvi_fid["ndvi"].idxmax()]
            peak_date = peak_row["date"]
            peak_yr = peak_row["year"]
            peak_crop = year_crop_labels.get(peak_yr, "")
            avg_ndvi = all_vals.mean()
            captions.append(
                f"Peak NDVI of {peak_ndvi:.3f} recorded on {pd.Timestamp(peak_date).strftime('%b %d, %Y')} "
                f"({peak_yr} {peak_crop}). 5-year mean NDVI: {avg_ndvi:.3f}."
            )

    if not weather.empty:
        w = weather.copy()
        if "field_id" in w.columns:
            w = w[w["field_id"] == fid]
        w = w.sort_values("date")
        w_clean = w.dropna(subset=["prectotcorr"])

        fig.add_trace(
            go.Bar(
                x=w_clean["date"], y=w_clean["prectotcorr"],
                marker=dict(color="#0077b6", opacity=0.6),
                name="Precipitation",
                hovertemplate="Date: %{x|%b %d, %Y}<br>Precip: %{y:.1f} mm<extra></extra>",
            ),
            row=2, col=1,
        )
        yr_precip = w_clean.groupby(w_clean["date"].dt.year)["prectotcorr"].sum()
        avg_precip = yr_precip.mean()
        max_precip_yr = yr_precip.idxmax()
        captions.append(
            f"Mean annual precipitation: {avg_precip:.0f} mm. "
            f"Wettest year: {int(max_precip_yr)} ({yr_precip.max():.0f} mm)."
        )

    if not weather.empty and all(c in weather.columns for c in ["t2m_min", "t2m_max", "t2m"]):
        w_temp = weather.copy()
        if "field_id" in w_temp.columns:
            w_temp = w_temp[w_temp["field_id"] == fid]
        w_temp = w_temp.sort_values("date").dropna(subset=["t2m_min", "t2m_max", "t2m"])

        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m_max"],
                mode="lines",
                name="Tmax",
                line=dict(color="#dc3545", width=1.5),
                hovertemplate="Max: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m_min"],
                mode="lines",
                name="Tmin",
                line=dict(color="#1b4965", width=1.5),
                fill=None,
                hovertemplate="Min: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m"],
                mode="lines",
                name="Tavg",
                line=dict(color="#2c6e49", width=2, dash="dash"),
                hovertemplate="Avg: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=pd.concat([w_temp["date"], w_temp["date"][::-1]]),
                y=pd.concat([w_temp["t2m_max"], w_temp["t2m_min"][::-1]]),
                fill="toself",
                fillcolor="rgba(220, 53, 69, 0.08)",
                line=dict(width=0),
                name="Range",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=3, col=1,
        )

        avg_max = w_temp["t2m_max"].mean()
        avg_min = w_temp["t2m_min"].mean()
        hottest_idx = w_temp["t2m_max"].idxmax()
        hottest_row = w_temp.loc[hottest_idx]
        captions.append(
            f"Mean Tmax: {avg_max:.1f}°C, Mean Tmin: {avg_min:.1f}°C. "
            f"Hottest day: {pd.Timestamp(hottest_row['date']).strftime('%b %d, %Y')} "
            f"({hottest_row['t2m_max']:.1f}°C)."
        )

    if not gdd.empty:
        g = gdd.copy()
        if "field_id" in g.columns:
            g = g[g["field_id"] == fid]
        g = g.sort_values("date")
        g_season = g[g["season_gdd"] > 0]

        for yr in sorted(g_season["date"].dt.year.unique()):
            sub = g_season[g_season["date"].dt.year == yr]
            color = year_colors.get(yr, "#333")
            crop = year_crop_labels.get(yr, "")
            label = f"{yr} ({crop})" if crop else str(yr)
            fig.add_trace(
                go.Scatter(
                    x=sub["date"], y=sub["season_gdd"],
                    mode="lines",
                    name=label,
                    line=dict(color=color, width=2),
                    hovertemplate=f"{yr} {crop}<br>Date: %{{x|%b %d}}<br>GDD: %{{y:.0f}}<extra></extra>",
                ),
                row=4, col=1,
            )

        final_gdd = g_season.groupby(g_season["date"].dt.year)["season_gdd"].max()
        avg_gdd = final_gdd.mean()
        max_gdd_yr = final_gdd.idxmax()
        captions.append(
            f"Mean seasonal GDD (base 10°C): {avg_gdd:.0f}. "
            f"Highest GDD year: {int(max_gdd_yr)} ({final_gdd.max():.0f})."
        )

    fig.update_layout(
        title=dict(
            text=f"\U0001f33e Aligned Field Timeline — {FIELD_DISPLAY}<br>"
                 f"<span style='font-size:14px;color:{THEME['muted']};font-weight:400'>"
                 f"Northern Iowa Farm \u2022 Cerro Gordo County, IA \u2022 2021-2025</span>",
            font=dict(size=18, color=THEME["primary"]),
        ),
        template="simple_white",
        height=1000,
        hovermode="x unified",
        margin=dict(l=60, r=30, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
    )

    fig.update_xaxes(title_text="", row=1, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="", row=2, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="", row=3, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="Date", row=4, col=1, gridcolor="#eee")

    fig.update_yaxes(title_text="NDVI", row=1, col=1, gridcolor="#eee", rangemode="tozero")
    fig.update_yaxes(title_text="mm", row=2, col=1, gridcolor="#eee", rangemode="tozero")
    fig.update_yaxes(title_text="°C", row=3, col=1, gridcolor="#eee")
    fig.update_yaxes(title_text="GDD", row=4, col=1, gridcolor="#eee", rangemode="tozero")

    caption_text = " \u2022 ".join(captions) if captions else "All four panels share a common date axis (2021-2025). Hover over any point for details."

    return dcc.Graph(figure=fig), caption_text


def create_app(data):
    app = dash.Dash(__name__)
    app.title = "Row Crop Field Timeline Dashboard"

    fid = data.field_ids[0] if data.field_ids else "osm-1219926116"
    crop_seq = data.get_field_crop_sequence(fid)
    crop_str = "; ".join(f"{yr}: {info['crop_name']}" for yr, info in sorted(crop_seq.items()))

    graph, caption = build_aligned_dashboard(data)

    app.layout = html.Div(
        style={
            "font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "background": THEME["bg"],
            "min-height": "100vh",
            "padding": "20px",
            "max-width": "1200px",
            "margin": "0 auto",
        },
        children=[
            html.Div(
                style={
                    "background": THEME["card_bg"],
                    "border-radius": "8px",
                    "padding": "16px 20px",
                    "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "margin-bottom": "16px",
                    "display": "flex",
                    "justify-content": "space-between",
                    "align-items": "center",
                },
                children=[
                    html.Div([
                        html.H2("\U0001f33e Row Crop Field Timeline",
                                style={"margin": "0", "color": THEME["primary"], "font-size": "22px"}),
                        html.P(f"{FIELD_DISPLAY} \u2022 Cerro Gordo County, IA \u2022 2021-2025",
                               style={"margin": "2px 0 0 0", "color": THEME["muted"], "font-size": "13px"}),
                    ]),
                    html.Div(
                        style={"text-align": "right", "font-size": "12px", "color": THEME["muted"]},
                        children=[html.Div(f"Crop Rotation: {crop_str}")],
                    ),
                ],
            ),

            html.Div(
                className="chart-card",
                style={
                    "background": THEME["card_bg"],
                    "border-radius": "8px",
                    "padding": "16px",
                    "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                },
                children=[graph],
            ),

            annotation_box(caption),

            html.Div(
                style={
                    "background": THEME["card_bg"],
                    "border-radius": "8px",
                    "padding": "14px 18px",
                    "box-shadow": "0 1px 3px rgba(0,0,0,0.1)",
                    "margin-top": "16px",
                    "font-size": "12px",
                    "color": THEME["muted"],
                    "line-height": "1.6",
                },
                children=[
                    html.Strong("Data Sources: "),
                    "Sentinel-2 NDVI (per-scene) \u2022 "
                    "NASA POWER daily weather (Tmin, Tmax, precip) \u2022 "
                    "USDA CDL crop classification \u2022 "
                    "NRCS SSURGO soil survey",
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
        print(f"Loaded field: {data.field_id or data.field_ids}")
        return data, kpis

    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT or use --json <path>")
        sys.exit(1)

    field_id = args.field or "osm-1219926116"
    print(f"Loading data for grower={args.grower}, farm={args.farm}, field={field_id}...")
    data = DashboardData(data_root, args.grower, args.farm, field_id=field_id)
    kpis = data.get_kpis()
    return data, kpis


def _build_figure(data):
    fid = data.field_ids[0] if data.field_ids else "osm-1219926116"
    ndvi = data.ndvi_scenes
    weather = data.weather
    gdd = data.gdd_daily
    crop_seq = data.get_field_crop_sequence(fid)

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            f"NDVI Accumulation — {FIELD_DISPLAY}",
            "Daily Precipitation",
            "Temperature Extremes (Tmin / Tavg / Tmax)",
            "Cumulative Growing Degree Days (GDD, base 10°C)",
        ),
        row_heights=[0.30, 0.20, 0.25, 0.25],
    )

    year_colors = {2021: "#1f77b4", 2022: "#ff7f0e", 2023: "#2ca02c",
                   2024: "#d62728", 2025: "#9467bd"}
    year_crop_labels = {}
    for yr_str, crop in crop_seq.items():
        year_crop_labels[int(yr_str)] = crop

    captions = []

    if not ndvi.empty:
        ndvi_fid = ndvi[ndvi["field_id"] == fid] if "field_id" in ndvi.columns else ndvi
        for yr in sorted(ndvi_fid["year"].unique()):
            sub = ndvi_fid[ndvi_fid["year"] == yr].sort_values("date")
            color = year_colors.get(yr, "#333")
            crop = year_crop_labels.get(yr, "")
            label = f"{yr} ({crop})" if crop else str(yr)
            fig.add_trace(
                go.Scatter(
                    x=sub["date"], y=sub["ndvi"],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=color, width=2),
                    marker=dict(size=6, color=color, symbol="circle"),
                    hovertemplate=f"{yr} {crop}<br>Date: %{{x|%b %d}}<br>NDVI: %{{y:.3f}}<extra></extra>",
                ),
                row=1, col=1,
            )
        all_vals = ndvi_fid["ndvi"].dropna()
        if len(all_vals) > 0:
            peak_ndvi = all_vals.max()
            peak_row = ndvi_fid.loc[ndvi_fid["ndvi"].idxmax()]
            peak_date = peak_row["date"]
            peak_yr = peak_row["year"]
            peak_crop = year_crop_labels.get(peak_yr, "")
            avg_ndvi = all_vals.mean()
            captions.append(
                f"Peak NDVI of {peak_ndvi:.3f} recorded on {pd.Timestamp(peak_date).strftime('%b %d, %Y')} "
                f"({peak_yr} {peak_crop}). 5-year mean NDVI: {avg_ndvi:.3f}."
            )

    if not weather.empty:
        w = weather.copy()
        if "field_id" in w.columns:
            w = w[w["field_id"] == fid]
        w = w.sort_values("date")
        w_clean = w.dropna(subset=["prectotcorr"])

        fig.add_trace(
            go.Bar(
                x=w_clean["date"], y=w_clean["prectotcorr"],
                marker=dict(color="#0077b6", opacity=0.6),
                name="Precipitation",
                hovertemplate="Date: %{x|%b %d, %Y}<br>Precip: %{y:.1f} mm<extra></extra>",
            ),
            row=2, col=1,
        )
        yr_precip = w_clean.groupby(w_clean["date"].dt.year)["prectotcorr"].sum()
        avg_precip = yr_precip.mean()
        max_precip_yr = yr_precip.idxmax()
        captions.append(
            f"Mean annual precipitation: {avg_precip:.0f} mm. "
            f"Wettest year: {int(max_precip_yr)} ({yr_precip.max():.0f} mm)."
        )

    if not weather.empty and all(c in weather.columns for c in ["t2m_min", "t2m_max", "t2m"]):
        w_temp = weather.copy()
        if "field_id" in w_temp.columns:
            w_temp = w_temp[w_temp["field_id"] == fid]
        w_temp = w_temp.sort_values("date").dropna(subset=["t2m_min", "t2m_max", "t2m"])

        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m_max"],
                mode="lines",
                name="Tmax",
                line=dict(color="#dc3545", width=1.5),
                hovertemplate="Max: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m_min"],
                mode="lines",
                name="Tmin",
                line=dict(color="#1b4965", width=1.5),
                fill=None,
                hovertemplate="Min: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=w_temp["date"], y=w_temp["t2m"],
                mode="lines",
                name="Tavg",
                line=dict(color="#2c6e49", width=2, dash="dash"),
                hovertemplate="Avg: %{y:.1f}°C<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=pd.concat([w_temp["date"], w_temp["date"][::-1]]),
                y=pd.concat([w_temp["t2m_max"], w_temp["t2m_min"][::-1]]),
                fill="toself",
                fillcolor="rgba(220, 53, 69, 0.08)",
                line=dict(width=0),
                name="Range",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=3, col=1,
        )

        avg_max = w_temp["t2m_max"].mean()
        avg_min = w_temp["t2m_min"].mean()
        hottest_idx = w_temp["t2m_max"].idxmax()
        hottest_row = w_temp.loc[hottest_idx]
        captions.append(
            f"Mean Tmax: {avg_max:.1f}°C, Mean Tmin: {avg_min:.1f}°C. "
            f"Hottest day: {pd.Timestamp(hottest_row['date']).strftime('%b %d, %Y')} "
            f"({hottest_row['t2m_max']:.1f}°C)."
        )

    if not gdd.empty:
        g = gdd.copy()
        if "field_id" in g.columns:
            g = g[g["field_id"] == fid]
        g = g.sort_values("date")
        g_season = g[g["season_gdd"] > 0]

        for yr in sorted(g_season["date"].dt.year.unique()):
            sub = g_season[g_season["date"].dt.year == yr]
            color = year_colors.get(yr, "#333")
            crop = year_crop_labels.get(yr, "")
            label = f"{yr} ({crop})" if crop else str(yr)
            fig.add_trace(
                go.Scatter(
                    x=sub["date"], y=sub["season_gdd"],
                    mode="lines",
                    name=label,
                    line=dict(color=color, width=2),
                    hovertemplate=f"{yr} {crop}<br>Date: %{{x|%b %d}}<br>GDD: %{{y:.0f}}<extra></extra>",
                ),
                row=4, col=1,
            )

        final_gdd = g_season.groupby(g_season["date"].dt.year)["season_gdd"].max()
        avg_gdd = final_gdd.mean()
        max_gdd_yr = final_gdd.idxmax()
        captions.append(
            f"Mean seasonal GDD (base 10°C): {avg_gdd:.0f}. "
            f"Highest GDD year: {int(max_gdd_yr)} ({final_gdd.max():.0f})."
        )

    fig.update_layout(
        title=dict(
            text=f"\U0001f33e Aligned Field Timeline — {FIELD_DISPLAY}<br>"
                 f"<span style='font-size:14px;color:{THEME['muted']};font-weight:400'>"
                 f"Northern Iowa Farm \u2022 Cerro Gordo County, IA \u2022 2021-2025</span>",
            font=dict(size=18, color=THEME["primary"]),
        ),
        template="simple_white",
        height=1000,
        hovermode="x unified",
        margin=dict(l=60, r=30, t=80, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
    )

    fig.update_xaxes(title_text="", row=1, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="", row=2, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="", row=3, col=1, gridcolor="#eee")
    fig.update_xaxes(title_text="Date", row=4, col=1, gridcolor="#eee")

    fig.update_yaxes(title_text="NDVI", row=1, col=1, gridcolor="#eee", rangemode="tozero")
    fig.update_yaxes(title_text="mm", row=2, col=1, gridcolor="#eee", rangemode="tozero")
    fig.update_yaxes(title_text="\u00b0C", row=3, col=1, gridcolor="#eee")
    fig.update_yaxes(title_text="GDD", row=4, col=1, gridcolor="#eee", rangemode="tozero")

    caption_text = " \u2022 ".join(captions) if captions else ""
    return fig, caption_text


def build_aligned_dashboard(data):
    fig, caption_text = _build_figure(data)
    return dcc.Graph(figure=fig), caption_text


def do_export(data, kpis, args):
    export_path = Path(args.export)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    import plotly.io as pio

    fig, _caption = _build_figure(data)
    fid = data.field_ids[0] if data.field_ids else "unknown"

    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>",
        f"<title>Row Crop Field Timeline — {fid}</title>",
        "<script src='https://cdn.plot.ly/plotly-2.32.0.min.js'></script>",
        "<style>body{font-family:-apple-system,sans-serif;max-width:1000px;margin:0 auto;padding:20px;background:#f8f9fa}"
        "h1{color:#2c6e49}.card{background:white;border-radius:8px;padding:16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1)}"
        ".caption{background:#f0f7f0;border-left:4px solid #2c6e49;padding:10px 14px;margin:8px 0;border-radius:4px;font-size:13px}</style>",
        "</head><body>",
        "<div class='card'><h1>Row Crop Field Timeline</h1>",
        f"<p style='color:#6c757d'>{fid} \u2022 Cerro Gordo County, IA \u2022 2021-2025</p></div>",
    ]
    html_parts.append(pio.to_html(fig, include_plotlyjs=False, full_html=False))
    html_parts.append("</body></html>")
    with open(str(export_path), "w") as f:
        f.write("\n".join(html_parts))
    print(f"Dashboard exported to {export_path}")


def main():
    parser = argparse.ArgumentParser(description="Row Crop Field Timeline Dashboard")
    parser.add_argument("--grower", default="iowa-grower")
    parser.add_argument("--farm", default="iowa-farm")
    parser.add_argument("--field", default="osm-1219926116")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--json", help="Load from dashboard_data.json")
    parser.add_argument("--export", help="Export dashboard HTML to this path")
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
