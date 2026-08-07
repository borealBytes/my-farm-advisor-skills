#!/usr/bin/env python3
"""
ndvi_extractor.py — Extract NDVI statistics from composite TIFFs using rasterstats.

Computes per-field, per-year:
  - mean NDVI
  - std NDVI (variability indicator)
  - min / max NDVI

Also computes cross-year NDVI stability score for the Sustainability Index.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

try:
    import rasterstats
    import rasterio
    HAS_RASTER = True
except ImportError:
    HAS_RASTER = False


def extract_ndvi_from_tiff(tiff_path: Path, boundary_geojson_path: Path) -> dict[str, float] | None:
    """Run zonal stats on a single NDVI composite TIFF against a field boundary.

    Returns dict with mean, std, min, max, count.
    """
    if not HAS_RASTER:
        raise RuntimeError("rasterio and rasterstats are required for TIFF-based NDVI extraction.")
    if not tiff_path.exists():
        return None
    if not boundary_geojson_path.exists():
        return None

    try:
        stats = rasterstats.zonal_stats(
            str(boundary_geojson_path),
            str(tiff_path),
            stats=["mean", "std", "min", "max", "count"],
            geojson_out=False,
            nodata=-9999,
        )
        if not stats:
            return None
        s = stats[0]
        return {
            "mean_ndvi": s.get("mean"),
            "std_ndvi": s.get("std"),
            "min_ndvi": s.get("min"),
            "max_ndvi": s.get("max"),
            "pixel_count": s.get("count"),
        }
    except Exception as e:
        print(f"[NDVI] Warning: failed to extract NDVI from {tiff_path}: {e}")
        return None


def extract_all_field_ndvi(
    data_root: Path,
    grower_slug: str,
    farm_slug: str,
    years: list[int] | None = None,
) -> pd.DataFrame:
    """Extract NDVI stats for all fields and all years from composite TIFFs.

    Returns DataFrame with columns:
      field_id, year, mean_ndvi, std_ndvi, min_ndvi, max_ndvi, pixel_count
    """
    fields_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "fields"
    if not fields_dir.exists():
        return pd.DataFrame()

    records = []
    for field_dir in sorted(fields_dir.iterdir()):
        if not field_dir.is_dir():
            continue
        field_id = field_dir.name
        boundary_path = field_dir / "boundary" / "field_boundary.geojson"

        # Discover available composite TIFFs
        features_dir = field_dir / "derived" / "features"
        if not features_dir.exists():
            continue

        tiff_files = sorted(features_dir.glob("ndvi_year_*_composite.tif"))
        for tiff in tiff_files:
            # Parse year from filename: ndvi_year_2023_composite.tif
            try:
                year_str = tiff.stem.split("_")[2]
                year = int(year_str)
            except (IndexError, ValueError):
                continue
            if years is not None and year not in years:
                continue

            stats = extract_ndvi_from_tiff(tiff, boundary_path)
            if stats is None:
                continue
            records.append({
                "field_id": field_id,
                "year": year,
                **stats,
            })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    # Round for readability
    for col in ["mean_ndvi", "std_ndvi", "min_ndvi", "max_ndvi"]:
        if col in df.columns:
            df[col] = df[col].round(4)
    return df


def compute_ndvi_stability(ndvi_df: pd.DataFrame) -> pd.DataFrame:
    """Compute NDVI stability score per field from multi-year NDVI records.

    Stability is based on the coefficient of variation (CV) of mean NDVI across years.
    Lower CV = higher stability = higher score.
    Score range: 0–20.
    """
    if ndvi_df is None or ndvi_df.empty:
        return pd.DataFrame()

    grouped = ndvi_df.groupby("field_id").agg(
        mean_ndvi_avg=("mean_ndvi", "mean"),
        mean_ndvi_std=("mean_ndvi", "std"),
        years_count=("mean_ndvi", "count"),
    ).reset_index()

    # Coefficient of variation (%)
    grouped["cv"] = (grouped["mean_ndvi_std"] / grouped["mean_ndvi_avg"] * 100.0).replace([np.inf, -np.inf], np.nan)
    max_cv = grouped["cv"].max() if not grouped["cv"].isna().all() else 50.0

    # Score: lower CV = higher score
    grouped["ndvi_stability_score"] = (
        (1 - grouped["cv"] / max(max_cv, 1.0)).clip(lower=0) * 20.0
    ).round(2)

    # Fill NaN with neutral 10.0
    grouped["ndvi_stability_score"] = grouped["ndvi_stability_score"].fillna(10.0)

    return grouped[["field_id", "ndvi_stability_score", "mean_ndvi_avg", "mean_ndvi_std", "years_count"]]
