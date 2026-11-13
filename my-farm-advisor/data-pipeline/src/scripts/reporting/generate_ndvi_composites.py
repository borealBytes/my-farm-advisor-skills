#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""Build yearly NDVI composites and crop-conditioned rollup rasters."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))
_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
_DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
_DEFAULT_INVENTORY = _REPO / "growers" / _DEFAULT_GROWER / "farms" / _DEFAULT_FARM / "manifests" / "field-inventory.csv"
_FIELD_INVENTORY = Path(os.environ.get("AG_INVENTORY_CSV", str(_DEFAULT_INVENTORY)))

from reporting_bootstrap import ensure_skill_path  # noqa: E402


ensure_skill_path("farm-intelligence-reporting")
ensure_skill_path("cdl-cropland")

from cdl_reporting import (
    filter_cdl_categories,  # noqa: E402  # pyright: ignore[reportMissingImports]
)
from paths import (  # noqa: E402
    farm_boundary_path,
    farm_cdl_preferred_full_composition_path,
    field_feature_path,
    field_manifest_dir,
    field_satellite_dir,
    field_summary_path,
    field_tables_dir,
    shared_cdl_preferred_full_composition_path,
)
from pipeline import (  # noqa: E402
    FieldReportingConfig,
    build_step_manifest,
    load_manifest,
    step_is_stale,
)  # pyright: ignore[reportMissingImports]

_SCRIPT = Path(__file__)


def _field_slug_lookup(inventory_path: Path = _FIELD_INVENTORY) -> dict[str, str]:
    if not inventory_path.exists():
        return {}
    inventory = pd.read_csv(inventory_path)
    if not {"field_id", "field_slug"}.issubset(inventory.columns):
        return {}
    return {
        str(row["field_id"]): str(row["field_slug"])
        for _, row in inventory[["field_id", "field_slug"]].dropna().iterrows()
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sensor_manifest_paths(field_slug: str) -> list[Path]:
    satellite_root = field_satellite_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
    return [
        satellite_root / "sentinel" / "manifest.json",
        satellite_root / "landsat" / "manifest.json",
    ]


def _collect_year_scene_paths(field_slug: str) -> dict[int, list[Path]]:
    by_year: dict[int, list[Path]] = {}
    for manifest_path in _sensor_manifest_paths(field_slug):
        if not manifest_path.exists():
            continue
        manifest = _load_json(manifest_path)
        for entry in manifest.get("years", []):
            year = entry.get("year")
            if year is None:
                continue
            for scene in entry.get("scenes", []):
                ndvi_tif = scene.get("ndvi_tif")
                if not ndvi_tif:
                    continue
                ndvi_path = _REPO / str(ndvi_tif)
                if ndvi_path.exists():
                    by_year.setdefault(int(year), []).append(ndvi_path)
    return by_year


def _dominant_crop_lookup(cdl_path: Path) -> dict[tuple[str, int], str]:
    cdl = filter_cdl_categories(pd.read_csv(cdl_path))
    if cdl.empty:
        return {}
    dominant = cdl.sort_values(
        ["field_id", "year", "pct"], ascending=[True, True, False]
    )
    dominant = dominant.groupby(["field_id", "year"], as_index=False).first()
    return {
        (str(row["field_id"]), int(row["year"])): str(row["crop_name"])
        for _, row in dominant[["field_id", "year", "crop_name"]].iterrows()
    }


def _read_resampled_like(source_path: Path, reference_path: Path) -> np.ndarray:
    with rasterio.open(reference_path) as ref_src, rasterio.open(source_path) as src:
        destination = np.full((ref_src.height, ref_src.width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_src.transform,
            dst_crs=ref_src.crs,
            resampling=Resampling.bilinear,
        )
    return destination


def _write_mean_raster(output_path: Path, raster_paths: list[Path]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference = raster_paths[0]
    stack = [_read_resampled_like(path, reference) for path in raster_paths]
    stacked = np.stack(stack, axis=0)
    valid_counts = np.sum(np.isfinite(stacked), axis=0)
    safe_sum = np.nansum(stacked, axis=0)
    mean_array = np.full(stacked.shape[1:], np.nan, dtype="float32")
    valid_mask = valid_counts > 0
    mean_array[valid_mask] = (safe_sum[valid_mask] / valid_counts[valid_mask]).astype(
        "float32"
    )
    with rasterio.open(reference) as src:
        profile = src.profile.copy()
    profile.update(dtype=rasterio.float32, count=1, compress="lzw", nodata=np.nan)
    from raster_rules import cog_profile as _cog  # pyright: ignore[reportMissingImports]
    with rasterio.open(output_path, "w", **_cog(profile, resampling="average")) as dst:
        dst.write(mean_array, 1)
    return output_path


def _output_paths(
    field_slug: str,
    yearly_inputs: dict[int, list[Path]],
    crop_lookup: dict[tuple[str, int], str],
    field_id: str,
) -> list[Path]:
    outputs: list[Path] = [
        field_summary_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_yearly_summary.json"
        ),
        field_tables_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        / "ndvi_year_crop_join.csv",
    ]
    for year in sorted(yearly_inputs):
        outputs.append(
            field_feature_path(
                _DEFAULT_GROWER,
                _DEFAULT_FARM,
                field_slug,
                f"ndvi_year_{year}_composite.tif",
            )
        )
    crops = {crop_lookup.get((field_id, year), "") for year in yearly_inputs}
    if "Corn" in crops:
        outputs.append(
            field_feature_path(
                _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_corn_rollup.tif"
            )
        )
    if "Soybeans" in crops:
        outputs.append(
            field_feature_path(
                _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_soybean_rollup.tif"
            )
        )
    return outputs


def main() -> None:
    print("=" * 60)
    print("NDVI yearly composites and crop joins")
    print("=" * 60)

    force = os.environ.get("AG_FORCE") == "1"
    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
        grower_slug=_DEFAULT_GROWER,
        farm_slug=_DEFAULT_FARM,
    )
    fields = gpd.read_file(_REPO / config.field_boundary_path)
    field_slugs = _field_slug_lookup()
    cdl_path = farm_cdl_preferred_full_composition_path(_DEFAULT_GROWER, _DEFAULT_FARM)
    if not cdl_path.exists():
        cdl_path = shared_cdl_preferred_full_composition_path()
    crop_lookup = _dominant_crop_lookup(cdl_path) if cdl_path.exists() else {}

    for _, field in fields.iterrows():
        field_id = str(field["field_id"])
        field_slug = field_slugs.get(field_id)
        if not field_slug:
            print(f"skip  {field_id} (no field slug)")
            continue

        yearly_inputs = _collect_year_scene_paths(field_slug)
        scene_inputs = [path for paths in yearly_inputs.values() for path in paths]
        input_paths = [*scene_inputs]
        if cdl_path.exists():
            input_paths.insert(0, cdl_path)
        outputs = _output_paths(field_slug, yearly_inputs, crop_lookup, field_id)
        manifest_dir = field_manifest_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        step_name = f"ndvi_composite_build_{field_id}"
        manifest = build_step_manifest(
            step_name=step_name,
            input_paths=input_paths,
            output_paths=outputs,
            code_paths=[_SCRIPT],
            config=config,
        )
        prior = load_manifest(manifest_dir / f"{step_name}.json")
        if not force and not step_is_stale(manifest, prior):
            print(f"skip  {field_id}")
            continue

        print(f"run   {field_id}")
        summary_rows: list[dict[str, Any]] = []
        yearly_rollups: dict[str, list[Path]] = {"Corn": [], "Soybeans": []}
        for year, raster_paths in sorted(yearly_inputs.items()):
            if not raster_paths:
                continue
            composite_path = field_feature_path(
                _DEFAULT_GROWER,
                _DEFAULT_FARM,
                field_slug,
                f"ndvi_year_{year}_composite.tif",
            )
            _write_mean_raster(composite_path, raster_paths)
            crop_name = crop_lookup.get((field_id, year), "Unknown")
            if crop_name in yearly_rollups:
                yearly_rollups[crop_name].append(composite_path)
            summary_rows.append(
                {
                    "field_id": field_id,
                    "field_slug": field_slug,
                    "year": year,
                    "crop_name": crop_name,
                    "scene_count": len(raster_paths),
                    "composite_tif": str(composite_path.relative_to(_REPO)),
                }
            )

        for crop_name, paths in yearly_rollups.items():
            if not paths:
                continue
            target_name = (
                "ndvi_corn_rollup.tif"
                if crop_name == "Corn"
                else "ndvi_soybean_rollup.tif"
            )
            _write_mean_raster(
                field_feature_path(
                    _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, target_name
                ),
                paths,
            )

        summary_df = pd.DataFrame(summary_rows)
        join_csv = (
            field_tables_dir(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
            / "ndvi_year_crop_join.csv"
        )
        join_csv.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(join_csv, index=False)
        summary_json = field_summary_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "ndvi_yearly_summary.json"
        )
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(
            json.dumps(
                {"field_id": field_id, "field_slug": field_slug, "years": summary_rows},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest.status = "complete"
        manifest.write(manifest_dir / f"{step_name}.json")

    print("\n✓ NDVI yearly composite generation complete")


if __name__ == "__main__":
    main()
