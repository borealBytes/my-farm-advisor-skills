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
    b = fields.to_crs("EPSG:4326").total_bounds
    pad = 0.004
    bounds = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)

    band_keys = list(raster_paths)
    n = len(band_keys)
    total = n + 1
    cols = min(3, total)
    rows = -(-total // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.1 * cols + 1.2, 3.5 * rows), constrained_layout=True)
    axes = np.atleast_1d(axes).ravel()
    dem = None
    if dem_path and dem_path.exists():
        dem = _clip_raster(dem_path, bounds, out_png.parent / f"{field_slug}_dem_clip.tif", res_deg=0.0003)
    ls = LightSource(azdeg=315, altdeg=45)
    ax0 = axes[0]
    if dem is not None:
        with rasterio.open(dem) as ds:
            arr = ds.read(1, masked=True).astype("float64").copy()
            arr = np.ma.masked_invalid(arr)
            ext = ds.bounds
            hs = ls.hillshade(np.ma.filled(arr, float("nan")), vert_exag=1.2)
            hs = np.ma.masked_invalid(hs)
            im0 = ax0.imshow(
                hs, cmap="gray", vmin=0, vmax=1,
                extent=[ext.left, ext.right, ext.bottom, ext.top], origin="upper",
            )
            flat = arr.compressed()
            if flat.size:
                norm = plt.Normalize(np.percentile(flat, 2), np.percentile(flat, 98))
            else:
                norm = plt.Normalize(0, 1)
            ax0.imshow(
                arr, cmap="terrain", alpha=0.12, extent=[ext.left, ext.right, ext.bottom, ext.top],
                origin="upper", norm=norm,
            )
            cb0 = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="terrain"), ax=ax0, fraction=0.046, pad=0.03)
            cb0.set_label("elevation (m)", fontsize=6)
            cb0.ax.tick_params(labelsize=6)
        ax0.set_title("Terrain (DEM hillshade, 30 m)", fontsize=9)
    else:
        ax0.text(0.5, 0.5, "no DEM", ha="center")
    fields.to_crs("EPSG:4326").plot(ax=ax0, facecolor="none", edgecolor="red", linewidth=1.4)
    _geo_ticks(ax0)

    poly = fields.to_crs("EPSG:4326").union_all()
    for ax, key in zip(axes[1:], band_keys):
        raster = _clip_raster(raster_paths[key], bounds, out_png.parent / f"{field_slug}_{key}_clip.tif")
        with rasterio.open(raster) as ds:
            arr = ds.read(1, masked=True).astype("float64")
            if _sg is not None and raster_paths[key].name.startswith("soilgrids_") and key in _sg.BAND_SPECS:
                # SoilGrids clips are raw Int16; ASF clips are already in true
                # units (verified scale=1.0 at ingest) and must NOT be rescaled.
                arr = _sg.apply_scale(arr, key)
            arr = _mask_to_polygon(arr, ds.transform, poly)
            ext = ds.bounds
            label, unit, _cmap = BAND_LABELS.get(key, (key, "", "viridis"))
            if key == "cec" and not raster_paths[key].name.startswith("soilgrids_"):
                # ASF CEC arrives in its own native scale; do not assert SoilGrids units.
                label, unit = "CEC 0–5 cm (ASF native units)", ""
            im = ax.imshow(arr, cmap="viridis", extent=[ext.left, ext.right, ext.bottom, ext.top], origin="upper")
            cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
            cb.set_label(unit, fontsize=6)
            cb.ax.tick_params(labelsize=6)
            mean_v = float(np.nanmean(arr))
        ax.set_title(f"{label} — mean {mean_v:.1f}", fontsize=8.5)
        fields.to_crs("EPSG:4326").plot(ax=ax, facecolor="none", edgecolor="red", linewidth=1.4)
        _geo_ticks(ax)

    for _ax in axes[total:]:
        _ax.axis("off")
    fig.suptitle(f"{field_slug} — gridded soil properties + relief {title_extra}", fontsize=11)
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
