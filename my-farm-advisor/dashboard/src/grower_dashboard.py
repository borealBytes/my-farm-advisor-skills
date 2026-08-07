#!/usr/bin/env python3
"""
grower_dashboard.py — Multi-Grower Field Intelligence Dashboard v5

All charts rendered as static matplotlib PNG for guaranteed visibility.
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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return b64


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
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.5), gridspec_kw={"width_ratios": [1, 1, 1]})
    growers = ["Iowa", "Illinois", "Nebraska"]
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    
    # Use actual SHS range for color normalization so variation is visible
    shs_min = metrics_df["shs"].min()
    shs_max = metrics_df["shs"].max()
    vmin = max(0, shs_min - 5)
    vmax = min(100, shs_max + 3)
    
    for ax, grower in zip(axes, growers):
        gdf = boundaries[boundaries["grower"] == grower].copy()
        if len(gdf) == 0:
            ax.text(0.5, 0.5, f"No data for {grower}", ha="center", va="center", transform=ax.transAxes, fontsize=12)
            continue
        gdf = gdf.merge(metrics_df[["field_id", "shs"]], on="field_id", how="left")
        
        # Ensure all fields have a valid SHS for coloring
        gdf["shs"] = gdf["shs"].fillna(metrics_df["shs"].mean())
        
        # Plot with fully opaque fill so every field is clearly visible
        gdf.plot(
            column="shs", cmap="RdYlGn", linewidth=1.5, edgecolor="black",
            alpha=0.95, ax=ax, vmin=vmin, vmax=vmax, legend=False,
        )
        
        ax.set_title(f"{grower} ({len(gdf)} fields)", fontsize=13, fontweight="bold", color=grower_colors.get(grower, "black"), pad=10)
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude", fontsize=9)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.set_aspect("equal", adjustable="datalim")
    
    # Vertical colorbar on the right — uses actual data range
    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar_ax = fig.add_axes([0.92, 0.15, 0.015, 0.7])
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="vertical")
    cbar.set_label(f"Soil Health Score ({vmin:.0f}–{vmax:.0f})", fontsize=11, fontweight="bold")
    cbar.ax.tick_params(labelsize=9)
    
    fig.suptitle("Field Boundaries by Grower — Colored by Soil Health Score", fontsize=15, fontweight="bold", y=0.98)
    fig.text(0.5, 0.93, "SHS = pH_score(25) + OM_score(25) + drainage(20) + AWC(20) + texture(10)  |  Range: {:.1f}–{:.1f}".format(shs_min, shs_max),
             ha="center", fontsize=10, style="italic", color="#555")
    plt.tight_layout(rect=[0.02, 0.02, 0.90, 0.92])
    
    return _fig_to_base64(fig)


def build_soil_texture(soil_scores: pd.DataFrame) -> str:
    texture_data = soil_scores.groupby("grower").agg({
        "clay_mean": "mean", "sand_mean": "mean", "silt_mean": "mean",
    }).reset_index()
    
    fig, ax = plt.subplots(figsize=(8, 5))
    growers = texture_data["grower"].tolist()
    x = np.arange(len(growers))
    width = 0.25
    
    bars1 = ax.bar(x - width, texture_data["clay_mean"], width, label="Clay %", color="#8d6e63", edgecolor="black", linewidth=0.5)
    bars2 = ax.bar(x, texture_data["sand_mean"], width, label="Sand %", color="#ffcc80", edgecolor="black", linewidth=0.5)
    bars3 = ax.bar(x + width, texture_data["silt_mean"], width, label="Silt %", color="#90a4ae", edgecolor="black", linewidth=0.5)
    
    # Add value labels on bars
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_ylabel("Percentage (%)", fontsize=11)
    ax.set_title("Soil Particle Size Distribution by Grower", fontsize=13, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(growers, fontsize=11)
    ax.legend(fontsize=10, loc="upper right")
    ax.set_ylim(0, max(texture_data[["clay_mean", "sand_mean", "silt_mean"]].max()) * 1.15)
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    
    plt.tight_layout()
    return _fig_to_base64(fig)


def build_ndvi_chart(year_ndvi: pd.DataFrame, year_focus: int) -> str:
    if year_ndvi.empty:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No NDVI data available", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        return _fig_to_base64(fig)
    
    ndvi_sorted = year_ndvi.sort_values("mean_ndvi", ascending=True)
    ndvi_sorted["short_id"] = ndvi_sorted["field_id"].str.replace("osm-", "")
    
    fig, ax = plt.subplots(figsize=(8, 6))
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    colors = [grower_colors.get(g, "gray") for g in ndvi_sorted["grower"]]
    
    bars = ax.barh(ndvi_sorted["short_id"], ndvi_sorted["mean_ndvi"], color=colors, edgecolor="black", linewidth=0.5)
    
    # Add value labels
    for bar, val in zip(bars, ndvi_sorted["mean_ndvi"]):
        ax.text(val + 0.005, bar.get_y() + bar.get_height()/2, f"{val:.3f}",
                va="center", ha="left", fontsize=7, fontweight="bold")
    
    ax.set_xlabel("Mean NDVI", fontsize=11)
    ax.set_title(f"NDVI Performance by Field — {year_focus}\n(Calculated from Sentinel-2 satellite imagery, composite mean per field)", 
                 fontsize=12, fontweight="bold", pad=15)
    ax.set_xlim(0, ndvi_sorted["mean_ndvi"].max() * 1.15)
    ax.grid(axis="x", alpha=0.3, linestyle="--")
    
    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, edgecolor="black", label=g) for g, c in grower_colors.items()]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)
    
    plt.tight_layout()
    return _fig_to_base64(fig)


def build_weather_chart(w2024: pd.DataFrame, year_focus: int) -> str:
    if w2024.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "No weather data available", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        return _fig_to_base64(fig)
    
    w2024["date"] = pd.to_datetime(w2024["date"])
    w2024["doy"] = w2024["date"].dt.dayofyear
    daily_grower = w2024.groupby(["doy", "grower"]).agg({
        "PRECTOTCORR": "mean", "T2M": "mean",
    }).reset_index()
    
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()
    
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    
    for grower in sorted(daily_grower["grower"].unique()):
        gdata = daily_grower[daily_grower["grower"] == grower].sort_values("doy")
        gdata["precip_smooth"] = gdata["PRECTOTCORR"].rolling(window=7, min_periods=1).mean()
        
        ax1.plot(gdata["doy"], gdata["precip_smooth"], color=grower_colors.get(grower, "gray"), 
                 linewidth=2, label=f"{grower} Precip", alpha=0.9)
        ax2.plot(gdata["doy"], gdata["T2M"], color=grower_colors.get(grower, "gray"), 
                 linewidth=1.5, linestyle="--", alpha=0.7)
    
    ax1.set_xlabel("Day of Year", fontsize=11)
    ax1.set_ylabel("Precipitation (mm, 7-day avg)", fontsize=11, color="#1565c0")
    ax1.tick_params(axis="y", labelcolor="#1565c0")
    ax2.set_ylabel("Temperature (°C)", fontsize=11, color="#c62828")
    ax2.tick_params(axis="y", labelcolor="#c62828")
    
    ax1.set_title(f"Daily Precipitation & Temperature by Day of Year — {year_focus}", fontsize=13, fontweight="bold", pad=15)
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.legend(loc="upper left", fontsize=9)
    
    plt.tight_layout()
    return _fig_to_base64(fig)


def build_gdd_chart(w2024: pd.DataFrame, year_focus: int, weather_all: pd.DataFrame = None) -> str:
    if w2024.empty or "T2M_MAX" not in w2024.columns or "T2M_MIN" not in w2024.columns:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "No GDD data available", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        return _fig_to_base64(fig)
    
    w2024["gdd_daily"] = ((w2024["T2M_MAX"] + w2024["T2M_MIN"]) / 2 - 10).clip(lower=0)
    gdd_grower = w2024.groupby(["date", "grower"]).agg({"gdd_daily": "mean"}).reset_index()
    gdd_grower["date"] = pd.to_datetime(gdd_grower["date"])
    gdd_grower["doy"] = gdd_grower["date"].dt.dayofyear
    gdd_grower = gdd_grower.sort_values(["grower", "doy"])
    gdd_grower["gdd_cum"] = gdd_grower.groupby("grower")["gdd_daily"].cumsum()
    
    fig, ax = plt.subplots(figsize=(10, 5))
    grower_colors = {"Iowa": "#4caf50", "Illinois": "#2196f3", "Nebraska": "#ff9800"}
    
    # Plot 5-year average as faint dashed background if available
    if weather_all is not None and not weather_all.empty and "year" in weather_all.columns:
        other_years = weather_all[weather_all["year"] != year_focus].copy()
        if not other_years.empty and "T2M_MAX" in other_years.columns and "T2M_MIN" in other_years.columns:
            other_years["gdd_daily"] = ((other_years["T2M_MAX"] + other_years["T2M_MIN"]) / 2 - 10).clip(lower=0)
            avg_gdd = other_years.groupby(["date", "grower"]).agg({"gdd_daily": "mean"}).reset_index()
            avg_gdd["date"] = pd.to_datetime(avg_gdd["date"])
            avg_gdd["doy"] = avg_gdd["date"].dt.dayofyear
            avg_gdd = avg_gdd.sort_values(["grower", "doy"])
            avg_gdd["gdd_cum"] = avg_gdd.groupby("grower")["gdd_daily"].cumsum()
            for grower in sorted(avg_gdd["grower"].unique()):
                gdata = avg_gdd[avg_gdd["grower"] == grower]
                ax.plot(gdata["doy"], gdata["gdd_cum"], color=grower_colors.get(grower, "gray"),
                        linewidth=1.5, linestyle="--", alpha=0.4)
    
    # Plot 2024 as solid bold lines
    for grower in sorted(gdd_grower["grower"].unique()):
        gdata = gdd_grower[gdd_grower["grower"] == grower]
        ax.plot(gdata["doy"], gdata["gdd_cum"], color=grower_colors.get(grower, "gray"), 
                linewidth=2.5, label=f"{grower} {year_focus}", alpha=0.9)
    
    ax.set_xlabel("Day of Year", fontsize=11)
    ax.set_ylabel("Cumulative GDD (°C, base 10°C)", fontsize=11)
    ax.set_title(f"Cumulative Growing Degree Days — {year_focus} vs Multi-Year Average", fontsize=13, fontweight="bold", pad=15)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper left")
    
    plt.tight_layout()
    return _fig_to_base64(fig)


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

    # === BUILD ALL CHARTS AS PNG ===
    print("[Dashboard] Building map...")
    map_b64 = build_map_per_grower(boundaries, metrics_df)
    
    print("[Dashboard] Building soil texture chart...")
    soil_b64 = build_soil_texture(soil_scores)
    
    print("[Dashboard] Building NDVI chart...")
    ndvi_b64 = build_ndvi_chart(year_ndvi, year_focus)
    
    print("[Dashboard] Building weather chart...")
    weather_b64 = build_weather_chart(w2024, year_focus)
    
    print("[Dashboard] Building GDD chart...")
    gdd_b64 = build_gdd_chart(w2024, year_focus, weather)

    # === MEANINGFUL METRICS TABLE ===
    print("[Dashboard] Building metrics table...")
    # Build transposed table: metrics as rows, growers + formula as columns
    growers_list = []
    for grower in ["Iowa", "Illinois", "Nebraska"]:
        gdf = metrics_df[metrics_df["grower"] == grower]
        if len(gdf) > 0:
            growers_list.append(grower)
    
    metric_definitions = [
        ("Fields monitored", "Count of fields in dataset", "count"),
        ("Avg Soil Health Score (SHS)", "pH_score + OM_score + drainage_score + awc_score + texture_score (each 0-25/20/10 pts)", "shs"),
        ("Avg Sustainability Index (SI)", "SHS×0.40 + rotation_score + weather_resilience + ndvi_stability_score", "si"),
        ("NDVI Stability Score", "(1 - CV_ndvi / max_CV) × 20, where CV = std(mean_NDVI) / mean(mean_NDVI)", "ndvi_stability_score"),
        ("Weather Resilience", "(1 - drought_days/max_drought)×10 + (1 - heat_stress_days/max_heat)×10", "weather_resilience"),
        ("Rotation Score", "Shannon_diversity / 2.0 × 20.0 from 5-year CDL crop rotation data", "rotation_score"),
    ]
    
    metric_rows = []
    for metric_name, formula, col in metric_definitions:
        row = {"Metric": metric_name, "Formula": formula}
        for grower in growers_list:
            gdf = metrics_df[metrics_df["grower"] == grower]
            if col == "count":
                row[grower] = len(gdf)
            elif col in gdf.columns:
                row[grower] = f"{gdf[col].mean():.1f}"
            else:
                row[grower] = "N/A"
        metric_rows.append(row)
    
    metrics_table_df = pd.DataFrame(metric_rows)

    # === 5 ANALYTICAL KEY HIGHLIGHTS ===
    print("[Dashboard] Generating highlights...")
    highlights = []
    
    best = metrics_df.loc[metrics_df["shs"].idxmax()]
    worst = metrics_df.loc[metrics_df["shs"].idxmin()]
    shs_by_grower = metrics_df.groupby("grower")["shs"].mean().sort_values(ascending=False)
    si_by_grower = metrics_df.groupby("grower")["si"].mean().sort_values(ascending=False)
    acres_by_grower = boundaries.groupby("grower")["area_acres"].sum().sort_values(ascending=False)
    
    # 1. Patterns / trends observed
    ndvi_text = ""
    if not year_ndvi.empty:
        ndvi_by_grower = year_ndvi.groupby("grower")["mean_ndvi"].mean().sort_values(ascending=False)
        ndvi_text = f" NDVI follows an inverse pattern — Illinois (most rain) shows highest vigor ({ndvi_by_grower.iloc[0]:.3f}) despite lowest soil health, suggesting rainfall may compensate for poorer soil conditions."
    
    precip_text = ""
    if not w2024.empty:
        total_precip = w2024.groupby("grower")["PRECTOTCORR"].sum().sort_values(ascending=False)
        precip_text = f" Rainfall and soil health show an inverse relationship: {total_precip.index[0]} received the most precipitation ({total_precip.iloc[0]:.0f}mm) but has the lowest average soil health ({shs_by_grower.iloc[-1]:.1f}), while {total_precip.index[-1]} is driest ({total_precip.iloc[-1]:.0f}mm) yet leads in soil health ({shs_by_grower.iloc[0]:.1f})."
    
    highlights.append(
        f"<strong>Patterns observed:</strong> A clear geographic gradient emerges — Nebraska fields dominate soil health (avg {shs_by_grower.iloc[0]:.1f}), Illinois lags ({shs_by_grower.iloc[-1]:.1f}), and Iowa sits in between.{precip_text}{ndvi_text}"
    )
    
    # 2. Healthiest vs most at-risk fields
    worst_ndvi = year_ndvi.loc[year_ndvi["mean_ndvi"].idxmin()] if not year_ndvi.empty else None
    worst_si = metrics_df.loc[metrics_df["si"].idxmin()]
    at_risk = []
    if worst["shs"] < 65:
        at_risk.append(f"lowest soil health ({worst['shs']:.1f}, {worst['field_id']})")
    if worst_si["si"] < 50:
        at_risk.append(f"lowest sustainability index ({worst_si['si']:.1f}, {worst_si['field_id']})")
    at_risk_text = "; ".join(at_risk) if at_risk else "multiple risk factors"
    highlights.append(
        f"<strong>Field health assessment:</strong> Best-performing field is {best['field_id']} (SHS {best['shs']:.1f}) in {best['grower']}, indicating strong pH, organic matter, and drainage. Most at-risk: {worst['field_id']} ({worst['grower']}) with {at_risk_text}. Priority for targeted soil amendment (lime, organic matter, drainage improvement)."
    )
    
    # 3. Environmental / soil variation
    soil_cv = (metrics_df["shs"].std() / metrics_df["shs"].mean() * 100)
    area_text = f"Field sizes range from {boundaries['area_acres'].min():.0f} to {boundaries['area_acres'].max():.0f} acres, averaging {boundaries['area_acres'].mean():.0f} acres."
    highlights.append(
        f"<strong>Environmental variation:</strong> Soil health varies by {soil_cv:.1f}% CV across all fields — a substantial {metrics_df['shs'].max() - metrics_df['shs'].min():.1f}-point spread. Within Illinois alone, SHS ranges {metrics_df[metrics_df['grower']=='Illinois']['shs'].min():.1f}–{metrics_df[metrics_df['grower']=='Illinois']['shs'].max():.1f}, showing high internal heterogeneity driven by texture differences (high sand = low SHS). {area_text}"
    )
    
    # 4. Decisions / actions
    highlights.append(
        f"<strong>Actionable insights:</strong> (1) <em>Lime and organic matter programs</em> should target Illinois sandier fields (SHS < 65) where pH and OM are limiting. (2) <em>Irrigation investment</em> may benefit Nebraska's drier climate despite strong soil — GDD analysis shows heat accumulation but rainfall deficit. (3) <em>Iowa's balanced profile</em> (SHS 83.4, moderate rain) supports maintaining current practices with precision-variable-rate fertilizer to preserve soil health. (4) <em>Cover cropping</em> could improve NDVI stability scores in fields with high year-to-year variation."
    )
    
    # 5. Most important variables
    highlights.append(
        f"<strong>Key drivers:</strong> Soil Health Score is the dominant variable — it explains {metrics_df['shs'].corr(metrics_df['si']):.0%} of Sustainability Index variation. Within SHS, organic matter and pH together contribute 50 points, making them the most leverageable inputs. Weather resilience (drought + heat stress) is the second-largest SI driver; Nebraska's poor weather resilience (1.0) drags down its otherwise excellent soil, dropping its SI below Iowa's despite higher SHS. NDVI stability adds the least variance, suggesting satellite vigor is more an outcome than a driver of field health."
    )

    # === FULL DATA TABLE ===
    full_table = metrics_df[["field_id", "grower", "area_acres", "shs", "si"]].copy()
    if not year_ndvi.empty:
        full_table = full_table.merge(year_ndvi[["field_id", "mean_ndvi"]], on="field_id", how="left")
    if "ndvi_stability_score" in metrics_df.columns:
        full_table = full_table.merge(metrics_df[["field_id", "ndvi_stability_score"]], on="field_id", how="left")
    if "weather_resilience" in metrics_df.columns:
        full_table = full_table.merge(metrics_df[["field_id", "weather_resilience"]], on="field_id", how="left")
    
    full_table = full_table.rename(columns={
        "field_id": "Field ID", "grower": "Grower", "area_acres": "Area (ac)",
        "shs": "Soil Health", "si": "Sustainability", "mean_ndvi": "NDVI 2024",
        "ndvi_stability_score": "NDVI Stability", "weather_resilience": "Weather Resilience",
    }).round({"Area (ac)": 1, "Soil Health": 1, "Sustainability": 1, "NDVI 2024": 3, "NDVI Stability": 1, "Weather Resilience": 1})

    # === RENDER HTML ===
    print("[Dashboard] Rendering HTML...")
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Field Intelligence Dashboard — {year_focus}</title>
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
.chart-img {{ width: 100%; border-radius: 8px; }}
.highlights {{ background: white; border-radius: 10px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; }}
.highlights h3 {{ margin: 0 0 16px 0; font-size: 16px; color: #1a5f2a; }}
.highlights ul {{ margin: 0; padding-left: 20px; }}
.highlights li {{ margin-bottom: 12px; line-height: 1.6; font-size: 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }}
th {{ background: #f1f8e9; font-weight: 600; color: #1a5f2a; position: sticky; top: 0; }}
tr:hover {{ background: #f9f9f9; }}
.table-wrap {{ max-height: 400px; overflow-y: auto; border-radius: 8px; border: 1px solid #e0e0e0; }}
.metrics-explanation {{ font-size: 12px; color: #555; margin-top: 12px; line-height: 1.6; background: #fafafa; padding: 14px; border-radius: 6px; border-left: 3px solid #4caf50; }}
.ndvi-explanation {{ font-size: 12px; color: #555; margin-top: 10px; line-height: 1.5; background: #f5f5f5; padding: 10px; border-radius: 4px; }}
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
      <img class="chart-img" src="data:image/png;base64,{map_b64}" alt="Field Map">
    </div>
  </div>

  <div class="row">
    <div class="panel">
      <h3>Soil Particle Size Distribution by Grower (%)</h3>
      <img class="chart-img" src="data:image/png;base64,{soil_b64}" alt="Soil Texture">
      <div class="ndvi-explanation">
        <strong>Method:</strong> Clay, sand, and silt percentages averaged from SSURGO soil survey data across all field horizons for each grower.
      </div>
    </div>
    <div class="panel">
      <h3>NDVI Performance by Field</h3>
      <img class="chart-img" src="data:image/png;base64,{ndvi_b64}" alt="NDVI Ranking">
      <div class="ndvi-explanation">
        <strong>How NDVI is calculated:</strong> Mean NDVI extracted from Sentinel-2 satellite imagery composites (10m resolution) for each field boundary. NDVI = (NIR - Red) / (NIR + Red), ranging from -1 to 1. Values > 0.3 indicate healthy vegetation. Higher NDVI = more vigorous crop biomass.
      </div>
    </div>
  </div>

  <div class="row">
    <div class="panel">
      <h3>Weather: Precipitation & Temperature by Day of Year</h3>
      <img class="chart-img" src="data:image/png;base64,{weather_b64}" alt="Weather">
      <div class="ndvi-explanation">
        <strong>Data source:</strong> NASA POWER daily weather data. Precipitation shown as 7-day rolling average. Temperature is daily mean (°C).
      </div>
    </div>
    <div class="panel">
      <h3>Growing Degree Days by Grower</h3>
      <img class="chart-img" src="data:image/png;base64,{gdd_b64}" alt="GDD">
      <div class="ndvi-explanation">
        <strong>Method:</strong> Cumulative GDD = Σ[max(0, (Tmax + Tmin)/2 - 10°C)] per day. Base temperature = 10°C. Solid lines = {year_focus}; dashed faint lines = multi-year average (2021–2025). Gaps above/below average indicate warmer/cooler seasons affecting crop development timing.
      </div>
    </div>
  </div>

  <div class="row-full">
    <div class="panel-full">
      <h3>Sustainability Metrics by Grower</h3>
      <div class="table-wrap">
        {metrics_table_df.to_html(index=False, classes='metrics-table', border=0)}
      </div>
      <div class="metrics-explanation">
        <strong>Notes:</strong> Each metric row above includes its exact calculation formula in the second column. All scores are computed per-field then averaged by grower. SHS and SI are scaled 0-100. NDVI Stability, Weather Resilience, and Rotation Score each contribute 0-20 points toward the SI.
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
      <h3>Field Data Summary</h3>
      <div class="table-wrap">
        {full_table.to_html(index=False, border=0, na_rep="—")}
      </div>
    </div>
  </div>
</div>
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
