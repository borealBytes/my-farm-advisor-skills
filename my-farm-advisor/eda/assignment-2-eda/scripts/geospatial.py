import os
from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATA_ROOT = Path(os.environ.get(
    "DATA_PIPELINE_DATA_ROOT",
    os.path.expanduser("~/my-farm-advisor-runtime/data-pipeline"),
))
GROWERS = DATA_ROOT / "growers"
OUTPUT = DATA_ROOT.parent / "eda-outputs" / "geospatial"

GROWERS_CONFIG = [
    ("illinois-grower", "illinois-farm", "Illinois (DeKalb Co.)", "#66c2a5"),
    ("iowa-grower", "iowa-farm", "Iowa (Cerro Gordo Co.)", "#fc8d62"),
    ("nebraska-grower", "nebraska-farm", "Nebraska (Merrick Co.)", "#8da0cb"),
]

TAB10 = plt.cm.tab10(np.linspace(0, 1, 10))


def load_boundaries(grower_slug: str, farm_slug: str) -> gpd.GeoDataFrame:
    path = GROWERS / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    return gdf


def plot_panel(ax, gdf: gpd.GeoDataFrame, title: str, color: str):
    gdf_3857 = gdf.to_crs("EPSG:3857")
    bounds = gdf_3857.total_bounds
    margin_x = (bounds[2] - bounds[0]) * 0.05
    margin_y = (bounds[3] - bounds[1]) * 0.05
    ax.set_xlim(bounds[0] - margin_x, bounds[2] + margin_x)
    ax.set_ylim(bounds[1] - margin_y, bounds[3] + margin_y)
    ax.axis("off")

    for i, (_, row) in enumerate(gdf_3857.iterrows()):
        field_color = TAB10[i % 10]
        gdf_3857.iloc[[i]].plot(
            ax=ax,
            color=field_color,
            edgecolor="white",
            linewidth=0.8,
            alpha=0.65,
        )
        centroid = row.geometry.centroid
        ax.annotate(
            str(i + 1),
            xy=(centroid.x, centroid.y),
            fontsize=5,
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
            bbox=dict(boxstyle="circle,pad=0.15", facecolor="black", alpha=0.5),
        )

    total_acres = gdf["area_acres"].sum()
    n_fields = len(gdf)
    ax.set_title(f"{title}\n{n_fields} fields, {total_acres:.0f} ac", fontsize=9)

    try:
        ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, crs="EPSG:3857")
    except Exception:
        try:
            ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, crs="EPSG:3857")
        except Exception:
            ax.set_facecolor("#e8e8e8")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    for ax, (grower_slug, farm_slug, label, color) in zip(axes, GROWERS_CONFIG):
        print(f"Loading {label} boundaries...")
        gdf = load_boundaries(grower_slug, farm_slug)
        print(f"  {len(gdf)} fields, {gdf['area_acres'].sum():.0f} total acres")
        plot_panel(ax, gdf, label, color)

    fig.suptitle(
        "Field boundaries across the Corn Belt: Illinois → Iowa → Nebraska",
        fontsize=13, y=0.98,
    )
    fig.tight_layout()
    out = OUTPUT / "field_boundaries_map.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Done. Output: {out}")


if __name__ == "__main__":
    main()
