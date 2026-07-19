#!/usr/bin/env python3
"""Generate a self-contained offline Grower Field Weather Dashboard.

Produces a single HTML file with embedded Plotly.js, field map, GDD and
rainfall charts, and inline weather data.  No runtime external dependencies.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import OrderedDict
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLOR_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

PLOTLY_CDN_URL = (
    "https://cdn.plot.ly/plotly-2.35.2.min.js"
)
PLOTLY_CACHE_FILENAME = "plotly-2.35.2.min.js"

ESRI_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

TILE_USER_AGENT = "MyFarmAdvisorDashboard/1.0"

# Spherical Mercator constants
MERCATOR_EXTENT = 20037508.342789244

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _mercator_x(lon: float) -> float:
    return lon * MERCATOR_EXTENT / 180.0


def _mercator_y(lat: float) -> float:
    return math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * MERCATOR_EXTENT / math.pi


def _mercator_ring(coords: list[list[float]]) -> list[list[float]]:
    return [[_mercator_x(lon), _mercator_y(lat)] for lon, lat in coords]


def _mercator_polygon(geom: dict[str, Any]) -> list[list[list[float]]]:
    typ = geom.get("type", "")
    if typ == "Polygon":
        return [_mercator_ring(geom["coordinates"][0])]
    elif typ == "MultiPolygon":
        rings: list[list[list[float]]] = []
        for poly in geom["coordinates"]:
            rings.append(_mercator_ring(poly[0]))
        return rings
    return []


def _color_for_index(idx: int) -> str:
    return COLOR_PALETTE[idx % len(COLOR_PALETTE)]


def _fmt(val: Any, decimals: int = 2) -> str:
    if val is None:
        return "null"
    return f"{val:.{decimals}f}"


# ---------------------------------------------------------------------------
# Runtime directory discovery
# ---------------------------------------------------------------------------

def _candidate_runtime_roots() -> list[Path]:
    candidates: list[Path] = []

    data_root_env = os.environ.get("DATA_PIPELINE_DATA_ROOT", "").strip()
    if data_root_env:
        p = Path(data_root_env).expanduser().resolve()
        candidates.append(p)

    home = Path.home()
    for pattern in (
        "my-farm-advisor-runtime",
        "my-farm-advisor-data",
        ".my-farm-advisor",
    ):
        candidate = home / pattern
        if candidate.is_dir():
            candidates.append(candidate)

    unique: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _find_farms_in_root(root: Path) -> list[Path]:
    farms: list[Path] = []
    # Try root/growers first, then root/data-pipeline/growers
    growers_candidates = [
        root / "growers",
        root / "data-pipeline" / "growers",
    ]
    growers: Path | None = None
    for gc in growers_candidates:
        if gc.is_dir():
            growers = gc
            break
    if growers is None:
        return farms
    for grower_dir in sorted(growers.iterdir()):
        if not grower_dir.is_dir():
            continue
        farms_dir = grower_dir / "farms"
        if not farms_dir.is_dir():
            continue
        for farm_dir in sorted(farms_dir.iterdir()):
            if not farm_dir.is_dir():
                continue
            boundary = farm_dir / "boundary" / "field_boundaries.geojson"
            fields_dir = farm_dir / "fields"
            if boundary.exists() and fields_dir.is_dir():
                farms.append(farm_dir)
    return farms


def resolve_farm_dir(
    farm_dir: str | Path | None = None,
    growers_dir: str | Path | None = None,
) -> Path:
    if farm_dir is not None:
        resolved = Path(farm_dir).expanduser().resolve()
        _validate_farm_dir(resolved)
        return resolved

    if growers_dir is not None:
        root = Path(growers_dir).expanduser().resolve()
        farms = _find_farms_in_root(root)
        return _disambiguate_farms(farms)

    for root in _candidate_runtime_roots():
        farms = _find_farms_in_root(root)
        if farms:
            return _disambiguate_farms(farms)

    raise RuntimeError(
        "No farm directory discovered. "
        "Set DATA_PIPELINE_DATA_ROOT or pass --farm-dir / --growers-dir."
    )


def _validate_farm_dir(farm_dir: Path) -> None:
    if not farm_dir.is_dir():
        raise RuntimeError(f"Farm directory does not exist: {farm_dir}")
    boundary = farm_dir / "boundary" / "field_boundaries.geojson"
    if not boundary.exists():
        raise RuntimeError(
            f"Missing required boundary/field_boundaries.geojson in {farm_dir}"
        )
    fields_dir = farm_dir / "fields"
    if not fields_dir.is_dir():
        raise RuntimeError(f"Missing required fields/ directory in {farm_dir}")


def _disambiguate_farms(farms: list[Path]) -> Path:
    if len(farms) == 1:
        return farms[0]
    if not farms:
        raise RuntimeError("No valid farm directories found.")
    candidates = "\n".join(f"  {p}" for p in farms)
    raise RuntimeError(
        f"Multiple farm directories found ({len(farms)}):\n{candidates}\n"
        "Use --farm-dir to select one explicitly."
    )


# ---------------------------------------------------------------------------
# Farm data reading
# ---------------------------------------------------------------------------

FarmMeta = dict[str, Any]
FieldRecord = dict[str, Any]
WeatherRecord = dict[str, Any]


def read_farm_data(farm_dir: Path) -> tuple[FarmMeta, list[FieldRecord], list[WeatherRecord]]:
    # Farm metadata
    farm_json_path = farm_dir / "farm.json"
    farm_meta: FarmMeta = {}
    if farm_json_path.exists():
        farm_meta = json.loads(farm_json_path.read_text(encoding="utf-8"))
    farm_slug = farm_meta.get("farm_slug") or farm_dir.name
    farm_name = farm_meta.get("display_name") or farm_slug.replace("-", " ").title()

    # Field boundaries
    boundary_path = farm_dir / "boundary" / "field_boundaries.geojson"
    boundaries = json.loads(boundary_path.read_text(encoding="utf-8"))
    features = boundaries.get("features", [])

    # Read inventory for stable field ordering
    inventory = _read_inventory(farm_dir)
    field_order: list[str] = []
    if inventory:
        inv_ids = {row["field_id"] for row in inventory}
        for row in inventory:
            field_order.append(row["field_id"])
        for feat in features:
            fid = str(feat.get("properties", {}).get("field_id", ""))
            if fid and fid not in inv_ids:
                field_order.append(fid)
    else:
        for feat in features:
            fid = str(feat.get("properties", {}).get("field_id", ""))
            if fid:
                field_order.append(fid)

    # Deduplicate
    seen_ids: set[str] = set()
    unique_order: list[str] = []
    for fid in field_order:
        if fid and fid not in seen_ids:
            seen_ids.add(fid)
            unique_order.append(fid)

    # Build field_id -> feature lookup
    feat_by_id: dict[str, dict[str, Any]] = {}
    for feat in features:
        fid = str(feat.get("properties", {}).get("field_id", ""))
        if fid:
            feat_by_id[fid] = feat

    fields: list[FieldRecord] = []
    for idx, fid in enumerate(unique_order):
        feat = feat_by_id.get(fid, {})
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})

        area = props.get("area_acres", None)
        if area is not None:
            try:
                area = float(area)
            except (ValueError, TypeError):
                area = None

        # Per-field metadata
        field_slug = _slugify(fid)
        field_dir = farm_dir / "fields" / field_slug
        field_json_path = field_dir / "field.json"
        display_name = field_slug
        if field_json_path.exists():
            try:
                field_meta = json.loads(field_json_path.read_text(encoding="utf-8"))
                dn = field_meta.get("display_name")
                if dn:
                    display_name = str(dn)
            except (json.JSONDecodeError, OSError):
                pass

        mercator_polys = _mercator_polygon(geom) if geom else []

        fields.append({
            "fieldId": fid,
            "fieldSlug": field_slug,
            "fieldName": display_name,
            "acres": area,
            "color": _color_for_index(idx),
            "mercatorPolygons": mercator_polys,
            "hasWeatherData": False,
            "availableYears": [],
        })

    # Per-field weather
    weather_records: list[WeatherRecord] = []
    for fld in fields:
        wcsv = farm_dir / "fields" / fld["fieldSlug"] / "weather" / "daily_weather.csv"
        if not wcsv.exists():
            continue
        wdf = _read_weather_csv(wcsv, fld["fieldId"])
        if not wdf:
            continue
        fld["hasWeatherData"] = True
        year_groups = _group_by_year(wdf)
        years = sorted(year_groups.keys())
        fld["availableYears"] = years
        for year in years:
            transformed = _compute_weather_transforms(year_groups[year], year, fld["fieldId"])
            if transformed:
                weather_records.append(transformed)
                fld["hasWeatherData"] = True

    # Fallback: farm-level aggregate weather table
    if not weather_records:
        alt = _try_farm_aggregate_weather(farm_dir, fields)
        if alt:
            weather_records.extend(alt)

    meta: FarmMeta = {
        "farmId": farm_slug,
        "farmName": farm_name,
        "growerSlug": farm_meta.get("grower_slug", "unknown"),
    }

    return meta, fields, weather_records


def _read_inventory(farm_dir: Path) -> list[dict[str, str]]:
    inv_path = farm_dir / "manifests" / "field-inventory.csv"
    if not inv_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with inv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _read_weather_csv(path: Path, field_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return rows
    # Filter to matching field_id if column exists
    if "field_id" in rows[0]:
        rows = [r for r in rows if r.get("field_id", "").strip() == field_id]
    return rows


def _group_by_year(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        raw_date = (row.get("date") or "").strip()
        if not raw_date:
            continue
        try:
            d = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            continue
        groups.setdefault(d.year, []).append(row)
    return groups


def _compute_weather_transforms(
    rows: list[dict[str, Any]], year: int, field_id: str
) -> WeatherRecord | None:
    if not rows:
        return None

    # Parse all dates and values
    parsed: list[dict[str, Any]] = []
    for row in rows:
        raw_date = (row.get("date") or "").strip()
        if not raw_date:
            continue
        try:
            d = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            continue
        t_min = _safe_float(row.get("T2M_MIN"))
        t_max = _safe_float(row.get("T2M_MAX"))
        precip = _safe_float(row.get("PRECTOTCORR"))
        parsed.append({"date": d, "tMin": t_min, "tMax": t_max, "precip": precip})

    if not parsed:
        return None

    parsed.sort(key=lambda r: r["date"])

    # Last frost date: latest day before July 1 with T2M_MIN <= 0
    july1 = date(year, 7, 1)
    last_frost_date: date = date(year, 1, 1)
    for p in parsed:
        if p["date"] < july1 and p["tMin"] is not None and p["tMin"] <= 0.0:
            last_frost_date = p["date"]

    last_frost_doy = last_frost_date.timetuple().tm_yday

    # Build daily records starting from last frost
    daily: list[dict[str, Any]] = []
    cum_gdd = 0.0
    cum_rain_in = 0.0
    for p in parsed:
        if p["date"] < last_frost_date:
            continue
        doy = p["date"].timetuple().tm_yday

        # Daily GDD
        daily_gdd = 0.0
        if p["tMax"] is not None and p["tMin"] is not None:
            daily_gdd = max((p["tMax"] + p["tMin"]) / 2.0 - 10.0, 0.0)

        daily_rain_in = 0.0
        if p["precip"] is not None:
            daily_rain_in = p["precip"] * 0.0393701

        cum_gdd += daily_gdd
        cum_rain_in += daily_rain_in

        daily.append({
            "date": p["date"].isoformat(),
            "dayOfYear": doy,
            "dailyGdd": round(daily_gdd, 4),
            "cumulativeGdd": round(cum_gdd, 4),
            "dailyRainfallIn": round(daily_rain_in, 4),
            "cumulativeRainfallIn": round(cum_rain_in, 4),
        })

    if not daily:
        return None

    return {
        "fieldId": field_id,
        "year": year,
        "lastFrostDate": last_frost_date.isoformat(),
        "lastFrostDoy": last_frost_doy,
        "daily": daily,
    }


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _try_farm_aggregate_weather(
    farm_dir: Path, fields: list[FieldRecord]
) -> list[WeatherRecord]:
    tables = farm_dir / "derived" / "tables"
    if not tables.is_dir():
        return []
    csv_files = sorted(tables.glob("*.csv"))
    for csv_file in csv_files:
        try:
            rows = _read_farm_weather_csv(csv_file)
            if rows:
                return _distribute_aggregate_to_fields(rows, fields)
        except Exception:
            continue
    return []


def _read_farm_weather_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _distribute_aggregate_to_fields(
    rows: list[dict[str, Any]], fields: list[FieldRecord]
) -> list[WeatherRecord]:
    weather_records: list[WeatherRecord] = []
    for fld in fields:
        field_rows = [r for r in rows if r.get("field_id", "").strip() == fld["fieldId"]]
        if not field_rows:
            continue
        year_groups = _group_by_year(field_rows)
        for year in sorted(year_groups.keys()):
            transformed = _compute_weather_transforms(year_groups[year], year, fld["fieldId"])
            if transformed:
                weather_records.append(transformed)
                if year not in fld["availableYears"]:
                    fld["availableYears"].append(year)
                fld["hasWeatherData"] = True
    return weather_records


# ---------------------------------------------------------------------------
# Plotly bundle download
# ---------------------------------------------------------------------------

def _plotly_cache_dir() -> Path:
    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT", str(Path.home()))
    return Path(data_root).expanduser() / "data-pipeline" / "shared" / "reference" / "plotly"


def ensure_plotly_bundle(force: bool = False) -> str:
    cache_dir = _plotly_cache_dir()
    cache_path = cache_dir / PLOTLY_CACHE_FILENAME
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8")

    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading Plotly bundle from {PLOTLY_CDN_URL} ...")
    try:
        req = urllib.request.Request(
            PLOTLY_CDN_URL,
            headers={"User-Agent": TILE_USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            js = resp.read().decode("utf-8")
        cache_path.write_text(js, encoding="utf-8")
        print(f"  Cached to {cache_path}  ({len(js) / 1024:.0f} KB)")
        return js
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if cache_path.exists():
            print(f"  WARNING: Download failed ({exc}), using cached version")
            return cache_path.read_text(encoding="utf-8")
        raise RuntimeError(
            f"Failed to download Plotly bundle and no cache available: {exc}"
        )


# ---------------------------------------------------------------------------
# Satellite basemap
# ---------------------------------------------------------------------------

def acquire_basemap(
    fields: list[FieldRecord], no_basemap: bool = False
) -> tuple[str | None, dict[str, float] | None]:
    if no_basemap:
        return None, None

    if not fields:
        return None, None

    try:
        from PIL import Image as PILImage
    except ImportError:
        print("  WARNING: Pillow not available, skipping basemap")
        return None, None

    # Compute full-farm Mercator extent with 15% buffer
    all_x: list[float] = []
    all_y: list[float] = []
    for fld in fields:
        for poly in fld["mercatorPolygons"]:
            for pt in poly:
                all_x.append(pt[0])
                all_y.append(pt[1])

    if not all_x:
        return None, None

    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)

    buf_x = (xmax - xmin) * 0.15
    buf_y = (ymax - ymin) * 0.15
    xmin -= buf_x
    xmax += buf_x
    ymin -= buf_y
    ymax += buf_y

    # Target ~1500px wide
    target_px = 1500.0
    world_size = MERCATOR_EXTENT * 2

    zoom = 0
    for z in range(1, 19):
        tiles_at_z = 2**z
        px_at_z = tiles_at_z * 256.0
        meters_per_px = world_size / px_at_z
        width_m = xmax - xmin
        est_width_px = width_m / meters_per_px
        if est_width_px <= target_px:
            zoom = max(z - 1, 0)
            break
        zoom = z

    zoom = min(zoom, 16)  # safety cap

    # Tile index ranges
    n_tiles = 2**zoom
    tile_size = 256

    def _merc_to_tile(mx: float, my: float) -> tuple[int, int]:
        tx = int((mx + MERCATOR_EXTENT) / world_size * n_tiles)
        ty = int((MERCATOR_EXTENT - my) / world_size * n_tiles)
        return (tx, ty)

    tx1, ty1 = _merc_to_tile(xmin, ymax)
    tx2, ty2 = _merc_to_tile(xmax, ymin)

    tx1 = max(0, tx1)
    ty1 = max(0, ty1)
    tx2 = min(n_tiles - 1, tx2)
    ty2 = min(n_tiles - 1, ty2)

    tile_count = (tx2 - tx1 + 1) * (ty2 - ty1 + 1)
    if tile_count > 50:
        print(f"  WARNING: {tile_count} tiles needed, limiting zoom")
        while zoom > 8 and tile_count > 50:
            zoom -= 1
            n_tiles = 2**zoom
            tx1, ty1 = _merc_to_tile(xmin, ymax)
            tx2, ty2 = _merc_to_tile(xmax, ymin)
            tx1 = max(0, tx1)
            ty1 = max(0, ty1)
            tx2 = min(n_tiles - 1, tx2)
            ty2 = min(n_tiles - 1, ty2)
            tile_count = (tx2 - tx1 + 1) * (ty2 - ty1 + 1)

    img_w = (tx2 - tx1 + 1) * tile_size
    img_h = (ty2 - ty1 + 1) * tile_size
    stitched = PILImage.new("RGB", (img_w, img_h))

    tiles_fetched = 0
    max_tiles = 50
    for tx in range(tx1, tx2 + 1):
        for ty in range(ty1, ty2 + 1):
            if tiles_fetched >= max_tiles:
                break
            url = ESRI_TILE_URL.format(z=zoom, x=tx, y=ty)
            tile_data = _fetch_tile(url)
            if tile_data:
                try:
                    tile_img = PILImage.open(BytesIO(tile_data))
                    ox = (tx - tx1) * tile_size
                    oy = (ty - ty1) * tile_size
                    stitched.paste(tile_img, (ox, oy))
                    tiles_fetched += 1
                except Exception:
                    pass
        if tiles_fetched >= max_tiles:
            break

    if tiles_fetched == 0:
        print("  WARNING: No tiles fetched, skipping basemap")
        return None, None

    # Crop to exact buffered Mercator bounds
    def _tile_merc_bounds(tx: int, ty: int, z: int) -> tuple[float, float, float, float]:
        nt = 2**z
        wx0 = (tx / nt) * world_size - MERCATOR_EXTENT
        wy1 = MERCATOR_EXTENT - (ty / nt) * world_size
        wx1 = ((tx + 1) / nt) * world_size - MERCATOR_EXTENT
        wy0 = MERCATOR_EXTENT - ((ty + 1) / nt) * world_size
        return (wx0, wy0, wx1, wy1)

    tile0_bounds = _tile_merc_bounds(tx1, ty1, zoom)
    crop_px_left = int((xmin - tile0_bounds[0]) / (tile0_bounds[2] - tile0_bounds[0]) * tile_size)
    crop_px_top = int((tile0_bounds[3] - ymax) / (tile0_bounds[3] - tile0_bounds[1]) * tile_size)
    crop_px_w = int((xmax - xmin) / (tile0_bounds[2] - tile0_bounds[0]) * tile_size)
    crop_px_h = int((ymax - ymin) / (tile0_bounds[3] - tile0_bounds[1]) * tile_size)

    crop_px_left = max(0, crop_px_left)
    crop_px_top = max(0, crop_px_top)
    crop_px_w = min(crop_px_w, stitched.width - crop_px_left)
    crop_px_h = min(crop_px_h, stitched.height - crop_px_top)

    if crop_px_w < 1 or crop_px_h < 1:
        print("  WARNING: Crop area too small, skipping basemap")
        stitched.close()
        return None, None

    cropped = stitched.crop((crop_px_left, crop_px_top, crop_px_left + crop_px_w, crop_px_top + crop_px_h))
    buf = BytesIO()
    cropped.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    merc_bounds = {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
    }
    print(f"  Basemap: {tiles_fetched} tiles, {len(b64) / 1024:.0f} KB PNG")
    return b64, merc_bounds


def _fetch_tile(url: str, timeout: int = 10) -> bytes | None:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": TILE_USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if attempt == 2:
                print(f"  WARNING: Tile fetch failed after 3 attempts: {exc}")
                return None
            time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def build_dashboard_html(
    farm_meta: FarmMeta,
    fields: list[FieldRecord],
    weather_records: list[WeatherRecord],
    plotly_js: str,
    basemap_b64: str | None,
    basemap_bounds: dict[str, float] | None,
    basemap_disabled: bool = False,
) -> str:
    farm_name = farm_meta.get("farmName", "Farm")

    farm_data_json = json.dumps({
        "farm": {
            "farmId": farm_meta.get("farmId", "unknown"),
            "farmName": farm_meta.get("farmName", "Farm"),
            "generatedAt": datetime.now(UTC).isoformat() + "Z",
            "basemapAvailable": basemap_b64 is not None,
        },
        "fields": fields,
        "weatherByFieldYear": weather_records,
    }, ensure_ascii=False)

    # Build field options HTML for the custom dropdown
    field_options_html = ""
    for fld in fields:
        fid = fld["fieldId"]
        fname = fld["fieldName"]
        color = fld["color"]
        nodata = " (no data)" if not fld["hasWeatherData"] else ""
        checked = "checked"
        field_options_html += (
            f'<label class="dd-option">'
            f'<input type="checkbox" value="{html.escape(fid)}" {checked}>'
            f'<span class="dd-color" style="background:{color}"></span>'
            f'{html.escape(fname)}{nodata}'
            f'</label>\n'
        )

    # Build year options
    all_years = sorted(set(
        wr["year"] for wr in weather_records
    ))
    default_year = 2025 if 2025 in all_years else (all_years[-1] if all_years else 2025)
    year_options_html = ""
    for yr in all_years:
        checked = "checked" if yr == default_year else ""
        year_options_html += (
            f'<label class="dd-option">'
            f'<input type="checkbox" value="{yr}" {checked}>'
            f'{yr}'
            f'</label>\n'
        )

    # Compute full-farm Mercator extent for map fallback
    all_mx: list[float] = []
    all_my: list[float] = []
    for fld in fields:
        for poly in fld.get("mercatorPolygons", []):
            for pt in poly:
                all_mx.append(pt[0])
                all_my.append(pt[1])
    if all_mx:
        farm_xmin, farm_xmax = min(all_mx), max(all_mx)
        farm_ymin, farm_ymax = min(all_my), max(all_my)
        buf_x = (farm_xmax - farm_xmin) * 0.15 or 1000
        buf_y = (farm_ymax - farm_ymin) * 0.15 or 1000
        farm_xmin -= buf_x
        farm_xmax += buf_x
        farm_ymin -= buf_y
        farm_ymax += buf_y
        farm_extent_js = (
            f'const FARM_EXTENT = {{'
            f'xmin: {farm_xmin}, ymin: {farm_ymin}, '
            f'xmax: {farm_xmax}, ymax: {farm_ymax}}};'
        )
    else:
        farm_extent_js = (
            'const FARM_EXTENT = {'
            'xmin: -1000, ymin: -1000, xmax: 1000, ymax: 1000};'
        )

    # Basemap image
    basemap_img_tag = ""
    if basemap_b64 and basemap_bounds:
        basemap_img_tag = (
            f'<img id="basemap-img" src="data:image/png;base64,{basemap_b64}" '
            f'style="position:absolute;top:0;left:0;width:100%;height:100%;'
            f'object-fit:fill;pointer-events:none;" '
            f'data-xmin="{basemap_bounds["xmin"]}" '
            f'data-ymin="{basemap_bounds["ymin"]}" '
            f'data-xmax="{basemap_bounds["xmax"]}" '
            f'data-ymax="{basemap_bounds["ymax"]}">'
        )

    no_basemap_note = ""
    if basemap_disabled:
        pass
    elif not basemap_b64:
        no_basemap_note = "Satellite imagery unavailable — using neutral background"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grower Field Weather Dashboard — {html.escape(farm_meta.get('farmName', farm_meta.get('farmId', '')))}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f4f5f7; color: #1e293b; line-height: 1.5; }}
.header {{ background: #fff; border-bottom: 1px solid #e2e8f0; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.header h1 {{ font-size: 1.4rem; font-weight: 600; color: #0f172a; }}
.header .subtitle {{ font-size: 0.88rem; color: #64748b; margin-top: 0.2rem; }}
.header .controls {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.75rem; align-items: center; }}
.controls .dd-wrap {{ position: relative; }}
.controls .dd-btn {{ background: #fff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 0.4rem 0.75rem; font-size: 0.82rem; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; min-width: 120px; }}
.controls .dd-btn:hover {{ border-color: #94a3b8; }}
.controls .dd-btn::after {{ content: '▾'; margin-left: auto; font-size: 0.7rem; color: #94a3b8; }}
.controls .dd-panel {{ display: none; position: absolute; top: 100%; left: 0; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.12); z-index: 100; min-width: 200px; max-height: 280px; overflow-y: auto; margin-top: 4px; }}
.controls .dd-panel.open {{ display: block; }}
.dd-option {{ display: flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0.75rem; font-size: 0.82rem; cursor: pointer; }}
.dd-option:hover {{ background: #f1f5f9; }}
.dd-option input[type="checkbox"] {{ accent-color: #2563eb; }}
.dd-color {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
.dd-actions {{ display: flex; gap: 0.25rem; padding: 0.3rem 0.75rem; border-bottom: 1px solid #e2e8f0; }}
.dd-actions button {{ background: none; border: none; color: #2563eb; font-size: 0.78rem; cursor: pointer; padding: 0.15rem 0.3rem; }}
.dd-actions button:hover {{ text-decoration: underline; }}
.selection-summary {{ font-size: 0.78rem; color: #64748b; }}
.reset-btn {{ background: #fff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 0.4rem 0.75rem; font-size: 0.82rem; cursor: pointer; }}
.reset-btn:hover {{ background: #f1f5f9; }}
.no-basemap-note {{ font-size: 0.72rem; color: #94a3b8; font-style: italic; }}
.neutral-bg-label {{ position: absolute; bottom: 8px; right: 10px; font-size: 0.65rem; color: #cbd5e1; font-style: italic; pointer-events: none; z-index: 1; }}
.main {{ display: flex; flex-direction: row; gap: 0.5rem; padding: 0.5rem; height: calc(100vh - 120px); min-height: 500px; }}
.pane {{ flex: 1; background: #fff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; position: relative; min-width: 0; }}
.chart-pane {{ display: flex; flex-direction: column; gap: 0.5rem; }}
.chart-pane .chart-wrap {{ flex: 1; min-height: 0; }}
@media (max-width: 900px) {{ .main {{ flex-direction: column; height: auto; }} .pane {{ min-height: 350px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>Grower Field Weather Dashboard</h1>
  <div class="subtitle">{html.escape(farm_name)} &middot; {len(fields)} fields &middot; Generated {html.escape(datetime.now(UTC).isoformat() + 'Z')}
  {('&middot; <span class="no-basemap-note">' + no_basemap_note + '</span>') if no_basemap_note else ''}</div>
  <div class="controls">
    <div class="dd-wrap" id="field-dd">
      <button class="dd-btn" id="field-dd-btn">Fields ({len(fields)})</button>
      <div class="dd-panel" id="field-dd-panel">
        <div class="dd-actions">
          <button id="field-select-all">Select all</button>
          <button id="field-clear-all">Clear all</button>
        </div>
        {field_options_html}
      </div>
    </div>
    <div class="dd-wrap" id="year-dd">
      <button class="dd-btn" id="year-dd-btn">Years ({len(all_years)})</button>
      <div class="dd-panel" id="year-dd-panel">
        <div class="dd-actions">
          <button id="year-select-all">Select all</button>
          <button id="year-clear-all">Clear all</button>
        </div>
        {year_options_html}
      </div>
    </div>
    <span class="selection-summary" id="selection-summary"></span>
    <button class="reset-btn" id="reset-btn">Reset view</button>
  </div>
</div>
  <div class="main">
    <div class="pane" id="map-container-wrapper" style="position:relative;">
      <div class="pane" id="map-container" style="position:absolute;top:0;left:0;right:0;bottom:0;"></div>
      {('<span class="neutral-bg-label">Neutral background</span>') if not basemap_b64 else ''}
    </div>
  <div class="pane chart-pane">
    <div class="chart-wrap" id="gdd-container"></div>
    <div class="chart-wrap" id="rainfall-container"></div>
  </div>
</div>
<script>
{plotly_js}
</script>
<script>
(function() {{
const FARM_DATA = {farm_data_json};
{farm_extent_js}

// ---- helpers ----
function getSelectedValues(containerId) {{
    const panel = document.getElementById(containerId + '-panel');
    const checks = panel.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checks).map(c => c.value);
}}

function getFieldColor(fieldId) {{
    const f = FARM_DATA.fields.find(f => f.fieldId === fieldId);
    return f ? f.color : '#1f77b4';
}}

function getFieldName(fieldId) {{
    const f = FARM_DATA.fields.find(f => f.fieldId === fieldId);
    return f ? f.fieldName : fieldId;
}}

// ---- custom dropdown toggle ----
document.querySelectorAll('.dd-btn').forEach(btn => {{
    btn.addEventListener('click', function(e) {{
        e.stopPropagation();
        const panel = this.parentElement.querySelector('.dd-panel');
        panel.classList.toggle('open');
    }});
}});
document.addEventListener('click', function(e) {{
    document.querySelectorAll('.dd-panel').forEach(p => {{
        if (!p.parentElement.contains(e.target)) {{
            p.classList.remove('open');
        }}
    }});
}});

// ---- select all / clear all ----
function wireActions(prefix, selectId, clearId) {{
    document.getElementById(selectId).addEventListener('click', function(e) {{
        e.stopPropagation();
        const panel = document.getElementById(prefix + '-dd-panel');
        panel.querySelectorAll('input[type="checkbox"]').forEach(c => c.checked = true);
        onFilterChange();
    }});
    document.getElementById(clearId).addEventListener('click', function(e) {{
        e.stopPropagation();
        const panel = document.getElementById(prefix + '-dd-panel');
        panel.querySelectorAll('input[type="checkbox"]').forEach(c => c.checked = false);
        onFilterChange();
    }});
}}
wireActions('field', 'field-select-all', 'field-clear-all');
wireActions('year', 'year-select-all', 'year-clear-all');

// ---- field DD checkbox click ----
document.querySelectorAll('#field-dd-panel input[type="checkbox"]').forEach(cb => {{
    cb.addEventListener('change', onFilterChange);
}});
document.querySelectorAll('#year-dd-panel input[type="checkbox"]').forEach(cb => {{
    cb.addEventListener('change', onFilterChange);
}});

// ---- weather lookup ----
function getWeather(fieldId, year) {{
    return FARM_DATA.weatherByFieldYear.find(
        w => w.fieldId === fieldId && w.year === parseInt(year)
    );
}}

// ---- build traces ----
function fieldTraces(selectedFields, selectedYears, mapOnly) {{
    const traces = [];
    const allFields = FARM_DATA.fields;
    const isSelected = new Set(selectedFields);

    allFields.forEach((f, idx) => {{
        const selected = isSelected.has(f.fieldId);
        const color = f.color;
        const fillOpacity = selected ? 0.6 : 0.13;
        const lineWidth = selected ? 2.5 : 1.0;
        const name = selected ? f.fieldName : '';

        if (!f.mercatorPolygons || f.mercatorPolygons.length === 0) return;

        f.mercatorPolygons.forEach((ring, ri) => {{
            const xs = ring.map(pt => pt[0]);
            const ys = ring.map(pt => pt[1]);
            traces.push({{
                type: 'scatter',
                mode: 'lines',
                x: xs,
                y: ys,
                fill: 'toself',
                fillcolor: color + (selected ? '99' : '22'),
                line: {{ color: color, width: lineWidth }},
                name: name,
                legendgroup: f.fieldId,
                showlegend: ri === 0 && selected,
                hoverinfo: ri === 0 ? 'text' : 'skip',
                hovertext: ri === 0 ? (f.fieldName + (f.acres != null ? ' (' + f.acres.toFixed(1) + ' ac)' : '')) : '',
                customdata: [f.fieldId],
                selectedpoints: [],
            }});
        }});
    }});
    return traces;
}}

// ---- GDD traces ----
function gddTraces(selectedFields, selectedYears) {{
    const traces = [];
    const isSelected = new Set(selectedFields);
    const yearSet = new Set(selectedYears.map(y => parseInt(y)));

    FARM_DATA.weatherByFieldYear.forEach(w => {{
        if (!isSelected.has(w.fieldId)) return;
        if (!yearSet.has(w.year)) return;
        const color = getFieldColor(w.fieldId);
        const name = getFieldName(w.fieldId) + ' ' + w.year;

        const doys = w.daily.map(d => d.dayOfYear);
        const cumGdd = w.daily.map(d => d.cumulativeGdd);
        const dates = w.daily.map(d => d.date);
        const dailyGdd = w.daily.map(d => d.dailyGdd);

        traces.push({{
            type: 'scatter',
            mode: 'lines',
            x: doys,
            y: cumGdd,
            name: name,
            legendgroup: w.fieldId + '-' + w.year,
            line: {{ color: color, width: 2 }},
            customdata: dates,
            hovertemplate: getFieldName(w.fieldId) + ' ' + w.year +
                '<br>Date: %{{customdata}}<br>DOY: %{{x}}<br>Cumulative GDD: %{{y:.1f}}<extra></extra>',
        }});

        // Frost marker
        traces.push({{
            type: 'scatter',
            mode: 'lines',
            x: [w.lastFrostDoy, w.lastFrostDoy],
            y: [0, 1],
            xaxis: 'x',
            yaxis: 'y',
            yref: 'paper',
            name: name + ' frost',
            legendgroup: w.fieldId + '-' + w.year + '-frost',
            showlegend: false,
            line: {{ color: color, width: 1.5, dash: 'dot' }},
            opacity: 0.6,
            hoverinfo: 'skip',
        }});
    }});

    return traces;
}}

// ---- rainfall traces ----
function rainfallTraces(selectedFields, selectedYears) {{
    const traces = [];
    const isSelected = new Set(selectedFields);
    const yearSet = new Set(selectedYears.map(y => parseInt(y)));

    FARM_DATA.weatherByFieldYear.forEach(w => {{
        if (!isSelected.has(w.fieldId)) return;
        if (!yearSet.has(w.year)) return;
        const color = getFieldColor(w.fieldId);
        const name = getFieldName(w.fieldId) + ' ' + w.year;

        const doys = w.daily.map(d => d.dayOfYear);
        const dailyRain = w.daily.map(d => d.dailyRainfallIn);
        const cumRain = w.daily.map(d => d.cumulativeRainfallIn);
        const dates = w.daily.map(d => d.date);

        // Daily rainfall bars
        traces.push({{
            type: 'bar',
            x: doys,
            y: dailyRain,
            name: name + ' daily',
            legendgroup: w.fieldId + '-' + w.year,
            marker: {{ color: color, opacity: 0.25 }},
            yaxis: 'y',
            customdata: dates,
            hovertemplate: getFieldName(w.fieldId) + ' ' + w.year +
                '<br>Date: %{{customdata}}<br>DOY: %{{x}}<br>Daily rainfall: %{{y:.2f}} in<extra></extra>',
        }});

        // Cumulative rainfall line
        traces.push({{
            type: 'scatter',
            mode: 'lines',
            x: doys,
            y: cumRain,
            name: name + ' cum',
            legendgroup: w.fieldId + '-' + w.year,
            line: {{ color: color, width: 2 }},
            yaxis: 'y2',
            customdata: dates,
            hovertemplate: getFieldName(w.fieldId) + ' ' + w.year +
                '<br>Date: %{{customdata}}<br>DOY: %{{x}}<br>Cumulative rainfall: %{{y:.2f}} in<extra></extra>',
        }});
    }});

    return traces;
}}

// ---- shared X range ----
let sharedXRange = null;
let syncing = false;

// ---- render functions ----
let mapPlot = null;
let gddPlot = null;
let rainPlot = null;

function renderMap(fieldsData) {{
    const container = document.getElementById('map-container');
    const selectedFields = getSelectedValues('field');
    const traces = fieldTraces(selectedFields, []);

    const layout = {{
        dragmode: 'pan',
        hovermode: 'closest',
        margin: {{ l: 0, r: 0, t: 10, b: 0, pad: 0 }},
        xaxis: {{
            visible: false,
            scaleanchor: 'y',
            scaleratio: 1,
            range: [FARM_EXTENT.xmin, FARM_EXTENT.xmax],
        }},
        yaxis: {{
            visible: false,
            range: [FARM_EXTENT.ymin, FARM_EXTENT.ymax],
        }},
        showlegend: false,
        paper_bgcolor: '#fff',
        plot_bgcolor: '#f4f5f7',
        uirevision: 'map',
    }};

    const basemapImg = document.getElementById('basemap-img');
    if (basemapImg) {{
        const xmin = parseFloat(basemapImg.dataset.xmin);
        const ymin = parseFloat(basemapImg.dataset.ymin);
        const xmax = parseFloat(basemapImg.dataset.xmax);
        const ymax = parseFloat(basemapImg.dataset.ymax);
        layout.images = [{{
            source: basemapImg.src,
            x: xmin,
            y: ymax,
            sizex: xmax - xmin,
            sizey: ymax - ymin,
            xref: 'x',
            yref: 'y',
            xanchor: 'left',
            yanchor: 'top',
            sizing: 'stretch',
            layer: 'below',
        }}];
    }}

    const config = {{
        responsive: true,
        displayModeBar: false,
    }};

    if (mapPlot) {{
        Plotly.react(container, {{ data: traces, layout: layout, config: config }});
    }} else {{
        mapPlot = Plotly.newPlot(container, traces, layout, config);
        // Click to toggle field — attach once
        mapPlot.on('plotly_click', function(data) {{
            if (data.points && data.points.length > 0) {{
                const fid = Array.isArray(data.points[0].customdata)
                    ? data.points[0].customdata[0]
                    : data.points[0].customdata;
                if (fid) {{
                    const panel = document.getElementById('field-dd-panel');
                    const cb = panel.querySelector('input[value="' + fid + '"]');
                    if (cb) {{
                        cb.checked = !cb.checked;
                        onFilterChange();
                    }}
                }}
            }}
        }});
    }}
}}

function renderGdd(selectedFields, selectedYears) {{
    const container = document.getElementById('gdd-container');
    const traces = gddTraces(selectedFields, selectedYears);

    if (traces.length === 0) {{
        const layout = {{
            title: {{ text: 'Growing Degree Days', font: {{ size: 14 }} }},
            xaxis: {{ visible: false }},
            yaxis: {{ visible: false }},
            annotations: [{{
                text: 'No data for selected fields and years',
                xref: 'paper', yref: 'paper',
                x: 0.5, y: 0.5, showarrow: false,
                font: {{ color: '#94a3b8', size: 14 }},
            }}],
            paper_bgcolor: '#fff',
            plot_bgcolor: '#f4f5f7',
            margin: {{ l: 50, r: 20, t: 40, b: 50, pad: 4 }},
        }};
        if (gddPlot) {{
            Plotly.react(container, {{ data: [], layout: layout }});
        }} else {{
            gddPlot = Plotly.newPlot(container, [], layout);
        }}
        return;
    }}

    const xRange = sharedXRange || [80, 320];
    const layout = {{
        title: {{ text: 'Growing Degree Days', font: {{ size: 14 }} }},
        xaxis: {{
            title: 'Day of Year',
            range: xRange,
            dtick: 30,
        }},
        yaxis: {{
            title: 'Cumulative GDD (base 10°C)',
        }},
        legend: {{
            orientation: 'h',
            y: 1.02,
            x: 1,
            xanchor: 'right',
            font: {{ size: 10 }},
        }},
        margin: {{ l: 50, r: 20, t: 40, b: 50, pad: 4 }},
        paper_bgcolor: '#fff',
        plot_bgcolor: '#f4f5f7',
        uirevision: 'gdd',
    }};

    const config = {{
        responsive: true,
        displayModeBar: false,
    }};

    if (gddPlot) {{
        Plotly.react(container, {{ data: traces, layout: layout, config: config }});
    }} else {{
        gddPlot = Plotly.newPlot(container, traces, layout, config);
        gddPlot.on('plotly_relayout', function(eventData) {{
            if (syncing) return;
            if (eventData && eventData['xaxis.range[0]'] != null) {{
                syncing = true;
                sharedXRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']];
                if (rainPlot) {{
                    Plotly.relayout(rainPlot, {{
                        'xaxis.range[0]': sharedXRange[0],
                        'xaxis.range[1]': sharedXRange[1],
                    }});
                }}
                syncing = false;
            }}
        }});
    }}
}}

function renderRainfall(selectedFields, selectedYears) {{
    const container = document.getElementById('rainfall-container');
    const traces = rainfallTraces(selectedFields, selectedYears);

    if (traces.length === 0) {{
        const layout = {{
            title: {{ text: 'Rainfall', font: {{ size: 14 }} }},
            xaxis: {{ visible: false }},
            yaxis: {{ visible: false }},
            yaxis2: {{ visible: false }},
            annotations: [{{
                text: 'No data for selected fields and years',
                xref: 'paper', yref: 'paper',
                x: 0.5, y: 0.5, showarrow: false,
                font: {{ color: '#94a3b8', size: 14 }},
            }}],
            paper_bgcolor: '#fff',
            plot_bgcolor: '#f4f5f7',
            margin: {{ l: 50, r: 50, t: 40, b: 50, pad: 4 }},
        }};
        if (rainPlot) {{
            Plotly.react(container, {{ data: [], layout: layout }});
        }} else {{
            rainPlot = Plotly.newPlot(container, [], layout);
        }}
        return;
    }}

    const xRange = sharedXRange || [80, 320];
    const layout = {{
        title: {{ text: 'Rainfall', font: {{ size: 14 }} }},
        xaxis: {{
            title: 'Day of Year',
            range: xRange,
            dtick: 30,
        }},
        yaxis: {{
            title: 'Daily rainfall (in)',
        }},
        yaxis2: {{
            title: 'Cumulative rainfall (in)',
            overlaying: 'y',
            side: 'right',
        }},
        bargap: 0.05,
        legend: {{
            orientation: 'h',
            y: 1.02,
            x: 1,
            xanchor: 'right',
            font: {{ size: 10 }},
        }},
        margin: {{ l: 50, r: 50, t: 40, b: 50, pad: 4 }},
        paper_bgcolor: '#fff',
        plot_bgcolor: '#f4f5f7',
        uirevision: 'rainfall',
    }};

    const config = {{
        responsive: true,
        displayModeBar: false,
        barmode: 'overlay',
    }};

    if (rainPlot) {{
        Plotly.react(container, {{ data: traces, layout: layout, config: config }});
    }} else {{
        rainPlot = Plotly.newPlot(container, traces, layout, config);
        rainPlot.on('plotly_relayout', function(eventData) {{
            if (syncing) return;
            if (eventData && eventData['xaxis.range[0]'] != null) {{
                syncing = true;
                sharedXRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']];
                if (gddPlot) {{
                    Plotly.relayout(gddPlot, {{
                        'xaxis.range[0]': sharedXRange[0],
                        'xaxis.range[1]': sharedXRange[1],
                    }});
                }}
                syncing = false;
            }}
        }});
    }}
}}

function updateSelectionSummary() {{
    const selFields = getSelectedValues('field');
    const selYears = getSelectedValues('year');
    const summary = document.getElementById('selection-summary');
    summary.textContent = selFields.length + ' field(s), ' + selYears.length + ' year(s) selected';
}}

function onFilterChange() {{
    const selFields = getSelectedValues('field');
    const selYears = getSelectedValues('year');
    updateSelectionSummary();
    renderMap(FARM_DATA.fields);
    renderGdd(selFields, selYears);
    renderRainfall(selFields, selYears);
    // Update field DD button text
    document.getElementById('field-dd-btn').textContent = 'Fields (' + selFields.length + ')';
    document.getElementById('year-dd-btn').textContent = 'Years (' + selYears.length + ')';
}}

function resetView() {{
    // Select all fields
    document.querySelectorAll('#field-dd-panel input[type="checkbox"]').forEach(c => c.checked = true);
    // Default year
    const defaultYear = {default_year};
    document.querySelectorAll('#year-dd-panel input[type="checkbox"]').forEach(c => {{
        c.checked = c.value == defaultYear;
    }});
    sharedXRange = null;
    syncing = false;
    onFilterChange();
}}

document.getElementById('reset-btn').addEventListener('click', resetView);

// Initial render
resetView();

}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a self-contained offline weather dashboard for a farm"
    )
    parser.add_argument(
        "--farm-dir",
        default=None,
        help="Explicit path to a farm output directory",
    )
    parser.add_argument(
        "--growers-dir",
        default=None,
        help="Path to growers root (discover farms under it)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Explicit output path for the generated HTML",
    )
    parser.add_argument(
        "--no-basemap",
        action="store_true",
        help="Skip satellite basemap acquisition",
    )
    parser.add_argument(
        "--force-plotly",
        action="store_true",
        help="Force re-download of Plotly bundle",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("  Grower Field Weather Dashboard Generator")
    print("=" * 60)

    # Resolve farm directory
    farm_dir = resolve_farm_dir(
        farm_dir=args.farm_dir,
        growers_dir=args.growers_dir,
    )
    print(f"  Farm directory: {farm_dir}")

    # Read farm data
    farm_meta, fields, weather_records = read_farm_data(farm_dir)
    print(f"  Fields discovered: {len(fields)}")
    print(f"  Weather-bearing field-year records: {len(weather_records)}")

    # Ensure Plotly bundle
    print("  Ensuring Plotly bundle...")
    plotly_js = ensure_plotly_bundle(force=args.force_plotly)

    # Acquire basemap
    basemap_b64: str | None = None
    basemap_bounds: dict[str, float] | None = None
    basemap_disabled = False
    if not args.no_basemap:
        print("  Acquiring satellite basemap...")
        basemap_b64, basemap_bounds = acquire_basemap(fields)
        if basemap_b64 is None:
            print("  (tiles unavailable, using neutral background)")
    else:
        basemap_disabled = True
        print("  Basemap disabled (--no-basemap)")

    # Build HTML
    print("  Generating dashboard HTML...")
    html_content = build_dashboard_html(
        farm_meta, fields, weather_records, plotly_js, basemap_b64, basemap_bounds,
        basemap_disabled=basemap_disabled,
    )

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        farm_slug = farm_meta.get("farmId", farm_dir.name)
        output_path = farm_dir / f"{farm_slug}_dashboard.html"

    # Atomic write
    tmp = output_path.with_suffix(".html.tmp")
    tmp.write_text(html_content, encoding="utf-8")
    tmp.replace(output_path)

    size_kb = output_path.stat().st_size / 1024.0
    print(f"  Dashboard written: {output_path}")
    print(f"  Size: {size_kb:.0f} KB")
    print("=" * 60)


if __name__ == "__main__":
    main()
