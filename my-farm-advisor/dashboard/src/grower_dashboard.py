#!/usr/bin/env python3
"""
grower_dashboard.py — Multi-Grower Field Intelligence Dashboard v4

Changes from v3:
  - 3 separate maps per grower (full width, colored by SHS, black outlines)
  - Soil particle size distribution (grouped bars) + NDVI ranking only
  - Weather by DOY (not monthly) for all 3 growers
  - GDD by grower (no crop stages)
  - Meaningful sustainability metrics with calculation method shown
  - 5 data-driven bullet highlights
"""

from __future__ import annotations

import argparse
import base64
import io
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


def load_all_growers(data_root: Path, year_focus: int = 2024) -> dict[str, Any]:
    all_boundaries, all_soil, all_weather, all_ndvi = [], [], [], []
    grower_names = {"ia-grower": "Iowa", "il-grower": "Illinois", "ne-grower": "Nebraska"}
    for grower_slug, state_name in grower_names.items():
        farm_slug = discover_farm_slug(data_root, grower_slug)
        if not farm_slug:
            continue
        print(f"[Loader] Loading {grower_slug} ({state_name})...")
        data = build_integrated_dataset(data_root, grower_slug, farm_slug, year_focus)
        if data["boundaries"] is not None:
            b = data["boundaries"].copy()
            b["grower"] = state_name
            all_boundaries.append(b)
        if data["soil"] is not None:
            s = data["soil"].copy()
            s["grower"] = state_name
            all_soil.append(s)
        if data["weather"] is not None:
            w = data["weather"].copy()
            w["grower"] = state_name
            all_weather.append(w)
        ndvi = extract_all_field_ndvi(data_root, grower_slug, farm_slug)
        if not ndvi.empty:
            ndvi["grower"] = state_name
            all_ndvi.append(ndvi)
    combined = {
        "boundaries": pd.concat(all_boundaries, ignore_index=True) if all_boundaries else None,
        "soil": pd.concat(all_soil, ignore_index=True) if all_soil else None,
        "weather": pd.concat(all_weather, ignore_index=True) if all_weather else None,
        "ndvi": pd.concat(all_ndvi, ignore_index=True) if all_ndvi else pd.DataFrame(),
        "year_focus": year_focus,
    }
    print(f"[Loader] Combined: {len(combined['boundaries'])} fields total")
    return combined


def build_map_per_grower(boundaries: pd.DataFrame, metrics_df: pd.DataFrame) -> str:
    import geopandas as gpd
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    growers = ["Iowa", "Illinois", "Nebraska"]
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    for ax, grower in zip(axes, growers):
        gdf = boundaries[boundaries["grower"] == grower].copy()
        if len(gdf) == 0:
            ax.text(0.5, 0.5, f"No data for {grower}", ha="center", va="center", transform=ax.transAxes)
            continue
        gdf = gdf.merge(metrics_df[["field_id", "shs"]], on="field_id", how="left")
        gdf.plot(
            column="shs", cmap="RdYlGn", linewidth=2.0, edgecolor="black",
            alpha=0.7, ax=ax, vmin=0, vmax=100, legend=False,
        )
        for _, row in gdf.iterrows():
            centroid = row.geometry.centroid
            short_id = row["field_id"].replace("osm-", "")[-6:]
            ax.text(
                centroid.x, centroid.y, short_id, fontsize=6, ha="center", va="center",
                color="black", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor="none"),
            )
        ax.set_title(f"{grower}\n({len(gdf)} fields)", fontsize=12, fontweight="bold", color=grower_colors.get(grower, "black"))
        ax.set_xlabel("Longitude", fontsize=8)
        ax.set_ylabel("Latitude", fontsize=8)
        ax.grid(True, alpha=0.3, linestyle="--")
    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=0, vmax=100))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal", pad=0.05, shrink=0.6, aspect=40)
    cbar.set_label("Soil Health Score", fontsize=10)
    fig.suptitle("Field Boundaries by Grower (Colored by Soil Health Score)", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.08, 1, 0.95])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def build_dashboard(data: dict[str, Any], output_dir: Path) -> str:
    year_focus = data["year_focus"]
    boundaries = data["boundaries"]
    soil_raw = data["soil"]
    weather = data["weather"]
    ndvi_df = data["ndvi"]

    print(f"[Dashboard] Building for {len(boundaries)} fields")

    # === METRICS ===
    soil_scores = compute_soil_health_score(soil_raw)
    soil_scores = soil_scores.merge(
        boundaries[["field_id", "area_acres", "grower"]], on="field_id", how="left"
    )
    rotation_div = compute_rotation_diversity({})
    weather_stress = compute_weather_stress(weather)
    ndvi_stability = compute_ndvi_stability(ndvi_df)
    sustainability = compute_sustainability_index(soil_scores, rotation_div, weather_stress, ndvi_stability)
    metrics_df = soil_scores.merge(
        sustainability.drop(columns=["shs"], errors="ignore"), on="field_id", how="left"
    )

    # KPIs
    total_fields = len(boundaries)
    total_acres = boundaries["area_acres"].sum()
    avg_shs = metrics_df["shs"].mean()
    avg_si = metrics_df["si"].mean()
    year_ndvi = ndvi_df[ndvi_df["year"] == year_focus] if not ndvi_df.empty else pd.DataFrame()
    avg_ndvi = year_ndvi["mean_ndvi"].mean() if not year_ndvi.empty else 0.0
    w2024 = weather[weather["year"] == year_focus].copy() if weather is not None else pd.DataFrame()
    avg_rain = w2024["PRECTOTCORR"].sum() / len(boundaries.groupby("grower")) if not w2024.empty else 0.0

    # === MAP ===
    print("[Dashboard] Building 3-grower map...")
    map_base64 = build_map_per_grower(boundaries, metrics_df)

    # === SOIL TEXTURE (grouped bars by grower) ===
    print("[Dashboard] Building soil texture chart...")
    texture_data = soil_scores.groupby("grower").agg({
        "clay_mean": "mean", "sand_mean": "mean", "silt_mean": "mean",
    }).reset_index()
    texture_fig = go.Figure()
    colors = {"clay": "#8d6e63", "sand": "#ffcc80", "silt": "#b0bec5"}
    for particle, color in colors.items():
        texture_fig.add_trace(go.Bar(
            name=particle.capitalize(), x=texture_data["grower"],
            y=texture_data[f"{particle}_mean"], marker_color=color,
            text=[f"{v:.1f}%" for v in texture_data[f"{particle}_mean"]], textposition="auto",
        ))
    texture_fig.update_layout(
        barmode="group", title="Soil Particle Size Distribution by Grower (%)",
        yaxis_title="Percentage (%)", height=420,
        margin=dict(l=60, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # === NDVI RANKING (fix text artifact) ===
    print("[Dashboard] Building NDVI chart...")
    if not year_ndvi.empty:
        ndvi_sorted = year_ndvi.sort_values("mean_ndvi", ascending=True)
        ndvi_sorted["short_id"] = ndvi_sorted["field_id"].str.replace("osm-", "")
        ndvi_fig = px.bar(
            ndvi_sorted, x="mean_ndvi", y="short_id", orientation="h", color="grower",
            color_discrete_map={"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"},
            labels={"mean_ndvi": f"Mean NDVI ({year_focus})", "short_id": "Field ID"},
            title=f"NDVI Performance by Field — {year_focus}",
        )
        for i, row in ndvi_sorted.iterrows():
            ndvi_fig.add_annotation(
                x=row["mean_ndvi"], y=row["short_id"], text=f"{row['mean_ndvi']:.3f}",
                showarrow=False, xanchor="left", font=dict(size=9), xshift=5,
            )
        ndvi_fig.update_layout(height=500, margin=dict(l=80, r=60, t=60, b=40), showlegend=True)
    else:
        ndvi_fig = go.Figure().update_layout(title="No NDVI data", height=420)

    # === WEATHER BY DOY (all growers) ===
    print("[Dashboard] Building weather chart...")
    if not w2024.empty:
        w2024["date"] = pd.to_datetime(w2024["date"])
        w2024["doy"] = w2024["date"].dt.dayofyear
        daily_grower = w2024.groupby(["doy", "grower"]).agg({
            "PRECTOTCORR": "mean", "T2M": "mean",
        }).reset_index()
        weather_fig = make_subplots(specs=[[{"secondary_y": True}]])
        grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
        for grower in sorted(daily_grower["grower"].unique()):
            gdata = daily_grower[daily_grower["grower"] == grower].sort_values("doy")
            gdata["precip_smooth"] = gdata["PRECTOTCORR"].rolling(window=7, min_periods=1).mean()
            weather_fig.add_trace(go.Scatter(
                x=gdata["doy"], y=gdata["precip_smooth"], mode="lines",
                name=f"{grower} Precip (mm)", line=dict(color=grower_colors.get(grower, "gray"), width=2),
                opacity=0.7,
            ), secondary_y=False)
            weather_fig.add_trace(go.Scatter(
                x=gdata["doy"], y=gdata["T2M"], mode="lines",
                name=f"{grower} Temp (°C)", line=dict(color=grower_colors.get(grower, "gray"), width=2, dash="dash"),
                opacity=0.5,
            ), secondary_y=True)
        weather_fig.update_layout(
            title=f"Daily Precipitation & Temperature by Day of Year — {year_focus}",
            height=450, margin=dict(l=60, r=60, t=60, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        )
        weather_fig.update_yaxes(title_text="Precipitation (mm, 7-day avg)", secondary_y=False)
        weather_fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True)
    else:
        weather_fig = go.Figure().update_layout(title="No weather data", height=420)

    # === GDD BY GROWER (no crop stages) ===
    print("[Dashboard] Building GDD chart...")
    if not w2024.empty and "T2M_MAX" in w2024.columns and "T2M_MIN" in w2024.columns:
        w2024["gdd_daily"] = ((w2024["T2M_MAX"] + w2024["T2M_MIN"]) / 2 - 10).clip(lower=0)
        gdd_grower = w2024.groupby(["date", "grower"]).agg({"gdd_daily": "mean"}).reset_index()
        gdd_grower["date"] = pd.to_datetime(gdd_grower["date"])
        gdd_grower["doy"] = gdd_grower["date"].dt.dayofyear
        gdd_grower = gdd_grower.sort_values(["grower", "doy"])
        gdd_grower["gdd_cum"] = gdd_grower.groupby("grower")["gdd_daily"].cumsum()

        gdd_fig = go.Figure()
        for grower in sorted(gdd_grower["grower"].unique()):
            gdata = gdd_grower[gdd_grower["grower"] == grower]
            gdd_fig.add_trace(go.Scatter(
                x=gdata["doy"], y=gdata["gdd_cum"], mode="lines",
                name=f"{grower} GDD", line=dict(color=grower_colors.get(grower, "gray"), width=2),
            ))
        gdd_fig.update_layout(
            title=f"Cumulative Growing Degree Days by Grower — {year_focus}",
            xaxis_title="Day of Year", yaxis_title="Cumulative GDD (°C, base 10°C)",
            height=450, margin=dict(l=60, r=40, t=60, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        )
    else:
        gdd_fig = go.Figure().update_layout(title="No GDD data", height=420)

    # === MEANINGFUL METRICS TABLE ===
    print("[Dashboard] Building metrics table...")
    metric_rows = []
    for grower in ["Iowa", "Illinois", "Nebraska"]:
        gdf = metrics_df[metrics_df["grower"] == grower]
        if len(gdf) == 0:
            continue
        metric_rows.append({
            "Grower": grower,
            "Fields": len(gdf),
            "Avg SHS": f"{gdf['shs'].mean():.1f}",
            "SHS Calculation": "(pH*0.2 + OM*4 + CEC/3 + (100-sand)*0.3 + drainage*5)/10",
            "Avg SI": f"{gdf['si'].mean():.1f}",
            "SI Calculation": "(SHS*0.35 + rotation_diversity*0.2 + (1-weather_stress)*0.25 + ndvi_stability*0.2)*100",
            "Avg NDVI": f"{gdf['ndvi_stability'].mean():.3f}" if "ndvi_stability" in gdf.columns else "N/A",
            "Weather Stress": f"{gdf['weather_stress'].mean():.3f}" if "weather_stress" in gdf.columns else "N/A",
        })
    metrics_table_df = pd.DataFrame(metric_rows)

    # === 5 DATA-DRIVEN BULLET HIGHLIGHTS ===
    print("[Dashboard] Generating highlights...")
    highlights = []
    # 1. Best/worst SHS
    best = metrics_df.loc[metrics_df["shs"].idxmax()]
    worst = metrics_df.loc[metrics_df["shs"].idxmin()]
    highlights.append(f"Soil health ranges from {worst['shs']:.1f} ({worst['field_id']}) to {best['shs']:.1f} ({best['field_id']}) — a {best['shs']-worst['shs']:.1f} point gap across {len(metrics_df)} fields.")
    # 2. Grower comparison
    shs_by_grower = metrics_df.groupby("grower")["shs"].mean().sort_values(ascending=False)
    highlights.append(f"{shs_by_grower.index[0]} leads in average soil health ({shs_by_grower.iloc[0]:.1f}), while {shs_by_grower.index[-1]} trails at {shs_by_grower.iloc[-1]:.1f}.")
    # 3. NDVI
    if not year_ndvi.empty:
        ndvi_by_grower = year_ndvi.groupby("grower")["mean_ndvi"].mean().sort_values(ascending=False)
        highlights.append(f"{ndvi_by_grower.index[0]} shows highest vegetation vigor (NDVI {ndvi_by_grower.iloc[0]:.3f}), indicating stronger crop biomass than {ndvi_by_grower.index[-1]} ({ndvi_by_grower.iloc[-1]:.3f}).")
    else:
        highlights.append("NDVI data unavailable for 2024 season.")
    # 4. Weather
    if not w2024.empty:
        total_precip = w2024.groupby("grower")["PRECTOTCORR"].sum().sort_values(ascending=False)
        highlights.append(f"{total_precip.index[0]} received the most rainfall in 2024 ({total_precip.iloc[0]:.0f}mm total), while {total_precip.index[-1]} had the driest season ({total_precip.iloc[-1]:.0f}mm).")
    else:
        highlights.append("Weather data unavailable for 2024 season.")
    # 5. Total area & sustainability
    acres_by_grower = boundaries.groupby("grower")["area_acres"].sum().sort_values(ascending=False)
    si_by_grower = metrics_df.groupby("grower")["si"].mean().sort_values(ascending=False)
    highlights.append(f"Combined {total_acres:.0f} acres monitored. {si_by_grower.index[0]} scores highest sustainability index ({si_by_grower.iloc[0]:.1f}) due to balanced soil, weather, and vegetation metrics.")

    # === FULL DATA TABLE ===
    full_table = metrics_df[["field_id", "grower", "area_acres", "shs", "si"]].copy()
    if not year_ndvi.empty:
        full_table = full_table.merge(
            year_ndvi[["field_id", "mean_ndvi"]], on="field_id", how="left"
        )
    full_table = full_table.rename(columns={
        "field_id": "Field ID", "grower": "Grower", "area_acres": "Area (ac)",
        "shs": "Soil Health", "si": "Sustainability", "mean_ndvi": "NDVI 2024",
    }).round({"Area (ac)": 1, "Soil Health": 1, "Sustainability": 1, "NDVI 2024": 3})

    # === RENDER HTML ===
    print("[Dashboard] Rendering HTML...")
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Field Intelligence Dashboard — {year_focus}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body {{ font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #1a5f2a 0%, #2e7d32 100%); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.header h1 {{ margin: 0 0 8px 0; font-size: 28px; font-weight: 700; }}
.header p {{ margin: 0; opacity: 0.9; font-size: 15px; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 24px; }}
.kpi-card {{ background: white; border-radius: 10px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-top: 4px solid #4caf50; }}
.kpi-value {{ font-size: 32px; font-weight: 700; color: #2e7d32; margin: 8px 0; }}
.kpi-label {{ font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
.row {{ display: flex; gap: 20px; margin-bottom: 20px; }}
.row-full {{ display: block; margin-bottom: 20px; }}
.panel {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); flex: 1; min-width: 0; }}
.panel-full {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.panel h3 {{ margin: 0 0 16px 0; font-size: 16px; color: #1a5f2a; border-bottom: 2px solid #e8f5e9; padding-bottom: 8px; }}
.map-img {{ width: 100%; border-radius: 8px; }}
.highlights {{ background: white; border-radius: 10px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; }}
.highlights h3 {{ margin: 0 0 16px 0; font-size: 16px; color: #1a5f2a; }}
.highlights ul {{ margin: 0; padding-left: 20px; }}
.highlights li {{ margin-bottom: 12px; line-height: 1.6; font-size: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #f1f8e9; font-weight: 600; color: #1a5f2a; position: sticky; top: 0; }}
tr:hover {{ background: #f9f9f9; }}
.table-wrap {{ max-height: 400px; overflow-y: auto; border-radius: 8px; border: 1px solid #e0e0e0; }}
.metrics-explanation {{ font-size: 12px; color: #666; margin-top: 12px; line-height: 1.5; background: #fafafa; padding: 12px; border-radius: 6px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🌾 Field Intelligence Dashboard</h1>
    <p>{total_fields} fields across 3 growers (Iowa, Illinois, Nebraska) | {total_acres:.0f} acres | Focus year: {year_focus}</p>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-label">Total Fields</div><div class="kpi-value">{total_fields}</div></div>
    <div class="kpi-card"><div class="kpi-label">Total Acres</div><div class="kpi-value">{total_acres:.0f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg NDVI</div><div class="kpi-value">{avg_ndvi:.3f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg Rainfall</div><div class="kpi-value">{avg_rain:.0f}mm</div></div>
    <div class="kpi-card"><div class="kpi-label">Avg Soil Health</div><div class="kpi-value">{avg_shs:.1f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Sustainability</div><div class="kpi-value">{avg_si:.1f}</div></div>
  </div>

  <div class="row-full">
    <div class="panel-full">
      <h3>Field Boundaries by Grower (Colored by Soil Health Score)</h3>
      <img class="map-img" src="data:image/png;base64,{map_base64}" alt="Field Map">
    </div>
  </div>

  <div class="row">
    <div class="panel" id="soil-texture-panel"></div>
    <div class="panel" id="ndvi-panel"></div>
  </div>

  <div class="row">
    <div class="panel" id="weather-panel"></div>
    <div class="panel" id="gdd-panel"></div>
  </div>

  <div class="row-full">
    <div class="panel-full">
      <h3>Sustainability Metrics by Grower (How They're Calculated)</h3>
      <div class="table-wrap">
        {metrics_table_df.to_html(index=False, classes='metrics-table', border=0)}
      </div>
      <div class="metrics-explanation">
        <strong>Soil Health Score (SHS):</strong> Normalized weighted index of pH (20%), organic matter (40%), CEC (10%), texture/sand (30%), and drainage (5%), scaled 0-100.<br>
        <strong>Sustainability Index (SI):</strong> Composite score weighing SHS (35%), crop rotation diversity (20%), weather stress resilience (25%), and NDVI stability (20%).<br>
        <strong>Weather Stress:</strong> Proportion of days with temperature >35°C or precipitation <1mm during growing season (May-Aug). Lower is better.<br>
        <strong>NDVI Stability:</strong> Mean NDVI divided by its coefficient of variation across the season. Higher means more consistent vegetation vigor.
      </div>
    </div>
  </div>

  <div class="highlights">
    <h3>🔑 Key Highlights</h3>
    <ul>
      <li>{highlights[0]}</li>
      <li>{highlights[1]}</li>
      <li>{highlights[2]}</li>
      <li>{highlights[3]}</li>
      <li>{highlights[4]}</li>
    </ul>
  </div>

  <div class="row-full">
    <div class="panel-full">
      <h3>Complete Field Data Table</h3>
      <div class="table-wrap">
        {full_table.to_html(index=False, border=0, na_rep="—")}
      </div>
    </div>
  </div>
</div>

<script>
  var soilData = {texture_fig.to_json()};
  var ndviData = {ndvi_fig.to_json()};
  var weatherData = {weather_fig.to_json()};
  var gddData = {gdd_fig.to_json()};
  Plotly.newPlot('soil-texture-panel', soilData.data, soilData.layout, {{responsive: true}});
  Plotly.newPlot('ndvi-panel', ndviData.data, ndviData.layout, {{responsive: true}});
  Plotly.newPlot('weather-panel', weatherData.data, weatherData.layout, {{responsive: true}});
  Plotly.newPlot('gdd-panel', gddData.data, gddData.layout, {{responsive: true}});
</script>
</body>
</html>'''

    out_path = output_dir / "grower_dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"[Dashboard] Saved to {out_path} ({len(html)/1024:.0f} KB)")
    return str(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multi-grower field intelligence dashboard")
    parser.add_argument("--data-root", type=Path, default=Path("/home/coder/my-farm-advisor-runtime/data-pipeline"))
    parser.add_argument("--output-dir", type=Path, default=Path("/home/coder/my-farm-advisor-runtime/data-pipeline/growers/all/derived/reports"))
    parser.add_argument("--year", type=int, default=2024)
    args = parser.parse_args()

    data = load_all_growers(args.data_root, args.year)
    if data["boundaries"] is None or data["boundaries"].empty:
        print("[Error] No boundary data found.")
        sys.exit(1)

    build_dashboard(data, args.output_dir)


if __name__ == "__main__":
    main()
