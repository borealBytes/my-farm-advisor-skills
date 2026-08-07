#!/usr/bin/env python3
"""
data_loader.py — Load and integrate all farm data sources for the dashboard.

Reads from the data-pipeline runtime tree:
  - Field boundaries (GeoJSON)
  - SSURGO soil data (CSV)
  - NASA POWER weather (CSV)
  - CDL crop history (CSV)
  - NDVI composite TIFFs (via ndvi_extractor)

Outputs a single merged DataFrame per field plus supporting structures.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)


def _data_root() -> Path:
    """Resolve DATA_PIPELINE_DATA_ROOT from environment."""
    import os

    root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not root:
        raise RuntimeError(
            "DATA_PIPELINE_DATA_ROOT is not set. "
            "Export it before running the dashboard."
        )
    return Path(root) / "data-pipeline"


def discover_farm_slug(data_root: Path, grower_slug: str) -> str | None:
    farms_dir = data_root / "growers" / grower_slug / "farms"
    if not farms_dir.exists():
        return None
    subdirs = [d.name for d in farms_dir.iterdir() if d.is_dir()]
    return subdirs[0] if subdirs else None


def load_boundaries(data_root: Path, grower_slug: str, farm_slug: str) -> gpd.GeoDataFrame | None:
    path = data_root / "growers" / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    # Ensure field_id column exists
    if "field_id" not in gdf.columns:
        # Try to infer from other common column names
        for col in ("name", "id", "fid", "osm_id"):
            if col in gdf.columns:
                gdf = gdf.rename(columns={col: "field_id"})
                break
        else:
            gdf["field_id"] = [f"field_{i}" for i in range(len(gdf))]
    # Compute area in acres if not present
    if "area_acres" not in gdf.columns:
        gdf = gdf.to_crs(epsg=5070)  # Albers Equal Area for CONUS
        gdf["area_acres"] = gdf.geometry.area / 4046.86
        gdf = gdf.to_crs(epsg=4326)  # Back to WGS84 for mapping
    return gdf


def load_soil(data_root: Path, grower_slug: str, farm_slug: str) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    if not tables_dir.exists():
        return None
    # Find the fields_soil CSV
    matches = list(tables_dir.glob("*_fields_soil.csv"))
    if not matches:
        return None
    df = pd.read_csv(matches[0])
    # Ensure field_id exists
    if "field_id" not in df.columns:
        for col in ("name", "id", "fid", "osm_id"):
            if col in df.columns:
                df = df.rename(columns={col: "field_id"})
                break
    return df


def load_weather(data_root: Path, grower_slug: str, farm_slug: str) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    if not tables_dir.exists():
        return None
    matches = list(tables_dir.glob("*_weather_*.csv"))
    if not matches:
        return None
    df = pd.read_csv(matches[0], parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["doy"] = df["date"].dt.dayofyear
    return df


def load_cdl(data_root: Path, grower_slug: str, farm_slug: str, year: int) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    if not tables_dir.exists():
        return None
    matches = list(tables_dir.glob(f"*_{year}_cdl.csv"))
    if not matches:
        return None
    df = pd.read_csv(matches[0])
    return df


def load_rotation(data_root: Path, grower_slug: str, farm_slug: str) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    if not tables_dir.exists():
        return None
    matches = list(tables_dir.glob("*_crop_rotation.csv"))
    if not matches:
        return None
    return pd.read_csv(matches[0])


def load_ndvi_summaries(data_root: Path, grower_slug: str, farm_slug: str) -> dict[str, Any]:
    """Load per-field NDVI yearly summary JSON files."""
    fields_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "fields"
    summaries = {}
    if not fields_dir.exists():
        return summaries
    for field_dir in fields_dir.iterdir():
        if not field_dir.is_dir():
            continue
        summary_path = field_dir / "derived" / "summaries" / "ndvi_yearly_summary.json"
        if summary_path.exists():
            with open(summary_path) as f:
                summaries[field_dir.name] = json.load(f)
    return summaries


def load_field_json(data_root: Path, grower_slug: str, farm_slug: str) -> pd.DataFrame:
    """Load field.json metadata files to get lat/lon centroids."""
    fields_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "fields"
    records = []
    if not fields_dir.exists():
        return pd.DataFrame()
    for field_dir in fields_dir.iterdir():
        if not field_dir.is_dir():
            continue
        json_path = field_dir / "field.json"
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
            records.append({
                "field_id": data.get("field_id", field_dir.name),
                "field_slug": data.get("field_slug", field_dir.name),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            })
    return pd.DataFrame(records)


def build_integrated_dataset(
    data_root: Path,
    grower_slug: str,
    farm_slug: str,
    year_focus: int | None = None,
) -> dict[str, Any]:
    """Load and merge all data sources into an integrated dictionary.

    Returns a dict with keys:
      - 'boundaries': GeoDataFrame with field polygons
      - 'soil': DataFrame (horizon-level, can be aggregated)
      - 'weather': DataFrame (daily)
      - 'cdl_years': dict[int, DataFrame]
      - 'rotation': DataFrame | None
      - 'ndvi_summaries': dict[str, dict]
      - 'field_meta': DataFrame (lat/lon)
    """
    print(f"[Loader] Loading data for grower={grower_slug}, farm={farm_slug}")

    boundaries = load_boundaries(data_root, grower_slug, farm_slug)
    soil = load_soil(data_root, grower_slug, farm_slug)
    weather = load_weather(data_root, grower_slug, farm_slug)
    rotation = load_rotation(data_root, grower_slug, farm_slug)
    ndvi_summaries = load_ndvi_summaries(data_root, grower_slug, farm_slug)
    field_meta = load_field_json(data_root, grower_slug, farm_slug)

    # Load all available CDL years
    cdl_years = {}
    if weather is not None:
        available_years = sorted(weather["year"].unique())
    else:
        available_years = list(range(2021, 2026))
    for yr in available_years:
        cdl = load_cdl(data_root, grower_slug, farm_slug, yr)
        if cdl is not None:
            cdl_years[yr] = cdl

    # Determine year focus
    if year_focus is None:
        year_focus = max(cdl_years.keys()) if cdl_years else (max(available_years) if available_years else 2024)

    print(f"[Loader] Boundaries: {len(boundaries) if boundaries is not None else 0} fields")
    print(f"[Loader] Soil records: {len(soil) if soil is not None else 0}")
    print(f"[Loader] Weather days: {len(weather) if weather is not None else 0}")
    print(f"[Loader] CDL years: {list(cdl_years.keys())}")
    print(f"[Loader] NDVI summaries: {len(ndvi_summaries)} fields")
    print(f"[Loader] Year focus: {year_focus}")

    return {
        "boundaries": boundaries,
        "soil": soil,
        "weather": weather,
        "cdl_years": cdl_years,
        "rotation": rotation,
        "ndvi_summaries": ndvi_summaries,
        "field_meta": field_meta,
        "year_focus": year_focus,
        "grower_slug": grower_slug,
        "farm_slug": farm_slug,
    }
