#!/usr/bin/env python3
"""Main orchestrator for Assignment 2 field-level EDA comparison v2.

Compares field boundaries, CDL/cropland data, and weather across Illinois,
Iowa, and Nebraska growers. Produces 18 static PNG outputs + 2 summary files.

Usage:
    export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
    python src/field_comparison.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import pandas as pd

from comparisons.boundary_comparison import boundary_analysis
from comparisons.cdl_comparison import cdl_analysis
from comparisons.crop_composition import crop_composition_analysis
from comparisons.geospatial_map import geospatial_maps
from comparisons.statistics_summary import write_stats_summary
from comparisons.synthesis import synthesis_panel
from comparisons.timeseries import timeseries_analysis
from comparisons.weather_comparison import weather_analysis


def _get_data_root() -> Path:
    root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not root:
        print("ERROR: DATA_PIPELINE_DATA_ROOT is required.")
        print("  export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime")
        sys.exit(1)
    return Path(root) / "data-pipeline"


def _build_grower_info(data_root: Path) -> dict:
    growers = {
        "northern-illinois-grower": {
            "state": "Illinois",
            "state_fips": "17",
            "county_name": "DeKalb",
            "farm": "illinois-farm",
        },
        "northern-iowa-grower": {
            "state": "Iowa",
            "state_fips": "19",
            "county_name": "Floyd",
            "farm": "iowa-farm",
        },
        "nebraska-grower": {
            "state": "Nebraska",
            "state_fips": "31",
            "county_name": "Hamilton",
            "farm": "nebraska-farm",
        },
    }

    for grower_slug, info in growers.items():
        farm = info["farm"]
        base = data_root / "growers" / grower_slug / "farms" / farm
        info["data_root"] = str(data_root)
        info["boundary"] = str(base / "boundary" / "field_boundaries.geojson")
        prefix = farm.replace("-farm", "")
        info["cdl_updated"] = str(base / "derived" / "tables" / f"{prefix}_cdl_2021_2025_full_composition_updated.csv")
        info["rotation"] = str(base / "derived" / "tables" / f"{prefix}_crop_rotation.csv")
        info["weather"] = str(base / "derived" / "tables" / f"{prefix}_weather_2021_2025.csv")
        info["fields_dir"] = str(base / "fields")

    return growers


def _load_rotation_data(growers: dict) -> pd.DataFrame:
    frames = []
    for grower_slug, info in growers.items():
        rot_path = Path(info["rotation"])
        if rot_path.exists():
            df = pd.read_csv(rot_path)
            df["state"] = info["state"]
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def main() -> None:
    data_root = _get_data_root()
    growers = _build_grower_info(data_root)

    # Create timestamped output directory (year corrected to 2026)
    today = datetime.now().strftime("%Y-%m-%d").replace("2025", "2026")
    output_dir = data_root / "eda" / "field-comparison" / "output" / today
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Load rotation data once for reuse
    rotation_df = _load_rotation_data(growers)
    if rotation_df.empty:
        print("WARNING: No rotation data loaded.")

    # Collect all stats for summary
    all_stats = []

    # Run all analyses
    stats_a = boundary_analysis(growers, rotation_df, output_dir)
    if stats_a:
        all_stats.append(stats_a)
    
    stats_b = cdl_analysis(growers, output_dir)
    if stats_b:
        all_stats.append(stats_b)

    # Crop composition figures (14, 15)
    crop_composition_analysis(growers, output_dir)

    stats_c = weather_analysis(growers, output_dir)
    if stats_c:
        all_stats.extend([v for v in stats_c.values() if isinstance(v, dict)])
    
    geospatial_maps(growers, output_dir)
    timeseries_analysis(growers, output_dir)
    synthesis_panel(growers, output_dir)
    
    # Write statistics summary
    write_stats_summary(all_stats, output_dir)

    # Final summary
    print("\n" + "=" * 60)
    print("Assignment 2 EDA v2 Complete")
    print("=" * 60)
    png_files = sorted(output_dir.glob("*.png"))
    txt_files = sorted(output_dir.glob("*.txt"))
    md_files = sorted(output_dir.glob("*.md"))
    print(f"Generated {len(png_files)} PNG files:")
    for f in png_files:
        print(f"  {f.name}")
    for f in txt_files + md_files:
        print(f"  {f.name}")
    print(f"\nAll outputs saved to: {output_dir}")


if __name__ == "__main__":
    main()
