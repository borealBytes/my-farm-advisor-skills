#!/usr/bin/env python3
"""Generate a lightweight interactive Leaflet web map for each grower,
showing field polygon boundaries with clickable metadata popups."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from paths import DATA_ROOT, GROWERS_ROOT, farm_boundary_path, farm_dir, grower_dir
from runtime_paths import resolve_runtime_paths

resolve_runtime_paths()

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  #map {{ height: 100%; width: 100%; }}
  .leaflet-popup-content {{ font-size: 14px; line-height: 1.5; }}
  .leaflet-popup-content strong {{ color: #2c5f2d; }}
  #sidebar {{
    position: absolute; top: 10px; right: 10px; z-index: 1000;
    background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    width: 260px; max-height: 70vh; display: flex; flex-direction: column;
    font-size: 13px;
  }}
  #sidebar-header {{
    padding: 10px 14px; background: #2c5f2d; color: white;
    border-radius: 8px 8px 0 0; font-weight: 600; font-size: 14px;
  }}
  #sidebar-list {{
    overflow-y: auto; padding: 6px 0; flex: 1;
  }}
  .sidebar-item {{
    padding: 7px 14px; cursor: pointer; border-left: 3px solid transparent;
    transition: all 0.15s; display: flex; justify-content: space-between;
  }}
  .sidebar-item:hover {{ background: #f0f7f0; border-left-color: #2c5f2d; }}
  .sidebar-item .field-id {{ font-weight: 500; }}
  .sidebar-item .field-acres {{ color: #666; font-size: 12px; }}
  .sidebar-farm-header {{
    padding: 6px 14px 4px; font-weight: 600; color: #555;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    background: #fafafa; border-bottom: 1px solid #eee;
  }}
  .color-dot {{
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    margin-right: 6px; flex-shrink: 0;
  }}
  .sidebar-item-inner {{ display: flex; align-items: center; gap: 6px; }}
  @media (max-width: 600px) {{
    #sidebar {{ width: 180px; font-size: 12px; top: 50px; right: 6px; max-height: 50vh; }}
  }}
</style>
</head>
<body>
<div id="map"></div>
<div id="sidebar">
  <div id="sidebar-header">Fields</div>
  <div id="sidebar-list">{sidebar_items}</div>
</div>
<script>
const map = L.map('map', {{ zoomControl: true }}).setView([{center_lat}, {center_lon}], {zoom});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}}).addTo(map);

const fields = {geo_json};

const colorPalette = {palette};
let colorIdx = 0;
function nextColor() {{
  const c = colorPalette[colorIdx % colorPalette.length];
  colorIdx++;
  return c;
}}

const fieldLayers = [];
const fieldMap = {{}};

L.geoJSON(fields, {{
  style: function(feature) {{
    const c = feature.properties._color || (feature.properties._color = nextColor());
    return {{
      fillColor: c, color: '#333', weight: 1.5, fillOpacity: 0.5
    }};
  }},
  onEachFeature: function(feature, layer) {{
    const p = feature.properties;
    const html = '<strong>Grower:</strong> ' + p._grower + '<br>' +
                 '<strong>Farm:</strong> ' + p._farm + '<br>' +
                 '<strong>Field:</strong> ' + p.field_id + '<br>' +
                 '<strong>Crop:</strong> ' + (p.crop_name || 'Unknown') + '<br>' +
                 '<strong>Area:</strong> ' + p.area_acres.toFixed(1) + ' acres<br>' +
                 '<strong>County:</strong> ' + (p.county_name || '');
    layer.bindPopup(html);
    fieldLayers.push(layer);
    fieldMap[p.field_id] = layer;
  }}
}}).addTo(map);

if (fieldLayers.length > 0) {{
  const group = L.featureGroup(fieldLayers);
  map.fitBounds(group.getBounds().pad(0.05));
}}

function zoomToField(fieldId) {{
  const layer = fieldMap[fieldId];
  if (layer) {{
    map.fitBounds(layer.getBounds().pad(0.1));
    layer.openPopup();
  }}
}}
</script>
</body>
</html>"""

_COLOR_PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9a6324", "#800000", "#aaffc3",
]


def _discover_growers() -> list[dict]:
    growers = []
    for grower_dir_path in sorted(GROWERS_ROOT.glob("*")):
        if not grower_dir_path.is_dir():
            continue
        grower_slug = grower_dir_path.name
        grower_json = grower_dir_path / "grower.json"
        grower_info = {"slug": grower_slug, "farms": []}
        if grower_json.exists():
            try:
                grower_info["data"] = json.loads(grower_json.read_text(encoding="utf-8"))
            except Exception:
                grower_info["data"] = {}
        farms_dir = grower_dir_path / "farms"
        if farms_dir.is_dir():
            for farm_dir_path in sorted(farms_dir.glob("*")):
                if not farm_dir_path.is_dir():
                    continue
                farm_slug = farm_dir_path.name
                farm_json = farm_dir_path / "farm.json"
                farm_info = {"slug": farm_slug}
                if farm_json.exists():
                    try:
                        farm_info["data"] = json.loads(farm_json.read_text(encoding="utf-8"))
                    except Exception:
                        farm_info["data"] = {}
                boundary_path = farm_boundary_path(grower_slug, farm_slug)
                if boundary_path.exists():
                    farm_info["boundary_path"] = boundary_path
                grower_info["farms"].append(farm_info)
        growers.append(grower_info)
    return growers


def _compute_center(features: list[dict]) -> tuple[float, float, int]:
    lats, lons = [], []
    for f in features:
        coords = _extract_coords(f.get("geometry", {}))
        for lon, lat in coords:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return (40.0, -95.0, 5)
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    lats_range = max(lats) - min(lats)
    lons_range = max(lons) - min(lons)
    max_range = max(lats_range, lons_range)
    if max_range < 0.01:
        zoom = 15
    elif max_range < 0.1:
        zoom = 13
    elif max_range < 0.5:
        zoom = 11
    elif max_range < 2:
        zoom = 9
    else:
        zoom = 7
    return (center_lat, center_lon, zoom)


def _extract_coords(geometry: dict) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    if geometry.get("type") == "Polygon":
        for ring in geometry.get("coordinates", []):
            coords.extend((c[0], c[1]) for c in ring)
    elif geometry.get("type") == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            for ring in polygon:
                coords.extend((c[0], c[1]) for c in ring)
    return coords


def _build_sidebar(growers: list[dict], features: list[dict]) -> str:
    items = []
    feature_idx = 0
    color_idx = 0
    for grower in growers:
        for farm in grower.get("farms", []):
            farm_name = farm.get("data", {}).get("display_name", farm["slug"])
            items.append(
                f'<div class="sidebar-farm-header">{farm_name}</div>'
            )
            farm_feature_count = sum(
                1 for f in features
                if f["properties"]["_grower"] == grower["slug"]
                and f["properties"]["_farm_slug"] == farm["slug"]
            )
            for _ in range(farm_feature_count):
                feature = features[feature_idx]
                p = feature["properties"]
                color = _COLOR_PALETTE[color_idx % len(_COLOR_PALETTE)]
                color_idx += 1
                items.append(
                    f'<div class="sidebar-item" onclick="zoomToField(\'{p["field_id"]}\')">'
                    f'<div class="sidebar-item-inner">'
                    f'<span class="color-dot" style="background:{color}"></span>'
                    f'<span class="field-id">{p["field_id"]}</span>'
                    f'</div>'
                    f'<span class="field-acres">{p["area_acres"]:.1f} ac</span>'
                    f'</div>'
                )
                feature_idx += 1
    return "".join(items) if items else "<div style='padding:14px;color:#999;'>No fields found</div>"


def generate_grower_map(grower_slug: str | None = None) -> list[Path]:
    growers = _discover_growers()
    if grower_slug:
        growers = [g for g in growers if g["slug"] == grower_slug]
        if not growers:
            print(f"ERROR: grower '{grower_slug}' not found")
            sys.exit(1)

    outputs: list[Path] = []
    for grower in growers:
        features: list[dict] = []
        for farm in grower.get("farms", []):
            boundary_path = farm.get("boundary_path")
            if not boundary_path or not boundary_path.exists():
                continue
            try:
                gdf = gpd.read_file(boundary_path)
            except Exception as exc:
                print(f"  warn  {grower['slug']}/{farm['slug']}: could not read boundaries: {exc}")
                continue
            farm_name = farm.get("data", {}).get("display_name", farm["slug"])
            grower_name = grower.get("data", {}).get("display_name", grower["slug"])
            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom is None or geom.is_empty:
                    continue
                props = {
                    "field_id": str(row.get("field_id", "")),
                    "crop_name": str(row.get("crop_name", "")),
                    "area_acres": float(row.get("area_acres", 0)),
                    "county_name": str(row.get("county_name", "")),
                    "state_fips": str(row.get("state_fips", "")),
                    "_grower": grower_name,
                    "_grower_slug": grower["slug"],
                    "_farm": farm_name,
                    "_farm_slug": farm["slug"],
                }
                geom_json = json.loads(gpd.GeoSeries([geom]).to_json())
                if geom_json.get("features"):
                    feat = geom_json["features"][0]
                    feat["properties"] = props
                    features.append(feat)

        if not features:
            print(f"  warn  {grower['slug']}: no field features found, skipping map")
            continue

        center_lat, center_lon, zoom = _compute_center(features)
        sidebar_items = _build_sidebar([grower], features)
        geo_json_str = json.dumps({"type": "FeatureCollection", "features": features})

        safe_grower = grower["slug"].replace('"', "")
        title = f"Grower Web Map - {grower.get('data', {}).get('display_name', grower['slug'])}"
        html = _HTML_TEMPLATE.format(
            title=title,
            center_lat=center_lat,
            center_lon=center_lon,
            zoom=zoom,
            geo_json=geo_json_str,
            sidebar_items=sidebar_items,
            palette=json.dumps(_COLOR_PALETTE),
        )

        output_dir = grower_dir(grower["slug"]) / "derived" / "dashboards"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "grower_web_map.html"
        output_path.write_text(html, encoding="utf-8")
        size_kb = len(html) / 1024
        field_count = len(features)
        print(f"  ok    {grower['slug']}: {field_count} fields, {size_kb:.0f} KB -> {output_path}")
        outputs.append(output_path)

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate interactive Leaflet web maps for growers"
    )
    parser.add_argument(
        "--grower-slug", default=None,
        help="Generate map for a specific grower only (default: all growers)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Grower Web Map Generator")
    print("=" * 60)

    outputs = generate_grower_map(grower_slug=args.grower_slug)

    if outputs:
        print()
        print("  Outputs:")
        for path in outputs:
            print(f"    {path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
