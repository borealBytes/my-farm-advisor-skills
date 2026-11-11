#!/usr/bin/env python3
"""ESA WorldCereal Reference Data Module (RDM) client — no account needed.

Public reference datasets at https://ewoc-rdm-api.iiasa.ac.at are anonymous:
  GET /collections                       -> all public collections (bbox, time)
  GET /collections/{id}/items            -> features; &Bbox / &ValidityTime /
                                            &EwocCodes filters, SkipCount paging
Every feature carries an EWOC crop/land-cover code; names come from the official
LC/CT legend CSV (vendored under data/ewoc_legend.csv).

Use in the best-available-data ladder: national official layers (CDL/ACI) for
years they cover, RDM harmonized in-situ points for validation, then the
default local model for every year as the always-available fallback.

Example:
    python download_rdm_reference.py --farm demo-ca --field on-r1 \
        --start 2016-06-01 --end 2018-06-01
"""
import argparse, csv, datetime as dt, json, os, sys
import geopandas as gpd
import requests
from pathlib import Path
from shapely.geometry import shape

API = os.environ.get("EWOC_RDM_API", "https://ewoc-rdm-api.iiasa.ac.at")
LEGEND_URL = ("https://auxdata.terrascope.be/worldcereal/legend/"
              "WorldCereal_LC_CT_legend_latest.csv")
_HERE = Path(__file__).resolve().parent
LEGEND = _HERE.parent / "data" / "ewoc_legend.csv"


def _legend() -> dict:
    """ewoc_code(int) -> (label_full, LC/CT class, quality-relevant info)."""
    if not LEGEND.exists():
        LEGEND.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(LEGEND_URL, timeout=120)
        r.raise_for_status()
        LEGEND.write_bytes(r.content)
    out = {}
    with open(LEGEND, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            code = row["ewoc_code"].replace("-", "")
            try:
                out[int(code)] = (row["label_full"], row["LC_code"])
            except ValueError:
                continue
    return out


def _root() -> Path:
    d = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not d:
        raise SystemExit("set DATA_PIPELINE_DATA_ROOT")
    return Path(d) / "data-pipeline" / "growers" / \
        os.environ.get("AG_GROWER_SLUG", "demo-grower") / "farms"


def public_collections(timeout=120):
    items, skip = [], 0
    while True:
        r = requests.get(f"{API}/collections",
                         params={"SkipCount": skip, "MaxResultCount": 200},
                         timeout=timeout).json()
        items += r["items"]
        skip += len(r["items"])
        if skip >= r["totalCount"] or not r["items"]:
            return items


def _overlap(bbox, lo1, la1, lo2, la2):
    for b in bbox:
        if b[0] < lo2 and b[2] > lo1 and b[1] < la2 and b[3] > la1:
            return True
    return False


def fetch(cid, bbox, t_start, t_end, limit=5000, timeout=120):
    feats, skip = [], 0
    params = {"SkipCount": skip, "MaxResultCount": 200}
    base = (f"{API}/collections/{cid}/items"
            f"?Bbox={bbox[0]}&Bbox={bbox[1]}&Bbox={bbox[2]}&Bbox={bbox[3]}"
            f"&ValidityTime.Start={t_start}T00%3A00%3A00Z"
            f"&ValidityTime.End={t_end}T00%3A00%3A00Z")
    while True:
        r = requests.get(f"{base}&SkipCount={skip}&MaxResultCount=200",
                         timeout=timeout)
        if r.status_code != 200:
            print(f"  {cid}: HTTP {r.status_code}", file=sys.stderr)
            break
        j = r.json()
        feats += j.get("features", [])
        skip += j.get("NumberReturned", 0)
        if skip >= j.get("NumberMatched", 0) or not j.get("features"):
            break
        if skip >= limit:
            break
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--farm", required=True)
    ap.add_argument("--field", required=True)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2026-01-01")
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to these collectionIds")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                    default=None, help="override search box (regional demo)")
    a = ap.parse_args()

    fdir = _root() / a.farm / "fields" / a.field
    if a.bbox:
        bbox = tuple(a.bbox)
    else:
        fb = gpd.read_file(fdir / "boundary" / "field_boundary.geojson").to_crs(4326)
        bbox = tuple(round(v, 5) for v in fb.total_bounds)
    print(f"{a.field} bbox(w,s,e,n) = {bbox}  window {a.start}..{a.end}")

    leg = _legend()
    out_dir = fdir / "worldcereal_rdm"
    out_dir.mkdir(exist_ok=True)
    summary = []
    for c in public_collections():
        if c.get("accessType") != "Public":
            continue
        if a.only and c["collectionId"] not in a.only:
            continue
        ext = c["extent"]
        if not _overlap(ext["spatial"]["bbox"], *bbox):
            continue
        tint = ext["temporal"]["interval"]
        tmin = min(iv[0][:10] for iv in tint)
        tmax = max(iv[-1][:10] for iv in tint)
        if tmax < a.start or tmin > a.end:
            continue
        feats = fetch(c["collectionId"], bbox, a.start, a.end)
        if not feats:
            continue
        if not feats:
            continue
        rows = []
        for ft in feats:
            p = ft.get("properties", {})
            code = p.get("ewoc_code")
            lab, lcc = leg.get(int(code), ("?", "?")) if code else ("?", "?")
            g = ft.get("geometry")
            if not g:
                continue
            rows.append({"geometry": shape(g), "ewoc_code": code,
                         "crop_label": lab, "collection": c["collectionId"],
                         "valid_time": p.get("valid_time"),
                         "q_lc": p.get("quality_score_lc"),
                         "q_ct": p.get("quality_score_ct")})
        gj = gpd.GeoDataFrame(rows, crs="EPSG:4326")
        gj.to_file(out_dir / f"rdm_{c['collectionId']}.geojson",
                   driver="GeoJSON")
        labs = gj.crop_label.value_counts().to_dict()
        summary.append({"collection": c["collectionId"], "title": c["title"],
                        "n": len(gj), "labels": labs,
                        "conf_ct": c.get("confidenceCropType")})
        print(f"  {c['collectionId']}: {len(gj)} features | {labs}")

    with open(out_dir / "rdm_summary.json", "w") as f:
        json.dump({"field": a.field, "bbox": bbox, "window": [a.start, a.end],
                   "hits": summary,
                   "api": API, "retrieved": dt.date.today().isoformat()}, f,
                  indent=1)
    print(f"WROTE {out_dir}/rdm_summary.json ({len(summary)} collections)")


if __name__ == "__main__":
    main()
