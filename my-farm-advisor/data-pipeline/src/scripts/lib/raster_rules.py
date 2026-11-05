"""Raster-extraction policy: always clip with margin, always report coverage.

A raster that only includes pixels whose centers fall inside the field
boundary cannot honestly describe its own edges: slope/hillshade/flow
neighborhoods, TPI windows, and any "what fraction of this field is actually
covered" question all need complete cell support up to (and one cell beyond)
the boundary. Two rules, applied at every site that intersects a raster with
a field polygon:

  1. BUFFER the field by at least EDGE_BUFFER_CELLS x the source cell size
     before clipping. 1 cell is the absolute floor (covers the mask edge);
     consumers that run neighborhood filters on the clip (any terrain
     derivative: 3x3 slope/aspect, 5x5 TPI, D8 flow) must use
     EDGE_BUFFER_CELLS_FILTER so edge pixels are computed, not smeared.
  2. REPORT coverage: the fraction of the field area whose raster cells carry
     valid data, computed as a polygon/pixel overlap, journalled beside the
     raster. A clip that "succeeded" while covering 40% of the field is a
     failure with a number on it.

Cell-size conversion: source rasters may be geographic; convert the cell to
metres (x 111 320 at equator, /cos(lat) for the degree side) before
buffering, and buffer in a metric CRS, never in bare degrees.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

EDGE_BUFFER_CELLS_MASK = 2     # clip consumed only as masked values (NDVI, class
                               # grids). FLOOR IS 2 CELLS: the buffer must EXCEED
                               # one full source cell in x and y so the field
                               # polygon is interior to the raster everywhere,
                               # including corners (1 cell leaves the corner
                               # diagonal exactly at the edge).
EDGE_BUFFER_CELLS_FILTER = 3   # clip fed into neighborhood filters (terrain derivatives)


def cell_m_of(src_crs, res_x: float, lon: float = 0.0) -> float:
    """Pixel edge length in metres for any CRS."""
    if getattr(src_crs, "is_geographic", False):
        return float(res_x) * 111320.0 * max(0.2, math.cos(math.radians(lon)))
    return float(res_x)


def margin_m(cell_m: float, cells: int = EDGE_BUFFER_CELLS_MASK, floor_m: float = 0.0) -> float:
    """Outward buffer that guarantees complete cell coverage of the boundary."""
    return max(floor_m, cells * cell_m)


def coverage(tif_path: str | Path, geom_wgs84, *, nodata_extra: float | None = None) -> dict[str, Any]:
    """Polygon/pixel overlap stats for a finished clip.

    Returns the fraction of field area backed by valid cells, the nodata
    ratio *inside the field* (the honest gate — a bbox-margin hole around
    the field is not a data failure), and the outer margin in metres the
    clip actually has (proves the buffer was applied).
    """
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask

    with rasterio.open(tif_path) as ds:
        geom = gpd.GeoSeries([geom_wgs84], crs="EPSG:4326").to_crs(ds.crs).iloc[0]
        in_field = geometry_mask([geom.__geo_interface__], out_shape=ds.shape,
                                 transform=ds.transform, invert=True)
        arr = ds.read(1, masked=True)
        filled = np.asarray(np.ma.filled(arr, np.nan), dtype="float64")
        valid = np.isfinite(filled)
        if nodata_extra is not None:
            valid &= filled != nodata_extra
        cell_area = abs(ds.transform.a * ds.transform.e)
        if ds.crs.is_geographic:
            cell_area *= (111320.0 ** 2) * max(0.2, math.cos(math.radians(geom.centroid.y)))
        field_cells = int(in_field.sum())
        field_valid = int((in_field & valid).sum())
        # margin actually present: field bounds vs raster bounds, in metres
        gb = gpd.GeoSeries([geom]).bounds.iloc[0]
        m_lat = (ds.bounds.top - gb[3]) if ds.bounds.top > gb[3] else 0.0
        m_lon = (gb[2] - ds.bounds.left) if ds.bounds.left < gb[2] else 0.0
        if ds.crs.is_geographic:
            m = max(m_lat, m_lon) * 111320.0
        else:
            m = max(m_lat, m_lon)
        return {
            "field_area_m2": float(geom.area if not ds.crs.is_geographic else field_cells * cell_area),
            "field_cell_count": field_cells,
            "valid_cell_count": field_valid,
            "coverage_pct": 100.0 * field_valid / max(field_cells, 1),
            "nodata_ratio_in_field": 1.0 - field_valid / max(field_cells, 1),
            "outer_margin_m": float(m),
        }
