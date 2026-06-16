#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
"""Generate a self-contained Leaflet HTML web map for each grower.

Scans the runtime grower tree, reads farm-level field_boundaries.geojson
files, and produces a grower_map.html per grower under
growers/<grower>/derived/maps/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

from paths import DATA_ROOT, GROWERS_ROOT, farm_boundary_path, farm_dir


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
#container {{ display: flex; height: 100vh; }}
#sidebar {{
  width: 280px; background: #f8f9fa; border-right: 1px solid #ddd;
  padding: 16px; overflow-y: auto; flex-shrink: 0;
}}
#sidebar h2 {{ font-size: 1.1em; margin-bottom: 12px; color: #1B5E20; }}
#sidebar p {{ font-size: 0.85em; color: #555; margin-bottom: 12px; }}
#field-list {{ list-style: none; }}
#field-list li {{
  padding: 8px 10px; margin: 2px 0; border-radius: 4px;
  cursor: pointer; font-size: 0.9em; background: #fff;
  border: 1px solid #e0e0e0; transition: background 0.15s;
}}
#field-list li:hover {{ background: #e8f5e9; border-color: #66bb6a; }}
#field-list li .field-name {{ font-weight: 600; color: #1B5E20; }}
#field-list li .field-farm {{ font-size: 0.8em; color: #777; }}
#map {{ flex: 1; }}
.leaflet-popup-content {{ font-size: 0.9em; line-height: 1.5; }}
.popup-label {{ font-weight: 600; color: #333; }}
</style>
</head>
<body>
<div id="container">
<div id="sidebar">
<h2>{grower_display}</h2>
<p>{farm_count} farm{farm_count_plural} &middot; {field_count} field{field_count_plural}</p>
<ul id="field-list">
{field_list_items}
</ul>
</div>
<div id="map"></div>
</div>
<script>
var map = L.map('map', {{ zoomControl: true }});

var satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: '&copy; Esri, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
  maxZoom: 19,
}});

var osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}});

satellite.addTo(map);

var baseMaps = {{
  "Satellite": satellite,
  "Street Map": osm,
}};

L.control.layers(baseMaps).addTo(map);

var geojsonData = {geojson};

var fieldLayers = [];
var bounds = L.latLngBounds();

L.geoJSON(geojsonData, {{
  style: function(feature) {{
    return {{
      color: feature.properties._color || '#2E7D32',
      weight: 2,
      fillOpacity: 0.35,
    }};
  }},
  onEachFeature: function(feature, layer) {{
    fieldLayers.push({{
      id: feature.properties.field_id,
      layer: layer,
    }});
    if (layer.getBounds) {{
      bounds.extend(layer.getBounds());
    }}
    layer.bindPopup(
      '<div><span class="popup-label">Field:</span> ' + (feature.properties.display_name || feature.properties.field_id) + '</div>' +
      '<div><span class="popup-label">Farm:</span> ' + (feature.properties._farm_name || '') + '</div>' +
      '<div><span class="popup-label">Grower:</span> ' + (feature.properties._grower_name || '') + '</div>' +
      '<div><span class="popup-label">Area:</span> ' + (feature.properties.area_acres ? feature.properties.area_acres.toFixed(1) + ' ac' : '') + '</div>' +
      (feature.properties.county_name ? '<div><span class="popup-label">County:</span> ' + feature.properties.county_name + '</div>' : '')
    );
  }}
}}).addTo(map);

if (bounds.isValid()) {{
  map.fitBounds(bounds, {{ padding: [30, 30] }});
}}

function zoomToField(fieldId) {{
  for (var i = 0; i < fieldLayers.length; i++) {{
    if (fieldLayers[i].id === fieldId) {{
      var layer = fieldLayers[i].layer;
      if (layer.getBounds) {{
        map.fitBounds(layer.getBounds(), {{ padding: [30, 30] }});
      }} else if (layer.getLatLng) {{
        map.setView(layer.getLatLng(), 16);
      }}
      layer.openPopup();
      break;
    }}
  }}
}}
</script>
</body>
</html>"""


FARM_COLORS = [
    "#2E7D32",
    "#1565C0",
    "#E65100",
    "#6A1B9A",
    "#00838F",
    "#C62828",
    "#F9A825",
    "#4E342E",
    "#37474F",
    "#558B2F",
]


def _discover_growers() -> list[str]:
    return sorted(
        d.name for d in GROWERS_ROOT.iterdir() if d.is_dir() and (d / "farms").is_dir()
    )


def _discover_farms(grower_slug: str) -> list[str]:
    farms_dir = GROWERS_ROOT / grower_slug / "farms"
    return sorted(d.name for d in farms_dir.iterdir() if d.is_dir())


def _load_farm_json(grower_slug: str, farm_slug: str) -> dict:
    path = farm_dir(grower_slug, farm_slug) / "farm.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _load_grower_json(grower_slug: str) -> dict:
    path = GROWERS_ROOT / grower_slug / "grower.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _build_field_list_html(items: list[dict]) -> str:
    lines = []
    for item in items:
        name = item.get("display_name") or item.get("field_id", "?")
        farm = item.get("_farm_name", "")
        fid = item.get("field_id", "")
        lines.append(
            f'<li onclick="zoomToField({json.dumps(fid)})">'
            f'<div class="field-name">{name}</div>'
            f'<div class="field-farm">{farm}</div>'
            f"</li>"
        )
    return "\n".join(lines)


def generate_grower_map(grower_slug: str) -> Path:
    grower_meta = _load_grower_json(grower_slug)
    grower_display = grower_meta.get("display_name", grower_slug)

    all_features: list[dict] = []
    field_list_items: list[dict] = []

    farms = _discover_farms(grower_slug)
    if not farms:
        print(f"  [skip] no farms found for grower {grower_slug}")
        return None

    for idx, farm_slug in enumerate(farms):
        boundary_path = farm_boundary_path(grower_slug, farm_slug)
        if not boundary_path.exists():
            print(f"  [skip] no boundary file for {grower_slug}/{farm_slug}")
            continue

        farm_meta = _load_farm_json(grower_slug, farm_slug)
        farm_display = farm_meta.get("display_name", farm_slug)
        color = FARM_COLORS[idx % len(FARM_COLORS)]

        gdf = gpd.read_file(boundary_path)
        for _, row in gdf.iterrows():
            props = dict(row.drop("geometry").to_dict())
            props["_color"] = color
            props["_farm_name"] = farm_display
            props["_grower_name"] = grower_display
            geom = row.geometry
            feat = {
                "type": "Feature",
                "properties": props,
                "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0][
                    "geometry"
                ],
            }
            all_features.append(feat)
            field_list_items.append(props)

    if not all_features:
        print(f"  [skip] no field features found for grower {grower_slug}")
        return None

    fc = {"type": "FeatureCollection", "features": all_features}
    geojson_str = json.dumps(fc, default=str)

    field_list_html = _build_field_list_html(field_list_items)
    plural_farm = "s" if len(farms) != 1 else ""
    plural_field = "s" if len(all_features) != 1 else ""

    html = HTML_TEMPLATE.format(
        title=f"Fields - {grower_display}",
        grower_display=grower_display,
        farm_count=len(farms),
        farm_count_plural=plural_farm,
        field_count=len(all_features),
        field_count_plural=plural_field,
        field_list_items=field_list_html,
        geojson=geojson_str,
    )

    out_dir = GROWERS_ROOT / grower_slug / "derived" / "maps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "grower_map.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  [ok]  {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate grower-level interactive web maps from pipeline field boundaries."
    )
    parser.add_argument(
        "--grower-slug",
        default=None,
        help="Generate map for a single grower. If omitted, generates for all growers.",
    )
    args = parser.parse_args()

    if args.grower_slug:
        slugs = [args.grower_slug]
    else:
        slugs = _discover_growers()

    for slug in slugs:
        print(f"[grower] {slug}")
        generate_grower_map(slug)


if __name__ == "__main__":
    main()
