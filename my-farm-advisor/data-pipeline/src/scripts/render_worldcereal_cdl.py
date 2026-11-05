#!/usr/bin/env python3
"""Extend the WorldCereal verification figure with a USDA CDL comparison panel.

Builds on render_worldcereal.py: same keyless Sentinel-2 basemaps and the same
WorldCereal class panels, plus a 5th map panel "USDA CDL 2023 (ground-truth
reference)" clipped over the field (+2 km buffer) from the shared state CDL
raster, and a text panel comparing in-field class shares of both products.

CDL ingest uses the existing path: scripts/ingest/download_cdl.py ->
$DATA_PIPELINE_DATA_ROOT/data-pipeline/shared/cdl/rasters/CDL_{year}_{fips}.tif
(NASS byfips pattern, https://nassgeodata.gmu.edu/nass_data_cache/byfips/).
Class names/colours come from the official CDL legend (mirrored in the Earth
Engine USDA/NASS_CDL band-properties table; anchors 1=Corn, 5=Soybeans
verified).
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "lib"))
sys.path.insert(0, os.path.join(_HERE, "ingest"))

import fiona
import geopandas as gpd
import matplotlib
import numpy as np
import pyproj
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from shapely.geometry import shape

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import render_worldcereal as rw  # noqa: E402  (reuses base_layer/class_panel/find_run)
from download_cdl import download_cdl  # noqa: E402
from reporting_bootstrap import ensure_skill_path  # noqa: E402

ensure_skill_path("cdl-cropland")
from cdl_reporting import extract_crop_composition  # noqa: E402

ROOT = os.environ["DATA_PIPELINE_DATA_ROOT"]
CDL_YEAR = 2023
CDL_STATE_FIPS = "19"  # Iowa
CDL_BUFFER_M = 2000.0
CDL_URL = (f"https://nassgeodata.gmu.edu/nass_data_cache/byfips/"
           f"CDL_{CDL_YEAR}_{CDL_STATE_FIPS}.tif")
CDL_DIR_FIELD = Path(ROOT) / "data-pipeline/growers/elvtr-demo/farms/" \
    "demo-us/fields/ia-r1/imagery/cdl"
LEGEND = {int(k): (v[0], v[1] or "#8d8d8d") for k, v in
          json.load(open(CDL_DIR_FIELD / "cdl_legend_2023.json")).items()}
GREY = "#8d8d8d"
FIG = {}  # epsg / bounds, set in main()


def clip_cdl(field_geom_4326, out_dir):
    """Window-clip the state CDL over field + buffer (EPSG:5070, native 30 m)."""
    state_raster = download_cdl(CDL_YEAR, CDL_STATE_FIPS)
    gdf = gpd.GeoDataFrame(geometry=[field_geom_4326],
                           crs="EPSG:4326").to_crs("EPSG:5070")
    x0, y0, x1, y1 = gdf.geometry.buffer(CDL_BUFFER_M).total_bounds
    clip_path = Path(out_dir) / f"CDL_{CDL_YEAR}_ia-r1_clip.tif"
    with rasterio.open(state_raster) as src:
        win = from_bounds(x0, y0, x1, y1, transform=src.transform)
        arr = src.read(1, window=win,
                       out_shape=(int(round(win.height)),
                                  int(round(win.width))),
                       resampling=Resampling.nearest)
        prof = src.profile
        prof.update(driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                    transform=src.window_transform(win), crs="EPSG:5070",
                    nodata=0, compress="deflate", tiled=True,
                    blockxsize=256, blockysize=256)
    with rasterio.open(clip_path, "w", **prof) as dst:
        dst.write(arr, 1)
    return state_raster, clip_path


def in_field_shares(raster_path, field_geom, crs, nodata):
    """Class -> (px, %) of in-field valid pixels for any raster + polygon."""
    gdf = gpd.GeoDataFrame(geometry=[field_geom], crs="EPSG:4326").to_crs(crs)
    with rasterio.open(raster_path) as s:
        arr = s.read(1)
        msk = rasterize([(gdf.geometry.iloc[0], 1)], out_shape=arr.shape,
                        transform=s.transform, fill=0, all_touched=False)
        vals = arr[msk == 1]
        vals = vals[~np.isin(vals, nodata)]
    total = int(vals.size)
    codes, counts = np.unique(vals, return_counts=True)
    order = np.argsort(-counts)
    return [(int(codes[i]), int(counts[i]), counts[i] / total * 100.0)
            for i in order], total


def cdl_panel(ax, clip_path):
    """Draw the CDL clip warped to the figure CRS on the shared figure extent."""
    epsg, (bx0, by0, bx1, by1) = FIG["epsg"], FIG["bounds"]
    with rasterio.open(clip_path) as src:
        hist = np.bincount(src.read(1).ravel(), minlength=256)  # clip-grid counts
        with WarpedVRT(src, crs=f"EPSG:{epsg}",
                       resampling=Resampling.nearest,
                       width=int((bx1 - bx0) / 30),
                       height=int((by1 - by0) / 30)) as vrt:
            arr = vrt.read(1).astype("int32")
    codes = sorted(int(c) for c in np.unique(arr) if c != 0)
    remap = np.zeros(256, dtype="uint16")
    colors = []
    for i, c in enumerate(codes, start=1):
        remap[c] = i
        colors.append(LEGEND.get(c, (f"Code_{c}", GREY))[1])
    disp = remap[arr].astype("float32")
    disp[arr == 0] = np.nan
    ax.imshow(disp, cmap=ListedColormap(colors), vmin=0.5,
              vmax=len(codes) + 0.5, extent=(bx0, bx1, by0, by1),
              interpolation="nearest")
    order = sorted(codes, key=lambda c: -hist[c])[:6]
    leg = [Patch(facecolor=LEGEND.get(c, (f"Code_{c}", GREY))[1],
                 label=f"{c} {LEGEND.get(c, (f'Code_{c}',))[0]} "
                       f"({hist[c]:,} px)") for c in order]
    rest = [c for c in codes if c not in order]
    if rest:
        leg.append(Patch(facecolor=GREY,
                         label="other codes: " + ", ".join(map(str, rest))))
    ax.legend(handles=leg, loc="lower left", fontsize=8, framealpha=.9)


def fmt(shares, named, top=4):
    out = []
    for code, cnt, pct in shares[:top]:
        name = named(code) if named else LEGEND.get(code, (f"Code_{code}",))[0]
        out.append(f"  {code:>3} {name:<28} {pct:5.1f}%  ({cnt:,} px)")
    return "\n".join(out)


def main():
    farm, field, season, scene_month = "demo-us", "ia-r1", "tc-s2", "2023-07"
    fdir = os.path.join(rw.ROOT, farm)
    field_dir = os.path.join(fdir, "fields", field)
    with fiona.open(os.path.join(field_dir, "boundary",
                                 "field_boundary.geojson")) as src:
        geom = shape(next(iter(src))["geometry"])

    run = rw.find_run(farm, field, season)
    epsg = FIG["epsg"] = run["epsg"]
    tfm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                      always_xy=True)
    x0, y0 = tfm.transform(geom.bounds[0], geom.bounds[1])
    x1, y1 = tfm.transform(geom.bounds[2], geom.bounds[3])
    buf = 600.0
    FIG["bounds"] = bounds = (x0 - buf, y0 - buf, x1 + buf, y1 + buf)

    crop_tif = [v["path"] for k, v in run["files"].items()
                if k.startswith("croptype")][0]
    land_tif = [v["path"] for k, v in run["files"].items()
                if k.startswith("cropland_classification")][0]
    crop_tif = crop_tif if os.path.isabs(crop_tif) else os.path.join(fdir, crop_tif)
    land_tif = land_tif if os.path.isabs(land_tif) else os.path.join(fdir, land_tif)

    # --- CDL ingest through the existing shared-raster path ---------------
    CDL_DIR_FIELD.mkdir(parents=True, exist_ok=True)
    state_raster, clip_path = clip_cdl(geom, CDL_DIR_FIELD)
    comp_df = extract_crop_composition(
        gpd.GeoDataFrame({"field_id": [field]}, geometry=[geom],
                         crs="EPSG:4326"), str(clip_path), CDL_YEAR)
    comp_csv = CDL_DIR_FIELD / f"cdl_{CDL_YEAR}_{field}_composition.csv"
    comp_df.to_csv(comp_csv, index=False)
    with open(state_raster, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    json.dump({
        "source_url": CDL_URL,
        "source_raster": str(state_raster),
        "source_bytes": os.path.getsize(state_raster),
        "source_sha256": sha,
        "clip": str(clip_path),
        "clip_bytes": clip_path.stat().st_size,
        "buffer_m": CDL_BUFFER_M,
        "legend_source": ("Official USDA NASS CDL data-layer legend "
                          "(values + display colours), mirrored from the "
                          "Google Earth Engine USDA/NASS_CDL band-properties "
                          "table; anchors 1=Corn, 5=Soybeans verified"),
        "legend_file": str(CDL_DIR_FIELD / "cdl_legend_2023.json"),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
    }, open(CDL_DIR_FIELD / "cdl_clip_provenance.json", "w"), indent=2)

    # --- basemaps (identical recipe to the 4-panel figure) -----------------
    item = run["imagery_scenes"][scene_month]["best_id"]
    with rasterio.open(crop_tif) as s:
        W, H = s.width, s.height
        ext = list(s.bounds)
    px = (ext[2] - ext[0]) / W
    out_w = int((bounds[2] - bounds[0]) / px * 2)
    out_h = int((bounds[3] - bounds[1]) / px * 2)
    vis, ndvi = rw.base_layer(item, bounds, epsg, out_w, out_h)
    d = item.split("_")[2]
    scene_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    # --- in-field agreement stats ------------------------------------------
    cdl_shares, cdl_total = in_field_shares(clip_path, geom, "EPSG:5070", [0])
    wc_shares, wc_total = in_field_shares(crop_tif, geom, f"EPSG:{epsg}", [254])
    labels = rw.LABELS
    cdl_top_code, cdl_top_pct = cdl_shares[0][0], cdl_shares[0][2]
    wc_top_code, wc_top_pct = wc_shares[0][0], wc_shares[0][2]
    agree = cdl_top_code == 5 and wc_top_code == 13

    # --- 5-panel figure -----------------------------------------------------
    fig, axes = plt.subplots(2, 3, figsize=(19, 11))
    axes[0, 0].imshow(vis, extent=(bounds[0], bounds[2], bounds[1], bounds[3]))
    axes[0, 0].set_title(f"Sentinel-2 true color — {scene_date}\n"
                        "10 m, keyless Planetary Computer (no accounts)",
                        fontsize=10)
    axes[0, 1].imshow(ndvi, extent=(bounds[0], bounds[2], bounds[1], bounds[3]),
                      cmap="RdYlGn", vmin=0, vmax=0.9)
    axes[0, 1].set_title("NDVI (same scene)", fontsize=10)
    fig.colorbar(axes[0, 1].images[0], ax=axes[0, 1], fraction=.046, pad=.02)
    rw.class_panel(axes[0, 2], land_tif, "land")
    axes[0, 2].set_title("WorldCereal cropland mask", fontsize=10)
    rw.class_panel(axes[1, 0], crop_tif, "crop")
    axes[1, 0].set_title(f"WorldCereal crop-type, {season} season\n"
                        f"calendar window {run['season_window'][0]} → "
                        f"{run['season_window'][1]}", fontsize=10)
    cdl_panel(axes[1, 1], clip_path)
    axes[1, 1].set_title(f"USDA CDL {CDL_YEAR} (ground-truth reference)\n"
                        "30 m state raster, window-clipped +2 km buffer",
                        fontsize=10)

    txt = (
        "In-field class share (polygon-masked)\n\n"
        f"USDA CDL {CDL_YEAR}   ({cdl_total:,} px)\n"
        f"{fmt(cdl_shares, None)}\n\n"
        f"WorldCereal crop-type {season}   ({wc_total:,} px)\n"
        f"{fmt(wc_shares, lambda c: labels[c] if c < len(labels) else str(c))}\n\n"
        f"Verdict: {'AGREE — CDL 5 Soybeans  ≙  WC 13 soy_soybeans' if agree else 'DISAGREE'}\n"
        f"CDL top class {cdl_top_pct:.1f}% in-field\n"
        f"WorldCereal top class {wc_top_pct:.1f}% in-field\n\n"
        "Honest comparison: CDL = USDA annual 30 m product\n"
        "with NASS ground-truth validation; WorldCereal =\n"
        "20 m seasonal model prediction. Different grids,\n"
        "both shown as produced — no recolouring to flatter\n"
        "either side."
    )
    ax = axes[1, 2]
    ax.set_axis_off()
    ax.text(0.02, 0.98, txt, va="top", ha="left", family="monospace",
            fontsize=9, transform=ax.transAxes)
    ax.set_title("Verification summary", fontsize=10)

    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(epsg)
    for ax in [axes[0, 0], axes[0, 1], axes[0, 2], axes[1, 0], axes[1, 1]]:
        gdf.buffer(150).boundary.plot(ax=ax, lw=.8, edgecolor="red",
                                      linestyle=":")
        gdf.boundary.plot(ax=ax, lw=2.2, edgecolor="red")
        ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3])
        ax.set_xticks([]); ax.set_yticks([])
    axes[0, 0].set_xlabel("red solid = field boundary; red dotted = +150 m",
                          fontsize=8)
    fig.suptitle("ia-r1 — Story County, Iowa · 171.7 ha · documented soybeans "
                 "2023 — WorldCereal vs USDA CDL", fontsize=13,
                 fontweight="bold")
    fig.text(.5, .012,
             "CDL via " + CDL_URL + " · official CDL legend (code 39 is "
             "Buckwheat; Grass/Pasture is 176) · keyless PC · 20 m WorldCereal "
             "composite grid vs 30 m CDL grid, both reprojected to UTM 15N",
             ha="center", fontsize=8, color="#555")

    out_dir = os.path.join(field_dir, "derived", "reports")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "wc_verify_ia_soy_cdl.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("WROTE", out)
    print("STATE_RASTER", state_raster, os.path.getsize(state_raster), "bytes")
    print("CLIP", clip_path, clip_path.stat().st_size, "bytes")
    print("CSV", comp_csv)
    print("CDL in-field:", [(c, round(p, 2)) for c, _, p in cdl_shares[:6]])
    print("WC  in-field:", [(c, round(p, 2)) for c, _, p in wc_shares[:6]])


if __name__ == "__main__":
    main()
