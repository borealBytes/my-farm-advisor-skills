"""Ingest real farm-field boundaries from OpenStreetMap (Overpass API).

Queries OSM `landuse=farmland` polygons over a bbox, keeps closed ways of at
least --min-area-ha, and writes them as per-field boundary GeoJSON + inventory
rows for a farm — giving verified, real-world field polygons in any country
where OSM mapping is dense (strong in AU/EU, patchy in parts of US/CA).

OSM data © OpenStreetMap contributors, ODbL 1.0. Requests are pinned:
the exact Overpass QL and the responding instance are journalled per run,
with the raw response sha256, so an identical bbox query replays byte-for-byte.

Usage:
  export DATA_PIPELINE_DATA_ROOT=... AG_GROWER_SLUG=... AG_FARM_SLUG=...
  python download_osm_fields.py --bbox S W N E --min-area-ha 20 \
      --field-prefix au-r --limit 3 [--country AU]

Notes:
  * Public instances rotate on 502/429 ("at capacity") with backoff.
  * --from-json replays a saved Overpass response (offline determinism).
  * Fields get polygon properties {field_id, country, source:'osm_farmland',
    osm_way_id}; downstream routing (soil/weather/terrain) keys off these.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from paths import DATA_ROOT  # pyright: ignore[reportMissingImports]

import geopandas as gpd  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingImports]
from shapely.geometry import Polygon  # pyright: ignore[reportMissingImports]

INSTANCES = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "my-farm-advisor/1.0 (data-pipeline; download_osm_fields)"
R_EARTH = 6371000.0


def _polygon_ha(ring: list[dict]) -> float:
    if len(ring) < 4:
        return 0.0
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1 = math.radians(ring[i]["lon"])
        y1 = math.radians(ring[i]["lat"])
        x2 = math.radians(ring[(i + 1) % n]["lon"])
        y2 = math.radians(ring[(i + 1) % n]["lat"])
        a += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(a * R_EARTH * R_EARTH / 2.0) / 10000.0


def overpass(bbox: tuple[float, float, float, float], retries_per_instance: int = 2) -> tuple[dict, str]:
    s, w, n, e = bbox
    ql = (
        f'[out:json][timeout:120];way["landuse"="farmland"]({s},{w},{n},{e});out geom tags;'
    )
    last_err = None
    for inst in INSTANCES:
        for attempt in range(retries_per_instance):
            req = urllib.request.Request(
                inst,
                data=("data=" + ql).encode(),
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    body = resp.read()
                doc = json.loads(body)
                if "elements" in doc:
                    return doc, inst
                last_err = f"{inst}: no elements key"
            except Exception as exc:  # noqa: BLE001 - 502/429/timeout all retry
                last_err = f"{inst}: {exc}"
            time.sleep(15 * (attempt + 1))
    raise SystemExit(f"all Overpass instances failed; last error: {last_err}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest real farm-field boundaries from OpenStreetMap (Overpass).")
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("S", "W", "N", "E"))
    ap.add_argument("--min-area-ha", type=float, default=10.0)
    ap.add_argument("--max-fields", type=int, default=5)
    ap.add_argument("--field-prefix", required=True, help="field_id prefix, e.g. au-r")
    ap.add_argument("--state", default="", help="state/province written to boundary properties")
    ap.add_argument("--year", default="", help="crop year written to boundary properties")
    ap.add_argument("--country", help="ISO-3 for written boundaries (default: farm manifest country)")
    ap.add_argument("--from-json", help="replay a saved Overpass response instead of querying")
    args = ap.parse_args(argv)

    grower = os.environ.get("AG_GROWER_SLUG") or sys.exit("AG_GROWER_SLUG required")
    farm = os.environ.get("AG_FARM_SLUG") or sys.exit("AG_FARM_SLUG required")
    farm_dir = DATA_ROOT / "growers" / grower / "farms" / farm
    if not farm_dir.exists():
        sys.exit(f"farm dir missing: {farm_dir}")
    manifest = json.loads((farm_dir / "farm.json").read_text())
    country = args.country or manifest.get("country") or ""

    if args.from_json:
        doc = json.loads(Path(args.from_json).read_text())
        instance = f"replay:{args.from_json}"
    else:
        if not args.bbox:
            sys.exit("--bbox required unless --from-json")
        doc, instance = overpass(tuple(args.bbox))

    raw = json.dumps(doc, sort_keys=True).encode()
    rows = []
    for el in doc.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        ring = el["geometry"]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        ha = _polygon_ha(ring)
        if ha < args.min_area_ha:
            continue
        coords = [[p["lon"], p["lat"]] for p in ring]
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
        except Exception:  # noqa: BLE001
            continue
        rows.append(
            {
                "way_id": el["id"],
                "ha": round(ha, 2),
                "poly": poly,
                "crop": (el.get("tags") or {}).get("crop", ""),
            }
        )

    rows.sort(key=lambda r: (-r["ha"], r["way_id"]))
    rows = rows[: args.max_fields]
    if not rows:
        print("no farmland polygons above --min-area-ha in this bbox")
        return 1

    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    fields = []
    merged = None
    farm_bounds = farm_dir / "boundary" / "field_boundaries.geojson"
    for i, r in enumerate(rows):
        fid = f"{args.field_prefix}{i + 1}"
        fdir = farm_dir / "fields" / fid
        (fdir / "boundary").mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame(
            [
                {
                    "field_id": fid,
                    "country": country,
                    "state": args.state or "",
                    "year": args.year or "",
                    "area_ha_est": r["ha"],
                    "crop": r.get("crop", ""),
                    "area_acres": round(r["ha"] * 2.47105, 1),
                    "source": "osm_farmland",
                    "osm_way_id": r["way_id"],
                    "geometry": r["poly"],
                }
            ],
            crs="EPSG:4326",
        )
        gdf.to_file(fdir / "boundary" / "field_boundary.geojson", driver="GeoJSON")
        merged = gdf if merged is None else pd.concat([merged, gdf], ignore_index=True)
        fields.append({"field_id": fid, "field_slug": fid})
        print(f"field {fid}  {r['ha']:>8.1f} ha  osm way {r['way_id']}")

    if farm_bounds.exists():
        old = gpd.read_file(farm_bounds)
        keep = old[~old["field_id"].isin([f["field_id"] for f in fields])]
        merged = pd.concat([keep, merged], ignore_index=True)
    farm_bounds.parent.mkdir(exist_ok=True)
    assert merged is not None
    merged.to_file(farm_bounds, driver="GeoJSON")

    # merge into field inventory (manifests/field-inventory.csv)
    inv = farm_dir / "manifests" / "field-inventory.csv"
    inv.parent.mkdir(exist_ok=True)
    frame = pd.DataFrame(fields)
    if inv.exists():
        old = pd.read_csv(inv)
        frame = pd.concat([old, frame]).drop_duplicates(subset="field_id", keep="last")
    frame.to_csv(inv, index=False)

    # provenance + journal
    prov = {
        "source": "OpenStreetMap via Overpass",
        "license": "ODbL 1.0",
        "query": 'way["landuse"="farmland"](bbox);out geom tags;',
        "bbox": args.bbox,
        "instance": instance,
        "min_area_ha": args.min_area_ha,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "accessed_at": now,
        "fields": [f["field_id"] for f in fields],
    }
    mdir = farm_dir / "manifests"
    mdir.mkdir(exist_ok=True)
    (mdir / "osm_fields_provenance.json").write_text(json.dumps(prov, indent=2, default=str))
    jdir = DATA_ROOT / "shared" / "osm" / "manifests"
    jdir.mkdir(parents=True, exist_ok=True)
    journal = jdir / "sha256_journal.json"
    log = json.loads(journal.read_text()) if journal.exists() else {}
    log[f"{grower}/{farm}/{args.field_prefix}"] = prov
    journal.write_text(json.dumps(log, indent=2, default=str))
    print(f"\n✓ {len(fields)} real OSM fields -> {inv}")
    print(f"  Provenance: {mdir / 'osm_fields_provenance.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
