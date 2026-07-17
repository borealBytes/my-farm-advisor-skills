#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate a lightweight interactive HTML web map for a grower with NDVI,
soil, and crop-type layers.

Scans all farms under growers/<grower>/farms/, reads field boundary GeoJSON
files, enriches with NDVI mean values (from yearly composite TIFs), SSURGO
soil summaries, and optional crop-type composition. Produces a single HTML
file with embedded GeoJSON, Leaflet.js, and a layer switcher.

Layers:
  - Field Boundaries (base view)
  - NDVI (mean NDVI from latest composite)
  - Soil: Organic Matter %
  - Soil: pH
  - Crop Type (placeholder when CDL unavailable)

Usage:
    python generate_grower_web_map.py --grower-slug il-grower
    python generate_grower_web_map.py --grower-slug ia-grower
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

_SCRIPTS = Path(__file__).resolve().parents[1]
_LIB = _SCRIPTS / "lib"
sys.path.insert(0, str(_LIB))
sys.path.insert(0, str(_SCRIPTS))

from bootstrap_runtime import ensure_runtime_environment  # noqa: E402
ensure_runtime_environment()

from runtime_paths import resolve_runtime_paths  # noqa: E402
from paths import (
    DATA_ROOT,
    farm_boundary_path,
    farm_metadata_path,
    grower_dir,
    grower_maps_dir,
    grower_metadata_path,
    farm_tables_dir,
    field_dir,
)  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()


def _load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _find_soil_summary(grower_slug: str, farm_slug: str) -> Path | None:
    tables_dir = farm_tables_dir(grower_slug, farm_slug)
    if not tables_dir.exists():
        return None
    for candidate in tables_dir.iterdir():
        if candidate.name.endswith("ssurgo_summary.csv"):
            return candidate
    return None


def _load_soil_data(grower_slug: str, farm_slug: str) -> dict[str, dict[str, Any]]:
    path = _find_soil_summary(grower_slug, farm_slug)
    if path is None:
        return {}
    result: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = str(row.get("field_id", "")).strip()
            if fid:
                result[fid] = {
                    "dominant_soil": row.get("dominant_soil", ""),
                    "drainage_class": row.get("drainage_class", ""),
                    "avg_om_pct": _safe_float(row.get("avg_om_pct")),
                    "avg_ph": _safe_float(row.get("avg_ph")),
                    "total_aws_inches": _safe_float(row.get("total_aws_inches")),
                    "avg_cec": _safe_float(row.get("avg_cec")),
                    "avg_clay_pct": _safe_float(row.get("avg_clay_pct")),
                    "avg_sand_pct": _safe_float(row.get("avg_sand_pct")),
                    "erosion_risk": row.get("erosion_risk", ""),
                }
    return result


def _safe_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


def _compute_mean_ndvi(tif_path: Path) -> float | None:
    if not tif_path.exists():
        return None
    try:
        with rasterio.open(tif_path) as src:
            data = src.read(1)
            valid = data[~np.isnan(data) & np.isfinite(data)]
            if len(valid) == 0:
                return None
            return float(np.mean(valid))
    except Exception:
        return None


def _load_ndvi_data(
    grower_slug: str, farm_slug: str, field_slug: str
) -> dict[str, Any]:
    summary_path = (
        field_dir(grower_slug, farm_slug, field_slug)
        / "derived"
        / "summaries"
        / "ndvi_yearly_summary.json"
    )
    summary = _load_json(summary_path)
    years = summary.get("years", [])
    latest_year = max((y for y in years if y.get("composite_tif")), key=lambda y: y["year"], default=None) if years else None
    mean_ndvi = None
    scene_count = 0
    if latest_year:
        tif_rel = latest_year.get("composite_tif", "")
        if tif_rel:
            tif_path = DATA_ROOT / tif_rel
            mean_ndvi = _compute_mean_ndvi(tif_path)
        scene_count = int(latest_year.get("scene_count", 0))
    return {
        "ndvi_mean": mean_ndvi,
        "ndvi_scene_count": scene_count,
        "ndvi_year": latest_year["year"] if latest_year else None,
    }


def _load_soil_polygons(
    grower_slug: str, farm_slug: str
) -> gpd.GeoDataFrame:
    """Collect all per-field soil type polygons into one GeoDataFrame."""
    all_parts: list[gpd.GeoDataFrame] = []
    farm_dir = grower_dir(grower_slug) / "farms" / farm_slug
    fields_root = farm_dir / "fields"
    if not fields_root.exists():
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    for field_path in sorted(fields_root.iterdir()):
        if not field_path.is_dir():
            continue
        soil_geo = field_path / "soil" / "ssurgo_soil_types.geojson"
        if not soil_geo.exists():
            continue
        try:
            gdf = gpd.read_file(soil_geo)
            if not gdf.empty:
                if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(epsg=4326)
                all_parts.append(gdf)
        except Exception:
            continue
    if not all_parts:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    combined = gpd.GeoDataFrame(pd.concat(all_parts, ignore_index=True, sort=False))
    if combined.crs is None:
        combined.set_crs(epsg=4326, inplace=True)
    return combined


def _collect_grower_fields(grower_slug: str) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Collect all field boundaries with NDVI and soil enrichment."""
    gdf_parts: list[gpd.GeoDataFrame] = []
    sidebar_records: list[dict[str, Any]] = []

    grower_meta = _load_json(grower_metadata_path(grower_slug))
    grower_display = grower_meta.get("display_name", grower_slug.replace("-", " ").title())

    farms_dir = grower_dir(grower_slug) / "farms"
    if not farms_dir.exists():
        raise FileNotFoundError(f"No farms directory found for grower: {grower_slug}")

    for farm_path in sorted(farms_dir.iterdir()):
        if not farm_path.is_dir():
            continue
        farm_slug = farm_path.name
        boundary_file = farm_boundary_path(grower_slug, farm_slug)
        if not boundary_file.exists():
            continue

        farm_meta = _load_json(farm_metadata_path(grower_slug, farm_slug))
        farm_display = farm_meta.get("display_name", farm_slug.replace("-", " ").title())

        soil_by_field = _load_soil_data(grower_slug, farm_slug)

        gdf = gpd.read_file(boundary_file)
        if gdf.empty:
            continue

        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        for idx, row in gdf.iterrows():
            field_id = row.get("field_id", "")
            field_slug = str(field_id).replace("OSM_", "osm-") if field_id else ""
            field_meta = _load_json(
                grower_dir(grower_slug) / "farms" / farm_slug / "fields" / field_slug / "field.json"
            )
            field_name = field_meta.get("display_name", field_slug) or field_slug

            ndvi = _load_ndvi_data(grower_slug, farm_slug, field_slug)
            soil = soil_by_field.get(field_id, {})

            gdf.at[idx, "grower_name"] = grower_display
            gdf.at[idx, "farm_name"] = farm_display
            gdf.at[idx, "field_name"] = field_name
            gdf.at[idx, "field_slug"] = field_slug
            gdf.at[idx, "farm_slug"] = farm_slug
            gdf.at[idx, "ndvi_mean"] = ndvi.get("ndvi_mean")
            gdf.at[idx, "ndvi_scene_count"] = ndvi.get("ndvi_scene_count")
            gdf.at[idx, "ndvi_year"] = ndvi.get("ndvi_year")
            gdf.at[idx, "soil_om"] = soil.get("avg_om_pct")
            gdf.at[idx, "soil_ph"] = soil.get("avg_ph")
            gdf.at[idx, "soil_aws"] = soil.get("total_aws_inches")
            gdf.at[idx, "soil_cec"] = soil.get("avg_cec")
            gdf.at[idx, "soil_clay"] = soil.get("avg_clay_pct")
            gdf.at[idx, "soil_sand"] = soil.get("avg_sand_pct")
            gdf.at[idx, "dominant_soil"] = soil.get("dominant_soil", "")
            gdf.at[idx, "drainage_class"] = soil.get("drainage_class", "")
            gdf.at[idx, "erosion_risk"] = soil.get("erosion_risk", "")

            bounds = row.geometry.bounds
            center = ((bounds[1] + bounds[3]) / 2.0, (bounds[0] + bounds[2]) / 2.0)

            sidebar_records.append(
                {
                    "field_name": field_name,
                    "farm_name": farm_display,
                    "field_slug": field_slug,
                    "farm_slug": farm_slug,
                    "area_acres": float(row.get("area_acres", 0.0)),
                    "county_name": str(row.get("county_name", "")),
                    "state_fips": str(row.get("state_fips", "")),
                    "center": center,
                    "bounds": bounds,
                    "ndvi_mean": ndvi.get("ndvi_mean"),
                    "soil_om": soil.get("avg_om_pct"),
                    "soil_ph": soil.get("avg_ph"),
                    "dominant_soil": soil.get("dominant_soil", ""),
                }
            )

        gdf_parts.append(gdf)

    if not gdf_parts:
        raise ValueError(f"No field boundaries found for grower: {grower_slug}")

    combined = gpd.GeoDataFrame(pd.concat(gdf_parts, ignore_index=True))
    if combined.crs is None:
        combined.set_crs(epsg=4326, inplace=True)

    return combined, sidebar_records


def _compute_map_view(gdf: gpd.GeoDataFrame) -> tuple[float, float, int]:
    bounds = gdf.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2.0
    center_lon = (bounds[0] + bounds[2]) / 2.0
    lat_span = abs(bounds[3] - bounds[1])
    zoom = 15 if lat_span < 0.01 else 13 if lat_span < 0.05 else 11 if lat_span < 0.2 else 10 if lat_span < 0.5 else 9 if lat_span < 1.0 else 8 if lat_span < 2.0 else 7 if lat_span < 5.0 else 6
    return center_lat, center_lon, zoom


def _build_html(
    gdf: gpd.GeoDataFrame,
    sidebar_records: list[dict[str, Any]],
    grower_slug: str,
    soil_polygons_gdf: gpd.GeoDataFrame | None = None,
) -> str:
    geojson_data = json.loads(gdf.to_json())
    geojson_str = json.dumps(geojson_data, separators=(",", ":"))

    soil_geojson_str = ""
    if soil_polygons_gdf is not None and not soil_polygons_gdf.empty:
        soil_geojson_data = json.loads(soil_polygons_gdf.to_json())
        soil_geojson_str = json.dumps(soil_geojson_data, separators=(",", ":"))

    center_lat, center_lon, zoom = _compute_map_view(gdf)

    sidebar_items = []
    for rec in sidebar_records:
        lat, lon = rec["center"]
        label = rec["field_name"]
        metric = ""
        if rec.get("ndvi_mean") is not None:
            metric = f" NDVI {rec['ndvi_mean']:.3f}"
        elif rec.get("soil_om") is not None:
            metric = f" OM {rec['soil_om']:.1f}%"
        elif rec.get("soil_ph") is not None:
            metric = f" pH {rec['soil_ph']:.1f}"
        sidebar_items.append(
            f"""<div class="field-item" onclick="zoomToField({lat:.6f}, {lon:.6f}, '{rec['field_slug']}', '{rec['farm_slug']}')">{label} <span class="field-metric">{metric}</span></div>"""
        )
    sidebar_html = "\n".join(sidebar_items)

    has_ndvi = any(r.get("ndvi_mean") is not None for r in sidebar_records)
    has_soil = any(r.get("soil_om") is not None for r in sidebar_records)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grower Map – {grower_slug.replace("-", " ").title()}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body, html {{ height:100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  #container {{ display:flex; height:100%; }}
  #sidebar {{
    width: 320px;
    background: #ffffff;
    border-right: 1px solid #ddd;
    padding: 16px;
    overflow-y: auto;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
  }}
  #sidebar h2 {{ font-size: 1.1em; margin-bottom: 6px; color: #1B5E20; }}
  #sidebar p {{ font-size: 0.85em; color: #555; margin-bottom: 8px; }}
  #layer-control {{
    margin-bottom: 12px;
    padding: 10px;
    background: #f4f6f8;
    border-radius: 6px;
    font-size: 0.85em;
  }}
  #layer-control label {{
    display: block;
    padding: 4px 0;
    cursor: pointer;
  }}
  #layer-control input {{ margin-right: 6px; vertical-align: middle; }}
  #field-list {{ flex: 1; overflow-y: auto; }}
  .field-item {{
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 4px;
    cursor: pointer;
    background: #f4f6f8;
    font-size: 0.9em;
    transition: background 0.15s;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .field-item:hover {{ background: #e8f5e9; }}
  .field-metric {{ font-size: 0.8em; color: #666; white-space: nowrap; margin-left: 8px; }}
  #map {{ flex: 1; height: 100%; }}
  .legend {{
    background: white;
    padding: 8px 12px;
    border-radius: 5px;
    box-shadow: 0 0 10px rgba(0,0,0,0.15);
    font-size: 0.85em;
    line-height: 1.5;
  }}
  .legend-item {{ display: flex; align-items: center; margin: 2px 0; }}
  .legend-swatch {{ display: inline-block; width: 14px; height: 14px; margin-right: 6px; border: 1px solid #999; flex-shrink: 0; }}
</style>
</head>
<body>
<div id="container">
  <div id="sidebar">
    <h2>Field List</h2>
    <p>Click a field to zoom to it.</p>
    <div id="layer-control">
      <strong>Layer:</strong>
      <label><input type="radio" name="layer" value="boundaries" checked onchange="setLayer('boundaries')"> Field Boundaries</label>
      <label><input type="radio" name="layer" value="ndvi" onchange="setLayer('ndvi')" {'disabled' if not has_ndvi else ''}> NDVI{' (no data)' if not has_ndvi else ''}</label>
      <label><input type="radio" name="layer" value="soil_om" onchange="setLayer('soil_om')" {'disabled' if not has_soil else ''}> Soil: Organic Matter %{' (no data)' if not has_soil else ''}</label>
      <label><input type="radio" name="layer" value="soil_ph" onchange="setLayer('soil_ph')" {'disabled' if not has_soil else ''}> Soil: pH{' (no data)' if not has_soil else ''}</label>
      <label><input type="radio" name="layer" value="crop_type" onchange="setLayer('crop_type')"> Crop Type</label>
      <label style="margin-top:6px;border-top:1px solid #ddd;padding-top:6px;">
        <input type="checkbox" id="showSoilPolygons" onchange="toggleSoilPolygons(this.checked)" {'disabled' if not soil_geojson_str else ''}>
        Soil Polygons (SSURGO){' <span style="color:#999">(no data)</span>' if not soil_geojson_str else ''}
      </label>
    </div>
    <div id="field-list">
      {sidebar_html}
    </div>
  </div>
  <div id="map"></div>
</div>
<script>
  var map = L.map('map', {{ renderer: L.canvas() }}).setView([{center_lat:.6f}, {center_lon:.6f}], {zoom});

  var satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19
  }});
  var streets = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }});
  satellite.addTo(map);
  L.control.layers({{"Satellite": satellite, "Street Map": streets}}, null, {{collapsed: false}}).addTo(map);

  var geojsonData = {geojson_str};
  var layerMap = {{}};
  var currentMode = 'boundaries';
  var fieldsLayer = null;

  function ndviColor(v) {{
    if (v == null) return '#cccccc';
    if (v > 0.45) return '#1a9850';
    if (v > 0.35) return '#66bd63';
    if (v > 0.25) return '#a6d96a';
    if (v > 0.15) return '#fee08b';
    if (v > 0.05) return '#f46d43';
    return '#a50026';
  }}

  function omColor(v) {{
    if (v == null) return '#cccccc';
    if (v > 3.0) return '#3e1a0a';
    if (v > 2.0) return '#6b3d1a';
    if (v > 1.5) return '#a07030';
    if (v > 1.0) return '#c4a56a';
    if (v > 0.5) return '#dfcba0';
    return '#f0e6d0';
  }}

  function phColor(v) {{
    if (v == null) return '#cccccc';
    if (v >= 6.0 && v <= 7.2) return '#2c7bb6';
    if (v >= 5.5 && v < 6.0) return '#abd9e9';
    if (v > 7.2 && v <= 7.8) return '#fdae61';
    if (v > 7.8) return '#d7191c';
    return('#ffffbf');
  }}

  function cropColor(crop) {{
    if (!crop || crop === 'Unknown' || crop === 'N/A') return '#cccccc';
    var colors = {{'Corn': '#ffd700', 'Soybeans': '#90ee90', 'Wheat': '#f5deb3', 'Cotton': '#ffffff'}};
    return colors[crop] || '#cccccc';
  }}

  function getStyle(mode) {{
    return function(feature) {{
      var p = feature.properties;
      var fill, opacity = 0.55, weight = 2.0, color = '#555';
      if (mode === 'ndvi') {{
        fill = ndviColor(p.ndvi_mean);
        opacity = 0.65;
        color = '#333';
      }} else if (mode === 'soil_om') {{
        fill = omColor(p.soil_om);
        opacity = 0.65;
        color = '#333';
      }} else if (mode === 'soil_ph') {{
        fill = phColor(p.soil_ph);
        opacity = 0.65;
        color = '#333';
      }} else if (mode === 'crop_type') {{
        fill = '#cccccc';
        opacity = 0.5;
        color = '#999';
      }} else {{
        fill = '#ffffff';
        opacity = 0.12;
        color = '#ffffff';
      }}
      return {{fillColor: fill, color: color, weight: weight, fillOpacity: opacity}};
    }};
  }}

  function buildPopup(p) {{
    var html = '<div style="font-size:0.9em;line-height:1.5;">';
    html += '<b>Grower:</b> ' + (p.grower_name || 'N/A') + '<br>';
    html += '<b>Farm:</b> ' + (p.farm_name || 'N/A') + '<br>';
    html += '<b>Field:</b> ' + (p.field_name || 'N/A') + '<br>';
    html += '<b>Field ID:</b> ' + (p.field_id || 'N/A') + '<br>';
    html += '<b>Area:</b> ' + (p.area_acres ? Number(p.area_acres).toFixed(2) : 'N/A') + ' acres<br>';
    html += '<b>County:</b> ' + (p.county_name || 'N/A') + '<br>';
    if (p.ndvi_mean != null) {{
      html += '<hr style="margin:4px 0"><b>NDVI (latest):</b> ' + Number(p.ndvi_mean).toFixed(4) + '<br>';
      html += '<b>Scenes:</b> ' + (p.ndvi_scene_count || 0) + '<br>';
    }}
    if (p.dominant_soil) {{
      html += '<hr style="margin:4px 0"><b>Dominant Soil:</b> ' + p.dominant_soil + '<br>';
      html += '<b>Drainage:</b> ' + (p.drainage_class || 'N/A') + '<br>';
      if (p.soil_om != null) html += '<b>OM:</b> ' + Number(p.soil_om).toFixed(2) + '%<br>';
      if (p.soil_ph != null) html += '<b>pH:</b> ' + Number(p.soil_ph).toFixed(2) + '<br>';
      if (p.soil_aws != null) html += '<b>AWS:</b> ' + Number(p.soil_aws).toFixed(2) + ' in<br>';
      if (p.soil_cec != null) html += '<b>CEC:</b> ' + Number(p.soil_cec).toFixed(1) + '<br>';
    }}
    html += '</div>';
    return html;
  }}

  fieldsLayer = L.geoJSON(geojsonData, {{
    style: getStyle('boundaries'),
    onEachFeature: function(feature, layer) {{
      var p = feature.properties;
      layer.bindPopup(buildPopup(p));
      layer.on('mouseover', function(e) {{
        if (currentMode === 'boundaries') {{
          e.target.setStyle({{color: '#FF8C00', weight: 4, fillColor: '#FF8C00', fillOpacity: 0.35}});
        }} else {{
          e.target.setStyle({{color: '#FF8C00', weight: 4, fillOpacity: 0.8}});
        }}
      }});
      layer.on('mouseout', function(e) {{
        if (currentMode === 'boundaries') {{
          fieldsLayer.resetStyle(e.target);
        }} else {{
          e.target.setStyle(getStyle(currentMode)(feature));
        }}
      }});
      if (p.field_slug && p.farm_slug) {{
        layerMap[p.farm_slug + '::' + p.field_slug] = layer;
      }}
    }}
  }}).addTo(map);

  map.fitBounds(fieldsLayer.getBounds(), {{padding: [20, 20]}});

  function setLayer(mode) {{
    currentMode = mode;
    fieldsLayer.setStyle(getStyle(mode));
    fieldsLayer.eachLayer(function(l) {{
      var f = l.feature;
      if (f) l.setStyle(getStyle(mode)(f));
    }});
    updateLegend(mode);
    updateSidebarMetrics(mode);
  }}

  function updateLegend(mode) {{
    var div = document.getElementById('legend-inner');
    if (!div) return;
    var items = [];
    if (mode === 'ndvi') {{
      items = [
        ['#1a9850', '> 0.45 (High)'], ['#66bd63', '0.35 - 0.45'],
        ['#a6d96a', '0.25 - 0.35'], ['#fee08b', '0.15 - 0.25'],
        ['#f46d43', '0.05 - 0.15'], ['#a50026', '< 0.05 (Low)']
      ];
    }} else if (mode === 'soil_om') {{
      items = [
        ['#3e1a0a', '> 3.0%'], ['#6b3d1a', '2.0 - 3.0%'],
        ['#a07030', '1.5 - 2.0%'], ['#c4a56a', '1.0 - 1.5%'],
        ['#dfcba0', '0.5 - 1.0%'], ['#f0e6d0', '< 0.5%']
      ];
    }} else if (mode === 'soil_ph') {{
      items = [
        ['#2c7bb6', '6.0 - 7.2 (Optimal)'], ['#abd9e9', '5.5 - 6.0 (Slightly Acidic)'],
        ['#fdae61', '7.2 - 7.8 (Slightly Alkaline)'], ['#d7191c', '> 7.8 (Alkaline)'],
        ['#ffffbf', '< 5.5 (Acidic)']
      ];
    }} else if (mode === 'crop_type') {{
      items = [['#cccccc', 'CDL data unavailable']];
    }} else {{
      items = [['#ffffff', 'Field Boundary']];
    }}
    div.innerHTML = '<b>Legend</b><br>' + items.map(function(i) {{
      return '<div class="legend-item"><span class="legend-swatch" style="background:' + i[0] + '"></span>' + i[1] + '</div>';
    }}).join('');
  }}

  function updateSidebarMetrics(mode) {{
    var items = document.querySelectorAll('.field-item');
    fieldsLayer.eachLayer(function(l, idx) {{
      var p = l.feature ? l.feature.properties : null;
      var span = items[idx] ? items[idx].querySelector('.field-metric') : null;
      if (!p || !span) return;
      var val = '';
      if (mode === 'ndvi' && p.ndvi_mean != null) val = 'NDVI ' + Number(p.ndvi_mean).toFixed(3);
      else if (mode === 'soil_om' && p.soil_om != null) val = 'OM ' + Number(p.soil_om).toFixed(1) + '%';
      else if (mode === 'soil_ph' && p.soil_ph != null) val = 'pH ' + Number(p.soil_ph).toFixed(1);
      else if (mode === 'boundaries') val = Number(p.area_acres || 0).toFixed(1) + ' ac';
      span.textContent = val;
    }});
  }}

  function toggleSoilPolygons(show) {{
    if (window.soilPolygonsLayer) {{
      if (show) {{ map.addLayer(window.soilPolygonsLayer); }}
      else {{ map.removeLayer(window.soilPolygonsLayer); }}
    }}
  }}

  function zoomToField(lat, lon, fieldSlug, farmSlug) {{
    var key = farmSlug + '::' + fieldSlug;
    var layer = layerMap[key];
    if (layer) {{
      map.fitBounds(layer.getBounds(), {{padding: [60, 60]}});
      layer.openPopup();
    }} else {{
      map.setView([lat, lon], 15);
    }}
  }}

  // Soil polygon overlay
  {f'var soilGeojson = {soil_geojson_str};' if soil_geojson_str else '/* no soil polygons */'}
  {f'''
  window.soilPolygonsLayer = L.geoJSON(soilGeojson, {{
    style: {{color: '#8B4513', weight: 1.5, fillColor: '#8B4513', fillOpacity: 0.08}},
    onEachFeature: function(feat, layer) {{
      layer.bindPopup('<b>Soil Map Unit:</b> ' + (feat.properties.mukey || 'N/A') + '<br><b>Field ID:</b> ' + (feat.properties.field_id_1 || 'N/A'));
    }}
  }});
  ''' if soil_geojson_str else ''}

  var legend = L.control({{position: 'bottomright'}});
  legend.onAdd = function(map) {{
    var div = L.DomUtil.create('div', 'legend');
    div.innerHTML = '<div id="legend-inner"><b>Legend</b><br><span style="font-size:0.8em;color:#666;">Select a layer above</span></div>';
    return div;
  }};
  legend.addTo(map);
  updateLegend('boundaries');
</script>
</body>
</html>"""
    return html


def generate_grower_web_map(grower_slug: str, output_dir: Path | None = None) -> Path:
    """Main entrypoint: generate the HTML map and return the output path."""
    gdf, sidebar_records = _collect_grower_fields(grower_slug)

    # Collect soil polygons as overlay
    soil_polygons = None
    farms_dir = grower_dir(grower_slug) / "farms"
    if farms_dir.exists():
        all_soil: list[gpd.GeoDataFrame] = []
        for farm_path in sorted(farms_dir.iterdir()):
            if not farm_path.is_dir():
                continue
            farm_slug = farm_path.name
            sp = _load_soil_polygons(grower_slug, farm_slug)
            if sp is not None and not sp.empty:
                all_soil.append(sp)
        if all_soil:
            soil_polygons = gpd.GeoDataFrame(pd.concat(all_soil, ignore_index=True, sort=False))

    html = _build_html(gdf, sidebar_records, grower_slug, soil_polygons)

    if output_dir is None:
        output_dir = grower_maps_dir(grower_slug)
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / "grower_web_map.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a lightweight interactive web map for a grower with NDVI, soil, and crop layers.")
    parser.add_argument("--grower-slug", required=True, help="Grower slug (e.g., il-grower)")
    parser.add_argument("--output-dir", default=None, help="Optional output directory override")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    out_path = generate_grower_web_map(args.grower_slug, out_dir)
    size_kb = out_path.stat().st_size / 1024.0
    print(f"Generated grower web map: {out_path}")
    print(f"File size: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
