#!/usr/bin/env python3
"""Render WorldCereal verification figures: true color + NDVI + class maps."""
import json, math, os, sys, urllib.request
from pathlib import Path
import numpy as np
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "lib"))
sys.path.insert(0, os.path.join(_HERE, "ingest"))
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
import fiona
import pyproj
import geopandas as gpd
from shapely.geometry import shape
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import satellite_imagery as si
import apply_worldcereal as aw
import field_frame as ff

_ROOT = os.environ.get("DATA_PIPELINE_DATA_ROOT")
if not _ROOT:
    raise SystemExit("set DATA_PIPELINE_DATA_ROOT (see data-pipeline/README)")
ROOT = os.path.join(_ROOT, "data-pipeline", "growers",
                    os.environ.get("AG_GROWER_SLUG", "elvtr-demo"), "farms")
SCRATCH = os.environ.get("WC_FIG_DIR") or os.getcwd()
LABELS = aw.CROPTYPE24_LABELS
from matplotlib import colormaps as _cm
PALETTE = (list(_cm.get_cmap("tab20").colors)
           + list(_cm.get_cmap("tab20b").colors[:3])
           + ["#8d8d8d"])          # index 23 = no_crop (grey)


def _field_frame_for(geom, panel_h_in, panel_w_in):
    """Field-local frame for a class-map panel. Circular footprints (center
    pivots) get force_rot=0 — rotation is meaningless on a circle, but the
    re-pinned origin, scale bar and true-north arrow still apply.
    """
    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    gu = gdf.to_crs(ff.utm_epsg(geom.centroid.x, geom.centroid.y))
    g = gu.geometry.iloc[0]
    q = 4 * math.pi * g.area / (g.length ** 2)          # isoperimetric quotient
    force = 0.0 if q > 0.85 else None                   # >.85 ≈ disc
    return ff.frame_for(gdf, panel_h_in, panel_w_in, force_rot=force)


def _into_frame_coords(geoms, f):
    """Zone (EPSG:f.epsg) geometries -> frame (x, y) per the published affine."""
    import shapely.ops
    r3 = math.radians(f.rot)
    cs, sn = math.cos(r3), math.sin(r3)

    def _f(x, y, *a):
        dE, dN = x - f.e0, y - f.n0
        return dE * cs + dN * sn, -dE * sn + dN * cs
    return geoms.map(lambda g: shapely.ops.transform(_f, g))


def find_run(farm, field, season, year=None):
    prov = json.load(open(os.path.join(ROOT, farm, "manifests",
                                       "worldcereal_provenance.json")))
    cands = [r for r in prov["runs"] if r.get("field_id", r.get("field")) == field
             and r["season"] == season and r.get("backend") == "pc"
             and (year is None or r.get("year") == year)]
    return cands[-1]


_NICE = {"other_temporary_crops": "other crops", "dry_pulses_legumes": "pulses/legumes",
         "soy_soybeans": "soybean", "rapeseed_rape": "rapeseed",
         "grass_fodder_crops": "grass/fodder", "sugar_cane": "sugarcane",
         "fibre_crops": "fibre crops", "other_oilseed": "other oilseed",
         "no_crop": "no crop"}


def _disp_name(t):
    lab = LABELS[t] if isinstance(t, int) else t
    if lab == "no_crop":
        return "no crop"
    if lab == "\u25a1_unobserved":
        return "unobserved"
    return _NICE.get(lab, lab.replace("_", " "))


def _two_run_title(fig, ax, y, segs, renderer=None):
    """Panel title: '<year> · PRIMARY 91%' with the PRIMARY run bold.

    A hidden real title reserves layout space (alpha-0 artists still join
    tight bboxes); the visible version is two fig-text runs, centred on the
    reserved slot with renderer-measured widths, so the winning class can be
    bold without unicode tricks.
    """
    for t in getattr(ax, "_wc_runs", ()):
        t.remove()
    plain = f"{y} — " + " · ".join(segs)
    ax.set_title(plain, fontsize=9.5)
    ax.title.set_alpha(0.0)
    head = f"{y} · {segs[0]}"
    tail = "   " + " · ".join(segs[1:]) if len(segs) > 1 else ""
    t0 = fig.text(0, 0, head, fontsize=9.5, weight="bold", ha="left", va="baseline")
    t1 = fig.text(0, 0, tail, fontsize=9.5, ha="left", va="baseline")
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    W, H = fig.canvas.get_width_height()
    bb = ax.title.get_window_extent(r)
    w0 = t0.get_window_extent(r).width
    w1 = t1.get_window_extent(r).width if tail else 0.0
    gap = 5.0
    x = (bb.x0 + bb.x1 - w0 - w1 - gap) / 2.0
    t0.set_position((x / W, bb.y0 / H))          # fig.text uses figure fractions
    if tail:
        t1.set_position(((x + w0 + gap) / W, bb.y0 / H))
    ax._wc_runs = (t0, t1)


# AAFC ACI class code -> WorldCereal CROPTYPE24 index; non-ag cover folds to
# no_crop (23); cloud (10) and nodata (0/255) become unobserved (254).
_ACI_TO_WC24 = {}
for _c in (140, 145, 146, 139): _ACI_TO_WC24[_c] = 0      # wheat + triticale
for _c in (133, 138): _ACI_TO_WC24[_c] = 1                 # barley, spelt
for _c in (134,): _ACI_TO_WC24[_c] = 2                     # (unused spelt slot)
for _c in (136,): _ACI_TO_WC24[_c] = 3                     # oats
for _c in (147,): _ACI_TO_WC24[_c] = 4                     # corn/maize
for _c in (142,): _ACI_TO_WC24[_c] = 5                     # sorghum
for _c in (135,): _ACI_TO_WC24[_c] = 8                     # millet
for _c in (175, 176, 177): _ACI_TO_WC24[_c] = 9            # vegetables
for _c in (178,): _ACI_TO_WC24[_c] = 10                    # sugarbeets
for _c in (160, 161, 162, 163, 167, 168, 174): _ACI_TO_WC24[_c] = 11  # pulses
for _c in (157,): _ACI_TO_WC24[_c] = 12                    # sunflower
for _c in (158,): _ACI_TO_WC24[_c] = 13                    # soybeans
for _c in (153, 155): _ACI_TO_WC24[_c] = 14                # canola, mustard
for _c in (143, 148, 149, 151, 156, 159, 180, 181, 182, 183, 185, 188,
           189, 190, 191, 192, 193, 194, 195, 199):
    _ACI_TO_WC24[_c] = 7                                   # fruit/veg/other
for _c in (152, 154, 196): _ACI_TO_WC24[_c] = 15           # camelina, flax, canaryseed
for _c in (197,): _ACI_TO_WC24[_c] = 17                    # hemp (fibre)
for _c in (110, 122, 132, 141, 198): _ACI_TO_WC24[_c] = 21 # grass/pasture/fodder
for _c in (130, 131): _ACI_TO_WC24[_c] = 23                # fallow/idle


def _aci_year_wc(farm, field, year):
    """Remap the field-level AAFC ACI export to a WC-24 coded GeoTIFF (cached)."""
    from paths import shared_cdl_dir
    src = shared_cdl_dir() / "aci" / str(year) / f"{field}.tif"
    if not src.exists():
        raise SystemExit(f"missing ACI export for {field} {year}: {src} "
                         f"(run ingest/download_cdl.py)")
    out = Path(ROOT) / farm / "fields" / field / "landcover" / f"aci24_{year}.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        with rasterio.open(src) as s:
            arr = s.read(1).astype("int32")
            prof = dict(s.profile, dtype="int32", nodata=254, count=1)
        rep = np.full(256, 23, dtype="uint8")   # default: named-but-unknown -> no_crop
        rep[0] = 254; rep[10] = 254; rep[255] = 254
        rep[20] = 23; rep[30] = 23; rep[34] = 23; rep[35] = 23; rep[50] = 23
        rep[60] = 23; rep[80] = 23; rep[85] = 23; rep[200] = 23; rep[210] = 23
        rep[220] = 23; rep[230] = 23
        for c, w in _ACI_TO_WC24.items():
            rep[c] = w
        with rasterio.open(out, "w", **prof) as s:
            s.write(rep[np.clip(arr, 0, 255)].astype("int32"), 1)
    return {"epsg": 4326,
            "files": {"croptype_classification": {"path": str(out)}}}


def render_year_series(farm, field, years, season, fname, title):
    """Per-year WorldCereal crop-type classification for one field.

    One panel per year; the title carries each class's share of the pixels
    INSIDE the field polygon (254 and the no_crop class both fold into
    "no crop"). The winning class is bolded — within one managed field the
    dominant model call is the truth-bearer; a field that reads as a mix is
    usually a boundary problem, not a rotation.
    """
    from rasterio.features import rasterize
    if season == "aci":
        runs = {y: _aci_year_wc(farm, field, y) for y in years}
    else:
        runs = {y: find_run(farm, field, season, year=y) for y in years}

    def _crop_tif(run):
        for k in (f"croptype_classification:{season}", "croptype_classification"):
            if k in run["files"]:
                return run["files"][k]["path"]
        raise KeyError(f"no croptype_classification in run files: "
                       f"{sorted(run['files'])}")
    n = len(years)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 5.4), squeeze=False)
    with fiona.open(os.path.join(ROOT, farm, "fields", field, "boundary",
                                 "field_boundary.geojson")) as src:
        geom = shape(next(iter(src))["geometry"])
    legend_seen = {}
    _segs_by_ax: dict[int, tuple] = {}
    frame = _field_frame_for(geom, 5.4, 4.6)
    FW = float(frame.geometry.total_bounds[2])
    FH = float(frame.geometry.total_bounds[3])
    for ax, y in zip(axes[0], years):
        run = runs[y]
        rel = _crop_tif(run)
        tif = rel if os.path.isabs(rel) else os.path.join(ROOT, farm, rel)
        epsg = run["epsg"]
        with rasterio.open(tif) as s:
            arr = s.read(1).astype("int32")
            gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(epsg)
            inside = rasterize([(g, 1) for g in gdf.geometry],
                               out_shape=arr.shape, transform=s.transform,
                               fill=0, all_touched=False).astype(bool)
        hist = np.bincount(arr[inside], minlength=255)
        total = max(int(inside.sum()), 1)
        share = {LABELS[t]: 100.0 * hist[t] / total for t in range(23)}
        share["no_crop"] = 100.0 * hist[23] / total
        share["\u25a1_unobserved"] = 100.0 * hist[254] / total
        ranked = sorted(share.items(), key=lambda kv: -kv[1])
        segs, shown = [], 0
        for lab, pct in ranked:
            if segs and pct < 3.0:
                continue
            segs.append(f"{_disp_name(lab)} {pct:.0f}%")
            shown += 1
            if shown == 3:
                break
        class_panel(ax, tif, "crop", frame=frame, legend=False)
        if ax.get_legend():
            ax.get_legend().remove()
        _two_run_title(fig, ax, y, segs)
        _segs_by_ax.setdefault(id(ax), (ax, y, segs))
        frame.geometry.boundary.plot(ax=ax, lw=1.8, edgecolor="red")
        _L, _R, _B, _T = ff.view_extent(0, FW, 0, FH)
        ax.set_xlim(_L, _R)
        ax.set_ylim(_B, _T)
        ax.set_aspect("equal")
        ax.set_xlabel(ff.crs_note(frame), fontsize=6.5)
        ax.set_ylabel("field-local m", fontsize=7)
        # narrow panels: arrow into the gray top-left corner; xlabel already
        # carries the tilt, so no callout; scale bar lifted off the frame edge
        ff.decorate(ax, frame, callout=False, arrow_xy=(0.075, 0.945),
                          scale_y=0.045, scale_x=FW * 0.40)
        for lab, pct in ranked[:3]:
            if pct >= 3.0 and lab not in ("no_crop", "\u25a1_unobserved"):
                t = LABELS.index(lab)
                legend_seen[t] = f"{t} {_disp_name(lab)}"
    handles = [Patch(facecolor=PALETTE[t], label=legend_seen[t])
               for t in sorted(legend_seen)]
    handles.append(Patch(facecolor="#ffffff", edgecolor="#8d8d8d",
                         label="unobserved / no crop"))
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles) + 1, 7),
               fontsize=8, framealpha=.95)
    fig.suptitle(title, fontsize=12, y=.99)
    fig.tight_layout(rect=(0, .06, 1, .965))
    # bold runs must sit on the FINAL title slots: nudge positions by the
    # delta between the two layout passes' title bboxes.
    for _ax, _y, _segs in _segs_by_ax.values():
        _two_run_title(fig, _ax, _y, _segs)
    out = os.path.join(SCRATCH, fname)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("OUT:", out)


def scene_assets(item_id):
    base = si.PLANETARY_COMPUTER_SEARCH_URL.rsplit("/search", 1)[0]
    url = base + "/collections/sentinel-2-l2a/items/" + item_id
    with urllib.request.urlopen(url, timeout=60) as r:
        feat = json.loads(r.read())
    out = {}
    for key in ("B04", "B03", "B02", "B08"):
        href = feat["assets"][key]["href"]
        out[key] = si.sign_planetary_computer_href("sentinel-2-l2a", href)
    return out


def base_layer(item_id, bounds, epsg, out_w, out_h):
    a = scene_assets(item_id)
    band = {}
    for k, href in a.items():
        with rasterio.open(href) as src:
            band[k] = src.read(
                1, window=from_bounds(*bounds, transform=src.transform),
                out_shape=(out_h, out_w),
                resampling=Resampling.bilinear).astype("float32")
    red, grn, blu, nir = band["B04"], band["B03"], band["B02"], band["B08"]
    rgb = np.stack([red, grn, blu])
    vis = np.empty_like(rgb)
    for i in range(3):
        lo, hi = np.percentile(rgb[i][rgb[i] > 0], [2, 98])
        vis[i] = np.clip((rgb[i] - lo) / max(hi - lo, 1.0), 0, 1) ** 0.55
    vis = np.moveaxis(vis, 0, -1)
    ndvi = (nir - red) / (nir + red + 1e-6)
    ndvi[(nir + red) < 100] = np.nan
    return vis, ndvi


def class_panel(ax, tif, kind, field_geom=None, frame=None, legend=True):
    """kind='crop' classification panel, optionally rendered IN THE FIELD
    FRAME (field_frame.Frame): the class grid is reprojected into the rotated
    metre frame in one nearest resample, axes read field-local metres, and
    callers add ff.decorate() for the true-north arrow + callout. Everything
    OUTSIDE the field is flat gray (an off-field tile fragment must never
    read as field data); in-field unobserved (254) is WHITE inside the red
    outline. Returns bincount of in-field classes (len 255).
    """
    from rasterio.features import rasterize
    with rasterio.open(tif) as s:
        crs = s.crs
        if frame is not None:
            _res = s.res[0]
            if s.crs.is_geographic:
                _res *= 111320 * math.cos(math.radians(s.bounds.top))
            w, ext = ff.reproject_into_frame(s, frame, _res,
                                             dst_dtype="int32", nodata=-1)
            inside = ~np.ma.getmaskarray(w)
            arr = np.ma.getdata(w).astype("int32")
            ext = [ext[0], ext[0] + (ext[1] - ext[0]), ext[2], ext[3]]
            ext = (ext[0], ext[1], ext[2], ext[3])
        else:
            arr = s.read(1).astype("int32")
            tfm = s.transform
            ext = list(s.bounds)
            if field_geom is not None:
                gg = gpd.GeoDataFrame(geometry=[field_geom], crs="EPSG:4326").to_crs(crs)
                inside = rasterize([(g, 1) for g in gg.geometry], out_shape=arr.shape,
                                   transform=tfm, fill=0, all_touched=True).astype(bool)
            else:
                inside = np.ones(arr.shape, dtype=bool)
    if kind == "crop":
        import matplotlib.colors as mcolors
        pal = mcolors.to_rgba_array(PALETTE[:24] + ["#c8b487"])
        idx = np.clip(arr, 0, 24).astype(int)
        rgba = np.dstack([pal[idx]])
        rgba[..., 3] = 1.0
        rgba[(~np.isin(arr, np.arange(25))) & inside] = (1, 1, 1, 1)   # 254/other = white
        rgba[~inside] = (0.88, 0.88, 0.88, 1)                          # off-field = gray
        e0, e1, e2, e3 = (ext if isinstance(ext, tuple) else (ext[0], ext[2], ext[1], ext[3]))
        ax.imshow(rgba, extent=(e0, e1, e2, e3), interpolation="nearest")
        hist = np.bincount(arr[inside], minlength=255)
        if legend:
            top = sorted(range(24), key=lambda t: -hist[t])[:3]
            leg = [Patch(facecolor=PALETTE[t],
                         label=f"{t} {LABELS[t]} ({hist[t]:,} px)")
                   for t in top if hist[t] > 0]
            ax.legend(handles=leg, loc="lower left", fontsize=8, framealpha=.9)
    else:
        shown = np.ma.masked_where((arr == 254) | (~inside), arr)
        cmap = ListedColormap(["#b0a08a", "#2e7d32"])
        e0, e1, e2, e3 = (ext if isinstance(ext, tuple) else (ext[0], ext[2], ext[1], ext[3]))
        ax.imshow(shown, cmap=cmap, vmin=-0.5, vmax=1.5, extent=(e0, e1, e2, e3),
                  interpolation="nearest")
        valid = arr[inside & (arr != 254)]
        if legend:
            ax.legend(handles=[
                Patch(facecolor="#2e7d32",
                      label=f"cropland ({int((valid==1).sum()):,} px)"),
                Patch(facecolor="#b0a08a",
                      label=f"not-cropland ({int((valid==0).sum()):,} px)")],
                loc="lower left", fontsize=8, framealpha=.9)
        hist = np.bincount(valid, minlength=255)
    return hist


def render(farm, field, season, scene_month, title, fname, extra_note=""):
    run = find_run(farm, field, season)
    fdir = os.path.join(ROOT, farm)
    with fiona.open(os.path.join(fdir, "fields", field, "boundary",
                                 "field_boundary.geojson")) as src:
        geom = shape(next(iter(src))["geometry"])
    epsg = run["epsg"]
    tfm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                      always_xy=True)
    x0, y0 = tfm.transform(geom.bounds[0], geom.bounds[1])
    x1, y1 = tfm.transform(geom.bounds[2], geom.bounds[3])
    buf = 600.0
    bounds = (x0 - buf, y0 - buf, x1 + buf, y1 + buf)

    crop_tif = [v["path"] for k, v in run["files"].items()
                if k.startswith("croptype")][0]
    land_tif = [v["path"] for k, v in run["files"].items()
                if k.startswith("cropland_classification")][0]
    crop_tif = crop_tif if os.path.isabs(crop_tif) else \
        os.path.join(ROOT, farm, crop_tif)
    land_tif = land_tif if os.path.isabs(land_tif) else \
        os.path.join(ROOT, farm, land_tif)

    item = run["imagery_scenes"][scene_month]["best_id"]
    with rasterio.open(crop_tif) as s:
        W, H = s.width, s.height
        ext = list(s.bounds)
    px = (ext[2] - ext[0]) / W  # composite grid resolution (m)
    out_w = int((bounds[2] - bounds[0]) / px * 2)   # render at 10 m base
    out_h = int((bounds[3] - bounds[1]) / px * 2)
    vis, ndvi = base_layer(item, bounds, epsg, out_w, out_h)
    d = item.split("_")[2]
    scene_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    # one field-local frame for all four panels (scene reprojected in-graph,
    # class grids via class_panel's frame path) — field-map-frame.md contract
    frame = _field_frame_for(geom, 5.5, 6.5)
    from rasterio.io import MemoryFile
    from rasterio.transform import Affine as _Af
    _px_x = (bounds[2] - bounds[0]) / vis.shape[1]
    _px_y = (bounds[3] - bounds[1]) / vis.shape[0]
    _tr = _Af(_px_x, 0, bounds[0], 0, -_px_y, bounds[3])
    _FW = float(frame.geometry.total_bounds[2])
    _FH = float(frame.geometry.total_bounds[3])
    _res = px
    def _warp_bands(a):
        a3 = a[..., None] if a.ndim == 2 else a
        outs = []
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", height=a3.shape[0], width=a3.shape[1],
                          count=a3.shape[2], dtype=a3.dtype,
                          crs=f"EPSG:{epsg}", transform=_tr) as ds0:
                for bi in range(a3.shape[2]):
                    ds0.write(np.ascontiguousarray(a3[..., bi]), bi + 1)
            with mf.open() as ds1:
                for bi in range(1, a3.shape[2] + 1):
                    w, _e = ff.reproject_into_frame(ds1, frame, _res, band=bi)
                    outs.append(w)
        stack = np.dstack([np.ma.filled(o, np.nan) for o in outs])
        return stack, (0, _FW, 0, _FH)

    visf, _ = _warp_bands(vis)
    ndvif, _ = _warp_bands(ndvi[..., None])
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    axes[0, 0].imshow(np.clip(visf, 0, 1), extent=(0, _FW, 0, _FH))
    axes[0, 0].set_title(f"Sentinel-2 true color — {scene_date}\n"
                        "10 m, keyless Planetary Computer (no accounts)",
                        fontsize=10)
    axes[1, 0].imshow(ndvif[..., 0], extent=(0, _FW, 0, _FH), cmap="RdYlGn", vmin=0, vmax=0.9)
    axes[1, 0].set_title("NDVI (same scene)", fontsize=10)
    fig.colorbar(axes[1, 0].images[0], ax=axes[1, 0], fraction=.046, pad=.02)
    class_panel(axes[0, 1], crop_tif, "crop", frame=frame)
    axes[0, 1].set_title(f"WorldCereal crop-type, {season} season\n"
                        f"calendar window {run['season_window'][0]} → "
                        f"{run['season_window'][1]}", fontsize=10)
    class_panel(axes[1, 1], land_tif, "land", frame=frame)
    axes[1, 1].set_title("WorldCereal cropland mask", fontsize=10)

    _gs = frame.geometry
    for ax in axes.flat:
        _gs.buffer(150).boundary.plot(ax=ax, lw=.8, edgecolor="red",
                                      linestyle=":")
        _gs.boundary.plot(ax=ax, lw=2.2, edgecolor="red")
        _L, _R, _B, _T = ff.view_extent(0, _FW, 0, _FH); ax.set_xlim(_L, _R); ax.set_ylim(_B, _T)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlabel(ff.crs_note(frame), fontsize=6.5)
        ax.set_ylabel("field-local m", fontsize=7)
        ff.decorate(ax, frame, callout=False, arrow_xy=(0.09, 0.80), scale_y=0.075)
    axes[0, 0].set_xlabel(axes[0, 0].get_xlabel() + "   ·   red solid = boundary; dotted = +150 m",
                          fontsize=6.5)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.text(.5, .012, extra_note or
             "backend=pc (zero accounts) · WorldCereal-PRESTO default v2.8.2 "
             "· legend 0-indexed · class maps on 20 m monthly-composite grid",
             ha="center", fontsize=8, color="#555")
    fig.savefig(os.path.join(SCRATCH, fname), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("WROTE", os.path.join(SCRATCH, fname), flush=True)




def render_rdm_overlay(farm, field, year, season, ref_geojson, fname, title,
                       ref_label_col="crop_label", buf_deg=0.02):
    """Two-panel ladder demo: keyless default model vs RDM regional reference.

    Left: default-model crop-type classification for the field/year.
    Right: harmonized WorldCereal RDM reference features overlapping the
    buffered field bbox, colored by crop label. Reference data names classes
    the default model cannot (e.g. sugarcane) and labels parcels in years the
    optical time series cannot see through clouds.
    """
    import fiona as _fiona
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.2), squeeze=False)
    ax_l, ax_r = axes[0]
    run = find_run(farm, field, season, year=year)
    rel = run["files"].get(f"croptype_classification:{season}",
                           run["files"].get("croptype_classification"))["path"]
    tif = rel if os.path.isabs(rel) else os.path.join(ROOT, farm, rel)
    with _fiona.open(os.path.join(ROOT, farm, "fields", field, "boundary",
                                  "field_boundary.geojson")) as src_:
        geom = shape(next(iter(src_))["geometry"])
    frame = _field_frame_for(geom, 5.2, 5.8)
    _hist = class_panel(ax_l, tif, "crop", frame=frame, legend=False)
    if ax_l.get_legend():
        ax_l.get_legend().remove()
    _top = sorted(range(24), key=lambda t: -_hist[t])[:6]
    _h = [Patch(facecolor=PALETTE[t],
                label=f"{_disp_name(t)} ({_hist[t]:,} px)")
          for t in _top if _hist[t] > 0]
    _h.append(Patch(facecolor="#f8f9fa", edgecolor="#9ca3af",
                    label=f"unobserved / no crop ({_hist[23] + _hist[254]:,} px)"))
    ax_l.legend(handles=_h, fontsize=6.2, loc="center left",
                bbox_to_anchor=(1.01, .5), framealpha=.95)
    ax_l.set_title(f"model default ({season} {year}, keyless Planetary Computer)",
                   fontsize=10)

    ref = gpd.read_file(ref_geojson)
    minx, miny, maxx, maxy = geom.bounds
    sel = ref.cx[minx-buf_deg:maxx+buf_deg, miny-buf_deg:maxy+buf_deg]
    cats = sorted(sel[ref_label_col].unique())
    cmap = {c: PALETTE[i % 20] for i, c in enumerate(cats)}
    _selz = sel.to_crs(run["epsg"])
    _cols = [cmap[c] for c in _selz[ref_label_col]]
    sel_plot = _into_frame_coords(_selz.geometry, frame)
    if (sel_plot.geom_type == "Point").all():
        ax_r.scatter([g.x for g in sel_plot], [g.y for g in sel_plot],
                     c=_cols, s=30, edgecolor="#374151", linewidths=.4, zorder=3)
    else:
        gpd.GeoDataFrame(geometry=sel_plot).plot(ax=ax_r, color=_cols,
                                                 edgecolor="#374151", lw=.4)
    frame.geometry.boundary.plot(ax=ax_l, lw=2.0, edgecolor="#111827")
    frame.geometry.boundary.plot(ax=ax_r, lw=2.2, edgecolor="#111827")
    _FW = float(frame.geometry.total_bounds[2]); _FH = float(frame.geometry.total_bounds[3])
    for _a in (ax_l, ax_r):
        _L, _R, _B, _T = ff.view_extent(0, _FW, 0, _FH); _a.set_xlim(_L, _R); _a.set_ylim(_B, _T); _a.set_aspect("equal")
        _a.set_xlabel(ff.crs_note(frame), fontsize=6.5)
        _a.set_ylabel("field-local m", fontsize=7)
        ff.decorate(_a, frame, callout=False, arrow_xy=(0.09, 0.80), scale_y=0.075)
    for _a in (ax_l, ax_r):
        _a.set_xticks([]); _a.set_yticks([]); _a.set_xlabel(""); _a.set_ylabel("")
        _a.spines["top"].set_visible(False); _a.spines["right"].set_visible(False)
        _a.spines["left"].set_visible(False); _a.spines["bottom"].set_visible(False)
    ax_r.set_title("WorldCereal RDM reference (harmonized, keyless API)",
                   fontsize=10)
    handles = [Patch(facecolor=cmap[c], edgecolor="#374151",
                     label=c.replace("_", " ")) for c in cats]
    ax_r.legend(handles=handles, fontsize=6.4, loc="center left",
                bbox_to_anchor=(1.01, .5), framealpha=.95,
                title="reference crop label", title_fontsize=6.6)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .93))
    out = os.path.join(SCRATCH, fname)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("OUT:", out)


if __name__ == "__main__":
    RD = os.path.join(ROOT, "demo-ca")
    render("demo-us", "ia-r1", "tc-s2", "2023-07",
           "ia-r1 — Story County, Iowa · 171.7 ha · documented soybeans 2023",
           "wc_verify_ia_soy.png",
           "keyless PC · THE CHECK: model independently called class 13 = "
           "soy_soybeans on this field (no CDL input given)")
    render("demo-au", "au-r1", "tc-s2", "2023-08",
           "au-r1 — Narrabri NSW · 1,233 ha cotton field · 2023 dry-season "
           "(tc-s2)", "wc_verify_au_tc2.png",
           "keyless PC · La Niña 2023: cotton was planted Nov-2023, so the "
           "Apr–Nov window is fallow — model sees mostly no_crop (correct)")
    render("demo-au", "au-r1", "tc-s1", "2023-02",
           "au-r1 — Narrabri NSW · 2022/23 summer season (tc-s1)",
           "wc_verify_au_tc1.png",
           "keyless PC · AU caveat: un-fine-tuned model called in-season "
           "pixels other_oilseed (15) — cotton is fibre_crops (17) in the "
           "legend; region accuracy genuinely unvalidated")
    render_year_series("demo-br", "br-r1", [2021, 2022, 2023, 2024], "tc-s2",
                       "wc_year_series_br.png",
                       "br-r1 — Rio Verde, Goiás · sugarcane↔maize rotation, "
                       "read year-by-year (layer has no cane class: cane years "
                       "read as no crop)")
    render_year_series("demo-ca", "on-r2", [2019, 2021, 2023], "aci",
                       "wc_year_series_on.png",
                       "on-r2 — Ontario · soybean↔corn rotation recovered "
                       "year-by-year (AAFC ACI cloud-free mosaic, 30 m)")
    render_rdm_overlay(
        "demo-ca", "on-r1", 2022, "tc-s2",
        os.path.join(ROOT, "demo-ca", "fields", "on-r1", "worldcereal_rdm",
                     "rdm_2017_can_aafccropinventory_point_110.geojson"),
        "wc_ladder_on.png",
        "on-r1 (Ontario, 593 ha) \u00b7 optical model cloud-gapped in-place; "
        "AAFC RDM points (2017) name what the field grows")
    render_rdm_overlay(
        "demo-br", "br-r2", 2021, "tc-s2",
        os.path.join(ROOT, "demo-br", "fields", "br-r1", "worldcereal_rdm",
                     "rdm_2017_bra_jecamcirad_poly_111.geojson"),
        "wc_ladder_br.png",
        "br-r2 (S\u00e3o Paulo cane belt) \u00b7 boundary from the RDM parcel itself; "
        "model has no cane class \u2014 RDM does")
