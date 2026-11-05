#!/usr/bin/env python3
"""USDA soil-texture-triangle figures from field soil component tables.

Draws the canonical 12-class USDA triangle (vertex geometry transcribed from
the CRAN `soiltexture` package, USDA.TT definition — not from memory) and
plots one point per soil component of a field, sized by its relative
abundance (comppct_r), plus a star for the comppct-weighted topsoil mean.

Input: the field's soil table (``ssurgo_full.csv`` for SSURGO and the
schema-compatible national surveys — Ontario DSS etc.), long-format with
columns: compname, comppct_r, hzdept_r, claytotal_r, silttotal_r,
sandtotal_r. Horizons are averaged to the first (topsoil) horizon per
component.

Usage:
    python generate_soil_texture_triangles.py --soil-csv <ssurgo_full.csv> \
        --label ia-r1 --out ia-r1_texture_triangle.png

Notes:
    * sand/silt/clay are percent <0.05 mm / 0.002-0.05 mm / <0.002 mm.
    * Rows with missing particle-size splits are dropped (honest gap, printed).
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Polygon as MplPolygon

# --- USDA triangle geometry -------------------------------------------------
# Fractions (clay, silt, sand), 1-indexed P01..P26, from CRAN soiltexture
# 1.5.3 (USDA.TT$tt.points). Class polygons reference these indices.
_POINTS = [
    (0.550, 0.000, 0.450), (0.600, 0.400, 0.000), (0.350, 0.000, 0.650),
    (0.350, 0.200, 0.450), (0.400, 0.150, 0.450), (0.400, 0.400, 0.200),
    (0.400, 0.600, 0.000), (0.200, 0.000, 0.800), (0.200, 0.275, 0.525),
    (0.275, 0.275, 0.450), (0.275, 0.500, 0.225), (0.275, 0.525, 0.200),
    (0.275, 0.725, 0.000), (0.150, 0.000, 0.850), (0.100, 0.000, 0.900),
    (0.075, 0.400, 0.525), (0.075, 0.500, 0.425), (0.125, 0.800, 0.075),
    (0.125, 0.875, 0.000), (0.000, 0.150, 0.850), (0.000, 0.300, 0.700),
    (0.000, 0.500, 0.500), (0.000, 0.800, 0.200), (1.000, 0.000, 0.000),
    (0.000, 0.000, 1.000), (0.000, 1.000, 0.000),
]
# class name -> (vertex indices 1-based, pastel fill)
_CLASSES = {
    "clay": ([24, 1, 5, 6, 2], "#b3504d"),
    "silty clay": ([2, 6, 7], "#c37b77"),
    "sandy clay": ([1, 3, 4, 5], "#a34643"),
    "clay loam": ([5, 4, 10, 11, 12, 6], "#d59a97"),
    "silty clay loam": ([6, 12, 13, 7], "#e0b5b2"),
    "sandy clay loam": ([3, 8, 9, 10, 4], "#c98c88"),
    "loam": ([10, 9, 16, 17, 11], "#f5deb3"),
    "silty loam": ([11, 17, 22, 23, 18, 19, 13, 12], "#e6c892"),
    "sandy loam": ([8, 14, 21, 22, 17, 16, 9], "#f0d9a8"),
    "silt": ([18, 23, 26, 19], "#d9c28f"),
    "loamy sand": ([14, 15, 20, 21], "#ffe9b0"),
    "sand": ([15, 25, 20], "#fff3cf"),
}


def _to_xy(clay: float, silt: float, sand: float) -> tuple[float, float]:
    """Ternary (fractions summing to 1) -> cartesian: sand on the base, clay up."""
    return sand + 0.5 * clay, (math.sqrt(3) / 2.0) * clay


def _poly_verts(idx: list[int]) -> np.ndarray:
    return np.array([_to_xy(*_POINTS[i - 1]) for i in idx])


def texture_class(clay: float, silt: float, sand: float) -> str | None:
    """Point-in-polygon against the canonical class polygons."""
    x, y = _to_xy(clay, silt, sand)
    for name, (idx, _) in _CLASSES.items():
        verts = _poly_verts(idx)
        # ray cast
        inside = False
        n = len(verts)
        j = n - 1
        for i in range(n):
            xi, yi = verts[i]
            xj, yj = verts[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
                inside = not inside
            j = i
        if inside:
            return name
    return None


def _topsoil_components(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    need = {"compname", "comppct_r", "hzdept_r", "claytotal_r", "silttotal_r", "sandtotal_r"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"soil table {csv_path} lacks columns: {sorted(missing)}")
    top = df[df["hzdept_r"] == df.groupby(["mukey", "compname"])["hzdept_r"].transform("min")]
    g = top.groupby(["mukey", "compname", "comppct_r"], as_index=False)[
        ["claytotal_r", "silttotal_r", "sandtotal_r"]
    ].mean()
    g = g.dropna(subset=["claytotal_r", "silttotal_r", "sandtotal_r"])
    g = g[g["comppct_r"] > 0]
    total = g["claytotal_r"] + g["silttotal_r"] + g["sandtotal_r"]
    g["clay"], g["silt"], g["sand"] = g["claytotal_r"] / total, g["silttotal_r"] / total, g["sandtotal_r"] / total
    # field-area share: comppct_r is WITHIN its map unit, so weight each
    # component by its mukey's clipped polygon area (equal weight where the
    # polygon table lacks a mukey). This turns rel-%-of-map-unit into % of field.
    g["share_in_mukey"] = g["comppct_r"] / g.groupby("mukey")["comppct_r"].transform("sum")
    areas = None
    gj = csv_path.parent / "ssurgo_soil_types.geojson"
    if gj.exists():
        try:
            import geopandas as _gpd
            poly = _gpd.read_file(gj).to_crs(6933)
            poly["mukey"] = poly["mukey"].astype(str)
            areas = poly.assign(a=poly.geometry.area).groupby("mukey")["a"].sum()
        except Exception:
            areas = None
    g["mukey"] = g["mukey"].astype(str)
    if areas is not None and g["mukey"].isin(areas.index).all():
        g["mukey_w"] = g["mukey"].map(areas)
    else:
        g["mukey_w"] = 1.0
        print("  (polygon areas unavailable for some mukeys — equal mukey weights)")
    g["field_share"] = g["mukey_w"] * g["share_in_mukey"]
    g["field_share"] = 100.0 * g["field_share"] / g["field_share"].sum()
    # one pin per series x texture cell (0.5 % grid): identical/adjacent
    # duplicates merge and their shares add
    g["_k"] = list(zip(g["compname"], (g["clay"] * 200).round(),
                       (g["silt"] * 200).round(), (g["sand"] * 200).round()))
    g = g.groupby("_k", as_index=False).agg(
        compname=("compname", "first"), mukey=("mukey", "first"),
        comppct_r=("field_share", "sum"),
        clay=("clay", "mean"), silt=("silt", "mean"), sand=("sand", "mean"))
    g["class"] = [texture_class(c, s, sa) for c, s, sa in zip(g["clay"], g["silt"], g["sand"])]
    return g


def _grid_components(soil_dir: Path) -> tuple[pd.DataFrame, str]:
    """Texture points from a gridded soil directory (SoilGrids 250 m, AU Soil
    Atlas, any provider writing clay_/silt_/sand_<depth>.tif next to the field).
    Every valid raster cell inside the boundary becomes one point."""
    import rasterio

    tifs = sorted(soil_dir.rglob("*clay_*.tif"))
    if not tifs:
        raise SystemExit(f"no clay grids under {soil_dir}")
    depth = tifs[0].name.split("clay_")[-1][:-4]
    arrays = {}
    for frac in ("clay", "silt", "sand"):
        hits = sorted(soil_dir.rglob(f"*{frac}_{depth}.tif"))
        if not hits:
            raise SystemExit(f"missing {frac}_{depth}.tif under {soil_dir}")
        with rasterio.open(hits[0]) as ds:
            arrays[frac] = ds.read(1).astype("float64")
    valid = np.isfinite(arrays["clay"]) & np.isfinite(arrays["silt"]) & np.isfinite(arrays["sand"])
    total = arrays["clay"] + arrays["silt"] + arrays["sand"]
    valid &= total >= 70  # honest gap: too little reported to normalize
    idx = np.argwhere(valid)
    if len(idx) > 900:  # stride-thin for plotting; star still uses ALL cells
        idx = idx[np.linspace(0, len(idx) - 1, 900).astype(int)]
    rows = []
    for r, c in idx:
        t = total[r, c]
        rows.append({"clay": arrays["clay"][r, c] / t, "silt": arrays["silt"][r, c] / t,
                     "sand": arrays["sand"][r, c] / t})
    grid = pd.DataFrame(rows)
    grid["class"] = [texture_class(a, b, c) for a, b, c in zip(grid["clay"], grid["silt"], grid["sand"])]
    # weighted mean over ALL cells, not the thinned sample
    allr = np.argwhere((np.isfinite(arrays["clay"]) & np.isfinite(arrays["silt"])
                        & np.isfinite(arrays["sand"]) & (total >= 70)))
    mean = {f: float(np.mean(arrays[f][allr[:, 0], allr[:, 1]] / total[allr[:, 0], allr[:, 1]]))
            for f in ("clay", "silt", "sand")}
    n_all = len(allr)
    return grid, f"{depth}|{mean['clay']}|{mean['silt']}|{mean['sand']}|{n_all}"


def render(csv_path: Path | None, label: str, out: Path, source_note: str = "SSURGO",
           soil_dir: Path | None = None) -> None:
    grid_note = None
    if soil_dir is not None:
        comp, note = _grid_components(soil_dir)
        grid_note = note.split("|")
        comp["comppct_r"] = 1.0
        comp["mukey"] = np.arange(len(comp))
        comp["compname"] = "cell"
        top = comp
    else:
        comp = _topsoil_components(csv_path)
    if comp.empty:
        raise SystemExit(f"no usable particle-size rows in {csv_path or soil_dir}")

    fig, ax = plt.subplots(figsize=(7.6, 6.6))
    # class fills
    for name, (idx, color) in _CLASSES.items():
        ax.add_patch(MplPolygon(_poly_verts(idx), closed=True, facecolor=color,
                                edgecolor="#7a4a44", linewidth=0.7, alpha=0.9))
    # class labels at polygon centroids, white halo so points never swallow them
    import matplotlib.patheffects as pe
    for name, (idx, _) in _CLASSES.items():
        cx, cy = _poly_verts(idx).mean(axis=0)
        ax.text(cx, cy, name, ha="center", va="center", fontsize=6.4, zorder=7,
                color="#3f2a26", style="italic",
                path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])

    # percent scales on ALL THREE edges — classic NRCS layout:
    #   % SAND below the base, increasing left -> right
    #   % CLAY along the RIGHT edge (horizontal clay lines meet it), to the apex
    #   % SILT along the LEFT edge (silt lines meet it), down to the silt corner
    sq3 = math.sqrt(3)
    for pct in range(10, 100, 10):
        f = pct / 100.0
        ax.plot(*zip(_to_xy(0, 1 - f, f), _to_xy(1, 0, 0)), color="#b08a7a", lw=0.3, alpha=0.6)
        ax.plot(*zip(_to_xy(f, 0, 1 - f), _to_xy(1, 0, 0)), color="#b08a7a", lw=0.3, alpha=0.6)
        ax.plot([1 - f, 0.5 * (1 - f)], [0, (sq3 / 2) * (1 - f)], color="#b08a7a", lw=0.3, alpha=0.6)
        ax.plot([f, f], [-0.004, -0.018], color="#3f2a26", lw=0.8)
        ax.text(f, -0.034, str(pct), fontsize=6.4, color="#3f2a26", ha="center", va="top")
        px, py = 1 - f / 2, (sq3 / 2) * f
        nx, ny = sq3 / 2, -0.5
        ax.plot([px, px + 0.012 * nx], [py, py + 0.012 * ny], color="#3f2a26", lw=0.8)
        ax.text(px + 0.030 * nx, py + 0.030 * ny, str(pct), fontsize=6.4, color="#3f2a26",
                ha="center", va="center", rotation=-60)
        px, py = (1 - f) / 2, (sq3 / 2) * (1 - f)
        nx, ny = -sq3 / 2, -0.5
        ax.plot([px, px + 0.012 * nx], [py, py + 0.012 * ny], color="#3f2a26", lw=0.8)
        ax.text(px + 0.030 * nx, py + 0.030 * ny, str(pct), fontsize=6.4, color="#3f2a26",
                ha="center", va="center", rotation=60)

    ax.add_patch(MplPolygon([_to_xy(0, 1, 0), _to_xy(0, 0, 1), _to_xy(1, 0, 0)],
                            closed=True, fill=False, edgecolor="#3f2a26", lw=1.6))
    ax.text(0.5, -0.108, "% SAND  \u2192", ha="center", fontsize=10, weight="bold", color="#3f2a26")
    ax.text(1.13, 0.30, "% CLAY  \u2197", fontsize=10, weight="bold", color="#3f2a26",
            rotation=-60, va="center")
    ax.text(-0.13, 0.30, "% SILT  \u2199", fontsize=10, weight="bold", color="#3f2a26",
            rotation=60, va="center")

    # component points, sized by comppct_r (grid cells: small translucent dots)
    sizes = 6 if grid_note else 18 + comp["comppct_r"] * 7.0
    _ = None  # placeholder
    xs, ys = zip(*(_to_xy(c, s, sa) for c, s, sa in zip(comp["clay"], comp["silt"], comp["sand"])))
    if grid_note:
        ax.scatter(xs, ys, s=34, c="#1d4ed8", zorder=5, alpha=0.55, linewidths=0)
    else:
        ax.scatter(xs, ys, s=sizes, c="#1d4ed8", edgecolors="white", linewidths=0.8, zorder=5, alpha=0.88)
        occupied = []
        for nm, (idx, _) in _CLASSES.items():
            cx0, cy0 = _poly_verts(idx).mean(axis=0)
            ww, hh = 0.0125 * len(nm) + 0.014, 0.032
            occupied.append((cx0 - ww / 2, cy0 - hh / 2, cx0 + ww / 2, cy0 + hh / 2))
        occupied.append((0.70, 0.66, 1.18, 0.98))  # star callout zone (top-right)
        _label_pins(ax, comp, sizes, occupied)

    # weighted field mean (comps: comppct-weighted; grid: all-cell weighted)
    if grid_note:
        mc, ms, msa = float(grid_note[1]), float(grid_note[2]), float(grid_note[3])
    else:
        w = comp["comppct_r"] / comp["comppct_r"].sum()
        mc, ms, msa = (float(np.average(comp[c], weights=w)) for c in ("clay", "silt", "sand"))
    mx, my = _to_xy(mc, ms, msa)
    mcls = texture_class(mc, ms, msa) or "unclassified"
    ax.scatter([mx], [my], marker="*", s=330, c="#f59e0b", edgecolors="#78350f",
               linewidths=0.9, zorder=6)
    # corner callout, top-right white space outside the triangle — never collides
    mean_kind = "cell-weighted" if grid_note else "comppct-weighted"
    ax.annotate(
        f"field mean ({mean_kind})\n{mcls} — clay {mc*100:.0f} / silt {ms*100:.0f} / sand {msa*100:.0f}",
        (mx, my), xytext=(0.985, 0.995), textcoords="axes fraction", fontsize=7.6,
        weight="bold", color="#78350f", zorder=8, ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.35", fc="#fffbeb", ec="#78350f", lw=0.8),
        arrowprops=dict(arrowstyle="->", color="#78350f", lw=0.9,
                        connectionstyle="arc3,rad=-0.28"),
    )

    if grid_note:
        unit = "one point per raster cell (thin-stride shown), star = weighted mean of all cells"
        n_note = f"{grid_note[4]} cells at {grid_note[0]}"
    else:
        unit = ("pins labelled soil series + % of FIELD area (map-unit polygons \u00d7 component share); "
                "size = field area; star = area-weighted mean")
        n_note = f"{len(comp)} pins"
    ax.set_title(
        f"{label} — soil texture classes (topsoil, {source_note.lower()})",
        fontsize=10.5, weight="bold", pad=14, loc="left",
    )
    ax.text(
        0, 1.005,
        f"{unit} | {n_note}",
        transform=ax.transAxes, fontsize=7.4, color="#4b5563",
    )
    ax.set_xlim(-0.16, 1.16)
    ax.set_ylim(-0.145, 0.95)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {out}")


def _hex_blend(white_frac: float, rgb) -> str:
    r, g, b = rgb
    r = round(255 * white_frac + r * (1 - white_frac))
    g = round(255 * white_frac + g * (1 - white_frac))
    b = round(255 * white_frac + b * (1 - white_frac))
    return f"#{r:02x}{g:02x}{b:02x}"


def _interp_profile(df: pd.DataFrame, col: str, bins: np.ndarray) -> np.ndarray | None:
    """Depth profile for one property: per component, piecewise-linear across
    horizon midpoints (constant beyond the first/last midpoint); components
    averaged weighted by comppct_r. The standard SSURGO interval interpolation."""
    series, weights = [], []
    for (_c, pct), sub in df.groupby(["compname", "comppct_r"]):
        sub = sub.dropna(subset=[col]).sort_values("hzdept_r")
        if sub.empty:
            continue
        mid = (sub["hzdept_r"] + sub["hzdepb_r"]) / 2.0
        val = sub[col]
        order = np.argsort(mid.values)
        mid, val = mid.values[order], val.values[order]
        keep = ~np.isnan(val)
        if keep.sum() == 0:
            continue
        series.append(np.interp(bins, mid[keep], val[keep]))
        weights.append(pct)
    if not series:
        return None
    w = np.asarray(weights, dtype=float)
    return (np.vstack(series) * w[:, None]).sum(axis=0) / w.sum()


def _label_pins(ax, comp: pd.DataFrame, sizes, occupied: list[tuple[float, float, float, float]]) -> None:
    """Series name + field-area % beside each pin. Radial candidate search at
    two distances x eight directions; boxes never land on a class name, the
    mean callout, or another label (falls back to least-overlapping)."""
    order = np.argsort(-comp["comppct_r"].values)
    boxes = list(occupied)

    def overlap(b):
        s = 0.0
        for q in boxes:
            s += max(0.0, min(b[2], q[2]) - max(b[0], q[0])) * max(0.0, min(b[3], q[3]) - max(b[1], q[1]))
        return s

    for i in order:
        r = comp.iloc[i]
        x, y = _to_xy(r.clay, r.silt, r.sand)
        share = float(r.comppct_r)
        label = f"{r.compname} {share:.1f}%" if share < 10 else f"{r.compname} {share:.0f}%"
        w, h = 0.0128 * len(label) + 0.022, 0.044
        rad0 = 0.014 + (float(sizes.values[i]) ** 0.5) * 0.0026
        best, best_score = None, np.inf
        for d in (rad0 + 0.014, rad0 + 0.058, rad0 + 0.105, rad0 + 0.155, rad0 + 0.21):
            for ang in (0, 30, 330, 60, 300, 90, 270, 15, 345, 75, 285, 120, 240, 150, 210, 180):
                a = math.radians(ang)
                bx, by = x + d * math.cos(a) - (w / 2 if ang in (90, 270, 80, 100, 260, 280) else (w if ang > 180 else 0)), \
                         y + d * math.sin(a) - h / 2
                box = (bx, by, bx + w, by + h)
                sc = overlap(box)
                if sc == 0.0:
                    best = box
                    break
                if sc < best_score:
                    best, best_score = box, sc
            if best and overlap(best) == 0.0:
                break
        boxes.append(best)
        ax.annotate(
            label, (x, y), xytext=(best[0], best[3]), fontsize=6.6, color="#111827",
            zorder=7, va="top", ha="left",
            bbox=dict(boxstyle="square,pad=0.16", fc="white", ec="#9ca3af", lw=0.4, alpha=0.93),
            arrowprops=dict(arrowstyle="-", color="#6b7280", lw=0.5, shrinkA=1, shrinkB=3),
        )


def render_horizon_table(csv_path: Path, label: str, out: Path, source_note: str = "SSURGO") -> None:
    """Color-coded component x horizon table with comppct-weighted,
    interval-interpolated 0-100 cm depth profiles beside it."""
    import matplotlib.gridspec as gridspec
    import matplotlib.patheffects as pe

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["claytotal_r"]).copy()
    df["slice"] = df["hzdept_r"].astype(int).astype(str) + "-" + df["hzdepb_r"].astype(int).astype(str) + " cm"
    g = df.groupby(["compname", "comppct_r", "slice"], as_index=False).agg(
        hzdept=("hzdept_r", "min"), om=("om_r", "mean"), ph=("ph1to1h2o_r", "mean"),
        awc=("awc_r", "mean"), clay=("claytotal_r", "mean"), sand=("sandtotal_r", "mean"),
    ).sort_values(["comppct_r", "hzdept"], ascending=[False, True])
    g = g.head(14)

    # --- field map units, colored by dominant component, field-share legend ---
    gj = csv_path.parent / "ssurgo_soil_types.geojson"
    map_units = None
    if gj.exists():
        import geopandas as _gpd
        _poly = _gpd.read_file(gj)
        _poly["mukey"] = _poly["mukey"].astype(str)
        _areas = (_poly.assign(a=_poly.to_crs(6933).geometry.area)
                        .groupby("mukey")["a"].sum())
        _d = df.dropna(subset=["comppct_r"]).copy()
        _d["mukey"] = _d["mukey"].astype(str)
        _dom = (_d.sort_values("comppct_r", ascending=False)
                  .groupby("mukey")["compname"].first())
        _top = _d[_d["hzdept_r"] == _d.groupby(["mukey", "compname"])["hzdept_r"].transform("min")]
        _top = _top.dropna(subset=["comppct_r"])
        _top = _top[_top["comppct_r"] > 0]
        _top["share"] = _top["comppct_r"] / _top.groupby("mukey")["comppct_r"].transform("sum")
        _top["field_share"] = _top["mukey"].map(_areas) * _top["share"]
        _fs = _top.groupby("compname")["field_share"].sum()
        _tot = float(_fs.sum())
        if _tot > 0:
            map_units = (_poly, _dom, _fs / _tot * 100.0)

    _ratios = ([1.05] if map_units is not None else []) + [1.45, 1.0]
    fig = plt.figure(figsize=(13.2 + (3.4 if map_units is not None else 0),
                              0.44 * len(g) + 1.6))
    gs = gridspec.GridSpec(1, len(_ratios), width_ratios=_ratios, wspace=0.12)
    idx_t = 1 if map_units is not None else 0
    ax_t = fig.add_subplot(gs[idx_t]); ax_t.axis("off")

    _col: dict = {}
    if map_units is not None:
        import matplotlib.patches as mpatches
        from matplotlib import colormaps as _cm
        _poly, _dom, _pct = map_units
        _names = sorted(_dom.dropna().unique())
        _cyc = _cm.get_cmap("tab20")
        _col = {n: _cyc(i / max(len(_names), 1) % 1.0 if len(_names) > 1 else 0.1)
                for i, n in enumerate(_names)}
        _poly = _poly.assign(comp=_poly["mukey"].map(_dom),
                             c=_poly["mukey"].map(_dom).map(_col))
        # field-local UTM metres, (0,0) pinned to the SW corner of the field
        # bounding box — degrees are noise at field scale
        _lon0 = float(_poly.dissolve().geometry.iloc[0].centroid.x)
        _lat0 = float(_poly.dissolve().geometry.iloc[0].centroid.y)
        _zone = int((_lon0 + 180) // 6) + 1
        _epsg = (32600 if _lat0 >= 0 else 32700) + _zone
        _gu = _poly.to_crs(_epsg)
        _x0, _y0, _, _ = _gu.total_bounds
        _gu = _gu.assign(geometry=_gu.geometry.translate(xoff=-_x0, yoff=-_y0))
        ax_m = fig.add_subplot(gs[0])
        _gu.plot(ax=ax_m, color=_gu["c"].fillna("#d1d5db"),
                 linewidth=0.4, edgecolor="#4b5563")
        _gu.dissolve().boundary.plot(ax=ax_m, color="#111827", lw=1.1)
        ax_m.set_xlabel(f"m E from SW corner (UTM {_zone})", fontsize=6.8)
        ax_m.set_ylabel("m N", fontsize=6.8)
        ax_m.tick_params(labelsize=6.4)
        ax_m.grid(alpha=0.18, lw=0.4)
        # north arrow, top-right, boxed for contrast
        ax_m.annotate("", xy=(0.90, 0.965), xytext=(0.90, 0.74),
                      xycoords="axes fraction",
                      arrowprops=dict(arrowstyle="-|>", lw=2.4, color="#111827",
                                      mutation_scale=16))
        ax_m.text(0.90, 0.985, "N", transform=ax_m.transAxes, fontsize=13,
                  fontweight="bold", ha="center", va="bottom", color="#111827",
                  bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#111827", lw=1.0))
        ax_m.set_title("map units — dominant component", fontsize=8.6, weight="bold", pad=13)
        _hand = [mpatches.Patch(facecolor=_col[n], edgecolor="#4b5563",
                                label=f"{n} — {float(_pct.get(n, 0)):.1f}% of field")
                 for n in _names if n in _col]
        ax_m.set_aspect("equal", adjustable="datalim")
        ax_m.legend(handles=_hand, fontsize=6.4, loc="upper left",
                    bbox_to_anchor=(0.0, -0.115), ncol=2, frameon=True, framealpha=0.95,
                    borderpad=0.5, labelspacing=0.4, columnspacing=0.9)
    cols = ["Component", "Rel. %", "Depth", "OM %", "pH", "AWC", "Clay %", "Sand %"]
    cells = [
        [r.compname, f"{r.comppct_r:.0f}", r.slice,
         "" if pd.isna(r.om) else f"{r.om:.1f}",
         "" if pd.isna(r.ph) else f"{r.ph:.1f}",
         "" if pd.isna(r.awc) else f"{r.awc:.2f}",
         f"{r.clay:.0f}", "" if pd.isna(r.sand) else f"{r.sand:.0f}"]
        for r in g.itertuples()
    ]
    tbl = ax_t.table(cellText=cells, colLabels=cols, loc="upper left", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(7.7)
    tbl.auto_set_column_width(col=(0, 2))
    tbl.scale(0.97, 1.28)
    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#1f2937"); cell.set_text_props(color="white", weight="bold")
            continue
        comp = cells[row - 1][0]
        if col == 0 and comp in _col:
            # row chips carry the map's own component colors — table rows and
            # polygons are one glance apart, same hue
            cell.set_facecolor(_col[comp])
            cell.set_text_props(ha="left", color="white", weight="bold",
                                path_effects=[pe.withStroke(linewidth=1.4, foreground="#111827")])
        elif row % 2 == 0:
            cell.set_facecolor("#f3f4f6")
        elif col == 0:
            cell.set_text_props(ha="left")
    fig.suptitle(
        f"{label} — soil horizon detail ({source_note.lower()})",
        fontsize=11, weight="bold", x=0.02, ha="left", y=1.045,
    )
    ax_t.text(0, 1.01, "component colors match the map at left | profiles at right: same "
              "table interpolated to continuous depth from 0 cm", transform=ax_t.transAxes,
              fontsize=7.4, color="#4b5563")

    # --- interpolated profiles (comppct-weighted, 5 cm bins) ---
    bins = np.arange(0, 101, 5.0)  # profile starts at the surface (0 cm)
    panels = [("OM %", _interp_profile(df, "om_r", bins), plt.get_cmap("Reds")),
              ("pH", _interp_profile(df, "ph1to1h2o_r", bins), plt.get_cmap("coolwarm_r")),
              ("AWC", _interp_profile(df, "awc_r", bins), plt.get_cmap("Blues"))]
    have = [(n, y, c) for n, y, c in panels if y is not None]
    # fifth profile: sand+silt+clay interpolated the same way, normalized to a
    # 100 % stack down the profile — you watch texture change with depth
    tex_curves = {}
    for key, tcol in (("sand", "sandtotal_r"), ("silt", "silttotal_r"), ("clay", "claytotal_r")):
        yy = _interp_profile(df, tcol, bins)
        if yy is not None:
            tex_curves[key] = yy
    has_tex = len(tex_curves) == 3
    # restrictive layers (SSURGO corestrictions, written by the soil ingest):
    # a red-hatched marker column right of the depth axis, one band per feature
    rfile = csv_path.parent / "ssurgo_restrictions.csv"
    restricts: list[tuple[str, float, float]] = []
    if rfile.exists():
        try:
            rdf = pd.read_csv(rfile).dropna(subset=["reskind", "resdept_r"])
            for (_kind, top, bot), grp in rdf.groupby(
                    ["reskind", "resdept_r", "resdepb_r"]):
                restricts.append((str(_kind), float(top), float(bot)))
        except BaseException:
            restricts = []
    has_restr = len(restricts) > 0
    known_restr = rfile.exists()
    def _restr_color(kind: str) -> str:
        k = kind.lower()
        if any(w in k for w in ("fragipan", "claypan", "duripan", "compacted", "plinthite", "ortstein")):
            return "#b45309"
        if any(w in k for w in ("bedrock", "substratum", "contact", "ice")):
            return "#374151"
        if any(w in k for w in ("water", "saturat", "perched", "aquic")):
            return "#1d4ed8"
        return "#7c2d12"
    n_cols2 = len(have) + (1 if has_tex else 0) + (1 if (has_restr or known_restr) else 0)
    ratios2 = [1] * (len(have) + (1 if has_tex else 0))
    if has_restr or known_restr:
        ratios2.append(0.62)
    gs2 = gridspec.GridSpecFromSubplotSpec(1, n_cols2, subplot_spec=gs[-1], wspace=0.30,
                                           width_ratios=ratios2)
    for i, (name, y, cmap) in enumerate(have):
        ax = fig.add_subplot(gs2[i])
        ax.plot(y, bins, color="#1f2937", lw=1.7)
        ax.fill_betweenx(bins, y, y.min(), alpha=0.25, color=cmap(0.6))
        ax.set_ylim(100, 0); ax.set_xlim(y.min() - (y.max()-y.min())*0.15 - 1e-9,
                                         y.max() + (y.max()-y.min())*0.15 + 1e-9)
        ax.text(0.5, 0.985, name, transform=ax.transAxes, ha="center", va="top",
                fontsize=7.6, weight="bold", color="#111827")
        ax.tick_params(labelsize=6.6)
        from matplotlib.ticker import MaxNLocator
        ax.xaxis.set_major_locator(MaxNLocator(3))
        ax.grid(alpha=0.25, lw=0.4)
    if has_tex:
        M = np.vstack([tex_curves["sand"], tex_curves["silt"], tex_curves["clay"]])
        M = np.clip(M, 0, None)
        M = M / M.sum(axis=0, keepdims=True) * 100.0
        s, si, c = M[0], M[1], M[2]
        axx = fig.add_subplot(gs2[len(have)])
        axx.fill_betweenx(bins, 0, s, color="#d9a066")
        axx.fill_betweenx(bins, s, s + si, color="#9aa5b1")
        axx.fill_betweenx(bins, s + si, 100, color="#b23a2f")
        # key sits mid-profile; use the fraction AT that depth, not the deepest bin
        for depth, frac, txt, cc in ((46, s[9] / 2, "sand", "#7c4a12"),
                                     (46, (s[9] + si[9] / 2), "silt", "#374151"),
                                     (46, (s[9] + si[9] + c[9] / 2), "clay", "#fef2f2")):
            axx.text(frac, depth, txt, fontsize=6.2, color=cc, ha="center", va="center",
                     path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])
        axx.set_ylim(100, 0); axx.set_xlim(0, 100)
        from matplotlib.ticker import MaxNLocator as _M
        axx.xaxis.set_major_locator(_M(3))
        axx.text(0.5, 0.985, "texture", transform=axx.transAxes, ha="center", va="top",
                 fontsize=7.6, weight="bold", color="#111827")
        axx.tick_params(labelsize=6.6)
    if has_restr or known_restr:
        axr = fig.add_subplot(gs2[n_cols2 - 1])
        axr.set_ylim(100, 0); axr.set_xlim(0, 1)
        axr.set_yticks([0, 20, 40, 60, 80, 100]); axr.tick_params(labelsize=6.6)
        axr.set_xticks([])
        axr.text(0.5, 0.985, "restrictions", transform=axr.transAxes, ha="center",
                 va="top", fontsize=7.6, weight="bold", color="#111827")
        if has_restr:
            for kind, top, bot in restricts:
                bot = min(bot, 100.0)
                if top > 100:
                    continue
                axr.add_patch(plt.Rectangle((0.08, top), 0.84, max(bot - top, 4),
                                            facecolor=_restr_color(kind), alpha=0.28,
                                            edgecolor=_restr_color(kind), hatch="///", lw=0.8))
                axr.text(0.5, max(top, (top + bot) / 2 - 3), kind, rotation=90, fontsize=5.6,
                         color=_restr_color(kind), ha="center", va="center", weight="bold",
                         path_effects=[pe.withStroke(linewidth=1.4, foreground="white")])
            axr.text(0.5, 0.015, "hatched = restrictive layer",
                     transform=axr.transAxes, ha="center", va="bottom", fontsize=5.8)
        else:
            axr.text(0.5, 50, "no restrictive\nfeatures \u2264 100 cm", rotation=90,
                     fontsize=6.0, color="#6b7280", ha="center", va="center")
    fig.text(0.99, 0.004, "profiles: piecewise-linear across horizon midpoints, comppct-weighted, "
             "constant beyond table | AWC cm water/cm soil; texture: same interpolation "
             "normalized to 100 %, 5 cm bins from 0 cm",
             fontsize=6.0, color="#6b7280", ha="right")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {out}")


# Domain-standard choropleth ramps: the ISRIC/SoilGrids `soil.legends`
# palettes (vendored under data/isric_legends/ — see SOURCE.md). Published
# units differ from SSURGO, so each spec carries a scale factor into legend
# space and a colorbar formatter back into the units growers read.
# (col, title, legend file stem, value->legend scale, colorbar cb_label, tick fmt)
_PROPERTY_SPECS = [
    ("om_r", "Soil organic carbon", "ORCDRC", 5.8, "g C/kg (OM x 0.58)", None),
    ("ph1to1h2o_r", "pH (1:1 H2O)", "PHIHOX", 10.0, "pH units", lambda x, _: f"{x/10:.1f}"),
    ("awc_r", "Available water capacity", "CECSOL", 100.0, "cm water / cm soil",
     lambda x, _: f"{x/100:.2f}"),
    ("claytotal_r", "Clay %", "CLYPPT", 1.0, "%", None),
    ("silttotal_r", "Silt %", "SLTPPT", 1.0, "%", None),
    ("sandtotal_r", "Sand %", "SNDPPT", 1.0, "%", None),
    ("cec7_r", "CEC (cmol/kg)", "CECSOL", 1.0, "cmol(c+)/kg", None),
    ("dbthirdbar_r", "Bulk density", "BLDFINE", 1000.0, "g/cm\u00b3",
     lambda x, _: f"{x/1000:.2f}"),
]

_ISRIC_CACHE: dict = {}


def _isric_cmap(code: str):
    """Continuous matplotlib colormap interpolated through the published
    ISRIC legend stops (class midpoints, piecewise-linear in RGB)."""
    import csv
    if code in _ISRIC_CACHE:
        return _ISRIC_CACHE[code]
    path = Path(__file__).resolve().parent.parent / "data" / "isric_legends" / f"{code}.txt"
    xs, cols = [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            c = int(row["COLOR"])
            lo, hi = float(row["MINIMUM"]), float(row["MAXIMUM"])
            xs.append((lo + hi) / 2.0)
            cols.append(((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255))
    lo, hi = xs[0], xs[-1]
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list(
        code, list(zip([(x - lo) / (hi - lo) for x in xs], cols)))
    _ISRIC_CACHE[code] = (cm, lo, hi)
    return _ISRIC_CACHE[code]


def render_property_map(csv_path: Path, label: str, out: Path, source_note: str = "SSURGO") -> None:
    """Whole-field weighted-average property maps: each map-unit polygon colored
    by its component mix's topsoil value, area-weighted (comppct within the
    mukey) — the field-level number most reports quote, drawn as a surface."""
    import geopandas as gpd

    df = pd.read_csv(csv_path)
    df["mukey"] = df["mukey"].astype(str)
    top = df[df["hzdept_r"] == df.groupby(["mukey", "compname"])["hzdept_r"].transform("min")]
    top = top.dropna(subset=["comppct_r"])
    top = top[top["comppct_r"] > 0]
    top["share"] = top["comppct_r"] / top.groupby("mukey")["comppct_r"].transform("sum")

    gj = csv_path.parent / "ssurgo_soil_types.geojson"
    if not gj.exists():
        print(f"  (no polygon file beside {csv_path}; skipping property map)")
        return
    poly = gpd.read_file(gj)
    poly["mukey"] = poly["mukey"].astype(str)
    areas = poly.assign(a=poly.to_crs(6933).geometry.area).groupby("mukey")["a"].sum()

    panels = []
    for col, title, code, scale, cb_label, tick_fmt in _PROPERTY_SPECS:
        sub = top.dropna(subset=[col])
        if sub.empty:
            continue
        wsum = sub.groupby("mukey")["share"].transform("sum")
        sub = sub.assign(w=sub["share"] / wsum)
        vals = (sub["w"] * sub[col]).groupby(sub["mukey"]).sum() * scale
        p = poly.merge(vals.rename("v"), on="mukey", how="left")
        cmap, _, _ = _isric_cmap(code)
        panels.append((title, cmap, p, cb_label, tick_fmt, scale))
    if not panels:
        return

    ncol = min(4, len(panels))
    nrow = int(np.ceil(len(panels) / ncol))
    fig = plt.figure(figsize=(3.3 * ncol + 1.4, 3.9 * nrow))
    gs = fig.add_gridspec(nrow, ncol, height_ratios=[3.5] * nrow,
                          hspace=0.52, wspace=0.30)
    axes = np.array([fig.add_subplot(gs[r, c]) for r in range(nrow) for c in range(ncol)])
    from matplotlib import ticker as _ticker
    for ax, (title, cmap, p, cb_label, tick_fmt, scale) in zip(axes, panels):
        p.plot(column="v", ax=ax, cmap=cmap, legend=False,
               missing_kwds={"color": "#e5e7eb"},
               linewidth=0.3, edgecolor="#9ca3af")
        cb = fig.colorbar(ax.collections[-1], ax=ax, fraction=0.046, pad=0.03)
        cb.ax.tick_params(labelsize=6.5)
        if tick_fmt is not None:
            cb.ax.yaxis.set_major_formatter(_ticker.FuncFormatter(tick_fmt))
        cb.set_label(cb_label, fontsize=7)
        outline = p.dissolve().boundary
        outline.plot(ax=ax, color="#111827", lw=1.0)
        # field mean in whatever units the colorbar displays: tick_fmt panels
        # are converted back by the formatter, so divide; None-formatter panels
        # show legend-space values directly (e.g. SOC g/kg), so keep the mean
        # in legend units
        mean = (float(p["v"].mean() / scale) if tick_fmt is not None
                else float(p["v"].mean())) if p["v"].notna().any() else float("nan")
        ax.set_title(f"{title}\nfield mean {mean:.2f}" if not np.isnan(mean) else title,
                     fontsize=8.6, weight="bold", pad=13)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlabel(""); ax.set_ylabel("")  # graticule labels only crowd the grid
    fig.suptitle(f"{label} — whole-field weighted soil properties (topsoil, {source_note.lower()})",
                 fontsize=11, weight="bold", x=0.02, ha="left", y=1.075)
    for axx in axes[len(panels):]:
        axx.axis("off")
    fig.text(0.02, 0.005, "polygons weighted by component mix — area-weighted field values as a "
             "surface | ramps: ISRIC/SoilGrids standard soil.legends palettes (vendored, "
             "files.isric.org)", fontsize=6.8, color="#4b5563")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=185, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {out}")


def _all_fields(args) -> None:
    """Normal-pipeline mode: every field of the farm gets whatever its soil
    source supports — survey triangle + horizon table + weighted property map,
    or the grid triangle for gridded providers."""
    import pandas as _pd
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lib.paths import farm_dir, field_dir, field_feature_path

    grower = os.environ.get("AG_GROWER_SLUG", "default-grower")
    farm = os.environ.get("AG_FARM_SLUG", "default-farm")
    inv = os.environ.get("AG_INVENTORY_CSV")
    if inv:
        ids = _pd.read_csv(inv)["field_slug"].tolist()
    else:
        ids = [q.name for q in sorted((farm_dir(grower, farm) / "fields").iterdir()) if q.is_dir()]
    for slug in ids:
        soil = field_dir(grower, farm, slug) / "soil"
        csv = soil / "ssurgo_full.csv"
        label = slug
        if csv.exists():
            try:
                render(csv, label, field_feature_path(grower, farm, slug, "soil_texture_triangle.png"))
            except BaseException as exc:  # noqa: BLE001 — per-field resilience
                print(f"  (triangle skipped for {slug}: {exc})")
            try:
                render_horizon_table(csv, label,
                                     field_feature_path(grower, farm, slug, "soil_horizon_table.png"))
            except BaseException as exc:  # noqa: BLE001
                print(f"  (horizon table skipped for {slug}: {exc})")
            try:
                render_property_map(csv, label,
                                    field_feature_path(grower, farm, slug, "soil_weighted_property_map.png"))
            except BaseException as exc:  # noqa: BLE001
                print(f"  (property map skipped for {slug}: {exc})")
        else:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from lib.paths import shared_soilgrids_field_dir  # gridded floor lives in shared/
            candidates = [soil]
            cand = shared_soilgrids_field_dir(slug)
            if cand.is_dir():
                candidates.append(cand)
            done = False
            for cand in candidates:
                try:
                    render(None, label,
                           field_feature_path(grower, farm, slug, "soil_texture_triangle.png"),
                           source_note="grid soil layers", soil_dir=cand)
                    done = True
                    break
                except BaseException:  # noqa: BLE001 — try next candidate
                    continue
            if not done:
                print(f"  (no usable soil for {slug})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--soil-csv", type=Path,
                    help="field soil table (ssurgo_full.csv / national-survey equivalent)")
    ap.add_argument("--soil-dir", type=Path,
                    help="gridded soil directory (clay_/silt_/sand_<depth>.tif — SoilGrids, AU atlas)")
    ap.add_argument("--label", help="field id shown in the title")
    ap.add_argument("--source", default="SSURGO", help="survey name for the title line")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--horizon-table", action="store_true",
                    help="render the component x horizon table instead of the triangle")
    ap.add_argument("--all-fields", action="store_true",
                    help="normal-pipeline mode: every field of the farm gets the full soil set")
    args = ap.parse_args()
    if args.all_fields:
        _all_fields(args)
        return
    if args.label is None or args.out is None:
        ap.error("--label and --out are required unless --all-fields")
    if args.horizon_table:
        if args.soil_csv is None:
            ap.error("--horizon-table requires --soil-csv")
        render_horizon_table(args.soil_csv, args.label, args.out, args.source)
        return
    if args.soil_csv is None and args.soil_dir is None:
        ap.error("pass --soil-csv or --soil-dir")
    render(args.soil_csv, args.label, args.out, args.source, soil_dir=args.soil_dir)


if __name__ == "__main__":
    main()
