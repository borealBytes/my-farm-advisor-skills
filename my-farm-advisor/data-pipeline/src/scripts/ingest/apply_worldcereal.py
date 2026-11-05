#!/usr/bin/env python3
"""Apply WorldCereal default crop models to one farm field for one year.

Derives a per-year cropland/crop-type classification for a field polygon with
the open worldcereal-classification toolbox (MIT; git-pinned v2.8.2 — see
references/crop-rotation-sources.md). Season windows resolve through the
toolbox's own crop-calendar lookup, so Southern-Hemisphere cross-calendar-year
seasons are handled correctly; --start/--end override.

DEFAULT IMAGERY PATH IS KEYLESS: Microsoft Planetary Computer STAC +
anonymous SAS tokens (same access the NDVI products already use), Sentinel-2
L2A monthly slots. Missing Sentinel-1 bands are fed as NODATA (documented
accuracy trade-off). --backend cdse opts into openEO/CDSE for S1+S2 fidelity
(its own free account); --netcdf accepts any pre-built patch.

Honesty (report with every result): default models trained on a global,
EU/US-biased reference DB; accuracy is region-dependent and UNVALIDATED for
e.g. Australia; the legend has no cotton/soybean/sorghum class; PC mode runs
S2-only.

Usage (env: DATA_PIPELINE_DATA_ROOT, AG_GROWER_SLUG, AG_FARM_SLUG):
    python apply_worldcereal.py --field au-r1 --year 2023 --season tc-s2 \
        [--epsg 32656] [--device cuda] [--probabilities] [--max-pixels 128] \
        [--backend pc|cdse] [--netcdf patch.nc] [--model-zip URL_OR_PATH]
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import sys
import os
import uuid
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (  # pyright: ignore[reportMissingImports]
    farm_dir,
)

# model band name -> PC asset key(s), in preference order
PC_BAND_ASSETS = {
    "B2": ["blue", "B02"],
    "B3": ["green", "B03"],
    "B4": ["red", "B04"],
    "B5": ["rededge1", "B05"],
    "B6": ["rededge2", "B06"],
    "B7": ["rededge3", "B07"],
    "B8": ["nir", "B08"],
    "B8A": ["nir08", "B8A"],
    "B11": ["swir16", "B11"],
    "B12": ["swir22", "B12"],
}


# CROPTYPE24 labels, verbatim from the pinned artifact's run_config.json
CROPTYPE24_LABELS = [
    "wheat", "barley", "rye", "oats", "maize", "sorghum", "rice",
    "other_temporary_crops", "millet", "vegetables", "beet",
    "dry_pulses_legumes", "sunflower", "soy_soybeans", "rapeseed_rape",
    "other_oilseed", "groundnuts", "fibre_crops", "potatoes", "cassava",
    "tobacco", "grass_fodder_crops", "sugar_cane", "no_crop",
]
LANDCOVER10_LABELS = [
    "temporary_crops", "temporary_grasses", "bare_sparsely_vegetated",
    "permanent_crops", "built_up", "grasslands", "wetlands", "shrubland",
    "trees", "water",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _field_bounds(fdir: Path, field_id: str):
    import geopandas as gpd

    p = fdir / "fields" / field_id / "boundary" / "field_boundary.geojson"
    if not p.exists():
        have = sorted(d.name for d in (fdir / "fields").glob("*")
                      if (d / "boundary" / "field_boundary.geojson").exists())
        raise SystemExit(f"no boundary for {field_id}; fields with boundaries: "
                         f"{', '.join(have) or 'none'}")
    gdf = gpd.read_file(p)
    return gdf.geometry.union_all().bounds


def _resolve_window(bbox, year: int, season: str):
    from openeo_gfmap import BoundingBoxExtent
    from worldcereal.seasons import get_season_dates_for_extent

    ext = BoundingBoxExtent(west=bbox[0], south=bbox[1], east=bbox[2],
                            north=bbox[3])
    tc = get_season_dates_for_extent(ext, year, season=season)
    s, e = tc.start_date, tc.end_date
    to_d = lambda v: (v.date() if isinstance(v, dt.datetime) else
                      dt.date.fromisoformat(str(v)[:10]))
    return to_d(s), to_d(e)


def _month_slots(start: dt.date, end: dt.date):
    """Up to 12 (slot_month_start, month_end) covering start..end."""
    slots = []
    cur = dt.date(start.year, start.month, 1)
    last = dt.date(end.year, end.month, calendar.monthrange(end.year,
                                                            end.month)[1])
    while cur <= last and len(slots) < 24:
        me = dt.date(cur.year, cur.month,
                     calendar.monthrange(cur.year, cur.month)[1])
        slots.append((cur, me))
        cur = dt.date(cur.year + cur.month // 12, cur.month % 12 + 1, 1)
    if len(slots) > 12:  # keep the 12 nearest the season end
        slots = slots[-12:]
    return slots


def _fetch_patch_pc(bbox, start, end, epsg, max_pixels):
    """Keyless Planetary Computer monthly Sentinel-2 composites -> engine ds.

    Layout verified against worldcereal 2.8.2: one uint16 variable per band,
    dims (t, y, x); band short names; SCL + dataMask included; S1 fed as
    constant NODATA (engine tolerates missing bands).
    """
    import numpy as np
    import rasterio
    from rasterio.vrt import WarpedVRT
    import satellite_imagery as si  # pipeline lib (keyless PC helpers)

    slots = _month_slots(start, end)

    # fixed grid over the full bbox: max_pixels per side, resolution clamped
    # to 10..20 m so fields of any size map onto it
    import math
    from rasterio.windows import from_bounds
    import pyproj
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    tfm = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                      always_xy=True)
    ux, uy = tfm.transform(cx, cy)
    x0u, y0u = tfm.transform(bbox[0], bbox[1])
    x1u, y1u = tfm.transform(bbox[2], bbox[3])
    ext_m = max(x1u - x0u, y1u - y0u, 100.0)
    res = min(20.0, max(10.0, ext_m / max_pixels))
    W = int(max(2, min(max_pixels, math.ceil((x1u - x0u) / res))))
    H = int(max(2, min(max_pixels, math.ceil((y1u - y0u) / res))))
    gx0 = int((x0u - x0u) / res)  # grid origin == bbox origin
    gy0 = int((y1u - y1u) / res)

    per_band = {b: [] for b in list(PC_BAND_ASSETS) + ["SCL", "dataMask"]}
    scene_log = {}

    import concurrent.futures as cf

    def _one_month(slot):
        slot_start, slot_end = slot
        rng = (f"{slot_start.isoformat()}T00:00:00Z/"
               f"{slot_end.isoformat()}T23:59:59Z")
        feats = si.search_features(si.SENTINEL_COLLECTION, bbox, rng,
                                   cloud_lt=60, limit=4)
        if not feats:
            feats = si.search_features(si.SENTINEL_COLLECTION, bbox, rng,
                                       cloud_lt=100, limit=2)
        band_stacks = {b: [] for b in per_band}
        for feat in feats[:3] if feats else []:
            assets = feat.get("assets", {})
            scene_stacks = {b: [] for b in per_band}
            for model_band, keys in dict(PC_BAND_ASSETS,
                                         SCL=["scl", "SCL"]).items():
                key = next((k for k in keys if k in assets), None)
                if key is None:
                    continue
                href = si.sign_planetary_computer_href(
                    si.SENTINEL_COLLECTION, assets[key]["href"])
                arr = np.zeros((H, W), "int64")
                with rasterio.open(href) as raw:
                    with WarpedVRT(
                        raw, crs=f"EPSG:{epsg}",
                        resampling=rasterio.enums.Resampling.nearest,
                    ) as vrt:
                        vb = vrt.bounds
                        inter = (max(x0u, vb[0]), max(y0u, vb[1]),
                                 min(x1u, vb[2]), min(y1u, vb[3]))
                        if inter[0] < inter[2] and inter[1] < inter[3]:
                            ix0, iy0, ix1, iy1 = inter
                            px0 = max(0, int((ix0 - x0u) / res))
                            px1 = min(W, math.ceil((ix1 - x0u) / res))
                            py0 = max(0, int((y1u - iy1) / res))
                            py1 = min(H, math.ceil((y1u - iy0) / res))
                            if px1 > px0 and py1 > py0:
                                win = from_bounds(
                                    ix0, iy0, ix1, iy1,
                                    transform=vrt.transform)
                                chunk = vrt.read(
                                    window=win,
                                    out_shape=(1, py1 - py0, px1 - px0),
                                    fill_value=0)[0].astype("int64")
                                arr[py0:py1, px0:px1] = chunk
                if model_band == "SCL":
                    arr = np.clip(arr, 0, 15)
                else:
                    arr = np.where(arr >= 1000, arr - 1000, arr)
                    arr = np.clip(arr, 0, 15000)
                scene_stacks[model_band].append(arr)
            for b, st in scene_stacks.items():
                if st:
                    band_stacks[b].append(st[0])
            month = slot_start.isoformat()[:7]
            if band_stacks["B4"]:
                def med(key, shape_ref=band_stacks["B4"][0].shape):
                    st = band_stacks.get(key) or []
                    if not st:
                        return np.zeros(shape_ref, "int64")
                    return np.median(np.stack(st), axis=0)
                comp = {b: np.round(med(b)).astype("uint16")
                        for b in PC_BAND_ASSETS}
                scl = np.round(med("SCL")).astype("uint16")
                comp["SCL"] = scl
                comp["dataMask"] = (scl > 0).astype("uint16")
                log = {"scenes": len(band_stacks["B4"]),
                       "best_id": feats[0].get("id"),
                       "cloud_pct": feats[0].get("properties", {}).get(
                           "eo:cloud_cover")}
            else:
                comp = {b: np.zeros((H, W), "uint16") for b in per_band}
                log = {"scenes": 0}
            return month, comp, log

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        results = {m: (c, lg) for m, c, lg in ex.map(_one_month, slots)}
    for slot_start, _slot_end in slots:
        month = slot_start.isoformat()[:7]
        comp, log = results[month]
        for b in per_band:
            per_band[b].append(comp[b])
        scene_log[month] = log

    import xarray as xr
    import pandas as pd
    t = [s[0] for s in slots]
    xs = x0u + (np.arange(W) + 0.5) * res
    ys = y1u - (np.arange(H) + 0.5) * res
    dv = {b: (("t", "y", "x"), np.stack(v)) for b, v in per_band.items()
          if len(v) == len(t)}
    for b in ("VV", "VH"):  # documented NODATA feed (S2-only keyless mode)
        dv[b] = (("t", "y", "x"),
                np.full((len(t), H, W), 65535, "uint16"))
    ds = xr.Dataset(dv, coords={"t": pd.to_datetime(t),
                                "y": ys.astype("float64"),
                                "x": xs.astype("float64")})
    ds["crs"] = ((), np.int32(epsg))
    return ds, scene_log


def _fetch_patch_cdse(bbox, start, end, epsg):
    """Optional openEO/CDSE path (free account) for full S1+S2 fidelity."""
    import geopandas as gpd
    import shapely
    from openeo_gfmap import Backend, BackendContext, FetchType
    from openeo_gfmap import TemporalContext
    from openeo_gfmap.backend import cdse_connection
    from openeo_gfmap.fetching import (build_sentinel1_grd_extractor,
                                       build_sentinel2_l2a_extractor)

    bc = BackendContext(Backend.CDSE)
    tctx = TemporalContext(str(start), str(end))
    s2bands = ["S2-L2A-B02", "S2-L2A-B03", "S2-L2A-B04", "S2-L2A-B05",
               "S2-L2A-B06", "S2-L2A-B07", "S2-L2A-B08", "S2-L2A-B8A",
               "S2-L2A-B11", "S2-L2A-B12"]
    poly = shapely.geometry.box(bbox[0], bbox[1], bbox[2], bbox[3])
    gj = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326").to_json()
    s2 = build_sentinel2_l2a_extractor(bc, s2bands, FetchType.POLYGON)
    s1 = build_sentinel1_grd_extractor(bc, ["S1-SIGMA0-VV", "S1-SIGMA0-VH"],
                                       FetchType.POLYGON)
    conn = cdse_connection()
    ds2 = s2.get_cube(conn, gj, tctx).execute()
    ds1 = s1.get_cube(conn, gj, tctx).execute()
    return (ds2.merge(ds1.rename({"image": "image_data"}),
                      compat="override")
            if "image" in ds1 else ds2), {"backend": "cdse"}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply WorldCereal default models to one field/year.")
    ap.add_argument("--field", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--season", default="tc-s2",
                    choices=["tc-s1", "tc-s2", "tc-annual"])
    ap.add_argument("--start", help="override window start (YYYY-MM-DD)")
    ap.add_argument("--end", help="override window end (YYYY-MM-DD)")
    ap.add_argument("--epsg", type=int, default=None,
                    help="patch CRS (default: field's UTM zone)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--probabilities", action="store_true")
    ap.add_argument("--backend", default="pc", choices=["pc", "cdse"],
                    help="pc = keyless Planetary Computer (default)")
    ap.add_argument("--max-pixels", type=int, default=128,
                    help="patch grid half-resolution cap")
    ap.add_argument("--netcdf", help="pre-built patch .nc (skips fetch)")
    ap.add_argument("--model-zip", default=None)
    ap.add_argument("--legend-offset", type=int, default=0,
                    help="add to class ids before label lookup "
                         "(0-based indices confirmed by US/CA reference runs)")
    ap.add_argument("--grower", default=os.environ.get("AG_GROWER_SLUG"))
    ap.add_argument("--farm", default=os.environ.get("AG_FARM_SLUG"))
    args = ap.parse_args()

    if not args.grower or not args.farm:
        raise SystemExit("set AG_GROWER_SLUG/AG_FARM_SLUG or --grower/--farm")
    if not os.environ.get("DATA_PIPELINE_DATA_ROOT"):
        raise SystemExit("DATA_PIPELINE_DATA_ROOT not set")
    fdir = farm_dir(args.grower, args.farm)

    import numpy as np
    import rasterio
    import xarray
    from rasterio.transform import from_origin
    from worldcereal.local_inference import run_seasonal_inference
    try:
        from worldcereal.openeo.parameters import DEFAULT_SEASONAL_MODEL_URL
    except ImportError:
        DEFAULT_SEASONAL_MODEL_URL = None

    bbox = _field_bounds(fdir, args.field)
    epsg = args.epsg or _utm_epsg((bbox[0] + bbox[2]) / 2,
                                  (bbox[1] + bbox[3]) / 2)

    if args.start and args.end:
        start = dt.date.fromisoformat(args.start)
        end = dt.date.fromisoformat(args.end)
        season_src = "manual"
    else:
        start, end = _resolve_window(bbox, args.year, args.season)
        season_src = "worldcereal-crop-calendar"
    print(f"[{args.field}] {args.year} {args.season} window {start}..{end} "
          f"({season_src}; epsg={epsg})")

    scene_log: dict = {}
    if args.netcdf:
        ds = xarray.open_dataset(args.netcdf)
    else:
        # Engine requires exactly as many monthly composites as the model was
        # trained with (12). Widen the fetch to the full calendar year of the
        # season window; the heads still mask to season_windows.
        year0 = min(start, end).year
        # Presto consumes exactly 12 monthly composites: 12 slots starting at
        # the season-start month (SH cross-year seasons need the tail).
        fetch_start = dt.date(start.year, start.month, 1)
        y, m = fetch_start.year, fetch_start.month + 11
        fetch_end = dt.date(y + (m - 1) // 12, (m - 1) % 12 + 1, 28)
        print(f"  fetch window widened to {fetch_start}..{fetch_end} "
              "(12 monthly slots; season masking unchanged)")
        if args.backend == "pc":
            ds, scene_log = _fetch_patch_pc(bbox, fetch_start, fetch_end,
                                            epsg, args.max_pixels)
        else:
            ds, scene_log = _fetch_patch_cdse(bbox, fetch_start, fetch_end,
                                              epsg)

    model = args.model_zip or DEFAULT_SEASONAL_MODEL_URL
    out = run_seasonal_inference(
        ds,
        seasonal_model_zip=model,
        season_windows={args.season: (str(start), str(end))},
        export_class_probabilities=args.probabilities,
        device=args.device,
        epsg=epsg,  # explicit: works on patches whose crs var lacks crs_wkt
    )

    run_id = uuid.uuid4().hex[:12]
    odir = fdir / "fields" / args.field / "worldcereal"
    odir.mkdir(parents=True, exist_ok=True)

    summary = {
        "field_id": args.field, "year": args.year, "season": args.season,
        "season_window": [str(start), str(end)],
        "season_source": season_src, "epsg": epsg, "run_id": run_id,
        "backend": ("netcdf" if args.netcdf else args.backend),
        "imagery_scenes": scene_log,
        "model_url": str(model),
        "toolbox": "worldcereal 2.8.2 (MIT, git-pinned)",
        "caveat": "region accuracy unvalidated outside reference regions; "
                  "no cotton/soy/sorghum class; pc mode runs S2-only (S1 "
                  "bands fed as NODATA)",
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    outds = out if isinstance(out, xarray.Dataset) \
        else xarray.Dataset({"tasked_classmap": out})
    for var in list(outds.data_vars):
        da = outds[var]
        if not np.issubdtype(da.dtype, np.integer):
            continue
        if not {"y", "x"} <= set(da.dims):
            continue
        flat = da.values
        flat = flat[flat != 65535]
        if flat.size:
            vals, cnts = np.unique(flat.astype("int64"),
                                   return_counts=True)
            dom = int(vals[cnts.argmax()])
            entry = {
                "histogram": {int(v): int(c) for v, c in zip(vals, cnts)},
                "dominant_class": dom,
                "valid_pixels": int(flat.size),
            }
            if var.startswith("croptype") and 0 <= dom - args.legend_offset \
                    < len(CROPTYPE24_LABELS):
                entry["dominant_label"] = CROPTYPE24_LABELS[
                    dom - args.legend_offset]
            summary[var] = entry
        tif = odir / f"wc_{var.replace(':', '_')}_{args.season}" \
                    f"_{args.year}_{run_id}.tif"
        try:
            da2 = da
            for extra in [d for d in da2.dims if d not in ("y", "x")]:
                da2 = da2.isel({extra: 0})
            yy, xx = np.sort(da2["y"].values), np.sort(da2["x"].values)
            arr2 = da2.values[::-1] if da2["y"].values[0] < da2["y"].values[-1] \
                else da2.values
            dx = float((xx.max() - xx.min()) / (xx.size - 1))
            dy = float((yy.max() - yy.min()) / (yy.size - 1))
            tr = from_origin(float(xx.min()) - dx / 2,
                             float(yy.max()) + dy / 2, dx, dy)
            with rasterio.open(
                tif, "w", driver="GTiff", height=arr2.shape[0],
                width=arr2.shape[1], count=1, dtype=arr2.dtype,
                crs=f"EPSG:{epsg}", transform=tr,
            ) as dst:
                dst.write(arr2.astype(da2.dtype), 1)
            summary.setdefault("files", {})[var] = {
                "path": tif.relative_to(fdir).as_posix(),
                "sha256": _sha256(tif),
            }
        except Exception as exc:  # keep the record even if one band fails
            summary.setdefault("export_skipped", {})[var] = str(exc)[:160]

    prov = fdir / "manifests" / "worldcereal_provenance.json"
    doc = json.loads(prov.read_text()) if prov.exists() else {"runs": []}
    doc["runs"].append(summary)
    prov.write_text(json.dumps(doc, indent=2, sort_keys=True))

    print(json.dumps(summary, indent=2)[:1500])
    print("OUT:", odir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
