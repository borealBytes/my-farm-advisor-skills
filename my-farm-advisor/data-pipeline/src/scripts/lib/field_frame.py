"""Field-local map frame for STATIC figures — the skill-locked convention.

Every static field map this pipeline renders (papers, presentations, README
examples) uses one frame, provided here deterministically:

  1. project to the field's real UTM zone (EPSG:326xx / 327xx) — never plot a
     single field on geodetic degrees;
  2. AUTO-ROTATE the geometry so the field's long edge lies along the panel's
     long edge (viewport fit). Canonical angle in (-90, +90] with a 0.5°
     dead-zone — an already-vertical field gets zero, not "-0°";
  3. translate so (0, 0) is the SW corner of the ROTATED bounding box: every
     coordinate is positive and the reader's ruler starts at the corner;
  4. decorate: boxed north arrow counter-rotated to the tilt, rotation
     callout whenever rotated, and a scale bar (metres) — the arrow counter-
     rotates, the metre grid does NOT;
  5. state the reproduction recipe: the official UTM zone the field sits in
     plus the CUSTOM FIELD CRS — a Transverse Mercator whose axis crosses the
     rotated-SW origin at the fitted azimuth — so anyone can regenerate the
     exact coordinates with pyproj/GDAL.

Web/interactive basemaps (Leaflet, MapLibre) keep real WGS84/EPSG:3857 —
this frame is for static plotting where the layout is optimized for the page.

Reproduction recipe (published verbatim by crs_note(full=True)):
    origin  = (E, N) in the field's UTM zone at frame (0, 0);
    x = (ΔE)cos r + (ΔN)sin r,   y = -(ΔE)sin r + (ΔN)cos r,  r = tilt, deg CW.
An affine rotation of a TM grid is NOT a stock PROJ projection — PROJ's
tmerc silently ignores +alpha (verified against pyproj, 2026-11-05) — so we
publish the exact affine rather than a fake "+proj=tmerc +alpha=..." string.
The north arrow additionally uses TRUE north computed numerically at the
origin: at zone edges grid convergence reaches ~2 degrees and (sin r, cos r)
would be visibly wrong on a 500 m scale bar.

Usage:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))   # scripts/lib
    from field_frame import frame_for, decorate, crs_note

    ff = frame_for(gdf_wgs84, panel_h_in=4.0, panel_w_in=2.6)     # -> Frame
    ff.geometry.plot(ax=ax, ...)                                  # framed geoms
    decorate(ax, ff)                                              # arrow+bars
    ax.set_xlabel(crs_note(ff))                                   # zone + tilt
    ax.set_title(crs_note(ff, full=True))                         # affine recipe
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import geopandas as gpd
from shapely import affinity

DEADZONE_DEG = 0.5
SCALE_BAR_M = 500.0


def utm_epsg(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _long_edge_bearing_deg(geom) -> float:
    """Bearing (deg, clockwise from north) of the minimum-rotated-rectangle
    long edge. Unwrapped to (-90, 90] because a long edge is 180-symmetric."""
    pts = list(geom.minimum_rotated_rectangle.exterior.coords)[:5]
    edges = list(zip(pts, pts[1:]))
    (x1, y1), (x2, y2) = max(edges, key=lambda e: (e[1][0] - e[0][0]) ** 2
                              + (e[1][1] - e[0][1]) ** 2)
    th = math.degrees(math.atan2(x2 - x1, y2 - y1))  # from north, east-positive
    while th <= -90.0:
        th += 180.0
    while th > 90.0:
        th -= 180.0
    return th


@dataclass
class Frame:
    geometry: gpd.GeoDataFrame          # framed polygons: metres, (0,0)=SW, rotated
    epsg: int                           # the real UTM zone the field lives in
    rot: float                          # applied tilt, deg (CW), canonical (-90, +90]
    e0: float                           # zone coords of the framed origin corner
    n0: float
    lon0: float                         # geographic location of that corner
    lat0: float
    adx: float = 0.0                    # TRUE north in frame coords (unit vec);
    ady: float = 1.0                    #  != (sin rot, cos rot) where grid
                                        #  convergence bites (up to ~2 deg at zone edges)
    scale_len: float = SCALE_BAR_M

    @property
    def rotated(self) -> bool:
        return self.rot != 0.0


def frame_for(gdf: gpd.GeoDataFrame, panel_h_in: float, panel_w_in: float,
              scale_len: float = SCALE_BAR_M) -> Frame:
    """Project (if needed), auto-fit, re-pin. gdf: WGS84 or any CRS."""
    lonlat = gdf.to_crs(4326)
    epsg = utm_epsg(lonlat.geometry.union_all().centroid.x,
                    lonlat.geometry.union_all().centroid.y)
    gu = gdf.to_crs(epsg)
    union = gu.dissolve().geometry.iloc[0] if len(gu) > 1 else gu.geometry.iloc[0]
    theta = _long_edge_bearing_deg(union)
    # bearing from north -> tilt from east: edge angle from E is (90 - theta)
    rot = (90.0 - theta) - (0.0 if panel_h_in < panel_w_in else 90.0)
    rot = ((rot + 90.0) % 180.0) - 90.0
    if abs(rot) < DEADZONE_DEG:
        rot = 0.0
    # translate, rotate about (0,0), re-translate to the ROTATED SW corner
    x0, y0, _, _ = gu.total_bounds
    gu = gu.assign(geometry=gu.geometry.translate(xoff=-x0, yoff=-y0))
    if rot:
        gu = gu.assign(geometry=gu.geometry.map(lambda g: affinity.rotate(g, -rot, origin=(0, 0))))
    x0r, y0r, _, _ = gu.total_bounds
    gu = gu.assign(geometry=gu.geometry.translate(xoff=-x0r, yoff=-y0r))
    # The framed (0,0) corner sits at (x0r, y0r) IN ROTATED SPACE. Inverting
    # the framing v = shift + R_ccw(f + rmin) gives the zone-coord anchor
    #   e0,n0 = (x0,y0) + R_ccw(x0r, y0r)
    # — rotating the re-pin offset back is mandatory (omitting it shears the
    # anchor off by ~rot_rad * |rmin|, i.e. km at rot 50+).
    rpin = math.radians(rot)
    e0 = x0 + x0r * math.cos(rpin) - y0r * math.sin(rpin)
    n0 = y0 + x0r * math.sin(rpin) + y0r * math.cos(rpin)
    corner = gpd.GeoDataFrame(geometry=[gpd.points_from_xy([e0], [n0])[0]],
                              crs=epsg).to_crs(4326).geometry.iloc[0]
    # TRUE north in frame coords, numerically (captures grid convergence)
    north_pt = gpd.GeoDataFrame(
        geometry=[gpd.points_from_xy([corner.x], [corner.y + 1e-4])[0]], crs=4326)
    np_utm = north_pt.to_crs(epsg).geometry.iloc[0]
    dxg, dyg = np_utm.x - e0, np_utm.y - n0  # ~11.1 m due true north, in zone coords
    r2 = math.radians(rot)
    adx = dxg * math.cos(r2) + dyg * math.sin(r2)
    ady = -dxg * math.sin(r2) + dyg * math.cos(r2)
    mag = math.hypot(adx, ady) or 1.0
    adx, ady = adx / mag, ady / mag
    if ady < 0:  # keep north pointing up (rot canonical range guarantees this anyway)
        adx, ady = -adx, -ady
    return Frame(geometry=gu, epsg=epsg, rot=rot, e0=e0, n0=n0,
                 lon0=corner.x, lat0=corner.y, adx=adx, ady=ady,
                 scale_len=scale_len)


def crs_note(f: Frame, full: bool = False) -> str:
    """Reproducible definition of the field-local frame.

    Short form (axis label): zone + tilt. Full form (caption): the exact
    affine recipe — (ΔE, ΔN) from the named corner's UTM coords, rotated CW
    by r. An affine rotation of a TM grid is NOT a stock PROJ projection
    (PROJ's tmerc silently ignores +alpha), so we publish the two-line
    formula rather than a fake CRS string.
    """
    zone = f.epsg - (32700 if f.epsg >= 32700 else 32600)
    hemi = "N" if f.epsg < 32700 else "S"
    short = (f"field-local m (rot {f.rot:+.0f}°) — UTM zone {zone}{hemi} (EPSG:{f.epsg})"
             if f.rotated else f"m from SW corner — UTM zone {zone}{hemi} (EPSG:{f.epsg})")
    if not full or not f.rotated:
        return short
    return (f"{short}; origin: {f.epsg} E={f.e0:.1f} N={f.n0:.1f} "
            f"(lat {f.lat0:.6f}, lon {f.lon0:.6f}) at frame (0,0); "
            f"x=(ΔE)cos{f.rot:.1f}°+(ΔN)sin{f.rot:.1f}°, "
            f"y=−(ΔE)sin{f.rot:.1f}°+(ΔN)cos{f.rot:.1f}°")


def reproject_into_frame(ds, f: Frame, dst_res: float, poly_metric=None):
    """RasterIO source dataset -> (masked array, extent) in this frame.

    One resample straight into the rotated grid via a rotated GDAL
    geotransform — the metre axes stay honest and the field mask is applied
    after warping, so partial boundary cells are complete (raster_rules
    margin was already applied at fetch time).
    """
    import math
    import numpy as np
    import rasterio
    import rasterio.warp
    from rasterio.features import geometry_mask
    from rasterio.transform import Affine

    r_ = math.radians(f.rot)
    H = _frame_height(f)
    nr, nc = int(H / dst_res) + 1, int(_frame_width(f) / dst_res) + 1
    a, b = math.cos(r_) * dst_res, math.sin(r_) * dst_res
    # Frame->UTM inverse: E = e0 + x*cos r - y*sin r, N = n0 + x*sin r + y*cos r,
    # with x = col*res, y = H - row*res (row 0 = north edge). Expanding:
    #   E = (e0 - H*sin r) + col*(res cos r) + row*(res sin r)
    #   N = (n0 + H*cos r) + col*(res sin r) + row*(-res cos r)
    # -> top-left corner in UTM is (e0 - H*sin r, n0 + H*cos r).
    h_pad = nr * dst_res
    dst_tr = Affine(a, b, f.e0 - h_pad * math.sin(r_),
                    b, -a, f.n0 + h_pad * math.cos(r_))
    dst = np.full((nr, nc), np.nan, dtype="float64")
    _src = ds.read(1, masked=True)
    _src = np.ma.masked_invalid(_src.astype("float64"))
    rasterio.warp.reproject(
        _src.filled(np.nan), dst,
        src_transform=ds.transform, src_crs=ds.crs,
        dst_transform=dst_tr, dst_crs=f.epsg,
        resampling=rasterio.warp.Resampling.bilinear)
    # Mask from the FRAME-coord polygon: exact by construction and independent
    # of the geographic anchor (passing a UTM polygon here reintroduces every
    # anchoring/convention bug into a step that has none). poly_metric is kept
    # in the signature for callers; it is currently unused for masking.
    _ = poly_metric
    gm = geometry_mask([f.geometry.dissolve().union_all().__geo_interface__]
                       if hasattr(f.geometry, "dissolve") else
                       [f.geometry.__geo_interface__],
                       out_shape=(nr, nc),
                       transform=Affine(dst_res, 0, 0, 0, -dst_res, nr * dst_res),
                       invert=True)
    return np.ma.masked_where(~gm, np.ma.masked_invalid(dst)), (0, nc * dst_res, 0, nr * dst_res)


def _frame_width(f: Frame) -> float:
    return float(f.geometry.total_bounds[2])


def _frame_height(f: Frame) -> float:
    return float(f.geometry.total_bounds[3])


def decorate(ax, f: Frame, arrow_r: float = 0.135, arrow_fs: float = 16.0,
             callout: bool = True, scalebar: bool = True,
             arrow_xy: tuple = (0.87, 0.845)) -> None:
    """Boxed true-north arrow (+ boxed N), rotation callout, scale bar.

    callout=False for dense grids where the xlabel already carries the tilt;
    scale_len <= 0 skips the bar (field too small to show 500 m)."""
    import matplotlib.patches as _mp
    import matplotlib.transforms as _mt

    dx, dy = f.adx, f.ady
    cx, cy = arrow_xy
    ax.annotate("", xy=(cx + arrow_r * dx, cy + arrow_r * dy),
                xytext=(cx - arrow_r * 0.72 * dx, cy - arrow_r * 0.72 * dy),
                xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", lw=3.0, color="#111827",
                                mutation_scale=20), zorder=10)
    ax.text(cx + arrow_r * 1.30 * dx, cy + arrow_r * 1.30 * dy, "N",
            transform=ax.transAxes, fontsize=arrow_fs, fontweight="bold", ha="center",
            va="center", color="#111827",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#111827", lw=1.0),
            zorder=11)
    if callout and f.rotated:
        ax.text(0.02, 0.98,
                f"field rotated {f.rot:+.0f}° to fit — N shown by arrow",
                transform=ax.transAxes, fontsize=6.8, style="italic",
                color="#374151", va="top")
    if not scalebar or f.scale_len <= 0:
        return
    tr = _mt.blended_transform_factory(ax.transData, ax.transAxes)
    x_lo = ax.get_xlim()[0]
    ax.plot([x_lo + 60, x_lo + 60 + f.scale_len], [0.035, 0.035], transform=tr,
            color="#111827", lw=2.0, clip_on=False)
    ax.text(x_lo + 60 + f.scale_len / 2, 0.055, f"{f.scale_len:.0f} m",
            transform=tr, fontsize=6.6, ha="center", color="#111827",
            bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none", alpha=0.85))
