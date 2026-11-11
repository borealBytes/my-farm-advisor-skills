"""Satellite basemap underlay for field figures (2026-11-05 user policy).

Every field-boundary figure is drawn over keyless Esri World Imagery tiles —
the style the SSURGO admin map established and the user chose for all maps:
nodata corners read as farm scenery, never as a gray void. Tiles are fetched
through contextily (anonymous XYZ, no account) and warped in ONE resample
into the same rotated field frame the data panels use (rotated rasterio
Affine), so basemap and data are pixel-registered at any rotation.

If the fetch fails (offline, tile outage) callers get False and the figure
keeps its plain background — a basemap must never break a render.
Attribution is drawn by :func:`attribution` wherever draw() succeeds
("Imagery (c) Esri", matching the SSURGO map's credit line).
"""
from __future__ import annotations

import math
import os
import tempfile

import numpy as np

_ESRI = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery"
         "/MapServer/tile/{z}/{y}/{x}")
_CACHE: dict = {}


def _web_zoom(lat_deg: float, res_m: float) -> int:
    res_m = max(float(res_m), 0.05)
    z = math.log2(156543.03392 * math.cos(math.radians(lat_deg)) / res_m)
    return int(np.clip(round(z), 3, 17))


def _tile_raster(bbox_wgs84, zoom, path):
    import contextily as ctx
    ctx.tile.bounds2raster(bbox_wgs84[0], bbox_wgs84[1], bbox_wgs84[2],
                           bbox_wgs84[3], path, zoom=zoom, source=_ESRI,
                           ll=True, wait=0.1, max_retries=2, n_connections=4,
                           use_cache=True)


def _warp_to_frame(ds, f, ext, ny, nx, dst_tr):
    import rasterio
    import rasterio.warp
    from rasterio.enums import Resampling
    src_n = min(ds.count, 4)
    src = ds.read(list(range(1, src_n + 1)))          # (C, h, w) uint8
    dst = np.full((src_n, ny, nx), 255, dtype="uint8")
    kwargs = {}
    if ds.nodata is not None:
        kwargs["src_nodata"] = ds.nodata
    elif src_n >= 4:
        kwargs["src_nodata"] = 0
    if kwargs.get("src_nodata") is not None:
        kwargs["dst_nodata"] = 255
    rasterio.warp.reproject(
        src, dst,
        src_transform=ds.transform, src_crs="EPSG:3857",
        dst_crs=f"EPSG:{f.epsg}", dst_transform=dst_tr,
        resampling=Resampling.bilinear,
        **kwargs)
    rgb = dst[:3].transpose(1, 2, 0).copy()
    if src_n >= 4:
        am = src[3] == 0 if "src_nodata" not in kwargs else dst[3] == 0
        rgb[am] = 255
    return rgb


def frame_basemap(f, ext, ny, nx, target_res_m: float = 8.0):
    """Esri World Imagery warped to exactly (ext, (ny, nx)) frame coords.

    ext = (x0, x1, y0, y1) in frame metres (origin-at-frame-corner
    convention every panel already uses). Returns (rgb uint8 (ny, nx, 3),
    ext) or (None, None) on any failure — callers must degrade gracefully.
    """
    try:
        import rasterio
        import pyproj
        from rasterio.transform import Affine
    except Exception:
        return None, None
    try:
        r_ = math.radians(float(getattr(f, "rot", 0.0)))
        cr, sr = math.cos(r_), math.sin(r_)
        resx, resy = (ext[1] - ext[0]) / nx, (ext[3] - ext[2]) / ny
        res = min(resx, resy)
        x_tl, y_tl = ext[0], ext[3]          # NW corner in frame coords
        dst_tr = Affine(cr * res, sr * res,
                        f.e0 + x_tl * cr - y_tl * sr,
                        sr * res, -cr * res,
                        f.n0 + x_tl * sr + y_tl * cr)
        tf = pyproj.Transformer.from_crs(f"EPSG:{f.epsg}", 4326, always_xy=True)
        def _f2ll(x, y):
            E = f.e0 + x * cr - y * sr
            N = f.n0 + x * sr + y * cr
            return tf.transform(E, N)
        pts = [_f2ll(x, y) for x, y in ((ext[0], ext[2]), (ext[1], ext[2]),
                                        (ext[0], ext[3]), (ext[1], ext[3]))]
        lons = [p[0] for p in pts]
        lats = [p[1] for p in pts]
        pad = 0.004
        bbox = (min(lons) - pad, max(min(lats) - pad, -84.0),
                max(lons) + pad, min(max(lats) + pad, 84.0))
        lat0 = sum(lats) / len(lats)
        zoom = _web_zoom(lat0, target_res_m)
        key = (round(bbox[0], 4), round(bbox[1], 4),
               round(bbox[2], 4), round(bbox[3], 4), zoom)
        fd, path = tempfile.mkstemp(suffix=".tif")
        os.close(fd)
        try:
            hit = _CACHE.get(key)
            if hit is None:
                _tile_raster(bbox, zoom, path)
                hit = (path, None)           # keep temp file alive for reuse
                _CACHE[key] = hit
                with rasterio.open(path) as ds:
                    rgb = _warp_to_frame(ds, f, ext, ny, nx, dst_tr)
            else:
                with rasterio.open(hit[0]) as ds:
                    rgb = _warp_to_frame(ds, f, ext, ny, nx, dst_tr)
        finally:
            if hit is None and os.path.exists(path):
                os.remove(path)
        return rgb, (ext[0], ext[1], ext[2], ext[3])
    except Exception as _exc:                      # pragma: no cover
        import os as _os
        if _os.environ.get("AG_BASEMAP_DEBUG"):
            raise
        return None, None


def draw(ax, f, ext, ny, nx, target_res_m: float = 8.0) -> bool:
    """Imagery underlay on ax. Draw FIRST in each panel; data layers on top."""
    rgb, e = frame_basemap(f, ext, ny, nx, target_res_m)
    if rgb is None:
        return False
    ax.imshow(rgb, extent=(e[0], e[1], e[2], e[3]), origin="upper",
              zorder=-10)
    attribution(ax)
    return True


def attribution(ax):
    ax.text(0.008, 0.012, "Imagery \u00a9 Esri", transform=ax.transAxes,
            fontsize=4.6, color="0.45", ha="left", va="bottom", zorder=8)
