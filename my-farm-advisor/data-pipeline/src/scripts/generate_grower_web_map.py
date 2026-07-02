#!/usr/bin/env python3
"""Generate a lightweight interactive HTML web map for a single grower/farm.

Usage:
    export DATA_PIPELINE_DATA_ROOT=/path/to/runtime
    python generate_grower_web_map.py <grower-slug> \
        --farm-slug <farm-slug> \
        --output <output.html>

Reads field boundary GeoJSON from the canonical pipeline tree and emits a
single self-contained HTML file with Leaflet.js (CDN), embedded GeoJSON,
clickable field popups, and a sidebar field list for zoom-to-field.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from paths import (
    DATA_ROOT,
    farm_boundary_path,
    farm_dir,
    grower_dir,
)


# Distinct fill colors for fields (8-cycle, avoids red/green for accessibility)
FIELD_COLORS = [
    "#e74c3c", "#3498db", "#f39c12", "#9b59b6",
    "#1abc9c", "#e67e22", "#2ecc71", "#34495e",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _field_color(idx: int) -> str:
    return FIELD_COLORS[idx % len(FIELD_COLORS)]


def _generate_html(
    geojson_data: dict,
    grower_name: str,
    farm_name: str,
    farm_state: str,
    county_name: str,
) -> str:
    """Build a self-contained Leaflet HTML page."""

    features = geojson_data.get("features", [])
    if not features:
        raise ValueError("No field features found in GeoJSON")

    # Compute center from all field centroids
    lats = []
    lons = []
    for feat in features:
        geom = feat.get("geometry", {})
        coords = _extract_coords(geom)
        if coords:
            lats.extend(c[1] for c in coords)
            lons.extend(c[0] for c in coords)
    center_lat = sum(lats) / len(lats) if lats else 41.0
    center_lon = sum(lons) / len(lons) if lons else -93.0

    # Build field metadata list for JS
    field_meta = []
    for idx, feat in enumerate(features, 1):
        props = feat.get("properties", {})
        field_id = props.get("field_id", f"Field {idx}")
        area = props.get("area_acres", "?")
        crop = props.get("crop_name", "Unknown")
        county = props.get("county_name", county_name)
        field_meta.append(
            {
                "index": idx,
                "fieldId": field_id,
                "area": round(area, 2) if isinstance(area, (int, float)) else area,
                "crop": crop,
                "county": county,
                "color": _field_color(idx - 1),
            }
        )

    geojson_json = json.dumps(geojson_data, separators=(",", ":"))
    field_meta_json = json.dumps(field_meta, separators=(",", ":"))

    # Generate unique div IDs to avoid collisions if multiple maps on one page
    uid = f"{random.randint(1000, 9999)}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{grower_name} – {farm_name}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<style>
  html, body {{ margin:0; padding:0; height:100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  #wrapper{{display:flex;height:100vh;width:100vw;}}
  #sidebar{{width:280px;min-width:240px;background:#f8f9fa;border-right:1px solid #dee2e6;display:flex;flex-direction:column;overflow:hidden;}}
  #sidebar h2{{margin:0;padding:16px 16px 4px;font-size:1.1rem;color:#212529;}}
  #sidebar h3{{margin:0;padding:0 16px 8px;font-size:0.9rem;font-weight:400;color:#495057;}}
  #field-list{{flex:1;overflow-y:auto;padding:0 12px 12px;}}
  .field-item{{padding:10px 12px;margin:6px 0;border-radius:6px;background:#fff;border:1px solid #e9ecef;cursor:pointer;transition:background .15s;}}
  .field-item:hover{{background:#e9ecef;}}
  .field-item .fid{{font-weight:600;font-size:0.9rem;color:#212529;}}
  .field-item .detail{{font-size:0.78rem;color:#6c757d;margin-top:2px;}}
  .field-item .swatch{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;}}
  #map{{flex:1;position:relative;}}
  .leaflet-popup-content-wrapper{{border-radius:8px;font-size:0.9rem;}}
  .leaflet-popup-content{{margin:10px 14px;}}
  .popup-row{{margin:2px 0;}}
  .popup-label{{font-weight:600;color:#495057;}}
</style>
</head>
<body>
<div id="wrapper">
  <div id="sidebar">
    <h2>{grower_name}</h2>
    <h3>{farm_name} &nbsp;|&nbsp; {farm_state} &nbsp;|&nbsp; {len(features)} field(s)</h3>
    <div id="field-list"></div>
  </div>
  <div id="map"></div>
</div>
<script>
(function(){{
  const geojson = {geojson_json};
  const fieldMeta = {field_meta_json};
  const map = L.map('map').setView([{center_lat:.6f}, {center_lon:.6f}], 12);

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }}).addTo(map);

  // Render field list in sidebar
  const listEl = document.getElementById('field-list');
  fieldMeta.forEach(function(f){{
    const item = document.createElement('div');
    item.className = 'field-item';
    item.innerHTML = '<span class="swatch" style="background:'+f.color+'"></span><span class="fid">'+f.fieldId+'</span>' +
      '<div class="detail">'+f.area+' ac &middot; '+f.crop+' &middot; '+f.county+'</div>';
    item.addEventListener('click', function(){{
      const layer = layers[f.index - 1];
      if(layer){{ map.fitBounds(layer.getBounds(), {{padding:[20,20], maxZoom:16}}); layer.openPopup(); }}
    }});
    listEl.appendChild(item);
  }});

  // Render GeoJSON layers
  const layers = [];
  L.geoJSON(geojson, {{
    style: function(feature, idx){{
      const i = (feature.properties && feature.properties._leaflet_idx) || 0;
      const color = fieldMeta[i % fieldMeta.length].color;
      return {{ color: '#2c3e50', weight: 2, fillColor: color, fillOpacity: 0.45 }};
    }},
    onEachFeature: function(feature, layer){{
      const idx = layers.length;
      feature.properties._leaflet_idx = idx;
      const f = fieldMeta[idx];
      const popup = '<div class="popup-row"><span class="popup-label">Grower:</span> {grower_name}</div>' +
        '<div class="popup-row"><span class="popup-label">Farm:</span> {farm_name}</div>' +
        '<div class="popup-row"><span class="popup-label">Field:</span> ' + (feature.properties.field_id || f.fieldId) + '</div>' +
        '<div class="popup-row"><span class="popup-label">Area:</span> ' + f.area + ' ac</div>' +
        '<div class="popup-row"><span class="popup-label">Crop:</span> ' + f.crop + '</div>' +
        '<div class="popup-row"><span class="popup-label">County:</span> ' + f.county + '</div>';
      layer.bindPopup(popup);
      layers.push(layer);
    }}
  }}).addTo(map);

  // Fit to all fields
  if(layers.length){{
    const group = new L.featureGroup(layers);
    map.fitBounds(group.getBounds(), {{padding:[30,30]}});
  }}
}})();
</script>
</body>
</html>"""
    return html


def _extract_coords(geom: dict) -> list:
    """Flatten coordinates from any GeoJSON geometry type."""
    coords = geom.get("coordinates", [])
    if not coords:
        return []
    gtype = geom.get("type", "")
    if gtype == "Polygon":
        return coords[0] if coords else []
    elif gtype == "MultiPolygon":
        out = []
        for poly in coords:
            for ring in poly:
                out.extend(ring)
        return out
    elif gtype == "Point":
        return [coords]
    return []


def generate_grower_web_map(grower_slug: str, farm_slug: str, output_path: str) -> Path:
    """Generate the interactive HTML map."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Load metadata
    grower_json = _load_json(grower_dir(grower_slug) / "grower.json")
    farm_json = _load_json(farm_dir(grower_slug, farm_slug) / "farm.json")
    geojson_data = _load_geojson(farm_boundary_path(grower_slug, farm_slug))

    grower_name = grower_json.get("display_name", grower_slug)
    farm_name = farm_json.get("display_name", farm_slug)
    farm_state = farm_json.get("state", "")
    county_name = ""
    if geojson_data.get("features"):
        county_name = geojson_data["features"][0].get("properties", {}).get("county_name", "")

    html = _generate_html(
        geojson_data=geojson_data,
        grower_name=grower_name,
        farm_name=farm_name,
        farm_state=farm_state,
        county_name=county_name,
    )

    out.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"Map saved: {out.resolve()} ({size_kb:.1f} KB, {len(geojson_data.get('features', []))} fields)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a lightweight interactive Leaflet web map for a grower's farm."
    )
    parser.add_argument("grower_slug", help="Grower slug (e.g. northern-iowa-grower)")
    parser.add_argument("--farm-slug", required=True, help="Farm slug (e.g. cerro-gordo-farm)")
    parser.add_argument("--output", required=True, help="Output HTML file path")
    args = parser.parse_args()

    if "DATA_PIPELINE_DATA_ROOT" not in dict(sys._getframe().f_globals):
        pass  # paths.py already validates via resolve_runtime_paths

    generate_grower_web_map(args.grower_slug, args.farm_slug, args.output)


if __name__ == "__main__":
    main()
