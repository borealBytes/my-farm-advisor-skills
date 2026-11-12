"""Field boundary downloader using real OpenStreetMap polygons.

This module avoids synthetic polygon generation and fetches real mapped
agricultural landuse polygons from Overpass API.
"""

from __future__ import annotations

import os
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from shapely.geometry import Polygon

HAS_DEPS = True


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Overpass returns HTTP 406 to requests' default UA; identify the client.
USER_AGENT = "my-farm-advisor/1.0 (field-boundaries; field_boundaries)"
REGION_BBOX = {
    "corn_belt": (40.45, -93.95, 40.85, -93.45),
    "great_plains": (40.55, -98.35, 40.95, -97.85),
    "southeast": (33.05, -84.45, 33.45, -83.95),
}
CROPS = ["corn", "soybeans", "wheat", "cotton"]


def _overpass_query(bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:120];
    (
      way["landuse"~"farmland|orchard|vineyard|meadow"]({south},{west},{north},{east});
    );
    out geom;
    """
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def _to_geodataframe(elements: list[dict[str, Any]], region: str) -> gpd.GeoDataFrame:
    records: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") != "way":
            continue
        geom = element.get("geometry", [])
        if len(geom) < 4:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        try:
            polygon = Polygon(coords)
            if not polygon.is_valid or polygon.area == 0:
                continue
        except Exception:
            continue

        tags = element.get("tags", {})
        crop = tags.get("crop") or tags.get("landuse", "Unknown")
        records.append(
            {
                "field_id": f"OSM_{element.get('id')}",
                "region": region,
                "crop_name": str(crop),
                "source": "OpenStreetMap/Overpass",
                "geometry": polygon,
            }
        )

    if not records:
        empty = pd.DataFrame(columns=["field_id", "region", "crop_name", "source"])  # type: ignore[arg-type]
        return gpd.GeoDataFrame(empty, geometry=[], crs="EPSG:4326")

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    area_proj = gdf.to_crs("EPSG:5070")
    gdf["area_acres"] = area_proj.geometry.area / 4046.8564224
    return gdf


def download_fields(
    count: int = 20,
    regions: list[str] | None = None,
    crops: list[str] | None = None,
    output_path: str | None = None,
    year: int = 2023,
) -> gpd.GeoDataFrame:
    """Download real field-like polygons from OSM for agricultural analysis.

    Args mirror previous API for compatibility.
    """
    if not HAS_DEPS:
        raise ImportError("Required packages not installed")
    if count < 1 or count > 1000:
        raise ValueError("count must be between 1 and 1000")

    selected_regions = regions or ["corn_belt"]
    invalid = set(selected_regions) - set(REGION_BBOX.keys())
    if invalid:
        raise ValueError(f"Invalid regions: {invalid}. Valid: {list(REGION_BBOX.keys())}")

    all_frames: list[gpd.GeoDataFrame] = []
    for region in selected_regions:
        payload = _overpass_query(REGION_BBOX[region])
        region_gdf = _to_geodataframe(payload.get("elements", []), region)
        if not region_gdf.empty:
            all_frames.append(region_gdf)

    if not all_frames:
        raise RuntimeError("No real polygons returned by Overpass. Try a different region.")

    gdf = gpd.GeoDataFrame(
        pd.concat(all_frames, ignore_index=True), geometry="geometry", crs="EPSG:4326"
    )

    if crops:
        crop_terms = [c.lower() for c in crops]
        mask = gdf["crop_name"].str.lower().apply(lambda val: any(t in val for t in crop_terms))
        filtered = gdf[mask]
        if not filtered.empty:
            gdf = filtered

    gdf = gdf.sort_values(by="area_acres", ascending=False).head(count).reset_index(drop=True)  # type: ignore[call-overload]

    if output_path:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        gdf.to_file(output_path, driver="GeoJSON")
        print(f"Saved {len(gdf)} real polygons to {output_path}")

    return gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")


def plot_fields(
    fields: gpd.GeoDataFrame,
    title: str = "Agricultural Fields",
    color_by: str | None = None,
    save_path: str | None = None,
) -> None:
    if not HAS_DEPS:
        raise ImportError("Required packages not installed")
    fig, ax = plt.subplots(figsize=(12, 8))
    if color_by and color_by in fields.columns:
        fields.plot(column=color_by, ax=ax, legend=True)
    else:
        fields.plot(ax=ax, color="lightgreen", edgecolor="darkgreen")
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    if save_path:
        out_dir = os.path.dirname(save_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
    else:
        plt.show()
    plt.close()


def get_summary(fields: gpd.GeoDataFrame) -> dict[str, Any]:
    areas = (
        fields["area_acres"]
        if "area_acres" in fields.columns
        else fields.to_crs("EPSG:5070").area / 4046.8564224
    )
    return {
        "total_fields": len(fields),
        "total_area_acres": float(areas.sum()),
        "avg_field_size": float(areas.mean()),
        "median_field_size": float(areas.median()),
        "size_range": (float(areas.min()), float(areas.max())),
        "std_field_size": float(areas.std()),
        "regions": fields["region"].dropna().unique().tolist()
        if "region" in fields.columns
        else [],
        "crops": fields["crop_name"].dropna().unique().tolist()
        if "crop_name" in fields.columns
        else [],
    }


def filter_by_size(
    fields: gpd.GeoDataFrame, min_acres: float = 0, max_acres: float | None = None
) -> gpd.GeoDataFrame:
    areas = (
        fields["area_acres"]
        if "area_acres" in fields.columns
        else fields.to_crs("EPSG:5070").area / 4046.8564224
    )
    mask = areas >= min_acres
    if max_acres is not None:
        mask = mask & (areas <= max_acres)
    return gpd.GeoDataFrame(fields[mask].copy(), geometry="geometry", crs=fields.crs)


def export_fields(fields: gpd.GeoDataFrame, output_path: str, format: str = "geojson") -> str:
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    if format.lower() == "geojson":
        fields.to_file(output_path, driver="GeoJSON")
    elif format.lower() == "geoparquet":
        fields.to_parquet(output_path)
    else:
        raise ValueError(f"Unsupported format: {format}")
    print(f"Exported {len(fields)} fields to {output_path}")
    return output_path
