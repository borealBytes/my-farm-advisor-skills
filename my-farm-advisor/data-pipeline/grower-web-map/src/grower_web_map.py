#!/usr/bin/env python3
"""Build a lightweight interactive HTML field map for a My Farm Advisor grower.

The generator reads real pipeline output from the installed runtime tree
(``growers/<grower>/farms/*/boundary/field_boundaries.geojson``, farm metadata,
field inventory, and per-field metadata) and writes one self-contained HTML file
per grower.

Only geometry and a small attribute set are embedded. Satellite basemap tiles are
requested from Esri at view time, so no imagery, rasters, or data bundles are
written into the HTML.

Area reporting is hectares. Source boundaries carry ``area_acres``; every metric
is converted with the exact international acre definition
(``1 acre = 4046.8564224 m^2``), never by relabelling a number.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any, Iterable

GENERATOR_NAME = "grower-web-map"
GENERATOR_VERSION = "0.1.0"

# Exact international acre and hectare definitions.
SQUARE_METRES_PER_ACRE = 4046.8564224
SQUARE_METRES_PER_HECTARE = 10_000.0
ACRE_TO_HECTARE = SQUARE_METRES_PER_ACRE / SQUARE_METRES_PER_HECTARE

MAP_SUBDIR = ("derived", "maps")

# Colourblind-friendly fills, assigned per farm in slug order.
FARM_PALETTE = (
    "#2f7d4f",
    "#c2703d",
    "#3b6ea5",
    "#8a5aa8",
    "#b8972e",
    "#2f8f8a",
    "#a5453b",
    "#5c6b73",
)

SUPPORTED_GEOMETRY_TYPES = ("Polygon", "MultiPolygon")


class GrowerMapError(RuntimeError):
    """Raised when a grower tree cannot be turned into a usable map."""


def acres_to_hectares(acres: float) -> float:
    """Convert acres to hectares using the exact international acre."""
    return float(acres) * ACRE_TO_HECTARE


def resolve_runtime_base(data_root: Path | str) -> Path:
    """Accept either the runtime root or its ``data-pipeline`` base directory."""
    root = Path(data_root).expanduser()
    for candidate in (root / "data-pipeline", root):
        if (candidate / "growers").is_dir():
            return candidate.resolve()
    raise GrowerMapError(
        f"no growers directory under {root}; expected <data-root>/data-pipeline/growers"
    )


def list_growers(base: Path) -> list[str]:
    growers_dir = base / "growers"
    if not growers_dir.is_dir():
        raise GrowerMapError(f"growers directory missing: {growers_dir}")
    return sorted(
        path.name
        for path in growers_dir.iterdir()
        if path.is_dir() and (path / "farms").is_dir()
    )


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GrowerMapError(f"cannot read JSON file {path}: {exc}") from exc


def _load_inventory(farm_dir: Path) -> dict[str, str]:
    inventory_path = farm_dir / "manifests" / "field-inventory.csv"
    mapping: dict[str, str] = {}
    if not inventory_path.is_file():
        return mapping
    for line in inventory_path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            mapping[parts[0]] = parts[1]
    return mapping


def _field_display_name(farm_dir: Path, field_slug: str) -> str:
    metadata = _read_json(farm_dir / "fields" / field_slug / "field.json", {}) or {}
    display = metadata.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.strip()
    return field_slug


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _iter_rings(geometry: dict[str, Any]) -> Iterable[list[Any]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        for ring in coordinates:
            if isinstance(ring, list):
                yield ring
    elif geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        for polygon in coordinates:
            if isinstance(polygon, list):
                for ring in polygon:
                    if isinstance(ring, list):
                        yield ring


def _geometry_is_usable(geometry: Any) -> bool:
    if not isinstance(geometry, dict) or geometry.get("type") not in SUPPORTED_GEOMETRY_TYPES:
        return False
    rings = list(_iter_rings(geometry))
    if not rings:
        return False
    for ring in rings:
        if len(ring) < 4:
            return False
        for position in ring:
            if not isinstance(position, (list, tuple)) or len(position) < 2:
                return False
            lon, lat = position[0], position[1]
            if not (_is_number(lon) and _is_number(lat)):
                return False
            if not (-180.0 <= float(lon) <= 180.0 and -90.0 <= float(lat) <= 90.0):
                return False
    return True


def _ring_area_m2(ring: list[Any]) -> float:
    """Spherical polygon area for one ring, using the authalic Earth radius.

    Only used as a fallback when the pipeline did not write ``area_acres``.
    """
    radius = 6371007.181
    total = 0.0
    for index in range(len(ring) - 1):
        lon1, lat1 = float(ring[index][0]), float(ring[index][1])
        lon2, lat2 = float(ring[index + 1][0]), float(ring[index + 1][1])
        total += math.radians(lon2 - lon1) * (
            2.0 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * radius * radius / 2.0


def _geometry_area_ha(geometry: dict[str, Any]) -> float:
    area_m2 = 0.0
    if geometry.get("type") == "Polygon":
        polygons = [geometry.get("coordinates", [])]
    else:
        polygons = geometry.get("coordinates", [])
    for polygon in polygons:
        for index, ring in enumerate(polygon):
            ring_area = _ring_area_m2(ring)
            # The first ring is the exterior; later rings are holes.
            area_m2 += ring_area if index == 0 else -ring_area
    return max(area_m2, 0.0) / SQUARE_METRES_PER_HECTARE


def _field_area_ha(properties: dict[str, Any], geometry: dict[str, Any]) -> float:
    acres = properties.get("area_acres")
    if _is_number(acres):
        return acres_to_hectares(float(acres))
    return _geometry_area_ha(geometry)


def _build_field_feature(
    *,
    raw_feature: dict[str, Any],
    grower_slug: str,
    grower_name: str,
    farm_slug: str,
    farm_name: str,
    inventory: dict[str, str],
    farm_dir: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, float]:
    geometry = raw_feature.get("geometry")
    if not _geometry_is_usable(geometry):
        return None, {"reason": "unsupported_or_invalid_geometry"}, 0.0

    properties = raw_feature.get("properties") or {}
    field_id = properties.get("field_id") or raw_feature.get("id")
    if not isinstance(field_id, str) or not field_id.strip():
        return None, {"reason": "missing_field_id"}, 0.0
    field_id = field_id.strip()
    field_slug = inventory.get(field_id, field_id)
    area_ha = _field_area_ha(properties, geometry)

    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "field_id": field_id,
            "field_slug": field_slug,
            "field_name": _field_display_name(farm_dir, field_slug),
            "farm_slug": farm_slug,
            "farm_name": farm_name,
            "grower_slug": grower_slug,
            "grower_name": grower_name,
            "area_ha": round(area_ha, 3),
            "crop_name": properties.get("crop_name"),
            "county_name": properties.get("county_name"),
            "state_fips": properties.get("state_fips"),
            "source": properties.get("source"),
        },
    }
    return feature, None, area_ha


def _build_farm(
    farm_dir: Path,
    *,
    grower_slug: str,
    grower_name: str,
    color: str,
) -> dict[str, Any] | None:
    boundary_path = farm_dir / "boundary" / "field_boundaries.geojson"
    if not boundary_path.is_file():
        return None

    collection = _read_json(boundary_path, {}) or {}
    raw_features = collection.get("features")
    if not isinstance(raw_features, list):
        raise GrowerMapError(f"boundary file has no feature list: {boundary_path}")

    farm_meta = _read_json(farm_dir / "farm.json", {}) or {}
    farm_slug = str(farm_meta.get("farm_slug") or farm_dir.name)
    farm_name = str(farm_meta.get("display_name") or farm_slug)
    state = farm_meta.get("state")
    inventory = _load_inventory(farm_dir)

    features: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    raw_area_ha = 0.0

    for index, raw_feature in enumerate(raw_features):
        feature, skip, area_ha = _build_field_feature(
            raw_feature=raw_feature,
            grower_slug=grower_slug,
            grower_name=grower_name,
            farm_slug=farm_slug,
            farm_name=farm_name,
            inventory=inventory,
            farm_dir=farm_dir,
        )
        if feature is None:
            skipped.append(
                {
                    "farm_slug": farm_slug,
                    "feature_index": index,
                    "reason": (skip or {}).get("reason", "unknown"),
                }
            )
            continue
        features.append(feature)
        raw_area_ha += area_ha
        fields.append(
            {
                "field_id": feature["properties"]["field_id"],
                "field_slug": feature["properties"]["field_slug"],
                "field_name": feature["properties"]["field_name"],
                "area_ha": feature["properties"]["area_ha"],
            }
        )

    features.sort(key=lambda item: item["properties"]["field_slug"])
    fields.sort(key=lambda item: item["field_slug"])

    return {
        "slug": farm_slug,
        "name": farm_name,
        "state": state,
        "color": color,
        "area_ha": round(raw_area_ha, 2),
        "area_ha_raw": raw_area_ha,
        "fields": fields,
        "features": features,
        "skipped": skipped,
        "boundary_path": str(boundary_path),
    }


def build_grower_payload(grower_dir: Path) -> dict[str, Any]:
    """Collect every farm and field under one grower into a render-ready payload."""
    grower_slug = grower_dir.name
    grower_meta = _read_json(grower_dir / "grower.json", {}) or {}
    grower_name = str(grower_meta.get("display_name") or grower_slug)

    farms_dir = grower_dir / "farms"
    if not farms_dir.is_dir():
        raise GrowerMapError(f"grower has no farms directory: {farms_dir}")

    farms: list[dict[str, Any]] = []
    feature_collection: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    total_area_ha_raw = 0.0

    farm_dirs = sorted(
        (path for path in farms_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    for index, farm_dir in enumerate(farm_dirs):
        farm = _build_farm(
            farm_dir,
            grower_slug=grower_slug,
            grower_name=grower_name,
            color=FARM_PALETTE[index % len(FARM_PALETTE)],
        )
        if farm is None:
            continue
        skipped.extend(farm["skipped"])
        if not farm["features"]:
            continue
        feature_collection.extend(farm["features"])
        total_area_ha_raw += farm["area_ha_raw"]
        farms.append(
            {
                "slug": farm["slug"],
                "name": farm["name"],
                "state": farm["state"],
                "color": farm["color"],
                "area_ha": farm["area_ha"],
                "fields": farm["fields"],
            }
        )

    total_area_ha = round(total_area_ha_raw, 2)

    return {
        "generator": GENERATOR_NAME,
        "version": GENERATOR_VERSION,
        "area_unit": "hectares",
        "grower": {
            "slug": grower_slug,
            "name": grower_name,
            "farm_count": len(farms),
            "field_count": sum(len(farm["fields"]) for farm in farms),
            "area_ha": total_area_ha,
        },
        "farms": farms,
        "geojson": {"type": "FeatureCollection", "features": feature_collection},
        "skipped": skipped,
    }


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-generator="__GENERATOR__" data-generator-version="__VERSION__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--panel:#16201a;--panel-2:#202c24;--ink:#f2f6f3;--muted:#a3b3a9;--accent:#63c98a;--line:#32413a}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#101410}
#app{display:grid;grid-template-columns:330px 1fr;height:100%}
#sidebar{background:var(--panel);color:var(--ink);display:flex;flex-direction:column;min-height:0;border-right:1px solid #0b110d}
#sidebar header{padding:18px 18px 12px;border-bottom:1px solid var(--line);position:relative}
#sidebar-close{display:none;padding:5px 9px;border-radius:6px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);font:inherit;font-size:.72rem;cursor:pointer}
#sidebar h1{margin:0;font-size:1.22rem;line-height:1.25;letter-spacing:.01em}
#sidebar .sub{margin:4px 0 0;color:var(--muted);font-size:.76rem;text-transform:uppercase;letter-spacing:.09em}
.stats{display:flex;gap:8px;margin:14px 0 12px;padding:0}
.stats div{flex:1;background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:8px 9px}
.stats dt{color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.08em}
.stats dd{margin:2px 0 0;font-size:1rem;font-weight:600;font-variant-numeric:tabular-nums}
#search{width:100%;padding:8px 10px;border-radius:7px;border:1px solid var(--line);background:#0f1712;color:var(--ink);font-size:.84rem}
#search::placeholder{color:#7f9187}
#field-list{flex:1;overflow-y:auto;padding:10px 10px 14px}
.farm-group{margin:0 0 14px}
.farm-group h2{display:flex;align-items:center;gap:7px;margin:6px 6px 7px;font-size:.79rem;font-weight:600;letter-spacing:.01em}
.farm-group .swatch{width:11px;height:11px;border-radius:3px;flex:0 0 auto;border:1px solid rgba(255,255,255,.5)}
.farm-group .farm-sub{margin-left:auto;color:var(--muted);font-weight:400;font-size:.7rem;white-space:nowrap}
.field-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;width:100%;margin:0 0 3px;padding:7px 9px;border:1px solid transparent;border-radius:6px;background:transparent;color:var(--ink);font:inherit;font-size:.82rem;text-align:left;cursor:pointer}
.field-row:hover,.field-row:focus-visible{background:var(--panel-2);border-color:var(--line);outline:none}
.field-row.is-active{background:#20362a;border-color:var(--accent)}
.field-name{overflow-wrap:anywhere}
.field-row .field-meta{color:var(--muted);font-size:.73rem;white-space:nowrap;font-variant-numeric:tabular-nums}
#sidebar footer{padding:12px 14px 14px;border-top:1px solid var(--line)}
#fit-all{width:100%;padding:8px 10px;border-radius:7px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink);font:inherit;font-size:.82rem;cursor:pointer}
#fit-all:hover{border-color:var(--accent)}
.hint{margin:8px 2px 0;color:var(--muted);font-size:.68rem;line-height:1.42}
#map-wrap{position:relative;min-height:0}
#map{position:absolute;inset:0;background:#dfe5df}
#sidebar-toggle{display:none;position:absolute;z-index:1000;top:88px;left:12px;padding:8px 12px;border-radius:8px;border:1px solid #cfd8d1;background:#fff;color:#16201a;font:inherit;font-size:.82rem;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.22);cursor:pointer}
#empty{display:none;position:absolute;z-index:900;inset:0;align-items:center;justify-content:center;padding:24px;background:rgba(22,32,26,.82);color:#fff;text-align:center;font-size:.95rem}
#map-error{display:none;position:absolute;z-index:950;left:50%;top:16px;transform:translateX(-50%);max-width:min(90%,520px);padding:10px 14px;border-radius:8px;background:#7f1d1d;color:#fff;font-size:.82rem;box-shadow:0 4px 18px rgba(0,0,0,.3)}
.leaflet-popup-content{margin:12px 14px}
.leaflet-popup-content .popup h3{margin:0 0 8px;font-size:.95rem;line-height:1.25}
.leaflet-popup-content .popup table{border-collapse:collapse;font-size:.8rem}
.leaflet-popup-content .popup th{text-align:left;vertical-align:top;padding:2px 12px 2px 0;color:#5b6b61;font-weight:600;white-space:nowrap}
.leaflet-popup-content .popup td{vertical-align:top;padding:2px 0}
@media (max-width:820px){
  #app{grid-template-columns:1fr}
  #sidebar{position:absolute;z-index:1100;inset:0 auto 0 0;width:min(88vw,340px);transform:translateX(-100%);transition:transform .18s ease;box-shadow:0 0 24px rgba(0,0,0,.4)}
  #app.sidebar-open #sidebar{transform:none}
  #sidebar-toggle{display:block}
  #app.sidebar-open #sidebar-close{display:block;position:absolute;top:10px;right:10px;z-index:1200}
}
@media (prefers-reduced-motion:reduce){#sidebar{transition:none}}
</style>
</head>
<body>
<noscript><p style="padding:16px;font-family:sans-serif">This map needs JavaScript enabled.</p></noscript>
<div id="app">
  <aside id="sidebar" aria-label="Grower fields">
    <header>
      <button id="sidebar-close" type="button" aria-label="Close field list">Close</button>
      <h1>__GROWER_NAME__</h1>
      <p class="sub">Grower field map</p>
      <dl class="stats">
        <div><dt>Farms</dt><dd id="stat-farms">0</dd></div>
        <div><dt>Fields</dt><dd id="stat-fields">0</dd></div>
        <div><dt>Area</dt><dd><span id="stat-area">0</span> ha</dd></div>
      </dl>
      <input id="search" type="search" placeholder="Filter fields" aria-label="Filter fields by name or ID">
    </header>
    <div id="field-list"></div>
    <footer>
      <button id="fit-all" type="button">Fit all fields</button>
      <p class="hint">Click a field on the map or in this list for grower, farm, and field details. Satellite imagery loads from Esri; area is shown in hectares.</p>
    </footer>
  </aside>
  <main id="map-wrap">
    <button id="sidebar-toggle" type="button" aria-expanded="false" aria-controls="sidebar">Fields</button>
    <div id="map" role="application" aria-label="Interactive map of grower fields"></div>
    <div id="empty">This grower has no field polygons to display.</div>
    <div id="map-error" role="alert"></div>
  </main>
</div>
<script id="grower-map-data" type="application/json">__DATA__</script>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function () {
  'use strict';

  var DATA = JSON.parse(document.getElementById('grower-map-data').textContent);
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }

  function fmtHa(value) {
    var number = Number(value);
    if (!isFinite(number)) { return '0.0'; }
    return number.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1});
  }

  function showError(message) {
    var box = document.getElementById('map-error');
    box.textContent = message;
    box.style.display = 'block';
  }

  var features = (DATA.geojson && DATA.geojson.features) || [];
  document.getElementById('stat-farms').textContent = String(DATA.grower.farm_count);
  document.getElementById('stat-fields').textContent = String(DATA.grower.field_count);
  document.getElementById('stat-area').textContent = fmtHa(DATA.grower.area_ha);

  var farmColors = {};
  DATA.farms.forEach(function (farm) { farmColors[farm.slug] = farm.color; });

  var map = L.map('map', {zoomControl: true, preferCanvas: true});
  var imagery = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {
      maxZoom: 19,
      maxNativeZoom: 19,
      attribution: 'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community'
    }
  );
  var streets = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  });
  var labels = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    {maxZoom: 19, attribution: 'Labels &copy; <a href="https://www.esri.com/">Esri</a>'}
  );

  imagery.addTo(map);
  labels.addTo(map);
  var locators = L.layerGroup().addTo(map);
  L.control.layers(
    {'Satellite (Esri World Imagery)': imagery, 'Street map (OpenStreetMap)': streets},
    {'Place labels': labels, 'Field locators': locators},
    {collapsed: true}
  ).addTo(map);
  L.control.scale({imperial: false, position: 'bottomright'}).addTo(map);

  var fieldLayers = {};
  var rowsById = {};

  function popupHtml(p) {
    var rows = [
      ['Grower', p.grower_name],
      ['Farm', p.farm_name],
      ['Field ID', p.field_id],
      ['Area', fmtHa(p.area_ha) + ' ha'],
      ['Crop (OSM tag)', p.crop_name || 'not tagged'],
      ['County', p.county_name || 'unknown'],
      ['Boundary source', p.source || 'pipeline boundary']
    ];
    var body = rows.map(function (row) {
      return '<tr><th>' + esc(row[0]) + '</th><td>' + esc(row[1]) + '</td></tr>';
    }).join('');
    return '<div class="popup"><h3>' + esc(p.field_name) + '</h3><table>' + body + '</table></div>';
  }

  function setActive(fieldId) {
    Object.keys(rowsById).forEach(function (key) {
      rowsById[key].classList.toggle('is-active', key === fieldId);
    });
    var row = rowsById[fieldId];
    if (row && row.scrollIntoView) {
      row.scrollIntoView({block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth'});
    }
  }

  function focusField(fieldId) {
    var layer = fieldLayers[fieldId];
    if (!layer) { return; }
    setActive(fieldId);
    var bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, {maxZoom: 17, padding: [50, 50], animate: !reduceMotion});
    }
    layer.openPopup();
  }

  if (!features.length) {
    document.getElementById('empty').style.display = 'flex';
  }

  var geoLayer = L.geoJSON(DATA.geojson, {
    style: function (feature) {
      return {
        color: '#ffffff',
        weight: 2,
        opacity: 0.95,
        fillColor: farmColors[feature.properties.farm_slug] || '#2f7d4f',
        fillOpacity: 0.28
      };
    },
    onEachFeature: function (feature, layer) {
      var p = feature.properties;
      layer.bindPopup(popupHtml(p), {maxWidth: 340, autoPan: true});
      layer.bindTooltip(p.field_name, {sticky: true, direction: 'top', opacity: 0.92});
      layer.on({
        mouseover: function () { layer.setStyle({weight: 3, opacity: 1, fillOpacity: 0.46}); },
        mouseout: function () { layer.setStyle({weight: 2, opacity: 0.95, fillOpacity: 0.28}); },
        click: function () { focusField(p.field_id); }
      });
      fieldLayers[p.field_id] = layer;

      var marker = L.circleMarker(layer.getBounds().getCenter(), {
        radius: 6,
        color: '#ffffff',
        weight: 2,
        opacity: 0.95,
        fillColor: farmColors[p.farm_slug] || '#2f7d4f',
        fillOpacity: 1
      });
      marker.bindTooltip(p.field_name, {direction: 'top', opacity: 0.92});
      marker.on('click', function () { focusField(p.field_id); });
      locators.addLayer(marker);
    }
  }).addTo(map);

  var list = document.getElementById('field-list');
  DATA.farms.forEach(function (farm) {
    var group = document.createElement('section');
    group.className = 'farm-group';

    var heading = document.createElement('h2');
    heading.innerHTML =
      '<span class="swatch" style="background:' + esc(farm.color) + '"></span>' +
      '<span>' + esc(farm.name) + '</span>' +
      '<span class="farm-sub">' + esc(farm.state || '') +
      (farm.state ? ' &middot; ' : '') + fmtHa(farm.area_ha) + ' ha</span>';
    group.appendChild(heading);

    farm.fields.forEach(function (field) {
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'field-row';
      row.dataset.fieldId = field.field_id;
      row.dataset.search = (field.field_name + ' ' + field.field_id + ' ' + field.field_slug + ' ' + farm.name).toLowerCase();
      row.innerHTML =
        '<span class="field-name">' + esc(field.field_name) + '</span>' +
        '<span class="field-meta">' + fmtHa(field.area_ha) + ' ha</span>';
      row.addEventListener('click', function () { focusField(field.field_id); });
      rowsById[field.field_id] = row;
      group.appendChild(row);
    });

    list.appendChild(group);
  });

  document.getElementById('fit-all').addEventListener('click', function () {
    var bounds = geoLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, {maxZoom: 16, padding: [40, 40], animate: !reduceMotion});
    }
  });

  var search = document.getElementById('search');
  search.addEventListener('input', function () {
    var query = search.value.trim().toLowerCase();
    var visible = 0;
    list.querySelectorAll('.field-row').forEach(function (row) {
      var match = !query || row.dataset.search.indexOf(query) !== -1;
      row.style.display = match ? '' : 'none';
      if (match) { visible += 1; }
    });
    list.querySelectorAll('.farm-group').forEach(function (group) {
      var any = Array.prototype.some.call(group.querySelectorAll('.field-row'), function (row) {
        return row.style.display !== 'none';
      });
      group.style.display = any ? '' : 'none';
    });
    if (!visible && query) {
      showError('No fields match "' + query + '".');
    } else {
      document.getElementById('map-error').style.display = 'none';
    }
  });

  var toggle = document.getElementById('sidebar-toggle');
  toggle.addEventListener('click', function () {
    var open = document.getElementById('app').classList.toggle('sidebar-open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  var closeButton = document.getElementById('sidebar-close');
  closeButton.addEventListener('click', function () {
    document.getElementById('app').classList.remove('sidebar-open');
    toggle.setAttribute('aria-expanded', 'false');
  });

  if (features.length) {
    var initial = geoLayer.getBounds();
    if (initial.isValid()) {
      map.fitBounds(initial, {maxZoom: 16, padding: [36, 36], animate: false});
    } else {
      map.setView([39.8, -98.5], 4);
    }
  } else {
    map.setView([39.8, -98.5], 4);
  }

  setTimeout(function () { map.invalidateSize(); }, 0);
})();
</script>
</body>
</html>
"""


def render_html(payload: dict[str, Any], title: str | None = None) -> str:
    """Render the single-file HTML document for one grower payload."""
    grower_name = payload["grower"]["name"]
    resolved_title = title or f"{grower_name} — field map"
    data_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    replacements = {
        "__GENERATOR__": GENERATOR_NAME,
        "__VERSION__": GENERATOR_VERSION,
        "__TITLE__": html.escape(resolved_title, quote=True),
        "__GROWER_NAME__": html.escape(grower_name, quote=True),
        "__DATA__": data_json,
    }
    document = _HTML_TEMPLATE
    for token, value in replacements.items():
        document = document.replace(token, value)
    return document


def write_grower_map(
    *,
    base: Path,
    grower_slug: str,
    output_dir: Path | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Build and write one grower map plus its manifest. Returns a result record."""
    grower_dir = base / "growers" / grower_slug
    if not grower_dir.is_dir():
        raise GrowerMapError(f"grower not found: {grower_dir}")

    payload = build_grower_payload(grower_dir)
    field_count = payload["grower"]["field_count"]
    if field_count == 0:
        raise GrowerMapError(
            f"grower '{grower_slug}' has no usable field polygons under {grower_dir / 'farms'}"
        )

    document = render_html(payload, title=title)
    destination = output_dir or grower_dir.joinpath(*MAP_SUBDIR)
    destination.mkdir(parents=True, exist_ok=True)
    html_path = destination / f"{grower_slug}_fields_map.html"
    html_path.write_text(document, encoding="utf-8")

    manifest = {
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "grower_slug": grower_slug,
        "grower_name": payload["grower"]["name"],
        "html_path": str(html_path),
        "html_bytes": len(document.encode("utf-8")),
        "farm_count": payload["grower"]["farm_count"],
        "field_count": field_count,
        "area_unit": "hectares",
        "area_ha": payload["grower"]["area_ha"],
        "area_source": (
            "converted from field_boundaries.geojson area_acres "
            "(1 acre = 4046.8564224 m2)"
        ),
        "farms": [
            {
                "slug": farm["slug"],
                "name": farm["name"],
                "state": farm["state"],
                "field_count": len(farm["fields"]),
                "area_ha": farm["area_ha"],
            }
            for farm in payload["farms"]
        ],
        "skipped_features": payload["skipped"],
        "basemap": {
            "provider": "Esri World Imagery",
            "url_template": (
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ),
            "requires_internet": True,
        },
        "sources": {
            "boundaries": "growers/*/farms/*/boundary/field_boundaries.geojson",
            "field_metadata": "growers/*/farms/*/fields/<field_slug>/field.json",
            "inventory": "growers/*/farms/*/manifests/field-inventory.csv",
        },
    }
    manifest_path = destination / f"{grower_slug}_fields_map.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return {
        "grower_slug": grower_slug,
        "html_path": html_path,
        "manifest_path": manifest_path,
        "html_bytes": manifest["html_bytes"],
        "farm_count": manifest["farm_count"],
        "field_count": field_count,
        "area_ha": manifest["area_ha"],
        "skipped_features": len(payload["skipped"]),
    }
