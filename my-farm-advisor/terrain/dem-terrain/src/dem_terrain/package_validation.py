"""Offline invariant checks for runtime DEM terrain output packages.

The validator reads an existing ``dem_terrain_manifest.json`` and checks it
against the product and schema contract in ``terrain_contract.py``. It is safe
for synthetic smoke tests: it never downloads providers and never writes DEM
outputs. Raster metadata checks load rasterio lazily so missing runtime raster
dependencies produce a clear validation error instead of an import traceback.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

try:  # Support both package imports and direct script execution.
    from .terrain_contract import (
        MANIFEST_ASSET_SCHEMA_FIELDS,
        MANIFEST_SCHEMA_FIELDS,
        PRODUCT_DEFINITIONS,
        SUMMARY_DEFINITIONS,
    )
except ImportError:  # pragma: no cover - exercised by direct CLI smoke usage.
    from terrain_contract import (  # type: ignore[no-redef]
        MANIFEST_ASSET_SCHEMA_FIELDS,
        MANIFEST_SCHEMA_FIELDS,
        PRODUCT_DEFINITIONS,
        SUMMARY_DEFINITIONS,
    )


DEFAULT_NODATA_RATIO_THRESHOLD = 0.75
FIELD_BOUNDARY_FILENAME = "field_boundary.geojson"
SOURCE_REFERENCE_FILENAME = "dem_source_reference.json"
SYNTHETIC_FIXTURE_WARNING = (
    "SYNTHETIC DEM FIXTURE ONLY - not real grower DEM evidence and not valid for agronomic decisions"
)
SYNTHETIC_URL_PREFIXES = ("synthetic://", "runtime-cache://offline-fixtures/")


@dataclass(slots=True)
class PackageValidationResult:
    """Collected validation messages for one DEM terrain package."""

    manifest_path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_check(self, message: str) -> None:
        self.checks.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.ok else "failed",
            "manifest_path": str(self.manifest_path),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def validate_dem_terrain_package(
    manifest_path: str | Path,
    *,
    field_boundary_path: str | Path | None = None,
    nodata_ratio_threshold: float = DEFAULT_NODATA_RATIO_THRESHOLD,
    repo_root: str | Path | None = None,
    check_git: bool = True,
    allow_synthetic_fixture_package: bool = False,
) -> PackageValidationResult:
    """Validate a runtime DEM terrain package and return structured results."""

    manifest = Path(manifest_path).expanduser().resolve()
    result = PackageValidationResult(manifest_path=manifest)
    payload = _load_manifest(manifest, result)
    if payload is None:
        return result

    _validate_manifest_fields(payload, result)
    outputs = payload.get("outputs")
    if not isinstance(outputs, dict):
        result.add_error("manifest.outputs must be an object")
        outputs = {}

    _validate_not_synthetic_fixture_package(
        payload,
        outputs,
        manifest,
        result,
        allow_synthetic_fixture_package=allow_synthetic_fixture_package,
    )

    _validate_required_outputs(outputs, manifest, result)
    _validate_source_warnings(payload, result)
    _validate_rasters(
        outputs,
        payload,
        manifest,
        result,
        field_boundary_path=_resolve_boundary_path(manifest, field_boundary_path),
        nodata_ratio_threshold=nodata_ratio_threshold,
    )
    if check_git:
        _validate_no_tracked_generated_assets(repo_root, result)
    return result


def _load_manifest(path: Path, result: PackageValidationResult) -> dict[str, Any] | None:
    if not path.exists():
        result.add_error(f"manifest file does not exist: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.add_error(f"manifest is not valid JSON: {exc}")
        return None
    except OSError as exc:
        result.add_error(f"manifest could not be read: {exc}")
        return None
    if not isinstance(payload, dict):
        result.add_error("manifest root must be a JSON object")
        return None
    result.add_check("manifest JSON loaded")
    return payload


def _validate_manifest_fields(payload: dict[str, Any], result: PackageValidationResult) -> None:
    missing = [field_name for field_name in MANIFEST_SCHEMA_FIELDS if field_name not in payload]
    if missing:
        result.add_error("missing manifest required fields: " + ", ".join(missing))
    else:
        result.add_check(f"all {len(MANIFEST_SCHEMA_FIELDS)} required manifest fields present")

    selected = payload.get("selected_source")
    if not isinstance(selected, dict):
        result.add_error("manifest.selected_source must be an object")
    elif "fallback_reason" in selected and selected.get("fallback_reason") != payload.get("fallback_reason"):
        result.add_error("manifest fallback_reason does not match selected_source.fallback_reason")
    else:
        result.add_check("fallback reason field is present and internally consistent")


def _validate_required_outputs(
    outputs: dict[str, Any],
    manifest_path: Path,
    result: PackageValidationResult,
) -> None:
    product_filenames = {definition.name: definition.filename for definition in PRODUCT_DEFINITIONS}
    summary_filenames = {definition.name: definition.filename for definition in SUMMARY_DEFINITIONS}
    required = {**product_filenames, **summary_filenames}

    missing_products = [name for name in required if name not in outputs]
    if missing_products:
        result.add_error("missing required output products: " + ", ".join(missing_products))
    else:
        result.add_check(f"all {len(required)} required output products listed")

    asset_field_error_count = 0
    for product_name, expected_filename in required.items():
        asset = outputs.get(product_name)
        if not isinstance(asset, dict):
            continue
        missing_asset_fields = [field_name for field_name in MANIFEST_ASSET_SCHEMA_FIELDS if field_name not in asset]
        if missing_asset_fields:
            asset_field_error_count += 1
            result.add_error(
                f"output {product_name} missing asset fields: " + ", ".join(missing_asset_fields)
            )
        href = asset.get("href")
        if not isinstance(href, str) or not href.strip():
            result.add_error(f"output {product_name} missing href")
            continue
        path = _resolve_href(href, manifest_path)
        if path.name != expected_filename:
            result.add_error(
                f"output {product_name} filename mismatch: expected {expected_filename}, got {path.name}"
            )
        if not path.exists():
            result.add_error(f"output {product_name} file does not exist: {path}")
    if not missing_products and asset_field_error_count == 0:
        result.add_check("required output asset records include manifest asset schema fields")


def _validate_source_warnings(payload: dict[str, Any], result: PackageValidationResult) -> None:
    surface_type = str(payload.get("surface_type") or "").upper()
    selected = payload.get("selected_source") if isinstance(payload.get("selected_source"), dict) else {}
    selected_surface = str(selected.get("surface_type") or "").upper() if isinstance(selected, dict) else ""
    warning_text = " ".join(
        str(value)
        for value in (
            payload.get("warnings", []),
            selected.get("warnings", []) if isinstance(selected, dict) else [],
            payload.get("fallback_reason", ""),
        )
    ).lower()
    if "DSM" in {surface_type, selected_surface} and "dsm" not in warning_text:
        result.add_error("DSM selected_source requires an explicit DSM warning")
    else:
        result.add_check("DSM warning invariant satisfied")


def _validate_not_synthetic_fixture_package(
    payload: dict[str, Any],
    outputs: dict[str, Any],
    manifest_path: Path,
    result: PackageValidationResult,
    *,
    allow_synthetic_fixture_package: bool,
) -> None:
    matches = list(_synthetic_marker_matches(payload, location="manifest"))
    source_reference = _load_source_reference_for_synthetic_scan(outputs, manifest_path, result)
    if source_reference is not None:
        matches.extend(_synthetic_marker_matches(source_reference, location="source reference"))

    if not matches:
        result.add_check("synthetic fixture marker scan passed")
        return

    detail = "; ".join(matches[:8])
    if len(matches) > 8:
        detail += f"; +{len(matches) - 8} more"
    message = "synthetic DEM fixture package detected: " + detail
    if allow_synthetic_fixture_package:
        result.add_warning(message + " (allowed by --allow-synthetic-fixture-package)")
        result.add_check("synthetic fixture marker scan inspected with explicit allowance")
        return
    result.add_error(message + "; rerun with --allow-synthetic-fixture-package only for test inspection")


def _load_source_reference_for_synthetic_scan(
    outputs: dict[str, Any],
    manifest_path: Path,
    result: PackageValidationResult,
) -> dict[str, Any] | None:
    candidates = _source_reference_candidates(outputs, manifest_path)
    if not candidates:
        result.add_warning("DEM source reference not found for synthetic marker scan")
        return None
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            result.add_error(f"DEM source reference is not valid JSON for synthetic scan: {candidate}: {exc}")
            return None
        except OSError as exc:
            result.add_error(f"DEM source reference could not be read for synthetic scan: {candidate}: {exc}")
            return None
        if not isinstance(payload, dict):
            result.add_error(f"DEM source reference root must be a JSON object for synthetic scan: {candidate}")
            return None
        result.add_check(f"DEM source reference loaded for synthetic marker scan: {candidate}")
        return payload
    result.add_warning("DEM source reference not found for synthetic marker scan")
    return None


def _source_reference_candidates(outputs: dict[str, Any], manifest_path: Path) -> list[Path]:
    candidates: list[Path] = []
    asset = outputs.get("dem_source_reference")
    if isinstance(asset, dict) and isinstance(asset.get("href"), str) and asset["href"].strip():
        candidates.append(_resolve_href(asset["href"], manifest_path))
    candidates.extend(
        [
            manifest_path.parent / SOURCE_REFERENCE_FILENAME,
            manifest_path.parent.parent / "terrain" / "dem" / SOURCE_REFERENCE_FILENAME,
            manifest_path.parent.parent / "dem" / SOURCE_REFERENCE_FILENAME,
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _synthetic_marker_matches(value: Any, *, location: str) -> Iterable[str]:
    yield from _synthetic_marker_matches_at(value, path=location)


def _synthetic_marker_matches_at(value: Any, *, path: str) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            key_text = str(key)
            if key_text in {"synthetic_fixture", "test_only"}:
                if item is True:
                    yield f"{item_path}=true"
                elif isinstance(item, str) and item.strip().lower() == "true":
                    yield f"{item_path}=true"
            yield from _synthetic_marker_matches_at(item, path=item_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _synthetic_marker_matches_at(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered in {"synthetic_fixture=true", "test_only=true"}:
            yield f"{path}={stripped}"
        if stripped.startswith(SYNTHETIC_URL_PREFIXES):
            yield f"{path}={stripped}"
        if SYNTHETIC_FIXTURE_WARNING.lower() in lowered:
            yield f"{path} contains synthetic fixture evidence warning"


def _validate_rasters(
    outputs: dict[str, Any],
    payload: dict[str, Any],
    manifest_path: Path,
    result: PackageValidationResult,
    *,
    field_boundary_path: Path | None,
    nodata_ratio_threshold: float,
) -> None:
    raster_products = [definition.name for definition in PRODUCT_DEFINITIONS if definition.filename.endswith(".tif")]
    try:
        import rasterio
        from rasterio.crs import CRS
    except ImportError:
        result.add_error("raster metadata checks require optional dependency rasterio")
        return

    expected_crs_raw = payload.get("analysis_crs")
    expected_crs = CRS.from_user_input(expected_crs_raw) if expected_crs_raw else None
    raster_bounds_for_coverage: tuple[float, float, float, float] | None = None
    raster_crs_for_coverage: Any = None
    raster_pixel_size_for_coverage: float | None = None

    inspected_count = 0
    for product_name in raster_products:
        asset = outputs.get(product_name)
        if not isinstance(asset, dict) or not isinstance(asset.get("href"), str):
            continue
        path = _resolve_href(asset["href"], manifest_path)
        if not path.exists():
            continue
        try:
            with rasterio.open(path) as dataset:
                if dataset.count < 1:
                    result.add_error(f"raster {product_name} has no bands")
                if dataset.crs is None:
                    result.add_error(f"raster {product_name} is missing CRS")
                else:
                    if dataset.crs.is_geographic:
                        result.add_error(f"raster {product_name} CRS must be projected, got {dataset.crs}")
                    if expected_crs is not None and dataset.crs != expected_crs:
                        result.add_error(
                            f"raster {product_name} CRS mismatch: expected {expected_crs}, got {dataset.crs}"
                        )
                validity = _dataset_validity(dataset)
                ratio = float(validity["nodata_ratio"])
                if int(validity["valid_pixel_count"]) <= 0:
                    result.add_error(f"raster {product_name} has no valid finite pixels")
                if ratio > nodata_ratio_threshold:
                    result.add_error(
                        f"raster {product_name} nodata ratio {ratio:.4f} exceeds threshold {nodata_ratio_threshold:.4f}"
                    )
                if product_name == "dem_clipped" and dataset.crs is not None:
                    raster_bounds_for_coverage = (
                        float(dataset.bounds.left),
                        float(dataset.bounds.bottom),
                        float(dataset.bounds.right),
                        float(dataset.bounds.top),
                    )
                    raster_crs_for_coverage = dataset.crs
                    raster_pixel_size_for_coverage = _dataset_pixel_size(dataset)
                inspected_count += 1
        except Exception as exc:  # rasterio raises multiple concrete exception types.
            result.add_error(f"raster {product_name} could not be inspected: {exc}")
    result.add_check(f"inspected {inspected_count}/{len(raster_products)} contract raster products")

    if field_boundary_path is None:
        result.add_warning("field boundary not found; buffered AOI coverage check skipped")
        return
    if raster_bounds_for_coverage is None or raster_crs_for_coverage is None:
        result.add_error("buffered AOI coverage check requires a readable dem_clipped raster")
        return
    _validate_buffered_aoi_coverage(
        field_boundary_path,
        raster_bounds_for_coverage,
        raster_crs_for_coverage,
        float(payload.get("buffer_meters") or 0.0),
        raster_pixel_size_for_coverage,
        result,
    )


def _dataset_validity(dataset: Any) -> dict[str, Any]:
    band = dataset.read(1, masked=True)
    total = int(band.size)
    if total == 0:
        return {"total_pixel_count": 0, "masked_pixel_count": 0, "valid_pixel_count": 0, "nodata_ratio": 1.0}
    mask = getattr(band, "mask", False)
    if isinstance(mask, bool):
        masked_count = total if mask else 0
    else:
        masked_count = int(mask.sum())
    values = band.compressed()
    try:
        import numpy as np

        valid_count = int(np.isfinite(values).sum())
    except Exception:
        valid_count = int(len(values))
    nodata_count = max(masked_count, total - valid_count)
    return {
        "total_pixel_count": total,
        "masked_pixel_count": masked_count,
        "valid_pixel_count": valid_count,
        "nodata_ratio": float(nodata_count) / float(total),
    }


def _dataset_pixel_size(dataset: Any) -> float | None:
    try:
        x_size, y_size = dataset.res
        pixel_sizes = [abs(float(value)) for value in (x_size, y_size) if float(value) > 0.0]
    except (AttributeError, TypeError, ValueError):
        return None
    return max(pixel_sizes) if pixel_sizes else None


def _validate_buffered_aoi_coverage(
    boundary_path: Path,
    raster_bounds: tuple[float, float, float, float],
    raster_crs: Any,
    buffer_meters: float,
    raster_pixel_size: float | None,
    result: PackageValidationResult,
) -> None:
    try:
        import rasterio.warp
    except ImportError:
        result.add_error("buffered AOI coverage check requires optional dependency rasterio")
        return
    try:
        boundary_payload = json.loads(boundary_path.read_text(encoding="utf-8"))
        geometry = _first_geojson_geometry(boundary_payload)
        transformed = rasterio.warp.transform_geom("EPSG:4326", raster_crs, geometry)
        coords = list(_iter_geojson_coords(transformed.get("coordinates", [])))
    except Exception as exc:
        result.add_error(f"field boundary could not be inspected for coverage: {exc}")
        return
    if not coords:
        result.add_error("field boundary has no coordinates for coverage check")
        return
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    expected = (
        min(xs) - buffer_meters,
        min(ys) - buffer_meters,
        max(xs) + buffer_meters,
        max(ys) + buffer_meters,
    )
    meter_tolerance = max(buffer_meters * 0.05, 1.0)
    pixel_tolerance = raster_pixel_size or 0.0
    tolerance = meter_tolerance + pixel_tolerance
    covers = (
        raster_bounds[0] <= expected[0] + tolerance
        and raster_bounds[1] <= expected[1] + tolerance
        and raster_bounds[2] >= expected[2] - tolerance
        and raster_bounds[3] >= expected[3] - tolerance
    )
    if not covers:
        result.add_error(
            "dem_clipped bounds do not cover buffered AOI: "
            f"raster={raster_bounds}, expected_buffered_bounds={expected}"
        )
        return
    result.add_check("dem_clipped bounds cover field boundary plus requested buffer")


def _first_geojson_geometry(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        features = payload.get("features")
        if isinstance(features, list) and features:
            geometry = features[0].get("geometry") if isinstance(features[0], dict) else None
            if isinstance(geometry, dict):
                return geometry
    if isinstance(payload, dict) and payload.get("type") == "Feature":
        geometry = payload.get("geometry")
        if isinstance(geometry, dict):
            return geometry
    if isinstance(payload, dict) and "coordinates" in payload:
        return payload
    raise ValueError("expected GeoJSON FeatureCollection, Feature, or geometry")


def _iter_geojson_coords(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        yield (float(value[0]), float(value[1]))
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_geojson_coords(item)


def _resolve_boundary_path(manifest_path: Path, field_boundary_path: str | Path | None) -> Path | None:
    if field_boundary_path is not None:
        return Path(field_boundary_path).expanduser().resolve()
    inferred = manifest_path.parent.parent / "boundary" / FIELD_BOUNDARY_FILENAME
    return inferred if inferred.exists() else None


def _resolve_href(href: str, manifest_path: Path) -> Path:
    parsed = urlparse(href)
    if parsed.scheme == "file":
        return Path(parsed.path).expanduser().resolve()
    if parsed.scheme:
        return Path(href)
    path = Path(href).expanduser()
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def _validate_no_tracked_generated_assets(
    repo_root: str | Path | None,
    result: PackageValidationResult,
) -> None:
    root = _find_repo_root(Path(repo_root).expanduser().resolve() if repo_root is not None else Path.cwd())
    if root is None:
        result.add_warning("git repository root not found; tracked generated asset check skipped")
        return
    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        result.add_warning(f"git tracked generated asset check skipped: {exc}")
        return

    forbidden_names = {
        "dem_clipped.tif",
        "dem_conditioned.tif",
        "dem_terrain_manifest.json",
        "dem_terrain_summary.csv",
        "dem_terrain_summary.json",
        *(definition.filename for definition in PRODUCT_DEFINITIONS if definition.filename.endswith(".tif")),
    }
    tracked = []
    for raw in completed.stdout.splitlines():
        path = Path(raw)
        if path.name not in forbidden_names and path.suffix.lower() != ".png":
            continue
        text = raw.replace("\\", "/")
        if text.startswith("my-farm-advisor/terrain/dem-terrain/") or text.startswith("my-farm-advisor/data-pipeline/"):
            tracked.append(raw)
    if tracked:
        result.add_error("tracked generated DEM assets found: " + ", ".join(tracked))
    else:
        result.add_check("no tracked generated DEM assets found in repository")


def _find_repo_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a runtime DEM terrain output package. Synthetic fixture packages are rejected by "
            "default so test-only DEM artifacts cannot be accepted as real grower evidence."
        )
    )
    parser.add_argument("manifest", help="Path to dem_terrain_manifest.json")
    parser.add_argument(
        "--field-boundary",
        help="Optional field_boundary.geojson path. Defaults to the canonical sibling boundary path when present.",
    )
    parser.add_argument(
        "--nodata-ratio-threshold",
        type=float,
        default=DEFAULT_NODATA_RATIO_THRESHOLD,
        help=f"Maximum allowed nodata ratio for each GeoTIFF (default: {DEFAULT_NODATA_RATIO_THRESHOLD})",
    )
    parser.add_argument("--repo-root", help="Optional repository root for tracked generated asset checks")
    parser.add_argument("--no-git-check", action="store_true", help="Skip git tracked generated asset invariant")
    parser.add_argument(
        "--allow-synthetic-fixture-package",
        action="store_true",
        help=(
            "TEST ONLY: inspect a package containing synthetic fixture markers instead of rejecting it by default"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result instead of text summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = validate_dem_terrain_package(
        args.manifest,
        field_boundary_path=args.field_boundary,
        nodata_ratio_threshold=args.nodata_ratio_threshold,
        repo_root=args.repo_root,
        check_git=not args.no_git_check,
        allow_synthetic_fixture_package=args.allow_synthetic_fixture_package,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"DEM terrain package validation: {'ok' if result.ok else 'failed'}")
        for check in result.checks:
            print(f"ok: {check}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
