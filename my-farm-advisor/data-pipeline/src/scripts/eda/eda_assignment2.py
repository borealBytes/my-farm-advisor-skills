#!/usr/bin/env python3
# pyright: reportCallIssue=false
"""
eda_assignment2.py - Field-Level EDA for Assignment 2

Compares field boundaries, CDL cropland history, and weather across 3 growers
(~10 fields each) in Illinois, Iowa, and Nebraska.

Output: static PNG figures + CSV tables under shared/assignment2-eda/derived/
"""

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import warnings

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))

warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS.*centroid.*")

from lib.paths import (  # noqa: E402
    SHARED_ROOT,
    farm_boundary_path,
    farm_cdl_full_composition_path,
    farm_cdl_rotation_path,
    farm_weather_path,
)

GROWERS = [
    ("illinois-grower", "illinois-grower-illinois", "Illinois"),
    ("iowa-grower", "iowa-grower-iowa", "Iowa"),
    ("nebraska-grower", "nebraska-grower-hall", "Nebraska"),
]

_OUTPUT_BASE = SHARED_ROOT / "assignment2-eda" / "derived"
_REPORTS_DIR = _OUTPUT_BASE / "reports"
_TABLES_DIR = _OUTPUT_BASE / "tables"

_GROWER_LABELS = dict((g, l) for g, _, l in GROWERS)
_FARM_SLUGS = dict((g, f) for g, f, _ in GROWERS)

sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 150


def _load_all_boundaries():
    frames = []
    for g, f, label in GROWERS:
        df = gpd.read_file(farm_boundary_path(g, f))
        df["grower"] = label
        df["grower_slug"] = g
        frames.append(df)
    combined = gpd.pd.concat(frames, ignore_index=True)
    return combined


def _load_all_weather():
    frames = []
    for g, f, label in GROWERS:
        df = pd.read_csv(
            farm_weather_path(g, f),
            parse_dates=["date"],
        )
        df["grower"] = label
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _load_all_cdl_composition():
    frames = []
    for g, f, label in GROWERS:
        df = pd.read_csv(farm_cdl_full_composition_path(g, f))
        df["grower"] = label
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _load_all_cdl_rotation():
    frames = []
    for g, f, label in GROWERS:
        df = pd.read_csv(farm_cdl_rotation_path(g, f))
        df["grower"] = label
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _save_csv(df, name):
    path = _TABLES_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  csv  {path}")


def _save_fig(fig, name):
    path = _REPORTS_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  png  {path}")


# ── Category 1: Field Boundaries ──────────────────────────────────────────


def boundaries_analyses(boundaries):
    print("\n── Boundaries ──")

    # Stat Vis 1: Histogram of field areas by grower
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, (label, grp) in zip(axes, boundaries.groupby("grower")):
        ax.hist(grp["area_acres"], bins=8, color="steelblue", edgecolor="white")
        ax.set_title(label, fontweight="bold")
        ax.set_xlabel("Area (acres)")
        if ax == axes[0]:
            ax.set_ylabel("Field count")
    fig.suptitle("Field Area Distribution by Grower", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_fig(fig, "boundaries_area_histogram.png")

    # Stat Vis 2: Mean/median area per grower bar chart
    stats = boundaries.groupby("grower")["area_acres"].agg(["mean", "median", "sum", "count"])
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(stats))
    w = 0.35
    ax.bar(x - w / 2, stats["mean"], w, label="Mean", color="steelblue")
    ax.bar(x + w / 2, stats["median"], w, label="Median", color="darkorange")
    ax.set_xticks(x)
    ax.set_xticklabels(stats.index)
    ax.set_ylabel("Area (acres)")
    ax.set_title("Mean vs Median Field Area by Grower", fontweight="bold")
    ax.legend()
    for i, row in enumerate(stats.itertuples()):
        ax.text(i - w / 2, row.mean + 5, f"{row.mean:.0f}", ha="center", fontsize=8)
        ax.text(i + w / 2, row.median + 5, f"{row.median:.0f}", ha="center", fontsize=8)
    fig.tight_layout()
    _save_fig(fig, "boundaries_area_stats.png")

    # Comparison: Box plot of area across growers
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=boundaries, x="grower", y="area_acres", hue="grower", ax=ax, palette="Set2", legend=False)
    sns.stripplot(data=boundaries, x="grower", y="area_acres", ax=ax, color="black", alpha=0.4, size=6)
    ax.set_title("Field Area Comparison Across Growers", fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Area (acres)")
    fig.tight_layout()
    _save_fig(fig, "boundaries_area_boxplot.png")

    # Map: All fields as proportional bubbles by grower
    fig, ax = plt.subplots(figsize=(10, 8))
    cents = boundaries.geometry.centroid
    sizes = np.sqrt(boundaries["area_acres"]) * 35
    colors = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}
    for label, grp in boundaries.groupby("grower"):
        mask = grp.index
        ax.scatter(cents.x[mask], cents.y[mask],
                   s=sizes.iloc[mask], c=colors[label], label=label,
                   alpha=0.7, edgecolor="black", linewidth=0.5)
    for acres, sz in [(10, np.sqrt(10) * 35), (100, np.sqrt(100) * 35), (300, np.sqrt(300) * 35)]:
        ax.scatter([], [], s=sz, c="gray", alpha=0.4, edgecolor="black", linewidth=0.5, label=f"{acres} ac")
    ax.legend(title="Grower / Size", loc="lower right", fontsize=8, title_fontsize=9)
    ax.set_title("Field Locations by Grower (bubble = area)", fontweight="bold")
    ax.set_axis_off()
    fig.tight_layout()
    _save_fig(fig, "boundaries_field_map.png")

    # Summary table
    summary = boundaries.groupby("grower").agg(
        field_count=("field_id", "count"),
        total_area=("area_acres", "sum"),
        min_area=("area_acres", "min"),
        max_area=("area_acres", "max"),
        mean_area=("area_acres", "mean"),
        median_area=("area_acres", "median"),
    ).reset_index()
    summary["state"] = ["Illinois", "Iowa", "Nebraska"]
    _save_csv(summary, "field_boundary_summary.csv")
    print(summary.to_string(index=False))


# ── Category 2: CDL / Cropland ────────────────────────────────────────────


def cdl_analyses(composition, rotation, boundaries):
    print("\n── CDL ──")

    b_lookup = boundaries[["field_id", "grower"]].drop_duplicates()

    dominant = composition.loc[composition.groupby(["field_id", "year"])["pct"].idxmax()].copy()
    dominant = dominant.drop(columns=["grower"], errors="ignore")
    dominant = dominant.merge(b_lookup, on="field_id", how="left")
    dominant["is_corn"] = dominant["crop_name"] == "Corn"
    dominant["is_soybean"] = dominant["crop_name"] == "Soybeans"

    rot = rotation.drop(columns=["grower"], errors="ignore").merge(b_lookup, on="field_id", how="left")

    # Stat Vis 1: Crop composition by grower (stacked bar)
    comp_by_grower = (
        dominant.groupby(["grower", "crop_name"])
        .size()
        .unstack(fill_value=0)
    )
    comp_pct = comp_by_grower.div(comp_by_grower.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 5))
    comp_pct.plot(kind="barh", stacked=True, ax=ax, colormap="Set3")
    ax.set_title("Crop Composition by Grower (% of field-years)", fontweight="bold")
    ax.set_xlabel("Percentage")
    ax.set_ylabel("")
    ax.legend(loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)
    fig.tight_layout()
    _save_fig(fig, "cdl_composition_by_grower.png")

    # Stat Vis 2: Corn/Soybean trend by year per grower
    trend = (
        dominant.groupby(["grower", "year"])[["is_corn", "is_soybean"]]
        .mean()
        .reset_index()
    )
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, (label, grp) in zip(axes, trend.groupby("grower")):
        ax.plot(grp["year"], grp["is_corn"] * 100, "o-", label="Corn", color="goldenrod")
        ax.plot(grp["year"], grp["is_soybean"] * 100, "s--", label="Soybeans", color="green")
        ax.set_title(label, fontweight="bold")
        ax.set_xlabel("Year")
        if ax == axes[0]:
            ax.set_ylabel("% of fields")
        ax.set_xticks(grp["year"])
        ax.legend(fontsize=8)
        ax.set_ylim(-5, 105)
    fig.suptitle("Dominant Crop Trend by Year per Grower", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_fig(fig, "cdl_crop_trend.png")

    # Comparison: Rotation diversity
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    div_stats = rot.groupby("grower")["crop_diversity"].mean().reset_index()
    axes[0].bar(div_stats["grower"], div_stats["crop_diversity"],
                color=["steelblue", "darkorange", "green"])
    axes[0].set_title("Mean Crop Diversity by Grower", fontweight="bold")
    axes[0].set_ylabel("Avg crop types in rotation")
    for label, grp in rot.groupby("grower"):
        axes[1].hist(grp["corn_years"], bins=5, alpha=0.6, label=label)
    axes[1].set_title("Corn Years in 5-Year Rotation", fontweight="bold")
    axes[1].set_xlabel("Corn years (out of 5)")
    axes[1].set_ylabel("Field count")
    axes[1].legend()
    fig.tight_layout()
    _save_fig(fig, "cdl_rotation_diversity.png")

    # Map: Dominant CDL crop as proportional bubbles (2025)
    dom_2025 = dominant[dominant["year"] == 2025].copy()
    b_map = boundaries[["field_id", "geometry", "area_acres"]].merge(
        dom_2025[["field_id", "crop_name"]], on="field_id", how="inner"
    )
    b_map = gpd.GeoDataFrame(b_map, geometry="geometry")
    fig, ax = plt.subplots(figsize=(10, 8))
    cents = b_map.geometry.centroid
    sizes = np.sqrt(b_map["area_acres"]) * 35
    crop_palette = {"Corn": "#f0c75e", "Soybeans": "#6db46d", "Grass/Pasture": "#b8c4a8",
                    "Forest": "#4a7c59", "Alfalfa": "#c4a882", "Winter Wheat": "#d4a04a"}
    for crop in b_map["crop_name"].unique():
        mask = b_map["crop_name"] == crop
        color = crop_palette.get(crop, "#999999")
        ax.scatter(cents.x[mask], cents.y[mask],
                   s=sizes[mask], c=color, label=crop,
                   alpha=0.7, edgecolor="black", linewidth=0.5)
    for acres, sz in [(10, np.sqrt(10) * 35), (100, np.sqrt(100) * 35), (300, np.sqrt(300) * 35)]:
        ax.scatter([], [], s=sz, c="gray", alpha=0.4, edgecolor="black", linewidth=0.5, label=f"{acres} ac")
    ax.legend(title="Crop / Size", loc="lower right", fontsize=8, title_fontsize=9)
    ax.set_title("Dominant CDL Crop Per Field, 2025 (bubble = area)", fontweight="bold")
    ax.set_axis_off()
    fig.tight_layout()
    _save_fig(fig, "cdl_dominant_crop_map.png")

    # Summary table
    cdl_summary = dominant.groupby(["grower", "year"]).agg(
        field_count=("field_id", "count"),
        corn_pct=("is_corn", "mean"),
        soybean_pct=("is_soybean", "mean"),
    ).reset_index()
    cdl_summary["corn_pct"] = (cdl_summary["corn_pct"] * 100).round(1)
    cdl_summary["soybean_pct"] = (cdl_summary["soybean_pct"] * 100).round(1)
    _save_csv(cdl_summary, "cdl_summary.csv")
    print(cdl_summary.to_string(index=False))


# ── Category 3: Weather ────────────────────────────────────────────────────


def weather_analyses(weather, boundaries):
    print("\n── Weather ──")

    weather["year"] = weather["date"].dt.year
    weather["month"] = weather["date"].dt.month

    w = weather.drop(columns=["grower"], errors="ignore").merge(
        boundaries[["field_id", "grower", "geometry"]], on="field_id", how="left"
    )

    # Stat Vis 1: Annual precipitation by grower
    annual_precip = (
        w.groupby(["grower", "year"])["PRECTOTCORR"].sum().reset_index()
    )
    # Convert mm to inches for readability
    annual_precip["precip_in"] = annual_precip["PRECTOTCORR"] / 25.4
    fig, ax = plt.subplots(figsize=(9, 5))
    for label in annual_precip["grower"].unique():
        grp = annual_precip[annual_precip["grower"] == label]
        ax.bar(grp["year"].astype(str) + f"\n{label}", grp["precip_in"], alpha=0.7, label=label)
    ax.set_title("Annual Total Precipitation by Grower", fontweight="bold")
    ax.set_ylabel("Precipitation (inches)")
    ax.tick_params(axis="x", labelsize=8)
    ax.legend()
    fig.tight_layout()
    _save_fig(fig, "weather_annual_precip.png")

    # Stat Vis 2: Monthly temperature profiles by grower
    monthly_temps = (
        w.groupby(["grower", "month"])["T2M"]
        .agg(["mean", "std"])
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    for label in monthly_temps["grower"].unique():
        grp = monthly_temps[monthly_temps["grower"] == label]
        ax.plot(grp["month"], grp["mean"], "o-", label=label)
        ax.fill_between(
            grp["month"],
            grp["mean"] - grp["std"],
            grp["mean"] + grp["std"],
            alpha=0.15,
        )
    ax.set_title("Monthly Temperature Profiles by Grower", fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.legend()
    ax.axhline(y=10, color="gray", linestyle="--", alpha=0.5, label="Growing base (10°C)")
    fig.tight_layout()
    _save_fig(fig, "weather_monthly_temps.png")

    # Comparison: Temperature vs Precipitation scatter by grower
    field_avg = (
        w.groupby(["grower", "field_id"])
        .agg(avg_temp=("T2M", "mean"), total_precip=("PRECTOTCORR", "sum"))
        .reset_index()
    )
    field_avg["total_precip_in"] = field_avg["total_precip"] / 25.4
    fig, ax = plt.subplots(figsize=(9, 6))
    for label in field_avg["grower"].unique():
        grp = field_avg[field_avg["grower"] == label]
        ax.scatter(grp["avg_temp"], grp["total_precip_in"], s=80,
                   alpha=0.7, edgecolor="black", label=label)
    ax.set_title("Field-Level Temperature vs Precipitation", fontweight="bold")
    ax.set_xlabel("Average Temperature (°C)")
    ax.set_ylabel("Total Precipitation (inches)")
    ax.legend()
    fig.tight_layout()
    _save_fig(fig, "weather_temp_precip_scatter.png")

    # Map: Field-level average temperature as proportional bubbles
    field_avg_map = boundaries[["field_id", "geometry", "area_acres"]].merge(
        field_avg, on="field_id", how="inner"
    )
    field_avg_map = gpd.GeoDataFrame(field_avg_map, geometry="geometry")
    fig, ax = plt.subplots(figsize=(10, 8))
    cents = field_avg_map.geometry.centroid
    sizes = np.sqrt(field_avg_map["area_acres"]) * 35
    norm = plt.Normalize(field_avg_map["avg_temp"].min(), field_avg_map["avg_temp"].max())
    cmap = plt.cm.RdYlBu_r
    sc = ax.scatter(cents.x, cents.y, s=sizes, c=field_avg_map["avg_temp"],
                    cmap=cmap, norm=norm, alpha=0.7, edgecolor="black", linewidth=0.5)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.6)
    cbar.set_label("Mean Temp (°C)", fontsize=10)
    for acres, sz in [(10, np.sqrt(10) * 35), (100, np.sqrt(100) * 35), (300, np.sqrt(300) * 35)]:
        ax.scatter([], [], s=sz, c="gray", alpha=0.4, edgecolor="black", linewidth=0.5, label=f"{acres} ac")
    ax.legend(title="Field size", loc="lower right", fontsize=8, title_fontsize=9)
    ax.set_title("Field-Level Average Temperature, 2021–2025 (bubble = area)", fontweight="bold")
    ax.set_axis_off()
    fig.tight_layout()
    _save_fig(fig, "weather_avg_temp_map.png")

    # Summary table
    weather_summary = (
        w.groupby(["grower", "year"])
        .agg(
            avg_temp=("T2M", "mean"),
            total_precip_mm=("PRECTOTCORR", "sum"),
            avg_solar=("ALLSKY_SFC_SW_DWN", "mean"),
            avg_humidity=("RH2M", "mean"),
            avg_wind=("WS10M", "mean"),
        )
        .reset_index()
    )
    _save_csv(weather_summary, "weather_summary.csv")
    print(weather_summary.to_string(index=False))


# ── Combined Summary ──────────────────────────────────────────────────────


def combined_summary(boundaries, composition, weather):
    print("\n── Combined ──")

    weather_stats = (
        weather.groupby("field_id")
        .agg(
            avg_temp=("T2M", "mean"),
            total_precip_mm=("PRECTOTCORR", "sum"),
            avg_solar=("ALLSKY_SFC_SW_DWN", "mean"),
        )
        .reset_index()
    )

    dominant = composition.loc[composition.groupby(["field_id", "year"])["pct"].idxmax()]
    dom_2025 = dominant[dominant["year"] == 2025][["field_id", "crop_name"]].rename(
        columns={"crop_name": "dominant_crop_2025"}
    )

    combined = boundaries[["field_id", "grower", "area_acres"]].merge(
        weather_stats, on="field_id", how="left"
    ).merge(
        dom_2025, on="field_id", how="left"
    )

    _save_csv(combined, "combined_field_summary.csv")
    print(combined.to_string(index=False))


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("Assignment 2: Field-Level EDA")
    print("=" * 60)
    print(f"\nOutput: {_OUTPUT_BASE}")
    print(f"Growers: {len(GROWERS)} ({', '.join(l for _, _, l in GROWERS)})")

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading data...")
    boundaries = _load_all_boundaries()
    weather = _load_all_weather()
    composition = _load_all_cdl_composition()
    rotation = _load_all_cdl_rotation()

    print(f"  Boundaries: {len(boundaries)} fields")
    print(f"  Weather: {len(weather)} records")
    print(f"  CDL composition: {len(composition)} records")
    print(f"  CDL rotation: {len(rotation)} records")

    boundaries_analyses(boundaries)
    cdl_analyses(composition, rotation, boundaries)
    weather_analyses(weather, boundaries)
    combined_summary(boundaries, composition, weather)

    print(f"\n{'=' * 60}")
    print(f"Done. {len(list(_REPORTS_DIR.glob('*.png')))} PNGs, "
          f"{len(list(_TABLES_DIR.glob('*.csv')))} CSVs")
    print(f"Reports: {_REPORTS_DIR}")
    print(f"Tables:  {_TABLES_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
