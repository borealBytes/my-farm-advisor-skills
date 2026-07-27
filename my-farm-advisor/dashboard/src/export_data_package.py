#!/usr/bin/env python3
"""
Export pre-computed dashboard data package.

Runs on the VM where the runtime data tree lives. Reads all source data,
computes metrics (including NDVI from TIFFs), and exports a single compact
JSON file that the dashboard can load without any runtime tree dependency.

Usage:
    export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
    python export_data_package.py --grower iowa-grower --farm iowa-farm
"""

import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_utils import DashboardData


def export_dashboard_data(data, output_path):
    kpis = data.get_kpis()
    metrics = data.compute_sustainability_index()

    field_boundaries = []
    if not data.field_geojson.empty:
        gdf = data.field_geojson.to_crs("EPSG:4326")
        for _, row in gdf.iterrows():
            coords = []
            if row.geometry.geom_type == "Polygon":
                coords = [list(row.geometry.exterior.coords)]
            elif row.geometry.geom_type == "MultiPolygon":
                coords = [list(p.exterior.coords) for p in row.geometry.geoms]
            centroid = [row.geometry.centroid.y, row.geometry.centroid.x]
            field_boundaries.append({
                "field_id": row.get("field_id", ""),
                "coordinates": coords,
                "area_acres": round(float(row.get("area_acres", 0)), 1),
                "centroid": centroid,
            })

    field_metrics = []
    if not metrics.empty:
        for _, row in metrics.iterrows():
            fm = {k: (v if not (isinstance(v, float) and np.isnan(v)) else None)
                  for k, v in row.items()}
            fm = {k: (round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, str) else v)
                  for k, v in fm.items()}
            field_metrics.append(fm)

    weather_monthly = []
    if not data.weather.empty:
        w = data.weather.copy()
        w["month"] = w["date"].dt.month
        w["year"] = w["date"].dt.year
        monthly = w.groupby(["year", "month"]).agg(
            precip=("prectotcorr", "sum"),
            temp=("t2m", "mean"),
            tmin=("t2m_min", "mean"),
            tmax=("t2m_max", "mean"),
        ).reset_index()
        weather_monthly = monthly.to_dict(orient="records")

    ndvi_annual = []
    if not data.ndvi.empty:
        for _, row in data.ndvi.iterrows():
            val = data._compute_ndvi_from_tiff(row.get("composite_tif", ""))
            ndvi_annual.append({
                "field_id": row["field_id"],
                "year": int(row["year"]),
                "crop_name": row.get("crop_name", ""),
                "ndvi": val,
                "scene_count": int(row.get("scene_count", 0)),
            })

    cdl_data = []
    if not data.cdl_composition.empty:
        for _, row in data.cdl_composition.iterrows():
            cdl_data.append({
                "field_id": row["field_id"],
                "year": int(row["year"]),
                "crop_name": row.get("crop_name", ""),
                "pct": round(float(row.get("pct", 0)), 1),
            })

    rotation_data = []
    if not data.crop_rotation.empty:
        for _, row in data.crop_rotation.iterrows():
            rotation_data.append({
                "field_id": row.get("field_id", ""),
                "diversity": int(row.get("crop_diversity", 0)),
                "sequence": row.get("rotation_sequence", ""),
                "predicted_next": row.get("predicted_next_crop", ""),
                "confidence": row.get("rotation_confidence", ""),
            })

    package = {
        "version": "1.0",
        "grower_slug": data.grower_slug,
        "farm_slug": data.farm_slug,
        "farm_display_name": "Northern Iowa Farm",
        "state": "IA",
        "kpis": {k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
                 for k, v in kpis.items()},
        "field_ids": data.field_ids,
        "field_boundaries": field_boundaries,
        "field_metrics": field_metrics,
        "weather_monthly": weather_monthly,
        "ndvi_annual": ndvi_annual,
        "cdl_composition": cdl_data,
        "crop_rotation": rotation_data,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(package, f, indent=2, default=str)

    print(f"Exported {output_path}")
    print(f"  Fields: {len(field_boundaries)}")
    print(f"  Field metrics: {len(field_metrics)}")
    print(f"  NDVI records: {len(ndvi_annual)}")
    print(f"  Weather months: {len(weather_monthly)}")
    print(f"  CDL records: {len(cdl_data)}")
    print(f"  Rotations: {len(rotation_data)}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    return package


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export dashboard data package")
    parser.add_argument("--grower", default="iowa-grower")
    parser.add_argument("--farm", default="iowa-farm")
    parser.add_argument("--output", default=None,
                        help="Output path for dashboard_data.json (default: ../dashboard_data.json)")
    args = parser.parse_args()

    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT")
        sys.exit(1)

    if args.output:
        output = Path(args.output)
    else:
        output = Path(__file__).resolve().parent.parent / "dashboard_data.json"

    print(f"Loading data for {args.grower}/{args.farm}...")
    data = DashboardData(data_root, args.grower, args.farm)
    export_dashboard_data(data, output)


if __name__ == "__main__":
    main()
