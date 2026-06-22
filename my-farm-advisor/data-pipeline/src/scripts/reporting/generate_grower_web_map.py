#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate lightweight interactive HTML web maps for each grower.

Aggregates field polygon boundaries across all farms for a grower and writes a
single self-contained HTML file per grower. The output can be opened directly
in any modern browser.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from lib.paths import GROWERS_ROOT  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grower-slug",
        default=os.environ.get("AG_GROWER_SLUG", ""),
        help="Grower slug to process. If omitted, all growers are processed.",
    )
    parser.add_argument(
        "--farm-slug",
        default=os.environ.get("AG_FARM_SLUG", ""),
        help="Farm slug to process. If omitted, all farms for the grower are processed.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Override output directory. Defaults to <grower>/derived/reports/.",
    )
    parser.add_argument(
        "--simplify-tolerance",
        type=float,
        default=0.0001,
        help="GeoJSON simplification tolerance in degrees (default: 0.0001).",
    )
    return parser.parse_args()


def _discover_growers() -> list[str]:
    if not GROWERS_ROOT.exists():
        return []
    return sorted([p.name for p in GROWERS_ROOT.iterdir() if p.is_dir() and (p / "grower.json").exists()])


def _discover_farms(grower_slug: str) -> list[str]:
    farms_root = GROWERS_ROOT / grower_slug / "farms"
    if not farms_root.exists():
        return []
    return sorted([p.name for p in farms_root.iterdir() if p.is_dir() and (p / "farm.json").exists()])


def _load_farm_geojson(grower_slug: str, farm_slug: str) -> gpd.GeoDataFrame | None:
    path = GROWERS_ROOT / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    if gdf.empty:
        return None
    return gdf


def _load_farm_metadata(grower_slug: str, farm_slug: str) -> dict[str, Any]:
    path = GROWERS_ROOT / grower_slug / "farms" / farm_slug / "farm.json"
    if not path.exists():
        return {"display_name": farm_slug, "state": "", "country": "US"}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_grower_metadata(grower_slug: str) -> dict[str, Any]:
    path = GROWERS_ROOT / grower_slug / "grower.json"
    if not path.exists():
        return {"display_name": grower_slug}
    return json.loads(path.read_text(encoding="utf-8"))


def _state_name_from_fips(state_fips: str) -> str:
    mapping = {
        "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
        "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
        "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
        "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
        "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
        "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
        "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
        "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
        "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
        "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
        "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
        "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
        "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
    }
    return mapping.get(state_fips.zfill(2), "")


def _build_geojson_for_grower(
    grower_slug: str, farm_slug_filter: str = "", simplify_tolerance: float = 0.0001
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    farm_slugs = _discover_farms(grower_slug)
    if farm_slug_filter:
        farm_slugs = [s for s in farm_slugs if s == farm_slug_filter]

    all_features: list[dict[str, Any]] = []
    farm_acres: dict[str, float] = {}
    farm_names: dict[str, str] = {}

    for farm_slug in farm_slugs:
        gdf = _load_farm_geojson(grower_slug, farm_slug)
        if gdf is None:
            continue
        farm_meta = _load_farm_metadata(grower_slug, farm_slug)
        farm_name = farm_meta.get("display_name", farm_slug)
        farm_names[farm_slug] = farm_name

        # Simplify to keep HTML small
        if simplify_tolerance > 0 and gdf.crs and gdf.crs.to_epsg() == 4326:
            gdf["geometry"] = gdf.geometry.simplify(simplify_tolerance, preserve_topology=True)

        farm_total = 0.0
        for _, row in gdf.iterrows():
            props = dict(row.drop(labels="geometry", errors="ignore"))
            area = float(props.get("area_acres", 0) or 0)
            farm_total += area
            # Add farm-level metadata
            props["_farm_name"] = farm_name
            props["_farm_slug"] = farm_slug
            feature = {
                "type": "Feature",
                "properties": props,
                "geometry": json.loads(json.dumps(mapping(row.geometry))),
            }
            all_features.append(feature)
        farm_acres[farm_slug] = farm_total

    if not all_features:
        return None, []

    geojson = {"type": "FeatureCollection", "features": all_features}

    # Build legend data (stable color order)
    farm_colors = ["#2E7D32", "#1565C0", "#E65100", "#6A1B9A", "#C62828", "#00695C"]
    legend: list[dict[str, Any]] = []
    for idx, farm_slug in enumerate(farm_slugs):
        if farm_slug in farm_names:
            legend.append({
                "farm_slug": farm_slug,
                "farm_name": farm_names[farm_slug],
                "acres": farm_acres.get(farm_slug, 0.0),
                "color": farm_colors[idx % len(farm_colors)],
            })

    return geojson, legend


def _render_html(
    grower_slug: str,
    geojson_data: dict[str, Any],
    farm_legend: list[dict[str, Any]],
    output_path: Path,
) -> None:
    grower_meta = _load_grower_metadata(grower_slug)
    grower_name = grower_meta.get("display_name", grower_slug)

    # Compute center from all features
    lats: list[float] = []
    lons: list[float] = []
    for f in geojson_data["features"]:
        geom = f["geometry"]
        coords = geom.get("coordinates", [])
        if geom["type"] == "Polygon":
            for ring in coords:
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
        elif geom["type"] == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    for lon, lat in ring:
                        lons.append(lon)
                        lats.append(lat)

    center_lat = sum(lats) / len(lats) if lats else 40.0
    center_lon = sum(lons) / len(lons) if lons else -95.0

    # Build field list for sidebar
    field_items: list[dict[str, Any]] = []
    for idx, f in enumerate(geojson_data["features"]):
        props = f["properties"]
        fid = str(props.get("field_id", f"field-{idx}"))
        # Compute centroid for zoom target
        geom = f["geometry"]
        coords = geom.get("coordinates", [])
        c_lats: list[float] = []
        c_lons: list[float] = []
        if geom["type"] == "Polygon":
            for ring in coords:
                for lon, lat in ring:
                    c_lons.append(lon)
                    c_lats.append(lat)
        elif geom["type"] == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    for lon, lat in ring:
                        c_lons.append(lon)
                        c_lats.append(lat)
        f_lat = sum(c_lats) / len(c_lats) if c_lats else center_lat
        f_lon = sum(c_lons) / len(c_lons) if c_lons else center_lon
        field_items.append({
            "index": idx,
            "id": fid,
            "name": fid,
            "farm": str(props.get("_farm_name", "")),
            "crop": str(props.get("crop_name", "")),
            "area": float(props.get("area_acres", 0) or 0),
            "lat": f_lat,
            "lon": f_lon,
        })

    geojson_str = json.dumps(geojson_data)
    field_list_json = json.dumps(field_items)

    # Use a subtle color per farm to differentiate
    farm_colors = ["#2E7D32", "#1565C0", "#E65100", "#6A1B9A", "#C62828", "#00695C"]
    legend_json = json.dumps(farm_legend)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{grower_name} — Grower Web Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; height: 100vh; overflow: hidden; }}
    #container {{ display: flex; height: 100vh; }}
    #sidebar {{ width: 300px; background: #f8f9fa; border-right: 1px solid #dee2e6; display: flex; flex-direction: column; flex-shrink: 0; }}
    #sidebar header {{ padding: 1rem; background: #1e3a5f; color: white; }}
    #sidebar header h1 {{ margin: 0; font-size: 1.1rem; }}
    #sidebar header p {{ margin: 0.25rem 0 0; font-size: 0.8rem; opacity: 0.9; }}
    #field-list {{ flex: 1; overflow-y: auto; padding: 0.5rem; }}
    .field-item {{ padding: 0.6rem; margin-bottom: 0.4rem; background: white; border-radius: 6px; border: 1px solid #e9ecef; cursor: pointer; transition: all 0.15s; }}
    .field-item:hover {{ border-color: #1e3a5f; box-shadow: 0 2px 6px rgba(30,58,95,0.15); }}
    .field-item .fid {{ font-weight: 600; font-size: 0.85rem; color: #1e3a5f; }}
    .field-item .meta {{ font-size: 0.78rem; color: #6c757d; margin-top: 0.2rem; }}
    #map {{ flex: 1; min-width: 0; }}
    .leaflet-popup-content-wrapper {{ border-radius: 8px; }}
    .leaflet-popup-content {{ margin: 0.8rem 1rem; font-size: 0.9rem; line-height: 1.5; }}
    .popup-row {{ margin-bottom: 0.3rem; }}
    .popup-label {{ font-weight: 600; color: #495057; }}
    /* Legend styles */
    .legend-panel {{ background: rgba(255,255,255,0.88); padding: 12px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.25); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; min-width: 160px; }}
    .legend-panel h4 {{ margin: 0 0 8px 0; font-size: 0.9rem; font-weight: 700; border-bottom: 1px solid rgba(0,0,0,0.1); padding-bottom: 6px; }}
    .legend-item {{ display: flex; align-items: center; margin-bottom: 6px; font-size: 0.82rem; }}
    .legend-color {{ width: 16px; height: 16px; border-radius: 3px; margin-right: 8px; flex-shrink: 0; border: 1px solid rgba(0,0,0,0.15); }}
    .legend-text {{ line-height: 1.3; }}
    .legend-farm {{ font-weight: 600; }}
    .legend-acres {{ color: #475569; font-size: 0.78rem; }}
    @media (max-width: 768px) {{
      #sidebar {{ width: 240px; }}
      .legend-panel {{ padding: 8px; min-width: 130px; }}
    }}
  </style>
</head>
<body>
  <div id="container">
    <div id="sidebar">
      <header>
        <h1>{grower_name}</h1>
        <p>{len(field_items)} fields &middot; Interactive web map</p>
      </header>
      <div id="field-list"></div>
    </div>
    <div id="map"></div>
  </div>

  <script>
    var map = L.map('map').setView([{center_lat}, {center_lon}], 12);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
    }}).addTo(map);

    var geojsonData = {geojson_str};
    var fieldItems = {field_list_json};
    var farmLegend = {legend_json};
    var farmColors = {json.dumps(farm_colors)};

    // Assign a stable color per farm
    var farmColorMap = {{}};
    var farmIndex = 0;
    geojsonData.features.forEach(function(f) {{
      var farm = f.properties._farm_slug || 'unknown';
      if (!farmColorMap[farm]) {{
        farmColorMap[farm] = farmColors[farmIndex % farmColors.length];
        farmIndex++;
      }}
    }});

    var layers = [];
    var geojsonLayer = L.geoJSON(geojsonData, {{
      renderer: L.canvas(),
      style: function(feature) {{
        var farm = feature.properties._farm_slug || 'unknown';
        return {{
          color: farmColorMap[farm],
          weight: 2.5,
          fillOpacity: 0.22,
          fillColor: farmColorMap[farm]
        }};
      }},
      onEachFeature: function(feature, layer) {{
        var p = feature.properties;
        var stateName = p.state_fips ? p.state_fips : '';
        var countyName = p.county_name ? p.county_name : '';
        var locationLine = '';
        if (countyName && stateName) {{
          locationLine = '<div class="popup-row"><span class="popup-label">Location:</span> ' + countyName + ', ' + stateName + '</div>';
        }} else if (countyName) {{
          locationLine = '<div class="popup-row"><span class="popup-label">County:</span> ' + countyName + '</div>';
        }}
        var popupHtml = '<div class="popup-row"><span class="popup-label">Grower:</span> {grower_name}</div>' +
          '<div class="popup-row"><span class="popup-label">Farm:</span> ' + (p._farm_name || '') + '</div>' +
          '<div class="popup-row"><span class="popup-label">Field:</span> ' + (p.field_id || '') + '</div>' +
          '<div class="popup-row"><span class="popup-label">Crop:</span> ' + (p.crop_name || '') + '</div>' +
          '<div class="popup-row"><span class="popup-label">Area:</span> ' + (p.area_acres ? parseFloat(p.area_acres).toFixed(2) + ' acres' : '') + '</div>' +
          locationLine;
        layer.bindPopup(popupHtml);
        layers.push(layer);
      }}
    }}).addTo(map);

    // Fit bounds to all features
    if (geojsonLayer.getBounds().isValid()) {{
      map.fitBounds(geojsonLayer.getBounds().pad(0.1));
    }}

    // Build sidebar list
    var listContainer = document.getElementById('field-list');
    fieldItems.forEach(function(item, idx) {{
      var div = document.createElement('div');
      div.className = 'field-item';
      div.innerHTML = '<div class="fid">' + item.name + '</div>' +
        '<div class="meta">' + item.farm + ' &middot; ' + item.crop + ' &middot; ' + item.area.toFixed(2) + ' ac</div>';
      div.addEventListener('click', function() {{
        map.setView([item.lat, item.lon], 15);
        layers[idx].openPopup();
      }});
      listContainer.appendChild(div);
    }});

    // Add legend control
    var legendControl = L.control({{position: 'bottomright'}});
    legendControl.onAdd = function(map) {{
      var div = L.DomUtil.create('div', 'legend-panel');
      var html = '<h4>Farms</h4>';
      farmLegend.forEach(function(item) {{
        html += '<div class="legend-item">' +
          '<div class="legend-color" style="background:' + item.color + ';"></div>' +
          '<div class="legend-text">' +
          '<div class="legend-farm">' + item.farm_name + '</div>' +
          '<div class="legend-acres">' + item.acres.toFixed(2) + ' acres</div>' +
          '</div></div>';
      }});
      div.innerHTML = html;
      return div;
    }};
    legendControl.addTo(map);
  </script>
</body>
</html>
'''

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    args = parse_args()

    if args.grower_slug:
        growers = [args.grower_slug]
    else:
        growers = _discover_growers()

    if not growers:
        print("No growers found under", GROWERS_ROOT)
        return 1

    generated: list[Path] = []
    for grower_slug in growers:
        geojson, farm_legend = _build_geojson_for_grower(
            grower_slug, args.farm_slug, args.simplify_tolerance
        )
        if geojson is None:
            print(f"  No field boundaries found for grower {grower_slug}; skipping.")
            continue

        if args.output_dir:
            out_dir = Path(args.output_dir)
        else:
            out_dir = GROWERS_ROOT / grower_slug / "derived" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{grower_slug}_web_map.html"

        _render_html(grower_slug, geojson, farm_legend, output_path)
        size_kb = output_path.stat().st_size / 1024
        print(f"  Generated: {output_path} ({size_kb:.1f} KB)")
        generated.append(output_path)

    if generated:
        print(f"\nDone. {len(generated)} grower map(s) generated.")
    else:
        print("\nNo maps were generated.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
