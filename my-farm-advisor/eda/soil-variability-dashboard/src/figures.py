"""Chart and KPI generation for the Soil Variability Dashboard.

Each ``fig_*`` function accepts the data dict from ``data_loader`` and returns a
Plotly figure. ``compute_kpis()`` derives summary metrics used by the HTML
template KPI cards and by several figures.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def compute_kpis(data: dict) -> dict:
    s = data["ssurgo_summary"]
    inv = data["field_inventory"]
    w = data["weather"]

    n_fields = len(s)
    total_acres = s["field_id"].map(
        lambda fid: _lookup_acres(fid, data)
    ).sum()

    ndvi_cards = data.get("ndvi_card_data", [])
    ndvi_vals = []
    for card in ndvi_cards:
        for crop_key in ("corn", "soybean"):
            c = card.get("cards", {}).get(crop_key, {})
            v = c.get("mean_ndvi")
            if v is not None:
                ndvi_vals.append(v)
    avg_ndvi = float(np.mean(ndvi_vals)) if ndvi_vals else None

    annual_rainfall = (
        w.groupby(w["date"].dt.year)["PRECTOTCORR"].sum().mean()
        if not w.empty and "PRECTOTCORR" in w.columns
        else None
    )

    soil_health_fields = _compute_soil_health(s)
    avg_soil_health = soil_health_fields["soil_health_score"].mean()

    erosion_counts = s["erosion_risk"].value_counts()
    dominant_erosion = (
        erosion_counts.index[0] if not erosion_counts.empty else "unknown"
    )

    return {
        "n_fields": n_fields,
        "total_acres": round(total_acres, 1),
        "avg_ndvi": round(avg_ndvi, 3) if avg_ndvi else None,
        "avg_annual_rainfall_mm": round(annual_rainfall, 1)
        if annual_rainfall
        else None,
        "avg_soil_health": round(avg_soil_health, 2),
        "dominant_erosion_risk": dominant_erosion,
        "soil_health_fields": soil_health_fields,
    }


def _lookup_acres(field_id: str, data: dict) -> float:
    b = data["boundaries"]
    m = b[b["field_id"] == field_id]
    if not m.empty:
        return float(m.iloc[0]["area_acres"])
    return 0.0


def _compute_soil_health(ssurgo_summary: pd.DataFrame) -> pd.DataFrame:
    df = ssurgo_summary.copy()
    metrics = ["avg_om_pct", "avg_ph", "total_aws_inches", "avg_cec"]
    available = [c for c in metrics if c in df.columns]
    if not available:
        df["soil_health_score"] = 50.0
        return df

    for c in available:
        col_min, col_max = df[c].min(), df[c].max()
        if col_max > col_min:
            df[f"{c}_norm"] = (df[c] - col_min) / (col_max - col_min)
        else:
            df[f"{c}_norm"] = 0.5

    norm_cols = [f"{c}_norm" for c in available]
    df["soil_health_score"] = df[norm_cols].mean(axis=1) * 100
    return df


def make_kpi_indicators(kpis: dict) -> go.Figure:
    labels = [
        "Fields",
        "Total Acres",
        "Avg NDVI",
        "Avg Rainfall (mm/yr)",
        "Soil Health Score",
        "Erosion Risk",
    ]
    values = [
        kpis["n_fields"],
        kpis["total_acres"],
        kpis["avg_ndvi"] if kpis["avg_ndvi"] else "N/A",
        kpis["avg_annual_rainfall_mm"]
        if kpis["avg_annual_rainfall_mm"]
        else "N/A",
        f'{kpis["avg_soil_health"]:.1f}/100',
        kpis["dominant_erosion_risk"].title(),
    ]

    fig = make_subplots(
        rows=1,
        cols=6,
        subplot_titles=labels,
        specs=[[{"type": "indicator"}] * 6],
    )
    for i, (label, val) in enumerate(zip(labels, values), 1):
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=val if isinstance(val, (int, float)) else 0,
                number={"font": {"size": 28}},
                title={"text": label, "font": {"size": 13}},
            ),
            row=1,
            col=i,
        )
    fig.update_layout(
        height=200,
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="#f8f9fa",
    )
    return fig


def fig_soil_ph_distribution(data: dict) -> go.Figure:
    df = data["ssurgo_summary"].sort_values("avg_ph")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df["field_id"],
            y=df["avg_ph"],
            marker_color="#2ecc71",
            text=df["avg_ph"].round(2),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>pH: %{y:.2f}<extra></extra>",
        )
    )
    fig.add_hline(y=6.5, line_dash="dash", line_color="#e74c3c")
    fig.add_annotation(
        xref="paper", x=1.02, y=6.5,
        text="Target pH 6.5",
        showarrow=False,
        font=dict(size=11, color="#e74c3c"),
        xanchor="left",
        yanchor="middle",
    )
    ph_vals = df["avg_ph"]
    y_min = min(ph_vals.min(), 6.5)
    y_max = max(ph_vals.max(), 6.5)
    padding = max((y_max - y_min) * 0.09, 0.3)

    fig.update_layout(
        title="Soil pH Distribution Across Fields",
        xaxis_title="Field",
        yaxis_title="Average pH",
        xaxis_tickangle=-45,
        height=400,
        margin=dict(b=120),
        hovermode="x unified",
        yaxis=dict(range=[y_min - padding, y_max + padding]),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Most fields fall near the optimal target of pH 6.5.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_ndvi_by_year_crop(data: dict) -> go.Figure:
    df = data.get("ndvi_year_join")
    if df is None or df.empty:
        return _empty_fig("NDVI data not available")

    df_2025 = df[df["year"] == 2025].copy()
    if df_2025.empty:
        return _empty_fig("No NDVI data for 2025")

    card_lookup = {}
    for card in data.get("ndvi_card_data", []):
        fid = card.get("field_id")
        cards = card.get("cards", {})
        for crop_key in ("corn", "soybean"):
            entry = cards.get(crop_key, {})
            mean_ndvi = entry.get("mean_ndvi")
            if mean_ndvi is not None:
                card_lookup[(fid, crop_key)] = mean_ndvi

    def _get_ndvi(field_id, crop_name):
        key = crop_name.lower().rstrip("s")
        if key == "soybean":
            key = "soybean"
        elif key == "corn":
            key = "corn"
        else:
            return None
        return card_lookup.get((field_id, key))

    df_2025["field_short"] = df_2025["field_id"].str.replace("osm-", "")
    df_2025["avg_ndvi"] = df_2025.apply(
        lambda r: _get_ndvi(r["field_id"], r["crop_name"]), axis=1
    )

    plot_df = df_2025.dropna(subset=["avg_ndvi"])

    if plot_df.empty:
        return _empty_fig("No NDVI card data available for 2025 fields")

    fig = px.bar(
        plot_df,
        x="field_short",
        y="avg_ndvi",
        color="crop_name",
        title="Average NDVI by Field — 2025",
        labels={
            "field_short": "Field",
            "avg_ndvi": "Average NDVI",
            "crop_name": "Crop",
        },
        barmode="group",
        color_discrete_sequence=px.colors.qualitative.Set2,
        text="avg_ndvi",
    )
    fig.update_traces(
        texttemplate="%{text:.3f}", textposition="outside"
    )
    data_max = plot_df["avg_ndvi"].max()
    padding = data_max * 0.15
    fig.update_layout(
        height=400,
        xaxis_tickangle=-45,
        margin=dict(b=120, t=50),
        yaxis=dict(range=[0, data_max + padding]),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Fields in the northern section show lower NDVI values and reduced organic matter.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_ph_cec_om_correlation(data: dict) -> go.Figure:
    df = data["ssurgo_summary"]
    fig = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=(
            "Organic Matter % by Field",
            "CEC by Field",
            "Average pH by Field",
        ),
    )

    bar_configs = [
        ("avg_om_pct", "Avg OM %", 1, 1, "#27ae60"),
        ("avg_cec", "CEC (meq/100g)", 1, 2, "#2980b9"),
        ("avg_ph", "pH", 1, 3, "#8e44ad"),
    ]

    for col_name, ylabel, row, col, color in bar_configs:
        sorted_df = df.sort_values(col_name, ascending=False)
        fields = sorted_df["field_id"].str.replace("osm-", "")
        fig.add_trace(
            go.Bar(
                x=fields,
                y=sorted_df[col_name],
                marker_color=color,
                text=sorted_df[col_name].round(2),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>"
                + f"{ylabel}: %{{y:.2f}}<extra></extra>",
                showlegend=False,
            ),
            row=row,
            col=col,
        )
        fig.update_xaxes(tickangle=-45, row=row, col=col)
        fig.update_yaxes(title_text=ylabel, row=row, col=col)

    for col_name, _, row, col, _ in bar_configs:
        data_max = df[col_name].max()
        padding = data_max * 0.15
        fig.update_yaxes(range=[0, data_max + padding], row=row, col=col)

    fig.update_layout(
        title="Soil Properties by Field",
        height=400,
        margin=dict(b=100),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Higher OM and CEC values correlate with better soil fertility potential.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_geospatial_soil_health(data: dict) -> go.Figure:
    boundaries = data["boundaries"].copy()
    shf = data["_kpis"]["soil_health_fields"]
    merged = boundaries.merge(
        shf[["field_id", "soil_health_score"]], on="field_id", how="left"
    )

    merged_4326 = merged.to_crs("EPSG:4326")
    center_lat = merged_4326.geometry.centroid.y.mean()
    center_lon = merged_4326.geometry.centroid.x.mean()
    geojson = merged_4326.__geo_interface__

    fig = go.Figure()
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=geojson,
            locations=merged["field_id"],
            z=merged["soil_health_score"],
            featureidkey="properties.field_id",
            colorscale=[[0, "#e74c3c"], [0.5, "#f1c40f"], [1, "#2ecc71"]],
            marker=dict(line=dict(width=1, color="#333")),
            colorbar=dict(
                title="Soil Health<br>Score",
                thickness=15,
                len=0.6,
            ),
            hovertemplate=(
                "<b>%{customdata}</b><br>"
                "Soil Health: %{z:.1f}/100<extra></extra>"
            ),
            customdata=merged["field_id"],
        )
    )

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=11,
        ),
        title="Field Boundaries Colored by Soil Health Score",
        margin=dict(t=50, b=20, l=20, r=20),
        height=550,
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Soil health scores vary notably across the farm, with higher scores in well-drained areas.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_monthly_precipitation(data: dict) -> go.Figure:
    w = data["weather"].copy()
    w["month"] = w["date"].dt.to_period("M").astype(str)
    monthly = (
        w.groupby("month")["PRECTOTCORR"]
        .sum()
        .reset_index()
    )
    monthly["month_dt"] = pd.to_datetime(monthly["month"] + "-01")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=monthly["month_dt"],
            y=monthly["PRECTOTCORR"],
            marker_color="#3498db",
            hovertemplate="%{x|%b %Y}<br>Rainfall: %{y:.1f} mm<extra></extra>",
        )
    )
    fig.update_layout(
        title="Monthly Precipitation (All Fields, 2021–2025)",
        xaxis_title="Date",
        yaxis_title="Total Precipitation (mm)",
        height=400,
        hovermode="x unified",
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Higher rainfall variability appears associated with lower crop health indicators.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_temperature_envelope(data: dict) -> go.Figure:
    w = data["weather"].copy()
    daily_avg = (
        w.groupby("date")[["T2M", "T2M_MAX", "T2M_MIN"]]
        .mean()
        .reset_index()
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily_avg["date"],
            y=daily_avg["T2M_MAX"],
            mode="lines",
            name="Max Temp",
            line=dict(color="#e74c3c", width=1.5),
            hovertemplate="%{x|%b %Y}<br>Max: %{y:.1f}°C<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily_avg["date"],
            y=daily_avg["T2M"],
            mode="lines",
            name="Mean Temp",
            line=dict(color="#f39c12", width=2),
            hovertemplate="%{x|%b %Y}<br>Mean: %{y:.1f}°C<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily_avg["date"],
            y=daily_avg["T2M_MIN"],
            mode="lines",
            name="Min Temp",
            line=dict(color="#3498db", width=1.5),
            hovertemplate="%{x|%b %Y}<br>Min: %{y:.1f}°C<extra></extra>",
        )
    )
    fig.update_layout(
        title="Daily Temperature Envelope (All Fields Average)",
        xaxis_title="Date",
        yaxis_title="Temperature (°C)",
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Growing season temperature extremes can impact crop development and yield stability.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_soil_health_score_chart(data: dict) -> go.Figure:
    shf = data["_kpis"]["soil_health_fields"].sort_values(
        "soil_health_score", ascending=True
    )
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=shf["field_id"],
            y=shf["soil_health_score"],
            marker_color=[
                "rgba(46, 204, 113, 0.5)" if s >= 70
                else "rgba(241, 196, 15, 0.5)" if s >= 50
                else "rgba(231, 76, 60, 0.5)"
                for s in shf["soil_health_score"]
            ],
            text=shf["soil_health_score"].round(1),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Score: %{y:.1f}/100<extra></extra>",
        )
    )
    data_max = shf["soil_health_score"].max()
    padding = data_max * 0.15
    fig.update_layout(
        title="Composite Soil Health Score by Field",
        xaxis_title="Field",
        yaxis_title="Soil Health Score (0–100)",
        xaxis_tickangle=-45,
        height=400,
        margin=dict(b=120),
        yaxis=dict(range=[0, data_max + padding]),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Fields with stronger drainage characteristics generally showed healthier vegetation patterns.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_drainage_class_distribution(data: dict) -> go.Figure:
    df = data["ssurgo_summary"]
    counts = df["drainage_class"].value_counts().reset_index()
    counts.columns = ["drainage_class", "count"]
    colors = {
        "Well drained": "#2ecc71",
        "Moderately well drained": "#f1c40f",
        "Somewhat poorly drained": "#e67e22",
        "Poorly drained": "#e74c3c",
    }
    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts["drainage_class"],
                values=counts["count"],
                marker_colors=[
                    colors.get(d, "#95a5a6")
                    for d in counts["drainage_class"]
                ],
                textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>Fields: %{value}<br>Percent: %{percent}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Drainage Class Distribution",
        height=350,
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Well-drained soils dominate the farm, supporting consistent crop establishment.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def fig_field_variability_radar(data: dict) -> go.Figure:
    df = data["ssurgo_summary"]
    metrics = ["avg_om_pct", "avg_cec", "total_aws_inches", "avg_ph", "avg_clay_pct"]
    available = [c for c in metrics if c in df.columns]
    if not available:
        return _empty_fig("Metric data not available")

    label_map = {
        "avg_om_pct": "OM (%)",
        "avg_cec": "CEC (meq/100g)",
        "total_aws_inches": "Water (in)",
        "avg_ph": "pH",
        "avg_clay_pct": "Clay (%)",
    }
    labels = [label_map[c] for c in available]
    fig = go.Figure()
    for _, row in df.iterrows():
        vals = [row[c] for c in available]
        fig.add_trace(
            go.Scatterpolar(
                r=vals + [vals[0]],
                theta=labels + [labels[0]],
                fill="toself",
                name=row["field_id"].replace("osm-", ""),
                hovertemplate="<b>%{fullText}</b><extra></extra>",
            )
        )
    fig.update_layout(
        title="Field Variability Radar — Soil Properties",
        polar=dict(
            radialaxis=dict(visible=True, showticklabels=False),
        ),
        height=450,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5
        ),
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=1.08,
        text="<i>Insight:</i> <span style='color:#555'>Field-to-field variability is most pronounced in OM and CEC.</span>",
        showarrow=False, font=dict(size=11),
        xanchor="left", yanchor="bottom",
    )
    return fig


def _empty_fig(msg: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color="#95a5a6"),
    )
    fig.update_layout(height=300)
    return fig
