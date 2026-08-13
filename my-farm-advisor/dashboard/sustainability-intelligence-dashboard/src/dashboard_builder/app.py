#!/usr/bin/env python3
"""
Sustainability Intelligence Dashboard Builder v4

Generates a standalone HTML dashboard with:
- Plotly interactive charts (scatter, heatmap, boxplot, climatology, timeseries)
- Folium interactive map
- Grower-level analysis: reads the field inventory from the pipeline manifest
- No hardcoded field list — works for any farm with the expected runtime outputs
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import geopandas as gpd
from rasterstats import zonal_stats
from scipy import stats as sp_stats

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False


# =============================================================================
# Configuration
# =============================================================================
GROWER_SLUG = os.environ.get("AG_GROWER_SLUG", "iowa-grower")
FARM_SLUG = os.environ.get("AG_FARM_SLUG", "iowa-grower-iowa")
FARM_NAME = os.environ.get("AG_FARM_NAME", "Iowa Farm")

DATA_ROOT = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "/home/coder/my-farm-advisor-runtime")) / "data-pipeline"
FARM_DIR = DATA_ROOT / "growers" / GROWER_SLUG / "farms" / FARM_SLUG
OUTPUT_DIR = FARM_DIR / "derived" / "dashboards"

YEARS = [2021, 2022, 2023, 2024, 2025]

FIELD_COLORS = (
    px.colors.qualitative.Plotly
    + px.colors.qualitative.Dark24
    + px.colors.qualitative.Set1
)


def _load_field_inventory(farm_dir: Path) -> dict[str, str]:
    """Load field IDs from the pipeline manifest, keep only fields with NDVI composites, and assign friendly names."""
    fallback = {
        "osm-1360326432": "Field 1",
        "osm-1360386537": "Field 2",
        "osm-1360394834": "Field 3",
        "osm-1360386533": "Field 4",
        "osm-1360394843": "Field 5",
    }
    try:
        inventory_path = farm_dir / "manifests" / "field-inventory.csv"
        if inventory_path.exists():
            df = pd.read_csv(inventory_path)
            ids = sorted(df["field_id"].dropna().astype(str).unique().tolist())
            if ids:
                fields_with_ndvi = []
                for fid in ids:
                    field_dir = farm_dir / "fields" / fid
                    if any((field_dir / "derived" / "features" / f"ndvi_year_{year}_composite.tif").exists() for year in YEARS):
                        fields_with_ndvi.append(fid)
                if fields_with_ndvi:
                    return {fid: f"Field {i + 1}" for i, fid in enumerate(fields_with_ndvi)}
    except Exception as e:
        print(f"  Warning: could not load field inventory: {e}")
    return fallback


FIELD_MAP = _load_field_inventory(FARM_DIR)
FIELD_ORDER = list(FIELD_MAP.values())
FIELD_IDS = list(FIELD_MAP.keys())


# =============================================================================
# Data Loader
# =============================================================================
class DataLoader:
    def __init__(self, farm_dir: Path):
        self.farm_dir = farm_dir
        self.tables_dir = farm_dir / "derived" / "tables"
        self.fields_dir = farm_dir / "fields"
        self.field_map = FIELD_MAP
        self.field_ids = FIELD_IDS
        self.field_order = FIELD_ORDER

    def _tag_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "field_id" not in df.columns:
            return df
        df = df[df["field_id"].isin(self.field_ids)].copy()
        df["field_name"] = df["field_id"].map(self.field_map)
        sort_map = {f: i for i, f in enumerate(self.field_order)}
        df["_sort"] = df["field_name"].map(sort_map)
        df = df.sort_values("_sort").drop(columns="_sort")
        return df

    def load_boundaries(self) -> gpd.GeoDataFrame:
        gdfs = []
        for field_id, field_name in self.field_map.items():
            boundary_path = self.fields_dir / field_id / "boundary" / "field_boundary.geojson"
            if not boundary_path.exists():
                continue
            try:
                gdf = gpd.read_file(boundary_path)
                gdf["field_id"] = field_id
                gdf["field_name"] = field_name
                gdf_proj = gdf.to_crs("EPSG:5070")
                gdf["area_acres"] = gdf_proj.geometry.area / 4046.86
                gdfs.append(gdf)
            except Exception as e:
                print(f"  Warning: Could not load boundary for {field_name}: {e}")
        return gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True)) if gdfs else gpd.GeoDataFrame()

    def load_master_analytics(self) -> pd.DataFrame:
        """Primary integrated dataset. Falls back to separate tables if absent."""
        master_path = self.tables_dir / "field_master_analytics.csv"
        if master_path.exists():
            df = pd.read_csv(master_path)
            return self._tag_fields(df)

        # Fallback: merge separate SHI and NDVI tables
        shi = self._load_csv("field_soil_health_index.csv")
        ndvi = self._load_csv("field_ndvi_stability.csv")
        if shi.empty and ndvi.empty:
            return pd.DataFrame()
        if not shi.empty and not ndvi.empty:
            return shi.merge(ndvi, on="field_id", how="outer")
        return shi if not shi.empty else ndvi

    def _load_csv(self, name: str) -> pd.DataFrame:
        path = self.tables_dir / name
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        return self._tag_fields(df)

    def load_ndvi_yearly(self) -> pd.DataFrame:
        rows = []
        for field_id, field_name in self.field_map.items():
            field_dir = self.fields_dir / field_id
            for year in YEARS:
                tif_path = field_dir / "derived" / "features" / f"ndvi_year_{year}_composite.tif"
                if not tif_path.exists():
                    continue
                boundary_path = field_dir / "boundary" / "field_boundary.geojson"
                if not boundary_path.exists():
                    continue
                try:
                    gdf = gpd.read_file(boundary_path)
                    stats = zonal_stats(gdf, str(tif_path), stats=["mean", "max"], nodata=np.nan)
                    stat = stats[0]
                    rows.append({
                        "field_id": field_id,
                        "field_name": field_name,
                        "year": year,
                        "mean_ndvi": stat["mean"],
                        "peak_ndvi": stat["max"],
                    })
                except Exception:
                    pass
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def load_weather_summary(self) -> pd.DataFrame:
        return self._load_csv("field_weather_growing_season.csv")

    def load_weather_anomalies(self) -> pd.DataFrame:
        path = self.tables_dir / "farm_weather_anomalies.csv"
        if path.exists():
            return pd.read_csv(path)
        return pd.DataFrame()

    def load_ssurgo_geojsons(self) -> gpd.GeoDataFrame | None:
        layers = []
        for field_id, field_name in self.field_map.items():
            geojson_path = self.fields_dir / field_id / "soil" / "ssurgo_soil_types.geojson"
            csv_path = self.fields_dir / field_id / "soil" / "ssurgo_full.csv"
            if not geojson_path.exists():
                continue
            try:
                gdf = gpd.read_file(geojson_path)
                gdf["field_id"] = field_id
                gdf["field_name"] = field_name
                if csv_path.exists():
                    csv = pd.read_csv(csv_path)
                    if "mukey" in gdf.columns and "mukey" in csv.columns and "drainagecl" in csv.columns:
                        gdf["mukey"] = gdf["mukey"].astype(str)
                        csv["mukey"] = csv["mukey"].astype(str)
                        csv_agg = csv.groupby("mukey").agg({
                            "drainagecl": lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0],
                            "compname": lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0],
                        }).reset_index()
                        gdf = gdf.merge(csv_agg[["mukey", "drainagecl", "compname"]], on="mukey", how="left")
                layers.append(gdf)
            except Exception as e:
                print(f"  Warning: Could not load SSURGO for {field_name}: {e}")
        if not layers:
            return None
        return gpd.GeoDataFrame(pd.concat(layers, ignore_index=True))


# =============================================================================
# Chart Builder (Plotly -> HTML divs)
# =============================================================================
class ChartBuilder:
    def __init__(self, data: dict[str, Any], field_map: dict[str, str], field_colors: list[str]):
        self.data = data
        self.field_map = field_map
        self.field_colors = field_colors

    def _fig_to_html(self, fig: go.Figure) -> str:
        return fig.to_html(full_html=False, include_plotlyjs=False, div_id=f"chart_{id(fig)}")

    def _field_color(self, field_name: str) -> str:
        idx = list(self.field_map.values()).index(field_name) % len(self.field_colors)
        return self.field_colors[idx]

    def build_scatter(self) -> str | None:
        ndvi = self.data.get("ndvi_stability")
        if ndvi is None or ndvi.empty or "shi" not in ndvi.columns:
            return None

        df = ndvi[["field_id", "field_name", "shi", "cv_ndvi", "psi", "mean_ndvi"]].dropna()
        if df.empty:
            return None

        df["color"] = df["field_name"].apply(self._field_color)

        fig = go.Figure()
        for _, row in df.iterrows():
            fig.add_trace(go.Scatter(
                x=[row["shi"]],
                y=[row["cv_ndvi"]],
                mode="markers+text",
                name=row["field_name"],
                text=row["field_name"],
                textposition="top center",
                marker=dict(size=18, color=row["color"], line=dict(width=1, color="black")),
                hovertemplate=(
                    f"<b>{row['field_name']}</b><br>"
                    f"SHI: {row['shi']:.1f}<br>"
                    f"NDVI CV: {row['cv_ndvi']:.3f}<br>"
                    f"Mean NDVI: {row['mean_ndvi']:.3f}<extra></extra>"
                ),
            ))

        r2, r_spear, p_spear = 0, 0, 1
        if len(df) >= 3:
            z = np.polyfit(df["shi"], df["cv_ndvi"], 1)
            p = np.poly1d(z)
            x_line = np.linspace(df["shi"].min() - 2, df["shi"].max() + 2, 100)
            y_line = p(x_line)
            fig.add_trace(go.Scatter(
                x=x_line, y=y_line, mode="lines",
                name="OLS Trend", line=dict(color="red", dash="dash", width=2),
                hoverinfo="skip",
            ))
            y_pred = p(df["shi"])
            ss_res = np.sum((df["cv_ndvi"] - y_pred) ** 2)
            ss_tot = np.sum((df["cv_ndvi"] - df["cv_ndvi"].mean()) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            r_spear, p_spear = sp_stats.spearmanr(df["shi"], df["cv_ndvi"])

        fig.update_layout(
            title="Soil Health vs NDVI Stability",
            xaxis_title="Soil Health Index (SHI)",
            yaxis_title="NDVI Coefficient of Variation",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            margin=dict(l=60, r=40, t=60, b=80),
        )

        fig.add_annotation(
            x=0.02, y=0.98, xref="paper", yref="paper",
            text=f"R² = {r2:.3f}<br>Spearman r = {r_spear:.3f}<br>p = {p_spear:.3f}",
            showarrow=False, align="left", bgcolor="white", bordercolor="red",
            borderwidth=1, font=dict(size=11), xanchor="left", yanchor="top",
        )
        return self._fig_to_html(fig)

    def build_heatmap(self) -> str | None:
        shi = self.data.get("shi")
        if shi is None or shi.empty:
            return None

        components = ["om_score", "aws_score", "cec_score", "ph_score", "clay_score"]
        labels = ["OM", "AWS", "CEC", "pH", "Clay"]
        matrix = shi[components].values
        field_names = shi["field_name"].tolist()

        fig = go.Figure(data=go.Heatmap(
            z=matrix,
            x=labels,
            y=field_names,
            colorscale=[[0, "#d62728"], [0.5, "#ffdd44"], [1, "#2ca02c"]],
            zmin=0, zmax=100,
            text=[[f"{v:.1f}" for v in row] for row in matrix],
            texttemplate="%{text}",
            hovertemplate="Field: %{y}<br>Component: %{x}<br>Score: %{z:.1f}<extra></extra>",
        ))
        fig.update_layout(
            title="SHI Component Breakdown by Field",
            template="plotly_white",
            yaxis=dict(categoryorder="array", categoryarray=field_names),
            margin=dict(l=80, r=40, t=60, b=40),
        )
        return self._fig_to_html(fig)

    def build_boxplot(self) -> str | None:
        shi = self.data.get("shi")
        if shi is None or shi.empty:
            return None

        properties = [
            ("avg_om_pct", "Organic Matter (%)"),
            ("avg_ph", "pH"),
            ("total_aws_inches", "Available Water (in)"),
            ("avg_cec", "CEC (cmolc/kg)"),
            ("avg_clay_pct", "Clay (%)"),
        ]

        long_rows = []
        for _, row in shi.iterrows():
            for col, label in properties:
                long_rows.append({
                    "field_name": row["field_name"],
                    "property": label,
                    "value": row[col],
                })
        long_df = pd.DataFrame(long_rows)

        fig = px.box(
            long_df, x="property", y="value", color="field_name",
            points="all", title="Soil Property Distribution Across Fields",
            template="plotly_white",
            color_discrete_sequence=self.field_colors,
        )
        fig.update_layout(
            xaxis_title="",
            yaxis_title="Value",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
            margin=dict(l=60, r=40, t=60, b=100),
        )
        return self._fig_to_html(fig)

    def build_climatology(self) -> str | None:
        anomalies = self.data.get("weather_anomalies")
        ndvi_yearly = self.data.get("ndvi_yearly")
        if anomalies is None or anomalies.empty:
            return None

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        years = anomalies["year"].values
        precip = anomalies["avg_precip_anomaly"].values
        gdd = anomalies["avg_gdd_anomaly"].values

        bar_colors = []
        for v in precip:
            if v < -20:
                bar_colors.append("#d62728")
            elif v < -10:
                bar_colors.append("#ff7f0e")
            elif v > 25:
                bar_colors.append("#2ca02c")
            else:
                bar_colors.append("#1f77b4")

        fig.add_trace(go.Bar(
            x=years, y=precip, name="Precip Anomaly (%)",
            marker_color=bar_colors, text=[f"{v:.0f}%" for v in precip],
            textposition="outside",
        ), secondary_y=False)

        fig.add_trace(go.Scatter(
            x=years, y=gdd, mode="lines+markers+text", name="GDD Anomaly (%)",
            line=dict(color="darkorange", width=2),
            marker=dict(size=8),
            text=[f"{v:.0f}%" for v in gdd],
            textposition="top center",
        ), secondary_y=True)

        if ndvi_yearly is not None and not ndvi_yearly.empty:
            ndvi_avg = ndvi_yearly.groupby("year")["mean_ndvi"].mean().reset_index().sort_values("year")
            ndvi_scaled = ndvi_avg["mean_ndvi"].values * 100
            fig.add_trace(go.Scatter(
                x=ndvi_avg["year"].values, y=ndvi_scaled, mode="lines+markers",
                name="Avg NDVI (x100)", line=dict(color="green", dash="dash"),
                marker=dict(size=6),
            ), secondary_y=False)

        if "dominant_stress" in anomalies.columns:
            for _, row in anomalies.iterrows():
                if row["dominant_stress"] != "Normal":
                    fig.add_annotation(
                        x=row["year"], y=max(precip) + 5,
                        text=row["dominant_stress"], showarrow=False,
                        font=dict(size=10, color="black"), bgcolor="white",
                        bordercolor="gray", borderwidth=1,
                    )

        fig.update_xaxes(title_text="Year", tickmode="array", tickvals=years)
        fig.update_yaxes(title_text="Precip Anomaly (%) / NDVI (x100)", secondary_y=False)
        fig.update_yaxes(title_text="GDD Anomaly (%)", secondary_y=True)
        fig.update_layout(
            title="Growing Season Weather Anomalies vs NDVI (2021-2025)",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            margin=dict(l=60, r=60, t=60, b=80),
        )
        return self._fig_to_html(fig)

    def build_ndvi_timeseries(self) -> str | None:
        ndvi = self.data.get("ndvi_yearly")
        if ndvi is None or ndvi.empty:
            return None

        fig = go.Figure()
        for field_name in self.field_map.values():
            field_data = ndvi[ndvi["field_name"] == field_name].sort_values("year")
            if field_data.empty:
                continue
            color = self._field_color(field_name)
            fig.add_trace(go.Scatter(
                x=field_data["year"], y=field_data["mean_ndvi"],
                mode="lines+markers", name=field_name,
                line=dict(width=2, color=color),
                marker=dict(size=8, color=color),
                hovertemplate="%{fullData.name}<br>Year: %{x}<br>NDVI: %{y:.3f}<extra></extra>",
            ))

        fig.update_layout(
            title="Mean NDVI Trajectories by Field (2021-2025)",
            xaxis_title="Year", yaxis_title="Mean NDVI",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
            xaxis=dict(tickmode="array", tickvals=YEARS),
            yaxis=dict(range=[0, 1.0]),
            margin=dict(l=60, r=40, t=60, b=80),
        )
        fig.add_hline(y=0.5, line_dash="dash", line_color="gray", opacity=0.3)
        return self._fig_to_html(fig)


# =============================================================================
# Map Builder
# =============================================================================
class MapBuilder:
    def __init__(self, data: dict[str, Any], field_map: dict[str, str], field_colors: list[str]):
        self.data = data
        self.field_map = field_map
        self.field_colors = field_colors

    def build_map(self) -> folium.Map | None:
        if not HAS_FOLIUM:
            return None

        boundaries = self.data.get("boundaries")
        shi = self.data.get("shi")
        ssurgo = self.data.get("ssurgo_geojsons")
        ndvi = self.data.get("ndvi_yearly")

        if boundaries is None or boundaries.empty:
            return None

        bounds_proj = boundaries.to_crs("EPSG:5070")
        centroid = bounds_proj.geometry.centroid
        centroid_wgs = gpd.GeoSeries(centroid, crs="EPSG:5070").to_crs("EPSG:4326")
        center = [centroid_wgs.y.mean(), centroid_wgs.x.mean()]

        m = folium.Map(location=center, zoom_start=13, tiles=None)

        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True).add_to(m)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Esri Satellite",
            overlay=False,
            control=True,
        ).add_to(m)

        if shi is not None and not shi.empty:
            boundaries = boundaries.merge(shi[["field_id", "shi"]], on="field_id", how="left")

        fg_boundaries = folium.FeatureGroup(name="Field Boundaries (SHI)", show=True)

        for _, row in boundaries.iterrows():
            field_id = row["field_id"]
            field_name = row["field_name"]
            area = round(row.get("area_acres", 0), 1)
            shi_val = row.get("shi", 0)

            if pd.isna(shi_val):
                fill_color = "#999999"
            elif shi_val >= 70:
                fill_color = "#2ca02c"
            elif shi_val >= 50:
                fill_color = "#ffdd44"
            elif shi_val >= 30:
                fill_color = "#ff7f0e"
            else:
                fill_color = "#d62728"

            popup_html = f"""
            <div style="font-family: Arial; min-width: 200px;">
                <h4 style="margin: 0 0 8px 0; color: #2a5298;">{field_name}</h4>
                <b>ID:</b> {field_id}<br>
                <b>Area:</b> {area} acres<br>
                <b>SHI:</b> {shi_val:.1f}<br>
            """
            if ndvi is not None and not ndvi.empty:
                field_ndvi = ndvi[ndvi["field_id"] == field_id]
                if not field_ndvi.empty:
                    latest = field_ndvi[field_ndvi["year"] == field_ndvi["year"].max()]
                    if not latest.empty:
                        popup_html += f"<b>Latest NDVI:</b> {latest.iloc[0]['mean_ndvi']:.3f}<br>"
            popup_html += "</div>"

            geojson = folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda x, fc=fill_color: {
                    "fillColor": fc,
                    "color": "#333333",
                    "weight": 2,
                    "fillOpacity": 0.6,
                },
                highlight_function=lambda x: {"fillOpacity": 0.85, "weight": 3},
                popup=folium.Popup(popup_html, max_width=250),
            )
            geojson.add_to(fg_boundaries)

        fg_boundaries.add_to(m)

        # NDVI Layer - circle markers at centroids colored by NDVI
        fg_ndvi = folium.FeatureGroup(name="NDVI Values (2021-2025 Avg)", show=True)
        if boundaries is not None and not boundaries.empty and ndvi is not None and not ndvi.empty:
            ndvi_avg = ndvi.groupby("field_id")["mean_ndvi"].mean().reset_index()
            ndvi_avg = ndvi_avg.rename(columns={"mean_ndvi": "avg_ndvi"})
            boundaries_with_ndvi = boundaries.merge(ndvi_avg, on="field_id", how="left")

            for _, row in boundaries_with_ndvi.iterrows():
                field_id = row["field_id"]
                field_name = row["field_name"]
                ndvi_val = row.get("avg_ndvi", 0)

                centroid = row.geometry.centroid
                lat, lon = centroid.y, centroid.x

                if pd.isna(ndvi_val):
                    marker_color = "#999999"
                elif ndvi_val >= 0.75:
                    marker_color = "#2ca02c"
                elif ndvi_val >= 0.6:
                    marker_color = "#ffdd44"
                elif ndvi_val >= 0.45:
                    marker_color = "#ff7f0e"
                else:
                    marker_color = "#d62728"

                radius = 15 + (ndvi_val * 20) if not pd.isna(ndvi_val) else 15

                popup_html = f"""
                <div style="font-family: Arial; min-width: 150px;">
                    <h4 style="margin: 0 0 6px 0; color: #2a5298;">{field_name}</h4>
                    <b>Avg NDVI:</b> {ndvi_val:.3f}<br>
                </div>
                """

                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    popup=folium.Popup(popup_html, max_width=200),
                    tooltip=f"{field_name}: NDVI {ndvi_val:.3f}",
                    color="black",
                    weight=1,
                    fill=True,
                    fill_color=marker_color,
                    fill_opacity=0.7,
                ).add_to(fg_ndvi)

        fg_ndvi.add_to(m)

        # Field-level drainage layer (lightweight; replaces full SSURGO polygon layer)
        if shi is not None and not shi.empty and "drainage_class" in shi.columns:
            fg_drainage = folium.FeatureGroup(name="Field Drainage Class", show=False)
            drainage_colors = {
                "Well drained": "#2ca02c",
                "Moderately well drained": "#98df8a",
                "Somewhat poorly drained": "#ffbb78",
                "Poorly drained": "#ff7f0e",
                "Very poorly drained": "#d62728",
            }
            boundaries_drainage = boundaries.merge(shi[["field_id", "drainage_class"]], on="field_id", how="left")
            for _, row in boundaries_drainage.iterrows():
                drainage = row.get("drainage_class", "Unknown")
                color = drainage_colors.get(drainage, "#999999")
                geo = folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda x, c=color: {
                        "fillColor": c,
                        "color": "#555555",
                        "weight": 1,
                        "fillOpacity": 0.5,
                    },
                    tooltip=folium.Tooltip(f"{row['field_name']}<br>{drainage}"),
                )
                geo.add_to(fg_drainage)
            fg_drainage.add_to(m)

        legend_html = """
        <div id="dynamic-legend" style="position: absolute; bottom: 12px; left: 12px; z-index: 1000; background: white; padding: 8px 10px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-family: Arial; font-size: 10px; line-height: 1.4; max-width: 160px;">
            <div style="font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid #ddd; padding-bottom: 3px; font-size: 11px;">Map Legend</div>
            <div style="margin-bottom: 6px;">
                <div style="font-weight: 600; margin-bottom: 3px;">Field SHI</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#2ca02c; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> High (&ge;70)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ffdd44; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Moderate (50-69)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ff7f0e; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Low (30-49)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#d62728; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Very Low (&lt;30)</div>
            </div>
            <div style="margin-bottom: 6px;">
                <div style="font-weight: 600; margin-bottom: 3px;">NDVI (2021-2025 Avg)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#2ca02c; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> High (&ge;0.75)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ffdd44; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Moderate (0.60-0.74)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ff7f0e; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Low (0.45-0.59)</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#d62728; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Very Low (&lt;0.45)</div>
            </div>
            <div>
                <div style="font-weight: 600; margin-bottom: 3px;">Drainage Class</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#2ca02c; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Well drained</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#98df8a; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Mod. well</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ffbb78; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Somewhat poor</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#ff7f0e; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Poorly drained</div>
                <div><span style="display:inline-block; width:12px; height:12px; background:#d62728; border-radius:2px; vertical-align:middle; margin-right:5px;"></span> Very poorly</div>
            </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        folium.LayerControl(collapsed=False, position="topright").add_to(m)
        bounds = boundaries.total_bounds
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
        return m


# =============================================================================
# Dashboard Assembly
# =============================================================================
class DashboardBuilder:
    def __init__(self, farm_dir: Path, output_dir: Path, field_map: dict[str, str]):
        self.farm_dir = farm_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.field_map = field_map
        self.field_order = list(field_map.values())
        self.field_colors = FIELD_COLORS

    def build(self) -> Path:
        print("=" * 60)
        print("Building Sustainability Intelligence Dashboard v4")
        print("=" * 60)

        # Load
        print("\n[1/5] Loading data...")
        loader = DataLoader(self.farm_dir)
        master = loader.load_master_analytics()
        ndvi_stability = (
            master[master["cv_ndvi"].notna()].copy()
            if not master.empty and "cv_ndvi" in master.columns
            else pd.DataFrame()
        )
        data = {
            "boundaries": loader.load_boundaries(),
            "shi": master,
            "ndvi_stability": ndvi_stability,
            "ndvi_yearly": loader.load_ndvi_yearly(),
            "weather_summary": loader.load_weather_summary(),
            "weather_anomalies": loader.load_weather_anomalies(),
            "ssurgo_geojsons": loader.load_ssurgo_geojsons(),
        }
        print(f"  Boundaries: {len(data['boundaries'])} fields")
        print(f"  Master analytics: {len(data['shi'])} fields")
        print(f"  NDVI yearly: {len(data['ndvi_yearly'])} records")
        print(f"  SSURGO layers: {len(data['ssurgo_geojsons']) if data['ssurgo_geojsons'] is not None else 0} features")

        # Charts
        print("\n[2/5] Building Plotly charts...")
        cb = ChartBuilder(data, self.field_map, self.field_colors)
        charts = {
            "scatter": cb.build_scatter(),
            "heatmap": cb.build_heatmap(),
            "boxplot": cb.build_boxplot(),
            "climatology": cb.build_climatology(),
            "ndvi_timeseries": cb.build_ndvi_timeseries(),
        }
        for name, html in charts.items():
            print(f"  {name}: {'OK' if html else 'FAIL'}")

        # KPIs
        kpis = self._build_kpis(data)

        # Map
        print("\n[3/5] Building map...")
        mb = MapBuilder(data, self.field_map, self.field_colors)
        m = mb.build_map()
        map_html = m._repr_html_() if m else "<p>Map unavailable</p>"

        # Assemble
        print("\n[4/5] Assembling HTML...")
        html = self._assemble(kpis, map_html, charts, data)

        # Save
        print("\n[5/5] Saving...")
        out_path = self.output_dir / "sustainability_dashboard.html"
        out_path.write_text(html, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  Saved: {out_path} ({size_kb:.1f} KB)")

        return out_path

    def _build_kpis(self, data: dict) -> list[dict]:
        """Build compact KPI items."""
        boundaries = data.get("boundaries")
        master = data.get("shi")
        ndvi = data.get("ndvi_stability")
        weather = data.get("weather_summary")

        kpis = []

        if boundaries is not None and not boundaries.empty:
            kpis.append({"label": "Fields", "value": str(len(boundaries)), "unit": ""})
            kpis.append({"label": "Acres", "value": f"{boundaries['area_acres'].sum():.0f}", "unit": "ac"})

        if master is not None and not master.empty and "shi" in master.columns:
            kpis.append({"label": "Avg SHI", "value": f"{master['shi'].mean():.1f}", "unit": ""})
            best = master.loc[master["shi"].idxmax()]
            kpis.append({"label": "Best", "value": best["field_name"], "unit": f"SHI {best['shi']:.1f}"})

        if ndvi is not None and not ndvi.empty and "mean_ndvi" in ndvi.columns:
            kpis.append({"label": "Avg NDVI", "value": f"{ndvi['mean_ndvi'].mean():.3f}", "unit": ""})
            kpis.append({"label": "NDVI Fields", "value": str(ndvi["field_id"].nunique()), "unit": ""})

        if weather is not None and not weather.empty and "total_precip" in weather.columns:
            kpis.append({"label": "Precip", "value": f"{weather['total_precip'].mean():.0f}", "unit": "mm"})

        return kpis

    def _generate_natural_language_summary(self, data: dict) -> str:
        """Generate a natural language summary of findings."""
        boundaries = data.get("boundaries")
        master = data.get("shi")
        ndvi = data.get("ndvi_stability")
        ndvi_yearly = data.get("ndvi_yearly")
        weather_anomalies = data.get("weather_anomalies")

        total_fields = len(boundaries) if boundaries is not None else 0
        ndvi_fields = ndvi["field_id"].nunique() if ndvi is not None and not ndvi.empty else 0

        parts = []

        if boundaries is not None and not boundaries.empty:
            total_acres = boundaries["area_acres"].sum()
            parts.append(f"This sustainability intelligence dashboard analyzes <b>{total_fields} fields</b> covering <b>{total_acres:.0f} acres</b> across the 2021–2025 growing seasons.")

        if master is not None and not master.empty and "shi" in master.columns:
            shi_range = f"{master['shi'].min():.1f} to {master['shi'].max():.1f}"
            shi_mean = master['shi'].mean()
            best = master.loc[master["shi"].idxmax()]
            worst = master.loc[master["shi"].idxmin()]
            parts.append(f"Soil Health Index (SHI) scores range from <b>{shi_range}</b> (mean: {shi_mean:.1f}), with <b>{best['field_name']}</b> showing the strongest soil profile and <b>{worst['field_name']}</b> requiring attention.")

        if master is not None and ndvi is not None and not master.empty and not ndvi.empty:
            df = ndvi[["field_id", "field_name", "shi", "cv_ndvi", "mean_ndvi"]].dropna()
            if len(df) >= 3:
                r_cv, p_cv = sp_stats.spearmanr(df["shi"], df["cv_ndvi"])
                r_mean, p_mean = sp_stats.spearmanr(df["shi"], df["mean_ndvi"])

                best_field = df.loc[df["shi"].idxmax()]
                worst_field = df.loc[df["shi"].idxmin()]
                if worst_field["mean_ndvi"] > 0:
                    ndvi_advantage = ((best_field["mean_ndvi"] - worst_field["mean_ndvi"]) / worst_field["mean_ndvi"]) * 100
                    parts.append(f"Among the {len(df)} fields with NDVI coverage, fields with stronger soil health achieve higher average NDVI (productivity proxy). The highest-SHI field ({best_field['field_name']} at SHI {best_field['shi']:.1f}) delivers <b>{ndvi_advantage:.0f}% greater mean NDVI</b> than the lowest-SHI field ({worst_field['field_name']} at SHI {worst_field['shi']:.1f}).")

                if r_cv > 0 and p_cv < 0.05:
                    parts.append(f"Higher-SHI fields also show greater year-to-year NDVI variation (Spearman r = {r_cv:.3f}, p = {p_cv:.3f}), likely reflecting more responsive crop systems during the 2022–2023 drought years.")

        if ndvi is not None and not ndvi.empty:
            stable = ndvi.loc[ndvi["cv_ndvi"].idxmin()]
            unstable = ndvi.loc[ndvi["cv_ndvi"].idxmax()]
            parts.append(f"<b>{stable['field_name']}</b> demonstrates the highest productivity stability (CV = {stable['cv_ndvi']:.3f}), while <b>{unstable['field_name']}</b> shows the greatest inter-annual variability (CV = {unstable['cv_ndvi']:.3f}).")

        if weather_anomalies is not None and not weather_anomalies.empty:
            drought_years = weather_anomalies[weather_anomalies["avg_precip_anomaly"] < -15]
            wet_years = weather_anomalies[weather_anomalies["avg_precip_anomaly"] > 15]
            if not drought_years.empty:
                years = ", ".join([str(int(y)) for y in drought_years["year"].values])
                parts.append(f"Notable <b>drought stress</b> occurred in {years}, which may have overwhelmed soil buffering capacity in lower-SHI fields.")
            if not wet_years.empty:
                years = ", ".join([str(int(y)) for y in wet_years["year"].values])
                parts.append(f"Above-average precipitation in {years} supported stronger NDVI recovery across all fields.")

        if ndvi_yearly is not None and not ndvi_yearly.empty:
            yearly_avg = ndvi_yearly.groupby("year")["mean_ndvi"].mean()
            best_year = yearly_avg.idxmax()
            worst_year = yearly_avg.idxmin()
            parts.append(f"Across all fields, <b>{int(best_year)}</b> recorded the highest average NDVI ({yearly_avg[best_year]:.3f}), while <b>{int(worst_year)}</b> showed the lowest ({yearly_avg[worst_year]:.3f}).")

        # Note on partial NDVI coverage
        if total_fields > 0 and ndvi_fields > 0 and ndvi_fields < total_fields:
            parts.append(f"<b>Note:</b> NDVI composites are available for {ndvi_fields} of {total_fields} fields; the remaining {total_fields - ndvi_fields} fields are included in soil, weather, and map sections but omitted from NDVI-specific charts.")

        return " ".join(parts) if parts else "Analysis pending data loading."

    def _assemble(self, kpis: list, map_html: str, charts: dict, data: dict) -> str:
        kpi_items = ""
        for kpi in kpis:
            kpi_items += f"""
            <div class="kpi-item">
                <div class="kpi-value">{kpi['value']}</div>
                <div class="kpi-label">{kpi['label']}</div>
                <div class="kpi-unit">{kpi['unit']}</div>
            </div>"""

        chart_slides = []
        chart_nav = []
        chart_titles = {
            "scatter": "Soil Health vs NDVI Stability",
            "heatmap": "SHI Component Breakdown",
            "boxplot": "Soil Property Distribution",
            "climatology": "Weather Anomalies & NDVI",
            "ndvi_timeseries": "NDVI Trajectories (2021-2025)",
        }

        idx = 0
        for key in ["scatter", "heatmap", "boxplot", "climatology", "ndvi_timeseries"]:
            html = charts.get(key)
            if html:
                active = "active" if idx == 0 else ""
                chart_slides.append(f"""
                <div class="carousel-slide {active}" data-index="{idx}">
                    {html}
                    <div class="chart-caption">{chart_titles[key]}</div>
                </div>""")
                chart_nav.append(f"""<button class="nav-dot {'active' if idx == 0 else ''}" onclick="goTo({idx})"></button>""")
                idx += 1

        slides_html = "\n".join(chart_slides)
        nav_html = "\n".join(chart_nav)
        total_slides = idx

        master = data.get("shi")
        ndvi = data.get("ndvi_stability")
        corr_summary = ""
        if master is not None and ndvi is not None and not master.empty and not ndvi.empty:
            df = ndvi[["field_id", "shi", "cv_ndvi"]].dropna()
            if len(df) >= 3:
                r, p = sp_stats.spearmanr(df["shi"], df["cv_ndvi"])
                z = np.polyfit(df["shi"], df["cv_ndvi"], 1)
                p_ols = np.poly1d(z)
                y_pred = p_ols(df["shi"])
                ss_res = np.sum((df["cv_ndvi"] - y_pred) ** 2)
                ss_tot = np.sum((df["cv_ndvi"] - df["cv_ndvi"].mean()) ** 2)
                r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                direction = "lower" if r < 0 else "higher"
                corr_summary = f"Spearman r = {r:.3f} (p = {p:.3f}), OLS R² = {r2:.3f}. Fields with stronger soil health show <b>{direction}</b> NDVI volatility."

        nl_summary = self._generate_natural_language_summary(data)

        ndvi_yearly = data.get("ndvi_yearly")
        weather_anomalies = data.get("weather_anomalies")
        year_data_json = {}
        if ndvi_yearly is not None and not ndvi_yearly.empty:
            for year in YEARS:
                year_df = ndvi_yearly[ndvi_yearly["year"] == year]
                if not year_df.empty:
                    year_data_json[year] = {"fields": {}}
                    for _, row in year_df.iterrows():
                        year_data_json[year]["fields"][row["field_name"]] = {
                            "ndvi": round(row["mean_ndvi"], 3),
                            "peak": round(row["peak_ndvi"], 3) if pd.notna(row.get("peak_ndvi")) else None,
                        }

        if weather_anomalies is not None and not weather_anomalies.empty:
            for _, row in weather_anomalies.iterrows():
                year = int(row["year"])
                if year in year_data_json:
                    year_data_json[year]["precip_anomaly"] = round(row.get("avg_precip_anomaly", 0), 1)
                    year_data_json[year]["gdd_anomaly"] = round(row.get("avg_gdd_anomaly", 0), 1)
                    year_data_json[year]["stress"] = row.get("dominant_stress", "Normal")

        year_data_str = json.dumps(year_data_json)
        years_list_str = json.dumps(YEARS)
        field_order_str = json.dumps(self.field_order)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{FARM_NAME} — Sustainability Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #f0f2f5; margin: 0; display: flex; flex-direction: column; height: 100vh; }}

        .header-bar {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}
        .header-title h1 {{ margin: 0; font-size: 1.25rem; font-weight: 600; }}
        .header-title p {{ margin: 0; opacity: 0.85; font-size: 0.75rem; }}

        .kpi-bar {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}
        .kpi-item {{
            background: rgba(255,255,255,0.15);
            backdrop-filter: blur(4px);
            border-radius: 6px;
            padding: 6px 8px;
            text-align: center;
            width: 82px;
            height: 48px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .kpi-value {{ font-size: 1.1rem; font-weight: 700; color: #fff; line-height: 1.1; }}
        .kpi-label {{ font-size: 0.6rem; color: rgba(255,255,255,0.7); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}
        .kpi-unit {{ font-size: 0.6rem; color: rgba(255,255,255,0.5); }}

        .main-container {{
            flex: 1;
            display: flex;
            gap: 15px;
            padding: 15px 15px 0 15px;
            min-height: 0;
            overflow: hidden;
        }}
        .map-panel {{
            flex: 1.6;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            min-width: 0;
            min-height: 0;
        }}
        .map-header {{
            padding: 10px 15px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
            font-size: 0.85rem;
            font-weight: 600;
            color: #495057;
        }}
        .map-body {{
            flex: 1;
            position: relative;
            min-height: 0;
        }}
        .map-body iframe, .map-body .folium-map {{
            width: 100% !important;
            height: 100% !important;
        }}

        .expand-btn {{
            float: right;
            background: #2a5298;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 0.7rem;
            cursor: pointer;
            margin-left: 8px;
            transition: background 0.2s;
        }}
        .expand-btn:hover {{ background: #1e3c72; }}

        .map-expanded {{
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 10000 !important;
            border-radius: 0 !important;
            max-width: none !important;
        }}

        .time-slider-container {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px 15px;
        }}
        .time-slider-label {{
            font-size: 0.8rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
        }}
        .year-slider {{
            display: flex;
            gap: 6px;
            align-items: center;
        }}
        .year-btn {{
            flex: 1;
            padding: 6px 4px;
            border: 2px solid #dee2e6;
            background: white;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            color: #6c757d;
            cursor: pointer;
            transition: all 0.2s;
            text-align: center;
        }}
        .year-btn:hover {{ border-color: #2a5298; color: #2a5298; }}
        .year-btn.active {{
            background: #2a5298;
            border-color: #2a5298;
            color: white;
        }}
        .year-details {{
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e9ecef;
            font-size: 0.8rem;
        }}
        .year-details table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .year-details th, .year-details td {{
            padding: 4px 8px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }}
        .year-details th {{
            font-weight: 600;
            color: #2a5298;
            font-size: 0.75rem;
            text-transform: uppercase;
        }}
        .stress-badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
        }}
        .stress-drought {{ background: #fff3cd; color: #856404; }}
        .stress-wet {{ background: #d4edda; color: #155724; }}
        .stress-normal {{ background: #e2e3e5; color: #383d41; }}

        .nl-summary {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 15px;
            font-size: 0.85rem;
            line-height: 1.6;
            color: #495057;
        }}
        .nl-summary h3 {{
            font-size: 0.95rem;
            font-weight: 600;
            color: #2a5298;
            margin: 0 0 10px 0;
        }}

        .bottom-bar {{
            display: flex;
            gap: 15px;
            padding: 15px;
            flex-shrink: 0;
            min-height: 0;
            max-height: 35vh;
            align-items: stretch;
        }}
        .bottom-bar .time-slider-container {{
            flex: 1;
            min-width: 420px;
            max-width: 560px;
        }}
        .bottom-bar .nl-summary {{
            flex: 1.6;
            min-width: 0;
            max-height: 100%;
            overflow-y: auto;
        }}

        .chart-panel {{
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
            min-width: 420px;
            max-width: 560px;
        }}
        .carousel-container {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 15px;
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }}
        .carousel-viewport {{
            flex: 1;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 0;
        }}
        .carousel-slide {{
            display: none;
            width: 100%;
            height: 100%;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .carousel-slide.active {{ display: flex; }}
        .carousel-slide .plotly-graph-div {{
            width: 100% !important;
            height: 100% !important;
            min-height: 320px;
        }}
        .chart-caption {{
            font-size: 0.85rem;
            font-weight: 600;
            color: #495057;
            margin-top: 8px;
            text-align: center;
        }}

        .carousel-controls {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e9ecef;
        }}
        .carousel-btn {{
            background: #2a5298;
            color: white;
            border: none;
            border-radius: 50%;
            width: 32px;
            height: 32px;
            cursor: pointer;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }}
        .carousel-btn:hover {{ background: #1e3c72; }}
        .nav-dots {{ display: flex; gap: 6px; }}
        .nav-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            border: none;
            background: #ced4da;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .nav-dot.active {{ background: #2a5298; }}
        .slide-counter {{
            font-size: 0.75rem;
            color: #6c757d;
            min-width: 50px;
            text-align: center;
        }}

        .info-box {{
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 12px 15px;
            font-size: 0.8rem;
            color: #495057;
        }}
        .info-box strong {{ color: #2a5298; }}

        @media (max-width: 992px) {{
            body {{ height: auto; }}
            .main-container {{ flex-direction: column; height: auto; overflow: visible; }}
            .chart-panel {{ max-width: 100%; min-width: auto; }}
            .bottom-bar {{ flex-direction: column; }}
            .bottom-bar .time-slider-container {{ max-width: 100%; min-width: auto; }}
            .bottom-bar .nl-summary {{ flex: 1; }}
        }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div class="header-title">
            <h1>{FARM_NAME} — Sustainability Intelligence</h1>
            <p>Soil Health & Yield Stability | {len(FIELD_IDS)} Fields | 2021-2025</p>
        </div>
        <div class="kpi-bar">
            {kpi_items}
        </div>
    </div>

    <div class="main-container">
        <div class="map-panel">
                <div class="map-header">
                    <span style="margin-right: 10px;">&#127758;</span> Interactive Field Map
                    <button class="expand-btn" onclick="toggleMapExpand()">Expand</button>
                    <span style="float:right; font-weight:400; font-size:0.75rem; color:#6c757d; margin-right: 8px;">
                        Toggle layers (top-right) for drainage class & NDVI
                    </span>
                </div>
            <div class="map-body">
                {map_html}
            </div>
        </div>

        <div class="chart-panel">
            <div class="carousel-container">
                <div class="carousel-viewport">
                    {slides_html}
                </div>
                <div class="carousel-controls">
                    <button class="carousel-btn" onclick="prevSlide()">&#9664;</button>
                    <span class="slide-counter" id="slideCounter">1 / {total_slides}</span>
                    <div class="nav-dots">
                        {nav_html}
                    </div>
                    <button class="carousel-btn" onclick="nextSlide()">&#9654;</button>
                </div>
            </div>

            <div class="info-box">
                <strong>Key Finding:</strong> {corr_summary or "Correlation analysis pending."}<br>
                <strong>Method:</strong> SHI = 30% OM + 25% AWS + 20% CEC + 15% pH + 10% Clay + drainage adj.
                NDVI stability = inter-annual CV. Lower CV = more stable productivity.
            </div>
        </div>
    </div>

    <div class="bottom-bar">
        <div class="nl-summary">
            <h3>&#128221; Executive Summary</h3>
            <p>{nl_summary}</p>
        </div>

        <div class="time-slider-container">
            <div class="time-slider-label">&#128197; Year Explorer — Select a year to view field-specific NDVI and weather conditions</div>
            <div class="year-slider" id="yearSlider"></div>
            <div class="year-details" id="yearDetails">
                <div style="color: #6c757d; font-style: italic;">Select a year above to see detailed field NDVI values and weather anomalies.</div>
            </div>
        </div>
    </div>

    <script>
        // --- Chart Carousel ---
        let currentSlide = 0;
        const slides = document.querySelectorAll('.carousel-slide');
        const dots = document.querySelectorAll('.nav-dot');
        const counter = document.getElementById('slideCounter');
        const total = slides.length;

        function showSlide(index) {{
            slides.forEach((s, i) => s.classList.toggle('active', i === index));
            dots.forEach((d, i) => d.classList.toggle('active', i === index));
            if (counter) counter.textContent = (index + 1) + ' / ' + total;
            currentSlide = index;
        }}

        function nextSlide() {{ showSlide((currentSlide + 1) % total); }}
        function prevSlide() {{ showSlide((currentSlide - 1 + total) % total); }}
        function goTo(index) {{ showSlide(index); }}

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'ArrowRight') nextSlide();
            if (e.key === 'ArrowLeft') prevSlide();
        }});

        // --- Year Slider ---
        const yearData = {year_data_str};
        const years = {years_list_str};
        const fieldOrder = {field_order_str};
        let currentYear = years[years.length - 1];

        function initYearSlider() {{
            const container = document.getElementById('yearSlider');
            years.forEach(year => {{
                const btn = document.createElement('button');
                btn.className = 'year-btn' + (year === currentYear ? ' active' : '');
                btn.textContent = year;
                btn.onclick = () => selectYear(year);
                container.appendChild(btn);
            }});
            selectYear(currentYear);
        }}

        function selectYear(year) {{
            currentYear = year;
            document.querySelectorAll('.year-btn').forEach(btn => {{
                btn.classList.toggle('active', parseInt(btn.textContent) === year);
            }});

            const details = document.getElementById('yearDetails');
            const data = yearData[year];

            if (!data) {{
                details.innerHTML = '<div style="color: #6c757d; font-style: italic;">No data available for ' + year + '.</div>';
                return;
            }}

            let html = '<table><thead><tr><th>Field</th><th>Mean NDVI</th><th>Peak NDVI</th></tr></thead><tbody>';
            fieldOrder.forEach(field => {{
                if (data.fields && data.fields[field]) {{
                    const f = data.fields[field];
                    const ndviColor = f.ndvi >= 0.75 ? '#2ca02c' : f.ndvi >= 0.6 ? '#ff7f0e' : '#d62728';
                    html += '<tr><td><b>' + field + '</b></td><td style="color:' + ndviColor + '; font-weight:600;">' + f.ndvi.toFixed(3) + '</td><td>' + (f.peak ? f.peak.toFixed(3) : '—') + '</td></tr>';
                }} else {{
                    html += '<tr><td><b>' + field + '</b></td><td colspan="2" style="color:#6c757d; font-style:italic;">No NDVI composite available</td></tr>';
                }}
            }});
            html += '</tbody></table>';

            if (data.precip_anomaly !== undefined) {{
                const stressClass = data.stress === 'Drought' ? 'stress-drought' : data.stress === 'Wet' ? 'stress-wet' : 'stress-normal';
                html += '<div style="margin-top:8px; display:flex; gap:10px; align-items:center;">';
                html += '<span>Precip: <b>' + (data.precip_anomaly > 0 ? '+' : '') + data.precip_anomaly + '%</b></span>';
                html += '<span>GDD: <b>' + (data.gdd_anomaly > 0 ? '+' : '') + data.gdd_anomaly + '%</b></span>';
                html += '<span class="stress-badge ' + stressClass + '">' + data.stress + '</span>';
                html += '</div>';
            }}

            details.innerHTML = html;
        }}

        initYearSlider();

        // --- Map Full-Screen Toggle ---
        function toggleMapExpand() {{
            const panel = document.querySelector('.map-panel');
            panel.classList.toggle('map-expanded');
            const btn = document.querySelector('.expand-btn');
            btn.textContent = panel.classList.contains('map-expanded') ? 'Close' : 'Expand';

            // Give the browser time to resize, then invalidate the Leaflet map
            setTimeout(() => {{
                let leafletMap = null;
                for (let key in window) {{
                    if (key.startsWith('map_') && window[key] && window[key].invalidateSize) {{
                        leafletMap = window[key];
                        break;
                    }}
                }}
                if (leafletMap) leafletMap.invalidateSize();
            }}, 350);
        }}

    </script>
</body>
</html>"""
        return html


def main() -> None:
    farm_dir = FARM_DIR
    output_dir = OUTPUT_DIR

    if not farm_dir.exists():
        print(f"ERROR: Farm directory not found: {farm_dir}")
        sys.exit(1)

    builder = DashboardBuilder(farm_dir, output_dir, FIELD_MAP)
    output_path = builder.build()

    print(f"\n{'='*60}")
    print(f"Dashboard complete!")
    print(f"Open: {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
