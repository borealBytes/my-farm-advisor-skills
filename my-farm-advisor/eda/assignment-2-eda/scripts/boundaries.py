import os
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

DATA_ROOT = Path(os.environ.get(
    "DATA_PIPELINE_DATA_ROOT",
    os.path.expanduser("~/my-farm-advisor-runtime/data-pipeline"),
))
GROWERS = DATA_ROOT / "growers"
OUTPUT = DATA_ROOT.parent / "eda-outputs" / "boundaries"

GROWERS_CONFIG = [
    ("illinois-grower", "illinois-farm", "Illinois"),
    ("iowa-grower", "iowa-farm", "Iowa"),
    ("nebraska-grower", "nebraska-farm", "Nebraska"),
]

sns.set_theme(style="whitegrid", palette="Set2")
COLORS = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}


def load_boundaries() -> pd.DataFrame:
    records = []
    for grower_slug, farm_slug, label in GROWERS_CONFIG:
        path = GROWERS / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
        gdf = gpd.read_file(path)
        projected = gdf.to_crs("EPSG:5070") if gdf.crs else gdf
        centroids_wgs84 = projected.geometry.centroid.to_crs("EPSG:4326")
        for i, row in gdf.iterrows():
            records.append({
                "grower": label,
                "field_id": row["field_id"],
                "area_acres": row["area_acres"],
                "lat": centroids_wgs84.iloc[i].y,
                "lon": centroids_wgs84.iloc[i].x,
            })
    df = pd.DataFrame(records)
    df["grower"] = pd.Categorical(df["grower"], categories=["Illinois", "Iowa", "Nebraska"])
    return df


def plot_size_distribution(df: pd.DataFrame, output: Path):
    fig, ax = plt.subplots(figsize=(8, 5))
    for grower in ["Illinois", "Iowa", "Nebraska"]:
        subset = df[df["grower"] == grower]
        sns.kdeplot(subset["area_acres"], label=grower, color=COLORS[grower], fill=True, alpha=0.3, ax=ax)
    ax.set_xlabel("Field size (acres)")
    ax.set_ylabel("Density")
    ax.set_title("Field size distribution by grower")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "field_size_distribution.png", dpi=150)
    plt.close(fig)


def plot_size_boxplot(df: pd.DataFrame, output: Path):
    fig, ax = plt.subplots(figsize=(7, 5))
    for i, grower in enumerate(["Illinois", "Iowa", "Nebraska"]):
        subset = df[df["grower"] == grower]
        bp = ax.boxplot(subset["area_acres"], positions=[i], widths=0.5,
                        patch_artist=True,
                        boxprops=dict(facecolor=COLORS[grower], alpha=0.7),
                        medianprops=dict(color="black"))
    ax.set_xticks(range(3))
    ax.set_xticklabels(["Illinois", "Iowa", "Nebraska"])
    sns.stripplot(data=df, x="grower", y="area_acres", color="black", alpha=0.4, size=6, ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel("Field size (acres)")
    ax.set_title("Field size variability by grower")
    fig.tight_layout()
    fig.savefig(output / "field_size_boxplot.png", dpi=150)
    plt.close(fig)


def plot_centroids(df: pd.DataFrame, output: Path):
    fig, ax = plt.subplots(figsize=(9, 6))
    for grower in ["Illinois", "Iowa", "Nebraska"]:
        subset = df[df["grower"] == grower]
        ax.scatter(
            subset["lon"], subset["lat"],
            s=subset["area_acres"] / 5,
            c=COLORS[grower],
            label=grower,
            alpha=0.8,
            edgecolors="black",
            linewidths=0.5,
        )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Field centroids by grower (point size = acres)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "field_centroids.png", dpi=150)
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Loading boundaries for all growers...")
    df = load_boundaries()
    print(f"  {len(df)} fields loaded")

    print("Plotting field size distribution...")
    plot_size_distribution(df, OUTPUT)

    print("Plotting field size boxplot...")
    plot_size_boxplot(df, OUTPUT)

    print("Plotting field centroids...")
    plot_centroids(df, OUTPUT)

    print(f"Done. Outputs in {OUTPUT}")


if __name__ == "__main__":
    main()
