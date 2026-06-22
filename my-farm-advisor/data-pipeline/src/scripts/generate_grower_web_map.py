#!/usr/bin/env python3
"""Generate a self-contained interactive Leaflet web map for a grower's fields."""

from __future__ import annotations

import argparse
import json
import os
import textwrap
from pathlib import Path

_LOCAL_LIB = Path(__file__).resolve().parent / "lib"
import sys
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_LIB))

from paths import (
    DATA_ROOT,
    GROWERS_ROOT,
    farm_boundary_path,
    farm_dir,
    grower_dir,
    grower_logs_dir,
)


LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"

PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9a6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
]


def _slug_from_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def _discover_growers() -> list[str]:
    if not GROWERS_ROOT.exists():
        return []
    return sorted(
        p.name for p in GROWERS_ROOT.iterdir()
        if p.is_dir() and p.name != "default-grower"
    )


def _discover_farms(grower_slug: str) -> list[str]:
    farms_dir = grower_dir(grower_slug) / "farms"
    if not farms_dir.exists():
        return []
    return sorted(p.name for p in farms_dir.iterdir() if p.is_dir())


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_fields(grower_slug: str) -> dict:
    combined = {"type": "FeatureCollection", "features": []}
    property_sources: dict[str, dict] = {}

    for farm_slug in _discover_farms(grower_slug):
        bpath = farm_boundary_path(grower_slug, farm_slug)
        if not bpath.exists():
            continue
        fc = _load_json(bpath)
        if not fc or "features" not in fc:
            continue
        for feat in fc["features"]:
            fid = feat.get("properties", {}).get("field_id", "")
            feat["properties"]["farm_slug"] = farm_slug
            feat["properties"]["grower_slug"] = grower_slug
            combined["features"].append(feat)
            property_sources[fid] = feat["properties"]

    return combined


def _build_html(grower_slug: str, fc: dict, grower_name: str) -> str:
    geo_json_str = json.dumps(fc, separators=(",", ":"))
    n_fields = len(fc["features"])

    return textwrap.dedent(f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Grower Web Map &mdash; {grower_name}</title>
<link rel="stylesheet" href="{LEAFLET_CSS}" />
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ height:100%; font-family:system-ui,sans-serif; }}
  #map {{ height:100%; width:100%; }}
  .sidebar {{
    position:fixed; top:0; left:0; width:280px; height:100%;
    background:#fff; z-index:1000; overflow-y:auto;
    box-shadow:2px 0 6px rgba(0,0,0,.2); padding:12px;
    transform:translateX(0); transition:transform .25s;
  }}
  .sidebar.collapsed {{ transform:translateX(-100%); }}
  .sidebar h2 {{ font-size:1rem; margin-bottom:4px; }}
  .sidebar p {{ font-size:.8rem; color:#555; margin-bottom:12px; }}
  .field-entry {{
    padding:6px 8px; margin:4px 0; border-radius:4px;
    cursor:pointer; font-size:.85rem; border-left:4px solid #ccc;
    transition:background .15s;
  }}
  .field-entry:hover {{ background:#f0f0f0; }}
  .toggle-btn {{
    position:fixed; top:10px; left:290px; z-index:1001;
    background:#fff; border:1px solid #ccc; border-radius:4px;
    padding:4px 8px; cursor:pointer; font-size:.8rem;
    box-shadow:0 1px 4px rgba(0,0,0,.2);
  }}
  .toggle-btn.collapsed {{ left:10px; }}
</style>
</head>
<body>

<div class="sidebar" id="sidebar">
  <h2>{grower_name}</h2>
  <p>{n_fields} field{'s' if n_fields != 1 else ''}</p>
  <div id="field-list"></div>
</div>

<button class="toggle-btn" id="toggle-btn" onclick="toggleSidebar()">&larr;</button>
<div id="map"></div>

<script src="{LEAFLET_JS}"></script>
<script>
var fields = {geo_json_str};

var map = L.map("map").setView([40.7, -89.5], 6);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}", {{
  attribution: "&copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
  maxZoom: 19,
}}).addTo(map);

var palette = {json.dumps(PALETTE)};
var fieldLayers = [];
var boundsGroup = [];

function assignColor(i) {{
  return palette[i % palette.length];
}}

var listEl = document.getElementById("field-list");

fields.features.forEach(function(f, i) {{
  var props = f.properties || {{}};
  var fid = props.field_id || "unknown";
  var farm = props.farm_slug || "";
  var crop = props.crop_name || "";
  var acres = props.area_acres != null ? Number(props.area_acres).toFixed(1) : "?";
  var county = props.county_name || "";
  var st = props.state_fips || "";
  var color = assignColor(i);

  var layer = L.geoJSON(f, {{
    style: {{
      color: color, weight: 2, fillColor: color, fillOpacity: 0.2,
    }},
  }});

  var label = fid.replace("osm-", "Field ");
  var popupHtml = (
    "<b>" + label + "</b><br>" +
    "Grower: " + "{grower_name}" + "<br>" +
    "Farm: " + farm + "<br>" +
    "Area: " + acres + " ac<br>" +
    "County: " + county + (st ? " (" + st + ")" : "") + "<br>" +
    (crop ? "Cover: " + crop : "")
  );
  layer.bindPopup(popupHtml);

  layer.addTo(map);
  fieldLayers.push(layer);
  boundsGroup.push(layer.getBounds());

  var entry = document.createElement("div");
  entry.className = "field-entry";
  entry.style.borderLeftColor = color;
  entry.innerHTML = "<b>" + label + "</b> &mdash; " + acres + " ac";
  entry.onclick = function() {{
    map.fitBounds(layer.getBounds(), {{ padding: [30, 30] }});
    layer.openPopup();
  }};
  listEl.appendChild(entry);
}});

if (boundsGroup.length > 0) {{
  var allBounds = boundsGroup[0];
  for (var j = 1; j < boundsGroup.length; j++) {{
    allBounds.extend(boundsGroup[j]);
  }}
  map.fitBounds(allBounds, {{ padding: [30, 30] }});
}}

function toggleSidebar() {{
  var sb = document.getElementById("sidebar");
  var btn = document.getElementById("toggle-btn");
  sb.classList.toggle("collapsed");
  btn.classList.toggle("collapsed");
  btn.innerHTML = sb.classList.contains("collapsed") ? "&#x2192;" : "&#x2190;";
  setTimeout(function() {{ map.invalidateSize(); }}, 260);
}}
</script>
</body>
</html>""")


def generate_for_grower(grower_slug: str) -> Path:
    gj = _load_json(grower_dir(grower_slug) / "grower.json")
    grower_name = (gj or {}).get("display_name", grower_slug)

    fc = _collect_fields(grower_slug)
    if not fc["features"]:
        print(f"[grower-web-map] No field boundaries found for {grower_slug}, skipping")
        return Path()

    html = _build_html(grower_slug, fc, grower_name)
    out = grower_dir(grower_slug) / "derived" / "reports" / "grower_web_map.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"[grower-web-map] {grower_slug}: {len(fc['features'])} fields, {size_kb:.0f} KB -> {out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a self-contained Leaflet web map for one or all growers."
    )
    parser.add_argument(
        "--grower-slug", required=True,
        help="Grower slug or 'all' to process every grower",
    )
    args = parser.parse_args()

    if args.grower_slug == "all":
        growers = _discover_growers()
        if not growers:
            print("[grower-web-map] No growers found")
            return
        for slug in growers:
            generate_for_grower(slug)
    else:
        generate_for_grower(args.grower_slug)


if __name__ == "__main__":
    main()
