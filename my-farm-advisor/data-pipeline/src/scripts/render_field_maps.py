#!/usr/bin/env python3
"""Render per-field composite maps: terrain hillshade, soil survey, crop classification.

Produces a one-row-per-field figure from whatever runtime layers exist under
``$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/``:

* terrain: ``terrain/dem/dem_clipped.tif`` -> hillshade + elevation contours
* soil:    ``soil/*/ssurgo_soil_types.geojson`` or ``soil/slga_asf/clay_0-5cm.tif``
           (SSURGO-style polygons, or a soil-property raster)
* imagery: ``worldcereal/wc_croptype_classification_*_<year>_*.tif`` (optional, --year)

Great Lakes (Natural Earth 10 m, shared/geoadmin/lakes/lakes.geojson) are overlaid
when present so US/CA maps keep geographic context. Output goes to
``<field>/field_maps/field_map_<field>_<YYYY-MM-DD>.png``.

Runtime data is read via DATA_PIPELINE_DATA_ROOT (see lib/runtime_paths.py);
nothing here writes outside that root.

Usage:
    python render_field_maps.py --grower elvtr-demo --farm demo-us --field ia-r1
    python render_field_maps.py --grower elvtr-demo --farm demo-au   # all fields
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib import cm, colors, patches
from matplotlib.colors import ListedColormap
from mpl_toolkits.axes_grid1 import make_axes_locatable

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.runtime_paths import RuntimePaths  # noqa: E402


def read_tif(path: Path):
    with rasterio.open(path) as src:
        data = src.read(1).astype("float64")
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        return data, src.bounds, src.crs


def read_tif_geo(path: Path, max_px: int = 512, nearest: bool = False):
    """Read band 1 reprojected to EPSG:4326. Returns (data, (w,e,s,n))."""
    from rasterio.warp import Resampling, reproject, transform_bounds
    from rasterio.transform import from_bounds as fb

    with rasterio.open(path) as src:
        w, s, e, n = transform_bounds(src.crs, "EPSG:4326", src.bounds.left, src.bounds.bottom,
                                      src.bounds.right, src.bounds.top)
        ny = max(int(max_px * (n - s) / max(e - w, 1e-9)), 32)
        out = np.empty((ny, max_px), dtype="float64")
        reproject(
            rasterio.band(src, 1), out, src_transform=src.transform, src_crs=src.crs,
            dst_transform=fb(w, s, e, n, max_px, ny), dst_crs="EPSG:4326",
            resampling=Resampling.nearest if nearest else Resampling.bilinear,
        )
        nodata = src.nodata
    if nodata is not None:
        out[out == nodata] = np.nan
    out[out <= -100] = np.nan
    return out, (w, e, s, n)


def read_geojson(path: Path):
    gj = json.loads(path.read_text())
    geoms = []
    props = []
    for feat in gj.get("features", []):
        g = feat["geometry"]
        if g is None:
            continue
        if g["type"] == "Polygon":
            poly_rings = [g["coordinates"]]
        elif g["type"] == "MultiPolygon":
            poly_rings = g["coordinates"]
        else:
            continue
        rings = [r for r in (np.array(ring, dtype=float)[:, :2] for poly in poly_rings for ring in poly)
                 if r.ndim == 2 and r.shape[0] >= 3]
        geoms.append(rings)
        props.append(feat.get("properties", {}))
    return geoms, props


def draw_polys(ax, geoms, face=None, edge="red", lw=1.2, z=5):
    for i, rings in enumerate(geoms):
        for r_i, ring in enumerate(rings):
            if np.ndim(ring) != 2 or np.shape(ring)[0] < 3 or np.shape(ring)[1] != 2:
                continue
            fc = face[i] if isinstance(face, list) else face
            ax.add_patch(
                patches.Polygon(
                    ring, closed=True, facecolor=fc if fc else "none",
                    edgecolor=edge, linewidth=lw, zorder=z, fill=fc is not None,
                )
            )


def hillshade(dem: np.ndarray, dx: float = 30.0, az=315.0, alt=45.0) -> np.ndarray:
    """Slope/aspect hillshade (matplotlib LightSource-free, in projected meters)."""
    lat0 = np.pi / 180 * 45  # mid-latitude approximation; fine for shading
    yy, xx = np.gradient(dem, dx * 1.0, dx / max(np.cos(lat0), 0.2))
    slope = np.pi / 2.0 - np.arctan(np.hypot(xx, yy))
    aspect = np.arctan2(-xx, yy)
    azr, altr = np.radians(az), np.radians(alt)
    hs = (
        np.sin(altr) * np.sin(slope)
        + np.cos(altr) * np.cos(slope) * np.cos(azr - aspect)
    )
    return np.clip(hs, 0, 1)



def _dem_source_label(field_dir: Path) -> str:
    """Name the DEM the resolver actually selected (recorded in the terrain
    manifest) instead of a hard-coded provider string."""
    try:
        import json

        manifest = field_dir / "manifests" / "dem_terrain_manifest.json"
        if not manifest.exists():
            return "DEM"
        sel = json.loads(manifest.read_text()).get("selected_source") or {}
        name = str(sel.get("source_name") or sel.get("adapter_name") or "DEM")
        res = sel.get("resolution_m")
        return f"{name} ({res:g} m)" if isinstance(res, (int, float)) else name
    except Exception:  # noqa: BLE001 — cosmetic label
        return "DEM"


def panel_terrain(ax, field_dir: Path, boundary):
    dems = sorted(field_dir.glob("terrain/dem/dem_clipped.tif"))
    if not dems:
        ax.text(0.5, 0.5, "no DEM", ha="center", va="center", transform=ax.transAxes)
        return False
    out, (w, e, s, n) = read_tif_geo(dems[0])
    ys = np.linspace(n, s, out.shape[0])
    xs = np.linspace(w, e, out.shape[1])
    m_per_deg = 111_320.0 * np.cos(np.radians(np.mean(ys)))
    dx = (xs[1] - xs[0]) * m_per_deg
    hs = hillshade(np.nan_to_num(out, nan=float(np.nanmedian(out))), dx=dx)
    ax.imshow(hs, cmap="gray", extent=(w, e, s, n), vmin=0, vmax=1, origin="upper")
    levels = np.linspace(np.nanmin(out), np.nanmax(out), 8)
    cs = ax.contour(xs, ys, out, levels=levels, colors="0.25", linewidths=0.5, alpha=0.6)
    ax.clabel(cs, fmt="%.0f m", fontsize=6)
    draw_polys(ax, boundary)
    ax.set_title(f"Terrain — hillshade + elevation contours ({_dem_source_label(field_dir)})", fontsize=8)
    return True


def panel_soil(ax, field_dir: Path, boundary, bbox, lakes):
    polys = sorted(field_dir.glob("soil/ssurgo_soil_types.geojson")) + sorted(
        field_dir.glob("soil/*/ssurgo_soil_types.geojson"))
    rasters = sorted(field_dir.glob("soil/*/clay_0-5cm.tif")) + sorted(
        field_dir.glob("soil/clay_0-5cm.tif"))
    geoms, props = [], []
    for cand in polys:
        try:
            g, pr = read_geojson(cand)
        except Exception:
            continue
        if g and pr:
            geoms, props = g, pr
            break
    if geoms:
        names = [p.get("compname") or p.get("mapunit_name") or p.get("component")
                 or p.get("musym") or p.get("mukey", "soil") for p in props]
        uniq = sorted(set(names))
        cmap = matplotlib.colormaps["tab20"].resampled(max(len(uniq), 3))
        idx = {n: i for i, n in enumerate(uniq)}
        faces = [cmap(idx[n] % 20 % cmap.N) for n in names]
        draw_polys(ax, geoms, face=faces, edge="0.15", lw=0.6, z=4)
        draw_polys(ax, boundary, face=None, edge="red", lw=1.6, z=6)
        ax.legend(
            handles=[patches.Patch(facecolor=cmap(i % cmap.N), label=n) for i, n in enumerate(uniq[:8])],
            fontsize=5.5, loc="best", framealpha=0.85,
        )
        ax.set_title("Soil survey — map units / components (SSURGO, national, SoilGrids)", fontsize=8)
        return True
    if rasters:
        data, (w, e, s, n) = read_tif_geo(rasters[0])
        im = ax.imshow(data, cmap="YlOrBr", extent=(w, e, s, n), origin="upper")
        draw_polys(ax, boundary)
        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="4%", pad=0.05)
        plt.colorbar(im, cax=cax).ax.tick_params(labelsize=6)
        ax.set_title("Soil clay % (0–5 cm, national atlas)", fontsize=8)
        return True
    ax.text(0.5, 0.5, "no soil data", ha="center", va="center", transform=ax.transAxes)
    return False


def panel_crop(ax, field_dir: Path, boundary, year: str | None):
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
        data_i, geo_i = read_tif_geo(cand, nearest=True)
        known_i = np.isin(np.nan_to_num(data_i, nan=-1).astype(int), list(labels))
        cov_i = float(known_i.mean())
        if best is None or cov_i > best[0]:
            best = (cov_i, data_i, geo_i)
    cov, data, (w, e, s, n) = best
    if cov < 0.25:
        return False
    known = np.isin(np.nan_to_num(data, nan=-1).astype(int), list(labels))
    data = np.where(known, data, np.nan)
    vals, cnts = np.unique(data[~np.isnan(data)].astype(int), return_counts=True)
    pairs = sorted(zip(cnts.tolist(), vals.tolist()), reverse=True)
    shown = [int(v) for _, v in pairs if int(v) in labels][:10]
    n_bins = max(len(shown), 2)
    lut = np.full(300, 0)
    for i, v in enumerate(shown):
        lut[v] = i
    remapped = np.where(np.isnan(data), 0, lut[np.clip(np.nan_to_num(data, nan=0).astype(int), 0, 299)])
    cmap = matplotlib.colormaps["tab20"].resampled(n_bins)
    im = ax.imshow(np.ma.masked_invalid(remapped), cmap=cmap, vmin=-0.5, vmax=n_bins - 0.5,
                   extent=(w, e, s, n), origin="upper")
    draw_polys(ax, boundary)
    ax.legend(
        handles=[patches.Patch(facecolor=cmap(shown.index(v)),
                               label=f"{labels[v]} ({int(dict(zip(vals, cnts))[v])} px)") for v in shown],
        fontsize=5.5, loc="best", framealpha=0.85,
    )
    cov_pct = int(100 * float(np.isfinite(data).mean()))
    ax.set_title(f"Crop type — WorldCereal default model, per-year inference ({cov_pct}% coverage)", fontsize=8)
    return True


def load_lakes(root: Path):
    p = root / "data-pipeline" / "shared" / "geoadmin" / "lakes" / "lakes.geojson"
    if not p.exists():
        return None, None
    try:
        return read_geojson(p)
    except Exception:
        return None, None


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
    fields = [Path(args.field)] if args.field else sorted(
        p.name for p in (farm_dir / "fields").iterdir() if p.is_dir()
    )
    lakes = load_lakes(root)
    today = dt.date.today().isoformat()

    for fid in fields:
        fdir = farm_dir / "fields" / fid
        bpath = fdir / "boundary" / "field_boundary.geojson"
        if not bpath.exists():
            continue
        boundary, _ = read_geojson(bpath)
        minx = min(r[:, 0].min() for rings in boundary for r in rings)
        maxx = max(r[:, 0].max() for rings in boundary for r in rings)
        miny = min(r[:, 1].min() for rings in boundary for r in rings)
        maxy = max(r[:, 1].max() for rings in boundary for r in rings)
        pad = 0.008 * max(maxx - minx, maxy - miny)
        bbox = (minx - pad, maxx + pad, miny - pad, maxy + pad)

        # decide which panels have content on throwaway axes, then draw only those
        tmpfig, taxes = plt.subplots(1, 3, figsize=(1, 1))
        draws = [lambda ax: panel_terrain(ax, fdir, boundary),
                 lambda ax: panel_soil(ax, fdir, boundary, bbox, lakes),
                 lambda ax: panel_crop(ax, fdir, boundary, args.year)]
        probes = [bool(draws[i](taxes[i])) for i in range(3)]
        plt.close(tmpfig)
        npanels = max(sum(probes), 1)
        fig, axes = plt.subplots(1, npanels, figsize=(4.5 * npanels + 2.0, 4.6))
        axes = np.atleast_1d(axes)
        idx = 0
        for ok, draw in zip(probes, draws):
            if ok:
                draw(axes[idx])
                idx += 1
            elif not any(probes):
                draw(axes[0])
        from matplotlib.ticker import FuncFormatter, MaxNLocator
        for ax in axes:
            ax.set_xlim(bbox[0], bbox[1])
            ax.set_ylim(bbox[2], bbox[3])
            ax.xaxis.set_major_locator(MaxNLocator(4))
            ax.yaxis.set_major_locator(MaxNLocator(4))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.3f}"))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.3f}"))
            ax.tick_params(labelsize=6)
            if lakes[0] is not None:
                lgeoms, _ = lakes
                for rings in lgeoms:
                    near = [r for r in rings if r[:, 0].max() > bbox[0] - 3 and r[:, 0].min() < bbox[1] + 3
                            and r[:, 1].max() > bbox[2] - 3 and r[:, 1].min() < bbox[3] + 3]
                    if not near:
                        continue
                    cx = np.mean([r[:, 0].mean() for r in rings])
                    cy = np.mean([r[:, 1].mean() for r in rings])
                    if bbox[0] - 0.5 <= cx <= bbox[1] + 0.5 and bbox[2] - 0.5 <= cy <= bbox[3] + 0.5:
                        continue
                    draw_polys(ax, near, face="#9ecae1", edge="none", lw=0, z=1)
        fig.suptitle(
            f"{args.grower} / {args.farm} / {fid} — field-boundary-aware data stack ({today})",
            fontsize=10,
        )
        fig.tight_layout()
        out = fdir / "field_maps" / f"field_map_{fid}_{today}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        plt.close(fig)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
