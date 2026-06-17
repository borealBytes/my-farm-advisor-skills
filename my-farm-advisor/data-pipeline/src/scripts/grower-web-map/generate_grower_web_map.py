#!/usr/bin/env python3
"""Generate a lightweight interactive Leaflet HTML web map for each grower.

Reads field boundary GeoJSON from the canonical data-pipeline runtime tree and
produces a self-contained HTML file that opens in any browser.  Polygon
geometry and basic metadata are embedded; Leaflet and basemap tiles load from
CDN at view time.

Typical usage::

    export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
    cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
    ../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import geopandas as gpd  # type: ignore[import-untyped]
except ImportError:
    sys.exit("geopandas is required.  Install it into the data-pipeline venv.")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _data_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT", "")
    if not raw:
        sys.exit("DATA_PIPELINE_DATA_ROOT is not set")
    root = Path(raw)
    if not root.is_absolute():
        sys.exit(f"DATA_PIPELINE_DATA_ROOT must be absolute: {raw}")
    return root


def _runtime_base() -> Path:
    return _data_root() / "data-pipeline"


def _growers_dir() -> Path:
    return _runtime_base() / "growers"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_growers(grower_slug: str | None = None) -> list[Path]:
    """Return grower directory Paths, optionally filtered by slug."""
    base = _growers_dir()
    if not base.is_dir():
        sys.exit(f"growers directory not found: {base}")
    slugs: list[str] = []
    if grower_slug:
        c = base / grower_slug
        if not c.is_dir():
            sys.exit(f"grower not found: {c}")
        slugs = [grower_slug]
    else:
        slugs = sorted(
            d.name for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    return [base / s for s in slugs]


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}}
#container{{display:flex;height:100vh;}}
#sidebar{{
  width:300px;min-width:260px;background:#fff;border-right:1px solid #ddd;
  display:flex;flex-direction:column;overflow:hidden;
}}
#sidebar-header{{
  padding:16px;background:#1B5E20;color:#fff;
}}
#sidebar-header h1{{font-size:1.1em;margin-bottom:4px;}}
#sidebar-header p{{font-size:0.8em;opacity:0.85;margin:0;}}
#sidebar-stats{{
  padding:12px 16px;background:#f5f5f5;border-bottom:1px solid #ddd;
  display:flex;gap:20px;font-size:0.82em;
}}
#sidebar-stats div{{text-align:center;}}
#sidebar-stats .stat-value{{font-size:1.3em;font-weight:700;color:#2E7D32;}}
#sidebar-stats .stat-label{{color:#666;}}
#field-list{{
  flex:1;overflow-y:auto;padding:8px 0;
}}
.field-item{{
  display:flex;align-items:center;justify-content:space-between;
  padding:8px 16px;cursor:pointer;border-bottom:1px solid #f0f0f0;
  transition:background .15s;
}}
.field-item:hover{{background:#e8f5e9;}}
.field-item.active{{background:#c8e6c9;}}
.field-item .field-name{{font-size:0.9em;font-weight:500;}}
.field-item .field-acres{{font-size:0.78em;color:#888;white-space:nowrap;}}
.field-zoom-btn{{
  background:#2E7D32;color:#fff;border:none;border-radius:4px;
  padding:3px 10px;font-size:0.75em;cursor:pointer;white-space:nowrap;
}}
.field-zoom-btn:hover{{background:#1B5E20;}}
#map{{flex:1;}}
.popup-table{{margin:0;}}
.popup-table td{{padding:2px 6px 2px 0;font-size:0.9em;}}
.popup-table td:first-child{{font-weight:600;color:#555;white-space:nowrap;}}
.popup-table td:last-child{{color:#222;}}
</style>
</head>
<body>
<div id="container">
<div id="sidebar">
  <div id="sidebar-header">
    <h1>{title}</h1>
    <p>Grower: {grower} | Farm: {farm_name}</p>
  </div>
  <div id="sidebar-stats">
    <div><div class="stat-value">{field_count}</div><div class="stat-label">Fields</div></div>
    <div><div class="stat-value">{total_acres}</div><div class="stat-label">Total Acres</div></div>
  </div>
  <div id="field-list"></div>
</div>
<div id="map"></div>
</div>
<script>
var map = L.map('map', {{zoomControl: true}});

// Basemaps
var osmLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19
}}).addTo(map);

var satLayer = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  attribution: 'Esri, Maxar, Earthstar Geographics',
  maxZoom: 18
}});

L.control.layers(
  {{'Street': osmLayer, 'Satellite': satLayer}},
  null,
  {{position: 'topright'}}
).addTo(map);

// Field GeoJSON
var fieldData = {geojson};

var allLayers = [];
var fieldListEl = document.getElementById('field-list');

var fieldsLayer = L.geoJSON(fieldData, {{
  style: function(f) {{
    return {{
      color: '{line_color}',
      weight: 2,
      opacity: 0.85,
      fillColor: '{fill_color}',
      fillOpacity: 0.25
    }};
  }},
  onEachFeature: function(feature, layer) {{
    allLayers.push({{layer: layer, props: feature.properties}});

    var props = feature.properties;
    var fid = props.field_id || 'Unknown';
    var county = props.county_name || '';
    var state = props.state_fips || '';
    var area = props.area_acres != null ? props.area_acres.toFixed(1) : 'N/A';

    layer.bindPopup(
      '<table class="popup-table">' +
      '<tr><td>Grower</td><td>{grower}</td></tr>' +
      '<tr><td>Farm</td><td>{farm_name}</td></tr>' +
      '<tr><td>Field</td><td>' + fid + '</td></tr>' +
      '<tr><td>County</td><td>' + county + ' (FIPS ' + state + ')</td></tr>' +
      '<tr><td>Area</td><td>' + area + ' acres</td></tr>' +
      '</table>',
      {{maxWidth: 280}}
    );

    layer.on('click', function() {{
      highlightField(fid);
    }});
  }}
}}).addTo(map);

// Fit map to all fields
map.fitBounds(fieldsLayer.getBounds().pad(0.08));

// Build field list
allLayers.sort(function(a, b) {{
  var na = a.props.field_id || '';
  var nb = b.props.field_id || '';
  return na.localeCompare(nb);
}});

allLayers.forEach(function(item) {{
  var props = item.props;
  var fid = props.field_id || 'Unknown';
  var acres = props.area_acres != null ? props.area_acres.toFixed(1) : 'N/A';

  var row = document.createElement('div');
  row.className = 'field-item';
  row.id = 'field-item-' + fid.replace(/[^a-zA-Z0-9]/g, '_');
  row.innerHTML =
    '<span class="field-name">' + fid + '</span>' +
    '<span class="field-acres">' + acres + ' ac</span>' +
    '<button class="field-zoom-btn">Zoom</button>';

  row.querySelector('.field-zoom-btn').addEventListener('click', function(e) {{
    e.stopPropagation();
    map.fitBounds(item.layer.getBounds().pad(0.15));
    highlightField(fid);
  }});

  row.addEventListener('click', function() {{
    map.fitBounds(item.layer.getBounds().pad(0.15));
    item.layer.openPopup();
    highlightField(fid);
  }});

  fieldListEl.appendChild(row);
}});

function highlightField(fid) {{
  document.querySelectorAll('.field-item').forEach(function(el) {{
    el.classList.remove('active');
  }});
  var target = document.getElementById('field-item-' + fid.replace(/[^a-zA-Z0-9]/g, '_'));
  if (target) target.classList.add('active');
}}
</script>
</body>
</html>"""


def generate_map(grower_path: Path, output_path: Path | None = None) -> Path:
    """Generate a single interactive HTML map for one grower.

    Returns the output ``Path``.
    """
    grower_slug = grower_path.name
    farms_dir = grower_path / "farms"
    if not farms_dir.is_dir():
        sys.exit(f"no farms directory for grower: {grower_path}")

    # Collect features from every farm
    all_features: list[dict] = []
    farm_name = grower_slug  # fallback
    fields_found = 0
    total_acres = 0.0

    for farm_entry in sorted(farms_dir.iterdir()):
        if not farm_entry.is_dir():
            continue
        farm_slug = farm_entry.name
        farm_name = farm_slug  # last farm wins as display name (typically one)
        bnd_path = farm_entry / "boundary" / "field_boundaries.geojson"
        if not bnd_path.is_file():
            print(f"  skip {farm_slug}: no field_boundaries.geojson", file=sys.stderr)
            continue

        gdf = gpd.read_file(bnd_path)
        if len(gdf) == 0:
            print(f"  skip {farm_slug}: empty boundary file", file=sys.stderr)
            continue

        for _, row in gdf.iterrows():
            geom = row.geometry.__geo_interface__
            props = {
                k: (v if not (isinstance(v, float) and v != v) else None)
                for k, v in row.drop("geometry").items()
            }
            # Inject farm metadata into properties for the popup
            props["grower_slug"] = grower_slug
            props["farm_slug"] = farm_slug
            all_features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": props,
            })
            fields_found += 1
            if props.get("area_acres"):
                total_acres += float(props["area_acres"])
            else:
                total_acres += 0.0

    if not all_features:
        print(f"  WARNING: no field features found for grower {grower_slug}", file=sys.stderr)
        # Still produce an empty map so the grower entry isn't silent
        fields_found = 0
        total_acres = 0.0

    geojson = json.dumps({"type": "FeatureCollection", "features": all_features})

    html = HTML_TEMPLATE.format(
        title=f"{grower_slug}",
        grower=grower_slug,
        farm_name=farm_name,
        field_count=str(fields_found),
        total_acres=f"{total_acres:.1f}",
        line_color="#1B5E20",
        fill_color="#4CAF50",
        geojson=geojson,
    )

    if output_path is None:
        # Write into the first farm's dashboards directory
        first_farm = None
        for farm_entry in sorted(farms_dir.iterdir()):
            if farm_entry.is_dir():
                first_farm = farm_entry
                break
        if first_farm is None:
            sys.exit(f"no farm directory found for grower: {grower_path}")
        dashboards_dir = first_farm / "derived" / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        output_path = dashboards_dir / "grower_web_map.html"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate lightweight interactive Leaflet HTML web maps per grower."
    )
    parser.add_argument(
        "--grower-slug",
        help="Generate map for a single grower (default: all growers).",
    )
    parser.add_argument(
        "--output",
        help="Override output file path (only valid with --grower-slug).",
    )
    args = parser.parse_args()

    if args.output and not args.grower_slug:
        sys.exit("--output requires --grower-slug")

    growers = discover_growers(args.grower_slug)
    print(f"Found {len(growers)} grower(s)")

    for gpath in growers:
        print(f"\nGenerating map for: {gpath.name}")
        out = generate_map(gpath, output_path=Path(args.output) if args.output else None)
        size_kb = out.stat().st_size / 1024
        print(f"  -> {out}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
