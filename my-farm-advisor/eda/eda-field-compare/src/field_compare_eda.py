#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.use("Agg")
sns.set_theme(style="whitegrid")

GROWERS = [
    {"slug": "il-grower", "farm": "il-grower-illinois", "label": "Illinois"},
    {"slug": "ia-grower", "farm": "ia-grower-iowa", "label": "Iowa"},
    {"slug": "ne-grower", "farm": "ne-grower-nebraska", "label": "Nebraska"},
]


def _resolve_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if raw:
        return Path(raw) / "data-pipeline"
    return Path.home() / "my-farm-advisor-runtime" / "data-pipeline"


def _grower_prefix(grower: str) -> str:
    return grower.replace("-", "_")


def _farm_prefix(farm: str) -> str:
    return farm.replace("-", "_")


def _table_prefix(grower: str, farm: str) -> str:
    state = farm[len(grower) + 1:] if farm.startswith(grower) else farm
    return _grower_prefix(grower) + "_" + state


def load_boundaries(data_root: Path) -> pd.DataFrame:
    frames = []
    for g in GROWERS:
        path = (
            data_root
            / "growers"
            / g["slug"]
            / "farms"
            / g["farm"]
            / "boundary"
            / "field_boundaries.geojson"
        )
        gdf = gpd.read_file(path)
        gdf["grower"] = g["label"]
        frames.append(gdf)
    return pd.concat(frames, ignore_index=True)


def load_cdl(data_root: Path) -> dict[str, pd.DataFrame]:
    comp_frames = []
    rot_frames = []
    for g in GROWERS:
        prefix = _table_prefix(g["slug"], g["farm"])
        base = data_root / "growers" / g["slug"] / "farms" / g["farm"] / "derived" / "tables"
        comp_path = base / f"{prefix}_cdl_2021_2025_full_composition.csv"
        rot_path = base / f"{prefix}_crop_rotation.csv"
        cdf = pd.read_csv(comp_path)
        cdf["grower"] = g["label"]
        comp_frames.append(cdf)
        rdf = pd.read_csv(rot_path)
        rdf["grower"] = g["label"]
        rot_frames.append(rdf)
    return {
        "composition": pd.concat(comp_frames, ignore_index=True),
        "rotation": pd.concat(rot_frames, ignore_index=True),
    }


def load_weather(data_root: Path) -> pd.DataFrame:
    frames = []
    for g in GROWERS:
        prefix = _table_prefix(g["slug"], g["farm"])
        path = (
            data_root
            / "growers"
            / g["slug"]
            / "farms"
            / g["farm"]
            / "derived"
            / "tables"
            / f"{prefix}_weather_2021_2025.csv"
        )
        df = pd.read_csv(path, parse_dates=["date"])
        df["grower"] = g["label"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def plot_field_size_distribution(bounds: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, (label, grp) in zip(axes, bounds.groupby("grower")):
        sns.histplot(grp["area_acres"], bins=8, kde=True, ax=ax, color="steelblue")
        ax.set_title(label)
        ax.set_xlabel("Area (acres)")
        ax.set_ylabel("Count")
    fig.suptitle("Field Size Distribution by Grower", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "field_size_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_size_distribution.png")


def plot_field_area_by_grower(bounds: pd.DataFrame, output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    order = ["Illinois", "Iowa", "Nebraska"]
    sns.boxplot(data=bounds, x="grower", y="area_acres", order=order, palette="Set2", hue="grower", legend=False, ax=ax)
    ax.set_title("Field Area by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Area (acres)")
    plt.tight_layout()
    plt.savefig(output_dir / "field_area_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_area_by_grower.png")


def plot_field_size_stats_table(bounds: pd.DataFrame, output_dir: Path) -> None:
    order = ["Illinois", "Iowa", "Nebraska"]
    stats = (
        bounds.groupby("grower")["area_acres"]
        .agg(["count", "mean", "median", "std", "min", "max"])
        .round(1)
        .reindex(order)
    )
    fig, (ax_bar, ax_tbl) = plt.subplots(2, 1, figsize=(8, 6), gridspec_kw={"height_ratios": [1, 1]})
    colors = sns.color_palette("Set2", n_colors=3)
    xpos = np.arange(len(order))
    means = stats["mean"].values
    stds = stats["std"].values
    ax_bar.bar(xpos, means, yerr=stds, capsize=5, color=colors, edgecolor="gray")
    ax_bar.set_xticks(xpos)
    ax_bar.set_xticklabels(order)
    ax_bar.set_ylabel("Mean Area (acres)")
    ax_bar.set_title("Mean Field Area by Grower (with std dev)", fontsize=13, fontweight="bold")
    ax_tbl.axis("off")
    tbl = ax_tbl.table(
        cellText=stats.values,
        rowLabels=stats.index,
        colLabels=stats.columns,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.5)
    plt.tight_layout()
    plt.savefig(output_dir / "field_size_stats_table.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_size_stats_table.png")


def plot_crop_composition(cdl: pd.DataFrame, output_dir: Path) -> None:
    order = ["Illinois", "Iowa", "Nebraska"]
    top = cdl.groupby(["grower", "crop_name"])["pct"].sum().reset_index()
    top["pct"] = top.groupby("grower")["pct"].transform(lambda x: x / x.sum() * 100)
    top = top.sort_values("pct", ascending=False)
    major = top.groupby("crop_name")["pct"].sum().nlargest(5).index
    top["crop"] = top["crop_name"].where(top["crop_name"].isin(major), "Other")
    pivot = top.pivot_table(index="grower", columns="crop", values="pct", aggfunc="sum").reindex(order)
    pivot = pivot.div(pivot.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 4))
    pivot.plot(kind="barh", stacked=True, ax=ax, colormap="Set3", edgecolor="gray", linewidth=0.5)
    ax.set_xlabel("Percent of total crop area (%)")
    ax.set_ylabel("")
    ax.set_title("Crop Composition by Grower (all years)", fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    plt.tight_layout()
    plt.savefig(output_dir / "crop_composition_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  crop_composition_by_grower.png")


def plot_crop_diversity(rotation: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, (label, grp) in zip(axes, rotation.groupby("grower")):
        max_div = int(grp["crop_diversity"].max())
        bins = range(1, max_div + 2)
        sns.histplot(grp["crop_diversity"], bins=bins, discrete=True, ax=ax, color="steelblue")
        ax.set_title(label)
        ax.set_xlabel("Distinct crops (5-year history)")
        ax.set_ylabel("Field count")
    fig.suptitle("Crop Diversity per Field by Grower", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "crop_diversity_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  crop_diversity_by_grower.png")


def plot_corn_soybean_tradeoff(rotation: pd.DataFrame, output_dir: Path) -> None:
    from scipy.stats import pearsonr

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}
    for label, grp in rotation.groupby("grower"):
        ax.scatter(
            grp["corn_years"], grp["soybean_years"],
            c=colors[label], label=label, s=60, edgecolors="gray", alpha=0.8,
        )
        mask = (grp["corn_years"] > 0) | (grp["soybean_years"] > 0)
        if mask.sum() > 1:
            r, p = pearsonr(grp.loc[mask, "corn_years"], grp.loc[mask, "soybean_years"])
            ax.annotate(
                f"{label}: r={r:.2f}{'*' if p<0.05 else ''}",
                xy=(0.98, 0.95 - 0.06 * list(rotation["grower"].unique()).index(label)),
                xycoords="axes fraction", ha="right", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8),
            )
    ax.set_xlabel("Corn years (out of 5)", fontsize=12)
    ax.set_ylabel("Soybean years (out of 5)", fontsize=12)
    ax.set_title("Corn vs Soybean Planting Frequency", fontsize=14, fontweight="bold")
    ax.legend()
    ax.set_xlim(-0.3, 5.3)
    ax.set_ylim(-0.3, 5.3)
    plt.tight_layout()
    plt.savefig(output_dir / "corn_soybean_tradeoff.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  corn_soybean_tradeoff.png")


def plot_monthly_temperature(weather: pd.DataFrame, output_dir: Path) -> None:
    order = ["Illinois", "Iowa", "Nebraska"]
    weather["month"] = weather["date"].dt.month
    monthly = weather.groupby(["grower", "field_id", "month"])["T2M"].mean().reset_index()
    stats = monthly.groupby(["grower", "month"])["T2M"].agg(["mean", "std"]).reset_index()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, label in zip(axes, order):
        grp = stats[stats["grower"] == label]
        ax.plot(grp["month"], grp["mean"], color="steelblue", linewidth=2)
        ax.fill_between(
            grp["month"],
            grp["mean"] - grp["std"],
            grp["mean"] + grp["std"],
            alpha=0.2,
            color="steelblue",
        )
        ax.set_title(label)
        ax.set_xlabel("Month")
        ax.set_ylabel("Mean T2M (°C)")
        ax.set_xticks(range(1, 13))
    fig.suptitle("Monthly Mean Temperature by Grower", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "monthly_temperature_profile.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  monthly_temperature_profile.png")


def plot_annual_precipitation(weather: pd.DataFrame, output_dir: Path) -> None:
    weather["year"] = weather["date"].dt.year
    annual = (
        weather.groupby(["grower", "year", "field_id"])["PRECTOTCORR"]
        .sum()
        .reset_index()
    )
    annual = annual.groupby(["grower", "year"])["PRECTOTCORR"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    order = ["Illinois", "Iowa", "Nebraska"]
    colors = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}
    width = 0.25
    x = np.arange(2021, 2026)
    for i, label in enumerate(order):
        grp = annual[annual["grower"] == label]
        vals = grp.set_index("year")["PRECTOTCORR"].reindex(x).values
        ax.bar(x + (i - 1) * width, vals, width, label=label, color=colors[label], edgecolor="gray")
    ax.set_xlabel("Year")
    ax.set_ylabel("Total Precipitation (mm)")
    ax.set_title("Annual Precipitation by Grower", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "annual_precipitation.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  annual_precipitation.png")


def plot_growing_season_climate(weather: pd.DataFrame, output_dir: Path) -> None:
    from scipy.stats import pearsonr

    weather["month"] = weather["date"].dt.month
    weather["year"] = weather["date"].dt.year
    gs = weather[weather["month"].between(4, 10)]
    gs_agg = gs.groupby(["grower", "field_id", "year"]).agg(
        mean_temp=("T2M", "mean"),
        total_precip=("PRECTOTCORR", "sum"),
    ).reset_index()
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}
    for label, grp in gs_agg.groupby("grower"):
        ax.scatter(
            grp["mean_temp"], grp["total_precip"],
            c=colors[label], label=label, s=50, alpha=0.7, edgecolors="gray",
        )
        if len(grp) > 2:
            r, p = pearsonr(grp["mean_temp"], grp["total_precip"])
            ax.annotate(
                f"{label}: r={r:.2f}{'*' if p<0.05 else ''}",
                xy=(0.98, 0.95 - 0.06 * list(gs_agg["grower"].unique()).index(label)),
                xycoords="axes fraction", ha="right", fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8),
            )
    ax.set_xlabel("Mean Growing-Season Temperature (°C)", fontsize=12)
    ax.set_ylabel("Total Growing-Season Precipitation (mm)", fontsize=12)
    ax.set_title("Growing-Season Climate by Grower (Apr-Oct)", fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "growing_season_climate.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  growing_season_climate.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Field comparison EDA across growers")
    parser.add_argument("--data-root", default=None, help="Path to data-pipeline root")
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory for PNGs (default: {data-root}/eda/field-compare/output)",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root) if args.data_root else _resolve_root()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else data_root / "eda" / "field-compare" / "output"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Data root: {data_root}")
    print(f"Output dir: {output_dir}")
    print()

    print("Loading field boundaries...")
    bounds = load_boundaries(data_root)
    print(f"  {len(bounds)} fields loaded")
    print()

    print("Loading CDL data...")
    cdl_data = load_cdl(data_root)
    print(f"  Composition: {len(cdl_data['composition'])} rows")
    print(f"  Rotation: {len(cdl_data['rotation'])} rows")
    print()

    print("Loading weather data...")
    weather = load_weather(data_root)
    print(f"  {len(weather)} rows")
    print()

    print("Generating visualizations...")
    print("--- Field Boundaries ---")
    plot_field_size_distribution(bounds, output_dir)
    plot_field_area_by_grower(bounds, output_dir)
    plot_field_size_stats_table(bounds, output_dir)
    print()

    print("--- CDL / Cropland ---")
    plot_crop_composition(cdl_data["composition"], output_dir)
    plot_crop_diversity(cdl_data["rotation"], output_dir)
    plot_corn_soybean_tradeoff(cdl_data["rotation"], output_dir)
    print()

    print("--- Weather ---")
    plot_monthly_temperature(weather, output_dir)
    plot_annual_precipitation(weather, output_dir)
    plot_growing_season_climate(weather, output_dir)
    print()

    print(f"Done. 9 outputs written to {output_dir}")


if __name__ == "__main__":
    main()
