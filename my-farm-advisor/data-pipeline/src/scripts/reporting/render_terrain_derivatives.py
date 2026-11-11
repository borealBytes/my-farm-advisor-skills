#!/usr/bin/env python3
"""Render a 3x3 grid of terrain-derivative layers for one field boundary.

Reads the derivative GeoTIFF stack produced by the terrain ingest
(derived/terrain/) and shows the nine layers growers actually use:
elevation, hillshade, slope, aspect, flow accumulation, wetness index,
TPI, relative elevation, and the erosion proxy. Every panel is masked to
the field polygon (red outline). DEM resolution is whatever the resolver
picked (USGS 3DEP 1 m in the US, Copernicus 30 m elsewhere).

Usage (env-gated, no absolute paths):
    DATA_PIPELINE_DATA_ROOT=... AG_GROWER_SLUG=... AG_FARM_SLUG=... \
    python render_terrain_derivatives.py --field ia-r1 --out /path/grid.png
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

import basemap as _bm
import rasterio.warp

LAYER_ORDER = [
    ("dem_conditioned.tif", "Elevation (filled DEM)", "m", "terrain", False),
    ("hillshade.tif", "Hillshade", "", "gray", False),
    ("slope_degrees.tif", "Slope", "\u00b0", "YlOrBr", False),
    ("aspect_degrees.tif", "Aspect", "\u00b0 (0=N, cw)", None, False),
    ("flow_accumulation.tif", "Flow accumulation (D8)", "log\u2081\u2080 upstream cells", "viridis", True),
    ("topographic_wetness_index.tif", "Wetness index (TWI)", "", "YlGnBu", False),
    ("tpi.tif", "Topographic position", "m", "RdBu_r", False),
    ("relative_elevation.tif", "Relative elevation", "m", "RdBu_r", False),
    ("erosion_proxy.tif", "Erosion proxy (LS)", "log\u2081\u2080 index", "YlOrRd", True),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field", required=True, help="field slug under the farm")
    ap.add_argument("--grower", default=os.environ.get("AG_GROWER_SLUG", ""), help="grower slug (or env)")
    ap.add_argument("--farm", default=os.environ.get("AG_FARM_SLUG", ""), help="farm slug (or env)")
    ap.add_argument("--out", required=True, type=Path, help="output PNG path")
    args = ap.parse_args()

    root = Path(os.environ["DATA_PIPELINE_DATA_ROOT"]) / "data-pipeline"
    fdir = root / "growers" / args.grower / "farms" / args.farm / "fields" / args.field
    tdir = fdir / "derived" / "terrain"
    bpath = fdir / "boundary" / "field_boundary.geojson"
    if not bpath.exists():
        cands = list(fdir.glob("boundary/*.geojson"))
        if not cands:
            raise SystemExit(f"no field boundary under {fdir/'boundary'}")
        bpath = cands[0]
    fields = gpd.read_file(bpath).to_crs("EPSG:4326")

    # --- field-local frame, same library as every other static figure ------
    # (lib/field_frame.py; references/field-map-frame.md). The DEM is warped
    # STRAIGHT into the rotated grid via a rotated GDAL geotransform — one
    # resample, no rotate-the-array step, so the metre grid is honest.
    import sys as _sys
    from math import cos as _c, sin as _s, radians as _rad
    from rasterio.transform import Affine
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import field_frame as _fflib

    fig, axes = plt.subplots(3, 3, figsize=(9.6, 9.2), constrained_layout=True)
    fig.canvas.draw()
    _rb = axes[0, 0].get_position()
    _sz = fig.get_size_inches()
    ff = _fflib.frame_for(fields, panel_h_in=_rb.height * _sz[1],
                         panel_w_in=_rb.width * _sz[0])
    poly_zone = fields.to_crs(ff.epsg).union_all()
    src_note = ""
    import raster_rules as _rr_rules
    _LW = max(float(ff.geometry.total_bounds[2]), float(ff.geometry.total_bounds[3]))
    _into_frame = lambda ds, dst_res: _fflib.reproject_into_frame(
        ds, ff, dst_res, poly_metric=poly_zone,
        margin_m=_rr_rules.VIEWPORT_FRAC * _LW + 2 * dst_res)

    for ax, (fn, title, unit, cmap, log) in zip(axes.ravel(), LAYER_ORDER):
        p = tdir / fn
        if not p.exists():
            ax.text(0.5, 0.5, f"missing\n{fn}", ha="center", va="center", fontsize=8)
            ax.axis("off")
            continue
        with rasterio.open(p) as ds:
            res_m = ds.res[0] * (111320 if ds.crs.is_geographic else 1)
            show, ext = _into_frame(ds, res_m)
        _bm.draw(ax, ff, ext, show.shape[0], show.shape[1])
        src_note = src_note or f"\u2248{res_m:.0f} m native grid"
        def _vminmax(m):
            d = np.array(np.ma.filled(m, np.nan), dtype="float64", copy=True).ravel()
            d = d[np.isfinite(d)]
            return (np.percentile(d, 2), np.percentile(d, 98)) if d.size else (0, 1)
        vmin, vmax = _vminmax(show)  # generic default; specific branches override
        import math as _math
        import palettes
        _cb_ticks = None
        _norm_obj = None
        if fn == "dem_conditioned.tif":
            _ecm, _enorm, _relief, _klass = palettes.dem_scale(show)
            cmap = _ecm
            vmin, vmax = _enorm.vmin, _enorm.vmax
            title = (f"Elevation ({_klass} stretch P2\u2013P98, "
                     f"{_relief:.0f} m relief)")
        elif fn == "topographic_wetness_index.tif":
            _tc, _tn, _tt = palettes.twi_scale(show)
            cmap, vmin, vmax, _cb_ticks = _tc, _tn.vmin, _tn.vmax, _tt
        elif fn == "slope_degrees.tif":
            # plot slope in % (the management unit); % class ticks stay round
            show = np.ma.masked_array(100.0 * np.tan(np.radians(np.ma.getdata(show))),
                                      mask=np.ma.getmaskarray(show))
            title, unit = "Slope", "%"
            _sc, _sn, _st = palettes.slope_scale(show)
            cmap = _sc
            vmin, vmax = _sn.vmin, _sn.vmax
            _cb_ticks = _st
        elif fn in ("tpi.tif", "relative_elevation.tif"):
            # signed about 0 -> diverging norm centered on 0 (standard rule:
            # a diverging map needs its neutral at the meaningful midpoint)
            _mag = np.abs(np.ma.filled(show, np.nan))
            _mag = _mag[np.isfinite(_mag)]
            _cap = max(float(np.percentile(_mag, 99)), 0.5) if _mag.size else 1.0
            _norm_obj = matplotlib.colors.TwoSlopeNorm(vcenter=0.0,
                                                       vmin=-_cap, vmax=_cap)
            vmin = vmax = None
            title = f"{title} (±{_cap:.1f} m at P99)"
        if log:
            show = np.ma.masked_where(show <= 0, show)
            if show.count():
                show = np.ma.log10(show)
                vmin, vmax = _vminmax(show)
        if cmap is None:  # aspect: cyclic
            im = ax.imshow(show, cmap="hsv", vmin=0, vmax=360,
                           extent=list(ext), origin="upper")
        else:
            _kw = {}
            if _norm_obj is not None:
                _kw["norm"] = _norm_obj
            else:
                _kw["vmin"], _kw["vmax"] = vmin, vmax
            im = ax.imshow(show, cmap=cmap, extent=list(ext), origin="upper",
                           **_kw)
        cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03,
                          **({"ticks": _cb_ticks} if _cb_ticks else {}))
        cb.set_label(unit, fontsize=6); cb.ax.tick_params(labelsize=5)
        _L, _R, _B, _T = _fflib.view_extent(*ext)
        ax.set_xlim(_L, _R); ax.set_ylim(_B, _T)
        ff.geometry.dissolve().boundary.plot(ax=ax, color="red", lw=1.2)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel(_fflib.crs_note(ff), fontsize=5.6)
        ax.set_ylabel("field-local m", fontsize=6)
        ax.tick_params(labelsize=5.8)
        _fflib.decorate(ax, ff, arrow_r=0.10, arrow_fs=10, callout=False)
    fig.suptitle(f"{args.field} — terrain derivatives ({src_note})", fontsize=11)
    fig.text(0.0, -0.012, "rasters warped into the field-local frame in one resample \u2014 "
             "hillshade lighting rotates with the frame", fontsize=6, color="#6b7280")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
