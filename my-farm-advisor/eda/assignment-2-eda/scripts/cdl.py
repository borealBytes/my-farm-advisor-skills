import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr

DATA_ROOT = Path(os.environ.get(
    "DATA_PIPELINE_DATA_ROOT",
    os.path.expanduser("~/my-farm-advisor-runtime/data-pipeline"),
))
GROWERS = DATA_ROOT / "growers"
OUTPUT = DATA_ROOT.parent / "eda-outputs" / "cdl"

GROWERS_CONFIG = [
    ("illinois-grower", "illinois-farm", "Illinois"),
    ("iowa-grower", "iowa-farm", "Iowa"),
    ("nebraska-grower", "nebraska-farm", "Nebraska"),
]

sns.set_theme(style="whitegrid", palette="Set2")

COLORS = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}

CROP_COLORS = {
    "Corn": "#ffd300",
    "Soybeans": "#007c00",
    "Winter Wheat": "#d3a06a",
    "Alfalfa": "#a800e6",
    "Grass/Pasture": "#b2b26b",
    "Forest": "#007a3d",
    "Fallow/Idle Cropland": "#bfbfbf",
    "Other Hay": "#b26636",
}
CROP_ORDER = ["Corn", "Soybeans", "Winter Wheat", "Alfalfa", "Grass/Pasture", "Forest", "Fallow/Idle Cropland", "Other Hay"]


def load_composition() -> pd.DataFrame:
    records = []
    for grower_slug, farm_slug, label in GROWERS_CONFIG:
        path = GROWERS / grower_slug / "farms" / farm_slug / "derived" / "tables" / f"{label.lower()}_cdl_2021_2025_full_composition.csv"
        df = pd.read_csv(path)
        df["grower"] = label
        records.append(df)
    return pd.concat(records, ignore_index=True)


def load_rotations() -> pd.DataFrame:
    records = []
    for grower_slug, farm_slug, label in GROWERS_CONFIG:
        path = GROWERS / grower_slug / "farms" / farm_slug / "derived" / "tables" / f"{label.lower()}_crop_rotation.csv"
        df = pd.read_csv(path)
        df["grower"] = label
        records.append(df)
    return pd.concat(records, ignore_index=True)


def get_dominant_crop(comp: pd.DataFrame) -> pd.DataFrame:
    idx = comp.groupby(["grower", "field_id", "year"])["pct"].idxmax()
    dominant = comp.loc[idx, ["grower", "field_id", "year", "crop_name", "pct"]].copy()
    dominant["crop_name"] = dominant["crop_name"].map(lambda x: x if x in CROP_COLORS else "Other")
    return dominant


def plot_crop_composition(comp: pd.DataFrame, output: Path):
    agg = comp.groupby(["grower", "crop_name"])["pct"].sum().reset_index()
    agg["crop_name"] = agg["crop_name"].map(lambda x: x if x in CROP_COLORS else "Other")
    pivot = agg.pivot_table(index="grower", columns="crop_name", values="pct", fill_value=0)
    for col in CROP_ORDER:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot[CROP_ORDER]
    pivot = pivot.div(pivot.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(9, 4))
    bottom = np.zeros(len(pivot))
    for crop in CROP_ORDER:
        if crop not in pivot.columns:
            continue
        vals = pivot[crop].values
        if vals.sum() == 0:
            continue
        ax.barh(pivot.index, vals, left=bottom, label=crop, color=CROP_COLORS.get(crop, "#999999"))
        bottom += vals

    ax.set_xlabel("Percent of total pixels (%)")
    ax.set_title("5-year crop composition by grower")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output / "crop_composition.png", dpi=150)
    plt.close(fig)


def plot_crop_diversity(rotations: pd.DataFrame, output: Path):
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, grower in zip(axes, ["Illinois", "Iowa", "Nebraska"]):
        subset = rotations[rotations["grower"] == grower]
        ax.hist(subset["crop_diversity"], bins=range(1, 7), align="left", rwidth=0.7, color= "#66c2a5" if grower == "Illinois" else "#fc8d62" if grower == "Iowa" else "#8da0cb")
        ax.set_title(grower)
        ax.set_xlabel("Unique crops per field (5 yr)")
        ax.set_ylabel("Field count")
    fig.suptitle("Crop diversity by grower")
    fig.tight_layout()
    fig.savefig(output / "crop_diversity.png", dpi=150)
    plt.close(fig)


def plot_rotation_heatmap(dominant: pd.DataFrame, rotations: pd.DataFrame, output: Path):
    dominant = dominant.sort_values(["grower", "field_id", "year"]).reset_index(drop=True)
    dominant["field_label"] = dominant.apply(lambda r: f"{r['grower'][:2]}-{r['field_id'].split('-')[1][-4:]}", axis=1)

    field_order = []
    for g in ["Illinois", "Iowa", "Nebraska"]:
        sub = dominant[dominant["grower"] == g]
        # sort fields by mean latitude or just alphabetical
        sub = sub.sort_values("field_id")
        field_order.extend(sub["field_label"].unique().tolist())

    pivot = dominant.pivot_table(index="field_label", columns="year", values="crop_name", aggfunc="first")
    pivot = pivot.reindex(field_order)

    years = sorted(dominant["year"].unique())
    n_fields = len(pivot)
    cmap = {c: i for i, c in enumerate(CROP_ORDER)}
    color_map = [CROP_COLORS.get(c, "#999999") for c in CROP_ORDER]

    data = np.full((n_fields, len(years)), np.nan)
    for i, field in enumerate(pivot.index):
        for j, yr in enumerate(years):
            crop = pivot.loc[field, yr] if yr in pivot.columns else None
            if pd.notna(crop) and crop in cmap:
                data[i, j] = cmap[crop]

    fig, ax = plt.subplots(figsize=(10, max(5, n_fields * 0.35)))
    im = ax.imshow(data, aspect="auto", cmap=plt.matplotlib.colors.ListedColormap(color_map),
                   vmin=-0.5, vmax=len(CROP_ORDER) - 0.5)

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years)
    ax.set_yticks(range(n_fields))
    ax.set_yticklabels(pivot.index, fontsize=7)
    ax.set_xlabel("Year")
    ax.set_ylabel("Field")
    ax.set_title("Dominant crop per field-year by grower")

    patches = [mpatches.Patch(color=CROP_COLORS[c], label=c) for c in CROP_ORDER if c in cmap]
    ax.legend(handles=patches, loc="upper right", fontsize=7, ncol=2)

    fig.tight_layout()
    fig.savefig(output / "rotation_heatmap.png", dpi=150)
    plt.close(fig)


def load_field_sizes() -> pd.DataFrame:
    records = []
    for grower_slug, farm_slug, label in GROWERS_CONFIG:
        path = GROWERS / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
        gdf = gpd.read_file(path)
        for _, row in gdf.iterrows():
            records.append({"field_id": row["field_id"], "area_acres": row["area_acres"], "grower": label})
    return pd.DataFrame(records)


def plot_crop_vs_fieldsize(comp: pd.DataFrame, field_sizes: pd.DataFrame, output: Path):
    corn = comp[comp["crop_name"] == "Corn"].copy()
    corn = corn.merge(field_sizes, on=["field_id", "grower"], how="left")
    corn = corn.dropna(subset=["area_acres"])

    fig, ax = plt.subplots(figsize=(8, 6))
    for grower in ["Illinois", "Iowa", "Nebraska"]:
        subset = corn[corn["grower"] == grower]
        ax.scatter(
            subset["area_acres"], subset["pct"],
            c=COLORS[grower], label=grower, alpha=0.6, s=30,
            edgecolors="black", linewidths=0.3,
        )
        if len(subset) > 2:
            rho, p = spearmanr(subset["area_acres"], subset["pct"])
            p_str = f"p={p:.3f}" if p >= 0.001 else "p<0.001"
            ax.annotate(
                f"{grower}: ρ={rho:.2f} ({p_str})",
                xy=(0.95, 0.95 - 0.08 * ["Illinois", "Iowa", "Nebraska"].index(grower)),
                xycoords="axes fraction", fontsize=8, ha="right", va="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
            )

    ax.set_xlabel("Field size (acres)")
    ax.set_ylabel("Corn % of field pixels")
    ax.set_title("Corn percentage vs field size by grower (field-year points)")
    ax.legend()
    ax.set_xscale("log")
    fig.tight_layout()
    fig.savefig(output / "crop_vs_fieldsize.png", dpi=150)
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Loading CDL composition data...")
    comp = load_composition()
    print(f"  {len(comp)} rows loaded")

    print("Loading rotation data...")
    rotations = load_rotations()
    print(f"  {len(rotations)} rows loaded")

    print("Loading field sizes...")
    field_sizes = load_field_sizes()
    print(f"  {len(field_sizes)} fields")

    print("Determining dominant crops...")
    dominant = get_dominant_crop(comp)
    print(f"  {len(dominant)} field-year records")

    print("Plotting crop composition...")
    plot_crop_composition(comp, OUTPUT)

    print("Plotting crop diversity...")
    plot_crop_diversity(rotations, OUTPUT)

    print("Plotting rotation heatmap...")
    plot_rotation_heatmap(dominant, rotations, OUTPUT)

    print("Plotting crop vs field size...")
    plot_crop_vs_fieldsize(comp, field_sizes, OUTPUT)

    print(f"Done. Outputs in {OUTPUT}")


if __name__ == "__main__":
    main()
