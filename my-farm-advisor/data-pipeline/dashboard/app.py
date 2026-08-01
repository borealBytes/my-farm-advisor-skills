"""Row Crop Intelligence Dashboard — Streamlit Application.

Final Project: Row Crop Intelligence Data Dashboard
Built on Assignments 1–3 outputs from the My Farm Advisor data pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import (
    compute_kpis,
    compute_sustainability_score,
    load_boundaries,
    load_cdl_composition,
    load_crop_rotation,
    load_ndvi_joins,
    load_ssurgo_summary,
    load_weather,
)

st.set_page_config(
    page_title="Row Crop Intelligence Dashboard",
    page_icon="🌾",
    layout="wide",
)


# ── Data loading (cached) ──────────────────────────────────────────────────
@st.cache_data
def get_boundaries():
    return load_boundaries()


@st.cache_data
def get_weather():
    return load_weather()


@st.cache_data
def get_ssurgo():
    return load_ssurgo_summary()


@st.cache_data
def get_cdl():
    return load_cdl_composition()


@st.cache_data
def get_rotation():
    return load_crop_rotation()


@st.cache_data
def get_ndvi():
    return load_ndvi_joins()


@st.cache_data
def get_kpis():
    return compute_kpis()


# ── Page Title ─────────────────────────────────────────────────────────────
st.title("🌾 Row Crop Intelligence Dashboard")
st.markdown(
    "Final Project — Exploratory analysis of 30 fields across Illinois, Iowa, and Nebraska "
    "using data from Assignments 1–3 of the My Farm Advisor data pipeline."
)

# ── Sidebar Filters ────────────────────────────────────────────────────────
st.sidebar.header("Filters")
all_states = ["All", "Illinois", "Iowa", "Nebraska"]
selected_state = st.sidebar.selectbox("State", all_states)

boundaries_df = get_boundaries()
weather_df = get_weather()
ssurgo_df = get_ssurgo()
cdl_df = get_cdl()
rotation_df = get_rotation()
ndvi_df = get_ndvi()
kpis = get_kpis()


def filter_df(df: pd.DataFrame) -> pd.DataFrame:
    if selected_state != "All" and "state" in df.columns:
        return df[df["state"] == selected_state]
    return df


# ── KPI Section ────────────────────────────────────────────────────────────
st.header("📊 Key Performance Indicators")

filtered_bounds = filter_df(boundaries_df)
filtered_weather = filter_df(weather_df)
filtered_ssurgo = filter_df(ssurgo_df)
filtered_ndvi = filter_df(ndvi_df)

kpi_total_fields = len(filtered_bounds)
kpi_total_acreage = round(filtered_bounds["area_acres"].sum(), 1) if not filtered_bounds.empty and "area_acres" in filtered_bounds.columns else 0
kpi_avg_ndvi = round(filtered_ndvi[filtered_ndvi["scene_count"] > 0]["scene_count"].mean(), 1) if not filtered_ndvi.empty and "scene_count" in filtered_ndvi.columns else 0
kpi_avg_rainfall = round(filtered_weather["PRECTOTCORR"].mean(), 2) if not filtered_weather.empty and "PRECTOTCORR" in filtered_weather.columns else 0

if not filtered_ssurgo.empty:
    scores = filtered_ssurgo.apply(compute_sustainability_score, axis=1)
    kpi_sustainability = round(scores.mean(), 1)
else:
    kpi_sustainability = 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Fields", kpi_total_fields)
col2.metric("Total Acreage", f"{kpi_total_acreage:,.0f} ac")
col3.metric("Avg NDVI Scenes", kpi_avg_ndvi)
col4.metric("Avg Daily Rainfall", f"{kpi_avg_rainfall} mm")
col5.metric("Soil Sustainability", f"{kpi_sustainability}/100")

st.markdown(
    f"*The portfolio spans **{kpi_total_fields} fields** across three Corn Belt states "
    f"totaling **{kpi_total_acreage:,.0f} acres**. Each field has Sentinel-2 NDVI composites "
    f"for 2021–2025 (avg {kpi_avg_ndvi} scenes/field/year). Mean daily precipitation across "
    f"the dataset is {kpi_avg_rainfall} mm. The composite soil sustainability score of "
    f"{kpi_sustainability}/100 reflects SSURGO-derived organic matter, pH, CEC, water storage, "
    f"erosion risk, and drainage class.*"
)

# ── Exploratory Visualization 1: Field Size & Crop Composition ─────────────
st.header("🔍 Exploratory Analysis 1 — Field Sizes & Crop Composition")

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Field Size Distribution by State")
    if not filtered_bounds.empty and "area_acres" in filtered_bounds.columns:
        fig_sizes = px.box(
            filtered_bounds,
            x="state",
            y="area_acres",
            color="state",
            points="all",
            hover_data=["field_id", "county_name"],
            title="Field Acreage Distribution",
            labels={"area_acres": "Acres", "state": "State"},
        )
        fig_sizes.update_layout(showlegend=False)
        st.plotly_chart(fig_sizes, width="stretch")
    else:
        st.info("No boundary data available.")

with col_b:
    st.subheader("Crop Type Distribution (CDL 2021–2025)")
    if not cdl_df.empty:
        crop_summary = (
            cdl_df.groupby(["state", "crop_name"])["pct"]
            .mean()
            .reset_index()
            .rename(columns={"pct": "avg_pct"})
        )
        fig_crops = px.bar(
            crop_summary,
            x="state",
            y="avg_pct",
            color="crop_name",
            barmode="group",
            title="Average Crop Prevalence by State",
            labels={"avg_pct": "Avg % of Field", "crop_name": "Crop"},
        )
        st.plotly_chart(fig_crops, width="stretch")
    else:
        st.info("No CDL data available.")

st.markdown(
    "**Interpretation:** The field size boxplot reveals variability in farm management scale "
    "across the three states. Illinois and Iowa tend to have more uniform field sizes typical "
    "of row-crop agriculture, while Nebraska fields show greater variance due to irrigation "
    "and dryland farming differences. The crop composition chart confirms corn and soybeans "
    "dominate the portfolio, consistent with the Corn Belt region. CDL data spanning 5 years "
    "shows consistent crop allocation patterns across the grower operations."
)

# ── Exploratory Visualization 2: Crop Rotation Patterns ────────────────────
st.header("🔍 Exploratory Analysis 2 — Crop Rotation Patterns")

col_c, col_d = st.columns(2)

with col_c:
    st.subheader("Rotation Diversity by State")
    if not rotation_df.empty:
        diversity_by_state = (
            rotation_df.groupby("state")["crop_diversity"]
            .mean()
            .reset_index()
            .rename(columns={"crop_diversity": "avg_crop_diversity"})
        )
        fig_diversity = px.bar(
            diversity_by_state,
            x="state",
            y="avg_crop_diversity",
            color="state",
            title="Average Crop Diversity per Field",
            labels={"avg_crop_diversity": "Avg Crop Types", "state": "State"},
        )
        fig_diversity.update_layout(showlegend=False)
        st.plotly_chart(fig_diversity, width="stretch")
    else:
        st.info("No rotation data available.")

with col_d:
    st.subheader("Rotation Sequences")
    if not rotation_df.empty:
        top_rotations = (
            rotation_df.groupby(["state", "rotation_sequence"])
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
            .head(10)
        )
        fig_rot = px.bar(
            top_rotations,
            x="count",
            y="rotation_sequence",
            color="state",
            orientation="h",
            title="Most Common Rotation Patterns",
            labels={"count": "Field Count", "rotation_sequence": "Rotation"},
        )
        fig_rot.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_rot, width="stretch")
    else:
        st.info("No rotation data available.")

st.markdown(
    "**Interpretation:** Crop diversity metrics show that most fields follow a standard "
    "corn-soybean rotation, which is the dominant practice in the Corn Belt. This 2-year "
    "rotation pattern is visible across all three states. Fields with higher diversity scores "
    "indicate more complex rotations that may include wheat or other small grains, which can "
    "improve soil health and break pest cycles. The rotation confidence metric in the data "
    "suggests predictable planting patterns that support yield stability."
)

# ── Interactive Geospatial Map ─────────────────────────────────────────────
st.header("🗺️ Interactive Field Map")

if not filtered_bounds.empty:
    bounds_total = filtered_bounds.total_bounds
    center_lat = (bounds_total[1] + bounds_total[3]) / 2
    center_lon = (bounds_total[0] + bounds_total[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="OpenStreetMap")

    folium.TileLayer("Esri WorldImagery", name="Satellite").add_to(m)

    state_colors = {"Illinois": "blue", "Iowa": "green", "Nebraska": "red"}

    for _, row in filtered_bounds.iterrows():
        color = state_colors.get(row.get("state", ""), "gray")
        popup_html = (
            f"<b>Field:</b> {row.get('field_id', 'N/A')}<br>"
            f"<b>State:</b> {row.get('state', 'N/A')}<br>"
            f"<b>County:</b> {row.get('county_name', 'N/A')}<br>"
            f"<b>Area:</b> {row.get('area_acres', 0):.1f} acres<br>"
        )
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _, c=color: {
                "fillColor": c,
                "color": "black",
                "weight": 1.5,
                "fillOpacity": 0.4,
            },
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{row.get('field_id', '')} — {row.get('area_acres', 0):.0f} ac",
        ).add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, width=900, height=550)
else:
    st.info("No boundary data for map display.")

st.markdown(
    "**Interpretation:** The interactive map displays all 30 field boundaries across the "
    "three states. Fields are color-coded by state (blue=Illinois, green=Iowa, red=Nebraska). "
    "Clicking any polygon reveals field-level metadata including ID, county, and acreage. "
    "The satellite overlay option enables visual inspection of current land use and field "
    "conditions. Field sizes range from small research plots to large commercial operations "
    "typical of the Corn Belt."
)

# ── Weather / Climate Visualization ────────────────────────────────────────
st.header("🌦️ Weather & Climate Analysis")

if not filtered_weather.empty and "date" in filtered_weather.columns:
    filtered_weather = filtered_weather.copy()
    filtered_weather["year"] = filtered_weather["date"].dt.year
    filtered_weather["month"] = filtered_weather["date"].dt.month
    filtered_weather["month_name"] = filtered_weather["date"].dt.strftime("%b")

    col_e, col_f = st.columns(2)

    with col_e:
        st.subheader("Monthly Precipitation by Year")
        monthly_precip = (
            filtered_weather.groupby(["state", "year", "month"])["PRECTOTCORR"]
            .sum()
            .reset_index()
        )
        fig_precip = px.line(
            monthly_precip,
            x="month",
            y="PRECTOTCORR",
            color="year",
            facet_col="state",
            title="Monthly Total Precipitation (mm)",
            labels={"PRECTOTCORR": "Precip (mm)", "month": "Month"},
            markers=True,
        )
        st.plotly_chart(fig_precip, width="stretch")

    with col_f:
        st.subheader("Temperature Extremes (Annual)")
        annual_temp = (
            filtered_weather.groupby(["state", "year"])
            .agg(
                avg_tmax=("T2M_MAX", "mean"),
                avg_tmin=("T2M_MIN", "mean"),
                avg_temp=("T2M", "mean"),
            )
            .reset_index()
        )
        fig_temp = go.Figure()
        for state in annual_temp["state"].unique():
            state_data = annual_temp[annual_temp["state"] == state]
            fig_temp.add_trace(go.Scatter(
                x=state_data["year"], y=state_data["avg_tmax"],
                mode="lines+markers", name=f"{state} Max",
            ))
            fig_temp.add_trace(go.Scatter(
                x=state_data["year"], y=state_data["avg_tmin"],
                mode="lines+markers", name=f"{state} Min",
                line=dict(dash="dash"),
            ))
        fig_temp.update_layout(
            title="Annual Average Temperature Extremes",
            xaxis_title="Year", yaxis_title="Temperature (°C)",
        )
        st.plotly_chart(fig_temp, width="stretch")

    # Growing Degree Days
    st.subheader("Cumulative Growing Degree Days (GDD) — 2025 Season")
    gdd_weather = filtered_weather[filtered_weather["year"] == 2025].copy()
    if not gdd_weather.empty:
        gdd_weather["gdd_daily"] = np.maximum(
            0, (gdd_weather["T2M_MAX"] + gdd_weather["T2M_MIN"]) / 2.0 - 10.0
        )
        gdd_cum = gdd_weather.groupby(["state", "date"])["gdd_daily"].sum().reset_index()
        gdd_cum["gdd_cumulative"] = gdd_cum.groupby("state")["gdd_daily"].cumsum()
        fig_gdd = px.line(
            gdd_cum,
            x="date",
            y="gdd_cumulative",
            color="state",
            title="2025 Cumulative GDD (Base 10°C)",
            labels={"gdd_cumulative": "Cumulative GDD", "date": "Date"},
        )
        st.plotly_chart(fig_gdd, width="stretch")
    else:
        st.info("No 2025 weather data available for GDD calculation.")

    st.markdown(
        "**Interpretation:** Precipitation patterns show the typical midwestern climate with "
        "peak rainfall in May–July during the growing season. Temperature extremes indicate "
        "that all three states experience adequate heat units for corn and soybean production. "
        "The GDD accumulation curves for 2025 show that growing conditions track normal "
        "patterns, with Nebraska accumulating slightly fewer degree days due to its more "
        "continental climate. These weather patterns directly influence the NDVI trajectories "
        "observed in the satellite imagery analysis."
    )
else:
    st.info("No weather data available.")

# ── Soil Health / Sustainability Metric ────────────────────────────────────
st.header("🌱 Soil Health & Sustainability")

if not filtered_ssurgo.empty:
    col_g, col_h = st.columns(2)

    with col_g:
        st.subheader("Soil Property Radar by State")
        radar_cols = ["avg_om_pct", "avg_ph", "avg_cec", "total_aws_inches", "avg_clay_pct"]
        radar_labels = ["Organic Matter", "pH", "CEC", "Water Storage", "Clay %"]
        radar_data = filtered_ssurgo.groupby("state")[radar_cols].mean().reset_index()

        fig_radar = go.Figure()
        for _, row in radar_data.iterrows():
            values = [row[c] for c in radar_cols]
            # Normalize to 0-100 scale for radar
            max_vals = [6, 14, 40, 8, 50]
            norm_values = [min(v / m * 100, 100) for v, m in zip(values, max_vals)]
            norm_values.append(norm_values[0])  # close the polygon
            fig_radar.add_trace(go.Scatterpolar(
                r=norm_values,
                theta=radar_labels + [radar_labels[0]],
                fill="toself",
                name=row["state"],
            ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title="Average Soil Properties by State (Normalized)",
            showlegend=True,
        )
        st.plotly_chart(fig_radar, width="stretch")

    with col_h:
        st.subheader("Sustainability Score Distribution")
        filtered_ssurgo = filtered_ssurgo.copy()
        filtered_ssurgo["sustainability_score"] = filtered_ssurgo.apply(
            compute_sustainability_score, axis=1
        )
        fig_sustain = px.box(
            filtered_ssurgo,
            x="state",
            y="sustainability_score",
            color="state",
            points="all",
            hover_data=["field_id", "dominant_soil"],
            title="Soil Sustainability Score by State",
            labels={"sustainability_score": "Score (0–100)", "state": "State"},
        )
        fig_sustain.update_layout(showlegend=False)
        st.plotly_chart(fig_sustain, width="stretch")

    # Soil summary table
    st.subheader("Field-Level Soil Summary")
    display_cols = ["field_id", "state", "dominant_soil", "drainage_class",
                    "avg_om_pct", "avg_ph", "avg_cec", "total_aws_inches",
                    "erosion_risk", "sustainability_score"]
    if all(c in filtered_ssurgo.columns for c in display_cols):
        st.dataframe(
            filtered_ssurgo[display_cols].sort_values("sustainability_score", ascending=False),
            width="stretch",
        )

    st.markdown(
        "**Interpretation:** The soil sustainability score is a composite metric weighting "
        "organic matter (20%), pH balance (15%), cation exchange capacity (15%), available "
        "water storage (20%), erosion risk (15%), and drainage class (15%). Iowa soils tend "
        "to score higher due to the Clarion–Nicollet–Webster soil association with high "
        "organic matter and good water-holding capacity. Illinois soils show strong CEC values "
        "from the deep mollisols. Nebraska soils vary more due to the transition from "
        "subhumid to semi-arid conditions. The dominant soil series (Ipava, Clarion, Coly) "
        "are representative of productive Corn Belt agricultural land."
    )
else:
    st.info("No soil data available.")

# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "*Row Crop Intelligence Dashboard — Built with Streamlit. Data from My Farm Advisor "
    "Assignments 1–3. 30 fields across IL, IA, NE (2021–2025). Soil data from SSURGO. "
    "Weather from NASA POWER. Imagery from Sentinel-2. Crop data from USDA CDL.*"
)
