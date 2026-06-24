#!/usr/bin/env python3
# ruff: noqa: E402
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportReturnType=false, reportGeneralTypeIssues=false
"""Bootstrap or expand a farm from county-scoped OSM field polygons.

This utility creates a deterministic boundary GeoJSON + inventory CSV for a
target county, then optionally runs the canonical farm pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from bootstrap_runtime import ensure_runtime_environment

ensure_runtime_environment()

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Polygon

from naming import field_slug_from_id
from paths import DATA_ROOT, SCRIPTS_ROOT, farm_boundary_path, farm_manifest_dir, shared_geoadmin_counties_dir

OVERPASS_URLS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
COUNTIES_PATH = shared_geoadmin_counties_dir() / "counties_usa.geojson"


def _runtime_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else DATA_ROOT / candidate


def _runtime_relative(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def _slugify(value: str) -> str:
    return (
        value.strip().lower().replace("_", "-").replace(" ", "-").replace("/", "-").replace(".", "")
    )


def _normalize_county_name(name: str) -> str:
    cleaned = name.strip().lower().replace(" county", "")
    return " ".join(cleaned.split())


def _ensure_counties_layer() -> None:
    if COUNTIES_PATH.exists():
        return
    cmd = [
        sys.executable,
        str(SCRIPTS_ROOT / "ingest" / "download_geoadmin.py"),
        "--levels",
        "l2_counties",
    ]
    subprocess.run(cmd, cwd=str(DATA_ROOT), check=True)


def _load_target_county(state_fips: str, county_name: str) -> gpd.GeoDataFrame:
    _ensure_counties_layer()
    counties = gpd.read_file(COUNTIES_PATH)
    target_state = state_fips.zfill(2)
    target_county = _normalize_county_name(county_name)

    candidates = counties[counties["state_fips"].astype(str).str.zfill(2) == target_state].copy()
    if candidates.empty:
        raise ValueError(f"No counties found for state_fips={target_state}")

    names = candidates["county_name"].astype(str).map(_normalize_county_name)
    exact = candidates[names == target_county].copy()
    if exact.empty:
        available = ", ".join(sorted(candidates["county_name"].astype(str).unique())[:15])
        raise ValueError(
            f"County '{county_name}' not found in state_fips={target_state}. "
            f"Sample available counties: {available}"
        )
    return exact.iloc[[0]].copy()


def _query_overpass_bbox(bbox: tuple[float, float, float, float]) -> dict:
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:180];
    (
      way["landuse"~"farmland|orchard|vineyard|meadow"]({south},{west},{north},{east});
    );
    out geom;
    """
    last_error: Exception | None = None
    for endpoint in OVERPASS_URLS:
        for attempt in range(1, 4):
            try:
                headers = {"Accept": "application/json", "User-Agent": "curl/7.68.0"}
                response = requests.post(endpoint, data={"data": query}, headers=headers, timeout=240)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(2.0 * attempt)
    raise RuntimeError(f"Overpass query failed for all endpoints: {last_error}")


def _osm_elements_to_fields(
    *,
    elements: list[dict],
    county_geom,
    state_fips: str,
    county_fips: str,
    county_name: str,
) -> gpd.GeoDataFrame:
    records: list[dict] = []
    county_gdf = gpd.GeoDataFrame([{"geometry": county_geom}], crs="EPSG:4326")

    for element in elements:
        if element.get("type") != "way":
            continue
        geometry_points = element.get("geometry", [])
        if len(geometry_points) < 4:
            continue
        ring = [(point["lon"], point["lat"]) for point in geometry_points]
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        try:
            polygon = Polygon(ring)
            if not polygon.is_valid or polygon.is_empty or polygon.area == 0:
                continue
        except Exception:
            continue

        field_gdf = gpd.GeoDataFrame([{"geometry": polygon}], crs="EPSG:4326")
        clipped = gpd.overlay(field_gdf, county_gdf, how="intersection")
        if clipped.empty:
            continue
        clipped_geom = clipped.geometry.iloc[0]
        if clipped_geom.is_empty:
            continue

        tags = element.get("tags", {})
        records.append(
            {
                "field_id": f"osm-{element.get('id')}",
                "source": "OpenStreetMap/Overpass",
                "crop_name": str(tags.get("crop") or tags.get("landuse", "Unknown")),
                "state_fips": state_fips.zfill(2),
                "county_fips": county_fips.zfill(3),
                "county_name": county_name,
                "geometry": clipped_geom,
            }
        )

    if not records:
        return gpd.GeoDataFrame(
            columns=["field_id", "geometry"], geometry="geometry", crs="EPSG:4326"
        )

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.drop_duplicates(subset=["field_id"]).reset_index(drop=True)
    gdf["area_acres"] = gdf.to_crs("EPSG:5070").geometry.area / 4046.8564224
    gdf = gdf[gdf["area_acres"] > 0.5].copy()
    return gdf


def _sample_fields(gdf: gpd.GeoDataFrame, *, count: int, seed: int) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    ranked = gdf.sort_values(["area_acres", "field_id"], ascending=[False, True]).reset_index(
        drop=True
    )
    if len(ranked) <= count:
        return ranked
    sampled = ranked.sample(n=count, random_state=seed).copy()
    return sampled.sort_values("field_id").reset_index(drop=True)


def _write_inventory(path: Path, fields: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field_id", "field_slug"])
        for field_id in fields["field_id"].astype(str).tolist():
            writer.writerow([field_id, field_slug_from_id(field_id)])


def _merge_with_existing(
    *,
    grower_slug: str,
    farm_slug: str,
    inventory_path: Path,
    new_fields: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    farm_boundary = farm_boundary_path(grower_slug, farm_slug)
    merged = new_fields.copy()
    if farm_boundary.exists():
        existing = gpd.read_file(farm_boundary)
        merged = pd.concat([existing, new_fields], ignore_index=True)
        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=new_fields.crs)
        merged = merged.drop_duplicates(subset=["field_id"], keep="last")
    merged = merged.sort_values("field_id").reset_index(drop=True)

    if inventory_path.exists():
        prior = pd.read_csv(inventory_path)
        if {"field_id", "field_slug"}.issubset(prior.columns):
            merged_ids = set(merged["field_id"].astype(str))
            prior = prior[prior["field_id"].astype(str).isin(merged_ids)].copy()
            prior_ids = set(prior["field_id"].astype(str))
            for field_id in merged["field_id"].astype(str):
                if field_id not in prior_ids:
                    prior = pd.concat(
                        [
                            prior,
                            pd.DataFrame(
                                [
                                    {
                                        "field_id": field_id,
                                        "field_slug": field_slug_from_id(field_id),
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
            prior = prior.drop_duplicates(subset=["field_id"], keep="last")
            prior = prior.sort_values("field_id").reset_index(drop=True)
            prior.to_csv(inventory_path, index=False)
            return merged

    _write_inventory(inventory_path, merged)

    return merged


def _run_farm_pipeline(args, boundary_path: Path, inventory_path: Path) -> None:
    cmd = [
        sys.executable,
        str(SCRIPTS_ROOT / "run_farm_pipeline.py"),
        "--boundaries",
        str(boundary_path),
        "--grower-slug",
        args.grower_slug,
        "--farm-slug",
        args.farm_slug,
        "--farm-name",
        args.farm_name,
        "--inventory-csv",
        str(inventory_path),
    ]
    if args.force:
        cmd.append("--force")
    subprocess.run(cmd, cwd=str(DATA_ROOT), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or append county-scoped field boundaries for a grower farm"
    )
    parser.add_argument(
        "--state-fips", required=True, help="Two-digit state FIPS, e.g. 29 for Missouri"
    )
    parser.add_argument("--county-name", required=True, help="County name, e.g. Boone")
    parser.add_argument("--count", type=int, default=4, help="Number of fields to sample")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed")
    parser.add_argument("--grower-slug", required=True)
    parser.add_argument("--farm-slug", required=True)
    parser.add_argument("--farm-name", required=True)
    parser.add_argument(
        "--append", action="store_true", help="Append sampled fields to existing farm"
    )
    parser.add_argument(
        "--inventory-csv",
        default=None,
        help=(
            "Inventory output path. Defaults to "
            "growers/<grower>/farms/<farm>/manifests/field-inventory.csv under the runtime root"
        ),
    )
    parser.add_argument(
        "--boundary-out",
        default=None,
        help="Boundary output path. Defaults to canonical farm boundary path.",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run full farm pipeline after bootstrap",
    )
    parser.add_argument("--force", action="store_true", help="Pass --force to run_farm_pipeline")
    args = parser.parse_args()

    county = _load_target_county(args.state_fips, args.county_name)
    county_geom = county.geometry.iloc[0]
    county_name = str(county["county_name"].iloc[0])
    county_fips = str(county["county_fips"].iloc[0]).zfill(3)
    bounds = county.total_bounds
    bbox = (float(bounds[1]), float(bounds[0]), float(bounds[3]), float(bounds[2]))

    payload = _query_overpass_bbox(bbox)
    fields = _osm_elements_to_fields(
        elements=payload.get("elements", []),
        county_geom=county_geom,
        state_fips=args.state_fips,
        county_fips=county_fips,
        county_name=county_name,
    )
    sampled = _sample_fields(fields, count=args.count, seed=args.seed)
    if sampled.empty:
        raise RuntimeError("No eligible farmland polygons found for requested county")

    default_inventory = (
        farm_manifest_dir(args.grower_slug, args.farm_slug) / "field-inventory.csv"
    )
    inventory_path = Path(args.inventory_csv) if args.inventory_csv else default_inventory
    inventory_path = inventory_path if inventory_path.is_absolute() else _runtime_path(inventory_path)

    boundary_out = (
        Path(args.boundary_out)
        if args.boundary_out
        else farm_boundary_path(args.grower_slug, args.farm_slug)
    )
    boundary_out = boundary_out if boundary_out.is_absolute() else _runtime_path(boundary_out)
    boundary_out.parent.mkdir(parents=True, exist_ok=True)

    final_fields = sampled
    if args.append:
        final_fields = _merge_with_existing(
            grower_slug=args.grower_slug,
            farm_slug=args.farm_slug,
            inventory_path=inventory_path,
            new_fields=sampled,
        )
    else:
        _write_inventory(inventory_path, sampled)

    final_fields.to_file(boundary_out, driver="GeoJSON")

    summary = {
        "grower_slug": args.grower_slug,
        "farm_slug": args.farm_slug,
        "farm_name": args.farm_name,
        "state_fips": args.state_fips.zfill(2),
        "county_name": county_name,
        "county_fips": county_fips,
        "sample_count": len(sampled),
        "final_field_count": len(final_fields),
        "seed": args.seed,
        "boundary_path": _runtime_relative(boundary_out),
        "inventory_csv": _runtime_relative(inventory_path),
        "append": bool(args.append),
    }
    print(json.dumps(summary, indent=2))

    if args.run_pipeline:
        _run_farm_pipeline(args, boundary_out, inventory_path)


if __name__ == "__main__":
    main()
