#!/usr/bin/env python3
"""Download clipped raw satellite TIFFs and NDVI rasters for each field."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import pandas as pd

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.paths import DATA_ROOT, farm_boundary_path, field_boundary_path, field_satellite_dir  # noqa: E402
from lib.satellite_imagery import (  # noqa: E402
    LANDSAT_COLLECTION,
    SENTINEL_COLLECTION,
    clip_asset_to_field,
    compute_landsat_ndvi,
    compute_sentinel_ndvi,
    feature_cloud_cover,
    feature_datetime,
    growing_season_range,
    landsat_asset_keys,
    SatelliteSearchError,
    search_features,
    sentinel_asset_keys,
    sign_planetary_computer_href,
)
from reporting_bootstrap import ensure_skill_path  # noqa: E402

_REPO = DATA_ROOT
_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")
_DEFAULT_FARM_NAME = os.environ.get("AG_FARM_NAME", "Default Farm")
_DEFAULT_INVENTORY = _REPO / "growers" / _DEFAULT_GROWER / "farms" / _DEFAULT_FARM / "manifests" / "field-inventory.csv"
_FIELD_INVENTORY = Path(os.environ.get("AG_INVENTORY_CSV", str(_DEFAULT_INVENTORY)))

ensure_skill_path("farm-intelligence-reporting")

from pipeline import FieldReportingConfig  # noqa: E402  # pyright: ignore[reportMissingImports]

_GROWING_SEASON_MONTHS = (3, 4, 5, 6, 7, 8, 9, 10, 11)


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _scene_dir(sensor_root: Path, scene_date: datetime, sensor: str) -> Path:
    return (
        sensor_root / f"{scene_date.year}" / f"{sensor}_{scene_date.strftime('%Y%m%d')}"
    )


def _scene_paths(
    sensor_root: Path, scene_date: datetime, sensor: str
) -> dict[str, Path]:
    scene_dir = _scene_dir(sensor_root, scene_date, sensor)
    stamp = scene_date.strftime("%Y%m%d")
    if sensor == "sentinel":
        return {
            "scene_dir": scene_dir,
            "red": scene_dir / f"sentinel_{stamp}_red.tif",
            "nir": scene_dir / f"sentinel_{stamp}_nir.tif",
            "scl": scene_dir / f"sentinel_{stamp}_scl.tif",
            "ndvi": scene_dir / f"sentinel_{stamp}_ndvi.tif",
        }
    return {
        "scene_dir": scene_dir,
        "red": scene_dir / f"landsat_{stamp}_red.tif",
        "nir": scene_dir / f"landsat_{stamp}_nir.tif",
        "qa": scene_dir / f"landsat_{stamp}_qa_pixel.tif",
        "ndvi": scene_dir / f"landsat_{stamp}_ndvi.tif",
    }


def _ensure_field_boundary(
    field_row: pd.Series, grower_slug: str, farm_slug: str, field_slug: str
) -> Path:
    output_path = field_boundary_path(grower_slug, farm_slug, field_slug)
    field_gdf = gpd.GeoDataFrame([field_row], geometry="geometry", crs="EPSG:4326")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    field_gdf.to_file(output_path, driver="GeoJSON")
    return output_path


def _relative_to_repo(path: Path) -> str:
    return str(path.relative_to(_REPO))


def _existing_entry_is_reusable(
    entry: dict[str, Any] | None, expected_id: str, paths: dict[str, Path]
) -> bool:
    if (
        not entry
        or entry.get("scene_id") != expected_id
        or entry.get("status") != "complete"
    ):
        return False
    required = [path for key, path in paths.items() if key != "scene_dir"]
    return all(path.exists() for path in required)


def _normalize_year_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    scenes = normalized.get("scenes")
    if isinstance(scenes, list):
        normalized["scenes"] = scenes
    elif normalized.get("scene_id"):
        normalized["scenes"] = [
            {
                "scene_id": normalized.get("scene_id"),
                "scene_date": normalized.get("scene_date"),
                "cloud_cover": normalized.get("cloud_cover"),
                "status": normalized.get("status", "complete"),
                "raw_tiffs": normalized.get("raw_tiffs", {}),
                "ndvi_tif": normalized.get("ndvi_tif"),
            }
        ]
    else:
        normalized["scenes"] = []
    normalized["scene_count"] = int(
        normalized.get("scene_count", len(normalized["scenes"]))
    )
    normalized.setdefault("coverage_months", [])
    normalized.setdefault("missing_months", [])
    return normalized


def _year_entry_fully_reusable(
    previous_entry: dict[str, Any] | None, *, sensor_root: Path, sensor: str
) -> tuple[bool, list[dict[str, Any]]]:
    if previous_entry is None:
        return False, []
    normalized = _normalize_year_entry(previous_entry)
    scenes = cast(list[dict[str, Any]], normalized.get("scenes", []))
    if normalized.get("status") != "complete" or not scenes:
        return False, []

    reusable: list[dict[str, Any]] = []
    for scene in scenes:
        scene_date_raw = scene.get("scene_date")
        scene_id = str(scene.get("scene_id", "")).strip()
        if not scene_date_raw or not scene_id:
            return False, []
        scene_date = datetime.fromisoformat(str(scene_date_raw))
        scene_paths = _scene_paths(sensor_root, scene_date, sensor)
        if not _existing_entry_is_reusable(scene, scene_id, scene_paths):
            return False, []
        reusable.append(scene)
    return True, reusable


def _select_scene_inventory(
    features: list[dict[str, Any]], *, max_scenes_per_year: int
) -> list[dict[str, Any]]:
    sorted_features = sorted(
        features,
        key=lambda feature: (
            feature_cloud_cover(feature),
            -feature_datetime(feature).timestamp(),
        ),
    )
    by_month: dict[int, list[dict[str, Any]]] = {}
    for feature in sorted_features:
        month = feature_datetime(feature).month
        if month not in _GROWING_SEASON_MONTHS:
            continue
        by_month.setdefault(month, []).append(feature)

    selected: list[dict[str, Any]] = []
    for month in _GROWING_SEASON_MONTHS:
        monthly = by_month.get(month, [])
        if not monthly:
            continue
        selected.append(monthly[0])

    return selected[:max_scenes_per_year]


def _download_sentinel_scene(
    feature: dict[str, Any], field_geom: Any, sensor_root: Path
) -> dict[str, Any]:
    scene_date = feature_datetime(feature)
    paths = _scene_paths(sensor_root, scene_date, "sentinel")
    asset_keys = sentinel_asset_keys(feature)
    assets = feature["assets"]
    red_path = clip_asset_to_field(
        sign_planetary_computer_href(
            SENTINEL_COLLECTION, assets[asset_keys["red"]]["href"]
        ),
        field_geom,
        paths["red"],
    )
    nir_path = clip_asset_to_field(
        sign_planetary_computer_href(
            SENTINEL_COLLECTION, assets[asset_keys["nir"]]["href"]
        ),
        field_geom,
        paths["nir"],
    )
    scl_path = clip_asset_to_field(
        sign_planetary_computer_href(
            SENTINEL_COLLECTION, assets[asset_keys["scl"]]["href"]
        ),
        field_geom,
        paths["scl"],
    )
    ndvi_path = compute_sentinel_ndvi(red_path, nir_path, scl_path, paths["ndvi"])
    return {
        "scene_id": feature["id"],
        "scene_date": scene_date.date().isoformat(),
        "cloud_cover": round(feature_cloud_cover(feature), 3),
        "status": "complete",
        "raw_tiffs": {
            "red": _relative_to_repo(red_path),
            "nir": _relative_to_repo(nir_path),
            "scl": _relative_to_repo(scl_path),
        },
        "ndvi_tif": _relative_to_repo(ndvi_path),
        "coverage": _coverage_of(red_path, field_geom),
    }


def _download_landsat_scene(
    feature: dict[str, Any], field_geom: Any, sensor_root: Path
) -> dict[str, Any]:
    scene_date = feature_datetime(feature)
    paths = _scene_paths(sensor_root, scene_date, "landsat")
    asset_keys = landsat_asset_keys(feature)
    assets = feature["assets"]
    red_path = clip_asset_to_field(
        sign_planetary_computer_href(
            LANDSAT_COLLECTION, assets[asset_keys["red"]]["href"]
        ),
        field_geom,
        paths["red"],
    )
    nir_path = clip_asset_to_field(
        sign_planetary_computer_href(
            LANDSAT_COLLECTION, assets[asset_keys["nir"]]["href"]
        ),
        field_geom,
        paths["nir"],
    )
    qa_path = clip_asset_to_field(
        sign_planetary_computer_href(
            LANDSAT_COLLECTION, assets[asset_keys["qa"]]["href"]
        ),
        field_geom,
        paths["qa"],
    )
    ndvi_path = compute_landsat_ndvi(red_path, nir_path, qa_path, paths["ndvi"])
    return {
        "scene_id": feature["id"],
        "scene_date": scene_date.date().isoformat(),
        "cloud_cover": round(feature_cloud_cover(feature), 3),
        "status": "complete",
        "raw_tiffs": {
            "red": _relative_to_repo(red_path),
            "nir": _relative_to_repo(nir_path),
            "qa_pixel": _relative_to_repo(qa_path),
        },
        "ndvi_tif": _relative_to_repo(ndvi_path),
        "coverage": _coverage_of(red_path, field_geom),
    }


def _coverage_of(tif_path: Path, field_geom) -> dict | None:
    """raster_rules field/pixel overlap stats journalled in the manifest."""
    try:
        import sys as _s
        _s.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
        import raster_rules as _rr
        return _rr.coverage(tif_path, field_geom)
    except Exception:
        return None


def _load_sensor_manifest(
    path: Path, dataset_name: str, field_id: str, field_slug: str
) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "dataset_name": dataset_name,
        "field_id": field_id,
        "field_slug": field_slug,
        "years": [],
    }


def _download_sensor_archive(
    *,
    field_id: str,
    field_slug: str,
    field_geom: Any,
    grower_slug: str,
    farm_slug: str,
    years: tuple[int, ...],
    sensor: str,
    collection: str,
    cloud_cover_max: float,
    max_scenes_per_year: int,
    force: bool,
) -> None:
    sensor_root = field_satellite_dir(grower_slug, farm_slug, field_slug) / sensor
    manifest_path = sensor_root / "manifest.json"
    previous_manifest = _load_sensor_manifest(
        manifest_path, sensor, field_id, field_slug
    )
    previous_by_year = {
        int(entry["year"]): _normalize_year_entry(entry)
        for entry in previous_manifest.get("years", [])
        if "year" in entry
    }
    year_entries: list[dict[str, Any]] = []

    for year in years:
        previous_entry = previous_by_year.get(year)
        if not force:
            can_reuse_year, reusable_scenes = _year_entry_fully_reusable(
                previous_entry, sensor_root=sensor_root, sensor=sensor
            )
            if can_reuse_year:
                coverage_months = sorted(
                    {
                        int(datetime.fromisoformat(str(scene["scene_date"])).month)
                        for scene in reusable_scenes
                    }
                )
                missing_months = [
                    month
                    for month in _GROWING_SEASON_MONTHS
                    if month not in coverage_months
                ]
                year_entries.append(
                    {
                        "year": year,
                        "status": "complete",
                        "scene_count": len(reusable_scenes),
                        "coverage_months": coverage_months,
                        "missing_months": missing_months,
                        "coverage_status": "full" if not missing_months else "partial",
                        "reused": True,
                        "api_skipped": True,
                        "scenes": sorted(
                            reusable_scenes,
                            key=lambda scene: str(scene.get("scene_date", "")),
                        ),
                    }
                )
                print(
                    f"skip  {field_id} {sensor} {year} (manifest+files reusable; API skipped)"
                )
                continue

        try:
            features = search_features(
                collection,
                tuple(field_geom.bounds),
                growing_season_range(year),
                cloud_cover_max,
                limit=max(60, max_scenes_per_year * 8),
            )
        except SatelliteSearchError as exc:
            year_entries.append(
                {
                    "year": year,
                    "status": "missing",
                    "reason": "search_failed",
                    "error": str(exc),
                    "scene_count": 0,
                    "scenes": [],
                    "coverage_months": [],
                    "missing_months": list(_GROWING_SEASON_MONTHS),
                }
            )
            print(f"warn  {field_id} {sensor} {year} search failed: {exc}")
            continue
        selected_features = _select_scene_inventory(
            features, max_scenes_per_year=max_scenes_per_year
        )
        if not selected_features:
            year_entries.append(
                {
                    "year": year,
                    "status": "missing",
                    "reason": "no_scene_found",
                    "scene_count": 0,
                    "scenes": [],
                    "coverage_months": [],
                    "missing_months": list(_GROWING_SEASON_MONTHS),
                }
            )
            print(f"warn  {field_id} {sensor} {year} no scene found")
            continue

        scenes: list[dict[str, Any]] = []
        all_reusable = not force and previous_entry is not None
        for feature in selected_features:
            scene_date = feature_datetime(feature)
            scene_paths = _scene_paths(sensor_root, scene_date, sensor)
            previous_scene = None
            if previous_entry is not None:
                previous_scene = next(
                    (
                        scene
                        for scene in previous_entry.get("scenes", [])
                        if scene.get("scene_id") == feature["id"]
                    ),
                    None,
                )
            if not force and _existing_entry_is_reusable(
                previous_scene, feature["id"], scene_paths
            ):
                scenes.append(cast(dict[str, Any], previous_scene))
                print(f"skip  {field_id} {sensor} {year} {feature['id']}")
                continue

            all_reusable = False
            print(f"run   {field_id} {sensor} {year} {feature['id']}")
            try:
                if sensor == "sentinel":
                    scenes.append(
                        _download_sentinel_scene(feature, field_geom, sensor_root)
                    )
                else:
                    scenes.append(
                        _download_landsat_scene(feature, field_geom, sensor_root)
                    )
            except Exception as exc:
                print(
                    f"warn  {field_id} {sensor} {year} {feature['id']} skipped: {exc}"
                )

        coverage_months = sorted(
            {
                int(datetime.fromisoformat(str(scene["scene_date"])).month)
                for scene in scenes
            }
        )
        missing_months = [
            month for month in _GROWING_SEASON_MONTHS if month not in coverage_months
        ]
        year_entries.append(
            {
                "year": year,
                "status": "complete" if scenes else "missing",
                "scene_count": len(scenes),
                "coverage_months": coverage_months,
                "missing_months": missing_months,
                "coverage_status": "full" if not missing_months else "partial",
                "reused": all_reusable,
                "scenes": sorted(
                    scenes, key=lambda scene: str(scene.get("scene_date", ""))
                ),
            }
        )

    manifest = {
        "dataset_name": sensor,
        "field_id": field_id,
        "field_slug": field_slug,
        "grower_slug": grower_slug,
        "farm_slug": farm_slug,
        "generated_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "years": sorted(year_entries, key=lambda entry: entry["year"]),
    }
    _write_json(manifest_path, manifest)


def main() -> None:
    print("=" * 60)
    print("Satellite imagery download - raw TIFFs first")
    print("=" * 60)

    force = os.environ.get("AG_FORCE") == "1"
    config = FieldReportingConfig(
        farm_name=_DEFAULT_FARM_NAME,
        field_boundary_path=str(farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)),
    )
    field_slugs = _field_slug_lookup()
    fields = gpd.read_file(_REPO / config.field_boundary_path).to_crs("EPSG:4326")

    for _, field in fields.iterrows():
        field_id = str(field["field_id"])
        field_slug = field_slugs.get(field_id)
        if not field_slug:
            print(f"skip  {field_id} no field slug")
            continue
        _ensure_field_boundary(field, _DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        _download_sensor_archive(
            field_id=field_id,
            field_slug=field_slug,
            field_geom=field.geometry,
            grower_slug=_DEFAULT_GROWER,
            farm_slug=_DEFAULT_FARM,
            years=config.imagery_years,
            sensor="sentinel",
            collection=SENTINEL_COLLECTION,
            cloud_cover_max=config.sentinel_cloud_cover_max,
            max_scenes_per_year=9,
            force=force,
        )
        _download_sensor_archive(
            field_id=field_id,
            field_slug=field_slug,
            field_geom=field.geometry,
            grower_slug=_DEFAULT_GROWER,
            farm_slug=_DEFAULT_FARM,
            years=config.imagery_years,
            sensor="landsat",
            collection=LANDSAT_COLLECTION,
            cloud_cover_max=config.landsat_cloud_cover_max,
            max_scenes_per_year=9,
            force=force,
        )

    print("\n✓ Raw satellite TIFF download complete")


if __name__ == "__main__":
    main()
