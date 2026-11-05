#!/usr/bin/env python3
"""Render per-field soil property maps (SoilGrids / ASF clips) + terrain relief.

Reference implementation for soil-gridded rasters produced by
ingest/download_soilgrids.py (and any clip with the same layout). Draws one
PNG per field: hillshaded DEM relief underland + requested property bands as
small-multiples, field outline, and a stats box from the field stats parquet.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource
import geopandas as gpd

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import DATA_ROOT, farm_boundary_path, field_boundary_path  # pyright: ignore[reportMissingImports]

from reporting_bootstrap import ensure_skill_path  # pyright: ignore[reportMissingImports]

try:
    ensure_skill_path("soilgrids-global")
    import soilgrids_global as _sg  # pyright: ignore[reportMissingImports]
except Exception:  # pragma: no cover - module optional, raw values shown as-is
    _sg = None

BAND_LABELS = {
    "clay": ("Clay 0–5 cm", "%", "viridis"),
    "silt": ("Silt 0–5 cm", "%", "cividis"),
    "sand": ("Sand 0–5 cm", "%", "copper"),
    "phh2o": ("pH (H$_2$O) 0–5 cm", "pH", "RdYlBu_r"),
    "phhcl": ("pH (CaCl$_2$) 0–5 cm", "pH", "RdYlBu_r"),
    "cec": ("CEC 0–5 cm", "cmol(+)/kg", "magma"),
    "soc": ("Organic carbon 0–5 cm", "gC/kg", "YlGn"),
    "nitrogen": ("Total N 0–5 cm", "g/kg", "YlGnBu"),
    "bdod": ("Bulk density 0–5 cm", "Mg/m$^3$", "PiYG"),
    "cfvo": ("Vol. fragments 0–5 cm", "cm$^3$/dm$^3$", "Blues"),
    # ASF (Australia) native band names — values already in true units
    "phcalciumchloride": ("pH (CaCl$_2$) 0–5 cm", "pH", "RdYlBu_r"),
    "carbon": ("Organic carbon 0–5 cm", "%", "YlGn"),
    "bulkdensity": ("Bulk density 0–5 cm", "g/cm$^3$", "PiYG"),
}


def _clip_raster(path: Path, bounds, out: Path, res_deg: float = 0.0018) -> Path:
    """Reproject+clip a source raster (any CRS) to a WGS84 bbox on a SHARED grid.

    The destination transform is built manually from `bounds` (no snapping),
    so every band/depth clip shares identical pixel geometry and the field
    mask aligns across panels.
    """
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    minx, miny, maxx, maxy = bounds
    width = max(1, int(math.ceil((maxx - minx) / res_deg)))
    height = max(1, int(math.ceil((maxy - miny) / res_deg)))
    transform = from_origin(minx, maxy, res_deg, res_deg)

    with rasterio.open(path) as src:
        if src.crs is None:
            raise SystemExit(f"{path}: missing CRS")
        dst_crs = "EPSG:4326"
        profile = src.profile
        profile.update(
            crs=dst_crs, transform=transform, width=width, height=height, count=1
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )
    return out


def _mask_to_polygon(arr, transform, polygon):
    """Set pixels outside the field polygon to NaN so rasters end at the boundary."""
    from rasterio.features import rasterize

    mask = rasterize(
        [(polygon, 1)], out_shape=arr.shape, transform=transform, fill=0, dtype="uint8"
    )
    out = np.array(arr, dtype="float64")
    out[mask == 0] = np.nan
    return out


def _geo_ticks(ax):
    import matplotlib.ticker as mticker

    ax.tick_params(labelsize=6)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
    ax.xaxis.set_major_locator(mticker.MaxNLocator(4))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(4))


def _panel_frame_labels(ax, ff, _fflib) -> None:
    """Axis furniture every static field panel carries (see field-map-frame.md)."""
    ax.set_xlabel(_fflib.crs_note(ff), fontsize=5.6)
    ax.set_ylabel("field-local m", fontsize=6)
    ax.tick_params(labelsize=5.8)
    ax.grid(alpha=0.15, lw=0.4)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlim(0, float(ff.geometry.total_bounds[2]))
    ax.set_ylim(0, float(ff.geometry.total_bounds[3]))
    _fflib.decorate(ax, ff, arrow_r=0.085, arrow_fs=8.5, callout=False,
                    arrow_xy=(0.955, 0.05))


_BAND_LEGEND = {  # ISRIC/SoilGrids standard legend files (vendored, data/isric_legends/)
    "clay": "CLYPPT", "silt": "SLTPPT", "sand": "SNDPPT",
    "phh2o": "PHIHOX", "phhcl": "PHIHOX", "cec": "CECSOL",
    "soc": "ORCDRC", "nitrogen": "ORCDRC", "bdod": "BLDFINE",
}


def _band_norm(key: str):
    """ListedColormap + BoundaryNorm straight from the vendored ISRIC TSVs."""
    stem = _BAND_LEGEND.get(key.lower())
    if stem is None:
        return None
    import csv as _csv
    from matplotlib.colors import ListedColormap, BoundaryNorm
    p = (Path(__file__).resolve().parent.parent / "data" / "isric_legends"
         / f"{stem}.txt")
    if not p.exists():
        return None
    rows = []
    _div = 10.0 if stem == "PHIHOX" else 1.0   # SoilGrids pH legend is x10
    with open(p, newline="") as fh:
        for row in _csv.DictReader(fh, delimiter="\t"):
            c = int(row["COLOR"])
            lo, hi = float(row["MINIMUM"]) / _div, float(row["MAXIMUM"]) / _div
            rows.append((lo, hi, ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255,
                                  (c & 255) / 255)))
    if len(rows) < 3:
        return None
    rows.sort()
    bounds, cols = [], []
    for lo, hi, col in rows:
        if not bounds or abs(bounds[-1] - lo) > 1e-9:
            bounds.append(lo)
        bounds.append(hi)
        cols.append(col)
    import numpy as _np
    bounds = _np.unique(_np.array(bounds))
    keep = []
    for i in range(len(cols)):
        lo, hi = rows[i][0], rows[i][1]
        j0 = int(_np.searchsorted(bounds, lo))
        j1 = int(_np.searchsorted(bounds, hi))
        if j1 > j0:
            keep.append((j0, j1, cols[i]))
    # rebuild per-bin colors over the full boundary grid
    full = [cols[0]] * (len(bounds) - 1)
    for j0, j1, c in keep:
        for j in range(j0, min(j1, len(full))):
            full[j] = c
    return ListedColormap(full), BoundaryNorm(bounds, len(full)), bounds


def _band_cmap(key: str):
    stem = _BAND_LEGEND.get(key.lower())
    if stem is not None:
        try:
            from generate_soil_texture_triangles import _isric_cmap
            cmap, _, _ = _isric_cmap(stem)
            return cmap
        except Exception:
            pass
    return "viridis"


def render_field(
    *,
    field_slug: str,
    boundary_path: Path,
    raster_paths: dict[str, Path],
    dem_path: Path | None,
    out_png: Path,
    title_extra: str = "",
) -> Path:
    fields = gpd.read_file(boundary_path)

    # field-local frame (lib/field_frame.py): every panel of every static
    # figure shares one metre grid, auto-rotated to fit, arrows on.
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import field_frame as _fflib
    import rasterio
    from rasterio.enums import Resampling as _Rsm
    fig = None
    band_keys = list(raster_paths)
    n = len(band_keys)
    total = n + 1
    cols = min(3, total)
    rows = -(-total // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.1 * cols + 1.2, 3.5 * rows), constrained_layout=True)
    axes = np.atleast_1d(axes).ravel()
    fig.canvas.draw()
    _rb = axes[0].get_position()
    _sz = fig.get_size_inches()
    ff = _fflib.frame_for(fields, panel_h_in=_rb.height * _sz[1],
                         panel_w_in=_rb.width * _sz[0])
    poly_zone = fields.to_crs(ff.epsg).union_all()

    def _square_pad(a, e):
        """Pad a panel up to a square extent, anchored at the NW corner
        (imshow origin='upper'): extra space falls east and south, so the
        identical frame rect is shared by every panel."""
        import numpy as _np
        w, h = e[1] - e[0], e[3] - e[2]
        if abs(w - h) < 1e-9:
            return a, e
        s = max(w, h)
        resx, resy = w / a.shape[1], h / a.shape[0]
        nc, nr = int(round(s / resx)), int(round(s / resy))
        import numpy as _npma
        is_masked = __import__("numpy").ma.isMaskedArray(a)
        if is_masked:
            out = __import__("numpy").ma.masked_array(
                _npma.full((nr, nc), _npma.nan), mask=True)
            out[nr - a.shape[0]:, :a.shape[1]] = a   # data bottom-anchored
        else:
            out = _npma.full((nr, nc), _npma.nan)
            out[nr - a.shape[0]:, :a.shape[1]] = a
        return out, (e[0], e[0] + s, e[2], e[2] + s)  # origin (0,0) preserved

    def _dst_res_of(path, default_m):
        with rasterio.open(path) as ds:
            import raster_rules as _rrl
            return _rrl.cell_m_of(ds.crs, ds.res[0], lon=ff.lon0) or default_m

    def _frame_show(src_path, default_m=250.0, scale_key=None):
        with rasterio.open(src_path) as ds:
            res = _dst_res_of(src_path, default_m)
            arr, ext = _fflib.reproject_into_frame(
                ds, ff, res, poly_metric=poly_zone)
            arr, ext = _square_pad(arr, ext)
            if scale_key is not None:
                _m = np.ma.getmaskarray(arr)
                _d = np.ma.getdata(arr)
                arr = np.ma.masked_invalid(_sg.apply_scale(_d, scale_key))
                arr = np.ma.masked_array(np.ma.getdata(arr),
                                         mask=_m | np.ma.getmaskarray(arr))
            return arr, ext

    ls = LightSource(azdeg=315, altdeg=45)
    ax0 = axes[0]
    if dem_path and dem_path.exists():
        arr, ext = _frame_show(dem_path, default_m=30.0)
        hs = np.ma.masked_invalid(ls.hillshade(np.ma.filled(arr, float("nan")), vert_exag=1.2))
        ax0.imshow(hs, cmap="gray", vmin=0, vmax=1,
                   extent=[ext[0], ext[1], ext[2], ext[3]], origin="upper")
        flat = arr.compressed()
        norm = (plt.Normalize(np.percentile(flat, 2), np.percentile(flat, 98))
                if flat.size else plt.Normalize(0, 1))
        ax0.imshow(arr, cmap="terrain", alpha=0.12,
                   extent=[ext[0], ext[1], ext[2], ext[3]], origin="upper", norm=norm)
        cb0 = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="terrain"), ax=ax0,
                           fraction=0.046, pad=0.03)
        cb0.set_label("elevation (m)", fontsize=6)
        cb0.ax.tick_params(labelsize=6)
        ax0.set_title("Terrain (DEM hillshade)", fontsize=9)
    else:
        ax0.text(0.5, 0.5, "no DEM", ha="center")
    ff.geometry.dissolve().boundary.plot(ax=ax0, color="red", lw=1.4)
    _panel_frame_labels(ax0, ff, _fflib)

    for ax, key in zip(axes[1:], band_keys):
        label, unit, _cmap = BAND_LABELS.get(key, (key, "", "viridis"))
        scale_key = (key if (raster_paths[key].name.startswith("soilgrids_")
                             and _sg is not None and key in _sg.BAND_SPECS) else None)
        arr, ext = _frame_show(raster_paths[key], scale_key=scale_key)
        if key == "cec" and not raster_paths[key].name.startswith("soilgrids_"):
            # ASF CEC arrives in its own native scale; do not assert SoilGrids units.
            label, unit = "CEC 0–5 cm (ASF native units)", ""
        bn = _band_norm(key)
        if bn is not None:
            bn_cm, bn_norm, bn_b = bn
            _lo, _hi = float(np.nanmin(arr)), float(np.nanmax(arr))
            _i0 = max(int(np.searchsorted(bn_b, _lo)) - 3, 0)
            _i1 = min(int(np.searchsorted(bn_b, _hi)) + 4, len(bn_b) - 1)
            _b = bn_b[_i0:_i1 + 1]
            _cmap2 = __import__("matplotlib.colors", fromlist=["ListedColormap"])                .ListedColormap([bn_cm.colors[i] for i in range(_i0, _i1)])
            _norm2 = __import__("matplotlib.colors", fromlist=["BoundaryNorm"])                .BoundaryNorm(_b, _i1 - _i0)
            im = ax.imshow(arr, cmap=_cmap2, norm=_norm2,
                           extent=[ext[0], ext[1], ext[2], ext[3]],
                           origin="upper")
            _step = max(1, (_i1 - _i0) // 5)
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03,
                              ticks=list(_b[::_step]))
        else:
            im = ax.imshow(arr, cmap=_band_cmap(key),
                           extent=[ext[0], ext[1], ext[2], ext[3]], origin="upper")
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
        cb.set_label(unit, fontsize=6)
        cb.ax.tick_params(labelsize=5.6)
        mean_v = float(np.nanmean(arr))
        ax.set_title(f"{label} — mean {mean_v:.1f}", fontsize=8.5)
        ff.geometry.dissolve().boundary.plot(ax=ax, color="red", lw=1.4)
        _panel_frame_labels(ax, ff, _fflib)

    for _ax in axes[total:]:
        _ax.axis("off")
    fig.suptitle(f"{field_slug} — gridded soil properties + relief {title_extra}", fontsize=11)
    # force every used panel onto an identical square box so all axes share
    # one frame rect (colorbars make the auto boxes differ otherwise)
    fig.canvas.draw()
    _used = axes[:total]
    _ws = [a.get_position().width for a in _used]
    _hs = [a.get_position().height for a in _used]
    _side = min(min(_ws), min(_hs))
    for _a, _p in zip(_used, [a.get_position() for a in _used]):
        _a.set_position([_p.x0 + (_p.width - _side) / 2,
                         _p.y0 + (_p.height - _side) / 2, _side, _side])
    _ = ff.geometry.total_bounds
    for _a in _used:
        _a.set_xlim(0, float(_[2]))
        _a.set_ylim(0, float(_[3]))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=170)
    plt.close(fig)
    return out_png


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--farm-boundary", type=Path, default=None, help="defaults to env AG_* farm boundary")
    parser.add_argument("--field", required=True, help="field slug (dir under farm fields/)")
    parser.add_argument("--bands", default="clay,phhcl,cec,soc", help="comma list of clipped band keys")
    parser.add_argument("--soil-dir", type=Path, required=True, help="dir holding <field>/soilgrids_<band>_<depth>.tif clips")
    parser.add_argument("--depth", default="0-5cm")
    parser.add_argument("--dem", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title-extra", default="")
    args = parser.parse_args()

    boundary = args.farm_boundary
    if boundary is None:
        grower = os.environ.get("AG_GROWER_SLUG", "default-grower")
        farm = os.environ.get("AG_FARM_SLUG", "default-farm")
        boundary = farm_boundary_path(grower, farm)
    fields = gpd.read_file(boundary)
    # fall back to the per-field canonical boundary
    grower = os.environ.get("AG_GROWER_SLUG", "default-grower")
    farm = os.environ.get("AG_FARM_SLUG", "default-farm")
    field_boundary = field_boundary_path(grower, farm, args.field)
    raster_paths = {}
    for band in args.bands.split(","):
        band = band.strip()
        for pattern in (
            args.soil_dir / f"{args.field}" / f"soilgrids_{band}_{args.depth}.tif",
            args.soil_dir / f"soilgrids_{band}_{args.depth}.tif",
            args.soil_dir / f"{args.field}" / f"{band}_{args.depth}.tif",
            args.soil_dir / f"{band}_{args.depth}.tif",
        ):
            if pattern.exists():
                raster_paths[band] = pattern
                break
        else:
            print(f"  warn  no clip for band={band} depth={args.depth} under {args.soil_dir}")
    out = render_field(
        field_slug=args.field,
        boundary_path=field_boundary,
        raster_paths=raster_paths,
        dem_path=args.dem,
        out_png=args.out,
        title_extra=args.title_extra,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
