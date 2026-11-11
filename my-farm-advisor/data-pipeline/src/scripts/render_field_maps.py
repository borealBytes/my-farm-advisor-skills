#!/usr/bin/env python3
"""Render per-field composite maps: terrain hillshade, soil survey, crop
classification — in the field-local UTM frame (CONTRACT below).

Produces a one-row-per-field figure from whatever runtime layers exist under
``$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/``:

* terrain: ``terrain/dem/dem_clipped.tif`` -> hillshade + elevation contours
* soil:    ``soil/*/ssurgo_soil_types.geojson`` or ``soil/slga_asf/clay_0-5cm.tif``
           (SSURGO-style polygons, or a soil-property raster)
* imagery: ``worldcereal/wc_croptype_classification_*_<year>_*.tif`` (optional, --year)

FIELD-MAP FRAME CONTRACT (lib/field_frame.py — same axes and arrow on
every panel): metres; x=0 at the west edge of the field's bounding box AFTER
best-fit rotation to the long-edge-horizontal pose; y=0 at its south edge;
boxed true-north arrow + rotation callout; distance from metre tick axes, no
scale bar. Center-pivot circles
and other orientation-free footprints keep rot=0 but still get arrow + bar.
Great Lakes (Natural Earth 10 m, shared/geoadmin/lakes/lakes.geojson) are
drawn when they fall inside the framed view so US/CA maps keep context.
Output goes to ``<field>/field_maps/field_map_<field>_<YYYY-MM-DD>.png``.

Runtime data is read via DATA_PIPELINE_DATA_ROOT (see lib/runtime_paths.py);
nothing here writes outside that root.

Usage:
    python render_field_maps.py --grower demo-grower --farm demo-us --field ia-r1
    python render_field_maps.py --grower demo-grower --farm demo-au   # all fields
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np
import rasterio
import rasterio.warp
from matplotlib import patches
from matplotlib.ticker import MaxNLocator

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_frame as ff  # noqa: E402
import basemap as _bm


# ---------------------------------------------------------------- geometry

def _frame_for(boundary_gdf: gpd.GeoDataFrame) -> ff.Frame:
    """Best-fit pose, except orientation-free footprints (isoperimetric
    quotient > 0.85 — center-pivot circles): those pin rot=0."""
    g = boundary_gdf.to_crs(4326).geometry.union_all()
    gu = g.buffer(0)
    iq = 4 * math.pi * gu.area / (gu.length ** 2) if gu.length > 0 else 0
    return ff.frame_for(boundary_gdf, panel_h_in=4.2, panel_w_in=4.5,
                        force_rot=0.0 if iq > 0.85 else None)


def _to_frame_coords(gdf: gpd.GeoDataFrame, f: ff.Frame) -> gpd.GeoDataFrame:
    """Any-CRS polygons -> this frame's (metres, rotated, origin SW) plane."""
    gu = gdf.to_crs(f.epsg)
    r = math.radians(f.rot)
    cr, sr = math.cos(r), math.sin(r)
    e0, n0 = f.e0, f.n0

    def xf(geom):
        if geom is None or geom.is_empty:
            return geom
        def mapper(x, y, z=None):
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            dE = x - e0
            dN = y - n0
            return (dE * cr + dN * sr, -dE * sr + dN * cr)
        return __import__("shapely").ops.transform(mapper, geom)

    out = gu.copy()
    out["geometry"] = [xf(gm) for gm in gu.geometry]
    return out.set_crs(f"EPSG:{f.epsg}", inplace=False)


def _read_tif_in_frame(path: Path, f: ff.Frame, dst_res: float, nearest=False):
    import raster_rules as _rr
    _tb = f.geometry.total_bounds
    with rasterio.open(path) as ds:
        data, extent = ff.reproject_into_frame(
            ds, f, dst_res,
            margin_m=_rr.VIEWPORT_FRAC * max(_tb[2], _tb[3]) + 2 * dst_res,
            resampling=rasterio.warp.Resampling.nearest if nearest
            else rasterio.warp.Resampling.bilinear)
    return data, extent


def _dst_res_for(f: ff.Frame, target_px: int = 1100) -> float:
    w = max(f.geometry.total_bounds[2], 50.0)
    return float(np.clip(w / target_px, 0.5, 10.0))


# ---------------------------------------------------------------- panels

def hillshade(dem: np.ndarray, dx: float = 2.0, az=315.0, alt=45.0,
              exag: float = 1.0) -> np.ndarray:
    """Hillshade on the uniform metre grid (frame coords -> isotropic dx).
    ``exag`` vertically exaggerates the gradient: x2-x3 on tile land where
    micro-relief is the signal, x1 on orographic relief (Esri practice)."""
    filled = np.where(np.isfinite(dem), dem, np.nanmedian(dem[np.isfinite(dem)])
                      if np.isfinite(dem).any() else 0.0)
    yy, xx = np.gradient(filled, dx * (1.0 / exag), dx * (1.0 / exag))
    slope = np.pi / 2.0 - np.arctan(np.hypot(xx, yy))
    aspect = np.arctan2(-xx, yy)
    azr, altr = math.radians(az), math.radians(alt)
    hs = (np.sin(altr) * np.sin(slope)
          + np.cos(altr) * np.cos(slope) * np.cos(azr - aspect))
    return np.clip(hs, 0, 1)


def _dem_source_label(field_dir: Path) -> str:
    """Name the DEM the resolver actually selected (recorded in the terrain
    manifest) instead of a hard-coded provider string."""
    try:
        manifest = field_dir / "manifests" / "dem_terrain_manifest.json"
        if not manifest.exists():
            return "DEM"
        sel = json.loads(manifest.read_text()).get("selected_source") or {}
        name = str(sel.get("source_name") or sel.get("adapter_name") or "DEM")
        name = name.split(" [")[0]  # drop dataset GUIDs from the title
        if len(name) > 42:
            name = name[:40] + "…"
        res = sel.get("resolution_m")
        return f"{name} ({res:g} m)" if isinstance(res, (int, float)) else name
    except Exception:  # noqa: BLE001 — cosmetic label
        return "DEM"


def _draw_frame_boundary(ax, f: ff.Frame):
    b = f.geometry
    b.boundary.plot(ax=ax, color="red", linewidth=1.4)


def _frame_axes(ax, f: ff.Frame, extent):
    _L, _R, _B, _T = ff.view_extent(0, extent[1], 0, extent[3])
    ax.set_xlim(_L, _R)
    ax.set_ylim(_B, _T)
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.tick_params(labelsize=6)
    ax.set_xlabel(f"m from SW corner (rot {f.rot:+.1f}°)" if f.rot != 0
                  else "m from SW corner", fontsize=6)
    ax.set_ylabel("field-local m", fontsize=6)


def panel_terrain(ax, field_dir: Path, f: ff.Frame, dst_res: float):
    dems = sorted(field_dir.glob("terrain/dem/dem_clipped.tif"))
    if not dems:
        ax.text(0.5, 0.5, "no DEM", ha="center", va="center", transform=ax.transAxes)
        return False
    out, extent = _read_tif_in_frame(dems[0], f, dst_res)
    arr = np.ma.filled(out, np.nan).astype(float)
    _bm.draw(ax, f, (0, extent[1], 0, extent[3]), arr.shape[0], arr.shape[1])
    import palettes
    _ecm, _enorm, _relief, _klass = (palettes.dem_scale(arr[np.isfinite(arr)])
                                     if np.isfinite(arr).any()
                                     else (None, None, 0.0, "low"))
    hs = hillshade(arr, dx=dst_res, exag=2.5 if _relief < 10 else
                   (1.5 if _relief < 50 else 1.0))
    ax.imshow(hs, cmap="gray", extent=(0, extent[1], 0, extent[3]),
              vmin=0, vmax=1, origin="upper", zorder=1)
    if _ecm is not None:
        ax.imshow(np.ma.masked_invalid(arr), cmap=_ecm, norm=_enorm, alpha=0.55,
                  extent=(0, extent[1], 0, extent[3]), origin="upper", zorder=2)
    if np.isfinite(arr).any():
        lo, hi = np.nanmin(arr), np.nanmax(arr)
        if hi - lo > 1.0:  # contours only where relief is mappable
            ys = np.linspace(extent[3], 0, arr.shape[0])
            xs = np.linspace(0, extent[1], arr.shape[1])
            n = int(float(np.clip((hi - lo) / max(dst_res, (hi - lo) / 8), 3, 8)))
            cs = ax.contour(xs, ys, arr, levels=np.linspace(lo, hi, n),
                            colors="0.25", linewidths=0.5, alpha=0.6)
            ax.clabel(cs, fmt="%.0f m", fontsize=5)
    _draw_frame_boundary(ax, f)
    ff.decorate(ax, f, arrow_xy=(0.86, 0.70), callout=False)
    ax.set_title(f"Terrain — hillshade + {_klass} tint, {_relief:.0f} m relief "
                 f"({_dem_source_label(field_dir)})", fontsize=8)
    _frame_axes(ax, f, extent)
    return True


def panel_soil(ax, field_dir: Path, f: ff.Frame, lakes_gdf):
    polys = sorted(field_dir.glob("soil/ssurgo_soil_types.geojson")) + sorted(
        field_dir.glob("soil/*/ssurgo_soil_types.geojson"))
    rasters = sorted(field_dir.glob("soil/*/clay_0-5cm.tif")) + sorted(
        field_dir.glob("soil/clay_0-5cm.tif"))
    gdf = None
    for cand in polys:
        try:
            g = gpd.read_file(cand)
            if not g.empty:
                gdf = g
                break
        except Exception:
            continue
    if gdf is not None:
        names = []
        for col in ("compname", "mapunit_name", "component", "musym"):
            if col in gdf.columns:
                names = gdf[col].astype(str).tolist()
                break
        else:
            names = ["soil"] * len(gdf)
        uniq = sorted(set(names))
        import palettes as _pal
        _cols = _pal.categorical(len(uniq))
        cmap = matplotlib.colors.ListedColormap(_cols)
        idx = {n: i for i, n in enumerate(uniq)}
        fgdf = _to_frame_coords(gdf, f)
        _tb = f.geometry.total_bounds
        _r = _dst_res_for(f)
        _bm.draw(ax, f, (0, _tb[2], 0, _tb[3]),
                 max(256, int(_tb[3] / _r)), max(256, int(_tb[2] / _r)))
        f.geometry.plot(ax=ax, facecolor="none", edgecolor="none", zorder=0)
        fgdf.plot(ax=ax, color=[cmap(idx[n] % cmap.N) for n in names],
                  edgecolor="0.15", linewidth=0.5, zorder=4)
        _draw_frame_boundary(ax, f)
        if lakes_gdf is not None and not lakes_gdf.empty:
            view = gpd.GeoDataFrame(geometry=[f.geometry.union_all().buffer(200)],
                                    crs=f"EPSG:{f.epsg}").to_crs(4326).total_bounds
            sel = lakes_gdf.to_crs(4326)
            sel = sel[sel.intersects(gpd.GeoDataFrame(
                geometry=[__import__("shapely").box(*view)], crs="EPSG:4326").geometry.iloc[0])]
            if not sel.empty:
                _to_frame_coords(sel, f).plot(ax=ax, facecolor="#9ecae1",
                                              edgecolor="none", zorder=2)
        ax.legend(handles=[patches.Patch(facecolor=cmap(i % cmap.N), label=n)
                           for i, n in enumerate(uniq[:8])],
                  fontsize=5.5, loc="best", framealpha=0.85)
        ax.set_title("Soil survey — map units / components (SSURGO, national, SoilGrids)",
                     fontsize=8)
        ff.decorate(ax, f, arrow_xy=(0.86, 0.70), callout=False)
        return True
    if rasters:
        data, extent = _read_tif_in_frame(rasters[0], f, _dst_res_for(f))
        import palettes as _pal
        _d = np.ma.masked_invalid(data)
        _bm.draw(ax, f, (0, extent[1], 0, extent[3]), _d.shape[0], _d.shape[1])
        if np.nanmax(_d) > 120:  # ISRIC integer storage = % x10
            _d = _d / 10.0
        _cm, _norm, _ticks = _pal.soil_scale("clay", _d)
        im = ax.imshow(_d, cmap=_cm, norm=_norm, alpha=0.82,
                       extent=(0, extent[1], 0, extent[3]), origin="upper", zorder=1)
        _draw_frame_boundary(ax, f)
        fig = ax.get_figure()
        cax = fig.add_axes([ax.get_position().x1 + 0.01, ax.get_position().y0,
                            0.02, ax.get_position().height])
        _cb = plt.colorbar(im, cax=cax,
                           **({"ticks": _ticks} if _ticks else {}))
        _cb.set_label("clay %", fontsize=6)
        _cb.ax.tick_params(labelsize=6)
        ax.set_title("Soil clay % (0–5 cm, national atlas)", fontsize=8)
        ff.decorate(ax, f, arrow_xy=(0.86, 0.70), callout=False)
        return True
    ax.text(0.5, 0.5, "no soil data", ha="center", va="center", transform=ax.transAxes)
    return False


def panel_crop(ax, field_dir: Path, f: ff.Frame, year: str | None, dst_res: float):
    cands = sorted(field_dir.glob(f"worldcereal/wc_croptype_classification_*_{year or ''}_*.tif"))
    if not cands:
        return False
    labels = {0: "wheat", 1: "barley", 2: "rye", 3: "oats", 4: "maize", 5: "sorghum",
              6: "rice", 8: "millet", 9: "vegetables", 10: "beet", 11: "dry pulses/legumes",
              12: "sunflower", 13: "soybean", 14: "rapeseed", 16: "groundnuts",
              18: "potatoes", 20: "tobacco", 21: "grass/fodder", 22: "sugarcane",
              254: "no crop (in season)", 255: "not cropland"}
    best = None
    for cand in cands:
        data_i, ext = _read_tif_in_frame(cand, f, dst_res, nearest=True)
        known_i = np.isin(np.ma.filled(data_i, np.nan), list(labels))
        cov_i = float(known_i.mean())
        if best is None or cov_i > best[0]:
            best = (cov_i, data_i, ext)
    cov, data, extent = best
    _bm.draw(ax, f, (0, extent[1], 0, extent[3]), data.shape[0], data.shape[1])
    if cov < 0.25:
        return False
    vals, cnts = np.unique(np.ma.filled(data, np.nan)[
        np.isin(np.ma.filled(data, np.nan), list(labels))].astype(int),
        return_counts=True)
    pairs = sorted(zip(cnts.tolist(), vals.tolist()), reverse=True)
    shown = [int(v) for _, v in pairs if int(v) in labels][:10]
    n_bins = max(len(shown), 2)
    lut = np.full(300, 0)
    for i, v in enumerate(shown):
        lut[v] = i
    filled = np.where(np.isfinite(np.ma.filled(data, np.nan)),
                      np.nan_to_num(np.ma.filled(data, np.nan)), 0).astype(int)
    remapped = np.where(np.isfinite(np.ma.filled(data, np.nan)),
                        lut[np.clip(filled, 0, 299)], np.nan)
    cmap = matplotlib.colormaps["tab20"].resampled(n_bins)
    im = ax.imshow(np.ma.masked_invalid(remapped), cmap=cmap, vmin=-0.5, vmax=n_bins - 0.5,
                   extent=(0, extent[1], 0, extent[3]), origin="upper", zorder=1)
    _draw_frame_boundary(ax, f)
    counts = dict(zip(vals.tolist(), cnts.tolist()))
    ax.legend(handles=[patches.Patch(facecolor=cmap(shown.index(v)),
                                     label=f"{labels[v]} ({int(counts[v])} px)") for v in shown],
              fontsize=5.5, loc="best", framealpha=0.85)
    cov_pct = int(100 * float(np.isfinite(np.ma.filled(data, np.nan)).mean()))
    ax.set_title(f"Crop type — WorldCereal default model, per-year inference ({cov_pct}% coverage)",
                 fontsize=8)
    ff.decorate(ax, f, arrow_xy=(0.86, 0.70), callout=False)
    return True


# ---------------------------------------------------------------- driver

def load_lakes(root: Path):
    p = root / "data-pipeline" / "shared" / "geoadmin" / "lakes" / "lakes.geojson"
    if not p.exists():
        return None
    try:
        return gpd.read_file(p)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="runtime root (default: DATA_PIPELINE_DATA_ROOT)")
    ap.add_argument("--grower", required=True)
    ap.add_argument("--farm", required=True)
    ap.add_argument("--field", default=None, help="field id; default: every field in the farm")
    ap.add_argument("--year", default=None, help="WorldCereal year filter, e.g. 2023")
    args = ap.parse_args()

    import os

    root = Path(args.root or os.environ["DATA_PIPELINE_DATA_ROOT"]).resolve()
    farm_dir = root / "data-pipeline" / "growers" / args.grower / "farms" / args.farm
    fields = [Path(args.field).name] if args.field else sorted(
        p.name for p in (farm_dir / "fields").iterdir() if p.is_dir()
    )
    lakes = load_lakes(root)
    today = dt.date.today().isoformat()

    for fid in fields:
        fdir = farm_dir / "fields" / fid
        bpath = fdir / "boundary" / "field_boundary.geojson"
        if not bpath.exists():
            continue
        boundary_gdf = gpd.read_file(bpath)
        f = _frame_for(boundary_gdf)
        dst_res = _dst_res_for(f)

        draws = [lambda ax: panel_terrain(ax, fdir, f, dst_res),
                 lambda ax: panel_soil(ax, fdir, f, lakes),
                 lambda ax: panel_crop(ax, fdir, f, args.year, dst_res)]
        tmpfig, taxes = plt.subplots(1, 3, figsize=(1, 1))
        probes = [bool(draw(taxes[i])) for i, draw in enumerate(draws)]
        plt.close(tmpfig)
        npanels = max(sum(probes), 1)
        fig, axes = plt.subplots(1, npanels, figsize=(4.5 * npanels + 2.0, 4.6))
        axes = np.atleast_1d(axes)
        idx = 0
        for ok, draw in zip(probes, draws):
            if ok:
                draw(axes[idx])
                _frame_axes(axes[idx], f,
                            (0, max(f.geometry.total_bounds[2], 1),
                             0, max(f.geometry.total_bounds[3], 1)))
                idx += 1
            elif not any(probes):
                draw(axes[0])
        fig.text(0.01, 0.012, ff.crs_note(f), ha="left", va="bottom",
                 fontsize=6, color="#4b5563", transform=fig.transFigure)
        _tg = os.environ.get("AG_TITLE_GROWER") or (
            "█████" if args.grower.lower().startswith("elvtr") else args.grower)
        fig.suptitle(
            f"{_tg} / {args.farm} / {fid} — field-boundary-aware data stack ({today})",
            fontsize=10,
        )
        fig.tight_layout(rect=(0, 0.045, 1, 1))
        out = fdir / "field_maps" / f"field_map_{fid}_{today}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
