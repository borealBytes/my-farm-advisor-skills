#!/usr/bin/env python3
"""Render WorldCereal verification figures: true color + NDVI + class maps."""
import json, os, sys, urllib.request
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


def find_run(farm, field, season):
    prov = json.load(open(os.path.join(ROOT, farm, "manifests",
                                       "worldcereal_provenance.json")))
    cands = [r for r in prov["runs"] if r.get("field_id", r.get("field")) == field
             and r["season"] == season and r.get("backend") == "pc"]
    return cands[-1]


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


def class_panel(ax, tif, kind):
    with rasterio.open(tif) as s:
        arr = s.read(1).astype("int32")
        ext = list(s.bounds)
    if kind == "crop":
        shown = np.ma.masked_where(arr == 254, arr)
        cmap = ListedColormap(PALETTE[:24] + ["#c8b487"])
        ax.imshow(shown, cmap=cmap, vmin=-0.5, vmax=24.5, extent=(ext[0], ext[2], ext[1], ext[3]),
                  interpolation="nearest")
        hist = np.bincount(arr.ravel(), minlength=25)
        top = sorted(range(24), key=lambda t: -hist[t])[:3]
        leg = [Patch(facecolor=PALETTE[t],
                     label=f"{t} {LABELS[t]} ({hist[t]:,} px)")
               for t in top if hist[t] > 0]
        ax.legend(handles=leg, loc="lower left", fontsize=8, framealpha=.9)
    else:
        shown = np.ma.masked_where(arr == 254, arr)
        cmap = ListedColormap(["#b0a08a", "#2e7d32"])
        ax.imshow(shown, cmap=cmap, vmin=-0.5, vmax=1.5, extent=(ext[0], ext[2], ext[1], ext[3]),
                  interpolation="nearest")
        valid = arr[arr != 254]
        ax.legend(handles=[
            Patch(facecolor="#2e7d32",
                  label=f"cropland ({int((valid==1).sum()):,} px)"),
            Patch(facecolor="#b0a08a",
                  label=f"not-cropland ({int((valid==0).sum()):,} px)")],
            loc="lower left", fontsize=8, framealpha=.9)


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

    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    axes[0, 0].imshow(vis, extent=(bounds[0], bounds[2], bounds[1], bounds[3]))
    axes[0, 0].set_title(f"Sentinel-2 true color — {scene_date}\n"
                        "10 m, keyless Planetary Computer (no accounts)",
                        fontsize=10)
    axes[1, 0].imshow(ndvi, extent=(bounds[0], bounds[2], bounds[1], bounds[3]), cmap="RdYlGn", vmin=0, vmax=0.9)
    axes[1, 0].set_title("NDVI (same scene)", fontsize=10)
    fig.colorbar(axes[1, 0].images[0], ax=axes[1, 0], fraction=.046, pad=.02)
    class_panel(axes[0, 1], crop_tif, "crop")
    axes[0, 1].set_title(f"WorldCereal crop-type, {season} season\n"
                        f"calendar window {run['season_window'][0]} → "
                        f"{run['season_window'][1]}", fontsize=10)
    class_panel(axes[1, 1], land_tif, "land")
    axes[1, 1].set_title("WorldCereal cropland mask", fontsize=10)

    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(epsg)
    for ax in axes.flat:
        gdf.buffer(150).boundary.plot(ax=ax, lw=.8, edgecolor="red",
                                      linestyle=":")
        gdf.boundary.plot(ax=ax, lw=2.2, edgecolor="red")
        ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3])
        ax.set_xticks([]); ax.set_yticks([])
    axes[0, 0].set_xlabel("red solid = field boundary; red dotted = +150 m",
                          fontsize=8)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.text(.5, .012, extra_note or
             "backend=pc (zero accounts) · WorldCereal-PRESTO default v2.8.2 "
             "· legend 0-indexed · class maps on 20 m monthly-composite grid",
             ha="center", fontsize=8, color="#555")
    fig.savefig(os.path.join(SCRATCH, fname), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("WROTE", os.path.join(SCRATCH, fname), flush=True)


if __name__ == "__main__":
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
