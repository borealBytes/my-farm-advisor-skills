from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.mask import mask
from rasterio.warp import Resampling, calculate_default_transform, reproject

PLANETARY_COMPUTER_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PLANETARY_COMPUTER_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
SENTINEL_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"
SENTINEL_CLOUD_CLASSES = {3, 8, 9, 10, 11}
LANDSAT_QA_MASK_BITS = (1, 2, 3, 4, 5)
TRANSIENT_SEARCH_STATUS_CODES = {429, 500, 502, 503, 504}
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class SatelliteSearchError(RuntimeError):
    """Raised when the STAC search endpoint remains unavailable after retries."""


def growing_season_range(year: int) -> str:
    return f"{year}-03-01T00:00:00Z/{year}-11-30T23:59:59Z"


def feature_datetime(feature: dict[str, Any]) -> datetime:
    raw_value = str(feature.get("properties", {}).get("datetime", "1970-01-01T00:00:00Z"))
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))


def feature_cloud_cover(feature: dict[str, Any]) -> float:
    return float(feature.get("properties", {}).get("eo:cloud_cover", 100.0))


def search_best_feature(
    collection: str,
    bbox: tuple[float, float, float, float],
    datetime_range: str,
    cloud_lt: float,
    *,
    limit: int = 20,
) -> dict[str, Any] | None:
    features = search_features(
        collection,
        bbox,
        datetime_range,
        cloud_lt,
        limit=limit,
    )
    if not features:
        return None
    return features[0]


def search_features(
    collection: str,
    bbox: tuple[float, float, float, float],
    datetime_range: str,
    cloud_lt: float,
    *,
    limit: int = 100,
    attempts: int = 3,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"eo:cloud_cover": {"lt": cloud_lt}}
    if collection == LANDSAT_COLLECTION:
        query["platform"] = {"in": ["landsat-8", "landsat-9"]}

    body = {
        "collections": [collection],
        "bbox": [bbox[0], bbox[1], bbox[2], bbox[3]],
        "datetime": datetime_range,
        "limit": limit,
        "query": query,
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.post(PLANETARY_COMPUTER_SEARCH_URL, json=body, timeout=60)
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            response = getattr(exc, "response", None)
            if response is not None and response.status_code not in TRANSIENT_SEARCH_STATUS_CODES:
                raise
            if attempt + 1 >= attempts:
                raise SatelliteSearchError(
                    f"Planetary Computer STAC search failed after {attempts} attempts "
                    f"for {collection} {datetime_range}"
                ) from exc
            time.sleep(min(2**attempt, 20))
    else:
        raise SatelliteSearchError(
            f"Planetary Computer STAC search failed for {collection} {datetime_range}"
        ) from last_error
    features = response.json().get("features", [])
    return sorted(
        features,
        key=lambda feature: (feature_cloud_cover(feature), -feature_datetime(feature).timestamp()),
    )


def sign_planetary_computer_href(collection: str, href: str) -> str:
    if collection not in {SENTINEL_COLLECTION, LANDSAT_COLLECTION}:
        return href
    cached = _TOKEN_CACHE.get(collection)
    now = time.time()
    if cached is not None and cached[1] > now:
        token = cached[0]
    else:
        token = ""
        last_error: Exception | None = None
        for attempt in range(5):
            token_response = requests.get(
                f"{PLANETARY_COMPUTER_TOKEN_URL}/{collection}", timeout=60
            )
            if token_response.status_code == 429:
                last_error = requests.HTTPError("Planetary Computer token rate limited")
                time.sleep(min(2**attempt, 20))
                continue
            token_response.raise_for_status()
            token = str(token_response.json()["token"])
            _TOKEN_CACHE[collection] = (token, now + 600)
            break
        if not token:
            raise last_error or RuntimeError(f"Unable to sign asset for {collection}")
    separator = "&" if "?" in href else "?"
    return f"{href}{separator}{token}"


def clip_asset_to_field(
    href: str,
    field_geometry: Any,
    output_path: Path,
    *,
    output_crs: str = "EPSG:4326",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(href) as src:
        field = gpd.GeoSeries([field_geometry], crs="EPSG:4326").to_crs(src.crs)
        out_image, out_transform = mask(src, [field.iloc[0].__geo_interface__], crop=True)
        profile = src.profile.copy()

    profile.update(
        {
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "compress": "lzw",
        }
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(out_image)

    if not output_crs:
        return output_path

    with rasterio.open(output_path) as src:
        if str(src.crs) == output_crs:
            return output_path
        reprojected = output_path.with_name(output_path.stem + "_epsg4326.tif")
        transform, width, height = calculate_default_transform(
            src.crs,
            output_crs,
            src.width,
            src.height,
            *src.bounds,
        )
        profile = src.profile.copy()
        profile.update(
            {
                "crs": output_crs,
                "transform": transform,
                "width": width,
                "height": height,
            }
        )
        with rasterio.open(reprojected, "w", **profile) as dst:
            for band_index in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band_index),
                    destination=rasterio.band(dst, band_index),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=output_crs,
                    resampling=Resampling.bilinear,
                )
        return reprojected


def sentinel_asset_keys(feature: dict[str, Any]) -> dict[str, str]:
    assets = feature.get("assets", {})
    return {
        "red": "red" if "red" in assets else "B04",
        "nir": "nir" if "nir" in assets else "B08",
        "scl": "scl" if "scl" in assets else "SCL",
    }


def landsat_asset_keys(feature: dict[str, Any]) -> dict[str, str]:
    return {
        "red": "red",
        "nir": "nir08",
        "qa": "qa_pixel",
    }


def _landsat_surface_reflectance(array: np.ndarray) -> np.ndarray:
    scaled = array.astype("float32")
    scaled[scaled == 0] = np.nan
    return scaled * 0.0000275 - 0.2


def _landsat_cloud_mask(qa_array: np.ndarray) -> np.ndarray:
    mask_array = np.zeros_like(qa_array, dtype=bool)
    for bit in LANDSAT_QA_MASK_BITS:
        mask_array |= (qa_array.astype("uint16") & (1 << bit)) != 0
    return mask_array


def write_single_band_raster(
    output_path: Path,
    data: np.ndarray,
    reference_raster: Path,
    *,
    nodata: float | None = np.nan,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(reference_raster) as src:
        profile = src.profile.copy()
    profile.update(dtype=rasterio.float32, count=1, compress="lzw", nodata=nodata)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)
    return output_path


def _read_resampled_like(
    source_path: Path,
    reference_path: Path,
    *,
    resampling: Resampling,
) -> np.ndarray:
    with rasterio.open(reference_path) as ref_src, rasterio.open(source_path) as src:
        destination = np.full((ref_src.height, ref_src.width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_src.transform,
            dst_crs=ref_src.crs,
            resampling=resampling,
        )
    return destination


def compute_sentinel_ndvi(
    red_path: Path,
    nir_path: Path,
    scl_path: Path | None,
    output_path: Path,
) -> Path:
    with rasterio.open(red_path) as red_src:
        red = red_src.read(1).astype("float32")
    with rasterio.open(nir_path) as nir_src:
        nir = nir_src.read(1).astype("float32")

    cloud_mask = np.zeros_like(red, dtype=bool)
    if scl_path is not None and scl_path.exists():
        scl = _read_resampled_like(scl_path, red_path, resampling=Resampling.nearest)
        cloud_mask = np.isin(scl, list(SENTINEL_CLOUD_CLASSES))

    denominator = nir + red
    valid = np.isfinite(red) & np.isfinite(nir) & (denominator != 0) & ~cloud_mask
    ndvi = np.full(red.shape, np.nan, dtype="float32")
    ndvi[valid] = (nir[valid] - red[valid]) / denominator[valid]
    ndvi = np.clip(ndvi, -1.0, 1.0)
    return write_single_band_raster(output_path, ndvi, red_path)


def compute_landsat_ndvi(
    red_path: Path,
    nir_path: Path,
    qa_path: Path | None,
    output_path: Path,
) -> Path:
    with rasterio.open(red_path) as red_src:
        red = _landsat_surface_reflectance(red_src.read(1))
    with rasterio.open(nir_path) as nir_src:
        nir = _landsat_surface_reflectance(nir_src.read(1))

    cloud_mask = np.zeros_like(red, dtype=bool)
    if qa_path is not None and qa_path.exists():
        qa_array = _read_resampled_like(qa_path, red_path, resampling=Resampling.nearest)
        cloud_mask = _landsat_cloud_mask(qa_array)

    denominator = nir + red
    valid = np.isfinite(red) & np.isfinite(nir) & (denominator != 0) & ~cloud_mask
    ndvi = np.full(red.shape, np.nan, dtype="float32")
    ndvi[valid] = (nir[valid] - red[valid]) / denominator[valid]
    ndvi = np.clip(ndvi, -1.0, 1.0)
    return write_single_band_raster(output_path, ndvi, red_path)
