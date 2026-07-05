"""Hydrologic conditioning and field-scale terrain derivative products.

This module derives advisory terrain rasters from an already clipped DEM. It
does not discover or download DEM sources and it never overwrites the clipped
DEM. Hydrology products are field-screening proxies only, not engineered
drainage, culvert, or watershed-design outputs.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

import numpy as np
import rasterio

from .raster_processing import DEFAULT_NODATA, file_size, nodata_ratio, sha256_file, write_raster_atomic
from .terrain_contract import (
    CONDITIONED_DEM_FILENAME,
    DERIVED_RASTER_FILENAMES,
    SUMMARY_CSV_FILENAME,
    SUMMARY_JSON_FILENAME,
)


ADVISORY_HYDROLOGY_WARNING = (
    "hydrology_products_are_advisory_proxies_not_engineered_drainage_design"
)
FLAT_TERRAIN_LIMITED_FLOW_WARNING = "flat_or_near_flat_terrain_limited_flow_proxy_signal"
CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE = "skipped_backend_unavailable"
CONDITIONING_RICHDEM_FILL = "conditioned_richdem_fill_depressions"

_EPSILON = 1.0e-6
_DERIVED_UNITS: dict[str, str] = {
    "slope_degrees": "degrees",
    "slope_percent": "percent",
    "aspect_degrees": "degrees_clockwise_from_north",
    "hillshade": "unitless_0_255",
    "profile_curvature": "1/map_unit",
    "planform_curvature": "1/map_unit",
    "tpi": "meters",
    "tri": "meters",
    "flow_direction": "d8_esri_code",
    "flow_accumulation": "cells",
    "topographic_wetness_index": "unitless_ln_specific_area_over_slope",
    "depression_depth": "meters",
    "relative_elevation": "meters",
    "erosion_proxy": "unitless_advisory_proxy",
}

_D8_NEIGHBORS: tuple[tuple[int, int, int, float], ...] = (
    (0, 1, 1, 1.0),
    (1, 1, 2, math.sqrt(2.0)),
    (1, 0, 4, 1.0),
    (1, -1, 8, math.sqrt(2.0)),
    (0, -1, 16, 1.0),
    (-1, -1, 32, math.sqrt(2.0)),
    (-1, 0, 64, 1.0),
    (-1, 1, 128, math.sqrt(2.0)),
)
_CODE_TO_OFFSET = {code: (row_delta, col_delta) for row_delta, col_delta, code, _ in _D8_NEIGHBORS}


@dataclass(frozen=True, slots=True)
class TerrainProductRecord:
    """Serializable metadata for one generated terrain raster."""

    product_name: str
    filename: str
    path: str
    preview_path: str | None
    unit: str
    source_product: str
    advisory: bool
    nodata: float | int | None
    dtype: str
    width: int
    height: int
    resolution: tuple[float, float]
    nodata_ratio: float
    checksum_sha256: str
    file_size: int
    statistics: dict[str, float | None]
    warnings: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly product record."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class TerrainDerivativeResult:
    """Serializable result for one terrain derivative run."""

    dem_clipped_path: str
    output_dir: str
    conditioning_status: str
    conditioning_backend: str | None
    conditioned_dem: TerrainProductRecord
    products: tuple[TerrainProductRecord, ...]
    summary_json_path: str
    summary_csv_path: str
    quality_warnings: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly run result."""

        record = asdict(self)
        record["conditioned_dem"] = self.conditioned_dem.to_dict()
        record["products"] = [product.to_dict() for product in self.products]
        return record


def derive_terrain_products(
    dem_clipped_path: str | Path,
    output_dir: str | Path,
    *,
    preview_dir: str | Path | None = None,
    tables_dir: str | Path | None = None,
    summary_json_path: str | Path | None = None,
    summary_csv_path: str | Path | None = None,
    write_previews: bool = True,
) -> TerrainDerivativeResult:
    """Derive DEM terrain products, previews, and summary records.

    Parameters point at runtime or temporary directories. The input
    ``dem_clipped_path`` is read-only and is never replaced by the conditioned
    surface. When no optional hydrologic conditioning backend is importable,
    ``dem_conditioned.tif`` is a separate copy of the clipped DEM values and the
    summary records ``conditioning_status=skipped_backend_unavailable``.
    """

    dem_path = _validate_local_path(dem_clipped_path, role="dem_clipped_path")
    raster_dir = _validate_local_path(output_dir, role="output_dir")
    preview_output_dir = _validate_local_path(preview_dir, role="preview_dir") if preview_dir is not None else raster_dir / "previews"
    table_output_dir = _validate_local_path(tables_dir, role="tables_dir") if tables_dir is not None else raster_dir / "tables"
    json_output_path = _validate_local_path(summary_json_path, role="summary_json_path") if summary_json_path is not None else table_output_dir / SUMMARY_JSON_FILENAME
    csv_output_path = _validate_local_path(summary_csv_path, role="summary_csv_path") if summary_csv_path is not None else table_output_dir / SUMMARY_CSV_FILENAME

    dem, valid_mask, profile, source_nodata = _read_dem(dem_path)
    output_nodata = _output_nodata(source_nodata)
    warnings = _base_quality_warnings(profile, valid_mask)
    conditioned_dem, conditioning_status, conditioning_backend, conditioning_warnings = _condition_dem(
        dem,
        valid_mask,
    )
    warnings.extend(conditioning_warnings)

    transform = profile["transform"]
    x_resolution = abs(float(transform.a)) or 1.0
    y_resolution = abs(float(transform.e)) or x_resolution
    cell_area = x_resolution * y_resolution
    calculation_dem = _filled_for_calculation(conditioned_dem, valid_mask)
    raw_calculation_dem = _filled_for_calculation(dem, valid_mask)

    derivatives = _compute_derivatives(
        calculation_dem,
        raw_calculation_dem,
        valid_mask,
        x_resolution=x_resolution,
        y_resolution=y_resolution,
    )
    warnings.extend(_terrain_signal_warnings(derivatives, valid_mask))

    raster_profile = _single_band_profile(profile, output_nodata)
    conditioned_path = raster_dir / CONDITIONED_DEM_FILENAME
    conditioned_tags = {
        "source_product": "dem_clipped",
        "conditioning_status": conditioning_status,
        "advisory_warning": ADVISORY_HYDROLOGY_WARNING,
    }
    if conditioning_backend:
        conditioned_tags["conditioning_backend"] = conditioning_backend
    write_raster_atomic(
        conditioned_path,
        _raster_band(conditioned_dem, valid_mask, output_nodata),
        raster_profile,
        tags=conditioned_tags,
    )
    conditioned_preview = _write_preview(
        conditioned_dem,
        valid_mask,
        preview_output_dir / "dem_conditioned.png",
        title="Conditioned DEM",
        write_preview=write_previews,
    )
    conditioned_record = _product_record(
        "dem_conditioned",
        conditioned_path,
        conditioned_preview,
        conditioned_dem,
        valid_mask,
        output_nodata,
        profile,
        unit="meters",
        source_product="dem_clipped",
        warnings=tuple(warnings),
    )

    product_records: list[TerrainProductRecord] = []
    for filename in DERIVED_RASTER_FILENAMES:
        product_name = filename.removesuffix(".tif")
        array = derivatives[product_name]
        product_path = raster_dir / filename
        product_tags = {
            "source_product": "dem_conditioned" if conditioning_status != CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE else "dem_clipped",
            "conditioning_status": conditioning_status,
            "advisory_warning": ADVISORY_HYDROLOGY_WARNING,
        }
        write_raster_atomic(
            product_path,
            _raster_band(array, valid_mask, output_nodata),
            raster_profile,
            tags=product_tags,
        )
        preview_path = _write_preview(
            array,
            valid_mask,
            preview_output_dir / f"{product_name}.png",
            title=product_name.replace("_", " ").title(),
            write_preview=write_previews,
        )
        product_records.append(
            _product_record(
                product_name,
                product_path,
                preview_path,
                array,
                valid_mask,
                output_nodata,
                profile,
                unit=_DERIVED_UNITS[product_name],
                source_product=product_tags["source_product"],
                warnings=tuple(warnings),
            )
        )

    summary = _summary_record(
        dem_path=dem_path,
        conditioned_path=conditioned_path,
        profile=profile,
        dem=dem,
        valid_mask=valid_mask,
        derivatives=derivatives,
        conditioning_status=conditioning_status,
        conditioning_backend=conditioning_backend,
        quality_warnings=tuple(warnings),
        cell_area=cell_area,
        products=tuple(product_records),
    )
    _write_summary_json(json_output_path, summary)
    _write_summary_csv(csv_output_path, summary)

    return TerrainDerivativeResult(
        dem_clipped_path=str(dem_path),
        output_dir=str(raster_dir),
        conditioning_status=conditioning_status,
        conditioning_backend=conditioning_backend,
        conditioned_dem=conditioned_record,
        products=tuple(product_records),
        summary_json_path=str(json_output_path),
        summary_csv_path=str(csv_output_path),
        quality_warnings=tuple(warnings),
    )


def _read_dem(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any], float | int | None]:
    with rasterio.open(path) as src:
        masked = src.read(1, masked=True).astype("float32")
        profile = src.profile.copy()
        nodata = src.nodata
    data = np.asarray(masked.filled(np.nan), dtype="float32")
    mask = np.asarray(np.ma.getmaskarray(masked), dtype=bool)
    valid = ~mask & np.isfinite(data)
    return data, valid, profile, nodata


def _validate_local_path(path: str | Path, *, role: str) -> Path:
    raw = os.fspath(path)
    normalized = raw.replace("\\", "/").casefold()
    if "://" in normalized or normalized.startswith("/vsi") or normalized.startswith("vsi"):
        raise ValueError(f"{role} must be a local filesystem path, not a URL or GDAL VSI path: {raw}")
    return Path(path)


def _reject_symlink_output(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink output: {path}")


def _output_nodata(source_nodata: float | int | None) -> float | int:
    if source_nodata is None:
        return DEFAULT_NODATA
    if isinstance(source_nodata, float) and math.isnan(source_nodata):
        return DEFAULT_NODATA
    return source_nodata


def _base_quality_warnings(profile: Mapping[str, Any], valid_mask: np.ndarray) -> list[dict[str, str]]:
    warnings = [
        {
            "code": "advisory_hydrology_proxy",
            "severity": "info",
            "message": ADVISORY_HYDROLOGY_WARNING,
        }
    ]
    crs = profile.get("crs")
    if crs is None:
        warnings.append(
            {
                "code": "missing_crs",
                "severity": "warning",
                "message": "DEM has no CRS; resolution and area summaries use raster units.",
            }
        )
    elif getattr(crs, "is_geographic", False):
        warnings.append(
            {
                "code": "geographic_crs_area_units",
                "severity": "warning",
                "message": "DEM CRS is geographic; terrain derivatives are safest in a projected metric CRS.",
            }
        )
    valid_count = int(np.count_nonzero(valid_mask))
    if valid_count == 0:
        warnings.append(
            {
                "code": "no_valid_dem_cells",
                "severity": "error",
                "message": "DEM contains no finite valid cells; derived rasters are nodata.",
            }
        )
    elif valid_count < valid_mask.size * 0.25:
        warnings.append(
            {
                "code": "nodata_heavy_dem",
                "severity": "warning",
                "message": "DEM has fewer than 25 percent valid cells; derivative summaries may be sparse.",
            }
        )
    return warnings


def _condition_dem(
    dem: np.ndarray,
    valid_mask: np.ndarray,
) -> tuple[np.ndarray, str, str | None, tuple[dict[str, str], ...]]:
    if not np.any(valid_mask):
        return dem.copy(), CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE, None, (
            {
                "code": "conditioning_skipped_no_valid_cells",
                "severity": "warning",
                "message": "Hydrologic conditioning skipped because the DEM has no valid cells.",
            },
        )

    try:
        import richdem as rd  # type: ignore[import-not-found]
    except Exception:
        return dem.copy(), CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE, None, (
            {
                "code": "conditioning_backend_unavailable",
                "severity": "warning",
                "message": "Optional breach/fill backend unavailable; hydrology outputs use unconditioned DEM values.",
            },
        )

    try:
        filled_input = _filled_for_calculation(dem, valid_mask).astype("float64")
        rd_array = rd.rdarray(filled_input, no_data=np.nan)
        conditioned = np.asarray(rd.FillDepressions(rd_array, epsilon=True, in_place=False), dtype="float32")
        conditioned[~valid_mask] = np.nan
        return conditioned, CONDITIONING_RICHDEM_FILL, "richdem", ()
    except Exception as exc:  # pragma: no cover - depends on optional backend behavior
        return dem.copy(), CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE, "richdem", (
            {
                "code": "conditioning_backend_failed",
                "severity": "warning",
                "message": f"Optional richdem conditioning failed; hydrology outputs use unconditioned DEM values: {exc}",
            },
        )


def _compute_derivatives(
    dem: np.ndarray,
    raw_dem: np.ndarray,
    valid_mask: np.ndarray,
    *,
    x_resolution: float,
    y_resolution: float,
) -> dict[str, np.ndarray]:
    empty = np.full(dem.shape, np.nan, dtype="float32")
    if not np.any(valid_mask):
        return {name.removesuffix(".tif"): empty.copy() for name in DERIVED_RASTER_FILENAMES}

    dz_drow, dz_dx = np.gradient(dem.astype("float64"), y_resolution, x_resolution)
    dz_dy = -dz_drow
    gradient_magnitude = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_radians = np.arctan(gradient_magnitude)
    slope_degrees = np.degrees(slope_radians)
    slope_percent = np.tan(slope_radians) * 100.0
    aspect = (np.degrees(np.arctan2(dz_dx, dz_dy)) + 180.0) % 360.0
    aspect = np.where(gradient_magnitude <= _EPSILON, -1.0, aspect)

    hillshade = _hillshade(dz_dx, dz_dy, slope_radians)
    profile_curvature, planform_curvature = _curvatures(dem, x_resolution, y_resolution)
    tpi, tri = _position_and_roughness(dem, valid_mask)
    flow_direction = _flow_direction(dem, valid_mask, x_resolution, y_resolution)
    flow_accumulation = _flow_accumulation(flow_direction, valid_mask)
    twi = _topographic_wetness_index(flow_accumulation, slope_radians, x_resolution, y_resolution)
    depression_depth = np.maximum(dem - raw_dem, 0.0)
    relative_elevation = dem - float(np.nanmin(dem[valid_mask]))
    erosion_proxy = _erosion_proxy(slope_percent, flow_accumulation, valid_mask)

    derivatives = {
        "slope_degrees": slope_degrees,
        "slope_percent": slope_percent,
        "aspect_degrees": aspect,
        "hillshade": hillshade,
        "profile_curvature": profile_curvature,
        "planform_curvature": planform_curvature,
        "tpi": tpi,
        "tri": tri,
        "flow_direction": flow_direction,
        "flow_accumulation": flow_accumulation,
        "topographic_wetness_index": twi,
        "depression_depth": depression_depth,
        "relative_elevation": relative_elevation,
        "erosion_proxy": erosion_proxy,
    }
    return {name: _masked_float(array, valid_mask) for name, array in derivatives.items()}


def _hillshade(dz_dx: np.ndarray, dz_dy: np.ndarray, slope_radians: np.ndarray) -> np.ndarray:
    azimuth = math.radians(315.0)
    altitude = math.radians(45.0)
    aspect = np.arctan2(dz_dx, dz_dy)
    shaded = 255.0 * (
        np.cos(altitude) * np.cos(slope_radians)
        + np.sin(altitude) * np.sin(slope_radians) * np.cos(azimuth - aspect)
    )
    return np.clip(shaded, 0.0, 255.0)


def _curvatures(dem: np.ndarray, x_resolution: float, y_resolution: float) -> tuple[np.ndarray, np.ndarray]:
    dz_drow, dz_dx = np.gradient(dem.astype("float64"), y_resolution, x_resolution)
    dz_dy = -dz_drow
    _, zxx = np.gradient(dz_dx, y_resolution, x_resolution)
    zyy_row, _ = np.gradient(dz_dy, y_resolution, x_resolution)
    zyy = -zyy_row
    zxy_row, _ = np.gradient(dz_dx, y_resolution, x_resolution)
    zxy = -zxy_row
    p = dz_dx**2 + dz_dy**2
    profile_denominator = np.maximum(p * np.sqrt(p), _EPSILON)
    plan_denominator = np.maximum(np.power(p, 1.5), _EPSILON)
    profile = -((zxx * dz_dx**2) + (2.0 * zxy * dz_dx * dz_dy) + (zyy * dz_dy**2)) / profile_denominator
    planform = ((zxx * dz_dy**2) - (2.0 * zxy * dz_dx * dz_dy) + (zyy * dz_dx**2)) / plan_denominator
    profile = np.where(p <= _EPSILON, 0.0, profile)
    planform = np.where(p <= _EPSILON, 0.0, planform)
    return profile, planform


def _position_and_roughness(dem: np.ndarray, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    neighbors = [_shift(dem, row_delta, col_delta, np.nan) for row_delta, col_delta, _, _ in _D8_NEIGHBORS]
    neighbor_valid = [
        _shift(valid_mask.astype("float32"), row_delta, col_delta, 0.0) > 0.5
        for row_delta, col_delta, _, _ in _D8_NEIGHBORS
    ]
    stack = np.stack(neighbors)
    valid_stack = np.stack(neighbor_valid)
    finite_stack = np.isfinite(stack) & valid_stack & np.expand_dims(valid_mask, axis=0)
    counts = np.count_nonzero(finite_stack, axis=0)
    sums = np.nansum(np.where(finite_stack, stack, np.nan), axis=0)
    mean = np.divide(sums, counts, out=np.full(dem.shape, np.nan), where=counts > 0)
    tpi = dem - mean
    differences = np.where(finite_stack, stack - dem, np.nan)
    tri = np.sqrt(
        np.divide(
            np.nansum(differences**2, axis=0),
            counts,
            out=np.zeros(dem.shape, dtype="float64"),
            where=counts > 0,
        )
    )
    return tpi, tri


def _flow_direction(
    dem: np.ndarray,
    valid_mask: np.ndarray,
    x_resolution: float,
    y_resolution: float,
) -> np.ndarray:
    best_drop = np.zeros(dem.shape, dtype="float64")
    direction = np.zeros(dem.shape, dtype="float32")
    for row_delta, col_delta, code, distance_factor in _D8_NEIGHBORS:
        distance = math.hypot(x_resolution * abs(col_delta), y_resolution * abs(row_delta))
        if distance == 0.0:
            distance = min(x_resolution, y_resolution) * distance_factor
        neighbor = _shift(dem, -row_delta, -col_delta, np.nan)
        neighbor_valid = _shift(valid_mask.astype("float32"), -row_delta, -col_delta, 0.0) > 0.5
        drop = (dem - neighbor) / distance
        candidate = valid_mask & neighbor_valid & np.isfinite(drop) & (drop > best_drop) & (drop > 0.0)
        direction[candidate] = float(code)
        best_drop[candidate] = drop[candidate]
    direction[~valid_mask] = np.nan
    return direction


def _flow_accumulation(flow_direction: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    height, width = flow_direction.shape
    total = height * width
    receiver = np.full(total, -1, dtype="int64")
    indegree = np.zeros(total, dtype="int64")
    flat_direction = np.nan_to_num(flow_direction, nan=0.0).astype("int64", copy=False)

    for row in range(height):
        for col in range(width):
            if not valid_mask[row, col]:
                continue
            code = int(flat_direction[row, col])
            offset = _CODE_TO_OFFSET.get(code)
            if offset is None:
                continue
            target_row = row + offset[0]
            target_col = col + offset[1]
            if 0 <= target_row < height and 0 <= target_col < width and valid_mask[target_row, target_col]:
                source_index = row * width + col
                target_index = target_row * width + target_col
                receiver[source_index] = target_index
                indegree[target_index] += 1

    accumulation = np.where(valid_mask.ravel(), 1.0, 0.0).astype("float64")
    queue = [index for index in range(total) if valid_mask.ravel()[index] and indegree[index] == 0]
    cursor = 0
    while cursor < len(queue):
        index = queue[cursor]
        cursor += 1
        target = receiver[index]
        if target >= 0:
            accumulation[target] += accumulation[index]
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))

    result = accumulation.reshape((height, width))
    result[~valid_mask] = np.nan
    return result


def _topographic_wetness_index(
    accumulation: np.ndarray,
    slope_radians: np.ndarray,
    x_resolution: float,
    y_resolution: float,
) -> np.ndarray:
    contour_width = max(min(x_resolution, y_resolution), _EPSILON)
    specific_area = np.maximum(accumulation * x_resolution * y_resolution / contour_width, _EPSILON)
    tangent = np.maximum(np.tan(slope_radians), 0.001)
    twi = np.log(specific_area / tangent)
    return np.clip(twi, -20.0, 20.0)


def _erosion_proxy(slope_percent: np.ndarray, flow_accumulation: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    slope_component = _normalize_positive(slope_percent, valid_mask)
    flow_component = _normalize_positive(np.log1p(flow_accumulation), valid_mask)
    return slope_component * flow_component


def _normalize_positive(array: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    values = np.asarray(array, dtype="float64")
    finite = valid_mask & np.isfinite(values)
    normalized = np.zeros(values.shape, dtype="float64")
    if not np.any(finite):
        normalized[~valid_mask] = np.nan
        return normalized
    min_value = float(np.nanmin(values[finite]))
    max_value = float(np.nanmax(values[finite]))
    if math.isclose(max_value, min_value):
        normalized[finite] = 0.0
    else:
        normalized[finite] = (values[finite] - min_value) / (max_value - min_value)
    normalized[~valid_mask] = np.nan
    return normalized


def _filled_for_calculation(data: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    if not np.any(valid_mask):
        return np.zeros(data.shape, dtype="float32")
    if np.all(valid_mask):
        return data.astype("float32", copy=True)
    try:
        from scipy import ndimage  # type: ignore[import-not-found]

        nearest_indices = ndimage.distance_transform_edt(
            ~valid_mask,
            return_distances=False,
            return_indices=True,
        )
        indices = cast(np.ndarray, nearest_indices)
        filled = data[tuple(np.asarray(axis, dtype=np.intp) for axis in indices)]
    except Exception:
        fill_value = float(np.nanmean(data[valid_mask]))
        filled = np.where(valid_mask, data, fill_value)
    return np.asarray(filled, dtype="float32")


def _shift(array: np.ndarray, row_delta: int, col_delta: int, fill_value: float) -> np.ndarray:
    shifted = np.full(array.shape, fill_value, dtype=np.asarray(array).dtype)
    source_rows, destination_rows = _slice_for_shift(array.shape[0], row_delta)
    source_cols, destination_cols = _slice_for_shift(array.shape[1], col_delta)
    shifted[destination_rows, destination_cols] = array[source_rows, source_cols]
    return shifted


def _slice_for_shift(size: int, delta: int) -> tuple[slice, slice]:
    if delta > 0:
        return slice(0, size - delta), slice(delta, size)
    if delta < 0:
        return slice(-delta, size), slice(0, size + delta)
    return slice(0, size), slice(0, size)


def _masked_float(array: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    output = np.asarray(array, dtype="float32")
    output = np.where(valid_mask & np.isfinite(output), output, np.nan).astype("float32")
    return output


def _single_band_profile(source_profile: Mapping[str, Any], nodata: float | int) -> dict[str, Any]:
    profile = dict(source_profile)
    blockxsize = 16 if int(profile.get("width", 16)) < 256 else 256
    blockysize = 16 if int(profile.get("height", 16)) < 256 else 256
    profile.update(
        {
            "driver": "GTiff",
            "count": 1,
            "dtype": "float32",
            "nodata": nodata,
            "compress": "deflate",
            "predictor": 3,
            "tiled": True,
            "blockxsize": blockxsize,
            "blockysize": blockysize,
            "interleave": "band",
        }
    )
    return profile


def _terrain_signal_warnings(
    derivatives: Mapping[str, np.ndarray],
    valid_mask: np.ndarray,
) -> tuple[dict[str, str], ...]:
    if not np.any(valid_mask):
        return ()
    slope = derivatives["slope_percent"]
    flow_direction = derivatives["flow_direction"]
    finite_slope = valid_mask & np.isfinite(slope)
    finite_flow = valid_mask & np.isfinite(flow_direction)
    max_slope = float(np.nanmax(slope[finite_slope])) if np.any(finite_slope) else 0.0
    routed_cells = int(np.count_nonzero(finite_flow & (flow_direction > 0.0)))
    if max_slope <= 0.1 or routed_cells == 0:
        return (
            {
                "code": "flat_or_near_flat_terrain_limited_flow_proxy_signal",
                "severity": "warning",
                "message": FLAT_TERRAIN_LIMITED_FLOW_WARNING,
            },
        )
    return ()


def _raster_band(array: np.ndarray, valid_mask: np.ndarray, nodata: float | int) -> np.ndarray:
    band = np.where(valid_mask & np.isfinite(array), array, nodata).astype("float32")
    return band.reshape((1, band.shape[0], band.shape[1]))


def _write_preview(
    array: np.ndarray,
    valid_mask: np.ndarray,
    output_path: Path,
    *,
    title: str,
    write_preview: bool,
) -> str | None:
    if not write_preview:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    output_path = _validate_local_path(output_path, role="preview_output_path")
    _reject_symlink_output(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    display = np.ma.masked_invalid(np.where(valid_mask, array, np.nan))
    fig, ax = plt.subplots(figsize=(5, 4))
    image = ax.imshow(display, cmap="viridis")
    ax.set_title(title)
    ax.axis("off")
    fig.colorbar(image, ax=ax, shrink=0.78)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".part.png",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        fig.savefig(temp_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        os.replace(temp_path, output_path)
    finally:
        plt.close(fig)
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return str(output_path)


def _product_record(
    product_name: str,
    path: Path,
    preview_path: str | None,
    array: np.ndarray,
    valid_mask: np.ndarray,
    nodata: float | int,
    profile: Mapping[str, Any],
    *,
    unit: str,
    source_product: str,
    warnings: tuple[dict[str, str], ...],
) -> TerrainProductRecord:
    transform = profile["transform"]
    raster_band = _raster_band(array, valid_mask, nodata)
    return TerrainProductRecord(
        product_name=product_name,
        filename=path.name,
        path=str(path),
        preview_path=preview_path,
        unit=unit,
        source_product=source_product,
        advisory=product_name in _DERIVED_UNITS,
        nodata=nodata,
        dtype="float32",
        width=int(profile["width"]),
        height=int(profile["height"]),
        resolution=(abs(float(transform.a)), abs(float(transform.e))),
        nodata_ratio=nodata_ratio(raster_band, nodata),
        checksum_sha256=sha256_file(path),
        file_size=file_size(path),
        statistics=_statistics(array, valid_mask),
        warnings=warnings,
    )


def _statistics(array: np.ndarray, valid_mask: np.ndarray) -> dict[str, float | None]:
    finite = valid_mask & np.isfinite(array)
    if not np.any(finite):
        return {"min": None, "max": None, "mean": None, "p05": None, "p50": None, "p95": None}
    values = array[finite].astype("float64")
    percentiles = np.nanpercentile(values, [5, 50, 95])
    return {
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        "mean": float(np.nanmean(values)),
        "p05": float(percentiles[0]),
        "p50": float(percentiles[1]),
        "p95": float(percentiles[2]),
    }


def _summary_record(
    *,
    dem_path: Path,
    conditioned_path: Path,
    profile: Mapping[str, Any],
    dem: np.ndarray,
    valid_mask: np.ndarray,
    derivatives: Mapping[str, np.ndarray],
    conditioning_status: str,
    conditioning_backend: str | None,
    quality_warnings: tuple[dict[str, str], ...],
    cell_area: float,
    products: tuple[TerrainProductRecord, ...],
) -> dict[str, Any]:
    valid_elevation = dem[valid_mask & np.isfinite(dem)]
    if valid_elevation.size:
        elevation_min = float(np.nanmin(valid_elevation))
        elevation_max = float(np.nanmax(valid_elevation))
    else:
        elevation_min = None
        elevation_max = None
    slope_percentiles = _named_percentiles(derivatives["slope_percent"], valid_mask, (5, 50, 75, 90, 95))
    ponding_risk_area = _ponding_risk_area(
        derivatives["depression_depth"],
        derivatives["topographic_wetness_index"],
        derivatives["slope_percent"],
        valid_mask,
        cell_area,
    )
    erosion_proxy_area = _erosion_proxy_area(
        derivatives["erosion_proxy"],
        derivatives["slope_percent"],
        valid_mask,
        cell_area,
    )
    transform = profile["transform"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dem_clipped": str(dem_path),
        "dem_conditioned": str(conditioned_path),
        "conditioning_status": conditioning_status,
        "conditioning_backend": conditioning_backend,
        "advisory_label": ADVISORY_HYDROLOGY_WARNING,
        "analysis_crs": str(profile.get("crs")),
        "width": int(profile["width"]),
        "height": int(profile["height"]),
        "resolution": [abs(float(transform.a)), abs(float(transform.e))],
        "valid_cell_count": int(np.count_nonzero(valid_mask)),
        "nodata_cell_count": int(valid_mask.size - np.count_nonzero(valid_mask)),
        "cell_area": float(cell_area),
        "slope_percentiles": slope_percentiles,
        "elevation_range_m": {
            "min": elevation_min,
            "max": elevation_max,
            "range": None if elevation_min is None or elevation_max is None else float(elevation_max - elevation_min),
        },
        "ponding_risk_area": ponding_risk_area,
        "erosion_proxy_area": erosion_proxy_area,
        "quality_warnings": list(quality_warnings),
        "products": [product.to_dict() for product in products],
    }


def _named_percentiles(
    array: np.ndarray,
    valid_mask: np.ndarray,
    percentiles: Iterable[int],
) -> dict[str, float | None]:
    finite = valid_mask & np.isfinite(array)
    if not np.any(finite):
        return {f"p{percentile:02d}": None for percentile in percentiles}
    values = array[finite].astype("float64")
    calculated = np.nanpercentile(values, list(percentiles))
    return {f"p{percentile:02d}": float(value) for percentile, value in zip(percentiles, calculated)}


def _ponding_risk_area(
    depression_depth: np.ndarray,
    twi: np.ndarray,
    slope_percent: np.ndarray,
    valid_mask: np.ndarray,
    cell_area: float,
) -> dict[str, float | int | None]:
    finite_twi = valid_mask & np.isfinite(twi)
    twi_threshold = float(np.nanpercentile(twi[finite_twi], 90)) if np.any(finite_twi) else None
    depression_candidate = valid_mask & np.isfinite(depression_depth) & (depression_depth > 0.05)
    wet_flat_candidate = np.zeros(valid_mask.shape, dtype=bool)
    if twi_threshold is not None:
        wet_flat_candidate = valid_mask & np.isfinite(twi) & np.isfinite(slope_percent) & (twi >= twi_threshold) & (slope_percent <= 2.0)
    risk = depression_candidate | wet_flat_candidate
    cells = int(np.count_nonzero(risk))
    return {
        "cell_count": cells,
        "area_square_map_units": float(cells * cell_area),
        "depression_depth_threshold_m": 0.05,
        "twi_percentile_threshold": twi_threshold,
    }


def _erosion_proxy_area(
    erosion_proxy: np.ndarray,
    slope_percent: np.ndarray,
    valid_mask: np.ndarray,
    cell_area: float,
) -> dict[str, float | int | None]:
    finite = valid_mask & np.isfinite(erosion_proxy)
    if not np.any(finite):
        return {"cell_count": 0, "area_square_map_units": 0.0, "erosion_proxy_threshold": None}
    threshold = float(np.nanpercentile(erosion_proxy[finite], 90))
    risk = finite & (erosion_proxy >= threshold) & np.isfinite(slope_percent) & (slope_percent >= 5.0)
    cells = int(np.count_nonzero(risk))
    return {
        "cell_count": cells,
        "area_square_map_units": float(cells * cell_area),
        "erosion_proxy_threshold": threshold,
    }


def _write_summary_json(path: Path, summary: Mapping[str, Any]) -> None:
    path = _validate_local_path(path, role="summary_json_path")
    _reject_symlink_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(path, payload)


def _write_summary_csv(path: Path, summary: Mapping[str, Any]) -> None:
    path = _validate_local_path(path, role="summary_csv_path")
    _reject_symlink_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    elevation = summary["elevation_range_m"]
    slope = summary["slope_percentiles"]
    ponding = summary["ponding_risk_area"]
    erosion = summary["erosion_proxy_area"]
    row = {
        "dem_clipped": summary["dem_clipped"],
        "dem_conditioned": summary["dem_conditioned"],
        "conditioning_status": summary["conditioning_status"],
        "conditioning_backend": summary["conditioning_backend"] or "",
        "elevation_min_m": elevation["min"],
        "elevation_max_m": elevation["max"],
        "elevation_range_m": elevation["range"],
        "slope_percent_p05": slope["p05"],
        "slope_percent_p50": slope["p50"],
        "slope_percent_p95": slope["p95"],
        "ponding_risk_area": ponding["area_square_map_units"],
        "erosion_proxy_area": erosion["area_square_map_units"],
        "quality_warning_count": len(summary["quality_warnings"]),
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".part",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def _write_text_atomic(path: Path, payload: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".part",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


__all__ = [
    "ADVISORY_HYDROLOGY_WARNING",
    "CONDITIONING_RICHDEM_FILL",
    "CONDITIONING_SKIPPED_BACKEND_UNAVAILABLE",
    "FLAT_TERRAIN_LIMITED_FLOW_WARNING",
    "TerrainDerivativeResult",
    "TerrainProductRecord",
    "derive_terrain_products",
]
