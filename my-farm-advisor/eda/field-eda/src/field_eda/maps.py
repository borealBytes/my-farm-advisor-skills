"""Farm-overview map frame helpers.

Maps here show every field in a grower, not one footprint. They follow the
repository frame contract where it applies — local UTM metres, kilometre ticks
from the farm's south-west corner, viewport padding, boxed north arrow, scale
bar — but deliberately skip auto-rotation, which is a single-field rule.

``view_extent`` and ``utm_epsg`` mirror ``data-pipeline/src/scripts/lib/
field_frame.py``. The installed runtime copy is imported when available so the
padding rule cannot drift; the local copies keep the subskill runnable on its
own.
"""

from __future__ import annotations

import math

import geopandas as gpd

from . import style

try:  # prefer the pipeline implementation when the runtime is installed
    from scripts.lib.field_frame import utm_epsg, view_extent  # type: ignore
except Exception:  # pragma: no cover - standalone fallback
    VIEW_PAD_FRAC = 0.04

    def utm_epsg(lon: float, lat: float) -> int:
        zone = int(math.floor((lon + 180.0) / 6.0)) + 1
        return (32600 if lat >= 0 else 32700) + zone

    def view_extent(x_min, x_max, y_min, y_max, pad_frac: float = VIEW_PAD_FRAC):
        margin = pad_frac * max(x_max - x_min, y_max - y_min)
        return (x_min - margin, x_max + margin, y_min - margin, y_max + margin)


def project_farm(fields: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Project one farm's fields into a local UTM frame in kilometres."""

    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    lonlat = fields.to_crs("EPSG:4326")
    centre = lonlat.geometry.union_all().centroid
    projected = fields.to_crs(epsg=utm_epsg(centre.x, centre.y))

    x_min, y_min = projected.total_bounds[0], projected.total_bounds[1]
    projected = projected.copy()
    projected["geometry"] = projected.geometry.translate(xoff=-x_min, yoff=-y_min)
    projected["geometry"] = projected.geometry.scale(xfact=0.001, yfact=0.001, origin=(0, 0))
    projected.attrs["utm_epsg"] = utm_epsg(centre.x, centre.y)
    return projected


def decorate(ax, fields: gpd.GeoDataFrame, *, unit: str = "km") -> None:
    """Apply extent, equal aspect, kilometre ticks, north arrow, and scale bar."""

    if fields.empty:
        return
    x_min, y_min, x_max, y_max = fields.total_bounds
    ax.set_xlim(*view_extent(x_min, x_max, y_min, y_max)[:2])
    ax.set_ylim(*view_extent(x_min, x_max, y_min, y_max)[2:])
    ax.set_aspect("equal")
    ax.grid(True, color=style.GRID, linewidth=0.5, alpha=0.8)
    ax.set_axisbelow(True)

    zone = fields.attrs.get("utm_epsg", "")
    ax.set_xlabel(f"{unit} east of farm SW (UTM {zone})")
    ax.set_ylabel(f"{unit} north")

    span_x = max(x_max - x_min, 1e-6)
    span_y = max(y_max - y_min, 1e-6)
    bar = style.nice_scale_km(max(span_x, span_y))
    style.draw_scale_bar(ax, x_min + 0.04 * span_x, y_min + 0.05 * span_y, bar)
    style.draw_north_arrow(ax)


def annotate_fields(ax, fields: gpd.GeoDataFrame, column: str, *, min_km2: float = 0.0) -> None:
    """Label fields at their representative point, skipping slivers."""

    for _, row in fields.iterrows():
        if row.geometry.area < min_km2:
            continue
        point = row.geometry.representative_point()
        ax.annotate(
            str(row[column]),
            xy=(point.x, point.y),
            xytext=(0, 0),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=6.6,
            color=style.INK,
            zorder=15,
            bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                      edgecolor="none", alpha=0.72),
        )


__all__ = ["decorate", "project_farm", "utm_epsg", "view_extent", "annotate_fields"]
