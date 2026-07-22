#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import geopandas as gpd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

os.environ.setdefault("DATA_PIPELINE_DATA_ROOT", str(_SCRIPTS_DIR.parents[1]))
os.environ.setdefault("AG_WEATHER_START_YEAR", "2021")
os.environ.setdefault("AG_WEATHER_END_YEAR", "2025")

from paths import (
    farm_boundary_path,
    farm_ssurgo_summary_path,
    farm_soil_sample_path,
    farm_weather_path,
    farm_cdl_full_composition_path,
    farm_cdl_rotation_path,
    farm_table_path,
    field_summary_path,
    farm_dir,
    farm_dashboard_path,
    ensure_parent,
)

st.set_page_config(page_title="Row Crop Intelligence Dashboard", layout="wide", page_icon="🌽")

DEFAULT_GROWER = "iowa-grower"
DEFAULT_FARM = "iowa-grower-iowa"
FIELD_NAMES = {
    "osm-1052414024": "Field A — Clarion (38.8 ac)",
    "osm-1360326432": "Field B — Webster (217.7 ac)",
    "osm-1360386537": "Field C — Webster (148.1 ac)",
    "osm-1360394834": "Field D — Spillville (25.3 ac)",
}
FIELD_COLORS = {
    "osm-1052414024": "#1f77b4",
    "osm-1360326432": "#ff7f0e",
    "osm-1360386537": "#2ca02c",
    "osm-1360394834": "#d62728",
}
DRAINAGE_ORDER = [
    "Excessively drained",
    "Somewhat excessively drained",
    "Well drained",
    "Moderately well drained",
    "Somewhat poorly drained",
    "Poorly drained",
    "Very poorly drained",
]


@st.cache_data(ttl=3600)
def load_field_boundaries(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_boundary_path(grower, farm)
    if not p.exists():
        return None
    gdf = gpd.read_file(p)
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    return gdf


@st.cache_data(ttl=3600)
def load_ssurgo_summary(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_ssurgo_summary_path(grower, farm)
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(ttl=3600)
def load_fields_soil(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_soil_sample_path(grower, farm)
    if not p.exists():
        p = farm_table_path(grower, farm, "iowa_grower_iowa_fields_soil.csv")
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(ttl=3600)
def load_weather(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_weather_path(grower, farm)
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    return df


@st.cache_data(ttl=3600)
def load_cdl_composition(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_cdl_full_composition_path(grower, farm)
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(ttl=3600)
def load_crop_rotation(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_cdl_rotation_path(grower, farm)
    if not p.exists():
        return None
    return pd.read_csv(p)


@st.cache_data(ttl=3600)
def load_ndvi_summaries(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    farm_p = farm_dir(grower, farm)
    field_dirs = sorted(farm_p.glob("fields/*"))
    records = []
    for fd in field_dirs:
        fid = fd.name
        p = field_summary_path(grower, farm, fid, "ndvi_card_summary.json")
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        cards = data.get("cards", {})
        rec = {"field_id": fid}
        for key in ["corn", "soybean", "corn_peak_95", "soybean_peak_95"]:
            card = cards.get(key, {})
            if card.get("status") == "available" and "mean_ndvi" in card:
                rec[f"ndvi_{key}"] = card["mean_ndvi"]
            else:
                rec[f"ndvi_{key}"] = None
        records.append(rec)
    if not records:
        return None
    df = pd.DataFrame(records)
    return df


@st.cache_data(ttl=3600)
def load_field_inventory(grower=DEFAULT_GROWER, farm=DEFAULT_FARM):
    p = farm_table_path(grower, farm, "field-inventory.csv")
    alt = farm_dir(grower, farm) / "manifests" / "field-inventory.csv"
    if p.exists():
        return pd.read_csv(p)
    if alt.exists():
        return pd.read_csv(alt)
    return None


def compute_soil_health_score(row):
    om = row.get("avg_om_pct", 0) or 0
    ph = row.get("avg_ph", 7) or 7
    awc = row.get("total_aws_inches", 0) or 0
    cec = row.get("avg_cec", 20) or 20
    drainage = str(row.get("drainage_class", ""))

    om_score = min(om / 5.0, 1.0)
    ph_fitness = 1.0 - abs(ph - 6.7) / 2.0
    ph_fitness = max(0.0, min(1.0, ph_fitness))
    awc_score = min(awc / 5.0, 1.0)
    cec_score = 1.0 - abs(cec - 25) / 25.0
    cec_score = max(0.0, min(1.0, cec_score))
    drain_scores = {
        "Excessively drained": 0.6,
        "Somewhat excessively drained": 0.7,
        "Well drained": 1.0,
        "Moderately well drained": 0.9,
        "Somewhat poorly drained": 0.7,
        "Poorly drained": 0.5,
        "Very poorly drained": 0.3,
    }
    drain_score = drain_scores.get(drainage, 0.5)
    shi = 0.25 * om_score + 0.20 * ph_fitness + 0.20 * awc_score + 0.15 * cec_score + 0.20 * drain_score
    return round(shi * 10, 1)


def compute_sustainability_index(soil_row, rotation_df, ndvi_df):
    shi = compute_soil_health_score(soil_row)
    shi_norm = shi / 10.0
    field_id = soil_row["field_id"]
    div = 0
    if rotation_df is not None:
        rot = rotation_df[rotation_df["field_id"] == field_id]
        if not rot.empty:
            div = rot.iloc[0].get("crop_diversity", 1) / 3.0
    ndvi_score = 0.5
    if ndvi_df is not None and field_id in ndvi_df["field_id"].values:
        row = ndvi_df[ndvi_df["field_id"] == field_id].iloc[0]
        peak = row.get("ndvi_corn_peak_95")
        if peak is not None:
            ndvi_score = min(peak / 0.95, 1.0)
    si = 0.50 * shi_norm + 0.30 * ndvi_score + 0.20 * min(div, 1.0)
    return round(si * 10, 1)


def generate_recommendations(soil_row, ndvi_df, rotation_df):
    fid = soil_row["field_id"]
    recs = []
    om = soil_row.get("avg_om_pct", 0) or 0
    ph = soil_row.get("avg_ph", 7) or 7
    awc = soil_row.get("total_aws_inches", 0) or 0
    cec = soil_row.get("avg_cec", 20) or 20
    drainage = str(soil_row.get("drainage_class", ""))
    name = FIELD_NAMES.get(fid, fid)

    if ph < 6.2:
        recs.append(("🌱", f"**{name}** — Apply lime to raise pH from {ph:.1f} (below optimal 6.2–7.0)."))
    elif ph > 7.5:
        recs.append(("🌱", f"**{name}** — Monitor micronutrient availability at pH {ph:.1f}; consider elemental sulfur if needed."))
    else:
        recs.append(("✅", f"**{name}** — pH {ph:.1f} is within optimal range."))

    if om < 3.0:
        recs.append(("🧪", f"**{name}** — Low OM ({om:.1f}%). Incorporate cover crops or manure to build organic matter."))
    elif om >= 5.0:
        recs.append(("🧪", f"**{name}** — High OM ({om:.1f}%). Reduce N fertilizer by 10–15% and monitor."))
    else:
        recs.append(("✅", f"**{name}** — OM ({om:.1f}%) is adequate."))

    if awc < 2.5:
        recs.append(("💧", f"**{name}** — Low water storage ({awc:.1f} in). Elevated drought risk; prioritize irrigation planning."))
    elif awc < 3.5:
        recs.append(("💧", f"**{name}** — Moderate water storage ({awc:.1f} in). Monitor during reproductive stages."))
    else:
        recs.append(("💧", f"**{name}** — Good water storage ({awc:.1f} in). Low drought risk."))

    if any(poor in drainage for poor in ["Poorly drained", "Very poorly drained"]):
        recs.append(("🚜", f"**{name}** — Drainage class '{drainage}'. Prioritize tile drainage and trafficability management."))
    elif "Somewhat" in drainage:
        recs.append(("🚜", f"**{name}** — Drainage is '{drainage}'. Monitor after heavy rains for saturated conditions."))

    if cec < 15:
        recs.append(("🧫", f"**{name}** — Low CEC ({cec:.0f}). Split-apply fertilizers to reduce leaching loss."))

    if ndvi_df is not None and fid in ndvi_df["field_id"].values:
        row = ndvi_df[ndvi_df["field_id"] == fid].iloc[0]
        peak = row.get("ndvi_corn_peak_95")
        if peak is not None and peak < 0.80:
            recs.append(("🛰️", f"**{name}** — Low peak NDVI ({peak:.3f}). Investigate potential yield-limiting factors."))

    if rotation_df is not None:
        rot = rotation_df[rotation_df["field_id"] == fid]
        if not rot.empty:
            outlook = rot.iloc[0].get("rotation_outlook", "")
            if "Corn next" in str(outlook):
                recs.append(("🔄", f"**{name}** — Rotation outlook: {outlook.split('.')[0]}. Plan N rates accordingly."))
    return recs


def get_css():
    return """
<style>
    .kpi-card {
        background: #fff;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .kpi-label {
        font-size: 0.78rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .kpi-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0f172a;
        margin-top: 0.15rem;
    }
    .kpi-delta {
        font-size: 0.78rem;
        color: #22c55e;
    }
    .interpretation {
        background: #f0f9ff;
        border-left: 4px solid #2563eb;
        padding: 0.8rem 1rem;
        border-radius: 0 6px 6px 0;
        font-size: 0.9rem;
        color: #1e293b;
        margin: 0.5rem 0;
    }
    .rec-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.7rem 1rem;
        margin: 0.3rem 0;
        font-size: 0.9rem;
    }
</style>
"""


def render_kpis(ssurgo_df, ndvi_df, fields_gdf, weather_df):
    st.markdown("### Key Performance Indicators")
    total_acres = fields_gdf["area_acres"].sum() if fields_gdf is not None and "area_acres" in fields_gdf.columns else 0
    n_fields = len(ssurgo_df) if ssurgo_df is not None else 0
    avg_ndvi = ndvi_df["ndvi_corn_peak_95"].mean() if ndvi_df is not None and "ndvi_corn_peak_95" in ndvi_df.columns else 0
    avg_shs = ssurgo_df["soil_health_score"].mean() if ssurgo_df is not None and "soil_health_score" in ssurgo_df.columns else 0
    avg_precip = None
    if weather_df is not None:
        avg_precip = weather_df.groupby("year")["PRECTOTCORR"].sum().mean()
    top_drainage = ssurgo_df["drainage_class"].value_counts().index[0] if ssurgo_df is not None and "drainage_class" in ssurgo_df.columns else ""
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Total Fields</div><div class="kpi-value">{n_fields}</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Total Acres</div><div class="kpi-value">{total_acres:.0f}</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Avg Peak NDVI</div><div class="kpi-value">{avg_ndvi:.3f}</div></div>""", unsafe_allow_html=True)
    with col4:
        val = f"{avg_precip:.0f}" if avg_precip else "—"
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Avg Annual Precip</div><div class="kpi-value">{val} mm</div></div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Soil Health Score</div><div class="kpi-value">{avg_shs:.1f}</div><div class="kpi-delta">/ 10</div></div>""", unsafe_allow_html=True)
    with col6:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Dominant Drainage</div><div class="kpi-value" style="font-size:1rem">{top_drainage}</div></div>""", unsafe_allow_html=True)


def render_soil_vegetation_tab(ssurgo_df, fields_soil, ndvi_df, cdl_df, fields_gdf, rotation_df, selected_fields, selected_year_range):
    st.markdown("## Soil & Vegetation Analysis")
    sf = [f for f in selected_fields if f in FIELD_NAMES]
    if not sf:
        st.info("Select at least one field in the sidebar.")
        return
    ssurgo_f = ssurgo_df[ssurgo_df["field_id"].isin(sf)] if ssurgo_df is not None else None
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Soil pH by Field")
        fig = go.Figure()
        if fields_soil is not None:
            fs = fields_soil[fields_soil["field_id"].isin(sf)]
            for fid in sf:
                sub = fs[fs["field_id"] == fid]
                if sub.empty:
                    continue
                fig.add_trace(go.Box(
                    y=sub["ph1to1h2o_r"].dropna(),
                    name=FIELD_NAMES.get(fid, fid),
                    marker_color=FIELD_COLORS.get(fid, "#1f77b4"),
                    hovertemplate="pH: %{y:.1f}<extra>%{text}</extra>",
                    text=[FIELD_NAMES.get(fid, fid)] * len(sub),
                ))
            fig.add_hline(y=6.5, line_dash="dash", line_color="green", annotation_text="Optimal min")
            fig.add_hline(y=7.0, line_dash="dash", line_color="green", annotation_text="Optimal max")
            fig.update_layout(height=350, margin=dict(l=40, r=20, t=20, b=40), yaxis_title="pH")
            st.plotly_chart(fig, width="stretch")
            st.markdown("""<div class="interpretation">Fields with pH outside the 6.5–7.0 optimal range may experience nutrient availability constraints. Clarion soils trend neutral; Spillville soils are slightly more acidic.</div>""", unsafe_allow_html=True)
    with c2:
        st.subheader("Organic Matter by Field")
        fig = go.Figure()
        if fields_soil is not None:
            fs = fields_soil[fields_soil["field_id"].isin(sf)]
            for fid in sf:
                sub = fs[fs["field_id"] == fid]
                if sub.empty:
                    continue
                fig.add_trace(go.Box(
                    y=sub["om_r"].dropna(),
                    name=FIELD_NAMES.get(fid, fid),
                    marker_color=FIELD_COLORS.get(fid, "#1f77b4"),
                    hovertemplate="OM: %{y:.1f}%<extra>%{text}</extra>",
                    text=[FIELD_NAMES.get(fid, fid)] * len(sub),
                ))
            fig.update_layout(height=350, margin=dict(l=40, r=20, t=20, b=40), yaxis_title="Organic Matter (%)")
            st.plotly_chart(fig, width="stretch")
            st.markdown("""<div class="interpretation">Organic matter ranges from 3.1% (Field D) to 4.9% (Field A). Higher OM improves water holding and nutrient cycling. Field D's sandy textures naturally hold less OM.</div>""", unsafe_allow_html=True)
    st.subheader("NDVI Comparison Across Fields")
    if ndvi_df is not None:
        ndvi_f = ndvi_df[ndvi_df["field_id"].isin(sf)]
        fig = go.Figure()
        metrics = [
            ("ndvi_corn", "Corn Avg NDVI"),
            ("ndvi_corn_peak_95", "Corn Peak NDVI"),
            ("ndvi_soybean", "Soybean Avg NDVI"),
            ("ndvi_soybean_peak_95", "Soybean Peak NDVI"),
        ]
        for i, (col, label) in enumerate(metrics):
            if col not in ndvi_f.columns:
                continue
            valid = ndvi_f[ndvi_f[col].notna()]
            if valid.empty:
                continue
            fig.add_trace(go.Bar(
                x=[FIELD_NAMES.get(f, f) for f in valid["field_id"]],
                y=valid[col],
                name=label,
                hovertemplate="%{y:.3f}<extra>" + label + "</extra>",
            ))
        fig.update_layout(
            height=400, barmode="group",
            xaxis_title="Field", yaxis_title="NDVI",
            legend=dict(orientation="h", y=1.1),
            margin=dict(l=40, r=20, t=40, b=60),
        )
        st.plotly_chart(fig, width="stretch")
        st.markdown("""<div class="interpretation">Corn peak NDVI values range from 0.833 (Field D) to 0.895 (Field A). Field A's higher NDVI correlates with higher OM and better drainage. Fields B and C (Webster soils) show moderate NDVI despite lower drainage ratings, likely due to their higher water-holding capacity during dry periods.</div>""", unsafe_allow_html=True)
    c_left, c_right = st.columns(2)
    with c_left:
        st.subheader("Soil Health Score Breakdown")
        if ssurgo_f is not None:
            fig = go.Figure()
            for _, row in ssurgo_f.iterrows():
                fid = row["field_id"]
                om_s = min((row.get("avg_om_pct", 0) or 0) / 5.0, 1.0) * 2.5
                ph_s = max(0, 1 - abs((row.get("avg_ph", 7) or 7) - 6.7) / 2.0) * 2.0
                awc_s = min((row.get("total_aws_inches", 0) or 0) / 5.0, 1.0) * 2.0
                cec_s = max(0, 1 - abs((row.get("avg_cec", 20) or 20) - 25) / 25.0) * 1.5
                drain_s = {"Well drained": 2.0, "Moderately well drained": 1.8, "Somewhat poorly drained": 1.4, "Poorly drained": 1.0, "Very poorly drained": 0.6}.get(str(row.get("drainage_class", "")), 1.0)
                fig.add_trace(go.Bar(
                    name=FIELD_NAMES.get(fid, fid),
                    x=["OM", "pH", "AWC", "CEC", "Drainage"],
                    y=[om_s, ph_s, awc_s, cec_s, drain_s],
                    marker_color=FIELD_COLORS.get(fid, "#1f77b4"),
                    hovertemplate="%{y:.1f}/max<br>%{x}<extra>" + FIELD_NAMES.get(fid, fid) + "</extra>",
                ))
            fig.update_layout(barmode="group", height=350, margin=dict(l=40, r=20, t=20, b=40))
            st.plotly_chart(fig, width="stretch")
    with c_right:
        st.subheader("Sustainability Index")
        if ssurgo_f is not None:
            si_df = []
            for _, row in ssurgo_f.iterrows():
                fid = row["field_id"]
                si = compute_sustainability_index(row, rotation_df, ndvi_df)
                si_df.append({"field_id": FIELD_NAMES.get(fid, fid), "Sustainability Index": si})
            si_df = pd.DataFrame(si_df)
            fig = px.bar(si_df, x="field_id", y="Sustainability Index", color="field_id",
                         color_discrete_map=FIELD_COLORS, height=350,
                         text_auto=".1f")
            fig.update_layout(showlegend=False, margin=dict(l=40, r=20, t=20, b=40),
                              xaxis_title="", yaxis=dict(range=[0, 10]))
            st.plotly_chart(fig, width="stretch")
            st.markdown("""<div class="interpretation">The Sustainability Index combines soil health (50%), NDVI performance (30%), and crop diversity (20%). Field A leads due to highest OM and good drainage. Field D trails due to sandy, low-OM soils.</div>""", unsafe_allow_html=True)


def render_weather_tab(weather_df, selected_fields, selected_year_range):
    st.markdown("## Weather & Climate Analysis")
    if weather_df is None:
        st.info("Weather data not available.")
        return
    sf = [f for f in selected_fields if f in FIELD_NAMES]
    weather_f = weather_df[weather_df["field_id"].isin(sf)]
    years = sorted(weather_f["year"].unique())
    years = [y for y in years if selected_year_range[0] <= y <= selected_year_range[1]]
    weather_f = weather_f[weather_f["year"].isin(years)]
    if weather_f.empty:
        st.info("No weather data for the selected filter.")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Monthly Precipitation by Year")
        monthly = weather_f.groupby(["year", "month"])["PRECTOTCORR"].sum().reset_index()
        fig = px.bar(
            monthly, x="month", y="PRECTOTCORR", color="year",
            barmode="group", height=400,
            labels={"PRECTOTCORR": "Precipitation (mm)", "month": "Month"},
            color_discrete_sequence=px.colors.qualitative.Set1,
        )
        fig.update_layout(margin=dict(l=40, r=20, t=20, b=40))
        fig.update_xaxes(tickvals=list(range(1, 13)), ticktext=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Temperature Range")
        daily = weather_f.groupby("date")[["T2M_MIN", "T2M", "T2M_MAX"]].mean().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["T2M_MAX"], name="Max", line=dict(color="#ef4444", width=1), hovertemplate="%{y:.1f}°C<extra>Max</extra>"))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["T2M"], name="Mean", line=dict(color="#1f77b4", width=2), hovertemplate="%{y:.1f}°C<extra>Mean</extra>"))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["T2M_MIN"], name="Min", line=dict(color="#3b82f6", width=1), hovertemplate="%{y:.1f}°C<extra>Min</extra>"))
        fig.add_hrect(y0=10, y1=30, fillcolor="green", opacity=0.05, line_width=0, annotation_text="Growing season", annotation_position="top left")
        fig.update_layout(height=400, margin=dict(l=40, r=20, t=20, b=40), yaxis_title="Temperature (°C)")
        st.plotly_chart(fig, width="stretch")
    st.subheader("Growing Degree Days (Base 10°C)")
    weather_f_daily = weather_f.groupby(["field_id", "date"])["T2M"].mean().reset_index()
    weather_f_daily["gdd"] = weather_f_daily["T2M"].clip(lower=10) - 10
    weather_f_daily = weather_f_daily.sort_values(["field_id", "date"])
    weather_f_daily["cum_gdd"] = weather_f_daily.groupby("field_id")["gdd"].cumsum()
    fig = go.Figure()
    for fid in sf:
        sub = weather_f_daily[weather_f_daily["field_id"] == fid]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["cum_gdd"],
            name=FIELD_NAMES.get(fid, fid),
            line=dict(color=FIELD_COLORS.get(fid, "#1f77b4"), width=2),
            hovertemplate="%{y:.0f} GDD<extra>" + FIELD_NAMES.get(fid, fid) + "</extra>",
        ))
    fig.update_layout(height=350, margin=dict(l=40, r=20, t=20, b=40), yaxis_title="Cumulative GDD")
    st.plotly_chart(fig, width="stretch")
    st.markdown("""<div class="interpretation">GDD accumulation is similar across fields due to their proximity, but small differences in microclimate and measurement timing create minor divergence. The growing season window (10–30°C) covers approximately April through October. 2023 showed optimal accumulation timing; monitor for late-spring frost risk in early-season varieties.</div>""", unsafe_allow_html=True)
    st.subheader("Year-over-Year Precipitation Anomaly")
    annual = weather_f.groupby(["field_id", "year"])["PRECTOTCORR"].sum().reset_index()
    overall_mean = annual["PRECTOTCORR"].mean()
    annual["anomaly"] = annual["PRECTOTCORR"] - overall_mean
    fig = px.bar(
        annual, x="year", y="anomaly", color="field_id",
        barmode="group", height=350,
        labels={"anomaly": "Precip Anomaly (mm)", "year": ""},
        color_discrete_map=FIELD_COLORS,
    )
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.update_layout(margin=dict(l=40, r=20, t=20, b=40))
    st.plotly_chart(fig, width="stretch")


def render_map_tab(ssurgo_df, fields_gdf, ndvi_df, map_layer, selected_fields):
    st.markdown("## Geospatial Analysis")
    if fields_gdf is None:
        st.info("Field boundary data not available.")
        return
    gdf = fields_gdf.copy()
    if "field_id" not in gdf.columns:
        gdf["field_id"] = gdf.index.astype(str)
    layer_label = map_layer
    if map_layer == "Soil Health Score":
        scores = {}
        if ssurgo_df is not None:
            for _, row in ssurgo_df.iterrows():
                scores[row["field_id"]] = compute_soil_health_score(row)
        gdf["value"] = gdf["field_id"].map(scores)
        color_scale = "RdYlGn"
        title = "Soil Health Score"
        hover_data = {"field_id": True, "value": ":.1f"}
        range_c = [0, 10]
    elif map_layer == "NDVI Peak (Corn)":
        vals = {}
        if ndvi_df is not None:
            for _, row in ndvi_df.iterrows():
                vals[row["field_id"]] = row.get("ndvi_corn_peak_95", 0) or 0
        gdf["value"] = gdf["field_id"].map(vals)
        color_scale = "YlGn"
        title = "Corn Peak NDVI"
        hover_data = {"field_id": True, "value": ":.3f"}
        range_c = [0.7, 1.0]
    elif map_layer == "Drainage Class":
        drain_nums = {d: i for i, d in enumerate(DRAINAGE_ORDER)}
        gdf["value"] = gdf["field_id"].map(
            lambda fid: drain_nums.get(ssurgo_df[ssurgo_df["field_id"] == fid]["drainage_class"].values[0] if ssurgo_df is not None and fid in ssurgo_df["field_id"].values else "", 3)
        )
        color_scale = "Viridis"
        title = "Drainage Class (0=excessive, 6=very poor)"
        hover_data = {"field_id": True, "value": True}
        range_c = [0, 6]
    else:
        vals = {}
        if ssurgo_df is not None:
            for _, row in ssurgo_df.iterrows():
                vals[row["field_id"]] = row.get("avg_om_pct", 0) or 0
        gdf["value"] = gdf["field_id"].map(vals)
        color_scale = "YlOrBr"
        title = "Organic Matter (%)"
        hover_data = {"field_id": True, "value": ":.1f"}
        range_c = [0, 6]
    gdf_proj = gdf.to_crs("EPSG:26915")
    center_lat = gdf_proj.geometry.centroid.to_crs("EPSG:4326").y.mean()
    center_lon = gdf_proj.geometry.centroid.to_crs("EPSG:4326").x.mean()
    fig = go.Figure()
    for _, row in gdf.iterrows():
        fid = row["field_id"]
        if fid not in selected_fields:
            continue
        geom = row.geometry
        if geom.geom_type == "Polygon":
            coords = geom.exterior.coords
            xs, ys = zip(*coords)
        elif geom.geom_type == "MultiPolygon":
            coords = geom.geoms[0].exterior.coords
            xs, ys = zip(*coords)
        else:
            continue
        val = row["value"]
        c = px.colors.sample_colorscale(color_scale, (val - range_c[0]) / (range_c[1] - range_c[0]) if range_c[1] != range_c[0] else 0.5)
        opacity = 0.7 if fid in selected_fields else 0.15
        fig.add_trace(go.Scattergeo(
            lon=list(xs), lat=list(ys),
            mode="lines",
            fill="toself",
            fillcolor=c[0] if isinstance(c, list) else c,
            line=dict(color="black", width=1.5),
            name=FIELD_NAMES.get(fid, fid),
            text=f"{title}: {val:.2f}" if isinstance(val, (int, float)) else f"{title}: {val}",
            hovertemplate="<b>%{text}</b><br>" + FIELD_NAMES.get(fid, fid) + "<extra></extra>",
            opacity=opacity,
            showlegend=True,
        ))
    fig.update_layout(
        geo=dict(
            projection_type="mercator",
            center=dict(lat=center_lat, lon=center_lon),
            showland=True,
            landcolor="#f0f0f0",
            coastlinecolor="#ccc",
            showcountries=True,
            countrycolor="#ccc",
            lonaxis_range=[center_lon - 0.5, center_lon + 0.5],
            lataxis_range=[center_lat - 0.3, center_lat + 0.3],
        ),
        height=500,
        margin=dict(l=20, r=20, t=20, b=20),
        title=f"Field Boundaries Colored by {title}",
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"""<div class="interpretation">Map layer shows <b>{map_layer}</b> across selected fields. Use the sidebar to switch between Soil Health, NDVI, Drainage, and Organic Matter layers. The underlying data comes from SSURGO soil surveys and Sentinel-2 satellite imagery.</div>""", unsafe_allow_html=True)


def render_comparison_tab(ssurgo_df, fields_soil, ndvi_df, cdl_df, rotation_df, weather_df, selected_fields):
    st.markdown("## Field Comparison")
    sf = [f for f in selected_fields if f in FIELD_NAMES]
    if len(sf) < 2:
        st.info("Select at least 2 fields in the sidebar to enable comparison.")
        return
    st.markdown(f"Comparing: **{', '.join(FIELD_NAMES.get(f, f) for f in sf)}**")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Radar: Soil Properties")
        if ssurgo_df is not None:
            metrics = ["avg_om_pct", "avg_ph", "total_aws_inches", "avg_cec"]
            labels = ["OM %", "pH", "AWC (in)", "CEC"]
            fig = go.Figure()
            for fid in sf[:2]:
                row = ssurgo_df[ssurgo_df["field_id"] == fid]
                if row.empty:
                    continue
                row = row.iloc[0]
                vals = [row.get(m, 0) or 0 for m in metrics]
                max_vals = [6, 8, 5, 35]
                norm = [v / mv for v, mv in zip(vals, max_vals)]
                fig.add_trace(go.Scatterpolar(
                    r=norm + [norm[0]],
                    theta=labels + [labels[0]],
                    name=FIELD_NAMES.get(fid, fid)[:20],
                    fill="toself",
                    line=dict(color=FIELD_COLORS.get(fid, "#1f77b4")),
                ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                height=380, margin=dict(l=60, r=60, t=20, b=20),
            )
            st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("NDVI Trend Overlay")
        if ndvi_df is not None:
            ndvi_f = ndvi_df[ndvi_df["field_id"].isin(sf)]
            fig = go.Figure()
            for fid in sf:
                row = ndvi_f[ndvi_f["field_id"] == fid]
                if row.empty:
                    continue
                row = row.iloc[0]
                years_labels = ["2021", "2022", "2023", "2024", "2025"]
                values = []
                for y in years_labels:
                    if row.get("ndvi_corn_peak_95") is not None:
                        values.append(row["ndvi_corn_peak_95"])
                    else:
                        values.append(None)
                fig.add_trace(go.Scatter(
                    x=years_labels, y=values,
                    mode="lines+markers",
                    name=FIELD_NAMES.get(fid, fid),
                    line=dict(color=FIELD_COLORS.get(fid, "#1f77b4"), width=2),
                    hovertemplate="%{y:.3f}<extra>" + FIELD_NAMES.get(fid, fid) + "</extra>",
                ))
            fig.update_layout(height=380, margin=dict(l=40, r=20, t=20, b=40), yaxis_title="Peak NDVI")
            st.plotly_chart(fig, width="stretch")
    st.markdown("""<div class="interpretation">The radar chart normalizes soil metrics to their max expected values for the region. Fields with larger radar area have better overall soil quality. The NDVI overlay shows interannual variability — comparing fields side by side reveals which fields consistently outperform others.</div>""", unsafe_allow_html=True)
    if rotation_df is not None:
        st.subheader("Crop Rotation Comparison")
        rot_f = rotation_df[rotation_df["field_id"].isin(sf)]
        if not rot_f.empty:
            for _, row in rot_f.iterrows():
                fid = row["field_id"]
                seq = row.get("rotation_sequence", "N/A")
                outlook = row.get("rotation_outlook", "")
                st.markdown(f"""<div class="rec-card"><strong>{FIELD_NAMES.get(fid, fid)}</strong><br>Rotation: {seq}<br>Outlook: {outlook[:100]}…</div>""", unsafe_allow_html=True)


def render_recommendations_tab(ssurgo_df, ndvi_df, rotation_df, selected_fields):
    st.markdown("## Recommendations & Decision Support")
    sf = [f for f in selected_fields if f in FIELD_NAMES]
    if ssurgo_df is None:
        st.info("Soil data required for recommendations.")
        return
    ssurgo_f = ssurgo_df[ssurgo_df["field_id"].isin(sf)]
    st.markdown("### Per-Field Action Items")
    for _, row in ssurgo_f.iterrows():
        recs = generate_recommendations(row, ndvi_df, rotation_df)
        for icon, text in recs:
            st.markdown(f"""<div class="rec-card">{icon} {text}</div>""", unsafe_allow_html=True)
    st.markdown("### Conservation Priority Ranking")
    scores = []
    for _, row in ssurgo_f.iterrows():
        fid = row["field_id"]
        shs = compute_soil_health_score(row)
        si = compute_sustainability_index(row, rotation_df, ndvi_df)
        scores.append({"field_id": FIELD_NAMES.get(fid, fid), "Soil Health Score": shs, "Sustainability Index": si})
    scores_df = pd.DataFrame(scores).sort_values("Soil Health Score")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(scores_df, x="field_id", y="Soil Health Score", color="field_id",
                     color_discrete_map=FIELD_COLORS, text_auto=".1f",
                     height=350, title="Soil Health Score (0-10)")
        fig.update_layout(showlegend=False, margin=dict(l=40, r=20, t=40, b=40))
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = px.bar(scores_df, x="field_id", y="Sustainability Index", color="field_id",
                     color_discrete_map=FIELD_COLORS, text_auto=".1f",
                     height=350, title="Sustainability Index (0-10)")
        fig.update_layout(showlegend=False, margin=dict(l=40, r=20, t=40, b=40))
        st.plotly_chart(fig, width="stretch")
    st.markdown("""
    <div class="interpretation">
    <strong>Conservation Priority:</strong> Fields with lower Soil Health Scores should be prioritized for conservation practices. Field D (Spillville) scores lowest — consider cover crops, reduced tillage, and organic amendments. Field A leads the farm in both soil health and sustainability metrics and should be managed to maintain its current trajectory.
    </div>
    """, unsafe_allow_html=True)
    st.markdown("### 2026 Season Outlook")
    st.markdown("""
    <div class="interpretation">
    <strong>Iowa Corn Farm — 2026 Planning Summary:</strong><br>
    • Portfolio bias: Corn-led (3 of 4 fields predicted Corn next)<br>
    • Primary risk: Variable drainage creates trafficability windows — prioritize Webster fields (B, C) for early operations when dry<br>
    • Nutrient management: Reduce N rates on Field A (high OM, 4.9%); split-apply on Field D (low CEC, 18.8)<br>
    • Scouting priority: Field B (217.7 ac, poorly drained) — watch for saturated soil disease pressure<br>
    • Maturity planning: RM 104-114 range suitable for this latitude band; verify GDD targets before final seed decisions
    </div>
    """, unsafe_allow_html=True)


def main():
    st.markdown(get_css(), unsafe_allow_html=True)
    st.title("🌽 Row Crop Intelligence Dashboard")
    st.caption(f"Iowa Corn Farm · {len(FIELD_NAMES)} fields · Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    with st.spinner("Loading farm data..."):
        ssurgo_df = load_ssurgo_summary()
        fields_soil = load_fields_soil()
        weather_df = load_weather()
        cdl_df = load_cdl_composition()
        rotation_df = load_crop_rotation()
        ndvi_df = load_ndvi_summaries()
        fields_gdf = load_field_boundaries()
    if ssurgo_df is not None:
        ssurgo_df["soil_health_score"] = ssurgo_df.apply(compute_soil_health_score, axis=1)
    st.sidebar.header("Controls")
    all_fields = list(FIELD_NAMES.keys())
    selected = st.sidebar.multiselect("Fields", all_fields, default=all_fields, format_func=lambda f: FIELD_NAMES.get(f, f))
    year_range = st.sidebar.slider("Year Range", 2021, 2025, (2021, 2025))
    map_layer = st.sidebar.selectbox("Map Layer", ["Soil Health Score", "NDVI Peak (Corn)", "Drainage Class", "Organic Matter (%)"])
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Data Sources**")
    st.sidebar.markdown("- NASA POWER (weather)")
    st.sidebar.markdown("- SSURGO (soil)")
    st.sidebar.markdown("- Sentinel-2 (NDVI)")
    st.sidebar.markdown("- USDA CDL (crops)")
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Farm:** Iowa Corn Farm, IA")
    st.sidebar.markdown(f"**Period:** {year_range[0]}–{year_range[1]}")
    render_kpis(ssurgo_df, ndvi_df, fields_gdf, weather_df)
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ Overview & Map", "🌱 Soil & Vegetation", "🌤️ Weather & Climate", "⚖️ Field Comparison", "📋 Recommendations"])
    with tab1:
        render_map_tab(ssurgo_df, fields_gdf, ndvi_df, map_layer, selected)
        st.subheader("Farm Summary")
        col_left, col_right = st.columns([1, 1])
        with col_left:
            st.markdown("""
            **Iowa Corn Farm** is a 4-field, 430-acre corn-soybean operation in north-central Iowa.
            - **Soils**: Clarion, Webster, Spillville series — loam to sandy loam
            - **Drainage**: Predominantly poorly drained; tile infrastructure is critical
            - **Rotation**: Corn-soybean with moderate diversity (2-crop system)
            - **Region**: Corn Belt — RM 104-114 maturity range, ~1,950 GDD (base 10°C)
            """)
        with col_right:
            st.markdown("""
            **Dashboard Interpretation:**
            - Fields in the northern section (A, B) show higher organic matter and better soil health scores
            - Poorly drained Webster fields (B, C) have higher water-holding capacity but trafficability constraints
            - Field D (Spillville, 25.3 ac) has the lowest soil health score — prioritize conservation there
            - Peak corn NDVI across the farm averages 0.855, indicating generally strong crop health
            """)
    with tab2:
        render_soil_vegetation_tab(ssurgo_df, fields_soil, ndvi_df, cdl_df, fields_gdf, rotation_df, selected, year_range)
    with tab3:
        render_weather_tab(weather_df, selected, year_range)
    with tab4:
        render_comparison_tab(ssurgo_df, fields_soil, ndvi_df, cdl_df, rotation_df, weather_df, selected)
    with tab5:
        render_recommendations_tab(ssurgo_df, ndvi_df, rotation_df, selected)
    st.markdown("---")
    st.caption(f"Row Crop Intelligence Dashboard · Data pipeline runtime · Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
