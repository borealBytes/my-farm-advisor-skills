#!/usr/bin/env python3
"""Generate a lightweight, self-contained interactive HTML web map for a grower.

Reads actual field boundary GeoJSON from the data-pipeline runtime, enriches
features with grower/farm/field metadata, and emits a single HTML file with
embedded GeoJSON and Leaflet.js.  No external imagery or heavy assets are
embedded; the basemap loads from the internet.

Usage:
    python scripts/admin/generate_grower_webmap.py --grower-slug <slug>

Environment:
    DATA_PIPELINE_DATA_ROOT  – required absolute path to the runtime tree.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Runtime path bootstrap (same pattern as sibling pipeline scripts)
# ---------------------------------------------------------------------------
_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_farms(grower_slug: str) -> list[tuple[str, str]]:
    """Return list of (farm_slug, farm_path) for the given grower."""
    farms_root = _RUNTIME_BASE / "growers" / grower_slug / "farms"
    if not farms_root.exists():
        return []
    results: list[tuple[str, str]] = []
    for farm_dir in sorted(farms_root.iterdir()):
        if farm_dir.is_dir() and (farm_dir / "farm.json").exists():
            results.append((farm_dir.name, str(farm_dir)))
    return results


def _read_farm_boundary(farm_path: Path) -> dict[str, Any] | None:
    boundary_path = farm_path / "boundary" / "field_boundaries.geojson"
    if not boundary_path.exists():
        return None
    return _load_json(boundary_path)


def _enrich_feature(
    feature: dict[str, Any],
    *,
    grower_name: str,
    farm_name: str,
    field_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Add human-readable metadata to a GeoJSON feature's properties."""
    props = dict(feature.get("properties") or {})
    field_id = props.get("field_id", "unknown")
    meta = field_metadata.get(field_id, {})

    props["grower_name"] = grower_name
    props["farm_name"] = farm_name
    props["field_name"] = meta.get("display_name", field_id)
    props["field_id"] = field_id
    # Keep existing area_acres, county_name, etc. if present
    return {**feature, "properties": props}


def _collect_field_metadata(farm_path: Path) -> dict[str, dict[str, Any]]:
    """Read every field.json under a farm to build a field_id -> metadata map."""
    meta: dict[str, dict[str, Any]] = {}
    fields_dir = farm_path / "fields"
    if not fields_dir.exists():
        return meta
    for field_dir in fields_dir.iterdir():
        if not field_dir.is_dir():
            continue
        field_json = field_dir / "field.json"
        if field_json.exists():
            data = _load_json(field_json)
            slug = data.get("field_slug", field_dir.name)
            meta[slug] = data
    return meta


def _geojson_bounds(features: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat) for all polygon coords."""
    lons: list[float] = []
    lats: list[float] = []
    for feat in features:
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])
        if geom.get("type") == "Polygon":
            rings = coords
        elif geom.get("type") == "MultiPolygon":
            rings = [ring for poly in coords for ring in poly]
        else:
            continue
        for ring in rings:
            for pt in ring:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    lons.append(float(pt[0]))
                    lats.append(float(pt[1]))
    if not lons:
        return (-98.0, 38.0, -88.0, 42.0)  # CONUS-ish fallback
    return (min(lons), min(lats), max(lons), max(lats))


def _center_from_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((bounds[1] + bounds[3]) / 2.0, (bounds[0] + bounds[2]) / 2.0)


def _html_escape(value: Any) -> str:
    s = str(value) if value is not None else ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _build_html(grower_name: str, geojson_data: dict[str, Any]) -> str:
    """Construct a self-contained HTML page with Leaflet and embedded GeoJSON."""
    features = list(geojson_data.get("features", []))
    bounds = _geojson_bounds(features)
    center = _center_from_bounds(bounds)
    geojson_str = json.dumps(geojson_data, separators=(",", ":"))

    # Build sidebar items from features
    sidebar_items: list[str] = []
    for idx, feat in enumerate(features):
        props = feat.get("properties", {})
        name = _html_escape(props.get("field_name", f"Field {idx + 1}"))
        farm = _html_escape(props.get("farm_name", "Unknown Farm"))
        area = props.get("area_acres", "")
        area_str = f"{area:.2f} acres" if isinstance(area, (int, float)) else ""
        county = _html_escape(props.get("county_name", ""))
        meta_parts = [p for p in [farm, county, area_str] if p]
        meta = " · ".join(meta_parts)
        sidebar_items.append(
            f'<li onclick="zoomToField({idx})">'
            f'<span class="fname">{name}</span>'
            f'<span class="fmeta">{meta}</span></li>'
        )

    sidebar_html = "\n".join(sidebar_items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html_escape(grower_name)} – Grower Web Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; font-family: system-ui, -apple-system, sans-serif; }}
  #container {{ display: flex; height: 100vh; }}
  #sidebar {{ width: 280px; background: #f8f9fa; border-right: 1px solid #dee2e6;
              display: flex; flex-direction: column; }}
  #sidebar header {{ padding: 1rem; background: #212529; color: #fff; }}
  #sidebar header h1 {{ margin: 0 0 .25rem; font-size: 1.1rem; }}
  #sidebar header p {{ margin: 0; font-size: .8rem; opacity: .8; }}
  #field-list {{ list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }}
  #field-list li {{ padding: .75rem 1rem; border-bottom: 1px solid #e9ecef;
                    cursor: pointer; transition: background .15s; }}
  #field-list li:hover {{ background: #e9ecef; }}
  #field-list .fname {{ display: block; font-weight: 600; font-size: .9rem; color: #212529; }}
  #field-list .fmeta {{ display: block; font-size: .75rem; color: #6c757d; margin-top: .15rem; }}
  #map {{ flex: 1; }}
  .leaflet-popup-content {{ font-size: .9rem; margin: .5rem .75rem; }}
  .leaflet-popup-content table {{ border-collapse: collapse; }}
  .leaflet-popup-content td {{ padding: .15rem .4rem; }}
  .leaflet-popup-content td:first-child {{ font-weight: 600; color: #495057; }}
</style>
</head>
<body>
<div id="container">
  <aside id="sidebar">
    <header>
      <h1>{_html_escape(grower_name)}</h1>
      <p>{len(features)} field(s)</p>
    </header>
    <ul id="field-list">
{sidebar_html}
    </ul>
  </aside>
  <div id="map"></div>
</div>
<script>
  var map = L.map('map').setView([{center[0]:.6f}, {center[1]:.6f}], 13);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 20
  }}).addTo(map);

  var geojsonData = {geojson_str};
  var layers = [];

  function onEachFeature(feature, layer) {{
    var p = feature.properties || {{}};
    var rows = [
      ['Grower', p.grower_name || ''],
      ['Farm',   p.farm_name   || ''],
      ['Field',  p.field_name  || ''],
      ['County', p.county_name || ''],
      ['Area',   (typeof p.area_acres === 'number') ? p.area_acres.toFixed(2) + ' acres' : '']
    ].filter(function(r) {{ return r[1]; }});
    var html = '<table>' + rows.map(function(r) {{
      return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>';
    }}).join('') + '</table>';
    layer.bindPopup(html);
    layers.push(layer);
  }}

  var geoLayer = L.geoJSON(geojsonData, {{
    style: {{ color: '#facc15', weight: 2.5, opacity: 1.0, fillColor: '#facc15', fillOpacity: 0.2 }},
    onEachFeature: onEachFeature
  }}).addTo(map);

  if (geoLayer.getBounds().isValid()) {{
    map.fitBounds(geoLayer.getBounds().pad(0.1));
  }}

  function zoomToField(index) {{
    var layer = layers[index];
    if (!layer) return;
    if (layer.getBounds && layer.getBounds().isValid()) {{
      map.fitBounds(layer.getBounds().pad(0.15));
    }} else if (layer.getLatLng) {{
      map.setView(layer.getLatLng(), 16);
    }}
    if (layer.openPopup) layer.openPopup();
  }}
</script>
</body>
</html>
"""


def generate_grower_webmap(grower_slug: str, output_dir: Path | None = None) -> Path:
    """Generate the web map HTML for a single grower and return the output path."""
    grower_dir = _RUNTIME_BASE / "growers" / grower_slug
    grower_json = _load_json(grower_dir / "grower.json")
    grower_name = grower_json.get("display_name") or grower_slug

    if output_dir is None:
        output_dir = grower_dir / "derived"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "grower_webmap.html"

    all_features: list[dict[str, Any]] = []

    for farm_slug, farm_path_str in _discover_farms(grower_slug):
        farm_path = Path(farm_path_str)
        farm_json = _load_json(farm_path / "farm.json")
        farm_name = farm_json.get("display_name") or farm_json.get("farm_slug") or farm_slug

        field_meta = _collect_field_metadata(farm_path)
        boundary_geojson = _read_farm_boundary(farm_path)
        if not boundary_geojson:
            continue

        for feat in boundary_geojson.get("features", []):
            enriched = _enrich_feature(
                feat,
                grower_name=grower_name,
                farm_name=farm_name,
                field_metadata=field_meta,
            )
            all_features.append(enriched)

    if not all_features:
        raise RuntimeError(f"No field boundary features found for grower '{grower_slug}'.")

    geojson_collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "name": f"{grower_slug}_field_boundaries",
        "features": all_features,
    }

    html = _build_html(grower_name, geojson_collection)
    output_path.write_text(html, encoding="utf-8")
    print(f"[generate_grower_webmap] wrote {output_path} ({len(html)} bytes, {len(all_features)} features)")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a lightweight interactive HTML web map for a grower."
    )
    parser.add_argument("--grower-slug", required=True, help="Grower slug to map.")
    parser.add_argument("--output-dir", default="", help="Override output directory.")
    args = parser.parse_args(argv)

    out_dir: Path | None = Path(args.output_dir) if args.output_dir else None
    generate_grower_webmap(args.grower_slug, output_dir=out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
