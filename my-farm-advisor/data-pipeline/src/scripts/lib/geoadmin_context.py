#!/usr/bin/env python3
"""Geopolitical context for small-footprint site maps.

Any client/site map (BMS, BreedBase, IoT …) that plots a handful of points on
a basemap should say WHERE those points are in admin terms, not just sit on
imagery. This helper reads the cached GeoAdmin layers (L0 countries, L1
states/provinces, L2 counties/census divisions — same files the choropleths
use, no new downloads) and adds to an existing axes:

  * L2 boundaries (subtle white hairlines)
  * L1 boundaries + a state/province name label if any is visible
  * L0 boundaries (white, thicker)
  * the full name of every L2 unit that contains or touches the sites,
    placed so it does not collide with the site markers

Resolution is intentionally cheap: clip to the current axes extent, skip
anything outside. Usage:

    import geopandas as gpd

# Natural Earth country polygons exceed pyogrio's default GeoJSON object
# size cap; lift it before any read in this module.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")
    from geoadmin_context import add_admin_context
    g = gpd.GeoDataFrame(sites, geometry=gpd.points_from_xy(lon, lat),
                         crs="EPSG:4326")
    add_admin_context(ax, g.to_crs("EPSG:3857"), crs="EPSG:3857")
"""

from __future__ import annotations

import os

# Natural Earth / Canada census-division polygons exceed pyogrio's default
# GeoJSON object size cap — and pyogrio captures GDAL config at import, so
# this MUST run before geopandas is imported.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

from pathlib import Path

import geopandas as gpd  # noqa: E402

_MIN_SITE_SEP_M = 15_000  # keep county labels off the site markers


def _geoadmin_root() -> Path:
    root = os.environ.get("DATA_PIPELINE_DATA_ROOT", "").strip()
    if not root:
        raise RuntimeError(
            "DATA_PIPELINE_DATA_ROOT is not set; the GeoAdmin cache lives "
            "under <root>/data-pipeline/shared/geoadmin"
        )
    return Path(root) / "data-pipeline" / "shared" / "geoadmin"


def _read_if_exists(rel: str) -> gpd.GeoDataFrame | None:
    path = _geoadmin_root() / rel
    if not path.exists():
        return None
    return gpd.read_file(path)


def add_admin_context(
    ax,
    sites_utm: gpd.GeoDataFrame,
    crs: str = "EPSG:3857",
    pad_m: float = 12_000,
) -> list[str]:
    """Draw L2/L1/L0 context on `ax` (already showing imagery/points),
    labeling the L2 units around the sites. `sites_utm` must be in `crs`.
    Returns the county labels drawn."""
    minx, miny, maxx, maxy = ax.get_xlim()[0], ax.get_ylim()[0], ax.get_xlim()[1], ax.get_ylim()[1]
    view = gpd.GeoSeries(
        gpd.points_from_xy([minx + pad_m, maxx - pad_m], [miny + pad_m, maxy - pad_m])
    ).set_crs(crs)
    from shapely.geometry import box

    view_box = box(minx + pad_m, miny + pad_m, maxx - pad_m, maxy - pad_m)
    view_gdf = gpd.GeoDataFrame(geometry=[view_box], crs=crs)

    site_pts = sites_utm.geometry

    # --- L2 counties / census divisions -------------------------------------
    drawn: list[str] = []
    for rel, name_col in (
        ("l2_counties/counties_usa.geojson", "county_name_full"),
        ("l2_counties/counties_canada.geojson", "NAME_2"),
    ):
        g = _read_if_exists(rel)
        if g is None:
            continue
        g = g.to_crs(crs)
        hits = g[g.intersects(view_box)]
        if hits.empty:
            continue
        hits.boundary.plot(ax=ax, color="#ffffff", linewidth=0.5, alpha=0.8, zorder=3)
        for _, row in hits.iterrows():
            label = str(row.get(name_col) or "").strip()
            if not label or label.lower() == "nan":
                continue
            pt = row.geometry.representative_point()
            # nudge off a site marker if they coincide
            if len(site_pts) and pt.distance(site_pts.union_all()) < _MIN_SITE_SEP_M:
                from shapely.geometry import Point

                pt = Point(pt.x + _MIN_SITE_SEP_M / 2, pt.y + _MIN_SITE_SEP_M / 2)
            ax.annotate(
                label,
                (pt.x, pt.y),
                fontsize=7.5,
                color="white",
                zorder=4,
                ha="center",
                bbox=dict(boxstyle="round,pad=0.18", fc="#374151", ec="none", alpha=0.55),
            )
            drawn.append(label)

    # --- L1 states / provinces ----------------------------------------------
    for rel, name_col in (
        ("l1_states/states_usa.geojson", "state_name"),
        ("l1_states/states_canada.geojson", "NAME_1"),
    ):
        g = _read_if_exists(rel)
        if g is None:
            continue
        g = g.to_crs(crs)
        hits = g[g.intersects(view_box)]
        if hits.empty:
            continue
        hits.boundary.plot(ax=ax, color="#ffffff", linewidth=1.0, alpha=0.95, zorder=5)
        view_gdf = gpd.GeoDataFrame(geometry=[view_box], crs=crs)
        clipped = gpd.clip(hits, view_gdf)
        for idx, part in clipped.iterrows():
            if part.geometry.is_empty:
                continue
            name = str(hits.loc[idx].get(name_col) or "").strip()
            if not name or name.lower() == "nan":
                continue
            pt = part.geometry.representative_point()
            ax.annotate(
                name.upper(),
                (pt.x, pt.y),
                fontsize=7.5,
                color="#f8fafc",
                zorder=6,
                ha="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="#111827", ec="none", alpha=0.62),
            )

    # --- L0 countries ---------------------------------------------------------
    c0 = _read_if_exists("l0_countries/countries.geojson")
    if c0 is not None:
        c0 = c0.to_crs(crs)
        hits = c0[c0.intersects(view_box)]
        if not hits.empty:
            hits.boundary.plot(ax=ax, color="#ffffff", linewidth=1.6, zorder=6)

    return drawn
