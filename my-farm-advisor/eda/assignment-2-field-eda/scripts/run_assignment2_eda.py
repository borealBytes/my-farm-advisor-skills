#!/usr/bin/env python3
"""Assignment 2 Field-Level EDA Script.

Generates static EDA artifacts for weather, CDL, and boundary data
across Illinois, Iowa, and Nebraska growers.

Usage:
    export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
    python run_assignment2_eda.py --output-dir "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment-2"
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_data_root() -> Path:
    env = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if env:
        return Path(env) / "data-pipeline"
    return Path("/home/coder/my-farm-advisor-runtime/data-pipeline")


DATA_ROOT = _resolve_data_root()
GROWERS_ROOT = DATA_ROOT / "growers"

GROWER_CONFIG = {
    "il-grower": {"farm_slug": "il-grower-illinois", "state": "Illinois", "fips": "17", "color": "#1f77b4"},
    "ia-grower": {"farm_slug": "ia-grower-iowa", "state": "Iowa", "fips": "19", "color": "#ff7f0e"},
    "ne-grower": {"farm_slug": "ne-grower-nebraska", "state": "Nebraska", "fips": "31", "color": "#2ca02c"},
}


def farm_boundary_path(grower_slug: str, farm_slug: str) -> Path:
    return GROWERS_ROOT / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"


def farm_weather_path(grower_slug: str, farm_slug: str) -> Path:
    prefix = farm_slug.replace("-", "_")
    if prefix.endswith("_farm"):
        prefix = prefix[:-5]
    return (
        GROWERS_ROOT
        / grower_slug
        / "farms"
        / farm_slug
        / "derived"
        / "tables"
        / f"{prefix}_weather_2021_2025.csv"
    )


def farm_cdl_full_composition_path(grower_slug: str, farm_slug: str) -> Path:
    prefix = farm_slug.replace("-", "_")
    if prefix.endswith("_farm"):
        prefix = prefix[:-5]
    return (
        GROWERS_ROOT
        / grower_slug
        / "farms"
        / farm_slug
        / "derived"
        / "tables"
        / f"{prefix}_cdl_2021_2025_full_composition.csv"
    )


def farm_cdl_rotation_path(grower_slug: str, farm_slug: str) -> Path:
    prefix = farm_slug.replace("-", "_")
    if prefix.endswith("_farm"):
        prefix = prefix[:-5]
    return (
        GROWERS_ROOT
        / grower_slug
        / "farms"
        / farm_slug
        / "derived"
        / "tables"
        / f"{prefix}_crop_rotation.csv"
    )


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_all_weather() -> pd.DataFrame:
    frames = []
    for grower_slug, cfg in GROWER_CONFIG.items():
        path = farm_weather_path(grower_slug, cfg["farm_slug"])
        if not path.exists():
            print(f"Warning: weather file not found: {path}")
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        df["grower"] = grower_slug
        df["state"] = cfg["state"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_all_cdl() -> pd.DataFrame:
    frames = []
    for grower_slug, cfg in GROWER_CONFIG.items():
        path = farm_cdl_full_composition_path(grower_slug, cfg["farm_slug"])
        if not path.exists():
            print(f"Warning: CDL file not found: {path}")
            continue
        df = pd.read_csv(path)
        df["grower"] = grower_slug
        df["state"] = cfg["state"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_all_rotations() -> pd.DataFrame:
    frames = []
    for grower_slug, cfg in GROWER_CONFIG.items():
        path = farm_cdl_rotation_path(grower_slug, cfg["farm_slug"])
        if not path.exists():
            print(f"Warning: rotation file not found: {path}")
            continue
        df = pd.read_csv(path)
        df["grower"] = grower_slug
        df["state"] = cfg["state"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_all_boundaries() -> gpd.GeoDataFrame:
    frames = []
    for grower_slug, cfg in GROWER_CONFIG.items():
        path = farm_boundary_path(grower_slug, cfg["farm_slug"])
        if not path.exists():
            print(f"Warning: boundary file not found: {path}")
            continue
        gdf = gpd.read_file(path)
        gdf["grower"] = grower_slug
        gdf["state"] = cfg["state"]
        frames.append(gdf)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Helper: dominant crop per field per year
# ---------------------------------------------------------------------------

def get_dominant_crop(cdl_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per field per year with the dominant crop."""
    idx = cdl_df.groupby(["field_id", "year"])["pct"].idxmax()
    return cdl_df.loc[idx, ["field_id", "year", "crop_name", "pct", "pixel_count", "grower", "state"]].copy()


# ---------------------------------------------------------------------------
# Weather visualizations
# ---------------------------------------------------------------------------

def plot_growing_season_temp_boxplot(weather_df: pd.DataFrame, out_dir: Path) -> None:
    """A1: Box plot of May–Sep mean daily temperature by grower."""
    weather_df = weather_df.copy()
    weather_df["month"] = weather_df["date"].dt.month
    gs = weather_df[weather_df["month"].isin(range(5, 10))]

    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    state_order = [GROWER_CONFIG[g]["state"] for g in order]
    palette_list = [GROWER_CONFIG[g]["color"] for g in order]
    sns.boxplot(data=gs, x="state", y="T2M", order=state_order,
                palette=palette_list, ax=ax)
    ax.set_title("Growing Season (May–Sep) Daily Mean Temperature by State\n2021–2025", fontsize=13)
    ax.set_ylabel("Daily Mean Temperature (°C)")
    ax.set_xlabel("")
    plt.tight_layout()
    out_path = out_dir / "weather" / "growing_season_temp_boxplot.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_annual_precip_by_field(weather_df: pd.DataFrame, out_dir: Path) -> None:
    """A2: Bar chart of annual total precipitation per field, faceted by grower."""
    weather_df = weather_df.copy()
    weather_df["year"] = weather_df["date"].dt.year
    annual = weather_df.groupby(["grower", "state", "field_id", "year"])["PRECTOTCORR"].sum().reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    order = ["il-grower", "ia-grower", "ne-grower"]
    for ax, grower in zip(axes, order):
        sub = annual[annual["grower"] == grower]
        states = sub["state"].unique()
        state_name = states[0] if len(states) else grower
        sns.barplot(data=sub, x="year", y="PRECTOTCORR", hue="field_id",
                    palette="tab20", ax=ax, legend=False)
        ax.set_title(state_name, fontsize=12)
        ax.set_xlabel("Year")
        ax.set_ylabel("Annual Precipitation (mm)")
    fig.suptitle("Annual Total Precipitation per Field\n2021–2025", fontsize=14, y=1.02)
    plt.tight_layout()
    out_path = out_dir / "weather" / "annual_precip_by_field.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_gdd_comparison(weather_df: pd.DataFrame, cdl_df: pd.DataFrame, out_dir: Path) -> None:
    """A3: Cumulative GDD curves per field, colored by grower."""
    # Determine dominant crop in 2025 for GDD parameters
    dominant = get_dominant_crop(cdl_df)
    dom_2025 = dominant[dominant["year"] == 2025][["field_id", "crop_name"]].copy()
    dom_2025.rename(columns={"crop_name": "dominant_crop_2025"}, inplace=True)

    weather_df = weather_df.copy()
    weather_df = weather_df.merge(dom_2025, on="field_id", how="left")
    weather_df["dominant_crop_2025"] = weather_df["dominant_crop_2025"].fillna("Unknown")

    # GDD params: Corn base=10, cap=30; Soybeans base=10, cap=30
    def calc_gdd(row):
        t_avg = (row["T2M_MIN"] + row["T2M_MAX"]) / 2
        t_avg = min(t_avg, 30.0)
        return max(0.0, t_avg - 10.0)

    weather_df["gdd"] = weather_df.apply(calc_gdd, axis=1)
    weather_df["year"] = weather_df["date"].dt.year
    weather_df["doy"] = weather_df["date"].dt.dayofyear

    # Focus on growing season (May 1 = DOY ~121 to Sep 30 = DOY ~273)
    gs = weather_df[(weather_df["doy"] >= 121) & (weather_df["doy"] <= 273)].copy()
    gs = gs.sort_values(["field_id", "year", "doy"])
    gs["gdd_cum"] = gs.groupby(["field_id", "year"])["gdd"].cumsum()

    fig, ax = plt.subplots(figsize=(12, 7))
    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}

    for grower in order:
        sub = gs[gs["grower"] == grower]
        for field_id, fsub in sub.groupby("field_id"):
            # Plot mean across years for each field to reduce noise
            mean_gdd = fsub.groupby("doy")["gdd_cum"].mean().reset_index()
            ax.plot(mean_gdd["doy"], mean_gdd["gdd_cum"],
                    color=palette[grower], alpha=0.4, linewidth=1)

    # Plot grower means
    for grower in order:
        sub = gs[gs["grower"] == grower]
        mean_gdd = sub.groupby("doy")["gdd_cum"].mean().reset_index()
        ax.plot(mean_gdd["doy"], mean_gdd["gdd_cum"],
                color=palette[grower], linewidth=2.5, label=GROWER_CONFIG[grower]["state"])

    ax.set_title("Cumulative Growing Degree Days (GDD)\nCorn/Soy Parameters: Base 10°C, Cap 30°C\nMay–September, 2021–2025 Average", fontsize=13)
    ax.set_xlabel("Day of Year")
    ax.set_ylabel("Cumulative GDD (°C·days)")
    ax.legend(title="State")
    plt.tight_layout()
    out_path = out_dir / "weather" / "gdd_comparison.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# CDL visualizations
# ---------------------------------------------------------------------------

def plot_crop_distribution_stacked(cdl_df: pd.DataFrame, out_dir: Path) -> None:
    """B1: 100% stacked bar chart of crop composition per grower × year."""
    dominant = get_dominant_crop(cdl_df)

    # Aggregate to grower-year-crop
    summary = dominant.groupby(["grower", "state", "year", "crop_name"]).size().reset_index(name="field_count")
    # Also compute from pixel counts for area estimate
    area = cdl_df.groupby(["grower", "state", "year", "crop_name"])["pixel_count"].sum().reset_index()
    area["pct"] = area.groupby(["grower", "year"])["pixel_count"].transform(lambda x: x / x.sum() * 100)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    order = ["il-grower", "ia-grower", "ne-grower"]
    crops = sorted(area["crop_name"].unique())
    crop_palette = sns.color_palette("tab10", n_colors=len(crops))
    crop_color_map = dict(zip(crops, crop_palette))

    for ax, grower in zip(axes, order):
        sub = area[area["grower"] == grower].copy()
        pivot = sub.pivot(index="year", columns="crop_name", values="pct").fillna(0)
        pivot = pivot.reindex(columns=crops, fill_value=0)
        pivot.plot(kind="bar", stacked=True, ax=ax, color=[crop_color_map[c] for c in pivot.columns],
                   legend=False, width=0.7)
        ax.set_title(GROWER_CONFIG[grower]["state"], fontsize=12)
        ax.set_xlabel("Year")
        ax.set_ylabel("Crop Area (%)")
        ax.set_ylim(0, 100)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=0)

    handles = [plt.Rectangle((0,0),1,1, color=crop_color_map[c]) for c in crops]
    fig.legend(handles, crops, loc="lower center", ncol=len(crops), title="Crop", bbox_to_anchor=(0.5, -0.05))
    fig.suptitle("Crop Composition by Grower and Year (2021–2025)\nBased on CDL Pixel Percentage", fontsize=14, y=1.02)
    plt.tight_layout()
    out_path = out_dir / "cdl" / "crop_distribution_stacked.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_rotation_diversity_hist(rotation_df: pd.DataFrame, out_dir: Path) -> None:
    """B2: Histogram of crop-diversity count per field."""
    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}

    for grower in order:
        sub = rotation_df[rotation_df["grower"] == grower]
        sns.histplot(data=sub, x="crop_diversity", color=palette[grower],
                     label=GROWER_CONFIG[grower]["state"], kde=True,
                     alpha=0.5, bins=range(1, sub["crop_diversity"].max()+3), ax=ax)

    ax.set_title("Crop Rotation Diversity per Field\nNumber of Unique Crops Observed (2021–2025)", fontsize=13)
    ax.set_xlabel("Crop Diversity (unique crops)")
    ax.set_ylabel("Number of Fields")
    ax.legend(title="State")
    plt.tight_layout()
    out_path = out_dir / "cdl" / "rotation_diversity_hist.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_corn_vs_soy_area_trend(cdl_df: pd.DataFrame, out_dir: Path) -> None:
    """B3: Line chart of estimated corn vs. soybean acreage across years per grower."""
    # Use pixel_count as proxy for area
    corn_soy = cdl_df[cdl_df["crop_name"].isin(["Corn", "Soybeans"])].copy()
    trend = corn_soy.groupby(["grower", "state", "year", "crop_name"])["pixel_count"].sum().reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}
    line_styles = {"Corn": "-", "Soybeans": "--"}

    for grower in order:
        for crop in ["Corn", "Soybeans"]:
            sub = trend[(trend["grower"] == grower) & (trend["crop_name"] == crop)]
            if sub.empty:
                continue
            ax.plot(sub["year"], sub["pixel_count"],
                    color=palette[grower], linestyle=line_styles[crop],
                    marker="o", linewidth=2,
                    label=f"{GROWER_CONFIG[grower]['state']} – {crop}")

    ax.set_title("Estimated Corn vs. Soybean Area Trend\nCDL Pixel Count Proxy (2021–2025)", fontsize=13)
    ax.set_xlabel("Year")
    ax.set_ylabel("Total CDL Pixel Count")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    out_path = out_dir / "cdl" / "corn_vs_soy_area_trend.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Boundary visualizations
# ---------------------------------------------------------------------------

def plot_field_size_distribution(boundaries_gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    """C1: Histogram of field sizes by grower with KDE overlay."""
    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}

    for grower in order:
        sub = boundaries_gdf[boundaries_gdf["grower"] == grower]
        sns.histplot(data=sub, x="area_acres", color=palette[grower],
                     label=GROWER_CONFIG[grower]["state"], kde=True,
                     alpha=0.4, bins=15, ax=ax)

    ax.set_title("Field Size Distribution by Grower", fontsize=13)
    ax.set_xlabel("Field Size (acres)")
    ax.set_ylabel("Number of Fields")
    ax.legend(title="State")
    plt.tight_layout()
    out_path = out_dir / "boundaries" / "field_size_distribution.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_total_acreage_by_grower(boundaries_gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    """C2: Bar chart of total farm acreage and field count per grower."""
    summary = boundaries_gdf.groupby(["grower", "state"]).agg(
        total_acres=("area_acres", "sum"),
        field_count=("field_id", "nunique"),
    ).reset_index()

    fig, ax1 = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    summary["grower_order"] = summary["grower"].apply(lambda x: order.index(x))
    summary = summary.sort_values("grower_order")
    palette = [GROWER_CONFIG[g]["color"] for g in summary["grower"]]

    bars = ax1.bar(summary["state"], summary["total_acres"], color=palette, alpha=0.8)
    ax1.set_ylabel("Total Acreage (acres)", color="black")
    ax1.set_title("Total Farm Acreage and Field Count by Grower", fontsize=13)

    ax2 = ax1.twinx()
    ax2.plot(summary["state"], summary["field_count"], color="black", marker="D", linewidth=2, markersize=8)
    ax2.set_ylabel("Field Count", color="black")

    # Add value labels
    for bar, acres in zip(bars, summary["total_acres"]):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                f"{acres:.1f}", ha="center", va="bottom", fontsize=10)
    for i, count in enumerate(summary["field_count"]):
        ax2.text(i, count + 0.2, str(count), ha="center", va="bottom", fontsize=10, color="black")

    plt.tight_layout()
    out_path = out_dir / "boundaries" / "total_acreage_by_grower.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_size_vs_dominant_crop(boundaries_gdf: gpd.GeoDataFrame, cdl_df: pd.DataFrame, out_dir: Path) -> None:
    """C3: Scatter plot of field area vs. dominant 2025 crop."""
    dominant = get_dominant_crop(cdl_df)
    dom_2025 = dominant[dominant["year"] == 2025][["field_id", "crop_name"]].copy()
    dom_2025.rename(columns={"crop_name": "dominant_crop_2025"}, inplace=True)

    merged = boundaries_gdf.merge(dom_2025, on="field_id", how="left")
    merged["dominant_crop_2025"] = merged["dominant_crop_2025"].fillna("Unknown")

    fig, ax = plt.subplots(figsize=(10, 6))
    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}

    for grower in order:
        sub = merged[merged["grower"] == grower]
        ax.scatter(sub["area_acres"], sub["dominant_crop_2025"],
                   c=palette[grower], label=GROWER_CONFIG[grower]["state"],
                   s=100, alpha=0.7, edgecolors="black")

    ax.set_title("Field Size vs. Dominant Crop (2025)\nColored by Grower", fontsize=13)
    ax.set_xlabel("Field Size (acres)")
    ax.set_ylabel("Dominant Crop (2025)")
    ax.legend(title="State")
    plt.tight_layout()
    out_path = out_dir / "boundaries" / "size_vs_dominant_crop.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Geospatial map
# ---------------------------------------------------------------------------

def create_interactive_map(boundaries_gdf: gpd.GeoDataFrame, cdl_df: pd.DataFrame, out_dir: Path) -> None:
    """M1: Interactive Folium map of all fields colored by grower."""
    try:
        import folium
        from folium import GeoJson, GeoJsonTooltip
    except ImportError:
        print("Warning: folium not installed, skipping interactive map.")
        return

    dominant = get_dominant_crop(cdl_df)
    dom_2025 = dominant[dominant["year"] == 2025][["field_id", "crop_name"]].copy()
    dom_2025.rename(columns={"crop_name": "dominant_crop_2025"}, inplace=True)
    merged = boundaries_gdf.merge(dom_2025, on="field_id", how="left")
    merged["dominant_crop_2025"] = merged["dominant_crop_2025"].fillna("Unknown")

    # Compute centroids for map center
    all_centroids = merged.geometry.centroid
    center_lat = all_centroids.y.mean()
    center_lon = all_centroids.x.mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="cartodbpositron")

    order = ["il-grower", "ia-grower", "ne-grower"]
    palette = {g: GROWER_CONFIG[g]["color"] for g in order}

    for grower in order:
        sub = merged[merged["grower"] == grower]
        feature_group = folium.FeatureGroup(name=GROWER_CONFIG[grower]["state"])
        for _, row in sub.iterrows():
            feature = {
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__,
                "properties": {
                    "field_id": str(row.get("field_id", "")),
                    "area_acres": float(row.get("area_acres", 0)),
                    "dominant_crop_2025": str(row.get("dominant_crop_2025", "Unknown")),
                    "county_name": str(row.get("county_name", "")),
                },
            }
            geo_json = folium.GeoJson(
                data=feature,
                style_function=lambda x, color=palette[grower]: {
                    "fillColor": color,
                    "color": "black",
                    "weight": 1,
                    "fillOpacity": 0.5,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["field_id", "area_acres", "dominant_crop_2025", "county_name"],
                    aliases=["Field ID:", "Area (acres):", "2025 Crop:", "County:"],
                    localize=True,
                ),
            )
            geo_json.add_to(feature_group)
        feature_group.add_to(m)

    folium.LayerControl().add_to(m)

    out_path = out_dir / "boundaries" / "all_fields_map.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def run_statistical_tests(weather_df: pd.DataFrame, out_dir: Path) -> None:
    """Run Kruskal-Wallis tests and save results."""
    weather_df = weather_df.copy()
    weather_df["month"] = weather_df["date"].dt.month
    gs = weather_df[weather_df["month"].isin(range(5, 10))]
    weather_df["year"] = weather_df["date"].dt.year
    annual = weather_df.groupby(["grower", "field_id", "year"])["PRECTOTCORR"].sum().reset_index()

    # Growing season temperature by state
    groups_temp = [gs[gs["grower"] == g]["T2M"].values for g in ["il-grower", "ia-grower", "ne-grower"]]
    kw_temp = stats.kruskal(*groups_temp)

    # Annual precipitation by state (aggregate to field means first)
    annual_mean = annual.groupby(["grower", "field_id"])["PRECTOTCORR"].mean().reset_index()
    groups_precip = [annual_mean[annual_mean["grower"] == g]["PRECTOTCORR"].values for g in ["il-grower", "ia-grower", "ne-grower"]]
    kw_precip = stats.kruskal(*groups_precip)

    results = pd.DataFrame([
        {
            "test_name": "Kruskal-Wallis",
            "variable": "Growing_Season_Mean_Temperature_C",
            "statistic": round(kw_temp.statistic, 4),
            "p_value": round(kw_temp.pvalue, 6),
            "significant_at_0.05": kw_temp.pvalue < 0.05,
            "interpretation": (
                "Significant difference in growing-season temperatures across states."
                if kw_temp.pvalue < 0.05 else
                "No significant difference in growing-season temperatures across states."
            ),
        },
        {
            "test_name": "Kruskal-Wallis",
            "variable": "Mean_Annual_Precipitation_mm",
            "statistic": round(kw_precip.statistic, 4),
            "p_value": round(kw_precip.pvalue, 6),
            "significant_at_0.05": kw_precip.pvalue < 0.05,
            "interpretation": (
                "Significant difference in mean annual precipitation across states."
                if kw_precip.pvalue < 0.05 else
                "No significant difference in mean annual precipitation across states."
            ),
        },
    ])

    out_path = out_dir / "cross_grower" / "statistical_tests.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")
    print(results.to_string(index=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Assignment 2 Field-Level EDA")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DATA_ROOT / "eda" / "assignment-2"),
        help="Directory to save all EDA artifacts",
    )
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Assignment 2 Field-Level EDA")
    print("=" * 60)

    print("\n[1/4] Loading data...")
    weather_df = load_all_weather()
    cdl_df = load_all_cdl()
    rotation_df = load_all_rotations()
    boundaries_gdf = load_all_boundaries()
    print(f"  Weather rows: {len(weather_df):,}")
    print(f"  CDL rows: {len(cdl_df):,}")
    print(f"  Rotation rows: {len(rotation_df):,}")
    print(f"  Boundary features: {len(boundaries_gdf):,}")

    print("\n[2/4] Generating weather visualizations...")
    plot_growing_season_temp_boxplot(weather_df, out_dir)
    plot_annual_precip_by_field(weather_df, out_dir)
    plot_gdd_comparison(weather_df, cdl_df, out_dir)

    print("\n[3/4] Generating CDL visualizations...")
    plot_crop_distribution_stacked(cdl_df, out_dir)
    plot_rotation_diversity_hist(rotation_df, out_dir)
    plot_corn_vs_soy_area_trend(cdl_df, out_dir)

    print("\n[4/4] Generating boundary visualizations and map...")
    plot_field_size_distribution(boundaries_gdf, out_dir)
    plot_total_acreage_by_grower(boundaries_gdf, out_dir)
    plot_size_vs_dominant_crop(boundaries_gdf, cdl_df, out_dir)
    create_interactive_map(boundaries_gdf, cdl_df, out_dir)

    print("\n[5/4] Running statistical tests...")
    run_statistical_tests(weather_df, out_dir)

    print("\n" + "=" * 60)
    print("EDA complete. All artifacts saved to:")
    print(f"  {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
