#!/usr/bin/env python3
"""Generate a self-contained interactive HTML web map from a grower's field boundaries."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


def _find_farms(data_root: Path, grower_slug: str) -> list[dict[str, str]]:
    grower_dir = data_root / "growers" / grower_slug / "farms"
    if not grower_dir.is_dir():
        print(f"ERROR: no farms directory for grower '{grower_slug}' at {grower_dir}")
        sys.exit(1)
    farms: list[dict[str, str]] = []
    for farm_dir in sorted(grower_dir.iterdir()):
        if not farm_dir.is_dir():
            continue
        farms.append({"slug": farm_dir.name, "path": str(farm_dir)})
    return farms


def _load_boundaries(boundary_path: Path) -> list[dict]:
    if not boundary_path.exists():
        print(f"ERROR: field boundaries not found at {boundary_path}")
        sys.exit(1)
    with open(boundary_path) as f:
        geojson = json.load(f)
    return geojson.get("features", [])


def _load_field_inventory(inventory_path: Path) -> dict[str, str]:
    field_names: dict[str, str] = {}
    if not inventory_path.exists():
        return field_names
    with open(inventory_path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                field_names[row[0].strip()] = row[1].strip()
    return field_names


def _load_field_display_names(
    data_root: Path, grower_slug: str, farm_slug: str, field_slugs: dict[str, str]
) -> dict[str, str]:
    display: dict[str, str] = {}
    for field_id, field_slug in field_slugs.items():
        field_json_path = (
            data_root
            / "growers"
            / grower_slug
            / "farms"
            / farm_slug
            / "fields"
            / field_slug
            / "field.json"
        )
        if field_json_path.exists():
            try:
                meta = json.loads(field_json_path.read_text())
                display[field_id] = meta.get("display_name", field_slug)
            except Exception:
                display[field_id] = field_slug
        else:
            display[field_id] = field_slug
    return display


def _compute_centroid(features: list[dict]) -> tuple[float, float]:
    lats: list[float] = []
    lons: list[float] = []
    for feature in features:
        geom = feature.get("geometry", {})
        coords: list = []
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif geom.get("type") == "MultiPolygon":
            for ring in geom.get("coordinates", [[[]]])[0]:
                coords.extend(ring)
        for lon, lat in coords:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return (40.0, -90.0)
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _build_html(
    features: list[dict],
    display_names: dict[str, str],
    grower_slug: str,
    farm_name: str,
    total_acres: float,
) -> str:
    geojson_str = json.dumps({"type": "FeatureCollection", "features": features})
    display_json = json.dumps(display_names)
    center_lat, center_lon = _compute_centroid(features)
    field_count = len(features)

    popup_data: list[dict] = []
    for f in features:
        props = f.get("properties", {})
        fid = props.get("field_id", "")
        popup_data.append(
            {
                "id": fid,
                "name": display_names.get(fid, fid),
                "acres": round(props.get("area_acres", 0), 1),
                "county": props.get("county_name", ""),
            }
        )
    popup_json = json.dumps(popup_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{grower_slug} — {farm_name} Web Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  #container {{ display: flex; height: 100vh; }}
  #sidebar {{
    width: 340px; background: #fafafa; border-right: 1px solid #ddd;
    padding: 16px; overflow-y: auto; flex-shrink: 0;
  }}
  #sidebar h1 {{ font-size: 1.2em; color: #1B5E20; margin-bottom: 4px; }}
  #sidebar .subtitle {{ font-size: 0.85em; color: #666; margin-bottom: 12px; }}
  #sidebar .field-list {{ list-style: none; }}
  #sidebar .field-item {{
    padding: 8px 10px; margin: 4px 0; border-radius: 6px;
    background: #fff; border: 1px solid #e0e0e0;
    cursor: pointer; transition: background 0.15s;
    font-size: 0.88em;
  }}
  #sidebar .field-item:hover {{ background: #e8f5e9; }}
  #sidebar .field-item .name {{ font-weight: 600; color: #1B5E20; }}
  #sidebar .field-item .detail {{ font-size: 0.82em; color: #777; margin-top: 2px; }}
  #sidebar .layer-control {{ margin: 12px 0; padding: 10px; background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; }}
  #sidebar .layer-control label {{ font-size: 0.88em; cursor: pointer; }}
  #map {{ flex: 1; }}
  .leaflet-popup-content {{ font-size: 0.9em; line-height: 1.5; }}
  .leaflet-popup-content b {{ color: #1B5E20; }}
</style>
</head>
<body>
<div id="container">
  <div id="sidebar">
    <h1>{farm_name}</h1>
    <div class="subtitle">{field_count} fields — {total_acres:.0f} total acres</div>
    <div class="layer-control">
      <label><input type="checkbox" id="chk-satellite" onchange="toggleSatellite()"> Satellite basemap</label>
    </div>
    <h3 style="font-size:0.85em;color:#333;margin-bottom:6px;">Fields</h3>
    <ul class="field-list" id="field-list"></ul>
  </div>
  <div id="map"></div>
</div>
<script>
  var fieldData = {geojson_str};
  var displayMap = {display_json};
  var popupList = {popup_json};

  var osmLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }});

  var satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: '&copy; Esri, Maxar, Earthstar Geographics',
    maxZoom: 19
  }});

  var map = L.map('map', {{
    center: [{center_lat:.6f}, {center_lon:.6f}],
    zoom: 13,
    layers: [osmLayer]
  }});

  var fieldLayer = L.geoJSON(fieldData, {{
    style: {{
      color: '#2E7D32',
      weight: 2,
      fillColor: '#43A047',
      fillOpacity: 0.35
    }},
    onEachFeature: function(feature, layer) {{
      var p = feature.properties;
      var fid = p.field_id;
      var name = displayMap[fid] || fid;
      var acres = p.area_acres ? p.area_acres.toFixed(1) : '?';
      var county = p.county_name || '';
      layer.bindPopup(
        '<b>' + name + '</b><br>' +
        'Field ID: ' + fid + '<br>' +
        'Area: ' + acres + ' acres' +
        (county ? '<br>County: ' + county : '')
      );
      layer.on('mouseover', function() {{ this.setStyle({{ fillOpacity: 0.6, weight: 3 }}); }});
      layer.on('mouseout', function() {{ this.setStyle({{ fillOpacity: 0.35, weight: 2 }}); }});
    }}
  }}).addTo(map);

  map.fitBounds(fieldLayer.getBounds().pad(0.05));

  var listEl = document.getElementById('field-list');
  popupList.forEach(function(item) {{
    var li = document.createElement('li');
    li.className = 'field-item';
    li.innerHTML = '<div class="name">' + item.name + '</div>' +
      '<div class="detail">' + item.acres + ' acres' + (item.county ? ' &middot; ' + item.county : '') + '</div>';
    li.addEventListener('click', function() {{
      fieldLayer.eachLayer(function(layer) {{
        if (layer.feature && layer.feature.properties.field_id === item.id) {{
          map.fitBounds(layer.getBounds().pad(0.1));
          layer.openPopup();
        }}
      }});
    }});
    listEl.appendChild(li);
  }});

  function toggleSatellite() {{
    var chk = document.getElementById('chk-satellite');
    if (chk.checked) {{
      map.removeLayer(osmLayer);
      map.addLayer(satelliteLayer);
    }} else {{
      map.removeLayer(satelliteLayer);
      map.addLayer(osmLayer);
    }}
  }}
</script>
</body>
</html>"""
    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an interactive HTML web map from a grower's field boundaries."
    )
    parser.add_argument("--grower-slug", required=True, help="Grower slug (e.g., il-grower)")
    parser.add_argument(
        "--farm-slug", default=None, help="Farm slug (auto-detected if omitted)"
    )
    args = parser.parse_args()

    data_root_env = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root_env:
        print("ERROR: DATA_PIPELINE_DATA_ROOT environment variable is not set")
        sys.exit(1)
    data_root = Path(data_root_env).resolve()
    pipeline_root = data_root / "data-pipeline"

    farms = _find_farms(pipeline_root, args.grower_slug)
    if not farms:
        print(f"ERROR: no farms found for grower '{args.grower_slug}'")
        sys.exit(1)

    target_farms = (
        [f for f in farms if f["slug"] == args.farm_slug]
        if args.farm_slug
        else farms
    )
    if not target_farms:
        print(
            f"ERROR: farm slug '{args.farm_slug}' not found for grower '{args.grower_slug}'. "
            f"Available: {[f['slug'] for f in farms]}"
        )
        sys.exit(1)

    for farm in target_farms:
        farm_slug = farm["slug"]
        farm_path = Path(farm["path"])
        inventory_path = farm_path / "manifests" / "field-inventory.csv"
        boundaries_path = farm_path / "boundary" / "field_boundaries.geojson"
        farm_json_path = farm_path / "farm.json"

        farm_name = farm_slug
        if farm_json_path.exists():
            try:
                farm_meta = json.loads(farm_json_path.read_text())
                farm_name = farm_meta.get("display_name", farm_slug)
            except Exception:
                pass

        features = _load_boundaries(boundaries_path)
        if not features:
            print(f"  skip  {farm_slug}: no field boundaries found")
            continue

        field_slug_map = _load_field_inventory(inventory_path)
        display_names = _load_field_display_names(
            pipeline_root, args.grower_slug, farm_slug, field_slug_map
        )

        total_acres = sum(
            f.get("properties", {}).get("area_acres", 0) for f in features
        )

        html = _build_html(
            features, display_names, args.grower_slug, farm_name, total_acres
        )

        out_dir = farm_path / "derived" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.grower_slug}_{farm_slug}_web_map.html"
        out_path.write_text(html, encoding="utf-8")

        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"  {farm_slug}: {len(features)} fields, {total_acres:.0f} acres")
        print(f"    -> {out_path.relative_to(pipeline_root)} ({size_mb:.1f} MB)")

    print("Done.")


if __name__ == "__main__":
    main()
