#!/usr/bin/env python3
"""Generate a lightweight interactive Leaflet HTML map for each grower.

Scans the runtime data tree for farm field-boundary GeoJSON files and
writes a self-contained HTML page per grower with field polygons on an
OpenStreetMap basemap, click popups with metadata, and a sidebar field list.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from lib.runtime_paths import resolve_runtime_paths
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    from runtime_paths import resolve_runtime_paths


_RUNTIME_PATHS = resolve_runtime_paths()
_DATA_ROOT = _RUNTIME_PATHS.runtime_base


def _grower_dir(slug: str) -> Path:
    return _DATA_ROOT / "growers" / slug


def _discover_growers(grower_slug: str | None) -> list[str]:
    growers_dir = _DATA_ROOT / "growers"
    if not growers_dir.exists():
        print("ERROR: growers directory not found", file=sys.stderr)
        sys.exit(1)
    if grower_slug:
        path = _grower_dir(grower_slug)
        if not path.exists():
            print(f"ERROR: grower '{grower_slug}' not found", file=sys.stderr)
            sys.exit(1)
        return [grower_slug]
    return sorted(p.name for p in growers_dir.iterdir() if p.is_dir())


def _discover_farms(grower: str) -> list[dict]:
    farms_dir = _grower_dir(grower) / "farms"
    if not farms_dir.exists():
        return []
    farms: list[dict] = []
    for farm_dir in sorted(farms_dir.iterdir()):
        if not farm_dir.is_dir():
            continue
        boundary = farm_dir / "boundary" / "field_boundaries.geojson"
        if not boundary.exists():
            continue
        farm_name = _read_farm_name(farm_dir.name, grower)
        farms.append({
            "slug": farm_dir.name,
            "name": farm_name,
            "boundary_path": boundary,
        })
    return farms


def _read_farm_name(farm_slug: str, grower_slug: str) -> str:
    farm_json = _grower_dir(grower_slug) / "farms" / farm_slug / "farm.json"
    if farm_json.exists():
        try:
            meta = json.loads(farm_json.read_text(encoding="utf-8"))
            return meta.get("display_name", farm_slug)
        except Exception:
            pass
    return farm_slug.replace("-", " ").title()


def _load_fields(boundary_path: Path) -> list[dict]:
    if not boundary_path.exists():
        return []
    data = json.loads(boundary_path.read_text(encoding="utf-8"))
    return data.get("features", [])


def _build_html(grower_slug: str, farms: list[dict]) -> str:
    all_feature_collections: list[dict] = []
    farm_labels: list[dict] = []

    for farm in farms:
        features = _load_fields(farm["boundary_path"])
        if not features:
            continue
        for feat in features:
            props = feat.get("properties", {})
            props["_farm_slug"] = farm["slug"]
            props["_farm_name"] = farm["name"]
            props["_grower"] = grower_slug
        all_feature_collections.append({
            "farm": farm,
            "features": features,
        })
        farm_labels.append({
            "slug": farm["slug"],
            "name": farm["name"],
            "count": len(features),
        })

    if not all_feature_collections:
        return "<html><body><h1>No fields found</h1></body></html>"

    geojson_payload = {
        "type": "FeatureCollection",
        "features": [f for fc in all_feature_collections for f in fc["features"]],
    }
    encoded_geojson = json.dumps(geojson_payload)
    farm_list_json = json.dumps(farm_labels)
    fields_with_farm = [
        {
            "field_id": f.get("properties", {}).get("field_id", ""),
            "farm_name": f.get("properties", {}).get("_farm_name", ""),
            "area_acres": f.get("properties", {}).get("area_acres", 0),
            "county": f.get("properties", {}).get("county_name", ""),
        }
        for f in geojson_payload["features"]
    ]
    fields_json = json.dumps(fields_with_farm)

    return _HTML_TEMPLATE.format(
        title=f"{grower_slug} — Farm Web Map",
        geojson_data=encoded_geojson,
        farm_list=farm_list_json,
        field_list=fields_json,
    )


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ height: 100%; font-family: system-ui, sans-serif; }}
  #wrapper {{ display: flex; height: 100%; }}
  #sidebar {{
    width: 320px; min-width: 320px; overflow-y: auto;
    background: #f8f9fa; border-right: 1px solid #ddd;
    display: flex; flex-direction: column;
  }}
  #sidebar h2 {{ font-size: 1rem; padding: 16px 12px 8px; color: #333; }}
  #sidebar .grower-header {{
    padding: 12px; background: #2c3e50; color: #fff;
    font-size: 1.1rem; font-weight: 600;
  }}
  #sidebar .farm-group {{ margin-bottom: 8px; }}
  #sidebar .farm-header {{
    padding: 6px 12px; font-size: 0.85rem; font-weight: 600;
    color: #555; text-transform: uppercase; letter-spacing: 0.5px;
  }}
  #sidebar .field-item {{
    padding: 6px 12px 6px 24px; cursor: pointer; font-size: 0.9rem;
    border-bottom: 1px solid #eee; transition: background 0.15s;
    display: flex; justify-content: space-between;
  }}
  #sidebar .field-item:hover {{ background: #e2e6ea; }}
  #sidebar .field-item .acres {{ color: #888; font-size: 0.8rem; }}
  #map {{ flex: 1; }}
  .leaflet-popup-content {{ font-size: 0.85rem; line-height: 1.5; }}
  .leaflet-popup-content strong {{ color: #2c3e50; }}
</style>
</head>
<body>
<div id="wrapper">
  <div id="sidebar">
    <div class="grower-header">{title}</div>
    <div id="farm-list"></div>
  </div>
  <div id="map"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
  const geojsonData = {geojson_data};
  const farmList = {farm_list};
  const fieldList = {field_list};

  const map = L.map('map', {{ zoomControl: true }}).setView([40, -95], 5);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }}).addTo(map);

  const colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6','#1abc9c','#e67e22'];
  const fieldMap = {{}};
  const fieldByIndex = [];

  const geoLayer = L.geoJSON(geojsonData, {{
    style: function(feature) {{
      const idx = geojsonData.features.indexOf(feature);
      return {{
        color: colors[idx % colors.length],
        weight: 2,
        fillOpacity: 0.2,
      }};
    }},
    onEachFeature: function(feature, layer) {{
      const p = feature.properties || {{}};
      const fieldId = p.field_id || 'unknown';
      const acres = p.area_acres ? p.area_acres.toFixed(1) : '?';
      const county = p.county_name || '?';
      const farmName = p._farm_name || p._farm_slug || '?';
      const grower = p._grower || '?';

      const popup = `
        <div>
          <strong>Grower:</strong> ${{grower}}<br>
          <strong>Farm:</strong> ${{farmName}}<br>
          <strong>Field:</strong> ${{fieldId}}<br>
          <strong>County:</strong> ${{county}}<br>
          <strong>Acres:</strong> ${{acres}}
        </div>`;
      layer.bindPopup(popup);

      fieldMap[fieldId] = layer;
      fieldByIndex.push({{ id: fieldId, layer: layer }});
    }}
  }}).addTo(map);

  if (fieldByIndex.length > 0) {{
    const group = L.featureGroup(fieldByIndex.map(f => f.layer));
    map.fitBounds(group.getBounds().pad(0.05));
  }}

  const sidebar = document.getElementById('farm-list');
  farmList.forEach(farm => {{
    const fields = fieldList.filter(f => f.farm_name === farm.name);
    const group = document.createElement('div');
    group.className = 'farm-group';
    const header = document.createElement('div');
    header.className = 'farm-header';
    header.textContent = farm.name + ' (' + farm.count + ' fields)';
    group.appendChild(header);

    fields.forEach(f => {{
      const item = document.createElement('div');
      item.className = 'field-item';
      const label = document.createElement('span');
      const lid = f.field_id.replace('osm-', '');
      label.textContent = '#' + lid;
      const acres = document.createElement('span');
      acres.className = 'acres';
      acres.textContent = (f.area_acres ? f.area_acres.toFixed(1) : '?') + ' ac';
      item.appendChild(label);
      item.appendChild(acres);
      item.addEventListener('click', function() {{
        const layer = fieldMap[f.field_id];
        if (layer) {{
          map.fitBounds(layer.getBounds().pad(0.3));
          layer.openPopup();
        }}
      }});
      group.appendChild(item);
    }});

    sidebar.appendChild(group);
  }});
}})();
</script>
</body>
</html>"""


def _write_map(grower_slug: str, html: str) -> Path:
    out = _grower_dir(grower_slug) / "farm-web-map.html"
    out.write_text(html, encoding="utf-8")
    print(f"  wrote {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate interactive Leaflet web map for growers"
    )
    parser.add_argument("--grower-slug", default=None, help="Target a single grower")
    args = parser.parse_args()

    growers = _discover_growers(args.grower_slug)
    for grower in growers:
        print(f"[{grower}]")
        farms = _discover_farms(grower)
        if not farms:
            print(f"  no farms with boundaries found, skipping")
            continue
        for f in farms:
            print(f"  farm: {f['slug']} ({f['name']})")
        html = _build_html(grower, farms)
        _write_map(grower, html)

    print("Done.")


if __name__ == "__main__":
    main()
