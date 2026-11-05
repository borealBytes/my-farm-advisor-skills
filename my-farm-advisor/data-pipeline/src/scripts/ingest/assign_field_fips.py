#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Assign demo farm fields to county FIPS using canonical geoadmin assets."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

# TIGER/GADM county geojsons contain multi-megabyte multipolygons; GDAL's
# default 500 MB single-feature object guard rejects them on read.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

import geopandas as gpd
import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))


def _runtime_relative(path: Path, runtime_base: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(runtime_base))
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grower-slug", default="default-grower")
    parser.add_argument("--farm-slug", default="default-farm")
    parser.add_argument(
        "--inventory-path",
        type=Path,
        default=None,
        help="Optional inventory CSV used to map field IDs to canonical field slugs",
    )
    return parser.parse_args()


def main() -> int:
    from paths import (
        DATA_ROOT,
        farm_boundary_path,
        farm_manifest_dir,
        farm_summary_path,
        farm_table_path,
        shared_geoadmin_counties_dir,
    )
    from reporting_bootstrap import (
        ensure_canonical_data_tree,
        ensure_skill_path,
        field_slug_map_from_inventory,
    )

    ensure_skill_path("geoadmin-admin")
    args = parse_args()
    inventory_path = (
        args.inventory_path
        if args.inventory_path is not None
        else farm_manifest_dir(args.grower_slug, args.farm_slug) / "field-inventory.csv"
    )
    inventory_path = inventory_path if inventory_path.is_absolute() else DATA_ROOT / inventory_path
    ensure_canonical_data_tree(
        grower_slug=args.grower_slug,
        farm_slug=args.farm_slug,
        inventory_path=inventory_path if inventory_path.exists() else None,
    )
    geoadmin_admin = importlib.import_module("geoadmin_admin")
    fields = gpd.read_file(farm_boundary_path(args.grower_slug, args.farm_slug))
    counties = gpd.read_file(shared_geoadmin_counties_dir() / "counties_usa.geojson")
    counties_canada_path = shared_geoadmin_counties_dir() / "counties_canada.geojson"
    if counties_canada_path.exists():
        counties = gpd.GeoDataFrame(
            pd.concat([counties, gpd.read_file(counties_canada_path)], ignore_index=True),
            geometry="geometry",
            crs="EPSG:4326",
        )
    field_slug_map = field_slug_map_from_inventory(
        inventory_path if inventory_path.exists() else None
    )
    mapping_df, ambiguity_df = geoadmin_admin.assign_fields_to_counties(
        fields, counties, field_slug_map=field_slug_map
    )

    mapping_path = farm_table_path(
        args.grower_slug, args.farm_slug, "field_fips_mapping.parquet"
    )
    ambiguity_path = farm_table_path(
        args.grower_slug, args.farm_slug, "field_fips_ambiguity.csv"
    )
    summary_path = farm_summary_path(
        args.grower_slug, args.farm_slug, "field_fips_mapping_summary.json"
    )
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_df.to_parquet(mapping_path, index=False)
    ambiguity_df.to_csv(ambiguity_path, index=False)
    summary_path.write_text(
        json.dumps(
            {
                "grower_slug": args.grower_slug,
                "farm_slug": args.farm_slug,
                "field_count": int(len(mapping_df)),
                "ambiguity_count": int(len(ambiguity_df)),
                "mapping_path": _runtime_relative(mapping_path, DATA_ROOT),
                "ambiguity_path": _runtime_relative(ambiguity_path, DATA_ROOT),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "mapping_path": str(mapping_path),
                "ambiguity_path": str(ambiguity_path),
                "summary_path": str(summary_path),
                "field_count": int(len(mapping_df)),
                "ambiguity_count": int(len(ambiguity_df)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
