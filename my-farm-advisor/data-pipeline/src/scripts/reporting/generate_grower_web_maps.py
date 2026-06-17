#!/usr/bin/env python3
"""Generate one lightweight interactive HTML web map per grower.

Scans the runtime grower tree and produces a self-contained Leaflet map
with switchable data layers:

  - NDVI (default)  – spatial raster overlay from yearly composite TIFs
  - Crop History    – field polygons colored by CDL dominant crop
  - pH Map          – SSURGO soil polygons colored by surface pH (if available)
  - Boundaries      – farm-colored field boundaries
"""

from __future__ import annotations

import base64
import csv
import io
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import DATA_ROOT, GROWERS_ROOT, farm_boundary_path, farm_reports_dir  # noqa: E402

FARM_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9a6324", "#800000", "#aaffc3",
]

CROP_COLORS: dict[str, str] = {
    "Corn": "#2E7D32",
    "Soybeans": "#F9A825",
    "Wheat": "#E65100",
    "Cotton": "#1565C0",
    "Rice": "#00ACC1",
    "Grass/Pasture": "#A5D6A7",
    "Alfalfa": "#66BB6A",
}

YEARS = [2021, 2022, 2023, 2024, 2025]


def _discover_growers() -> list[dict]:
    growers: list[dict] = []
    for grower_dir in sorted(GROWERS_ROOT.glob("*")):
        if not grower_dir.is_dir():
            continue
        g_slug = grower_dir.name
        farms: list[dict] = []
        farm_dir_path = grower_dir / "farms"
        if not farm_dir_path.is_dir():
            continue
        for farm_dir in sorted(farm_dir_path.glob("*")):
            if not farm_dir.is_dir():
                continue
            f_slug = farm_dir.name
            boundary = farm_boundary_path(g_slug, f_slug)
            if not boundary.exists():
                continue
            gdf = gpd.read_file(boundary)
            farms.append({"farm_slug": f_slug, "boundary_path": boundary, "gdf": gdf})
        if farms:
            growers.append({"grower_slug": g_slug, "farms": farms})
    return growers


def _build_field_list(grower_slug: str, farms: list[dict]) -> list[dict]:
    fields: list[dict] = []
    for farm in farms:
        gdf = farm["gdf"]
        if "field_id" not in gdf.columns:
            continue
        for _, row in gdf.iterrows():
            fields.append({
                "grower_slug": grower_slug,
                "farm_slug": farm["farm_slug"],
                "field_id": str(row.get("field_id", "")),
                "area_acres": float(row.get("area_acres", 0)),
                "county_name": str(row.get("county_name", "")),
                "crop_name": str(row.get("crop_name", "")),
            })
    return fields


def _grower_center(farms: list[dict]) -> tuple[float, float]:
    lats, lons = [], []
    for farm in farms:
        bounds = farm["gdf"].total_bounds
        lats.extend([bounds[1], bounds[3]])
        lons.extend([bounds[0], bounds[2]])
    if not lats:
        return 40.0, -95.0
    return (min(lats) + max(lats)) / 2.0, (min(lons) + max(lons)) / 2.0


# ── NDVI spatial raster overlay ──────────────────────────────────

def _render_ndvi_overlay(farms: list[dict], g_slug: str) -> dict:
    """Render yearly NDVI composites to colored PNGs for each field.

    Returns a dict keyed by field_id → {year: {bounds: [s,w,n,e], data_b64: str}}
    """
    result: dict[str, dict[int, dict]] = {}
    cmap = plt.colormaps["RdYlGn"]
    for farm in farms:
        f_slug = farm["farm_slug"]
        gdf = farm["gdf"]
        for _, row in gdf.iterrows():
            fid = str(row.get("field_id", ""))
            if not fid:
                continue
            result.setdefault(fid, {})
            for year in YEARS:
                composite = (
                    DATA_ROOT / "growers" / g_slug / "farms" / f_slug
                    / "fields" / fid / "derived" / "features"
                    / f"ndvi_year_{year}_composite.tif"
                )
                if not composite.exists():
                    continue
                try:
                    with rasterio.open(composite) as src:
                        data = src.read(1).astype(np.float32)
                        bounds = src.bounds
                        nodata = src.nodata if src.nodata is not None else -9999
                        mask = np.isnan(data) if np.isnan(nodata) else (data == nodata)
                        valid = data[~mask]
                        if valid.size == 0:
                            continue
                        vmin, vmax = float(np.percentile(valid, 2)), float(np.percentile(valid, 98))
                        if vmax - vmin < 0.01:
                            vmin, vmax = 0.0, 1.0
                        normed = np.ma.masked_where(mask, data)
                        rendered = cmap((normed - vmin) / (vmax - vmin))
                        rendered = (rendered[:, :, :3] * 255).astype(np.uint8)
                        rendered[mask] = 0
                        buf = io.BytesIO()
                        plt.imsave(buf, rendered, format="png")
                        b64 = base64.b64encode(buf.getvalue()).decode()
                        result[fid][year] = {
                            "bounds": [bounds.bottom, bounds.left, bounds.top, bounds.right],
                            "b64": b64,
                        }
                except Exception:
                    pass
    return result


# ── Crop history layer ──────────────────────────────────────────

def _load_crop_data(g_slug: str, farms: list[dict]) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = {}
    for farm in farms:
        f_slug = farm["farm_slug"]
        tables_dir = DATA_ROOT / "growers" / g_slug / "farms" / f_slug / "derived" / "tables"
        comp_paths = sorted(tables_dir.glob("*cdl*composition*")) if tables_dir.exists() else []
        comp_path = comp_paths[0] if comp_paths else None
        if comp_path and comp_path.exists():
            with comp_path.open() as f:
                for row in csv.DictReader(f):
                    fid = row.get("field_id", "")
                    try:
                        year = int(row.get("year", 0))
                    except ValueError:
                        continue
                    cname = row.get("crop_name", "")
                    if fid and year and cname:
                        result.setdefault(fid, {})[year] = cname
        for _, row in farm["gdf"].iterrows():
            fid = str(row.get("field_id", ""))
            if fid and fid not in result:
                result[fid] = {}
    return result


# ── pH spatial layer ────────────────────────────────────────────

def _load_ph_map(g_slug: str, farms: list[dict]) -> tuple[dict[str, dict], str | None]:
    """Build a pH-colored GeoJSON from SSURGO polygons + soil CSV.

    Returns (geojson_dict, overlay_bounds_json) or ({}, None) if no data.
    """
    soil_csv_paths: list[Path] = []
    for farm in farms:
        td = DATA_ROOT / "growers" / g_slug / "farms" / farm["farm_slug"] / "derived" / "tables"
        if td.exists():
            soil_csv_paths.extend(sorted(td.glob("*fields_soil*")))
    if not soil_csv_paths:
        return {}, None

    soil_csv = soil_csv_paths[0]
    soil_df = pd.read_csv(soil_csv)
    surface = soil_df[soil_df["hzdept_r"] == 0].copy()
    if surface.empty:
        surface = soil_df.loc[soil_df.groupby("field_id")["hzdept_r"].idxmin()]

    ph_lookup: dict[str, dict] = {}
    for _, row in surface.iterrows():
        fid = str(row.get("field_id", ""))
        mukey = str(row.get("mukey", ""))
        if fid and mukey:
            try:
                ph = round(float(row["ph1to1h2o_r"]), 1)
            except (ValueError, TypeError):
                ph = None
            ph_lookup[(fid, mukey)] = ph

    all_features: list[dict] = []
    bounds_list: list[float] = []
    for farm in farms:
        f_slug = farm["farm_slug"]
        gdf = farm["gdf"]
        for _, frow in gdf.iterrows():
            fid = str(frow.get("field_id", ""))
            if not fid:
                continue
            ssurgo = (
                DATA_ROOT / "growers" / g_slug / "farms" / f_slug
                / "fields" / fid / "soil" / "ssurgo_soil_types.geojson"
            )
            if not ssurgo.exists():
                continue
            try:
                sgdf = gpd.read_file(ssurgo)
            except Exception:
                continue
            for _, srow in sgdf.iterrows():
                mukey = str(srow.get("mukey", ""))
                ph = ph_lookup.get((fid, mukey))
                geom_json = json.loads(gpd.GeoSeries([srow.geometry]).to_json())["features"][0]["geometry"]
                feat = {
                    "type": "Feature",
                    "properties": {"mukey": mukey, "ph": ph, "field_id": fid},
                    "geometry": geom_json,
                }
                all_features.append(feat)
                b = srow.geometry.bounds
                bounds_list.extend([b[1], b[0], b[3], b[2]])

    if not all_features:
        return {}, None

    collection = {"type": "FeatureCollection", "features": all_features}
    return collection, json.dumps(collection)


# ── HTML generation ─────────────────────────────────────────────

def _generate_html(
    grower_slug: str,
    farms: list[dict],
    field_list: list[dict],
    center_lat: float,
    center_lon: float,
    ndvi_overlays: dict,
    crop_data: dict[str, dict[int, str]],
    ph_geojson: dict | None,
    ph_geojson_str: str | None,
) -> str:
    features: list[dict] = []
    for idx, farm in enumerate(farms):
        geojson = json.loads(farm["gdf"].to_json())
        for feat in geojson.get("features", []):
            feat["properties"]["_farm_slug"] = farm["farm_slug"]
            feat["properties"]["_farm_color"] = FARM_COLORS[idx % len(FARM_COLORS)]
            features.append(feat)

    collection = {"type": "FeatureCollection", "features": features}
    geojson_str = json.dumps(collection)
    fields_json = json.dumps(field_list)
    ndvi_json = json.dumps(ndvi_overlays)
    crop_json = json.dumps(crop_data)
    years_json = json.dumps(YEARS)
    has_ph = ph_geojson_str is not None
    ph_json = ph_geojson_str or "null"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{grower_slug} — Field Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; display:flex; height:100vh; }}
#sidebar {{ width:320px; min-width:320px; background:#f8f9fa; border-right:1px solid #ddd; display:flex; flex-direction:column; }}
#sidebar h1 {{ font-size:1.1em; padding:12px 14px; background:#2c3e50; color:#fff; margin:0; }}
#sidebar h1 small {{ font-weight:400; font-size:0.75em; opacity:.8; display:block; }}
.controls {{ padding:10px 14px; background:#fff; border-bottom:1px solid #ddd; }}
.controls label {{ font-size:.8em; font-weight:600; color:#555; display:block; margin-top:6px; }}
.controls select, .controls .layer-opts {{ width:100%; margin-top:3px; font-size:.85em; padding:4px 6px; border:1px solid #ccc; border-radius:3px; }}
.controls .layer-opts label {{ font-weight:400; font-size:.8em; display:block; margin:2px 0; cursor:pointer; }}
.controls .layer-opts input {{ margin-right:4px; }}
#legend {{ padding:6px 14px; background:#fff; border-bottom:1px solid #ddd; font-size:.78em; }}
#legend .bar {{ height:10px; border-radius:3px; margin:4px 0; }}
#legend .lbl {{ display:flex; justify-content:space-between; color:#666; }}
#legend .crop-item {{ display:flex; align-items:center; gap:6px; margin:2px 0; }}
#legend .crop-swatch {{ width:14px; height:14px; border-radius:2px; border:1px solid #999; }}
#legend .ph-bar {{ height:10px; border-radius:3px; margin:4px 0; }}
#field-list {{ flex:1; overflow-y:auto; padding:8px; }}
.field-item {{ padding:8px 10px; margin:4px 0; background:#fff; border-radius:4px; cursor:pointer; border-left:4px solid #999; transition:background .15s; font-size:.85em; }}
.field-item:hover {{ background:#eef; }}
.field-item .farm-label {{ font-size:.75em; color:#666; }}
#fit-btn {{ margin:8px; padding:8px; background:#3498db; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:.85em; }}
#fit-btn:hover {{ background:#2980b9; }}
#map {{ flex:1; }}
.popup-table {{ font-size:.8em; border-collapse:collapse; }}
.popup-table td {{ padding:2px 6px; }}
.popup-table td:first-child {{ font-weight:600; color:#555; }}
</style>
</head>
<body>
<div id="sidebar">
<h1>{grower_slug}<small>{len(field_list)} field{'s' if len(field_list)!=1 else ''} across {len(farms)} farm{'s' if len(farms)!=1 else ''}</small></h1>
<div class="controls">
<label>Layer</label>
<div class="layer-opts">
<label><input type="radio" name="layer" value="ndvi" checked onchange="setLayer('ndvi')"> NDVI</label>
<label><input type="radio" name="layer" value="crop" onchange="setLayer('crop')"> Crop History</label>
{"<label><input type=\"radio\" name=\"layer\" value=\"ph\" onchange=\"setLayer('ph')\"> pH Map</label>" if has_ph else ""}
<label><input type="radio" name="layer" value="boundaries" onchange="setLayer('boundaries')"> Boundaries</label>
</div>
<label>Year</label>
<select id="year-select" onchange="setYear(this.value)"></select>
</div>
<div id="legend"></div>
<button id="fit-btn">&#8634; Fit all fields</button>
<div id="field-list"></div>
</div>
<div id="map"></div>
<script>
var fieldData = {geojson_str};
var fieldList = {fields_json};
var ndviOverlays = {ndvi_json};
var cropData = {crop_json};
var phData = {ph_json};
var years = {years_json};
var currentYear = years[years.length-1];
var currentLayer = 'ndvi';
var phLayer = null;

var map = L.map('map', {{zoomControl:true}}).setView([{center_lat},{center_lon}], 10);
var satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution:'&copy; Esri, Maxar, Earthstar Geographics', maxZoom:19
}}).addTo(map);
var streets = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution:'&copy; OpenStreetMap contributors', maxZoom:19
}});
L.control.layers({{'Satellite': satellite, 'Streets': streets}}).addTo(map);

function phColor(ph) {{
  if (ph === null || ph === undefined) return '#ccc';
  if (ph < 5.5) return '#d73027';
  if (ph < 6.0) return '#fc8d59';
  if (ph < 6.5) return '#fee08b';
  if (ph < 7.0) return '#d9ef8b';
  if (ph < 7.5) return '#91cf60';
  return '#1a9850';
}}

function defaultStyle(feature) {{
  return {{ color: feature.properties._farm_color, weight:2, fillOpacity:0.2 }};
}}

function cropStyle(feature, year) {{
  var fid = feature.properties.field_id;
  var crop = cropData[fid] && cropData[fid][year];
  var c = cropColors[crop] || '#999';
  return {{ color: '#333', weight:1, fillColor: c, fillOpacity:0.7 }};
}}

var cropColors = {json.dumps(CROP_COLORS)};

var fieldLayer = L.geoJSON(fieldData, {{
  style: function(feature) {{ return defaultStyle(feature); }},
  onEachFeature: function(feature, layer) {{
    layer.on('click', function() {{ updatePopup(feature, layer); }});
  }}
}}).addTo(map);
map.fitBounds(fieldLayer.getBounds().pad(0.08));

function buildNdviOverlays(year) {{
  var group = L.layerGroup();
  for (var fid in ndviOverlays) {{
    var yd = ndviOverlays[fid][year];
    if (!yd) continue;
    var url = 'data:image/png;base64,' + yd.b64;
    var overlay = L.imageOverlay(url, [[yd.bounds[0], yd.bounds[1]], [yd.bounds[2], yd.bounds[3]]], {{opacity:0.85}});
    group.addLayer(overlay);
  }}
  return group;
}}

var currentNdviGroup = null;
function setLayer(name) {{
  currentLayer = name;
  applyVisibility();
  updateLegend();
}}

function setYear(year) {{
  currentYear = parseInt(year);
  if (currentLayer === 'ndvi') applyVisibility();
  else if (currentLayer === 'crop') applyCropStyles();
}}

function applyVisibility() {{
  if (currentNdviGroup) {{ map.removeLayer(currentNdviGroup); currentNdviGroup = null; }}
  if (phLayer) {{ map.removeLayer(phLayer); }}
  fieldLayer.eachLayer(function(l) {{ l.setStyle(defaultStyle(l.feature)); }});

  if (currentLayer === 'ndvi') {{
    currentNdviGroup = buildNdviOverlays(currentYear);
    map.addLayer(currentNdviGroup);
  }} else if (currentLayer === 'crop') {{
    applyCropStyles();
  }} else if (currentLayer === 'ph' && phData) {{
    if (!phLayer) {{
      phLayer = L.geoJSON(phData, {{
        style: function(f) {{
          return {{ color: '#555', weight:0.5, fillColor: phColor(f.properties.ph), fillOpacity:0.8 }};
        }},
        onEachFeature: function(f, layer) {{
          layer.bindPopup('<b>pH:</b> ' + (f.properties.ph !== null ? f.properties.ph : 'N/A') + '<br><b>Mukey:</b> ' + f.properties.mukey);
        }}
      }});
    }}
    map.addLayer(phLayer);
  }}
}}

function applyCropStyles() {{
  fieldLayer.eachLayer(function(l) {{
    l.setStyle(cropStyle(l.feature, currentYear));
  }});
}}

function updatePopup(feature, layer) {{
  var p = feature.properties;
  var fid = p.field_id;
  var crop = cropData[fid] && cropData[fid][currentYear];
  var html = '<table class="popup-table">' +
    '<tr><td>Field</td><td>' + (fid||'') + '</td></tr>' +
    '<tr><td>Farm</td><td>' + (p._farm_slug||'') + '</td></tr>' +
    '<tr><td>Grower</td><td>{grower_slug}</td></tr>' +
    '<tr><td>County</td><td>' + (p.county_name||'') + '</td></tr>' +
    '<tr><td>Acres</td><td>' + (p.area_acres ? Number(p.area_acres).toFixed(1) : '') + '</td></tr>' +
    (crop ? '<tr><td>Crop '+currentYear+'</td><td>'+crop+'</td></tr>' : '') +
    '</table>';
  var latlng = layer ? layer.getCenter() : null;
  if (!latlng && feature.geometry && feature.geometry.type === 'Point') {{
    var c = feature.geometry.coordinates;
    latlng = [c[1], c[0]];
  }} else if (!latlng && feature.geometry && feature.geometry.type === 'Polygon') {{
    var c0 = feature.geometry.coordinates[0][0];
    latlng = [c0[1], c0[0]];
  }}
  if (latlng) {{
    map.closePopup();
    L.popup().setLatLng(latlng).setContent(html).openOn(map);
  }}
}}

function updateLegend() {{
  var el = document.getElementById('legend');
  if (currentLayer === 'ndvi') {{
    el.innerHTML = '<div class="bar" style="background:linear-gradient(to right,#d73027,#f46d43,#fdae61,#fee08b,#d9ef8b,#a6d96a,#1a9850)"></div>' +
      '<div class="lbl"><span>Low</span><span>NDVI</span><span>High</span></div>';
  }} else if (currentLayer === 'crop') {{
    var used = new Set();
    fieldLayer.eachLayer(function(l) {{
      var c = cropData[l.feature.properties.field_id] && cropData[l.feature.properties.field_id][currentYear];
      if (c) used.add(c);
    }});
    var h = '';
    used.forEach(function(c) {{ h += '<div class="crop-item"><div class="crop-swatch" style="background:'+(cropColors[c]||'#999')+'"></div>'+c+'</div>'; }});
    el.innerHTML = h || '<span style="color:#999">No crop data</span>';
  }} else if (currentLayer === 'ph') {{
    el.innerHTML = '<div class="ph-bar" style="background:linear-gradient(to right,#d73027,#fc8d59,#fee08b,#d9ef8b,#91cf60,#1a9850)"></div>' +
      '<div class="lbl"><span>5.0</span><span>pH</span><span>7.5+</span></div>';
  }} else {{
    el.innerHTML = '<span style="color:#999">Farm-colored boundaries</span>';
  }}
}}

var fieldItems = {{}};
fieldLayer.eachLayer(function(layer) {{
  var fid = layer.feature.properties.field_id;
  if (fid) fieldItems[fid] = layer;
}});

var sel = document.getElementById('year-select');
years.forEach(function(y) {{
  var opt = document.createElement('option');
  opt.value = y;
  opt.textContent = y;
  if (y === currentYear) opt.selected = true;
  sel.appendChild(opt);
}});

var listEl = document.getElementById('field-list');
fieldList.forEach(function(f) {{
  var div = document.createElement('div');
  div.className = 'field-item';
  div.innerHTML = '<strong>' + (f.field_id||'') + '</strong><br><span class="farm-label">' +
    (f.farm_slug||'') + ' &middot; ' + (Number(f.area_acres).toFixed(1)||'') + ' ac</span>';
  div.addEventListener('click', function() {{
    var layer = fieldItems[f.field_id];
    if (layer) {{
      map.fitBounds(layer.getBounds().pad(0.1));
      updatePopup(layer.feature, layer);
    }}
  }});
  listEl.appendChild(div);
}});

document.getElementById('fit-btn').addEventListener('click', function() {{
  map.fitBounds(fieldLayer.getBounds().pad(0.08));
}});
</script>
</body>
</html>"""


def main() -> None:
    growers = _discover_growers()
    if not growers:
        print("No growers with field boundaries found under", GROWERS_ROOT)
        sys.exit(0)

    for grower in growers:
        g_slug = grower["grower_slug"]
        farms = grower["farms"]
        print(f"\n{g_slug}:")
        fields = _build_field_list(g_slug, farms)
        center_lat, center_lon = _grower_center(farms)

        ndvi = _render_ndvi_overlay(farms, g_slug)
        ndvi_count = sum(len(v) for v in ndvi.values())
        ndvi_total_kb = 0
        for fid in ndvi:
            for yr in ndvi[fid]:
                ndvi_total_kb += len(ndvi[fid][yr]["b64"]) * 3 // 4
        print(f"  NDVI overlays: {ndvi_count} field-years ({ndvi_total_kb // 1024} KB base64)")

        crops = _load_crop_data(g_slug, farms)
        print(f"  Crop records: {sum(len(v) for v in crops.values())} field-years")

        ph_gj, ph_str = _load_ph_map(g_slug, farms)
        if ph_gj:
            print(f"  pH polygons: {len(ph_gj.get('features', []))}")
        else:
            print("  pH map: not available")

        html = _generate_html(g_slug, farms, fields, center_lat, center_lon, ndvi, crops, ph_gj, ph_str)

        out_dir = farm_reports_dir(g_slug, farms[0]["farm_slug"]).parent
        out_path = out_dir / f"{g_slug}_fields_map.html"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        size_kb = out_path.stat().st_size / 1024
        print(f"  Map -> {out_path.relative_to(DATA_ROOT)} ({size_kb:.0f} KB)")

    print(f"\nGenerated {len(growers)} grower web map(s)")


if __name__ == "__main__":
    main()
