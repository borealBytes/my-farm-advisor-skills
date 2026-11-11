"""Build lightweight per-farm interactive field maps for existing growers."""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# NDVI rendering is the only part that needs third-party packages. It is
# optional: without rasterio/Pillow the map still builds, just without the
# NDVI overlay. Soil polygons only need the standard library.
NDVI_VMIN = -0.2
NDVI_VMAX = 1.0
NDVI_MAX_SIDE = 256

# matplotlib's RdYlGn, kept byte-identical so a value has the same colour in
# the map as in the NDVI cards the pipeline already renders.
RDYLGN_STOPS = (
    "#a50026",
    "#d73027",
    "#f46d43",
    "#fdae61",
    "#fee08b",
    "#ffffbf",
    "#d9ef8b",
    "#a6d96a",
    "#66bd63",
    "#1a9850",
    "#006837",
)

# Categorical palette for soil map units. Assigned in mukey order per farm so a
# unit keeps the same colour across rebuilds.
SOIL_PALETTE = (
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
    "#8cd17d",
    "#86bcb6",
    "#d37295",
    "#a0cbe8",
    "#ffbe7d",
    "#fabfd2",
    "#b6992d",
    "#499894",
    "#f1ce63",
    "#d4a6c8",
)

M_PER_DEG = 111_320.0
ACRES_PER_SQM = 1.0 / 4046.8564224
TRACE_ACRES = 0.05

DEFAULT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root { --ink:#1b2430; --panel:#ffffff; --accent:#ffd23f; --muted:#5b6776; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--ink); }
  #map { position:absolute; inset:0; background:#e9eef3; }
  #panel {
    position:absolute; z-index:1000; top:12px; left:12px; width:308px; max-height:calc(100% - 24px);
    display:flex; flex-direction:column; background:var(--panel); border-radius:10px;
    box-shadow:0 6px 24px rgba(16,24,40,.22); overflow:hidden;
  }
  #panel header { padding:14px 16px 10px; border-bottom:1px solid #e6ebf1; }
  #panel h1 { margin:0; font-size:17px; line-height:1.25; }
  #panel p { margin:4px 0 0; font-size:12.5px; color:var(--muted); }
  #panel .actions { padding:10px 12px 4px; }
  #panel button.reset {
    width:100%; padding:7px 10px; font-size:12.5px; cursor:pointer;
    border:1px solid #d4dbe4; border-radius:7px; background:#f7f9fc; color:#24303f;
  }
  #panel button.reset:hover { background:#eef2f7; }
  #scroll { overflow:auto; padding:8px 12px 12px; }
  #fields { padding:0; }
  .field-btn {
    display:flex; justify-content:space-between; align-items:baseline; gap:8px; width:100%;
    margin:0 0 6px; padding:8px 10px; text-align:left; cursor:pointer;
    border:1px solid #e0e6ee; border-radius:7px; background:#fff;
  }
  .field-btn:hover { border-color:#9fb0c3; background:#f7f9fc; }
  .field-btn strong { font-size:13px; }
  .field-btn small { font-size:11.5px; color:var(--muted); white-space:nowrap; }
  .leaflet-popup-content { font-size:13px; line-height:1.45; }
  .leaflet-popup-content strong { font-size:14px; }
  .muted { color:var(--muted); }

  /* layer legend */
  .legend { margin-top:14px; }
  .legend h2 {
    margin:0 0 7px; font-size:10.5px; text-transform:uppercase; letter-spacing:.09em;
    color:var(--muted); font-weight:700;
  }
  .legend-field { border:1px solid #e6ebf1; border-radius:7px; margin:0 0 6px; overflow:hidden; }
  .legend-field > summary {
    display:flex; justify-content:space-between; gap:8px; cursor:pointer;
    padding:7px 9px; font-size:12.5px; font-weight:600; list-style:none; background:#fbfcfe;
  }
  .legend-field > summary::-webkit-details-marker { display:none; }
  .legend-field > summary .ac { font-weight:500; color:var(--muted); font-variant-numeric:tabular-nums; }
  .legend-field[open] > summary { border-bottom:1px solid #eef2f7; }
  .legend-row {
    display:grid; grid-template-columns:12px 1fr auto; gap:1px 8px;
    align-items:center; padding:6px 9px; font-size:12px;
  }
  .legend-row + .legend-row { border-top:1px solid #f2f5f9; }
  .legend-row:hover, .legend-row.active { background:#f7f9fc; }
  .swatch {
    width:12px; height:12px; border-radius:3px; border:1px solid rgba(15,23,42,.28);
  }
  .legend-row .name { font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .legend-row .ac { font-variant-numeric:tabular-nums; color:#24303f; }
  .legend-row .meta {
    grid-column:2 / 4; color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums;
  }
  .legend-note { margin:2px 0 0; font-size:11px; color:var(--muted); }

  /* NDVI legend */
  .chips { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:9px; }
  .chips.off { opacity:.55; }
  .chip {
    padding:4px 8px; font-size:11.5px; cursor:pointer; color:#24303f;
    border:1px solid #d4dbe4; border-radius:6px; background:#fff; font-variant-numeric:tabular-nums;
  }
  .chip:hover { border-color:#9fb0c3; }
  .chip[aria-pressed="true"] { background:#24303f; border-color:#24303f; color:#fff; }
  .colorbar { height:11px; border-radius:4px; border:1px solid #d4dbe4; background:__GRADIENT__; }
  .scale {
    display:flex; justify-content:space-between; margin-top:3px;
    font-size:10.5px; color:var(--muted); font-variant-numeric:tabular-nums;
  }
  #ndvi-caption { margin:6px 0 0; font-size:11.5px; color:var(--muted); }
  .leaflet-control-layers { font-size:12.5px; }

  @media (max-width: 640px) {
    #panel { width:calc(100% - 24px); max-height:58%; }
  }
</style>
</head>
<body>
<div id="map" role="application" aria-label="Interactive field map"></div>
<aside id="panel">
  <header>
    <h1>__TITLE__</h1>
    <p>__SUBTITLE__</p>
  </header>
  <div class="actions"><button class="reset" id="reset" type="button">Zoom to all fields</button></div>
  <div id="scroll">
    <div id="fields">__SIDEBAR__</div>
    __LEGEND__
  </div>
</aside>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = __DATA__;
const SOILS = __SOILS__;
const NDVI = __NDVI__;

const map = L.map('map', { zoomControl: true, scrollWheelZoom: true, minZoom: 3, maxZoom: 19 });

function makePane(name, zIndex) {
  const pane = map.createPane(name);
  pane.style.zIndex = String(zIndex);
  pane.classList.add('leaflet-overlay-pane');
  return pane;
}
makePane('ndviPane', 350);
makePane('soilPane', 360);
makePane('boundaryPane', 400);

const satellite = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community' }
).addTo(map);

const streets = L.tileLayer(
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }
);

const fieldLayers = {};
const fieldLayer = L.geoJSON(DATA, {
  pane: 'boundaryPane',
  style: { color: '#ffd23f', weight: 2, fillColor: '#ffd23f', fillOpacity: 0.12 },
  onEachFeature: (feature, layer) => {
    fieldLayers[feature.properties.field_id] = layer;
    layer.bindPopup(feature.properties.popup, { maxWidth: 340 });
    layer.on('mouseover', () => layer.setStyle({ weight: 3.5, fillOpacity: 0.30 }));
    layer.on('mouseout', () => layer.setStyle({ weight: 2, fillOpacity: 0.12 }));
  }
}).addTo(map);

const allBounds = fieldLayer.getBounds();
map.fitBounds(allBounds, { padding: [24, 24] });

/* ---- SSURGO soil map units ---- */
const soilLayers = {};
const defaultSoilStyle = (feature) => ({
  color: '#3f3f46',
  weight: 0.7,
  opacity: 0.85,
  fillColor: feature.properties.color,
  fillOpacity: 0.55
});
const soilLayer = L.geoJSON(SOILS, {
  pane: 'soilPane',
  style: defaultSoilStyle,
  onEachFeature: (feature, layer) => {
    const key = feature.properties.key;
    (soilLayers[key] = soilLayers[key] || []).push(layer);
    layer.bindPopup(feature.properties.popup, { maxWidth: 320 });
    layer.on('mouseover', () => {
      layer.setStyle({ weight: 1.8, fillOpacity: 0.78 });
      setActiveRow(key, true);
    });
    layer.on('mouseout', () => {
      layer.setStyle({ weight: 0.7, fillOpacity: 0.55 });
      setActiveRow(key, false);
    });
  }
});

function setActiveRow(key, on) {
  const el = document.querySelector('.legend-row[data-key="' + CSS.escape(key) + '"]');
  if (!el) return;
  if (on) {
    el.classList.add('active');
    el.scrollIntoView({ block: 'nearest' });
  } else {
    el.classList.remove('active');
  }
}

document.querySelectorAll('.legend-row').forEach((row) => {
  const key = row.dataset.key;
  row.addEventListener('mouseenter', () => {
    (soilLayers[key] || []).forEach((layer) => layer.setStyle({ weight: 1.8, fillOpacity: 0.78 }));
  });
  row.addEventListener('mouseleave', () => {
    (soilLayers[key] || []).forEach((layer) => layer.setStyle({ weight: 0.7, fillOpacity: 0.55 }));
  });
});

/* ---- NDVI overlays, one year at a time ---- */
const ndviGroup = L.layerGroup();
let ndviYear = NDVI.defaultYear;

function ndviCaption(year) {
  const meta = NDVI.yearMeta[String(year)];
  const el = document.getElementById('ndvi-caption');
  if (!el || !meta) return;
  el.textContent = year + ' · ' + meta.label + ' · mean NDVI ' + meta.mean.toFixed(3);
}

function rebuildNdvi() {
  ndviGroup.clearLayers();
  DATA.features.forEach((feature) => {
    const scene = NDVI.scenes[feature.properties.field_id + '::' + ndviYear];
    if (!scene) return;
    ndviGroup.addLayer(
      L.imageOverlay(scene.img, scene.bounds, { pane: 'ndviPane', opacity: 0.9, interactive: false })
    );
  });
  ndviCaption(ndviYear);
}

function setYear(year) {
  ndviYear = Number(year);
  rebuildNdvi();
  document.querySelectorAll('.chip').forEach((chip) => {
    chip.setAttribute('aria-pressed', String(Number(chip.dataset.year) === ndviYear));
  });
  if (NDVI.years.length && !map.hasLayer(ndviGroup)) map.addLayer(ndviGroup);
}

document.querySelectorAll('.chip').forEach((chip) => {
  chip.addEventListener('click', () => setYear(chip.dataset.year));
});

if (NDVI.years.length) {
  rebuildNdvi();
  document.querySelectorAll('.chip').forEach((chip) => {
    chip.setAttribute('aria-pressed', String(Number(chip.dataset.year) === ndviYear));
  });
  map.on('layeradd layerremove', (event) => {
    if (event.layer !== ndviGroup) return;
    document.getElementById('ndvi-chips').classList.toggle('off', !map.hasLayer(ndviGroup));
  });
  document.getElementById('ndvi-chips').classList.add('off');
}

/* ---- layer control ---- */
const overlays = {};
if (SOILS.features.length) overlays['SSURGO soils'] = soilLayer;
if (NDVI.years.length) overlays['NDVI'] = ndviGroup;
overlays['Field boundaries'] = fieldLayer;

L.control.layers(
  { 'Satellite (Esri)': satellite, 'Streets (OSM)': streets },
  overlays,
  { position: 'topright', collapsed: false }
).addTo(map);
L.control.scale({ imperial: true, metric: true }).addTo(map);

/* ---- sidebar field list ---- */
function zoomToAll() {
  map.fitBounds(allBounds, { padding: [24, 24] });
}

document.getElementById('reset').addEventListener('click', zoomToAll);

document.querySelectorAll('.field-btn').forEach((button) => {
  button.addEventListener('click', () => {
    const layer = fieldLayers[button.dataset.field];
    if (!layer) return;
    map.flyToBounds(layer.getBounds().pad(0.35), { maxZoom: 17 });
    layer.openPopup();
  });
});
</script>
</body>
</html>
"""


def _resolve_growers_root(data_root: str | None) -> Path:
    raw = data_root or os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not raw:
        raise SystemExit(
            "DATA_PIPELINE_DATA_ROOT is required (or pass --data-root); "
            "it must point at the runtime root, e.g. ~/my-farm-advisor-runtime"
        )
    root = Path(raw).expanduser()
    candidates = [root / "data-pipeline" / "growers", root / "growers"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"no growers directory under {root} (looked for data-pipeline/growers and growers)")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [
                {str(key): (value or "") for key, value in row.items() if key is not None}
                for row in csv.DictReader(handle)
            ]
    except OSError:
        return []


def _prettify(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-") if part)


def _display_name(manifest: dict[str, Any], slug: str) -> str:
    value = str(manifest.get("display_name") or "").strip()
    if value and value != slug:
        return value
    return _prettify(slug)


def _round_coords(value: Any, digits: int = 6) -> Any:
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    if isinstance(value, (list, tuple)):
        return [_round_coords(item, digits) for item in value]
    return value


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_features(farm_dir: Path) -> list[dict[str, Any]]:
    merged = farm_dir / "boundary" / "field_boundaries.geojson"
    paths: list[Path] = []
    if merged.is_file():
        paths = [merged]
    else:
        paths = sorted((farm_dir / "fields").glob("*/boundary/field_boundary.geojson"))

    features: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        for feature in payload.get("features") or []:
            geometry = feature.get("geometry") or {}
            if not geometry.get("coordinates"):
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": dict(feature.get("properties") or {}),
                    "geometry": {
                        "type": geometry.get("type") or "Polygon",
                        "coordinates": _round_coords(geometry.get("coordinates")),
                    },
                }
            )
    return features


def _field_slug_lookup(farm_dir: Path) -> dict[str, str]:
    rows = _read_csv(farm_dir / "manifests" / "field-inventory.csv")
    return {
        str(row.get("field_id") or "").strip(): str(row.get("field_slug") or "").strip()
        for row in rows
        if str(row.get("field_id") or "").strip() and str(row.get("field_slug") or "").strip()
    }


def _popup_html(properties: dict[str, Any], grower: str, farm: str) -> str:
    field_name = str(properties.get("name") or properties.get("field_id") or "Unnamed field")
    area_acres = _num(properties.get("area_acres"))
    area_ha = _num(properties.get("area_ha_est"))
    if area_acres is None and area_ha is not None:
        area_acres = area_ha * 2.47105
    area = "—"
    if area_acres is not None and area_ha is not None:
        area = f"{area_acres:,.1f} ac ({area_ha:,.1f} ha)"
    elif area_acres is not None:
        area = f"{area_acres:,.1f} ac"

    location = ", ".join(
        part
        for part in (
            str(properties.get("county") or "").strip(),
            str(properties.get("state") or "").strip(),
        )
        if part
    )

    rows = [
        ("Grower", grower),
        ("Farm", farm),
        ("Field", field_name),
        ("Area", area),
    ]
    if properties.get("crop"):
        rows.append(("Crop", str(properties["crop"])))
    if location:
        rows.append(("Location", location))
    if properties.get("source"):
        rows.append(("Boundary source", str(properties["source"])))

    body = "".join(
        f"<div><span class='muted'>{html.escape(label)}:</span> {html.escape(value)}</div>"
        for label, value in rows
    )
    return f"<strong>{html.escape(field_name)}</strong>{body}"


def _soil_popup_html(properties: dict[str, Any]) -> str:
    rows: list[tuple[str, str]] = [("Map unit", str(properties.get("mukey") or "—"))]
    if properties.get("comp_pct") is not None:
        rows.append(("Component", f"{properties['comp_pct']:.0f}% of map unit"))
    if properties.get("drainage"):
        rows.append(("Drainage", str(properties["drainage"])))
    if properties.get("om") is not None:
        rows.append(("Organic matter", f"{properties['om']:.2f}%"))
    if properties.get("ph") is not None:
        rows.append(("pH (1:1 H2O)", f"{properties['ph']:.1f}"))
    if properties.get("awc") is not None:
        rows.append(("AWC (surface)", f"{properties['awc']:.2f} in/in"))
    if properties.get("acres") is not None:
        rows.append(
            (
                "Area",
                f"{properties['acres']:.1f} ac ({properties.get('pct_field', 0):.0f}% of field)",
            )
        )
    body = "".join(
        f"<div><span class='muted'>{html.escape(label)}:</span> {html.escape(value)}</div>"
        for label, value in rows
    )
    series = html.escape(str(properties.get("series") or "Soil map unit"))
    return f"<strong>{series}</strong>{body}"


def _sidebar_html(features: list[dict[str, Any]]) -> str:
    buttons: list[str] = []
    for feature in features:
        properties = feature["properties"]
        field_id = str(properties.get("field_id") or "field")
        label = str(properties.get("name") or field_id)
        area_acres = _num(properties.get("area_acres"))
        area_ha = _num(properties.get("area_ha_est"))
        if area_acres is None and area_ha is not None:
            area_acres = area_ha * 2.47105
        detail = []
        if area_acres is not None:
            detail.append(f"{area_acres:,.0f} ac")
        if properties.get("crop"):
            detail.append(str(properties["crop"]))
        buttons.append(
            "<button class='field-btn' type='button' data-field='{field}'>"
            "<strong>{label}</strong><small>{detail}</small></button>".format(
                field=html.escape(field_id, quote=True),
                label=html.escape(label),
                detail=html.escape(" · ".join(detail)),
            )
        )
    return "".join(buttons)


def _ring_area(ring: list[list[float]]) -> float:
    """Signed shoelace area of one lon/lat ring, in square degrees."""
    total = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = float(ring[index][0]), float(ring[index][1])
        x2, y2 = float(ring[index + 1][0]), float(ring[index + 1][1])
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _geometry_area_acres(geometry: dict[str, Any]) -> float:
    """Area of a lon/lat polygon in acres, corrected for longitude convergence.

    Only relative areas matter here: the per-field totals are normalised to the
    boundary's own ``area_acres`` afterwards, so the small projection error in
    this approximation never reaches the legend.
    """
    coordinates = geometry.get("coordinates") or []
    polygons = [coordinates] if geometry.get("type") == "Polygon" else list(coordinates)
    total = 0.0
    for rings in polygons:
        if not rings:
            continue
        exterior = abs(_ring_area(rings[0]))
        holes = sum(abs(_ring_area(ring)) for ring in rings[1:])
        lats = [float(point[1]) for ring in rings for point in ring]
        if not lats:
            continue
        scale = math.cos(math.radians(sum(lats) / len(lats)))
        total += (exterior - holes) * (M_PER_DEG**2) * scale
    return total * ACRES_PER_SQM


def _component_index(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """mukey -> dominant component plus its surface-horizon properties."""
    by_mukey: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        mukey = str(row.get("mukey") or "").strip()
        if mukey:
            by_mukey[mukey].append(row)

    index: dict[str, dict[str, Any]] = {}
    for mukey, group in by_mukey.items():
        components: dict[str, dict[str, Any]] = {}
        for row in group:
            name = str(row.get("compname") or "").strip() or "Unknown"
            entry = components.setdefault(
                name,
                {"pct": _num(row.get("comppct_r")) or 0.0, "rows": []},
            )
            entry["pct"] = max(entry["pct"], _num(row.get("comppct_r")) or 0.0)
            entry["rows"].append(row)
        if not components:
            continue
        series, component = max(components.items(), key=lambda item: item[1]["pct"])
        surface = min(
            component["rows"],
            key=lambda row: _num(row.get("hzdept_r")) if _num(row.get("hzdept_r")) is not None else 0.0,
        )
        index[mukey] = {
            "series": series,
            "comp_pct": component["pct"],
            "drainage": str(surface.get("drainagecl") or "").strip(),
            "om": _num(surface.get("om_r")),
            "ph": _num(surface.get("ph1to1h2o_r")),
            "awc": _num(surface.get("awc_r")),
        }
    return index


def _soil_payload(
    farm_dir: Path,
    features: list[dict[str, Any]],
    slug_lookup: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    collected: list[dict[str, Any]] = []
    mukeys: set[str] = set()

    for feature in features:
        properties = feature["properties"]
        field_id = str(properties.get("field_id") or "").strip()
        if not field_id:
            continue
        slug = slug_lookup.get(field_id, field_id)
        field_dir = farm_dir / "fields" / slug
        payload = _read_json(field_dir / "soil" / "ssurgo_soil_types.geojson")
        if not payload.get("features"):
            continue
        components = _component_index(_read_csv(field_dir / "soil" / "ssurgo_full.csv"))

        units: list[dict[str, Any]] = []
        for soil_feature in payload.get("features") or []:
            geometry = soil_feature.get("geometry") or {}
            if not geometry.get("coordinates"):
                continue
            mukey = str((soil_feature.get("properties") or {}).get("mukey") or "").strip()
            if not mukey:
                continue
            acres = _geometry_area_acres(geometry)
            if acres <= 0:
                continue
            units.append({"mukey": mukey, "geometry": geometry, "acres": acres})
            mukeys.add(mukey)

        if units:
            collected.append(
                {
                    "field_id": field_id,
                    "label": str(properties.get("name") or field_id),
                    "field_acres": _num(properties.get("area_acres")),
                    "units": units,
                    "components": components,
                }
            )

    colors = {
        mukey: SOIL_PALETTE[index % len(SOIL_PALETTE)]
        for index, mukey in enumerate(sorted(mukeys))
    }

    soil_features: list[dict[str, Any]] = []
    legend: list[dict[str, Any]] = []

    for entry in collected:
        raw_total = sum(unit["acres"] for unit in entry["units"])
        field_acres = entry["field_acres"] or raw_total
        scale = (field_acres / raw_total) if raw_total else 1.0

        grouped: dict[str, dict[str, Any]] = {}
        for unit in entry["units"]:
            acres = unit["acres"] * scale
            bucket = grouped.setdefault(
                unit["mukey"],
                {"acres": 0.0, "geometry": [], "type": "Polygon"},
            )
            bucket["acres"] += acres
            bucket["geometry"].append(unit["geometry"])

        rows: list[dict[str, Any]] = []
        for mukey, bucket in grouped.items():
            info = entry["components"].get(mukey, {})
            shares = list(bucket["geometry"])
            # A clipped soil unit can itself be a MultiPolygon, so flatten one
            # level: GeoJSON MultiPolygon coordinates are a list of polygons,
            # each polygon a list of rings.
            polygons: list[Any] = []
            for share in shares:
                if (share.get("type") or "Polygon") == "MultiPolygon":
                    polygons.extend(share.get("coordinates") or [])
                else:
                    polygons.append(share.get("coordinates") or [])
            if not polygons:
                continue
            geometry = (
                {"type": "Polygon", "coordinates": polygons[0]}
                if len(polygons) == 1
                else {"type": "MultiPolygon", "coordinates": polygons}
            )
            key = f"{entry['field_id']}|{mukey}"
            properties = {
                "key": key,
                "field_id": entry["field_id"],
                "mukey": mukey,
                "series": info.get("series") or "Unknown",
                "comp_pct": info.get("comp_pct"),
                "drainage": info.get("drainage") or "",
                "om": info.get("om"),
                "ph": info.get("ph"),
                "awc": info.get("awc"),
                "acres": round(bucket["acres"], 2),
                "pct_field": round(bucket["acres"] / field_acres * 100.0, 1) if field_acres else 0.0,
                "color": colors.get(mukey, SOIL_PALETTE[0]),
            }
            properties["popup"] = _soil_popup_html(properties)
            soil_features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": geometry.get("type") or "Polygon",
                        "coordinates": _round_coords(geometry.get("coordinates")),
                    },
                }
            )
            rows.append(
                {
                    "key": key,
                    "mukey": mukey,
                    "series": properties["series"],
                    "drainage": properties["drainage"],
                    "acres": properties["acres"],
                    "pct": properties["pct_field"],
                    "color": properties["color"],
                    "trace": properties["acres"] < TRACE_ACRES,
                }
            )

        rows.sort(key=lambda row: row["acres"], reverse=True)
        legend.append(
            {
                "field_id": entry["field_id"],
                "label": entry["label"],
                "acres": round(field_acres, 1),
                "rows": rows,
            }
        )

    return {"type": "FeatureCollection", "features": soil_features}, legend


def _rdylgn_lut():
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy ships with the runtime venv
        return None
    stops = [tuple(int(stop[index : index + 2], 16) for index in (1, 3, 5)) for stop in RDYLGN_STOPS]
    positions = np.linspace(0.0, 1.0, len(stops))
    samples = np.linspace(0.0, 1.0, 256)
    return np.stack(
        [
            np.interp(samples, positions, [stop[channel] for stop in stops])
            for channel in range(3)
        ],
        axis=1,
    ).astype("uint8")


_RDYLGN_LUT = None


def _gradient_css() -> str:
    stops = ", ".join(
        f"{stop} {index / (len(RDYLGN_STOPS) - 1) * 100:.0f}%"
        for index, stop in enumerate(RDYLGN_STOPS)
    )
    return f"linear-gradient(90deg, {stops})"


def _render_ndvi_image(
    path: Path, field_geometry: dict[str, Any] | None = None
) -> tuple[str, list[list[float]], float] | None:
    """Render one NDVI composite to a transparent PNG data URI.

    The composites are clipped to a padded box, not to the field, so the array
    is masked against the boundary here — otherwise the overlay paints the
    neighbouring properties as well.

    Returns ``(data_uri, bounds, mean)`` or ``None`` when the raster is missing,
    unreadable, not in WGS84, or the optional raster stack is unavailable.
    """
    global _RDYLGN_LUT
    try:
        import numpy as np
        import rasterio
        from PIL import Image
        from rasterio.features import rasterize
    except ImportError:
        return None

    try:
        with rasterio.open(path) as dataset:
            if dataset.count < 1:
                return None
            if dataset.crs is not None and str(dataset.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                return None
            data = dataset.read(1).astype("float32")
            bounds = dataset.bounds
            transform = dataset.transform
    except (OSError, ValueError, rasterio.errors.RasterioError):
        return None

    data = np.where(np.isfinite(data), data, np.nan)
    valid = np.isfinite(data)

    if field_geometry:
        try:
            inside = rasterize(
                [(field_geometry, 1)],
                out_shape=data.shape,
                transform=transform,
                fill=0,
                dtype="uint8",
            ).astype(bool)
        except (ValueError, TypeError):
            inside = None
        if inside is not None and inside.any():
            valid &= inside

    if not valid.any():
        return None
    mean = float(np.nanmean(np.where(valid, data, np.nan)))

    if _RDYLGN_LUT is None:
        _RDYLGN_LUT = _rdylgn_lut()
    if _RDYLGN_LUT is None:
        return None

    # 254 colour levels plus index 255 reserved for transparent pixels, so the
    # overlay can be saved as an indexed PNG (about a third the size of RGBA).
    normalised = np.clip((data - NDVI_VMIN) / (NDVI_VMAX - NDVI_VMIN), 0.0, 1.0)
    indices = np.where(valid, normalised * 254.0, 0.0).astype("uint8")
    indices[~valid] = 255

    image = Image.fromarray(indices, "P")
    height, width = indices.shape
    scale = NDVI_MAX_SIDE / max(height, width)
    if scale < 1.0:
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.NEAREST,
        )
    image.putpalette(_RDYLGN_LUT.flatten().tolist())

    buffer = io.BytesIO()
    try:
        image.save(buffer, format="PNG", optimize=True, transparency=bytes([230] * 255 + [0]))
    except (TypeError, ValueError):
        image.convert("RGBA").save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return (
        f"data:image/png;base64,{encoded}",
        [
            [round(bounds.bottom, 7), round(bounds.left, 7)],
            [round(bounds.top, 7), round(bounds.right, 7)],
        ],
        mean,
    )


def _ndvi_payload(
    farm_dir: Path,
    features: list[dict[str, Any]],
    slug_lookup: dict[str, str],
) -> dict[str, Any]:
    scenes: dict[str, dict[str, Any]] = {}
    per_year: dict[int, list[tuple[str, float]]] = defaultdict(list)

    for feature in features:
        properties = feature["properties"]
        field_id = str(properties.get("field_id") or "").strip()
        if not field_id:
            continue
        slug = slug_lookup.get(field_id, field_id)
        field_dir = farm_dir / "fields" / slug

        summary = _read_json(field_dir / "derived" / "summaries" / "ndvi_yearly_summary.json")
        crop_by_year = {
            int(entry["year"]): str(entry.get("crop_name") or "").strip()
            for entry in summary.get("years") or []
            if entry.get("year") is not None
        }

        for path in sorted((field_dir / "derived" / "features").glob("ndvi_year_*_composite.tif")):
            stem = path.stem
            try:
                year = int(stem.split("_")[2])
            except (IndexError, ValueError):
                continue
            rendered = _render_ndvi_image(path, feature["geometry"])
            if rendered is None:
                continue
            data_uri, bounds, mean = rendered
            crop = crop_by_year.get(year, "")
            if not crop or crop.lower() == "unknown":
                crop = ""
            scenes[f"{field_id}::{year}"] = {
                "img": data_uri,
                "bounds": bounds,
                "year": year,
                "field_id": field_id,
                "crop": crop,
                "mean": round(mean, 4),
            }
            per_year[year].append((crop, mean))

    if not scenes:
        return {"years": [], "defaultYear": None, "scenes": {}, "yearMeta": {}}

    year_meta: dict[str, dict[str, Any]] = {}
    for year, entries in sorted(per_year.items()):
        crops = sorted({crop for crop, _ in entries if crop})
        if not crops:
            label = "crop unknown"
        elif len(crops) == 1:
            label = crops[0]
        else:
            label = "mixed crops"
        year_meta[str(year)] = {
            "label": label,
            "mean": sum(mean for _, mean in entries) / len(entries),
        }

    years = sorted(per_year)
    return {
        "years": years,
        "defaultYear": years[-1],
        "scenes": scenes,
        "yearMeta": year_meta,
    }


def _soil_legend_html(legend: list[dict[str, Any]]) -> str:
    if not legend:
        return ""
    parts = ["<section class='legend' id='soil-legend'><h2>Soil map units</h2>"]
    for index, entry in enumerate(legend):
        cap = (
            f"<details class='legend-field'{' open' if index == 0 else ''}>"
            f"<summary><span>{html.escape(entry['label'])}</span>"
            f"<span class='ac'>{entry['acres']:,.1f} ac</span></summary>"
        )
        rows: list[str] = []
        for row in entry["rows"]:
            amount = "trace" if row["trace"] else f"{row['acres']:,.1f} ac"
            share = "&lt;1%" if row["trace"] else f"{row['pct']:.0f}%"
            meta_parts = [row["mukey"]]
            if row["drainage"]:
                meta_parts.append(row["drainage"])
            meta_parts.append(share)
            rows.append(
                f"<div class='legend-row' data-key='{html.escape(row['key'], quote=True)}'>"
                f"<span class='swatch' style='background:{row['color']}'></span>"
                f"<span class='name'>{html.escape(row['series'])}</span>"
                f"<span class='ac'>{amount}</span>"
                f"<span class='meta'>{html.escape(' · '.join(meta_parts))}</span>"
                "</div>"
            )
        parts.append(cap + "".join(rows) + "</details>")
    parts.append(
        "<p class='legend-note'>Trace units cover less than "
        f"{TRACE_ACRES:g} ac. Percentages are of field area.</p>"
    )
    parts.append("</section>")
    return "".join(parts)


def _ndvi_legend_html(ndvi: dict[str, Any]) -> str:
    years = ndvi.get("years") or []
    if not years:
        return ""
    chips = "".join(
        f"<button class='chip' type='button' data-year='{year}' aria-pressed='false'>"
        f"{year}</button>"
        for year in years
    )
    return (
        "<section class='legend' id='ndvi-legend'><h2>NDVI</h2>"
        f"<div class='chips' id='ndvi-chips'>{chips}</div>"
        "<div class='colorbar'></div>"
        f"<div class='scale'><span>{NDVI_VMIN:g}</span><span>0.4</span><span>{NDVI_VMAX:g}</span></div>"
        "<p id='ndvi-caption'></p>"
        "<p class='legend-note'>Yearly NDVI composite per field. "
        "The scale matches the NDVI cards in the farm report.</p>"
        "</section>"
    )


def _render_html(
    *,
    grower_name: str,
    farm_name: str,
    features: list[dict[str, Any]],
    soils: dict[str, Any],
    soil_legend: list[dict[str, Any]],
    ndvi: dict[str, Any],
) -> str:
    payload: list[dict[str, Any]] = []
    total_acres = 0.0
    for feature in features:
        properties = dict(feature["properties"])
        properties["popup"] = _popup_html(properties, grower_name, farm_name)
        area_acres = _num(properties.get("area_acres"))
        if area_acres is None:
            area_ha = _num(properties.get("area_ha_est"))
            area_acres = area_ha * 2.47105 if area_ha is not None else None
        if area_acres is not None:
            total_acres += area_acres
        payload.append({"type": "Feature", "properties": properties, "geometry": feature["geometry"]})

    count = len(payload)
    subtitle_parts = [farm_name, f"{count} field{'s' if count != 1 else ''}"]
    if total_acres:
        subtitle_parts.append(f"{total_acres:,.0f} ac")
    subtitle = " · ".join(subtitle_parts)

    data_json = json.dumps(
        {"type": "FeatureCollection", "features": payload},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    title = f"{grower_name} — {farm_name}"
    document = DEFAULT_HTML
    document = document.replace("__GRADIENT__", _gradient_css())
    document = document.replace("__TITLE__", html.escape(title))
    document = document.replace("__SUBTITLE__", html.escape(subtitle))
    document = document.replace("__SIDEBAR__", _sidebar_html(payload))
    document = document.replace(
        "__LEGEND__", _soil_legend_html(soil_legend) + _ndvi_legend_html(ndvi)
    )
    document = document.replace("__DATA__", data_json)
    document = document.replace(
        "__SOILS__", json.dumps(soils, separators=(",", ":"), ensure_ascii=False)
    )
    document = document.replace(
        "__NDVI__", json.dumps(ndvi, separators=(",", ":"), ensure_ascii=False)
    )
    return document


def build_grower(grower_dir: Path) -> list[Path]:
    grower_slug = grower_dir.name
    grower_name = _display_name(_read_json(grower_dir / "grower.json"), grower_slug)
    written: list[Path] = []

    for farm_dir in sorted(path for path in (grower_dir / "farms").glob("*") if path.is_dir()):
        features = _field_features(farm_dir)
        if not features:
            print(f"skip  {grower_slug}/{farm_dir.name}: no field boundaries found")
            continue
        farm_name = _display_name(_read_json(farm_dir / "farm.json"), farm_dir.name)
        slug_lookup = _field_slug_lookup(farm_dir)

        try:
            soils, soil_legend = _soil_payload(farm_dir, features, slug_lookup)
        except Exception as error:  # noqa: BLE001 - one bad farm must not stop the run
            print(f"warn  {grower_slug}/{farm_dir.name}: soils skipped ({error})", file=sys.stderr)
            soils, soil_legend = {"type": "FeatureCollection", "features": []}, []

        try:
            ndvi = _ndvi_payload(farm_dir, features, slug_lookup)
        except Exception as error:  # noqa: BLE001 - NDVI is optional
            print(f"warn  {grower_slug}/{farm_dir.name}: NDVI skipped ({error})", file=sys.stderr)
            ndvi = {"years": [], "defaultYear": None, "scenes": {}, "yearMeta": {}}

        document = _render_html(
            grower_name=grower_name,
            farm_name=farm_name,
            features=features,
            soils=soils,
            soil_legend=soil_legend,
            ndvi=ndvi,
        )
        output = farm_dir / "derived" / "dashboards" / f"{farm_dir.name}_fields_map.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        print(
            f"map   {grower_slug}/{farm_dir.name}: {len(features)} fields, "
            f"{len(soils.get('features') or [])} soil polygons, "
            f"{len(ndvi.get('years') or [])} NDVI years -> {output}"
        )
        written.append(output)
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--grower-slug", help="Build maps for one grower slug")
    target.add_argument("--all-growers", action="store_true", help="Build maps for every grower")
    parser.add_argument(
        "--data-root",
        default=None,
        help="Runtime root (defaults to DATA_PIPELINE_DATA_ROOT)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    growers_root = _resolve_growers_root(args.data_root)

    if args.grower_slug:
        grower_dirs = [growers_root / args.grower_slug]
        if not grower_dirs[0].is_dir():
            raise SystemExit(f"grower not found: {grower_dirs[0]}")
    else:
        grower_dirs = sorted(path for path in growers_root.glob("*") if path.is_dir())

    written: list[Path] = []
    for grower_dir in grower_dirs:
        written.extend(build_grower(grower_dir))

    if not written:
        print("no maps written", file=sys.stderr)
        return 1
    print(f"\n{len(written)} map(s) written")
    return 0
