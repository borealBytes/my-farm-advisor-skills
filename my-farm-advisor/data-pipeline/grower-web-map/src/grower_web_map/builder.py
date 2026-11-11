"""Build lightweight per-farm interactive field maps for existing growers."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root { --ink:#1b2430; --panel:#ffffff; --accent:#ffd23f; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--ink); }
  #map { position:absolute; inset:0; background:#e9eef3; }
  #panel {
    position:absolute; z-index:1000; top:12px; left:12px; width:290px; max-height:calc(100% - 24px);
    display:flex; flex-direction:column; background:var(--panel); border-radius:10px;
    box-shadow:0 6px 24px rgba(16,24,40,.22); overflow:hidden;
  }
  #panel header { padding:14px 16px 10px; border-bottom:1px solid #e6ebf1; }
  #panel h1 { margin:0; font-size:17px; line-height:1.25; }
  #panel p { margin:4px 0 0; font-size:12.5px; color:#5b6776; }
  #panel .actions { padding:10px 12px 4px; }
  #panel button.reset {
    width:100%; padding:7px 10px; font-size:12.5px; cursor:pointer;
    border:1px solid #d4dbe4; border-radius:7px; background:#f7f9fc; color:#24303f;
  }
  #panel button.reset:hover { background:#eef2f7; }
  #fields { overflow:auto; padding:8px 12px 12px; }
  .field-btn {
    display:flex; justify-content:space-between; align-items:baseline; gap:8px; width:100%;
    margin:0 0 6px; padding:8px 10px; text-align:left; cursor:pointer;
    border:1px solid #e0e6ee; border-radius:7px; background:#fff;
  }
  .field-btn:hover { border-color:#9fb0c3; background:#f7f9fc; }
  .field-btn strong { font-size:13px; }
  .field-btn small { font-size:11.5px; color:#5b6776; white-space:nowrap; }
  .leaflet-popup-content { font-size:13px; line-height:1.45; }
  .leaflet-popup-content strong { font-size:14px; }
  .muted { color:#5b6776; }
  @media (max-width: 640px) {
    #panel { width:calc(100% - 24px); max-height:46%; }
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
  <div id="fields">__SIDEBAR__</div>
</aside>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = __DATA__;
const map = L.map('map', { zoomControl: true, scrollWheelZoom: true, minZoom: 3, maxZoom: 19 });

const satellite = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community' }
).addTo(map);

const streets = L.tileLayer(
  'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }
);

L.control.layers({ 'Satellite (Esri)': satellite, 'Streets (OSM)': streets }, null, { position: 'topright' }).addTo(map);
L.control.scale({ imperial: true, metric: true }).addTo(map);

const fieldLayers = {};
const fieldLayer = L.geoJSON(DATA, {
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


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _render_html(
    *,
    grower_name: str,
    farm_name: str,
    features: list[dict[str, Any]],
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
    sidebar = _sidebar_html(payload)
    title = f"{grower_name} — {farm_name}"
    document = DEFAULT_HTML
    document = document.replace("__TITLE__", html.escape(title))
    document = document.replace("__SUBTITLE__", html.escape(subtitle))
    document = document.replace("__SIDEBAR__", sidebar)
    document = document.replace("__DATA__", data_json)
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
        document = _render_html(
            grower_name=grower_name,
            farm_name=farm_name,
            features=features,
        )
        output = farm_dir / "derived" / "dashboards" / f"{farm_dir.name}_fields_map.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        print(f"map   {grower_slug}/{farm_dir.name}: {len(features)} fields -> {output}")
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
