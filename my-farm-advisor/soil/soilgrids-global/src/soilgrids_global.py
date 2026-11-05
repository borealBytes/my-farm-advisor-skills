#!/usr/bin/env python3
"""SoilGrids 250 m global soil provider for the My Farm Advisor data pipeline.

Source: ISRIC "SoilGrids" global digital soil mapping, 250 m resolution, six
standard GlobalSoilMap depth intervals, CC-BY 4.0
(https://files.isric.org/soilgrids/latest/data/, license statement in the
release README at .../data/README.md). The current release line on `latest`
self-describes in its VRT metadata as Code_version v2.0.0 / Outputs_version
RUN10 / "no WISE, March 2020 snapshot, NZ and Siberia gaps".

Verified 2026-11-03 against the live server:
- Band VRTs at ``{SOURCE_BASE}/{band}/{band}_{depth}_mean.vrt`` open
  anonymously through GDAL/rasterio; the VRT XML references GeoTIFF tiles
  ``./{band}_{depth}_mean/tileSG-*/...`` which GDAL fetches by HTTP range
  request on read (no local tile cache is required, but each clip pays one
  ~5-6 MB VRT header fetch plus the few tiles that intersect the window).
- Property directories currently published: bdod, cec, cfvo, clay, landmask,
  nitrogen, ocd, ocs, phh2o, sand, silt, soc, wrb. ``phhcl`` (pH CaCl2),
  ``awchc``/``awchl`` (available water capacity), and ``thickness`` return
  HTTP 404 on this release line — pH ships as H2O only and AWC is absent.
  This module intentionally specs only the numeric properties verified today.
- Raster facts: CRS Interrupted Goode Homolosine (no EPSG code; a projected
  composite of sinusoidal/Mollweide lobes), Int16, nodata -32768, 250 m
  pixels, global grid 159246 x 58034. Because the source CRS is interrupted,
  clipping a lat/lon window MUST reproject (see clip_bbox): compute the
  source pixel window from densely transformed bbox corners (a single-corner
  transform can flip lobes near the 40-degree seams), then
  ``rasterio.warp.reproject`` into an EPSG:4326 destination grid.

Scale/offset conversion (physical = raw * scale + offset) was determined
empirically on 2026-11-03 by clipping known landscapes and comparing with
field-expected values, plus the release's own embedded global layer
statistics (clay+silt+sand raw means sum to exactly 1000 g/kg, proving the
texture rasters store g/kg directly). See BAND_SPECS below and GUIDE.md.
"""

from __future__ import annotations

import hashlib
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.warp import transform as crs_transform
from rasterio.windows import Window

SOURCE_NAME = "soilgrids_250m"
SOURCE_BASE = "https://files.isric.org/soilgrids/latest/data"
DATASET_PAGE = "https://www.isric.org/explore/soilgrids/soilgrids-access"
LICENSE = "CC-BY-4.0 (ISRIC data policy)"
ATTRIBUTION = (
    "SoilGrids contributors / ISRIC (2020), SoilGrids 250 m, "
    "https://files.isric.org/soilgrids/latest/data/ - CC BY 4.0"
)

NODATA = -32768
SOURCE_RESOLUTION_METERS = 250
DEPTH_INTERVALS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")
DEFAULT_DEPTH_INTERVALS = ("0-5cm", "5-15cm", "15-30cm")
DEFAULT_BUFFER_METERS = 50.0
DEGREES_PER_METER_LAT = 1.0 / 111_320.0

# physical = raw * scale + offset. Scale factors verified empirically
# 2026-11-03 (Narrabri NSW, clay 15-39%/mean 27; Michigan UP, clay
# 3-51%/mean 16; bdod 0.85-1.35 Mg/m3; pH(H2O) 4.1-7.4; plus the embedded
# global layer statistics in each release VRT header).
BAND_SPECS: dict[str, dict[str, Any]] = {
    "clay": {"unit": "%", "scale": 0.1, "offset": 0.0,
             "description": "Clay content (fraction < 2 um)",
             "typical_range": (0.5, 80.0),
             "note": "raw raster value equals g/kg; scale converts to %"},
    "silt": {"unit": "%", "scale": 0.1, "offset": 0.0,
             "description": "Silt content (2-50 um)",
             "typical_range": (0.5, 95.0),
             "note": "raw raster value equals g/kg; scale converts to %"},
    "sand": {"unit": "%", "scale": 0.1, "offset": 0.0,
             "description": "Sand content (50-2000 um)",
             "typical_range": (0.5, 99.0),
             "note": "raw raster value equals g/kg; scale converts to %"},
    "bdod": {"unit": "Mg/m3", "scale": 0.01, "offset": 0.0,
             "description": "Bulk density (-100 kPa)",
             "typical_range": (0.5, 2.0),
             "note": "kg/dm3 = g/cm3 = Mg/m3 numerically identical"},
    "phh2o": {"unit": "pH (H2O)", "scale": 0.1, "offset": 0.0,
              "description": "Soil reaction, 1:2.5 soil:solution in water",
              "typical_range": (3.0, 9.5),
              "note": "pH CaCl2 (phhcl) is absent from this release line; "
                      "empirically pH(CaCl2) ~ pH(H2O) - 0.5..1.0"},
    "cec": {"unit": "cmol(+)/kg", "scale": 0.1, "offset": 0.0,
            "description": "Cation exchange capacity",
            "typical_range": (0.5, 100.0), "note": ""},
    "soc": {"unit": "hg/cdm3", "scale": 0.1, "offset": 0.0,
            "description": "Soil organic carbon content",
            "typical_range": (0.1, 300.0),
            "note": "ISRIC unit label hg/cdm3, numerically ~ g C/kg at bulk "
                    "density 1.0"},
    "nitrogen": {"unit": "g/kg", "scale": 0.01, "offset": 0.0,
                 "description": "Total nitrogen content",
                 "typical_range": (0.02, 30.0),
                 "note": "verified via embedded global stats (raw mean 377 "
                         "-> 3.8 g/kg)"},
    "cfvo": {"unit": "cm3/dm3", "scale": 0.1, "offset": 0.0,
             "description": "Coxa fragments volume (< 2 mm excluded)",
             "typical_range": (0.0, 85.0),
             "note": "volume percent; verified via embedded global stats"},
    "ocd": {"unit": "kg/m3", "scale": 0.1, "offset": 0.0,
            "description": "Organic carbon density",
            "typical_range": (0.5, 250.0),
            "note": "scale checked against embedded global stats only"},
}
# ocs (organic carbon stock) is published but its scale was never cross-
# checked; wrb/landmask are categorical layers — intentionally unspec'd here.
DEFAULT_BANDS = ("bdod", "cec", "cfvo", "clay", "nitrogen", "phh2o", "sand", "silt", "soc")

GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def gdal_version() -> str:
    return rasterio.__gdal_version__


def vrt_url(band: str, depth: str) -> str:
    """Canonical band VRT URL, e.g. .../clay/clay_0-5cm_mean.vrt."""
    return f"{SOURCE_BASE}/{band}/{band}_{depth}_mean.vrt"


def band_spec(band: str) -> dict[str, Any]:
    spec = BAND_SPECS.get(band)
    if spec is None:
        raise KeyError(
            f"no verified SoilGrids scale spec for band {band!r}; supported: "
            + ", ".join(sorted(BAND_SPECS))
        )
    return spec


def apply_scale(raw: float | int | np.ndarray, band: str) -> Any:
    spec = band_spec(band)
    return np.asarray(raw, dtype="float64") * spec["scale"] + spec["offset"]


def field_bbox(geometry: Any, buffer_meters: float = DEFAULT_BUFFER_METERS) -> tuple[float, float, float, float]:
    """Bbox (minx, miny, maxx, maxy) in EPSG:4326, buffered outward.

    Buffer is converted to degrees using the bbox center latitude; for the
    250 m grid a few meters of distortion at the edges is irrelevant.
    """
    minx, miny, maxx, maxy = geometry.bounds
    dlat = buffer_meters * DEGREES_PER_METER_LAT
    lon_cos = max(0.05, math.cos(math.radians((miny + maxy) / 2.0)))
    dlon = dlat / lon_cos
    return (minx - dlon, miny - dlat, maxx + dlon, maxy + dlat)


def _source_window(src, bbox: tuple[float, float, float, float], grid: int = 6, pad_px: int = 2) -> Window:
    """Pixel window in the (interrupted) source grid covering the bbox.

    Dense grid sampling (not corner-only) so a bbox that approaches an
    interruption seam still yields a safe bounding window.
    """
    lons = list(np.linspace(bbox[0], bbox[2], grid))
    lats = list(np.linspace(bbox[1], bbox[3], grid))
    xs, ys = crs_transform(CRS.from_epsg(4326), src.crs, lons, lats)
    cols: list[int] = []
    rows: list[int] = []
    for x, y in zip(xs, ys):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"source CRS transform produced non-finite point ({x}, {y})")
        row, col = src.index(x, y)
        cols.append(int(col))
        rows.append(int(row))
    min_c, max_c = min(cols) - pad_px, max(cols) + pad_px
    min_r, max_r = min(rows) - pad_px, max(rows) + pad_px
    return Window(min_c, min_r, max_c - min_c, max_r - min_r)


def _zonal_stats(arr: np.ndarray, zmask: np.ndarray, band: str) -> dict[str, Any]:
    spec = band_spec(band)
    valid = arr[zmask]
    total = int(arr.size)
    record: dict[str, Any] = {
        "band": band,
        "n_pixels": int(valid.size),
        "n_pixels_window": total,
        "nodata_ratio": round(1.0 - valid.size / total, 4) if total else 1.0,
    }
    if valid.size:
        values = valid.astype("float64") * spec["scale"] + spec["offset"]
        record.update(
            unit=spec["unit"],
            scale=spec["scale"],
            mean=float(values.mean()),
            min=float(values.min()),
            max=float(values.max()),
            stdev=float(values.std(ddof=0)),
            raw_min=int(valid.min()),
            raw_max=int(valid.max()),
            raw_mean=float(valid.astype("float64").mean()),
        )
    else:
        record.update(unit=spec["unit"], scale=spec["scale"],
                      mean=None, min=None, max=None, stdev=None,
                      raw_min=None, raw_max=None, raw_mean=None)
    return record


def clip_bbox(
    band: str,
    depth: str,
    bbox: tuple[float, float, float, float],
    out_path: Path,
    *,
    polygon: Any | None = None,
    buffer_note: str = "",
) -> dict[str, Any]:
    """Clip one band/depth VRT to a WGS84 bbox, write GeoTIFF, return stats.

    ``polygon`` (EPSG:4326 geometry with ``__geo_interface__``, e.g. a
    shapely geometry) restricts the statistics via an exact zonal mask;
    without it the whole clipped window is counted. The written raster keeps
    the raw Int16/0.1-scale encoding (documented in raster tags).
    """
    spec = band_spec(band)
    url = vrt_url(band, depth)
    env_vars = dict(GDAL_ENV)
    env_vars.update({k: v for k, v in os.environ.items() if k.startswith("GDAL_")})
    with rasterio.Env(**env_vars):
        with rasterio.open(url) as src:
            window = _source_window(src, bbox)
            # one source pixel is 250 m; the latitude degree is the stable
            # linear unit for the destination grid
            res_deg = SOURCE_RESOLUTION_METERS * DEGREES_PER_METER_LAT
            dst_w = max(1, int(round((bbox[2] - bbox[0]) / res_deg)))
            dst_h = max(1, int(round((bbox[3] - bbox[1]) / res_deg)))
            dst_transform = from_bounds(*bbox, width=dst_w, height=dst_h)
            data = np.full((1, dst_h, dst_w), NODATA, dtype="int16")
            reproject(
                source=rasterio.band(src, 1),
                destination=data,
                src_crs=src.crs,
                src_window=[int(window.col_off), int(window.row_off),
                            int(window.width), int(window.height)],
                dst_crs=CRS.from_epsg(4326),
                dst_transform=dst_transform,
                dst_nodata=NODATA,
                resampling=Resampling.nearest,
            )
    arr = data[0]
    if polygon is not None:
        zmask = geometry_mask(
            [polygon], out_shape=arr.shape, transform=dst_transform,
            all_touched=True, invert=True,
        )
    else:
        zmask = np.ones(arr.shape, dtype=bool)
    zmask &= arr != NODATA

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            out_path, "w",
            driver="GTiff", height=dst_h, width=dst_w, count=1, dtype="int16",
            crs="EPSG:4326", transform=dst_transform, nodata=NODATA,
            compress="deflate", tiled=True,
        ) as dst:
            dst.write(data)
            dst.update_tags(
                source=SOURCE_NAME,
                vrt_url=url,
                band=band,
                depth=depth,
                unit=spec["unit"],
                scale=str(spec["scale"]),
                offset=str(spec["offset"]),
                source_crs="Interrupted Goode Homolosine",
                accessed_utc=utc_now(),
                attribution=ATTRIBUTION,
            )

    record = _zonal_stats(arr, zmask, band)
    record.update(
        depth=depth,
        source_url=url,
        raster_path=str(out_path) if out_path is not None else None,
        height=dst_h,
        width=dst_w,
        bbox=[float(v) for v in bbox],
        accessed_at=utc_now(),
        gdal_version=gdal_version(),
        note=buffer_note,
    )
    return record


def stats_from_raster(path: Path, band: str, polygon: Any | None = None) -> dict[str, Any]:
    """Recompute zonal stats from an already-written clip (cached replay)."""
    path = Path(path)
    with rasterio.open(path) as dataset:
        arr = dataset.read(1)
        transform = dataset.transform
        if polygon is not None:
            zmask = geometry_mask([polygon], out_shape=arr.shape,
                                  transform=transform, all_touched=True, invert=True)
        else:
            zmask = np.ones(arr.shape, dtype=bool)
        zmask &= arr != NODATA
        record = _zonal_stats(arr, zmask, band)
        record.update(bbox=[float(v) for v in dataset.bounds], raster_path=str(path))
    return record


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_availability(bands: Iterable[str] | None = None, depths: Iterable[str] | None = None) -> dict[str, dict[str, bool]]:
    """HEAD-probe band VRT URLs; {band: {depth: exists}}. Network only, no reads."""
    import urllib.request

    band_list = list(bands if bands is not None else sorted(BAND_SPECS))
    depth_list = list(depths if depths is not None else DEPTH_INTERVALS)
    result: dict[str, dict[str, bool]] = {}
    for band in band_list:
        result[band] = {}
        for depth in depth_list:
            request = urllib.request.Request(vrt_url(band, depth), method="HEAD")
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    result[band][depth] = response.status == 200
            except Exception:
                result[band][depth] = False
    return result
