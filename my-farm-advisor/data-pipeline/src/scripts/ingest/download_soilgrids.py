#!/usr/bin/env python3
# ruff: noqa: E402,I001
"""Clip SoilGrids 250 m band VRTs into per-field rasters and a stats table.

Global soil-parity provider: every farm, everywhere, gets gridded soil
properties even when SSURGO (US) or the Ontario Detailed Soil Survey do not
cover the fields. Reads the farm boundary GeoJSON like ingest/download_soil.py
does, clips each field's buffered bbox (reprojecting away the source
Interrupted Goode Homolosine CRS), and writes:

- shared/soilgrids/<field_slug>/soilgrids_<band>_<depth>.tif  (raw Int16)
- shared/soilgrids/tables/soilgrids_field_stats.parquet       (zonal stats)
- shared/soilgrids/manifests/sha256_journal.json              (per-raster)
- growers/<grower>/farms/<farm>/manifests/soilgrids_provenance.json

Clips are idempotent: existing rasters are skipped (and their stats replayed
from disk) unless --force / AG_FORCE=1.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from lib.naming import field_slug_from_id  # pyright: ignore[reportMissingImports]
from paths import (  # pyright: ignore[reportMissingImports]
    DATA_ROOT,
    farm_boundary_path,
    farm_soilgrids_provenance_path,
    shared_soilgrids_field_dir,
    shared_soilgrids_journal_path,
    shared_soilgrids_stats_table_path,
    validate_path_slug,
)
from reporting_bootstrap import (  # pyright: ignore[reportMissingImports]
    ensure_canonical_data_tree,
    ensure_skill_path,
    field_slug_map_from_inventory,
)

ensure_skill_path("soilgrids-global")

import soilgrids_global as sg  # pyright: ignore[reportMissingImports]

STATS_COLUMNS = [
    "field_id",
    "field_slug",
    "band",
    "depth",
    "unit",
    "scale",
    "mean",
    "min",
    "max",
    "stdev",
    "n_pixels",
    "source_url",
    "accessed_at",
    "gdal_version",
    "note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grower", default=os.environ.get("AG_GROWER_SLUG", "default-grower"))
    parser.add_argument("--farm", default=os.environ.get("AG_FARM_SLUG", "default-farm"))
    parser.add_argument(
        "--inventory-csv",
        default=os.environ.get("AG_INVENTORY_CSV"),
        help="field_id,field_slug inventory CSV; defaults to the farm manifest copy",
    )
    parser.add_argument(
        "--boundaries",
        default=os.environ.get("AG_BOUNDARIES"),
        help="Farm boundary GeoJSON override; defaults to the canonical farm boundary",
    )
    parser.add_argument(
        "--bands",
        default=",".join(sg.DEFAULT_BANDS),
        help="Comma-separated SoilGrids bands (see soilgrids_global.BAND_SPECS)",
    )
    parser.add_argument(
        "--depths",
        default=",".join(sg.DEFAULT_DEPTH_INTERVALS),
        help="Comma-separated depth intervals, e.g. 0-5cm,5-15cm,15-30cm",
    )
    parser.add_argument(
        "--buffer-meters",
        type=float,
        default=float(os.environ.get("AG_SOILGRIDS_BUFFER_M") or sg.DEFAULT_BUFFER_METERS),
        help="Buffer around each field bbox before clipping (default 50 m)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=os.environ.get("AG_FORCE") == "1",
        help="Re-clip even when the output raster already exists",
    )
    return parser.parse_args()


def _journal() -> dict[str, dict[str, object]]:
    path = shared_soilgrids_journal_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _journal_record(journal: dict[str, dict[str, object]], raster_path: Path, record: dict) -> None:
    digest = sg.sha256_file(raster_path)
    key = str(raster_path.relative_to(DATA_ROOT))
    entry: dict[str, object] = {
        "sha256": digest,
        "bytes": raster_path.stat().st_size,
        "source_url": record["source_url"],
        "band": record["band"],
        "depth": record["depth"],
        "raster_path": str(raster_path),
        "accessed_at": record["accessed_at"],
        "gdal_version": record["gdal_version"],
    }
    prior = journal.get(key)
    if prior and prior.get("sha256") != digest:
        entry["replaced_previous_sha256"] = prior.get("sha256")
    journal[key] = entry


def _row_from_record(field_id: str, field_slug: str, record: dict, note_prefix: str = "") -> dict:
    spec = sg.band_spec(record["band"])
    notes = [note_prefix.strip(), str(spec.get("note") or "").strip(),
             f"nodata_ratio={record.get('nodata_ratio', '')}"]
    if record.get("n_pixels", 0) == 0:
        notes.append("all_nodata_in_field_polygon")
    return {
        "field_id": field_id,
        "field_slug": field_slug,
        "band": record["band"],
        "depth": record["depth"],
        "unit": record["unit"],
        "scale": record["scale"],
        "mean": record["mean"],
        "min": record["min"],
        "max": record["max"],
        "stdev": record["stdev"],
        "n_pixels": int(record["n_pixels"]),
        "source_url": record["source_url"],
        "accessed_at": record["accessed_at"],
        "gdal_version": record["gdal_version"],
        "note": "; ".join(n for n in notes if n),
    }


def _merge_stats_table(rows: list[dict]) -> pd.DataFrame:
    new = pd.DataFrame(rows, columns=STATS_COLUMNS)
    table_path = shared_soilgrids_stats_table_path()
    if table_path.exists():
        existing = pd.read_parquet(table_path)
        keys = {(r["field_id"], r["field_slug"], r["band"], r["depth"]) for r in rows}
        mask = existing.apply(
            lambda r: (str(r["field_id"]), str(r["field_slug"]), str(r["band"]), str(r["depth"])) in keys,
            axis=1,
        )
        new = pd.concat([existing[~mask], new], ignore_index=True)[STATS_COLUMNS]
    table_path.parent.mkdir(parents=True, exist_ok=True)
    new = new.sort_values(["field_slug", "band", "depth"]).reset_index(drop=True)
    new.to_parquet(table_path, index=False)
    return new


def main():
    args = parse_args()
    grower_slug = validate_path_slug(args.grower, "grower_slug")
    farm_slug = validate_path_slug(args.farm, "farm_slug")
    bands = [b.strip() for b in args.bands.split(",") if b.strip()]
    depths = [d.strip() for d in args.depths.split(",") if d.strip()]
    for band in bands:
        sg.band_spec(band)
    for depth in depths:
        if depth not in sg.DEPTH_INTERVALS:
            raise SystemExit(f"unknown SoilGrids depth interval: {depth}")

    default_inventory = farm_soilgrids_provenance_path(grower_slug, farm_slug).parent / "field-inventory.csv"
    inventory_path = Path(args.inventory_csv) if args.inventory_csv else default_inventory
    ensure_canonical_data_tree(grower_slug=grower_slug, farm_slug=farm_slug, inventory_path=inventory_path)
    field_slug_map = field_slug_map_from_inventory(inventory_path if inventory_path.exists() else None)

    boundaries_path = Path(args.boundaries) if args.boundaries else farm_boundary_path(grower_slug, farm_slug)
    fields = gpd.read_file(boundaries_path).to_crs("EPSG:4326")
    print(f"Loaded {len(fields)} fields from {boundaries_path}")

    journal = _journal()
    rows: list[dict] = []
    written = 0
    skipped = 0
    for _, field in fields.iterrows():
        field_id = str(field["field_id"])
        field_slug = field_slug_map.get(field_id) or field_slug_from_id(field_id)
        validate_path_slug(field_slug, "field_slug")
        geometry = field.geometry
        bbox = sg.field_bbox(geometry, buffer_meters=args.buffer_meters)
        for band in bands:
            for depth in depths:
                raster_path = shared_soilgrids_field_dir(field_slug) / f"soilgrids_{band}_{depth}.tif"
                if raster_path.exists() and not args.force:
                    replay = sg.stats_from_raster(raster_path, band, polygon=geometry)
                    replay.update(
                        depth=depth,
                        source_url=sg.vrt_url(band, depth),
                        accessed_at=sg.utc_now(),
                        gdal_version=sg.gdal_version(),
                    )
                    rows.append(_row_from_record(field_id, field_slug, replay, note_prefix="cached_replay"))
                    skipped += 1
                    print(f"skip  {field_slug} {band} {depth} (exists: {raster_path})")
                    continue
                record = sg.clip_bbox(
                    band,
                    depth,
                    bbox,
                    raster_path,
                    polygon=geometry,
                    buffer_note=f"bbox buffered {args.buffer_meters:g} m; zonal mask = field polygon",
                )
                _journal_record(journal, raster_path, record)
                rows.append(_row_from_record(field_id, field_slug, record))
                written += 1
                print(f"run   {field_slug} {band} {depth}: mean={record['mean']} n={record['n_pixels']}")

    table = _merge_stats_table(rows)
    table_path = shared_soilgrids_stats_table_path()

    journal_path = shared_soilgrids_journal_path()
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provenance = {
        "source": sg.SOURCE_NAME,
        "source_base": sg.SOURCE_BASE,
        "license": sg.LICENSE,
        "attribution": sg.ATTRIBUTION,
        "grower_slug": grower_slug,
        "farm_slug": farm_slug,
        "accessed_at": sg.utc_now(),
        "rasterio_version": sg.rasterio.__version__,
        "gdal_version": sg.gdal_version(),
        "buffer_meters": args.buffer_meters,
        "bands": bands,
        "depths": depths,
        "scale_factors": {
            band: {
                "unit": sg.band_spec(band)["unit"],
                "scale": sg.band_spec(band)["scale"],
                "offset": sg.band_spec(band)["offset"],
            }
            for band in bands
        },
        "fields": sorted({r["field_slug"] for r in rows}),
        "rasters_written": written,
        "rasters_skipped_existing": skipped,
        "stats_table": str(table_path),
        "journal": str(journal_path),
    }
    provenance_path = farm_soilgrids_provenance_path(grower_slug, farm_slug)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(
        f"\n✓ SoilGrids: {written} rasters clipped, {skipped} reused, "
        f"{len(table)} stats rows total"
    )
    print(f"  Stats table: {table_path}")
    print(f"  Provenance:  {provenance_path}")
    print(f"  Journal:     {journal_path}")


if __name__ == "__main__":
    main()
