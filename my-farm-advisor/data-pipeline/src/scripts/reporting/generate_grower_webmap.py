#!/usr/bin/env python3
"""Generate a lightweight interactive HTML grower web map from field boundaries.

Usage:
    python scripts/reporting/generate_grower_webmap.py \
        --grower-slug northern-illinois-grower \
        --farm-slug illinois-farm

Outputs a standalone HTML file under:
    growers/<grower>/farms/<farm>/derived/dashboards/<farm>_grower_webmap.html

The HTML embeds field polygon GeoJSON inline and loads Leaflet from a CDN,
so it requires no server or external data files at runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running both from runtime copy and during development
_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

try:
    from lib.paths import farm_boundary_path, farm_dashboards_dir, farm_dir
    from lib.runtime_paths import resolve_runtime_paths
except ImportError:
    from paths import farm_boundary_path, farm_dashboards_dir, farm_dir
    from runtime_paths import resolve_runtime_paths


_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base

_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sanitize(value: str) -> str:
    """Basic HTML escaping for embedded values."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_html(
    *,
    grower_slug: str,
    grower_name: str,
    farm_slug: str,
    farm_name: str,
    geojson_data: dict,
) -> str:
    """Construct the self-contained HTML map."""

    features = geojson_data.get("features", [])
    if not features:
        raise ValueError("GeoJSON contains no field features.")

    # Build per-field metadata list for sidebar and popups
    fields_meta: list[dict] = []
    for feat in features:
        props = feat.get("properties", {})
        fid = str(props.get("field_id", "unknown"))
        area = float(props.get("area_acres", 0.0))
        crop = str(props.get("crop_name", "—"))
        # Compute centroid for zoom-to-field
        geom = feat.get("geometry", {})
        coords: list = []
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif geom.get("type") == "MultiPolygon":
            coords = geom.get("coordinates", [[[]]])[0][0]
        if coords:
            lons = [c[0] for c in coords if len(c) >= 2]
            lats = [c[1] for c in coords if len(c) >= 2]
            centroid_lat = sum(lats) / len(lats) if lats else 0.0
            centroid_lon = sum(lons) / len(lons) if lons else 0.0
        else:
            centroid_lat = 0.0
            centroid_lon = 0.0

        fields_meta.append(
            {
                "field_id": fid,
                "area_acres": area,
                "crop_name": crop,
                "centroid_lat": centroid_lat,
                "centroid_lon": centroid_lon,
                "feature": feat,
            }
        )

    # Overall bounds for initial view
    all_lons: list[float] = []
    all_lats: list[float] = []
    for fm in fields_meta:
        geom = fm["feature"].get("geometry", {})
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif geom.get("type") == "MultiPolygon":
            coords = geom.get("coordinates", [[[]]])[0][0]
        else:
            coords = []
        for c in coords:
            if len(c) >= 2:
                all_lons.append(float(c[0]))
                all_lats.append(float(c[1]))

    if all_lons and all_lats:
        center_lat = (min(all_lats) + max(all_lats)) / 2
        center_lon = (min(all_lons) + max(all_lons)) / 2
    else:
        center_lat = 42.0
        center_lon = -93.0

    # Serialize GeoJSON for embedding
    geojson_json = json.dumps(geojson_data)

    # Build sidebar rows
    sidebar_rows = []
    for idx, fm in enumerate(fields_meta):
        fid = _sanitize(fm["field_id"])
        area = fm["area_acres"]
        crop = _sanitize(fm["crop_name"])
        sidebar_rows.append(
            f"""
            <div class="field-row" id="field-row-{idx}">
                <div class="field-info">
                    <div class="field-id">{fid}</div>
                    <div class="field-detail">{area:.1f} ac &middot; {crop}</div>
                </div>
                <button class="zoom-btn" onclick="zoomToField({idx})">Zoom</button>
            </div>
            """
        )
    sidebar_html = "\n".join(sidebar_rows)

    # Build popup content in JS
    popup_contents_js = []
    for idx, fm in enumerate(fields_meta):
        fid = _sanitize(fm["field_id"])
        area = fm["area_acres"]
        crop = _sanitize(fm["crop_name"])
        popup_contents_js.append(
            f'"'
            f'<b>Grower:</b> {_sanitize(grower_name)}<br>'
            f'<b>Farm:</b> {_sanitize(farm_name)}<br>'
            f'<b>Field:</b> {fid}<br>'
            f'<b>Area:</b> {area:.1f} acres<br>'
            f'<b>Crop:</b> {crop}'
            f'"'
        )
    popup_contents_array = ",\n            ".join(popup_contents_js)

    # Field metadata array for zooming
    field_meta_js = json.dumps(
        [
            {
                "lat": fm["centroid_lat"],
                "lon": fm["centroid_lon"],
                "field_id": fm["field_id"],
            }
            for fm in fields_meta
        ]
    )

    n_fields = len(fields_meta)
    total_acres = sum(fm["area_acres"] for fm in fields_meta)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_sanitize(farm_name)} — Grower Web Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
          crossorigin=""></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    #container {{ display: flex; height: 100vh; width: 100vw; }}

    #sidebar {{
      width: 300px;
      min-width: 260px;
      background: #f8f9fa;
      border-right: 1px solid #dee2e6;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    #sidebar-header {{
      padding: 1rem 1.25rem;
      background: linear-gradient(135deg, #1e3a5f, #2c5282);
      color: white;
      flex-shrink: 0;
    }}

    #sidebar-header h1 {{
      margin: 0 0 0.25rem 0;
      font-size: 1.15rem;
      font-weight: 600;
    }}

    #sidebar-header .meta {{
      margin: 0;
      font-size: 0.82rem;
      opacity: 0.85;
    }}

    #sidebar-header .stats {{
      margin: 0.5rem 0 0 0;
      font-size: 0.78rem;
      opacity: 0.75;
    }}

    #field-list {{
      flex: 1;
      overflow-y: auto;
      padding: 0.5rem;
    }}

    .field-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.6rem 0.75rem;
      margin-bottom: 0.4rem;
      background: white;
      border: 1px solid #e9ecef;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}

    .field-row:hover {{
      border-color: #2c5282;
      box-shadow: 0 2px 6px rgba(30,58,95,0.1);
    }}

    .field-row.active {{
      border-color: #2c5282;
      background: #e7f0ff;
    }}

    .field-info {{
      flex: 1;
      min-width: 0;
    }}

    .field-id {{
      font-weight: 600;
      font-size: 0.9rem;
      color: #1e3a5f;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .field-detail {{
      font-size: 0.78rem;
      color: #6c757d;
      margin-top: 0.15rem;
    }}

    .zoom-btn {{
      margin-left: 0.5rem;
      padding: 0.35rem 0.75rem;
      font-size: 0.78rem;
      font-weight: 500;
      color: #2c5282;
      background: white;
      border: 1px solid #2c5282;
      border-radius: 5px;
      cursor: pointer;
      white-space: nowrap;
    }}

    .zoom-btn:hover {{
      background: #2c5282;
      color: white;
    }}

    #map {{
      flex: 1;
      min-width: 0;
      height: 100%;
    }}

    .leaflet-popup-content-wrapper {{
      border-radius: 8px;
    }}

    .leaflet-popup-content {{
      margin: 0.75rem 1rem;
      font-size: 0.88rem;
      line-height: 1.6;
    }}

    @media (max-width: 768px) {{
      #sidebar {{ width: 100%; height: 40vh; border-right: none; border-bottom: 1px solid #dee2e6; }}
      #container {{ flex-direction: column; }}
      #map {{ height: 60vh; }}
    }}
  </style>
</head>
<body>
  <div id="container">
    <div id="sidebar">
      <div id="sidebar-header">
        <h1>{_sanitize(farm_name)}</h1>
        <p class="meta">Grower: {_sanitize(grower_name)}</p>
        <p class="stats">{n_fields} fields &middot; {total_acres:.1f} total acres</p>
      </div>
      <div id="field-list">
        {sidebar_html}
      </div>
    </div>
    <div id="map"></div>
  </div>

  <script>
    (function() {{
      var map = L.map('map');

      var satelliteLayer = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
        {{
          attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
          maxZoom: 19
        }}
      );

      var streetLayer = L.tileLayer(
        'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
        {{
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 19
        }}
      );

      var hybridLayer = L.layerGroup([
        L.tileLayer(
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
          {{ maxZoom: 19 }}
        ),
        L.tileLayer(
          'https://{{s}}.basemaps.cartocdn.com/light_only_labels/{{z}}/{{x}}/{{y}}{{r}}.png',
          {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
          }}
        )
      ]);

      L.control.layers({{
        'Satellite': satelliteLayer,
        'Street': streetLayer,
        'Hybrid': hybridLayer
      }}, null, {{ collapsed: true, position: 'topright' }}).addTo(map);

      satelliteLayer.addTo(map);

      var geojsonData = {geojson_json};

      var popupContents = [
        {popup_contents_array}
      ];

      var fieldMeta = {field_meta_js};
      var selectedIndex = -1;

      // Style constants
      var STYLE_DEFAULT = {{ color: '#fbbf24', weight: 3, fillColor: '#fbbf24', fillOpacity: 0.2 }};
      var STYLE_SELECTED = {{ color: '#06b6d4', weight: 4, fillColor: '#06b6d4', fillOpacity: 0.4 }};

      // Add index to each feature for popup correlation
      var features = geojsonData.features || [];
      features.forEach(function(f, i) {{
        if (!f.properties) f.properties = {{}};
        f.properties._fieldIndex = i;
      }});

      var layerGroup = L.geoJSON(geojsonData, {{
        style: function() {{ return STYLE_DEFAULT; }},
        onEachFeature: function(feature, layer) {{
          var idx = feature.properties ? feature.properties._fieldIndex : -1;
          if (idx >= 0 && popupContents[idx]) {{
            layer.bindPopup(popupContents[idx]);
          }}
          layer.on('click', function() {{
            selectField(idx);
          }});
        }}
      }}).addTo(map);

      // Fit bounds to all fields
      if (layerGroup.getLayers().length > 0) {{
        map.fitBounds(layerGroup.getBounds(), {{ padding: [40, 40] }});
      }} else {{
        map.setView([{center_lat}, {center_lon}], 10);
      }}

      function selectField(index) {{
        if (index === selectedIndex) return;
        selectedIndex = index;

        // Update polygon styles
        var layers = layerGroup.getLayers();
        layers.forEach(function(layer, i) {{
          if (i === index) {{
            layer.setStyle(STYLE_SELECTED);
            layer.bringToFront();
          }} else {{
            layer.setStyle(STYLE_DEFAULT);
          }}
        }});

        // Update sidebar
        var rows = document.querySelectorAll('.field-row');
        rows.forEach(function(row, i) {{
          if (i === index) {{
            row.classList.add('active');
            row.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
          }} else {{
            row.classList.remove('active');
          }}
        }});
      }}

      // Zoom to field helper
      window.zoomToField = function(index) {{
        var meta = fieldMeta[index];
        if (!meta) return;
        map.setView([meta.lat, meta.lon], 16);
        selectField(index);
        var layers = layerGroup.getLayers();
        if (layers[index]) {{
          layers[index].openPopup();
        }}
      }};

      // Click on row zooms to field
      document.querySelectorAll('.field-row').forEach(function(row, index) {{
        row.addEventListener('click', function(e) {{
          if (e.target.tagName.toLowerCase() === 'button') return;
          zoomToField(index);
        }});
      }});
    }})();
  </script>
</body>
</html>
"""
    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a lightweight interactive HTML grower web map."
    )
    parser.add_argument(
        "--grower-slug",
        default=_DEFAULT_GROWER,
        help="Grower slug (default: AG_GROWER_SLUG env var or 'default-grower')",
    )
    parser.add_argument(
        "--farm-slug",
        default=_DEFAULT_FARM,
        help="Farm slug (default: AG_FARM_SLUG env var or 'default-farm')",
    )
    parser.add_argument(
        "--output-filename",
        default=None,
        help="Override output filename (default: <farm>_grower_webmap.html)",
    )
    args = parser.parse_args()

    grower_slug = args.grower_slug
    farm_slug = args.farm_slug

    # Resolve paths
    boundary_path = farm_boundary_path(grower_slug, farm_slug)
    if not boundary_path.exists():
        print(f"[ERROR] Boundary file not found: {boundary_path}", file=sys.stderr)
        sys.exit(1)

    farm_json_path = farm_dir(grower_slug, farm_slug) / "farm.json"
    farm_json = _load_json(farm_json_path)
    farm_name = farm_json.get("display_name") or farm_slug.replace("-", " ").title()

    grower_json_path = _RUNTIME_BASE / "growers" / grower_slug / "grower.json"
    grower_json = _load_json(grower_json_path)
    grower_name = grower_json.get("display_name") or grower_slug.replace("-", " ").title()

    # Load GeoJSON
    geojson_data = _load_json(boundary_path)

    # Build HTML
    html = _build_html(
        grower_slug=grower_slug,
        grower_name=grower_name,
        farm_slug=farm_slug,
        farm_name=farm_name,
        geojson_data=geojson_data,
    )

    # Write output
    dashboards_dir = farm_dashboards_dir(grower_slug, farm_slug)
    dashboards_dir.mkdir(parents=True, exist_ok=True)

    output_filename = args.output_filename or f"{farm_slug}_grower_webmap.html"
    output_path = dashboards_dir / output_filename
    output_path.write_text(html, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"[OK] Grower web map saved → {output_path}")
    print(f"     Size: {size_kb:.1f} KB")
    print(f"     Fields: {len(geojson_data.get('features', []))}")
    print(f"     Grower: {grower_name}")
    print(f"     Farm: {farm_name}")


if __name__ == "__main__":
    main()
