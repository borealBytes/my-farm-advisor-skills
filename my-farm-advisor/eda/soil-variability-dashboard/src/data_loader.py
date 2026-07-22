"""Load and aggregate grower-level data across all farms for dashboard generation."""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


def _resolve(pattern: Path) -> Path:
    matches = list(Path(pattern.parent).glob(pattern.name))
    if not matches:
        raise FileNotFoundError(f"No file matching: {pattern}")
    return matches[0]


def _resolve_optional(pattern: Path) -> Path | None:
    matches = list(Path(pattern.parent).glob(pattern.name))
    return matches[0] if matches else None


def _load_farm_ssurgo(farm_dir: Path, farm_slug: str) -> pd.DataFrame:
    """Load SSURGO summary for a single farm, tagged with farm_slug."""
    tables_dir = farm_dir / "derived" / "tables"
    ssurgo = pd.read_csv(_resolve(tables_dir / "*_ssurgo_summary.csv"))
    ssurgo["farm_slug"] = farm_slug
    return ssurgo


def _load_farm_boundaries(farm_dir: Path) -> gpd.GeoDataFrame:
    """Load field boundaries for a single farm."""
    return gpd.read_file(farm_dir / "boundary" / "field_boundaries.geojson")


def _load_farm_weather(farm_dir: Path) -> pd.DataFrame:
    """Load weather data for a single farm (date, PRECTOTCORR, T2M, etc.)."""
    tables_dir = farm_dir / "derived" / "tables"
    weather = pd.read_csv(_resolve(tables_dir / "*_weather_*.csv"))
    weather["date"] = pd.to_datetime(weather["date"])
    return weather


def _load_farm_ndvi(farm_dir: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Load field-level NDVI joins and card summaries for all fields in a farm.

    Returns:
        (ndvi_year_join DataFrame, ndvi_card_data list of dicts)
    """
    fields_dir = farm_dir / "fields"
    ndvi_joins = []
    for fdir in sorted(fields_dir.iterdir()):
        jpath = fdir / "derived" / "tables" / "ndvi_year_crop_join.csv"
        if jpath.exists():
            ndvi_joins.append(pd.read_csv(jpath))

    ndvi_year_join = (
        pd.concat(ndvi_joins, ignore_index=True) if ndvi_joins else pd.DataFrame()
    )

    ndvi_card_data = []
    for fdir in sorted(fields_dir.iterdir()):
        jpath = fdir / "derived" / "summaries" / "ndvi_card_summary.json"
        if jpath.exists():
            with open(jpath) as f:
                ndvi_card_data.append(json.load(f))

    return ndvi_year_join, ndvi_card_data


def load_grower_data(grower_dir: str | Path) -> dict:
    """Load and aggregate all field, soil, weather, and NDVI data for a grower.

    Iterates every farm under ``grower_dir/farms/`` and concatenates
    per-farm tables so the dashboard can reason across the entire grower.

    Returns:
        dict with keys: ssurgo_summary, weather, boundaries, ndvi_year_join,
        ndvi_card_data, field_inventory (from first farm), farm_dir, tables_dir
    """
    root = Path(grower_dir)
    farm_dirs = sorted(root.glob("farms/*"))

    if not farm_dirs:
        raise FileNotFoundError(f"No farms found under {root / 'farms'}")

    # SSURGO — concatenated across farms
    ssurgo_parts = []
    for fd in farm_dirs:
        slug = fd.name
        try:
            ssurgo_parts.append(_load_farm_ssurgo(fd, slug))
        except (FileNotFoundError, ValueError):
            continue
    ssurgo_summary = pd.concat(ssurgo_parts, ignore_index=True) if ssurgo_parts else pd.DataFrame()

    # Weather — use the first farm that has it (grower-level weather assumed shared)
    weather = pd.DataFrame()
    for fd in farm_dirs:
        try:
            weather = _load_farm_weather(fd)
            break
        except (FileNotFoundError, ValueError):
            continue

    # Boundaries — concatenated across all farms
    boundary_parts = []
    for fd in farm_dirs:
        try:
            boundary_parts.append(_load_farm_boundaries(fd))
        except (FileNotFoundError, ValueError):
            continue
    boundaries = pd.concat(boundary_parts, ignore_index=True) if boundary_parts else gpd.GeoDataFrame()

    # NDVI — aggregated across all fields in all farms
    ndvi_joins = []
    ndvi_cards = []
    for fd in farm_dirs:
        nj, nc = _load_farm_ndvi(fd)
        if not nj.empty:
            ndvi_joins.append(nj)
        ndvi_cards.extend(nc)
    ndvi_year_join = pd.concat(ndvi_joins, ignore_index=True) if ndvi_joins else pd.DataFrame()

    # Field inventory — use from the first farm
    field_inventory = pd.DataFrame()
    for fd in farm_dirs:
        inv_path = fd / "manifests" / "field-inventory.csv"
        if inv_path.exists():
            field_inventory = pd.read_csv(inv_path)
            break

    return {
        "ssurgo_summary": ssurgo_summary,
        "weather": weather,
        "boundaries": boundaries,
        "ndvi_year_join": ndvi_year_join,
        "ndvi_card_data": ndvi_cards,
        "field_inventory": field_inventory,
        "farm_dir": farm_dirs[0],
    }
