#!/usr/bin/env python3
import json
import os
import sys
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

    weather_daily = []
    if not data.weather.empty:
        w = data.weather[["date", "t2m", "t2m_max", "t2m_min", "prectotcorr"]].copy()
        w["date"] = w["date"].dt.strftime("%Y-%m-%d")
        weather_daily = w.to_dict(orient="records")

    ndvi_scenes = []
    if not data.ndvi_scenes.empty:
        for _, row in data.ndvi_scenes.iterrows():
            ndvi_scenes.append({
                "field_id": row["field_id"],
                "year": int(row["year"]),
                "date": row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
                "ndvi": row.get("ndvi"),
                "source": row.get("source", "sentinel"),
                "scene": row.get("scene", ""),
            })

    gdd_daily = []
    if not data.gdd_daily.empty:
        g = data.gdd_daily[["date", "doy", "gdd", "season_gdd"]].copy()
        g["date"] = g["date"].dt.strftime("%Y-%m-%d")
        gdd_daily = g.to_dict(orient="records")

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

    field_id = data.field_id or (data.field_ids[0] if data.field_ids else None)
    field_summary = data.get_single_field_summary(field_id) if field_id else {}

    package = {
        "version": "2.0",
        "grower_slug": data.grower_slug,
        "farm_slug": data.farm_slug,
        "farm_display_name": "Northern Iowa Farm",
        "state": "IA",
        "field_id": field_id,
        "kpis": {k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
                 for k, v in kpis.items()},
        "field_ids": data.field_ids,
        "field_boundaries": field_boundaries,
        "field_metrics": field_metrics,
        "weather_daily": weather_daily,
        "ndvi_scenes": ndvi_scenes,
        "gdd_daily": gdd_daily,
        "cdl_composition": cdl_data,
        "crop_rotation": rotation_data,
        "field_summary": field_summary,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(package, f, indent=2, default=str)

    print(f"Exported {output_path}")
    print(f"  Field: {field_id}")
    print(f"  Field metrics: {len(field_metrics)}")
    print(f"  NDVI scenes: {len(ndvi_scenes)}")
    print(f"  Weather days: {len(weather_daily)}")
    print(f"  GDD days: {len(gdd_daily)}")
    print(f"  CDL records: {len(cdl_data)}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    return package


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export dashboard data package")
    parser.add_argument("--grower", default="iowa-grower")
    parser.add_argument("--farm", default="iowa-farm")
    parser.add_argument("--field", default="osm-1219926116")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT")
        sys.exit(1)

    if args.output:
        output = Path(args.output)
    else:
        output = Path(__file__).resolve().parent.parent / "dashboard_data.json"

    print(f"Loading data for {args.grower}/{args.farm} field={args.field} ...")
    data = DashboardData(data_root, args.grower, args.farm, field_id=args.field)
    export_dashboard_data(data, output)


if __name__ == "__main__":
    main()
