#!/usr/bin/env python3
"""Generate a lightweight interactive HTML web map for a grower's farm fields.

This subskill creates a standalone Leaflet-based map using Folium. It reads the
farm boundary GeoJSON produced by the data pipeline, renders field polygons on a
CartoDB Positron basemap, and adds click popups with field metadata. A simple
field list sidebar allows quick zoom-to-field navigation.

Usage (from runtime src root):
    python scripts/reporting/grower_web_map/generate_grower_web_map.py \
        --grower-slug illinois-grower \
        --farm-slug illinois-grower-farm \
        --farm-name "Illinois Demo Farm"

Output:
    growers/<grower>/farms/<farm>/derived/reports/<prefix>_grower_web_map.html
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import textwrap
from pathlib import Path
from typing import Any

import geopandas as gpd

# Ensure runtime paths are available
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_SCRIPTS_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (  # noqa: E402
    DATA_ROOT,
    farm_boundary_path,
    farm_reports_dir,
    _normalized_farm_artifact_prefix,
)


def _farm_report_asset_path(grower_slug: str, farm_slug: str) -> Path:
    prefix = _normalized_farm_artifact_prefix(farm_slug)
    return farm_reports_dir(grower_slug, farm_slug) / f"{prefix}_grower_web_map.html"


def _ensure_folium() -> Any:
    try:
        import folium
        return folium
    except ImportError as exc:
        raise RuntimeError(
            "folium is required for grower_web_map. "
            "Install it into the runtime venv: "
            f'{DATA_ROOT.parents[1] / ".venv"}/bin/python -m pip install folium'
        ) from exc


def _style_function(feature: dict) -> dict:
    """Return a consistent polygon style."""
    return {
        "fillColor": "#4CAF50",
        "color": "#2E7D32",
        "weight": 2,
        "fillOpacity": 0.45,
    }


def _highlight_function(feature: dict) -> dict:
    """Return a highlighted polygon style on hover."""
    return {
        "fillColor": "#FF9800",
        "color": "#E65100",
        "weight": 3,
        "fillOpacity": 0.65,
    }


def _popup_html(feature: dict, grower_slug: str, farm_name: str) -> str:
    props = feature.get("properties", {})
    field_id = props.get("field_id", "N/A")
    area_acres = props.get("area_acres", "N/A")
    county = props.get("county_name", "N/A")
    crop = props.get("crop_name", "N/A")
    return textwrap.dedent(
        f"""\
        <div style="font-family: sans-serif; font-size: 13px; min-width: 160px;">
          <strong style="font-size: 15px;">{field_id}</strong><br/>
          <hr style="margin: 6px 0; border: none; border-top: 1px solid #ddd;"/>
          <b>Grower:</b> {grower_slug}<br/>
          <b>Farm:</b> {farm_name}<br/>
          <b>Area:</b> {area_acres} acres<br/>
          <b>County:</b> {county}<br/>
          <b>Crop/Landuse:</b> {crop}
        </div>
        """
    )


def _get_centroid(feature: dict) -> tuple[float, float]:
    """Return (lat, lon) centroid for a GeoJSON feature."""
    geom = feature.get("geometry", {})
    coords = []
    if geom.get("type") == "Polygon":
        coords = geom.get("coordinates", [[]])[0]
    elif geom.get("type") == "MultiPolygon":
        coords = geom.get("coordinates", [[[]]])[0][0]
    if not coords:
        return (0.0, 0.0)
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def generate_web_map(
    *,
    grower_slug: str,
    farm_slug: str,
    farm_name: str,
    output_path: Path | None = None,
) -> Path:
    folium = _ensure_folium()
    from branca.element import Element

    boundary_path = farm_boundary_path(grower_slug, farm_slug)
    if not boundary_path.exists():
        raise FileNotFoundError(f"Farm boundary not found: {boundary_path}")

    gdf = gpd.read_file(boundary_path).to_crs("EPSG:4326")
    if gdf.empty:
        raise ValueError("Farm boundary contains no features.")

    # Compute centroid and bounds for initial view
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    center_lat = (bounds[1] + bounds[3]) / 2.0
    center_lon = (bounds[0] + bounds[2]) / 2.0

    def _zoom_from_bounds(minx: float, miny: float, maxx: float, maxy: float) -> int:
        diff = max(maxx - minx, maxy - miny)
        if diff <= 0:
            return 10
        return max(3, min(int(math.log2(360.0 / diff)), 18))

    zoom_start = _zoom_from_bounds(*bounds)

    # Create map with explicit height
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles="cartodbpositron",
        height="100%",
    )

    # Ensure map container fills viewport
    m.get_root().header.add_child(
        Element(
            "<style>html, body { height: 100%; margin: 0; padding: 0; }"
            " .folium-map { height: 100vh !important; width: 100vw !important; }</style>"
        )
    )

    # Add GeoJSON layer with tooltip
    geojson_data = json.loads(gdf.to_json())
    folium.GeoJson(
        geojson_data,
        name="Fields",
        style_function=_style_function,
        highlight_function=_highlight_function,
        tooltip=folium.GeoJsonTooltip(
            fields=["field_id", "area_acres"],
            aliases=["Field:", "Area (acres):"],
            localize=True,
            sticky=False,
            labels=True,
            style=(
                "background-color: white; color: #333; font-family: sans-serif;"
                " font-size: 12px; padding: 6px; border-radius: 4px;"
            ),
        ),
    ).add_to(m)

    # Add popups via small clickable markers at centroids
    for feature in geojson_data.get("features", []):
        popup_html = _popup_html(feature, grower_slug, farm_name)
        lat, lon = _get_centroid(feature)
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html="", icon_size=(0, 0)),
            popup=folium.Popup(popup_html, max_width=260),
        ).add_to(m)

    # Fit bounds to all fields
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    # Build sidebar field list
    field_list = []
    for feature in geojson_data.get("features", []):
        fid = feature.get("properties", {}).get("field_id", "")
        lat, lon = _get_centroid(feature)
        if fid:
            field_list.append({"id": fid, "lat": lat, "lon": lon})
    field_list.sort(key=lambda x: x["id"])

    list_items = []
    for e in field_list:
        js = (
            f"map.setView([{e['lat']:.6f}, {e['lon']:.6f}], 16); "
            "document.querySelectorAll('.leaflet-popup').forEach(function(p){ p.remove(); }); "
            f"L.popup({{maxWidth:260}}).setLatLng([{e['lat']:.6f}, {e['lon']:.6f}])"
            f".setContent('<b>{e['id']}</b>').openOn(map);"
        )
        li = (
            '<li style="padding:4px 8px; cursor:pointer; border-bottom:1px solid #eee;" '
            f'onclick="{js}" '
            'onmouseover="this.style.backgroundColor=\'#f0f0f0\'" '
            'onmouseout="this.style.backgroundColor=\'transparent\'">'
            f'{e["id"]}</li>'
        )
        list_items.append(li)

    sidebar_items = "\n".join(list_items)
    sidebar_html = textwrap.dedent(
        f"""\
        <div id="field-sidebar" style="
            position: absolute;
            top: 10px;
            left: 10px;
            width: 220px;
            max-height: 90%;
            background: rgba(255,255,255,0.95);
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            font-family: sans-serif;
            font-size: 13px;
            z-index: 9999;
            overflow-y: auto;
            padding-bottom: 8px;
        ">
          <div style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold; font-size: 14px;">
            {farm_name}
            <div style="font-weight: normal; font-size: 11px; color: #666; margin-top: 2px;">
              Grower: {grower_slug} | Fields: {len(field_list)}
            </div>
          </div>
          <ul style="list-style: none; margin: 0; padding: 0;">
            {sidebar_items}
          </ul>
        </div>
        """
    )

    # Inject sidebar as raw HTML (Element does NOT escape)
    m.get_root().html.add_child(Element(sidebar_html))

    # Determine output path
    if output_path is None:
        output_path = _farm_report_asset_path(grower_slug, farm_slug)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))
    print(f"Saved grower web map: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grower interactive web map")
    parser.add_argument("--grower-slug", required=True)
    parser.add_argument("--farm-slug", required=True)
    parser.add_argument("--farm-name", default=None)
    parser.add_argument("--output", default=None, help="Optional output HTML path")
    args = parser.parse_args()

    farm_name = args.farm_name or args.farm_slug.replace("-", " ").title()
    output_path = Path(args.output) if args.output else None

    generate_web_map(
        grower_slug=args.grower_slug,
        farm_slug=args.farm_slug,
        farm_name=farm_name,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
