#!/usr/bin/env python3
"""Generate a static field-year dashboard image for a single field.

Prototype: osm-1157043055, 2023, Soybeans
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.dates import DateFormatter
from matplotlib.gridspec import GridSpec

_DATA_ROOT = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "/tmp")).expanduser() / "data-pipeline"
_OUTPUT = _DATA_ROOT / "eda" / "field-comparison" / "plots"

# Prototype configuration
_FIELD_ID = "osm-1157043055"
_YEAR = 2023
_CROP = "Soybeans"
_GROWER = "ia-northern-grower"
_FARM = "ia-northern-grower-farm"


def _load_boundary() -> gpd.GeoDataFrame:
    path = _DATA_ROOT / "growers" / _GROWER / "farms" / _FARM / "boundary" / "field_boundaries.geojson"
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    return gdf[gdf["field_id"] == _FIELD_ID].copy()


def _load_ndvi_composite() -> tuple[np.ndarray | None, rasterio.Affine | None]:
    tif_path = (
        _DATA_ROOT
        / "growers"
        / _GROWER
        / "farms"
        / _FARM
        / "fields"
        / _FIELD_ID
        / "derived"
        / "features"
        / f"ndvi_year_{_YEAR}_composite.tif"
    )
    if not tif_path.exists():
        return None, None
    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype("float32")
        arr[arr == src.nodata] = np.nan
        return arr, src.transform


def _load_weather() -> pd.DataFrame:
    path = (
        _DATA_ROOT
        / "growers"
        / _GROWER
        / "farms"
        / _FARM
        / "fields"
        / _FIELD_ID
        / "weather"
        / "daily_weather.csv"
    )
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"].dt.year == _YEAR].copy()
    return df


def _load_ndvi_scenes() -> pd.DataFrame:
    """Load individual scene NDVI values from the satellite manifest."""
    manifest_path = (
        _DATA_ROOT
        / "growers"
        / _GROWER
        / "farms"
        / _FARM
        / "fields"
        / _FIELD_ID
        / "satellite"
        / "sentinel"
        / "manifest.json"
    )
    if not manifest_path.exists():
        return pd.DataFrame()
    manifest = json.loads(manifest_path.read_text())
    records = []
    for year_entry in manifest.get("years", []):
        if year_entry.get("year") != _YEAR:
            continue
        for scene in year_entry.get("scenes", []):
            scene_date = scene.get("scene_date")
            ndvi_tif = scene.get("ndvi_tif")
            if not scene_date or not ndvi_tif:
                continue
            ndvi_path = _DATA_ROOT / ndvi_tif
            if ndvi_path.exists():
                try:
                    with rasterio.open(ndvi_path) as src:
                        arr = src.read(1).astype("float32")
                        arr[arr == src.nodata] = np.nan
                        valid = arr[np.isfinite(arr)]
                        if len(valid) > 0:
                            records.append(
                                {
                                    "date": pd.to_datetime(scene_date),
                                    "ndvi_mean": float(np.nanmean(valid)),
                                    "ndvi_max": float(np.nanmax(valid)),
                                    "ndvi_min": float(np.nanmin(valid)),
                                }
                            )
                except Exception:
                    pass
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def main() -> None:
    _OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"Generating dashboard for {_FIELD_ID} {_YEAR} {_CROP}...")

    # Load data
    boundary = _load_boundary()
    ndvi_arr, ndvi_transform = _load_ndvi_composite()
    weather = _load_weather()
    ndvi_scenes = _load_ndvi_scenes()

    print(f"  Boundary: {len(boundary)} feature(s)")
    print(f"  NDVI composite: {'YES' if ndvi_arr is not None else 'NO'}")
    print(f"  Weather days: {len(weather)}")
    print(f"  NDVI scene points: {len(ndvi_scenes)}")

    # Create figure
    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(3, 2, figure=fig, height_ratios=[1.2, 1, 1], hspace=0.35, wspace=0.3)

    # Title
    fig.suptitle(
        f"Field-Year Dashboard: {_FIELD_ID}\n{_YEAR} | {_CROP} | {_GROWER}",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    # Panel 1: Field boundary map
    ax_map = fig.add_subplot(gs[0, 0])
    if not boundary.empty:
        boundary.plot(ax=ax_map, color="#2ecc71", edgecolor="black", linewidth=1.5, alpha=0.7)
        bounds = boundary.total_bounds
        ax_map.set_xlim(bounds[0] - 0.001, bounds[2] + 0.001)
        ax_map.set_ylim(bounds[1] - 0.001, bounds[3] + 0.001)
    ax_map.set_title("Field Boundary", fontsize=12, fontweight="bold")
    ax_map.set_xlabel("Longitude")
    ax_map.set_ylabel("Latitude")
    ax_map.set_aspect("equal")

    # Panel 2: NDVI composite raster
    ax_raster = fig.add_subplot(gs[0, 1])
    if ndvi_arr is not None:
        im = ax_raster.imshow(
            ndvi_arr,
            cmap="RdYlGn",
            vmin=-0.2,
            vmax=1.0,
            interpolation="nearest",
        )
        plt.colorbar(im, ax=ax_raster, fraction=0.046, pad=0.04, label="NDVI")
    ax_raster.set_title(f"NDVI Composite {_YEAR}", fontsize=12, fontweight="bold")
    ax_raster.set_xlabel("Pixel")
    ax_raster.set_ylabel("Pixel")

    # Panel 3: NDVI time series
    ax_ndvi = fig.add_subplot(gs[1, :])
    if not ndvi_scenes.empty:
        ax_ndvi.plot(
            ndvi_scenes["date"],
            ndvi_scenes["ndvi_mean"],
            marker="o",
            linestyle="-",
            color="#27ae60",
            linewidth=2,
            markersize=6,
            label="Mean NDVI",
        )
        ax_ndvi.fill_between(
            ndvi_scenes["date"],
            ndvi_scenes["ndvi_min"],
            ndvi_scenes["ndvi_max"],
            alpha=0.2,
            color="#27ae60",
            label="Min-Max Range",
        )
        # Add crop growth stage annotations
        ax_ndvi.axvspan(
            pd.Timestamp(f"{_YEAR}-05-01"), pd.Timestamp(f"{_YEAR}-06-15"),
            alpha=0.1, color="blue", label="Planting-V6"
        )
        ax_ndvi.axvspan(
            pd.Timestamp(f"{_YEAR}-06-15"), pd.Timestamp(f"{_YEAR}-08-15"),
            alpha=0.1, color="green", label="V6-R2 (Peak Growth)"
        )
        ax_ndvi.axvspan(
            pd.Timestamp(f"{_YEAR}-08-15"), pd.Timestamp(f"{_YEAR}-09-30"),
            alpha=0.1, color="orange", label="R2-Harvest"
        )
    ax_ndvi.set_title("NDVI Time Series (Sentinel-2 Scenes)", fontsize=12, fontweight="bold")
    ax_ndvi.set_xlabel("Date")
    ax_ndvi.set_ylabel("NDVI")
    ax_ndvi.set_ylim(-0.2, 1.0)
    ax_ndvi.legend(loc="lower right", fontsize=8)
    ax_ndvi.xaxis.set_major_formatter(DateFormatter("%b"))
    ax_ndvi.grid(True, alpha=0.3)

    # Panel 4: Temperature
    ax_temp = fig.add_subplot(gs[2, 0])
    if not weather.empty:
        gs_mask = weather["date"].dt.month.isin([5, 6, 7, 8, 9])
        gs_weather = weather[gs_mask]
        ax_temp.plot(
            gs_weather["date"],
            gs_weather["T2M_MAX"],
            color="#e74c3c",
            alpha=0.6,
            linewidth=0.8,
            label="Daily Max",
        )
        ax_temp.plot(
            gs_weather["date"],
            gs_weather["T2M_MIN"],
            color="#3498db",
            alpha=0.6,
            linewidth=0.8,
            label="Daily Min",
        )
        ax_temp.plot(
            gs_weather["date"],
            gs_weather["T2M"],
            color="#2c3e50",
            linewidth=1.5,
            label="Daily Mean",
        )
    ax_temp.set_title("Growing-Season Temperature", fontsize=12, fontweight="bold")
    ax_temp.set_xlabel("Date")
    ax_temp.set_ylabel("Temperature (°C)")
    ax_temp.legend(loc="upper right", fontsize=8)
    ax_temp.xaxis.set_major_formatter(DateFormatter("%b"))
    ax_temp.grid(True, alpha=0.3)

    # Panel 5: Precipitation
    ax_precip = fig.add_subplot(gs[2, 1])
    if not weather.empty:
        gs_mask = weather["date"].dt.month.isin([5, 6, 7, 8, 9])
        gs_weather = weather[gs_mask]
        ax_precip.bar(
            gs_weather["date"],
            gs_weather["PRECTOTCORR"],
            color="#3498db",
            alpha=0.7,
            width=1.5,
        )
        # Cumulative line
        cumsum = gs_weather["PRECTOTCORR"].cumsum()
        ax_precip_twin = ax_precip.twinx()
        ax_precip_twin.plot(
            gs_weather["date"],
            cumsum,
            color="#e74c3c",
            linewidth=2,
            label="Cumulative",
        )
        ax_precip_twin.set_ylabel("Cumulative Precipitation (mm)", color="#e74c3c")
        ax_precip_twin.tick_params(axis="y", labelcolor="#e74c3c")
    ax_precip.set_title("Growing-Season Precipitation", fontsize=12, fontweight="bold")
    ax_precip.set_xlabel("Date")
    ax_precip.set_ylabel("Daily Precipitation (mm)")
    ax_precip.xaxis.set_major_formatter(DateFormatter("%b"))
    ax_precip.grid(True, alpha=0.3)

    # Footer annotation
    fig.text(
        0.5,
        0.01,
        f"Data sources: OSM boundaries, USDA NASS CDL, NASA POWER weather, Sentinel-2 NDVI | Generated: 2026-07-20",
        ha="center",
        fontsize=9,
        color="#666",
    )

    output_path = _OUTPUT / f"prototype_{_FIELD_ID}_{_YEAR}_{_CROP.lower()}_dashboard.png"
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved dashboard to: {output_path}")


if __name__ == "__main__":
    main()
