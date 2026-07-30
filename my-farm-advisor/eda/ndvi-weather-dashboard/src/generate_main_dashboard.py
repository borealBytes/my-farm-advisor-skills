import base64
import json
import re
import sys
import urllib.request
import warnings
from io import BytesIO
from pathlib import Path

import numpy as np
warnings.filterwarnings("ignore", message="Setting the shape on a NumPy array")
import pandas as pd
from PIL import Image
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ndvi_weather_dashboard import (
    _resolve_data_root,
    _field_root,
    _load_weather_for_year,
    _compute_gdd,
    _collect_all_scenes,
    _read_crop_info,
    _read_field_boundary_properties,
    _read_boundary,
    GDD_BASE_TEMP,
    GDD_CAP_TEMP,
)

_NDVI_CMAP = [
    (-0.2, (103, 0, 31)),
    (0.0, (178, 24, 43)),
    (0.2, (214, 96, 77)),
    (0.4, (244, 165, 130)),
    (0.6, (253, 219, 199)),
    (0.8, (166, 217, 106)),
    (1.0, (26, 152, 80)),
]


def _ndvi_to_png_datauri(ndvi_path: Path) -> tuple[str, tuple[float, float, float, float]]:
    with rasterio.open(ndvi_path) as src:
        data = np.array(src.read(1), dtype=np.float32)
        bounds = src.bounds
    mask = np.isfinite(data)
    norm = np.clip((data + 0.2) / 1.2, 0, 1)
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if mask.any():
        vn = norm[mask]
        stops = np.array([c[0] for c in _NDVI_CMAP])
        colors = np.array([c[1] for c in _NDVI_CMAP], dtype=np.float32)
        r = np.interp(vn, stops, colors[:, 0]).astype(np.uint8)
        g = np.interp(vn, stops, colors[:, 1]).astype(np.uint8)
        b = np.interp(vn, stops, colors[:, 2]).astype(np.uint8)
        rgba[mask, 0] = r
        rgba[mask, 1] = g
        rgba[mask, 2] = b
        rgba[mask, 3] = 255
    img = Image.fromarray(rgba, mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}", (bounds.left, bounds.bottom, bounds.right, bounds.top)

def _collect_weather_events(wdf: pd.DataFrame, aws_mm: float) -> list[dict]:
    events: list[dict] = []
    for _, row in wdf.iterrows():
        d = str(row["date"].date())
        if row["PRECTOTCORR"] > aws_mm:
            events.append({"date": d, "type": "precip", "label": "High Precip", "detail": f"{row['PRECTOTCORR']:.0f} mm"})
        if row["T2M_MAX"] > 35:
            events.append({"date": d, "type": "hot", "label": "Hot Day", "detail": f"{row['T2M_MAX']:.0f}°C"})
        if row["T2M_MAX"] < 0:
            if row["date"].month not in (12, 1, 2):
                events.append({"date": d, "type": "cold", "label": "Freeze Day", "detail": f"{row['T2M_MAX']:.0f}°C"})
    return events


def _compute_spi(lat: float, lon: float, year: int) -> str:
    try:
        url = f"https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=RE&longitude={lon}&latitude={lat}&start=2000&end={year}&format=JSON"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as f:
            data = json.loads(f.read())
        precip = data["properties"]["parameter"]["PRECTOTCORR"]
    except Exception:
        return "N/A"

    apr_sep_totals: list[float] = []
    for y in range(2000, year + 1):
        months = []
        for m in range(4, 10):
            key = f"{y}{m:02d}"
            val = precip.get(key)
            if val is None or val < 0:
                break
            months.append(val)
        if len(months) == 6:
            apr_sep_totals.append(sum(months))

    if len(apr_sep_totals) < 5:
        return "N/A"

    current = apr_sep_totals[-1]
    historical = np.array(apr_sep_totals[:-1])
    mean = float(np.mean(historical))
    std = float(np.std(historical, ddof=1))
    if std == 0:
        return "N/A"

    spi = (current - mean) / std

    if spi >= 2.0:
        cat = "W4 - Exceptionally Wet"
    elif spi >= 1.6:
        cat = "W3 - Extremely Wet"
    elif spi >= 1.3:
        cat = "W2 - Severely Wet"
    elif spi >= 0.8:
        cat = "W1 - Moderately Wet"
    elif spi >= 0.5:
        cat = "W0 - Abnormally Wet"
    elif spi >= -0.5:
        cat = "Normal"
    elif spi >= -0.8:
        cat = "D0 - Abnormally Dry"
    elif spi >= -1.3:
        cat = "D1 - Moderate Drought"
    elif spi >= -1.6:
        cat = "D2 - Severe Drought"
    elif spi >= -2.0:
        cat = "D3 - Extreme Drought"
    else:
        cat = "D4 - Exceptional Drought"
    return f"{cat} ({spi:+.2f})"


FIELD = "osm-1499317763"
YEARS = [2021, 2022, 2023, 2024, 2025]
GROWER = "il-grower"
FARM = "il-grower-illinois"

data_root = _resolve_data_root()
froot = _field_root(data_root, GROWER, FARM, FIELD)
field_info = _read_field_boundary_properties(froot)

summary_csv = froot / "soil" / "ssurgo_summary.csv"
soil: dict[str, str] = {}
aws_mm = 0
if summary_csv.exists():
    sdf = pd.read_csv(summary_csv)
    if not sdf.empty:
        r = sdf.iloc[0]
        aws_mm = round(float(r["total_aws_inches"]) * 25.4, 1)
        soil = {
            "aws_mm": f"{aws_mm} mm",
            "om_pct": f'{float(r["avg_om_pct"]):.2f}%',
            "ph": str(round(float(r["avg_ph"]), 2)),
            "dominant": str(r["dominant_soil"]),
            "drainage": str(r["drainage_class"]),
        }

rows: dict[str, list] = {
    "Crop": [],
    "Cumulative GDD": [],
    "Days > 30°C (Heat Stress Warning)": [],
    "Days < 10°C (Not Enough Heat)": [],
    "Days Precip > 44.7 mm (Flood Warning)": [],
    "Drought (6-mo SPI)": [],
    "Peak NDVI": [],
}

year_links = []
wdf_first = _load_weather_for_year(froot, YEARS[0])
if wdf_first is not None and not wdf_first.empty:
    lat = float(wdf_first["lat"].iloc[0])
    lon = float(wdf_first["lon"].iloc[0])
else:
    lat, lon = 40.508, -87.787

for year in YEARS:
    crop_info = _read_crop_info(froot, year)
    crop = crop_info["crop_name"]

    wdf = _load_weather_for_year(froot, year)
    if wdf is not None and not wdf.empty:
        days_over_cap = int((wdf["T2M_MAX"] > GDD_CAP_TEMP).sum())
        days_below_base = int((wdf["T2M_MAX"] < GDD_BASE_TEMP).sum())
        gdd_series = _compute_gdd(wdf)
        cum_gdd = round(float(gdd_series.iloc[-1]), 1)

        precip = wdf["PRECTOTCORR"].values
        mask = precip > aws_mm
        if len(precip) >= 2:
            two_day_sum = precip[:-1] + precip[1:]
            overlap = np.zeros(len(precip), dtype=bool)
            overlap[:-1] |= two_day_sum > aws_mm
            overlap[1:]  |= two_day_sum > aws_mm
            mask |= overlap
        high_precip_days = int(mask.sum())
    else:
        days_over_cap = 0
        days_below_base = 0
        cum_gdd = None
        high_precip_days = 0

    scenes = _collect_all_scenes(froot, year, data_root)
    valid = [s for s in scenes if s["mean_ndvi"] is not None]
    if valid:
        peak = max(valid, key=lambda s: s["mean_ndvi"])
        peak_str = f'{peak["mean_ndvi"]:.3f} ({peak["date"]})'
    else:
        peak_str = "N/A"

    emoji = "\U0001F33D" if crop == "Corn" else "\U0001FAD8" if crop == "Soybeans" else ""
    rows["Crop"].append(f"{emoji} {crop}")
    rows["Cumulative GDD"].append(str(cum_gdd) if cum_gdd is not None else "N/A")
    rows["Days > 30°C (Heat Stress Warning)"].append(str(days_over_cap))
    rows["Days < 10°C (Not Enough Heat)"].append(str(days_below_base))
    rows["Days Precip > 44.7 mm (Flood Warning)"].append(str(high_precip_days))
    rows["Drought (6-mo SPI)"].append(_compute_spi(lat, lon, year))
    rows["Peak NDVI"].append(peak_str)
    year_links.append(f'ndvi_weather_dashboard_{year}.html')

ndvi_scenes_all: list[dict] = []
for year in YEARS:
    scenes = _collect_all_scenes(froot, year, data_root)
    valid_scenes = [s for s in scenes if s["mean_ndvi"] is not None]
    for s in valid_scenes:
        try:
            png_uri, bbox = _ndvi_to_png_datauri(Path(s["ndvi_path"]))
        except Exception:
            continue
        ndvi_scenes_all.append({
            "date": s["date"],
            "year": year,
            "mean_ndvi": round(s["mean_ndvi"], 3),
            "data_uri": png_uri,
            "bounds": list(bbox),
            "source": s.get("source", "unknown"),
        })

from datetime import datetime as dt_mod

scene_idx_by_date = [(i, s["date"]) for i, s in enumerate(ndvi_scenes_all)]
seen_events: set = set()
events_flat: list[dict] = []
for year in YEARS:
    wdf = _load_weather_for_year(froot, year)
    if wdf is None or wdf.empty:
        continue
    for evt in _collect_weather_events(wdf, aws_mm):
        key = (evt["date"], evt["type"])
        if key in seen_events:
            continue
        seen_events.add(key)
        nearest = min(scene_idx_by_date, key=lambda x: abs(
            (dt_mod.strptime(x[1], "%Y-%m-%d") - dt_mod.strptime(evt["date"], "%Y-%m-%d")).days
        ))
        events_flat.append({
            "date": evt["date"],
            "year": year,
            "type": evt["type"],
            "detail": evt["detail"],
            "scene_idx": nearest[0],
        })
events_flat.sort(key=lambda e: e["date"])

boundary_gj = None
boundary_obj = _read_boundary(froot)
if boundary_obj is not None:
    boundary_gj = boundary_obj.__geo_interface__

county = field_info.get("county_name", "")
acres = field_info.get("area_acres", 0)
crop_rotation = " → ".join(rows["Crop"])

soil_cards_html = ""
if soil:
    soil_cards_html = """  <div class="card">
    <h2>Soil Summary</h2>
    <div class="summary-grid">
""" + "".join(
        f'      <div class="summary-item"><div class="num">{v}</div><div class="lbl">{k}</div></div>\n'
        for k, v in {
            "Water Hold. Cap.": soil["aws_mm"],
            "Organic Matter": soil["om_pct"],
            "pH": soil["ph"],
            "Dominant Soil": soil["dominant"],
            "Drainage": soil["drainage"],
        }.items()
    ) + "    </div>\n  </div>\n"

year_cells = "".join(
    f'<th><a href="{link}">{y}</a></th>'
    for y, link in zip(YEARS, year_links)
)
table_rows = ""
for label, vals in rows.items():
    if label == "Crop":
        cells = "".join(f"<td>{v}</td>" for v in vals)
    else:
        nums = []
        for v in vals:
            n = None
            try:
                n = float(v.split()[0])
            except (ValueError, IndexError):
                m = re.search(r'\(([+-]?\d+\.?\d*)\)', v)
                if m:
                    try:
                        n = float(m.group(1))
                    except ValueError:
                        pass
            nums.append(n)
        if label == "Drought (6-mo SPI)":
            extreme = min((n for n in nums if n is not None), default=None)
        else:
            extreme = max((n for n in nums if n is not None), default=None)
        cells = ""
        for i, v in enumerate(vals):
            if nums[i] is not None and extreme is not None and nums[i] == extreme:
                cells += f'<td style="color:#dc2626;font-weight:700;">{v}</td>'
            else:
                cells += f"<td>{v}</td>"
    table_rows += f"<tr><td class='row-label'>{label}</td>{cells}</tr>"

ndvi_scenes_json = json.dumps(ndvi_scenes_all)
events_json = json.dumps(events_flat)
boundary_gj_json = json.dumps(boundary_gj) if boundary_gj else "null"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Main Dashboard · {FIELD}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f1f5f9; color: #0f172a; line-height: 1.5;
}}
.dashboard {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{
  background: linear-gradient(135deg, #166534, #15803d);
  color: white; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
}}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
.header .sub {{ font-size: 14px; opacity: 0.9; }}
.header .meta {{ font-size: 13px; opacity: 0.75; margin-top: 6px; }}
.card {{
  background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
.card h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: #0f172a; }}
.summary-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px;
}}
.summary-item {{
  background: #f8fafc; border-radius: 8px; padding: 14px; text-align: center;
  border: 1px solid #e2e8f0;
}}
.summary-item .num {{ font-size: 24px; font-weight: 700; color: #166534; }}
.summary-item .lbl {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ padding: 10px 14px; text-align: center; border-bottom: 1px solid #e2e8f0; }}
th {{
  background: #f0fdf4; font-weight: 600; color: #166534;
  border-bottom: 2px solid #15803d;
}}
th a {{ color: #166534; text-decoration: none; }}
th a:hover {{ text-decoration: underline; color: #15803d; }}
.row-label {{ text-align: left; font-weight: 600; color: #334155; background: #f8fafc; }}
tr:hover td {{ background: #f8fafc; }}
.footer {{
  text-align: center; font-size: 11px; color: #94a3b8; padding: 16px;
}}
.data-badge {{
  display: inline-block; background: white; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; margin-right: 6px; margin-bottom: 4px;
  color: #0f172a;
}}
#ndvi-map {{ height: 450px; border-radius: 8px; }}
.map-controls {{ display: flex; align-items: center; gap: 14px; margin-top: 12px; flex-wrap: wrap; }}
.map-controls input[type=range] {{ flex: 1; min-width: 100px; accent-color: #15803d; }}
.map-info {{ font-size: 13px; color: #334155; white-space: nowrap; }}
.map-info strong {{ color: #0f172a; }}
.map-legend {{ display: flex; align-items: center; gap: 4px; margin-top: 8px; font-size: 11px; color: #64748b; }}
.map-legend .bar {{ height: 10px; flex: 1; border-radius: 4px; background: linear-gradient(to right, #67001f, #b2182b, #d6604d, #f4a582, #fddbc7, #a6d96a, #1a9850); }}
.map-legend .lbl {{ min-width: 28px; text-align: center; }}
.play-btn {{
  background: #15803d; color: white; border: none; border-radius: 6px;
  padding: 4px 14px; font-size: 13px; cursor: pointer; font-weight: 600;
}}
.play-btn:hover {{ background: #166534; }}
.play-btn.playing {{ background: #dc2626; }}
#map-wrap {{ position: relative; }}
.ev-list {{ margin-top: 8px; }}
.ev-list-body {{ max-height: 200px; overflow-y: auto; }}
.ev-group {{ margin-bottom: 2px; }}
.ev-group summary {{
  cursor: pointer; font-size: 12px; font-weight: 600; color: #475569;
  padding: 3px 6px; border-radius: 4px; user-select: none;
}}
.ev-group summary:hover {{ background: #f1f5f9; }}
.ev-group[open] summary {{ margin-bottom: 3px; }}
.ev-item {{
  cursor: pointer; padding: 2px 8px; font-size: 12px; border-radius: 4px;
  display: inline-block; margin: 1px;
}}
.ev-item:hover {{ background: #f1f5f9; }}
.ev-item.active {{ background: #15803d; color: white; }}
</style>
</head>
<body>
<div class="dashboard">
  <div class="header">
    <h1>{FIELD} · Main Dashboard</h1>
    <div class="sub">{county}{", " + str(acres) + " ac" if acres else ""}</div>
    <div class="meta">
      <span class="data-badge">📅 {YEARS[0]}–{YEARS[-1]}</span>
      <span class="data-badge">🔄 {crop_rotation}</span>
      <span class="data-badge">🧑‍🌾 {soil.get('dominant', '')}</span>
    </div>
  </div>

  {soil_cards_html}  <div class="card">
    <h2>Key Environmental Indicators per Year</h2>
    <p style="font-size:12px;color:#64748b;margin-top:-8px;margin-bottom:12px;">Click a year to view detailed dashboard</p>
    <table>
      <thead><tr><th>Metric</th>{year_cells}</tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>NDVI Timelapse 2021–2025</h2>
    <div id="map-wrap">
      <div id="ndvi-map"></div>
    </div>
    <div class="map-controls">
      <button class="play-btn" id="play-btn">&#9654; Play</button>
      <input type="range" id="ndvi-slider" min="0" max="0" value="0">
      <span class="map-info" id="ndvi-info">Loading...</span>
    </div>
    <div class="map-legend">
      <span class="lbl">-0.2</span>
      <div class="bar"></div>
      <span class="lbl">1.0</span>
    </div>
    <div class="ev-list">
      <div class="ev-list-body" id="ev-list-body"></div>
    </div>
  </div>

  <div class="footer">
    Generated by ndvi-weather-dashboard &middot; Data: CDL, Sentinel-2, NASA POWER
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin></script>
<script>
(function() {{
var scenes = {ndvi_scenes_json};
var events = {events_json};
var boundaryGj = {boundary_gj_json};
if (!scenes.length) {{
  document.getElementById('ndvi-map').innerHTML = '<div style="text-align:center;padding:80px 0;color:#94a3b8;">No NDVI scenes available</div>';
  return;
}}
var map = L.map('ndvi-map', {{ zoomControl: false, attributionControl: false, scrollWheelZoom: false, doubleClickZoom: false }});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  maxZoom: 19,
  attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
}}).addTo(map);

var overlays = [];
var bounds = L.latLngBounds(scenes[0].bounds[1], scenes[0].bounds[0]);
scenes.forEach(function(s, i) {{
  var b = s.bounds;
  var imgBounds = L.latLngBounds([b[1], b[0]], [b[3], b[2]]);
  bounds.extend(imgBounds);
  var overlay = L.imageOverlay(s.data_uri, imgBounds, {{ opacity: 1, interactive: false }});
  overlay._ndviIdx = i;
  overlays.push(overlay);
  map.addLayer(overlay);
}});
map.fitBounds(bounds.pad(0.05));

if (boundaryGj && boundaryGj.features) {{
  L.geoJSON(boundaryGj, {{
    style: {{ color: '#0f172a', weight: 2, fill: false, opacity: 0.8 }}
  }}).addTo(map);
}}

var evtIcons = {{ precip: '\\uD83C\\uDF27', hot: '\\uD83D\\uDD25', cold: '\\u2744' }};

function renderEventsList(events) {{
  var body = document.getElementById('ev-list-body');
  body.innerHTML = '';
  var byYear = {{}};
  events.forEach(function(e) {{
    (byYear[e.year] = byYear[e.year] || []).push(e);
  }});
  var yearsSorted = Object.keys(byYear).sort();
  yearsSorted.forEach(function(yr) {{
    var details = document.createElement('details');
    details.className = 'ev-group';
    details.open = true;
    var sum = document.createElement('summary');
    sum.textContent = yr + ' (' + byYear[yr].length + ' events)';
    details.appendChild(sum);
    byYear[yr].forEach(function(e) {{
      var div = document.createElement('span');
      div.className = 'ev-item';
      div.innerHTML = (evtIcons[e.type] || '\\u2022') + ' ' + e.date + ' ' + e.detail;
      div.addEventListener('click', function() {{
        document.querySelectorAll('.ev-item.active').forEach(function(el) {{ el.classList.remove('active'); }});
        this.classList.add('active');
        slider.value = e.scene_idx;
        showScene(e.scene_idx);
        if (playInterval) {{ clearInterval(playInterval); playInterval = null; playBtn.textContent = '\\u25B6 Play'; playBtn.classList.remove('playing'); }}
      }});
      details.appendChild(div);
    }});
    body.appendChild(details);
  }});
}}

var slider = document.getElementById('ndvi-slider');
var info = document.getElementById('ndvi-info');
var playBtn = document.getElementById('play-btn');
slider.max = overlays.length - 1;
slider.value = 0;

function showScene(idx) {{
  overlays.forEach(function(o, i) {{
    if (i === idx) {{
      map.addLayer(o);
    }} else {{
      map.removeLayer(o);
    }}
  }});
  var s = scenes[idx];
  info.innerHTML = '<strong>' + s.date + '</strong> &middot; NDVI ' + s.mean_ndvi + ' &middot; ' + s.source + ' &middot; <span style="color:#64748b;">' + (idx + 1) + ' of ' + scenes.length + '</span>';
}}

renderEventsList(events);
showScene(0);

showScene(0);

slider.addEventListener('input', function() {{
  if (playInterval) {{ clearInterval(playInterval); playInterval = null; playBtn.textContent = '\\u25B6 Play'; playBtn.classList.remove('playing'); }}
  showScene(parseInt(this.value));
}});

var playInterval = null;
playBtn.addEventListener('click', function() {{
  if (playInterval) {{
    clearInterval(playInterval);
    playInterval = null;
    playBtn.textContent = '\\u25B6 Play';
    playBtn.classList.remove('playing');
  }} else {{
    playBtn.textContent = '\\u25A0 Stop';
    playBtn.classList.add('playing');
    var cur = parseInt(slider.value);
    playInterval = setInterval(function() {{
      cur = (cur + 1) % overlays.length;
      slider.value = cur;
      showScene(cur);
    }}, 1200);
  }}
}});

window.addEventListener('resize', function() {{ map.invalidateSize(); }});
}})();
</script>
</body>
</html>"""

out_dir = froot / "derived" / "dashboards"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "field_dashboard.html"
out_path.write_text(html, encoding="utf-8")
print(f"✓ Main dashboard: {out_path}")
