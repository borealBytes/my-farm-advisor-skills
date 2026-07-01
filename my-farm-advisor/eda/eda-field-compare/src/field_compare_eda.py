#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import pearsonr, f_oneway

matplotlib.use("Agg")
sns.set_theme(style="whitegrid")
COLORS = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}
ORDER = ["Illinois", "Iowa", "Nebraska"]

GROWERS = [
    {"slug": "il-grower", "farm": "il-grower-illinois", "label": "Illinois", "fips": "17", "county": "Iroquois"},
    {"slug": "ia-grower", "farm": "ia-grower-iowa", "label": "Iowa", "fips": "19", "county": "Kossuth"},
    {"slug": "ne-grower", "farm": "ne-grower-nebraska", "label": "Nebraska", "fips": "31", "county": "Buffalo"},
]

_TERRAIN_AVAILABLE = False
_TERRAIN_NOTE = ""


def _resolve_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if raw:
        return Path(raw) / "data-pipeline"
    return Path.home() / "my-farm-advisor-runtime" / "data-pipeline"


def _grower_prefix(grower: str) -> str:
    return grower.replace("-", "_")


def _table_prefix(grower: str, farm: str) -> str:
    state = farm[len(grower) + 1:] if farm.startswith(grower) else farm
    return _grower_prefix(grower) + "_" + state


def load_boundaries(data_root: Path) -> gpd.GeoDataFrame:
    frames = []
    for g in GROWERS:
        path = data_root / "growers" / g["slug"] / "farms" / g["farm"] / "boundary" / "field_boundaries.geojson"
        gdf = gpd.read_file(path)
        gdf["grower"] = g["label"]
        frames.append(gdf)
    return pd.concat(frames, ignore_index=True)


def load_terrain_summaries(data_root: Path) -> pd.DataFrame | None:
    rows = []
    for g in GROWERS:
        base = data_root / "growers" / g["slug"] / "farms" / g["farm"] / "fields"
        field_dirs = sorted(base.iterdir()) if base.exists() else []
        for fd in field_dirs:
            summary_csv = fd / "terrain" / "derived" / "tables" / "dem_terrain_summary.csv"
            if summary_csv.exists():
                df = pd.read_csv(summary_csv)
                df["grower"] = g["label"]
                rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else None


def load_geoadmin(data_root: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    states = gpd.read_file(data_root / "shared" / "geoadmin" / "l1_states" / "states_usa.geojson")
    counties = gpd.read_file(data_root / "shared" / "geoadmin" / "l2_counties" / "counties_usa.geojson")
    return states, counties


def load_cdl(data_root: Path) -> dict[str, pd.DataFrame]:
    comp_frames = []
    rot_frames = []
    for g in GROWERS:
        prefix = _table_prefix(g["slug"], g["farm"])
        base = data_root / "growers" / g["slug"] / "farms" / g["farm"] / "derived" / "tables"
        cdf = pd.read_csv(base / f"{prefix}_cdl_2021_2025_full_composition.csv")
        cdf["grower"] = g["label"]
        comp_frames.append(cdf)
        rdf = pd.read_csv(base / f"{prefix}_crop_rotation.csv")
        rdf["grower"] = g["label"]
        rot_frames.append(rdf)
    return {"composition": pd.concat(comp_frames, ignore_index=True),
            "rotation": pd.concat(rot_frames, ignore_index=True)}


def load_weather(data_root: Path) -> pd.DataFrame:
    frames = []
    for g in GROWERS:
        prefix = _table_prefix(g["slug"], g["farm"])
        path = data_root / "growers" / g["slug"] / "farms" / g["farm"] / "derived" / "tables" / f"{prefix}_weather_2021_2025.csv"
        df = pd.read_csv(path, parse_dates=["date"])
        df["grower"] = g["label"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def plot_geospatial_context(bounds: gpd.GeoDataFrame, states: gpd.GeoDataFrame, counties: gpd.GeoDataFrame,
                            terrain: pd.DataFrame | None, output_dir: Path) -> None:
    target_fips = [g["fips"] for g in GROWERS]
    target_counties = [g["county"] for g in GROWERS]
    state_frame = states[states["state_fips"].astype(str).str.zfill(2).isin(target_fips)].to_crs("EPSG:3857")
    county_frame = counties[
        counties["county_name"].str.lower().isin([c.lower() for c in target_counties]) &
        counties["state_fips"].astype(str).str.zfill(2).isin(target_fips)
    ].to_crs("EPSG:3857")
    bounds_3857 = bounds.to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(14, 9))
    for _, row in state_frame.iterrows():
        gpd.GeoSeries([row["geometry"]]).plot(ax=ax, facecolor="none", edgecolor="#555555", linewidth=1.5, alpha=0.7)
    for _, row in county_frame.iterrows():
        gpd.GeoSeries([row["geometry"]]).plot(ax=ax, facecolor="none", edgecolor="#888888", linewidth=1, linestyle="--", alpha=0.5)
    for label, grp in bounds_3857.groupby("grower"):
        grp.plot(ax=ax, color=COLORS[label], label=label, edgecolor="white", linewidth=0.4, alpha=0.85)
    try:
        cx.add_basemap(ax, source=cx.providers.CartoDB.Positron, alpha=0.6)
    except Exception:
        pass
    for _, row in county_frame.iterrows():
        centroid = row["geometry"].centroid
        ax.annotate(row["county_name"], xy=(centroid.x, centroid.y), fontsize=11,
                    ha="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[g["label"]]) for g in GROWERS]
    labels = [f"{g['label']} ({g['county']} Co.) — {g['farm']}" for g in GROWERS]
    if terrain is not None and not terrain.empty:
        elev_stats = terrain.groupby("grower")["elevation_mean_m"].mean()
        for i, g in enumerate(GROWERS):
            if g["label"] in elev_stats.index:
                labels[i] += f"  |  ~{elev_stats[g['label']]:.0f}m elev"
    else:
        ne_note = "NE: Buffalo Co. ~655m elev" if False else ""
    ax.legend(handles, labels, loc="lower right", fontsize=9, framealpha=0.9)
    ax.set_title("Geospatial Context: 30 Fields Across Three States", fontsize=15, fontweight="bold")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(output_dir / "geospatial_context.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  geospatial_context.png")


def plot_field_size_distribution(bounds: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, (label, grp) in zip(axes, bounds.groupby("grower")):
        sns.histplot(grp["area_acres"], bins=8, kde=True, ax=ax, color=COLORS[label])
        ax.set_title(f"{label}\n(n={len(grp)} fields)", fontsize=12)
        ax.set_xlabel("Area (acres)")
        ax.set_ylabel("Field count")
        ax.text(0.95, 0.95, f"Median: {grp['area_acres'].median():.0f} ac", transform=ax.transAxes,
                ha="right", va="top", fontsize=9, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
    fig.suptitle("Field Size Distribution by Grower", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "field_size_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_size_distribution.png")


def plot_field_area_by_grower(bounds: pd.DataFrame, output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=bounds, x="grower", y="area_acres", order=ORDER, palette=COLORS, hue="grower", legend=False, ax=ax)
    ax.set_title("Field Area by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Area (acres)")
    for i, label in enumerate(ORDER):
        grp = bounds[bounds["grower"] == label]["area_acres"]
        ax.text(i, ax.get_ylim()[1] * 0.95, f"n={len(grp)}", ha="center", fontsize=10, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "field_area_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_area_by_grower.png")


def plot_field_size_comparison(bounds: pd.DataFrame, output_dir: Path) -> None:
    groups = [bounds[bounds["grower"] == label]["area_acres"].values for label in ORDER]
    f_stat, p_val = f_oneway(*groups)
    stats = bounds.groupby("grower")["area_acres"].agg(["count", "mean", "median", "std", "min", "max"]).round(1).reindex(ORDER)
    fig, (ax_bar, ax_tbl) = plt.subplots(2, 1, figsize=(9, 6.5), gridspec_kw={"height_ratios": [1, 1.1]})
    xpos = np.arange(len(ORDER))
    means = stats["mean"].values
    stds = stats["std"].values
    colors = [COLORS[label] for label in ORDER]
    ax_bar.bar(xpos, means, yerr=stds, capsize=5, color=colors, edgecolor="gray")
    ax_bar.set_xticks(xpos)
    ax_bar.set_xticklabels(ORDER)
    ax_bar.set_ylabel("Mean area (acres)")
    sig = "*" if p_val < 0.05 else "n.s."
    ax_bar.set_title(f"Mean Field Area Comparison\nANOVA: F={f_stat:.1f}, p={p_val:.4f} ({sig})", fontsize=13, fontweight="bold")
    for i, (m, s) in enumerate(zip(means, stds)):
        ax_bar.text(i, m + s + 5, f"{m:.0f} ± {s:.0f}", ha="center", fontsize=9, fontweight="bold")
    ax_tbl.axis("off")
    tbl = ax_tbl.table(cellText=stats.values, rowLabels=stats.index, colLabels=stats.columns,
                       loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.0, 1.5)
    plt.tight_layout()
    plt.savefig(output_dir / "field_size_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  field_size_comparison.png")


def plot_monthly_temperature(weather: pd.DataFrame, output_dir: Path) -> None:
    weather["month"] = weather["date"].dt.month
    monthly = weather.groupby(["grower", "field_id", "month"])["T2M"].mean().reset_index()
    stats = monthly.groupby(["grower", "month"])["T2M"].agg(["mean", "std"]).reset_index()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, label in zip(axes, ORDER):
        grp = stats[stats["grower"] == label]
        ax.plot(grp["month"], grp["mean"], color=COLORS[label], linewidth=2)
        ax.fill_between(grp["month"], grp["mean"] - grp["std"], grp["mean"] + grp["std"],
                        alpha=0.2, color=COLORS[label])
        summer = grp[(grp["month"] >= 5) & (grp["month"] <= 9)]
        ax.axhspan(summer["mean"].min(), summer["mean"].max(), xmin=0.3, xmax=0.7,
                   alpha=0.06, color="orange")
        ax.text(6.5, ax.get_ylim()[0] + 0.5, "growing\nseason", fontsize=8, ha="center", alpha=0.5)
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Month")
        ax.set_ylabel("Mean T2M (°C)")
        ax.set_xticks(range(1, 13))
    fig.suptitle("Monthly Temperature Profile (2021–2025 avg)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "monthly_temperature_profile.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  monthly_temperature_profile.png")


def plot_annual_precipitation(weather: pd.DataFrame, output_dir: Path) -> None:
    weather["year"] = weather["date"].dt.year
    annual = weather.groupby(["grower", "year", "field_id"])["PRECTOTCORR"].sum().reset_index()
    annual = annual.groupby(["grower", "year"])["PRECTOTCORR"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.25
    x = np.arange(2021, 2026)
    for i, label in enumerate(ORDER):
        grp = annual[annual["grower"] == label]
        vals = grp.set_index("year")["PRECTOTCORR"].reindex(x).values
        ax.bar(x + (i - 1) * width, vals, width, label=label, color=COLORS[label], edgecolor="gray")
    for label in ORDER:
        means = annual[annual["grower"] == label].set_index("year")["PRECTOTCORR"]
        ax.plot(x + 0.05 * (ORDER.index(label) - 1), means.reindex(x).values,
                color=COLORS[label], linewidth=1.5, marker="o", markersize=4, alpha=0.5)
    ax.set_xlabel("Year")
    ax.set_ylabel("Total precipitation (mm)")
    ax.set_title("Annual Precipitation by Grower", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.legend(title="Grower")
    ne_total = annual[annual["grower"] == "Nebraska"]["PRECTOTCORR"].mean()
    il_total = annual[annual["grower"] == "Illinois"]["PRECTOTCORR"].mean()
    ax.text(0.98, 0.08, f"NE receives ~{ne_total / il_total * 100:.0f}% of IL rainfall",
            transform=ax.transAxes, ha="right", fontsize=10, fontstyle="italic",
            bbox=dict(boxstyle="round", fc="white", alpha=0.8))
    plt.tight_layout()
    plt.savefig(output_dir / "annual_precipitation.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  annual_precipitation.png")


def plot_growing_season_climate(weather: pd.DataFrame, output_dir: Path) -> None:
    weather["month"] = weather["date"].dt.month
    weather["year"] = weather["date"].dt.year
    gs = weather[weather["month"].between(4, 10)]
    gs_agg = gs.groupby(["grower", "field_id", "year"]).agg(
        mean_temp=("T2M", "mean"), total_precip=("PRECTOTCORR", "sum")).reset_index()
    fig, ax = plt.subplots(figsize=(9, 6))
    for label, grp in gs_agg.groupby("grower"):
        ax.scatter(grp["mean_temp"], grp["total_precip"], c=COLORS[label], label=label,
                   s=50, alpha=0.7, edgecolors="gray")
        if len(grp) > 2:
            r, p = pearsonr(grp["mean_temp"], grp["total_precip"])
            sig = "*" if p < 0.05 else ""
            ax.annotate(f"{label}: r={r:.2f}{sig} (p={p:.3f})",
                        xy=(0.98, 0.95 - 0.06 * ORDER.index(label)), xycoords="axes fraction",
                        ha="right", fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))
    ax.set_xlabel("Mean growing-season temperature (°C)", fontsize=12)
    ax.set_ylabel("Total growing-season precipitation (mm)", fontsize=12)
    ax.set_title("Growing-Season Climate by Grower (Apr–Oct, all years)", fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "growing_season_climate.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  growing_season_climate.png")


def plot_crop_composition(cdl: pd.DataFrame, output_dir: Path) -> None:
    top = cdl.groupby(["grower", "crop_name"])["pct"].sum().reset_index()
    top["pct"] = top.groupby("grower")["pct"].transform(lambda x: x / x.sum() * 100)
    major = top.groupby("crop_name")["pct"].sum().nlargest(5).index
    top["crop"] = top["crop_name"].where(top["crop_name"].isin(major), "Other")
    pivot = top.pivot_table(index="grower", columns="crop", values="pct", aggfunc="sum").reindex(ORDER)
    pivot = pivot.div(pivot.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 4))
    pivot.plot(kind="barh", stacked=True, ax=ax, colormap="Set3", edgecolor="gray", linewidth=0.5)
    for i, label in enumerate(ORDER):
        corn_pct = pivot.loc[label, "Corn"] if "Corn" in pivot.columns else 0
        soy_pct = pivot.loc[label, "Soybeans"] if "Soybeans" in pivot.columns else 0
        ax.text(98, i, f"Corn {corn_pct:.0f}% / Soy {soy_pct:.0f}%", va="center", fontsize=9, ha="right",
                fontweight="bold")
    ax.set_xlabel("Percent of total crop area")
    ax.set_ylabel("")
    ax.set_title("Crop Composition by Grower (2021–2025)", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    plt.tight_layout()
    plt.savefig(output_dir / "crop_composition_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  crop_composition_by_grower.png")


def plot_crop_diversity(rotation: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for ax, (label, grp) in zip(axes, rotation.groupby("grower")):
        max_div = int(grp["crop_diversity"].max())
        bins = range(1, max_div + 2)
        sns.histplot(grp["crop_diversity"], bins=bins, discrete=True, ax=ax, color=COLORS[label])
        mc_count = (grp["crop_diversity"] == 1).sum()
        ax.text(0.95, 0.95, f"{mc_count} field(s) monoculture\n({mc_count / len(grp) * 100:.0f}%)",
                transform=ax.transAxes, ha="right", va="top", fontsize=9,
                bbox=dict(boxstyle="round", fc="white", alpha=0.7))
        ax.set_title(f"{label}\nmean diversity: {grp['crop_diversity'].mean():.1f}", fontsize=12)
        ax.set_xlabel("Distinct crops (5-year history)")
        ax.set_ylabel("Field count")
    fig.suptitle("Crop Diversity per Field by Grower", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_dir / "crop_diversity_by_grower.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  crop_diversity_by_grower.png")


def plot_corn_soybean_tradeoff(rotation: pd.DataFrame, output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, grp in rotation.groupby("grower"):
        ax.scatter(grp["corn_years"], grp["soybean_years"], c=COLORS[label], label=label,
                   s=60, edgecolors="gray", alpha=0.8)
        mask = (grp["corn_years"] > 0) | (grp["soybean_years"] > 0)
        if mask.sum() > 1:
            r, p = pearsonr(grp.loc[mask, "corn_years"], grp.loc[mask, "soybean_years"])
            ax.annotate(f"{label}: r={r:.2f}{'*' if p<0.05 else ''}",
                        xy=(0.98, 0.95 - 0.06 * ORDER.index(label)), xycoords="axes fraction",
                        ha="right", fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))
    ax.set_xlabel("Corn years (out of 5)", fontsize=12)
    ax.set_ylabel("Soybean years (out of 5)", fontsize=12)
    ax.set_title("Corn vs Soybean Planting Frequency\n(5-year rotation pattern)", fontsize=14, fontweight="bold")
    ax.legend()
    ax.set_xlim(-0.3, 5.3)
    ax.set_ylim(-0.3, 5.3)
    ax.plot([0, 5], [5, 0], "--", color="gray", linewidth=0.7, alpha=0.4)
    ax.annotate("Strict\nrotation\nline", xy=(4.5, 0.5), fontsize=8, color="gray", fontstyle="italic", alpha=0.5)
    plt.tight_layout()
    plt.savefig(output_dir / "corn_soybean_tradeoff.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  corn_soybean_tradeoff.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Field comparison EDA across growers — story-driven analysis")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    data_root = Path(args.data_root) if args.data_root else _resolve_root()
    output_dir = Path(args.output_dir) if args.output_dir else data_root / "eda" / "field-compare" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    global _TERRAIN_AVAILABLE
    print(f"Data root: {data_root}")
    print(f"Output dir: {output_dir}")
    print()

    print("Loading geoadmin boundaries...")
    states, counties = load_geoadmin(data_root)
    print(f"  {len(states)} states, {len(counties)} counties loaded")

    print("Loading field boundaries...")
    bounds = load_boundaries(data_root)
    print(f"  {len(bounds)} fields ({bounds['grower'].value_counts().to_dict()})")

    print("Checking for terrain data...")
    terrain = load_terrain_summaries(data_root)
    if terrain is not None and not terrain.empty:
        _TERRAIN_AVAILABLE = True
        print(f"  Found terrain data for {len(terrain)} field-runs")
    else:
        print("  No terrain data found (run pipeline with DEM terrain to enable)")
    print()

    print("Loading CDL data...")
    cdl_data = load_cdl(data_root)
    print(f"  Composition: {len(cdl_data['composition'])} rows, Rotation: {len(cdl_data['rotation'])} rows")

    print("Loading weather data...")
    weather = load_weather(data_root)
    print(f"  {len(weather):,} daily records (2021–2025)")
    print()

    print("=" * 60)
    print("STORY: Three States, Three Growing Environments")
    print("=" * 60)
    print()

    print("Act 1 — Geospatial Context <<<")  # ---- MAP ----
    plot_geospatial_context(bounds, states, counties, terrain, output_dir)
    print()

    print("Act 2 — Field Boundaries: The Physical Canvas <<<")
    plot_field_size_distribution(bounds, output_dir)
    plot_field_area_by_grower(bounds, output_dir)
    plot_field_size_comparison(bounds, output_dir)
    print()

    print("Act 3 — Weather: The Environmental Driver <<<")
    plot_monthly_temperature(weather, output_dir)
    plot_annual_precipitation(weather, output_dir)
    plot_growing_season_climate(weather, output_dir)
    print()

    print("Act 4 — CDL/Cropland: The Cropping Response <<<")
    plot_crop_composition(cdl_data["composition"], output_dir)
    plot_crop_diversity(cdl_data["rotation"], output_dir)
    plot_corn_soybean_tradeoff(cdl_data["rotation"], output_dir)
    print()

    print(f"Done. 10 outputs written to {output_dir}")
    if not _TERRAIN_AVAILABLE:
        print("Note: No terrain/elevation data was found. Run `run_farm_pipeline.py` with DEM terrain")
        print("  enabled to add elevation context. The script will automatically include it.")


if __name__ == "__main__":
    main()
