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

LAYER_ORDER = [
    ("dem_conditioned.tif", "Elevation (filled DEM)", "m", "terrain", False),
    ("hillshade.tif", "Hillshade", "", "gray", False),
    ("slope_degrees.tif", "Slope", "\u00b0", "YlOrBr", False),
    ("aspect_degrees.tif", "Aspect", "\u00b0 (0=N, cw)", None, False),
    ("flow_accumulation.tif", "Flow accumulation (D8)", "upstream cells", "viridis", True),
    ("topographic_wetness_index.tif", "Wetness index (TWI)", "", "YlGnBu", False),
    ("tpi.tif", "Topographic position", "m", "RdBu_r", False),
    ("relative_elevation.tif", "Relative elevation", "m", "RdBu_r", False),
    ("erosion_proxy.tif", "Erosion proxy (LS)", "", "YlOrRd", True),
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
    poly = fields.union_all()
    b = fields.total_bounds
    pad = 0.002
    bounds = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)

    fig, axes = plt.subplots(3, 3, figsize=(9.6, 9.2), constrained_layout=True)
    src_note = ""
    for ax, (fn, title, unit, cmap, log) in zip(axes.ravel(), LAYER_ORDER):
        p = tdir / fn
        if not p.exists():
            ax.text(0.5, 0.5, f"missing\n{fn}", ha="center", va="center", fontsize=8)
            ax.axis("off")
            continue
        with rasterio.open(p) as ds:
            arr = ds.read(1, masked=True).astype("float64")
            ext0 = ds.bounds
            crs = ds.crs
            res = ds.res[0]
            tr = ds.transform
        from rasterio.features import geometry_mask
        from rasterio.transform import from_bounds
        from rasterio.warp import transform as wtransform
        # Panel axes are always lat/lon; rasters may be projected (US 3DEP clips) —
        # mask in the raster's own CRS, then re-express bounds in EPSG:4326.
        poly_use = poly if str(crs).upper() == "EPSG:4326" else gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326").to_crs(crs).geometry.iloc[0]
        gm = geometry_mask([poly_use], out_shape=arr.shape,
                           transform=tr, invert=True)
        o = wtransform(crs, "EPSG:4326", [ext0[0], ext0[2]], [ext0[1], ext0[3]])
        ext = (o[0][0], o[1][0], o[0][1], o[1][1])
        if crs.is_geographic:
            res_m = res * 111320
        else:
            res_m = res
        src_note = src_note or f"\u2248{res_m:.0f} m native grid"
        show = np.ma.masked_where(~gm, np.ma.masked_invalid(np.array(arr, dtype="float64", copy=True)))
        def _vminmax(m):
            d = np.array(np.ma.filled(m, np.nan), dtype="float64", copy=True).ravel()
            d = d[np.isfinite(d)]
            return (np.percentile(d, 2), np.percentile(d, 98)) if d.size else (0, 1)
        vmin, vmax = _vminmax(show)
        if log:
            show = np.ma.masked_where(show <= 0, show)
            if show.count():
                show = np.ma.log10(show)
                vmin, vmax = _vminmax(show)
        if cmap is None:  # aspect: cyclic
            im = ax.imshow(show, cmap="hsv", vmin=0, vmax=360,
                           extent=[ext[0], ext[2], ext[1], ext[3]], origin="upper")
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03); cb.set_label(unit, fontsize=6)
        else:
            im = ax.imshow(show, cmap=cmap, vmin=vmin, vmax=vmax,
                           extent=[ext[0], ext[2], ext[1], ext[3]], origin="upper")
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03); cb.set_label(unit, fontsize=6)
        cb.ax.tick_params(labelsize=5)
        fields.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.2)
        ax.set_title(title, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"{args.field} — terrain derivatives ({src_note})", fontsize=11)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=170)
    plt.close(fig)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
