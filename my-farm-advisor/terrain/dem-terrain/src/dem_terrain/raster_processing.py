"""Raster clipping, CRS selection, COG-style output, and cache primitives.

These helpers operate on local DEM raster paths or already-readable raster hrefs.
They do not discover providers, download DEMs, or write runtime manifests. Field
geometries are projected to a local metric CRS before meter buffering, then the
source rasters are mosaicked in source CRS and reprojected once to the analysis
CRS for downstream terrain derivatives.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, cast

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


DEFAULT_FIELD_CRS = "EPSG:4326"
DEFAULT_BUFFER_METERS = 20.0
DEFAULT_NODATA = -9999.0
POLAR_NORTH_EPSG = 3413
POLAR_SOUTH_EPSG = 3031


@dataclass(frozen=True, slots=True)
class AnalysisGeometry:
    """Field and buffer geometry prepared in the local analysis CRS."""

    field_crs: str
    analysis_crs: str
    analysis_epsg: int | None
    buffer_meters: float
    field_bounds_wgs84: tuple[float, float, float, float]
    field_bounds_analysis: tuple[float, float, float, float]
    buffered_bounds_analysis: tuple[float, float, float, float]
    centroid_lonlat: tuple[float, float]
    field_geometry_analysis: BaseGeometry
    buffered_geometry_analysis: BaseGeometry
    warnings: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-friendly summary without embedding full geometry objects."""

        return {
            "field_crs": self.field_crs,
            "analysis_crs": self.analysis_crs,
            "analysis_epsg": self.analysis_epsg,
            "buffer_meters": self.buffer_meters,
            "field_bounds_wgs84": self.field_bounds_wgs84,
            "field_bounds_analysis": self.field_bounds_analysis,
            "buffered_bounds_analysis": self.buffered_bounds_analysis,
            "centroid_lonlat": self.centroid_lonlat,
            "warnings": self.warnings,
        }


@dataclass(frozen=True, slots=True)
class RasterOutputRecord:
    """Serializable metadata for one clipped DEM output."""

    path: str
    analysis_crs: str
    source_crs: str
    bounds: tuple[float, float, float, float]
    width: int
    height: int
    count: int
    dtype: str
    buffer_meters: float
    nodata: float | int | None
    checksum_sha256: str
    file_size: int
    source_paths: tuple[str, ...]
    source_bounds: tuple[float, float, float, float]
    nodata_ratio: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


def utm_crs_for_lonlat(lon: float, lat: float) -> tuple[CRS, tuple[str, ...]]:
    """Return a local projected CRS for a lon/lat point.

    UTM EPSG zones are used for latitudes where UTM is defined. For high-latitude
    polar fields, this returns standard polar stereographic fallbacks with an
    explicit warning instead of silently guessing a UTM zone outside its valid
    range.
    """

    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError("Longitude and latitude must be finite numbers")
    if lat > 84.0:
        return CRS.from_epsg(POLAR_NORTH_EPSG), (
            "analysis_crs_fallback=EPSG:3413 for latitude north of UTM valid range",
        )
    if lat < -80.0:
        return CRS.from_epsg(POLAR_SOUTH_EPSG), (
            "analysis_crs_fallback=EPSG:3031 for latitude south of UTM valid range",
        )

    normalized_lon = ((lon + 180.0) % 360.0) - 180.0
    zone = int((normalized_lon + 180.0) // 6.0) + 1
    zone = min(max(zone, 1), 60)
    epsg = (32600 if lat >= 0.0 else 32700) + zone
    return CRS.from_epsg(epsg), ()


def prepare_analysis_geometry(
    field_geometry: BaseGeometry | dict[str, Any],
    *,
    field_crs: str | CRS = DEFAULT_FIELD_CRS,
    buffer_meters: float = DEFAULT_BUFFER_METERS,
) -> AnalysisGeometry:
    """Project a field to local metric CRS and buffer by meters.

    This function never buffers in EPSG:4326 degrees. It first computes the field
    centroid in WGS84 for CRS selection, projects the field to the chosen metric
    CRS, and only then applies the meter buffer.
    """

    if buffer_meters < 0:
        raise ValueError("buffer_meters must be non-negative")

    geometry = _coerce_geometry(field_geometry)
    if geometry.is_empty:
        raise ValueError("field_geometry must not be empty")

    field_crs_obj = CRS.from_user_input(field_crs)
    field_series = gpd.GeoSeries([geometry], crs=field_crs_obj)
    field_wgs84 = field_series.to_crs(DEFAULT_FIELD_CRS)
    centroid = field_wgs84.iloc[0].centroid
    analysis_crs, warnings = utm_crs_for_lonlat(float(centroid.x), float(centroid.y))
    field_analysis = field_series.to_crs(analysis_crs).iloc[0]
    buffered = field_analysis.buffer(buffer_meters)

    return AnalysisGeometry(
        field_crs=field_crs_obj.to_string(),
        analysis_crs=analysis_crs.to_string(),
        analysis_epsg=analysis_crs.to_epsg(),
        buffer_meters=float(buffer_meters),
        field_bounds_wgs84=_bounds_tuple(field_wgs84.iloc[0].bounds),
        field_bounds_analysis=_bounds_tuple(field_analysis.bounds),
        buffered_bounds_analysis=_bounds_tuple(buffered.bounds),
        centroid_lonlat=(float(centroid.x), float(centroid.y)),
        field_geometry_analysis=field_analysis,
        buffered_geometry_analysis=buffered,
        warnings=warnings,
    )


def transform_buffered_bounds_to_source_crs(
    analysis_geometry: AnalysisGeometry,
    source_crs: str | CRS,
) -> tuple[float, float, float, float]:
    """Transform buffered analysis bounds to a source raster CRS."""

    return _bounds_tuple(
        transform_bounds(
            analysis_geometry.analysis_crs,
            CRS.from_user_input(source_crs),
            *analysis_geometry.buffered_bounds_analysis,
            densify_pts=21,
        )
    )


def clip_dem_tiles_to_buffer(
    source_paths: Sequence[str | Path],
    field_geometry: BaseGeometry | dict[str, Any],
    output_path: str | Path,
    *,
    field_crs: str | CRS = DEFAULT_FIELD_CRS,
    buffer_meters: float = DEFAULT_BUFFER_METERS,
    nodata: float | int | None = None,
    source_vertical_datum: str | None = None,
    target_vertical_datum: str | None = None,
    resampling: Resampling = Resampling.bilinear,
    compress: str = "deflate",
) -> RasterOutputRecord:
    """Mosaic source DEM tiles, clip to a metric buffer, and write one GeoTIFF.

    The source rasters are mosaicked in the first tile's CRS using the buffered
    field bounds transformed into that source CRS. The clipped mosaic is then
    reprojected once to the analysis CRS selected from the field centroid.
    """

    if not source_paths:
        raise ValueError("At least one source raster path is required")

    analysis = prepare_analysis_geometry(
        field_geometry,
        field_crs=field_crs,
        buffer_meters=buffer_meters,
    )
    output = Path(output_path)
    source_names = tuple(str(path) for path in source_paths)
    datasets = [rasterio.open(path) for path in source_paths]
    try:
        source_crs = datasets[0].crs
        if source_crs is None:
            raise ValueError(f"Source raster has no CRS: {source_names[0]}")
        for dataset, name in zip(datasets[1:], source_names[1:]):
            if dataset.crs != source_crs:
                raise ValueError(
                    "All source rasters must share one source CRS before mosaicking; "
                    f"{name} has {dataset.crs}, expected {source_crs}"
                )

        resolved_nodata = _resolve_nodata(datasets, nodata)
        output_dtype = _compatible_dtype(datasets[0].dtypes[0], resolved_nodata)
        source_bounds = transform_buffered_bounds_to_source_crs(analysis, source_crs)
        mosaic_array, mosaic_transform = merge(
            datasets,
            bounds=source_bounds,
            nodata=resolved_nodata,
            dtype=output_dtype,
        )

        buffered_source = _geometry_to_crs(
            analysis.buffered_geometry_analysis,
            analysis.analysis_crs,
            source_crs,
        )
        clipped_array = _mask_array_to_geometry(
            mosaic_array,
            mosaic_transform,
            buffered_source,
            resolved_nodata,
        )

        destination_array, destination_transform = _reproject_array(
            clipped_array,
            mosaic_transform,
            source_crs,
            analysis.analysis_crs,
            resolved_nodata,
            resampling,
        )
        destination_array = _mask_array_to_geometry(
            destination_array,
            destination_transform,
            analysis.buffered_geometry_analysis,
            resolved_nodata,
        )

        warnings = list(analysis.warnings)
        warning = vertical_datum_warning(source_vertical_datum, target_vertical_datum)
        if warning:
            warnings.append(warning)

        profile = _output_profile(
            datasets[0].profile,
            destination_array,
            destination_transform,
            analysis.analysis_crs,
            resolved_nodata,
            output_dtype,
            compress,
        )
        tags = _vertical_datum_tags(source_vertical_datum, target_vertical_datum, warning)
        write_raster_atomic(output, destination_array, profile, tags=tags)

        return RasterOutputRecord(
            path=str(output),
            analysis_crs=analysis.analysis_crs,
            source_crs=source_crs.to_string(),
            bounds=_bounds_from_transform(destination_transform, destination_array.shape[2], destination_array.shape[1]),
            width=int(destination_array.shape[2]),
            height=int(destination_array.shape[1]),
            count=int(destination_array.shape[0]),
            dtype=str(destination_array.dtype),
            buffer_meters=float(buffer_meters),
            nodata=resolved_nodata,
            checksum_sha256=sha256_file(output),
            file_size=file_size(output),
            source_paths=source_names,
            source_bounds=_bounds_tuple(source_bounds),
            nodata_ratio=nodata_ratio(destination_array, resolved_nodata),
            warnings=tuple(dict.fromkeys(warnings)),
        )
    finally:
        for dataset in datasets:
            dataset.close()


def write_raster_atomic(
    output_path: str | Path,
    array: np.ndarray,
    profile: dict[str, Any],
    *,
    tags: dict[str, str] | None = None,
) -> Path:
    """Write a raster through a temporary sibling and atomically replace target."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink raster output: {output}")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",
            suffix=".part",
            dir=output.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        with rasterio.open(temp_path, "w", **profile) as dst:
            dst.write(array)
            if tags:
                dst.update_tags(**tags)
        os.replace(temp_path, output)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise
    return output


def sha256_file(path: str | Path) -> str:
    """Return the SHA256 checksum for a file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_size(path: str | Path) -> int:
    """Return file size in bytes."""

    return Path(path).stat().st_size


def nodata_ratio(array: np.ndarray, nodata: float | int | None) -> float:
    """Return the fraction of raster cells that are nodata across all bands."""

    if array.size == 0:
        return 0.0
    if nodata is None:
        if np.issubdtype(array.dtype, np.floating):
            mask = np.isnan(array)
        else:
            return 0.0
    elif isinstance(nodata, float) and math.isnan(nodata):
        mask = np.isnan(array)
    else:
        mask = array == nodata
    return float(np.count_nonzero(mask) / array.size)


def vertical_datum_warning(source_vertical_datum: str | None, target_vertical_datum: str | None) -> str | None:
    """Return a metadata warning for differing vertical datums without transforming."""

    source = (source_vertical_datum or "").strip()
    target = (target_vertical_datum or "").strip()
    if not source or not target or source.casefold() == target.casefold():
        return None
    return (
        "vertical_datum_mismatch_no_transform="
        f"source:{source};target:{target};v1 preserves elevations without vertical transform"
    )


def _coerce_geometry(geometry: BaseGeometry | dict[str, Any]) -> BaseGeometry:
    if isinstance(geometry, BaseGeometry):
        return geometry
    if isinstance(geometry, dict):
        return shape(geometry)
    raise TypeError("field_geometry must be a Shapely geometry or GeoJSON-like dict")


def _bounds_tuple(bounds: Iterable[float]) -> tuple[float, float, float, float]:
    left, bottom, right, top = bounds
    return (float(left), float(bottom), float(right), float(top))


def _geometry_to_crs(geometry: BaseGeometry, src_crs: str | CRS, dst_crs: str | CRS) -> BaseGeometry:
    return gpd.GeoSeries([geometry], crs=CRS.from_user_input(src_crs)).to_crs(CRS.from_user_input(dst_crs)).iloc[0]


def _resolve_nodata(datasets: Sequence[Any], override: float | int | None) -> float | int:
    if override is not None:
        return override
    for dataset in datasets:
        if dataset.nodata is not None:
            return dataset.nodata
    return DEFAULT_NODATA


def _compatible_dtype(dtype_name: str, nodata: float | int) -> str:
    dtype = np.dtype(dtype_name)
    if np.issubdtype(dtype, np.floating):
        return dtype.name
    info = np.iinfo(dtype)
    if info.min <= nodata <= info.max:
        return dtype.name
    return "float32"


def _mask_array_to_geometry(
    array: np.ndarray,
    transform: Affine,
    geometry: BaseGeometry,
    nodata: float | int,
) -> np.ndarray:
    inside = geometry_mask(
        [mapping(geometry)],
        out_shape=(array.shape[1], array.shape[2]),
        transform=transform,
        invert=True,
    )
    masked = array.copy()
    masked[:, ~inside] = nodata
    return masked


def _reproject_array(
    source_array: np.ndarray,
    source_transform: Affine,
    source_crs: str | CRS,
    destination_crs: str | CRS,
    nodata: float | int,
    resampling: Resampling,
) -> tuple[np.ndarray, Affine]:
    destination_transform, width, height = calculate_default_transform(
        source_crs,
        destination_crs,
        source_array.shape[2],
        source_array.shape[1],
        *_bounds_from_transform(source_transform, source_array.shape[2], source_array.shape[1]),
    )
    width = cast(int, width)
    height = cast(int, height)
    destination = np.full(
        (source_array.shape[0], height, width),
        nodata,
        dtype=source_array.dtype,
    )
    for band_index in range(source_array.shape[0]):
        reproject(
            source=source_array[band_index],
            destination=destination[band_index],
            src_transform=source_transform,
            src_crs=source_crs,
            src_nodata=nodata,
            dst_transform=destination_transform,
            dst_crs=destination_crs,
            dst_nodata=nodata,
            resampling=resampling,
        )
    return destination, destination_transform


def _bounds_from_transform(transform: Affine, width: int, height: int) -> tuple[float, float, float, float]:
    left = transform.c
    top = transform.f
    right = left + transform.a * width
    bottom = top + transform.e * height
    return _bounds_tuple((min(left, right), min(bottom, top), max(left, right), max(bottom, top)))


def _output_profile(
    source_profile: dict[str, Any],
    array: np.ndarray,
    transform: Affine,
    crs: str | CRS,
    nodata: float | int,
    dtype: str,
    compress: str,
) -> dict[str, Any]:
    profile = source_profile.copy()
    profile.update(
        {
            "driver": "GTiff",
            "height": int(array.shape[1]),
            "width": int(array.shape[2]),
            "count": int(array.shape[0]),
            "dtype": dtype,
            "crs": crs,
            "transform": transform,
            "nodata": nodata,
            "compress": compress,
            "tiled": True,
            "blockxsize": 16,
            "blockysize": 16,
            "interleave": "band",
        }
    )
    if compress.lower() in {"deflate", "lzw"} and np.issubdtype(np.dtype(dtype), np.floating):
        profile["predictor"] = 3
    return profile


def _vertical_datum_tags(
    source_vertical_datum: str | None,
    target_vertical_datum: str | None,
    warning: str | None,
) -> dict[str, str]:
    tags: dict[str, str] = {}
    if source_vertical_datum:
        tags["source_vertical_datum"] = source_vertical_datum
    if target_vertical_datum:
        tags["target_vertical_datum"] = target_vertical_datum
    if warning:
        tags["dem_vertical_datum_warning"] = warning
    return tags


__all__ = [
    "AnalysisGeometry",
    "DEFAULT_BUFFER_METERS",
    "DEFAULT_FIELD_CRS",
    "RasterOutputRecord",
    "clip_dem_tiles_to_buffer",
    "file_size",
    "nodata_ratio",
    "prepare_analysis_geometry",
    "sha256_file",
    "transform_buffered_bounds_to_source_crs",
    "utm_crs_for_lonlat",
    "vertical_datum_warning",
    "write_raster_atomic",
]
