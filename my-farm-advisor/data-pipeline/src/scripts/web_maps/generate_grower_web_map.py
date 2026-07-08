#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate lightweight interactive Leaflet web maps for each grower.

Reads actual field boundary GeoJSON from the runtime tree and emits a single
self-contained HTML file per grower with an embedded GeoJSON payload,
sidebar field list, click popups, and an internet basemap.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

# Ensure lib/ is on path when running from runtime copy
_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
_GROWERS_ROOT = _RUNTIME_BASE / "growers"

# Subtle green palette for multi-farm growers
_FARM_COLORS = [
    "#2E7D32",
    "#388E3C",
    "#43A047",
    "#66BB6A",
    "#81C784",
    "#558B2F",
    "#33691E",
]


def _prettify_grower(slug: str) -> str:
    """Turn a slug like 'il-grower' into 'IL Grower'."""
    parts = slug.replace("_", " ").replace("-", " ").split()
    return " ".join(p.upper() if len(p) == 2 else p.capitalize() for p in parts)


def _prettify_farm(name: str) -> str:
    """Turn a slug like 'il-grower-illinois' into 'Il Grower Illinois'."""
    return name.replace("_", " ").replace("-", " ").title()


def _discover_growers() -> list[str]:
    if not _GROWERS_ROOT.exists():
        return []
    return sorted(
        d.name for d in _GROWERS_ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _discover_farms(grower_slug: str) -> list[str]:
    farms_dir = _GROWERS_ROOT / grower_slug / "farms"
    if not farms_dir.exists():
        return []
    return sorted(
        d.name for d in farms_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _discover_fields(grower_slug: str, farm_slug: str) -> list[str]:
    fields_dir = _GROWERS_ROOT / grower_slug / "farms" / farm_slug / "fields"
    if not fields_dir.exists():
        return []
    return sorted(
        d.name for d in fields_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _load_field_boundary(grower_slug: str, farm_slug: str, field_slug: str) -> dict | None:
    path = (
        _GROWERS_ROOT
        / grower_slug
        / "farms"
        / farm_slug
        / "fields"
        / field_slug
        / "boundary"
        / "field_boundary.geojson"
    )
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_feature_collection(grower_slug: str) -> tuple[list[dict], list[dict]]:
    """Return (geojson_feature_collection_as_dict, field_records_list).

    Each field record has: farm_slug, farm_name, field_slug, field_name,
    area_acres, bounds, centroid.
    """
    farms = _discover_farms(grower_slug)
    features: list[dict] = []
    records: list[dict] = []

    for farm_idx, farm_slug in enumerate(farms):
        farm_name = _prettify_farm(farm_slug)
        color = _FARM_COLORS[farm_idx % len(_FARM_COLORS)]
        fields = _discover_fields(grower_slug, farm_slug)
        for field_slug in fields:
            geo = _load_field_boundary(grower_slug, farm_slug, field_slug)
            if geo is None or "features" not in geo:
                continue
            for feat in geo["features"]:
                if feat.get("type") != "Feature":
                    continue
                props = dict(feat.get("properties", {}))
                props["_farm_name"] = farm_name
                props["_farm_slug"] = farm_slug
                props["_field_slug"] = field_slug
                props["_field_name"] = props.get("field_id", field_slug)
                props["_color"] = color

                area = props.get("area_acres")
                try:
                    area = float(area) if area is not None else None
                except Exception:
                    area = None
                props["_area_acres"] = area

                geom = feat.get("geometry")
                coords = _extract_coords(geom)
                bounds = _bounds_from_coords(coords) if coords else None
                centroid = _centroid_from_coords(coords) if coords else None

                records.append(
                    {
                        "farm_slug": farm_slug,
                        "farm_name": farm_name,
                        "field_slug": field_slug,
                        "field_name": props["_field_name"],
                        "area_acres": area,
                        "bounds": bounds,
                        "centroid": centroid,
                    }
                )

                features.append(
                    {
                        "type": "Feature",
                        "properties": props,
                        "geometry": geom,
                    }
                )

    return {"type": "FeatureCollection", "features": features}, records


def _extract_coords(geom: dict | None) -> list:
    """Crude coordinate extractor for Polygon/MultiPolygon."""
    if geom is None:
        return []
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        return c[0] if c and len(c) > 0 else []
    if t == "MultiPolygon":
        return c[0][0] if c and len(c) > 0 and c[0] else []
    return []


def _bounds_from_coords(coords: list) -> list[float] | None:
    if not coords:
        return None
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    return [min(lons), min(lats), max(lons), max(lats)]


def _centroid_from_coords(coords: list) -> list[float] | None:
    if not coords:
        return None
    lons = [p[0] for p in coords]
    lats = [p[1] for p in coords]
    return [sum(lats) / len(lats), sum(lons) / len(lons)]


def _generate_html(grower_slug: str, fc: dict, records: list[dict]) -> str:
    grower_name = _prettify_grower(grower_slug)
    n_farms = len({r["farm_slug"] for r in records})
    n_fields = len(records)

    # Overall bounds
    all_bounds = [r["bounds"] for r in records if r["bounds"]]
    if all_bounds:
        min_lon = min(b[0] for b in all_bounds)
        min_lat = min(b[1] for b in all_bounds)
        max_lon = max(b[2] for b in all_bounds)
        max_lat = max(b[3] for b in all_bounds)
        center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
        bounds_js = f"[[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]]"
    else:
        center = [40.0, -95.0]
        bounds_js = "null"

    geojson_str = json.dumps(fc)

    # Sidebar rows
    sidebar_rows: list[str] = []
    for idx, r in enumerate(records):
        area_txt = f"{r['area_acres']:.1f} ac" if r["area_acres"] is not None else ""
        centroid = r["centroid"]
        lat = centroid[0] if centroid else 0
        lon = centroid[1] if centroid else 0
        sidebar_rows.append(
            f"""<div class="field-item" onclick="zoomToField({idx}, {lat}, {lon})">
                <span class="field-name">{r['field_name']}</span>
                <span class="field-meta">{r['farm_name']} {area_txt}</span>
            </div>"""
        )

    sidebar_html = "\n".join(sidebar_rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{grower_name} - Field Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  #container {{ display: flex; height: 100vh; }}
  #sidebar {{
    width: 280px;
    background: #f8f9fa;
    border-right: 1px solid #dee2e6;
    display: flex;
    flex-direction: column;
  }}
  #sidebar header {{
    padding: 1rem;
    background: #1B5E20;
    color: white;
  }}
  #sidebar header h1 {{ margin: 0; font-size: 1.1rem; }}
  #sidebar header p {{ margin: 0.25rem 0 0; font-size: 0.8rem; opacity: 0.9; }}
  #field-list {{
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
  }}
  .field-item {{
    padding: 0.6rem 0.5rem;
    margin-bottom: 0.4rem;
    background: white;
    border-radius: 6px;
    border: 1px solid #e9ecef;
    cursor: pointer;
    transition: background 0.15s;
  }}
  .field-item:hover {{ background: #e8f5e9; border-color: #a5d6a7; }}
  .field-name {{ display: block; font-weight: 600; font-size: 0.9rem; color: #1B5E20; }}
  .field-meta {{ display: block; font-size: 0.78rem; color: #6c757d; margin-top: 0.15rem; }}
  #map {{ flex: 1; }}
  .legend {{
    background: white;
    padding: 8px 12px;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-size: 0.8rem;
    line-height: 1.5;
  }}
  .legend-item {{ display: flex; align-items: center; margin: 4px 0; }}
  .legend-color {{ width: 14px; height: 14px; border-radius: 3px; margin-right: 8px; }}
</style>
</head>
<body>
<div id="container">
  <div id="sidebar">
    <header>
      <h1>{grower_name}</h1>
      <p>{n_farms} farm{'s' if n_farms != 1 else ''} &middot; {n_fields} field{'s' if n_fields != 1 else ''}</p>
    </header>
    <div id="field-list">
      {sidebar_html}
    </div>
  </div>
  <div id="map"></div>
</div>
<script>
  var map = L.map('map').setView([{center[0]}, {center[1]}], 12);

  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
  }}).addTo(map);

  var fieldData = {geojson_str};

  var layers = [];

  var geoLayer = L.geoJSON(fieldData, {{
    style: function(feature) {{
      return {{
        color: '#1B5E20',
        weight: 2,
        fillColor: feature.properties._color || '#2E7D32',
        fillOpacity: 0.45
      }};
    }},
    onEachFeature: function(feature, layer) {{
      var p = feature.properties;
      var area = p._area_acres ? p._area_acres.toFixed(1) + ' acres' : 'N/A';
      var popup = '<b>Grower:</b> ' + {json.dumps(grower_name)} + '<br>' +
                  '<b>Farm:</b> ' + (p._farm_name || 'N/A') + '<br>' +
                  '<b>Field:</b> ' + (p._field_name || 'N/A') + '<br>' +
                  '<b>Area:</b> ' + area;
      layer.bindPopup(popup);
      layers.push(layer);
    }}
  }}).addTo(map);

  var bounds = {bounds_js};
  if (bounds) {{
    map.fitBounds(bounds, {{ padding: [40, 40] }});
  }}

  function zoomToField(idx, lat, lon) {{
    if (lat && lon) {{
      map.setView([lat, lon], 15);
    }}
    var layer = layers[idx];
    if (layer) {{
      layer.openPopup();
    }}
  }}
</script>
</body>
</html>
"""
    return html


def _emit_map(grower_slug: str) -> Path | None:
    fc, records = _build_feature_collection(grower_slug)
    if not records:
        print(f"  {grower_slug}: no field boundaries found, skipping.")
        return None

    html = _generate_html(grower_slug, fc, records)
    out_dir = _GROWERS_ROOT / grower_slug / "derived" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{grower_slug}_web_map.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"  {grower_slug}: wrote {out_path} ({size_kb:.1f} KB)")
    return out_path


def main() -> None:
    print("=" * 60)
    print("Grower Web Map Generator")
    print("=" * 60)

    growers = _discover_growers()
    if not growers:
        print("No growers found under", _GROWERS_ROOT)
        return

    print(f"Discovered {len(growers)} grower(s): {', '.join(growers)}\n")

    for g in growers:
        _emit_map(g)

    print("\nDone.")


if __name__ == "__main__":
    main()
