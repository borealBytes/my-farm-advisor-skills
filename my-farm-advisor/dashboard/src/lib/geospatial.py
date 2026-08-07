#!/usr/bin/env python3
"""
geospatial.py — Build the interactive Plotly choropleth map for field boundaries.

Colors fields by Soil Health Score with hover popups and click info.
"""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def build_field_map(
    boundaries: gpd.GeoDataFrame,
    metrics_df: pd.DataFrame,
    ndvi_df: pd.DataFrame | None = None,
    year_focus: int = 2024,
) -> go.Figure:
    """Build an interactive Plotly choropleth map of fields colored by Soil Health Score.

    Args:
        boundaries: GeoDataFrame with field polygons (must have 'field_id')
        metrics_df: DataFrame with 'field_id', 'shs', 'si', 'conservation_priority', plus soil details
        ndvi_df: Optional DataFrame with per-field-year NDVI stats
        year_focus: Year to show NDVI in popup

    Returns:
        Plotly Figure object
    """
    # Merge metrics into boundaries
    gdf = boundaries.copy()
    gdf = gdf.merge(metrics_df, on="field_id", how="left")

    # Add NDVI for focus year if available
    if ndvi_df is not None and not ndvi_df.empty:
        year_ndvi = ndvi_df[ndvi_df["year"] == year_focus][["field_id", "mean_ndvi"]].copy()
        if not year_ndvi.empty:
            gdf = gdf.merge(year_ndvi, on="field_id", how="left")
            gdf["mean_ndvi"] = gdf["mean_ndvi"].fillna(0)
        else:
            gdf["mean_ndvi"] = 0.0
    else:
        gdf["mean_ndvi"] = 0.0

    # Convert GeoDataFrame to GeoJSON for Plotly
    geojson = json.loads(gdf.to_json())

    # Build hover text
    def _hover_text(row: pd.Series) -> str:
        lines = [
            f"<b>Field:</b> {row.get('field_id', 'N/A')}",
            f"<b>Area:</b> {row.get('area_acres', 0):.1f} acres",
            f"<b>Soil Health Score:</b> {row.get('shs', 0):.1f} / 100",
            f"<b>Sustainability Index:</b> {row.get('si', 0):.1f} / 100",
            f"<b>Conservation Priority:</b> {row.get('conservation_priority', 0):.1f}",
            f"<b>Mean pH:</b> {row.get('ph_mean', 0):.2f}",
            f"<b>Mean OM:</b> {row.get('om_mean', 0):.2f}%",
            f"<b>Mean NDVI ({year_focus}):</b> {row.get('mean_ndvi', 0):.3f}",
        ]
        return "<br>".join(lines)

    gdf["hover_text"] = gdf.apply(_hover_text, axis=1)

    # Create choropleth
    fig = px.choropleth_mapbox(
        gdf,
        geojson=geojson,
        locations="field_id",
        featureidkey="properties.field_id",
        color="shs",
        color_continuous_scale="RdYlGn",
        range_color=(0, 100),
        mapbox_style="carto-positron",
        zoom=12,
        center={"lat": gdf.geometry.centroid.y.mean(), "lon": gdf.geometry.centroid.x.mean()},
        opacity=0.7,
        hover_name="field_id",
        hover_data={
            "shs": True,
            "si": True,
            "conservation_priority": True,
            "area_acres": True,
            "mean_ndvi": True,
        },
        labels={
            "shs": "Soil Health Score",
            "si": "Sustainability Index",
            "conservation_priority": "Conservation Priority",
            "area_acres": "Acres",
            "mean_ndvi": f"Mean NDVI ({year_focus})",
        },
        title="Field Soil Health Score Map",
    )

    fig.update_layout(
        height=550,
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
        coloraxis_colorbar={
            "title": "Soil Health<br>Score",
            "ticksuffix": "/100",
            "len": 0.6,
            "y": 0.5,
        },
        mapbox={
            "center": {"lat": gdf.geometry.centroid.y.mean(), "lon": gdf.geometry.centroid.x.mean()},
            "zoom": 12,
            "style": "carto-positron",
        },
        paper_bgcolor="white",
        title={
            "text": "Field Soil Health Score Map",
            "x": 0.5,
            "xanchor": "center",
        },
    )

    return fig
