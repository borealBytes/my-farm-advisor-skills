#!/usr/bin/env python3
"""Generate a lightweight interactive HTML web map for a grower's farms.

Usage:
    python scripts/reporting/generate_grower_web_map.py \\
        --grower-slug il-grower [--farm-slug il-grower-illinois]

Output: growers/<grower>/farms/<farm>/derived/dashboards/grower_web_map.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_LIB))

from paths import (  # noqa: E402
    DATA_ROOT,
    GROWERS_ROOT,
    farm_boundary_path,
    farm_dashboards_dir,
)

FIELD_COLORS = [
    "#2E7D32",
    "#1565C0",
    "#E65100",
    "#F9A825",
    "#8E24AA",
    "#00ACC1",
    "#7B1FA2",
    "#AD1457",
    "#C62828",
    "#283593",
    "#00695C",
    "#BF360C",
    "#4A148C",
    "#1B5E20",
    "#0D47A1",
    "#E65100",
    "#004D40",
    "#880E4F",
    "#3E2723",
    "#311B92",
]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_farms(grower_slug: str, farm_slug: str | None = None) -> list[dict[str, str]]:
    grower_root = GROWERS_ROOT / grower_slug
    if not grower_root.is_dir():
        raise FileNotFoundError(f"grower directory not found: {grower_root}")

    farms: list[dict[str, str]] = []
    farms_dir = grower_root / "farms"
    if not farms_dir.is_dir():
        return farms

    for farm_entry in sorted(farms_dir.iterdir()):
        if not farm_entry.is_dir():
            continue
        f_slug = farm_entry.name
        if farm_slug and f_slug != farm_slug:
            continue
        boundary = farm_entry / "boundary" / "field_boundaries.geojson"
        if not boundary.exists():
            print(f"skip  {grower_slug}/{f_slug} — no field_boundaries.geojson")
            continue
        farm_json = _load_json(farm_entry / "farm.json")
        farms.append(
            {
                "grower_slug": grower_slug,
                "farm_slug": f_slug,
                "farm_name": farm_json.get("display_name", f_slug.replace("-", " ").title()),
                "boundary_path": str(boundary),
            }
        )

    if not farms:
        raise RuntimeError(f"no farms with boundaries found for grower {grower_slug}")
    return farms


def _read_boundary_geojson(boundary_path: Path) -> dict:
    data = _load_json(boundary_path)
    if not data:
        raise RuntimeError(f"empty or missing boundary GeoJSON: {boundary_path}")
    return data


def _field_properties(feature: dict) -> dict:
    props = feature.get("properties", {})
    return {
        "field_id": props.get("field_id", ""),
        "area_acres": round(float(props.get("area_acres", 0)), 1),
        "county_name": props.get("county_name", ""),
        "crop_name": props.get("crop_name", ""),
    }


def _generate_html(
    geojson_data: dict,
    grower_slug: str,
    farm_slug: str,
    farm_name: str,
) -> str:
    features = geojson_data.get("features", [])

    field_list_entries: list[str] = []
    field_js_lookup: list[str] = []
    for idx, feature in enumerate(features):
        props = _field_properties(feature)
        field_id = props["field_id"]
        color = FIELD_COLORS[idx % len(FIELD_COLORS)]
        field_list_entries.append(
            f'<li class="field-item" style="border-left: 4px solid {color}" '
            f'onclick="zoomToField(\'{field_id}\')">'
            f'<span class="field-name">{field_id or "Field " + str(idx + 1)}</span>'
            f'<span class="field-acres">{props["area_acres"]} ac</span>'
            f'</li>'
        )
        field_js_lookup.append(
            f'"{field_id}": {{"color": "{color}", "index": {idx}}},'
        )

    geojson_json = json.dumps(geojson_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{farm_name} — Grower Web Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
#container {{ display: flex; height: 100vh; }}
#sidebar {{
    width: 300px; min-width: 240px;
    background: #f8fafc; border-right: 1px solid #e2e8f0;
    display: flex; flex-direction: column; overflow: hidden;
}}
#sidebar-header {{
    padding: 16px; border-bottom: 1px solid #e2e8f0; background: white;
}}
#sidebar-header h1 {{ font-size: 1.1em; color: #1e293b; margin: 0; }}
#sidebar-header .sub {{
    font-size: 0.8em; color: #64748b; margin-top: 4px;
}}
#field-list {{ flex: 1; overflow-y: auto; padding: 8px 0; }}
.field-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 16px; cursor: pointer; transition: background 0.15s;
    border-bottom: 1px solid #f1f5f9;
}}
.field-item:hover {{ background: #e2e8f0; }}
.field-name {{ font-size: 0.85em; font-weight: 500; color: #334155; }}
.field-acres {{ font-size: 0.78em; color: #64748b; white-space: nowrap; }}
#map {{ flex: 1; }}
.leaflet-popup-content {{ font-size: 0.88em; line-height: 1.5; }}
.leaflet-popup-content b {{ color: #1e293b; }}
@media (max-width: 600px) {{
    #container {{ flex-direction: column; }}
    #sidebar {{ width: 100%; max-height: 40vh; }}
}}
</style>
</head>
<body>
<div id="container">
<div id="sidebar">
    <div id="sidebar-header">
        <h1>{farm_name}</h1>
        <div class="sub">Grower: {grower_slug} &middot; {len(features)} fields</div>
    </div>
    <ul id="field-list">
        {chr(10).join("        " + entry for entry in field_list_entries)}
    </ul>
</div>
<div id="map"></div>
</div>
<script>
var fieldColors = {{
    {chr(10).join("    " + entry for entry in field_js_lookup)}
}};

var geojson = {geojson_json};

var map = L.map('map', {{ zoomControl: true }});

var osmLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
}});

var satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 19,
}});

satelliteLayer.addTo(map);

var baseMaps = {{
    "Street Map": osmLayer,
    "Satellite": satelliteLayer
}};

L.control.layers(baseMaps).addTo(map);

var fieldLayer = L.geoJSON(geojson, {{
    style: function(feature) {{
        var fid = feature.properties.field_id || '';
        var cinfo = fieldColors[fid];
        return {{
            color: cinfo ? cinfo.color : '#757575',
            weight: 2,
            opacity: 0.9,
            fillOpacity: 0.25,
            fillColor: cinfo ? cinfo.color : '#757575',
        }};
    }},
    onEachFeature: function(feature, layer) {{
        var p = feature.properties;
        var popup = '<b>Grower:</b> {grower_slug}<br>'
                  + '<b>Farm:</b> {farm_name}<br>'
                  + '<b>Field:</b> ' + (p.field_id || '—') + '<br>'
                  + '<b>Area:</b> ' + (p.area_acres != null ? p.area_acres.toFixed(1) : '—') + ' acres<br>'
                  + '<b>County:</b> ' + (p.county_name || '—') + '<br>'
                  + '<b>OSM Land Use:</b> ' + (p.crop_name || '—');
        layer.bindPopup(popup);

        layer.on('mouseover', function() {{
            layer.setStyle({{ weight: 4, fillOpacity: 0.45 }});
        }});
        layer.on('mouseout', function() {{
            fieldLayer.resetStyle(layer);
        }});
    }}
}}).addTo(map);

map.fitBounds(fieldLayer.getBounds().pad(0.1));

function zoomToField(fieldId) {{
    fieldLayer.eachLayer(function(layer) {{
        if (layer.feature && layer.feature.properties.field_id === fieldId) {{
            map.fitBounds(layer.getBounds().pad(0.3));
            layer.openPopup();
        }}
    }});
}}
</script>
</body>
</html>"""


def _farm_name(boundary_path: Path, fallback: str) -> str:
    farm_dir = boundary_path.parent.parent
    farm_json = _load_json(farm_dir / "farm.json")
    return farm_json.get("display_name", fallback)


def generate_map(grower_slug: str, farm_slug: str) -> Path:
    boundary_path = farm_boundary_path(grower_slug, farm_slug)

    if not boundary_path.exists():
        raise FileNotFoundError(f"field boundaries not found: {boundary_path}")

    geojson_data = _read_boundary_geojson(boundary_path)
    farm_name = _farm_name(boundary_path, farm_slug.replace("-", " ").title())

    html = _generate_html(
        geojson_data=geojson_data,
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        farm_name=farm_name,
    )

    output_dir = farm_dashboards_dir(grower_slug, farm_slug)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "grower_web_map.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a grower-level interactive web map from pipeline outputs"
    )
    parser.add_argument(
        "--grower-slug",
        default=os.environ.get("AG_GROWER_SLUG", "default-grower"),
    )
    parser.add_argument(
        "--farm-slug",
        default=os.environ.get("AG_FARM_SLUG") or None,
    )
    args = parser.parse_args()

    farms = _discover_farms(args.grower_slug, args.farm_slug)
    for farm in farms:
        try:
            output = generate_map(
                grower_slug=farm["grower_slug"],
                farm_slug=farm["farm_slug"],
            )
            relative = str(output.resolve(strict=False).relative_to(_RUNTIME_BASE))
            print(f"  ok  {relative}")
        except Exception as exc:
            print(f"fail  {farm['grower_slug']}/{farm['farm_slug']}: {exc}")

    print(f"\nGenerated {len(farms)} map(s) for grower {args.grower_slug}")


if __name__ == "__main__":
    main()
