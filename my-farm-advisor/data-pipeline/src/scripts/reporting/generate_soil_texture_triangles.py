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


def render(csv_path: Path, label: str, out: Path, source_note: str = "SSURGO",
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

    # gridlines: sand % along base, clay % along left edge
    for pct in range(10, 100, 10):
        f = pct / 100.0
        x0, y0 = _to_xy(0, 1 - f, f)
        x1, y1 = _to_xy(1, 0, 0)
        ax.plot([x0, x1], [y0, y1], color="#b08a7a", lw=0.3, alpha=0.6)  # sand lines
        xa, ya = _to_xy(f, 0, 1 - f)
        xb, yb = _to_xy(1, 0, 0)
        ax.plot([xa, xb], [ya, yb], color="#b08a7a", lw=0.3, alpha=0.6)  # clay lines
        ax.text(xa + 0.015, ya + 0.02, str(pct), fontsize=5.5, color="#8a665a")

    # outer triangle + corner axis titles
    ax.add_patch(MplPolygon([_to_xy(0, 1, 0), _to_xy(0, 0, 1), _to_xy(1, 0, 0)],
                            closed=True, fill=False, edgecolor="#3f2a26", lw=1.4))
    ax.text(0.5, -0.045, "% SAND", ha="center", fontsize=8, weight="bold", color="#3f2a26")
    ax.text(-0.055, 0.30, "% CLAY", fontsize=8, weight="bold", color="#3f2a26", rotation=60, va="center")
    ax.text(1.045, 0.30, "% SILT", fontsize=8, weight="bold", color="#3f2a26", rotation=-60, va="center")

    # component points, sized by comppct_r (grid cells: small translucent dots)
    sizes = 6 if grid_note else 30 + comp["comppct_r"] * 1.9
    xs, ys = zip(*(_to_xy(c, s, sa) for c, s, sa in zip(comp["clay"], comp["silt"], comp["sand"])))
    if grid_note:
        ax.scatter(xs, ys, s=34, c="#1d4ed8", zorder=5, alpha=0.55, linewidths=0)
    else:
        ax.scatter(xs, ys, s=sizes, c="#1d4ed8", edgecolors="white", linewidths=0.8, zorder=5, alpha=0.88)

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
        arrowprops=dict(arrowstyle="->", color="#78350f", lw=0.9),
    )

    if grid_note:
        unit = "one point per raster cell (thin-stride shown), star = weighted mean of all cells"
        n_note = f"{grid_note[4]} cells at {grid_note[0]}"
    else:
        unit = "one point per component (size = relative abundance), star = comppct-weighted mean"
        n_note = f"{len(comp)} components"
    ax.set_title(
        f"{label} — soil texture classes (topsoil, {source_note.lower()})",
        fontsize=10.5, weight="bold", pad=14, loc="left",
    )
    ax.text(
        0, 1.005,
        f"{unit} | {n_note}",
        transform=ax.transAxes, fontsize=7.4, color="#4b5563",
    )
    ax.set_xlim(-0.12, 1.14)
    ax.set_ylim(-0.08, 0.95)
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

    fig = plt.figure(figsize=(13.2, 0.44 * len(g) + 1.6))
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.45, 1.0], wspace=0.12)
    ax_t = fig.add_subplot(gs[0]); ax_t.axis("off")
    cols = ["Component", "Rel. %", "Depth", "OM %", "pH", "AWC", "Clay %", "Sand %"]
    num_cols = {3: ("om", plt.get_cmap("Reds"), 0.6), 4: ("ph", plt.get_cmap("coolwarm_r"), 0.55),
                5: ("awc", plt.get_cmap("Blues"), 0.6), 6: ("clay", plt.get_cmap("PuRd"), 0.6),
                7: ("sand", plt.get_cmap("YlOrBr"), 0.6)}
    cells = [
        [r.compname, f"{r.comppct_r:.0f}", r.slice,
         "" if pd.isna(r.om) else f"{r.om:.1f}",
         "" if pd.isna(r.ph) else f"{r.ph:.1f}",
         "" if pd.isna(r.awc) else f"{r.awc:.2f}",
         f"{r.clay:.0f}", "" if pd.isna(r.sand) else f"{r.sand:.0f}"]
        for r in g.itertuples()
    ]
    tbl = ax_t.table(cellText=cells, colLabels=cols, loc="upper left", cellLoc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(8.2)
    tbl.auto_set_column_width(col=(0, 2))
    tbl.scale(1, 1.34)
    spans = {}
    for ci, (key, _, _) in num_cols.items():
        vals = pd.to_numeric(pd.Series([row[ci] for row in cells]), errors="coerce").dropna()
        if len(vals):
            spans[ci] = (vals.min(), vals.max())
    for (row, col), cell in tbl.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#1f2937"); cell.set_text_props(color="white", weight="bold")
            continue
        if col in num_cols and cells[row - 1][col]:
            key, cmap, strength = num_cols[col]
            lo, hi = spans[col]
            v = float(cells[row - 1][col])
            f = 0.5 if hi == lo else (v - lo) / (hi - lo)
            if key == "ph":  # diverging: neutral mid keeps lightness honest
                f = abs(v - float(np.mean([lo, hi]))) / max((hi - lo) / 2, 1e-9)
            cell.set_facecolor(_hex_blend(1 - strength * f, tuple(int(x * 255) for x in cmap(f)[:3])))
            cell.set_text_props(path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])
        elif row % 2 == 0:
            cell.set_facecolor("#f3f4f6")
        if col == 0:
            cell.set_text_props(ha="left")
    ax_t.set_title(
        f"{label} — soil horizon detail ({source_note.lower()})",
        fontsize=11, weight="bold", loc="left", pad=26,
    )
    ax_t.text(0, 1.01, "cells color-coded within column | lines at right are the same table "
              "interpolated to continuous depth", transform=ax_t.transAxes,
              fontsize=7.4, color="#4b5563")

    # --- interpolated profiles (comppct-weighted, 5 cm bins) ---
    bins = np.arange(5, 101, 5.0)
    panels = [("OM %", _interp_profile(df, "om_r", bins), plt.get_cmap("Reds")),
              ("pH", _interp_profile(df, "ph1to1h2o_r", bins), plt.get_cmap("coolwarm_r")),
              ("AWC (cm/cm)", _interp_profile(df, "awc_r", bins), plt.get_cmap("Blues")),
              ("Clay %", _interp_profile(df, "claytotal_r", bins), plt.get_cmap("PuRd"))]
    have = [(n, y, c) for n, y, c in panels if y is not None]
    gs2 = gridspec.GridSpecFromSubplotSpec(1, len(have), subplot_spec=gs[1], wspace=0.08)
    for i, (name, y, cmap) in enumerate(have):
        ax = fig.add_subplot(gs2[i])
        ax.plot(y, bins, color="#1f2937", lw=1.7)
        ax.fill_betweenx(bins, y, y.min(), alpha=0.25, color=cmap(0.6))
        ax.set_ylim(100, 0); ax.set_xlim(y.min() - (y.max()-y.min())*0.15 - 1e-9,
                                         y.max() + (y.max()-y.min())*0.15 + 1e-9)
        ax.set_title(name, fontsize=8.2, weight="bold", pad=4)
        ax.tick_params(labelsize=6.6)
        ax.grid(alpha=0.25, lw=0.4)
        ax.set_xlabel("interp @ 5 cm", fontsize=6.2)
    ax_t.text(0.99, 0.02, "profiles: piecewise-linear across horizon midpoints, comppct-weighted, "
              "constant beyond table", transform=ax_t.transAxes, fontsize=6.0,
              color="#6b7280", ha="right")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--soil-csv", type=Path,
                    help="field soil table (ssurgo_full.csv / national-survey equivalent)")
    ap.add_argument("--soil-dir", type=Path,
                    help="gridded soil directory (clay_/silt_/sand_<depth>.tif — SoilGrids, AU atlas)")
    ap.add_argument("--label", required=True, help="field id shown in the title")
    ap.add_argument("--source", default="SSURGO", help="survey name for the title line")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--horizon-table", action="store_true",
                    help="render the component x horizon table instead of the triangle")
    args = ap.parse_args()
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
