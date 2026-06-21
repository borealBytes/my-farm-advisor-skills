#!/usr/bin/env python3
"""Generate interactive grower-level web map with field boundaries, NDVI and SSURGO overlays."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from bootstrap_runtime import ensure_runtime_environment

ensure_runtime_environment()

from lib.paths import farm_boundary_path, farm_derived_dir, farm_tables_dir, field_dir
from lib.runtime_paths import resolve_runtime_paths

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts


def _grower_dir(grower_slug: str) -> Path:
    return _RUNTIME_BASE / "growers" / grower_slug


def _discover_farms(grower_slug: str) -> list[dict[str, str]]:
    grower = _grower_dir(grower_slug)
    farms_dir = grower / "farms"
    if not farms_dir.exists():
        return []
    farms: list[dict[str, str]] = []
    for entry in sorted(farms_dir.iterdir()):
        if entry.is_dir() and (entry / "farm.json").exists():
            meta = json.loads((entry / "farm.json").read_text())
            farms.append({
                "grower_slug": grower_slug,
                "farm_slug": entry.name,
                "farm_name": meta.get("display_name", entry.name),
            })
    return farms


def _load_geojson(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"type": "FeatureCollection", "features": []}


def _load_cdl_composition(tables_dir: Path) -> dict[str, list[dict]]:
    pattern = list(tables_dir.glob("*cdl_*_full_composition.csv"))
    if not pattern:
        return {}
    rows: dict[str, list[dict]] = {}
    with open(pattern[0], newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row["field_id"]
            if fid not in rows:
                rows[fid] = []
            rows[fid].append({
                "year": int(row["year"]),
                "crop": row["crop_name"],
                "pct": round(float(row["pct"]), 1),
            })
    for fid in rows:
        rows[fid].sort(key=lambda r: r["year"])
    return rows


def _load_ndvi_summary(field_path: Path) -> dict | None:
    path = field_path / "derived" / "summaries" / "ndvi_card_summary.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _load_ssurgo_summary(tables_dir: Path) -> dict[str, dict]:
    pattern = list(tables_dir.glob("*ssurgo_summary.csv"))
    if not pattern:
        return {}
    result: dict[str, dict] = {}
    with open(pattern[0], newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["field_id"]] = {
                "avg_om_pct": _safe_float(row.get("avg_om_pct")),
                "avg_ph": _safe_float(row.get("avg_ph")),
                "avg_clay_pct": _safe_float(row.get("avg_clay_pct")),
                "avg_sand_pct": _safe_float(row.get("avg_sand_pct")),
                "drainage_class": row.get("drainage_class", ""),
                "dominant_soil": row.get("dominant_soil", ""),
            }
    return result


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _build_field_collection(farms: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    features: list[dict] = []
    data: dict[str, dict] = {}
    for farm in farms:
        gs = farm["grower_slug"]
        fs = farm["farm_slug"]
        boundary = _load_geojson(farm_boundary_path(gs, fs))
        tables_dir = farm_tables_dir(gs, fs)
        cdl = _load_cdl_composition(tables_dir)
        ssurgo = _load_ssurgo_summary(tables_dir)
        for feat in boundary.get("features", []):
            props = feat.get("properties", {})
            fid = props.get("field_id", "")
            if not fid:
                continue
            field_path = field_dir(gs, fs, fid)
            ndvi = _load_ndvi_summary(field_path)
            crop_years = cdl.get(fid, [])
            ndvi_peak = None
            if ndvi and "cards" in ndvi:
                for card_key, card_val in ndvi["cards"].items():
                    if "peak_95" in card_key and card_val.get("mean_ndvi") is not None:
                        ndvi_peak = card_val["mean_ndvi"]
                        break
            merged = {
                **props,
                "farm_name": farm["farm_name"],
                "farm_slug": fs,
                "grower_slug": gs,
                "crop_years": crop_years,
                "ndvi_peak": ndvi_peak,
                "ssurgo": ssurgo.get(fid, {}),
            }
            data[fid] = merged
            feat["properties"] = merged
            features.append(feat)
    return features, data


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ height: 100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  #wrapper {{ display: flex; height: 100%; }}
  #sidebar {{ width: 300px; min-width: 300px; background: #f8f9fa; border-right: 1px solid #dee2e6; display: flex; flex-direction: column; overflow: hidden; }}
  #sidebar h2 {{ font-size: 16px; padding: 14px 16px 8px; color: #1a1a2e; }}
  #sidebar p {{ font-size: 12px; padding: 0 16px 8px; color: #6c757d; }}
  #field-list {{ flex: 1; overflow-y: auto; padding: 4px 8px; }}
  .field-item {{ display: flex; align-items: center; justify-content: space-between; padding: 6px 8px; margin: 2px 0; border-radius: 4px; cursor: pointer; font-size: 13px; }}
  .field-item:hover {{ background: #e9ecef; }}
  .field-item .name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .field-item .zoom-btn {{ background: #0d6efd; color: #fff; border: none; border-radius: 3px; padding: 2px 8px; font-size: 11px; cursor: pointer; }}
  .field-item .zoom-btn:hover {{ background: #0b5ed7; }}
  #controls {{ padding: 10px 16px; border-top: 1px solid #dee2e6; background: #fff; }}
  #controls label {{ display: block; font-size: 12px; font-weight: 600; margin: 4px 0; }}
  #controls select, #controls .layer-btn {{ width: 100%; padding: 5px 8px; font-size: 12px; border: 1px solid #ced4da; border-radius: 3px; }}
  .layer-group {{ display: flex; gap: 4px; margin: 6px 0; }}
  .layer-btn {{ flex: 1; padding: 5px 4px; font-size: 11px; border: 1px solid #ced4da; background: #fff; border-radius: 3px; cursor: pointer; text-align: center; }}
  .layer-btn.active {{ background: #0d6efd; color: #fff; border-color: #0d6efd; }}
  .layer-btn:hover:not(.active) {{ background: #e9ecef; }}
  #legend {{ margin-top: 6px; font-size: 11px; display: none; }}
  #legend-bar {{ height: 12px; border-radius: 2px; margin: 4px 0; }}
  #legend-labels {{ display: flex; justify-content: space-between; font-size: 10px; color: #6c757d; }}
  #map {{ flex: 1; }}
</style>
</head>
<body>
<div id="wrapper">
  <div id="sidebar">
    <h2>{title}</h2>
    <p>{field_count} fields across {farm_count} farm(s)</p>
    <div id="field-list"></div>
    <div id="controls">
      <label>Map Layer</label>
      <div class="layer-group">
        <button class="layer-btn active" data-layer="boundaries">Boundaries</button>
        <button class="layer-btn" data-layer="ndvi">NDVI</button>
        <button class="layer-btn" data-layer="ssurgo">SSURGO</button>
      </div>
      <label>SSURGO Property</label>
      <select id="ssurgo-prop">
        <option value="avg_om_pct">Organic Matter %</option>
        <option value="avg_ph">pH</option>
        <option value="avg_clay_pct">Clay %</option>
        <option value="avg_sand_pct">Sand %</option>
        <option value="drainage_class">Drainage Class</option>
        <option value="dominant_soil">Dominant Soil</option>
      </select>
      <div id="legend"></div>
    </div>
  </div>
  <div id="map"></div>
</div>
<script>
const GROUPS = {groups_json};
const FIELDS = {fields_json};
const FARMS = {farms_json};

const map = L.map('map');
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19, attribution: '&copy; <a href="https://openstreetmap.org/copyright">OSM</a>'
}}).addTo(map);

const colors = ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00','#ffff33','#a65628','#f781bf'];
const farmColors = {{}};
FARMS.forEach((f, i) => {{ farmColors[f.farm_slug] = colors[i % colors.length]; }});

const geojsonLayer = L.geoJSON(FIELDS, {{
  style: feature => ({{
    fillColor: farmColors[feature.properties.farm_slug] || '#3388ff',
    fillOpacity: 0.2,
    color: '#333',
    weight: 1.5,
  }}),
  onEachFeature: (feature, layer) => {{
    const p = feature.properties;
    layer.bindPopup(buildPopup(p));
    layer.fieldId = p.field_id;
  }}
}}).addTo(map);

map.fitBounds(geojsonLayer.getBounds().pad(0.05));

function buildPopup(p) {{
  let html = `<b>Field:</b> ${{p.field_id}}<br><b>Farm:</b> ${{p.farm_name}}<br><b>Grower:</b> ${{p.grower_slug}}<br><b>Area:</b> ${{p.area_acres?.toFixed(1) || '?'}} acres<br><b>County:</b> ${{p.county_name || '?'}}`;
  if (p.crop_years && p.crop_years.length) {{
    const byYear = {{}};
    p.crop_years.forEach(c => {{ if (!byYear[c.year]) byYear[c.year] = []; byYear[c.year].push(c); }});
    const years = Object.keys(byYear).sort().reverse();
    html += '<br><br><b>Crop History:</b><br>';
    years.forEach(y => {{
      const items = byYear[y].sort((a,b) => b.pct - a.pct);
      html += `${{y}}: ${{items.map(i => `${{i.crop}} (${{i.pct}}%)`).join(', ')}}<br>`;
    }});
  }}
  if (p.ssurgo && p.ssurgo.dominant_soil) {{
    html += `<br><b>Soil:</b> ${{p.ssurgo.dominant_soil}}`;
  }}
  return html;
}}

function buildSidebar() {{
  const list = document.getElementById('field-list');
  FIELDS.features.forEach(f => {{
    const p = f.properties;
    const div = document.createElement('div');
    div.className = 'field-item';
    div.innerHTML = `<span class="name">${{p.field_id}}</span><button class="zoom-btn">Zoom</button>`;
    div.querySelector('.zoom-btn').onclick = () => zoomToField(p.field_id);
    div.onclick = () => zoomToField(p.field_id);
    list.appendChild(div);
  }});
}}

function zoomToField(fid) {{
  geojsonLayer.eachLayer(l => {{
    if (l.fieldId === fid) {{
      map.fitBounds(l.getBounds().pad(0.3));
      l.openPopup();
    }}
  }});
}}

const SSURGO_PROPS = ['avg_om_pct', 'avg_ph', 'avg_clay_pct', 'avg_sand_pct'];

function getNumericRange(prop) {{
  let min = Infinity, max = -Infinity;
  FIELDS.features.forEach(f => {{
    const v = f.properties.ssurgo?.[prop];
    if (v != null && typeof v === 'number') {{ min = Math.min(min, v); max = Math.max(max, v); }}
  }});
  return min === Infinity ? null : {{ min, max }};
}}

const DRAINAGE_ORDER = ['excessively drained', 'somewhat excessively drained', 'well drained', 'moderately well drained', 'somewhat poorly drained', 'poorly drained', 'very poorly drained'];
const DRAINAGE_COLORS = ['#8B4513', '#A0522D', '#D2B48C', '#90EE90', '#FFD700', '#FF8C00', '#8B0000'];

function styleField(feature, layerName) {{
  const p = feature.properties;
  if (layerName === 'boundaries') {{
    return {{ fillColor: farmColors[p.farm_slug] || '#3388ff', fillOpacity: 0.2, color: '#333', weight: 1.5 }};
  }}
  if (layerName === 'ndvi') {{
    const v = p.ndvi_peak;
    if (v == null) return {{ fillColor: '#ccc', fillOpacity: 0.3, color: '#999', weight: 1 }};
    const r = Math.round(255 * (1 - v));
    const g = Math.round(255 * v);
    return {{ fillColor: `rgb(${{r}},${{g}},0)`, fillOpacity: 0.6, color: '#333', weight: 1 }};
  }}
  if (layerName === 'ssurgo') {{
    const prop = document.getElementById('ssurgo-prop').value;
    const s = p.ssurgo || {{}};
    if (prop === 'drainage_class') {{
      const idx = DRAINAGE_ORDER.indexOf((s[prop] || '').toLowerCase());
      return {{ fillColor: idx >= 0 ? DRAINAGE_COLORS[idx] : '#ccc', fillOpacity: 0.5, color: '#333', weight: 1 }};
    }}
    if (prop === 'dominant_soil') {{
      return {{ fillColor: farmColors[p.farm_slug] || '#3388ff', fillOpacity: 0.3, color: '#333', weight: 1 }};
    }}
    const v = s[prop];
    if (v == null) return {{ fillColor: '#ccc', fillOpacity: 0.3, color: '#999', weight: 1 }};
    const range = getNumericRange(prop);
    if (!range || range.max === range.min) return {{ fillColor: '#3388ff', fillOpacity: 0.4, color: '#333', weight: 1 }};
    const t = (v - range.min) / (range.max - range.min);
    const r = Math.round(245 * (1 - t) + 10);
    const g = Math.round(175 * (1 - t) + 130);
    const b = Math.round(50 * (1 - t) + 180);
    return {{ fillColor: `rgb(${{r}},${{g}},${{b}})`, fillOpacity: 0.6, color: '#333', weight: 1 }};
  }}
  return {{ fillColor: '#3388ff', fillOpacity: 0.2, color: '#333', weight: 1.5 }};
}}

function updateLegend(layerName) {{
  const legend = document.getElementById('legend');
  if (layerName === 'boundaries') {{ legend.style.display = 'none'; return; }}
  legend.style.display = 'block';
  if (layerName === 'ndvi') {{
    legend.innerHTML = '<b>NDVI (Peak 95th %ile)</b><div id="legend-bar" style="background:linear-gradient(to right,rgb(255,0,0),rgb(255,255,0),rgb(0,255,0))"></div><div id="legend-labels"><span>0.0</span><span>0.5</span><span>1.0</span></div>';
    return;
  }}
  if (layerName === 'ssurgo') {{
    const prop = document.getElementById('ssurgo-prop').value;
    if (prop === 'drainage_class') {{
      legend.innerHTML = '<b>Drainage Class</b>' + DRAINAGE_ORDER.map((d, i) => `<div><span style="display:inline-block;width:12px;height:12px;background:${{DRAINAGE_COLORS[i]}};margin-right:4px;vertical-align:middle"></span>${{d}}</div>`).join('');
      return;
    }}
    if (prop === 'dominant_soil') {{
      const uniq = new Set();
      FIELDS.features.forEach(f => {{ const s = f.properties.ssurgo?.dominant_soil; if (s) uniq.add(s); }});
      legend.innerHTML = '<b>Dominant Soil</b><div style="font-size:11px;margin-top:4px">' + [...uniq].map(d => `<div>${{d}}</div>`).join('') + '</div>';
      return;
    }}
    const range = getNumericRange(prop);
    if (!range) {{ legend.style.display = 'none'; return; }}
    const labels = {{
      'avg_om_pct': 'Organic Matter %',
      'avg_ph': 'pH',
      'avg_clay_pct': 'Clay %',
      'avg_sand_pct': 'Sand %',
    }};
    const bar = `linear-gradient(to right,rgb(10,130,180),rgb(130,175,50),rgb(245,175,50))`;
    legend.innerHTML = `<b>${{labels[prop] || prop}}</b><div id="legend-bar" style="background:${{bar}}"></div><div id="legend-labels"><span>${{range.min.toFixed(1)}}</span><span>${{range.max.toFixed(1)}}</span></div>`;
  }}
}}

function setLayer(layerName) {{
  document.querySelectorAll('.layer-btn').forEach(b => b.classList.toggle('active', b.dataset.layer === layerName));
  const showSsurgoProp = layerName === 'ssurgo';
  document.getElementById('ssurgo-prop').style.display = showSsurgoProp ? 'block' : 'none';
  geojsonLayer.eachLayer(l => {{
    l.setStyle(styleField(l.feature, layerName));
  }});
  updateLegend(layerName);
}}

document.querySelectorAll('.layer-btn').forEach(btn => {{
  btn.onclick = () => setLayer(btn.dataset.layer);
}});

document.getElementById('ssurgo-prop').onchange = () => {{
  setLayer('ssurgo');
}};

buildSidebar();
</script>
</body>
</html>"""


def generate_map(grower_slug: str, output: Path | None = None) -> Path:
    farms = _discover_farms(grower_slug)
    if not farms:
        print(f"No farms found for grower '{grower_slug}'", file=sys.stderr)
        raise SystemExit(1)

    features, data = _build_field_collection(farms)
    fc = {"type": "FeatureCollection", "features": features}

    farm_list = [
        {"farm_slug": f["farm_slug"], "farm_name": f["farm_name"]} for f in farms
    ]

    groups = {}
    for f in farms:
        slug = f["farm_slug"]
        g_fields = [feat["properties"]["field_id"] for feat in features if feat["properties"]["farm_slug"] == slug]
        groups[slug] = {"farm_name": f["farm_name"], "fields": g_fields}

    field_count = len(features)
    farm_count = len(farms)
    title = f"{grower_slug} — Grower Web Map"

    html = _HTML_TEMPLATE.replace("{{", "{").replace("}}", "}")
    html = html.replace("{title}", title)
    html = html.replace("{field_count}", str(field_count))
    html = html.replace("{farm_count}", str(farm_count))
    html = html.replace("{groups_json}", json.dumps(groups))
    html = html.replace("{fields_json}", json.dumps(fc))
    html = html.replace("{farms_json}", json.dumps(farm_list))

    if output is None:
        grower = _grower_dir(grower_slug)
        dashboards = grower / "dashboards"
        dashboards.mkdir(parents=True, exist_ok=True)
        output = dashboards / "grower_web_map.html"

    output.write_text(html, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate interactive grower-level web map"
    )
    parser.add_argument("--grower-slug", required=True, help="Grower slug")
    parser.add_argument("--output", default=None, help="Output HTML path")
    args = parser.parse_args()

    out = generate_map(args.grower_slug, Path(args.output) if args.output else None)
    size_kb = out.stat().st_size / 1024
    print(f"Written {size_kb:.0f} KB to {out}")


if __name__ == "__main__":
    main()
