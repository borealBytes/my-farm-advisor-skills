#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false
"""ingest_user_boundaries.py — user-boundary ingest gate (Hermes plugin onboarding exec leg).

INVOCATION CONTRACT (frozen by myfarm-hermes-plugin seeder.boundary_enqueue,
red-team 2026-11-13; normative source: data-pipeline AGENTS.md @ ce7f59b,
"Plugin onboarding — user-boundary ingest contract"):

  argv (plugin always passes all three):
      --data-root <writer data root>          absolute; becomes DATA_PIPELINE_DATA_ROOT
      --job-id    <64-hex sha256 of the canonical geojson>
      --geojson   <path to canonical FeatureCollection JSON on disk>
  env:
      DATA_PIPELINE_DATA_ROOT equals --data-root; the FLAG wins on divergence
      and the divergence is warned on stderr.
  exit codes:
      0  = success (plugin advances the job checkpoint)
      !=0 = failure; the plugin surfaces stderr verbatim — stderr therefore
      carries human sentences naming every rejected feature, never a traceback.
  streams:
      stdout = machine-journalable `checkpoint=...` lines only
      stderr = human sentences

Everything else below is operator-facing and optional:

  --grower-slug / --farm-slug   target records (defaults: default-grower /
                                default-farm, the same defaults as
                                run_farm_pipeline.py and assign_field_fips.py)
  --counties-dir                inject a county lookup layer root (offline
                                tests/fixtures; default is the shared geoadmin
                                l2_counties dir the assign_field_fips.py lookup uses)
  --handoff {detach,sync,off}   run_farm_pipeline.py handoff mode (default:
                                detach — the legs keep running in the background
                                and the pane polls the grower manifest; sync
                                waits for the operator; off = gate only)
  --prune-missing               explicit opt-in: delete previously-uploaded
                                fields absent from THIS upload (never prunes
                                other sources' fields, and never runs implicitly)

Behavioral law (contract bullets, restated): input GeoJSON FeatureCollection,
EPSG:4326 closed rings; per-feature ``country`` + ``field_id`` hard-required;
``state``/``year``/``crop``/``area_ha_est``/``area_acres`` optional; areas are
recomputed via an equal-area reprojection (EPSG:6933) and user-supplied areas
are journaled, never routed on. The write set is exactly the repository
contract in references/field-boundary-sources.md (farm + per-field boundary
GeoJSONs, field-inventory.csv, user_upload_fields_provenance.json +
sha256_journal.json, farm.json country/state), merged by ``field_id`` and never
wholesale-replaced, with ``source=user_upload`` per feature. Re-posting the
same sha256 is a no-op. Wrong-country uploads fail VISIBLY at the
counties_matched checkpoint — before any write, before any downstream leg can
consume the routing key. This script is a validation/provenance/echo GATE over
the existing refresh path (farm_dashboard.py refresh consumes the contract
files as-is), not a second code path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# TIGER/GADM county geojsons contain multi-megabyte multipolygons; GDAL's
# default object guard rejects them on read (same guard as assign_field_fips.py).
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../data-pipeline/src/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

# ---------------------------------------------------------------- constants

EPSG_4326 = "EPSG:4326"
EQUAL_AREA_CRS = "EPSG:6933"  # World Cylindrical Equal Area (WGS84) — global, offline

_COUNTRY_ALIASES = {
    "USA": "US",
    "U.S.A.": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "CAN": "CA",
    "CANADA": "CA",
}

# county layer file stem -> ISO-2 (mirrors how download_geoadmin.py names layers)
_LAYER_COUNTRY_BY_STEM = {"counties_usa": "US", "counties_canada": "CA"}
_COUNTIES_FILENAME_RE = re.compile(r"^counties_(?P<iso>[A-Za-z]+)\.geojson$")

# US state FIPS -> USPS abbreviation (TIGER l2 frames carry state_fips only).
STATE_ABBR_BY_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}
_STATE_NAME_BY_ABBR = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "ON": "Ontario", "QC": "Quebec",
}

_INVENTORY_HEADER = "field_id,field_slug"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _out(line: str) -> None:
    """Machine-journalable stdout line."""
    print(line, flush=True)


def _fail(stage: str, *sentences: str) -> int:
    """Human sentences to stderr (plugin surfaces them), machine line to stdout."""
    for sentence in sentences:
        print(sentence, file=sys.stderr)
    _out(f"checkpoint=failed stage={stage}")
    return 1


# ---------------------------------------------------------------- validation


def _rings_of(geometry: dict) -> list | None:
    """All coordinate rings of a Polygon/MultiPolygon, or None if not a polygon type."""
    gtype = geometry.get("type")
    if gtype == "Polygon":
        return geometry.get("coordinates") or []
    if gtype == "MultiPolygon":
        return [ring for poly in geometry.get("coordinates") or [] for ring in poly]
    return None


def _check_crs_declared(doc: dict, feature_props: dict, label: str, errors: list[str]) -> None:
    """4326 assumed: absent CRS member is fine; a present one must say 4326.

    Covers the top-level ``crs`` member, per-feature ``crs``/``epsg`` properties,
    and a ``filename`` field whose name carries an EPSG code (the plugin gate's
    payload can name the source file; ``fields_epsg_3857.geojson`` must reject).
    """
    candidates: list[tuple[str, object]] = []
    for key in ("crs", "epsg"):
        if key in doc:
            candidates.append(("document." + key, doc[key]))
        if key in feature_props:
            candidates.append((f"{label}.{key}", feature_props[key]))
    for key in ("filename", "filename_crs"):
        for source, bag in (("document", doc), (label, feature_props)):
            value = bag.get(key)
            if isinstance(value, str):
                codes = re.findall(r"(?i)epsg[:_/-]?(\d+)", value)
                for code in codes:
                    candidates.append((f"{source}.{key}", f"EPSG:{code}"))
    for where, value in candidates:
        text = json.dumps(value, default=str).upper()
        if "4326" in text or "GEOGCRS" in text and "4326" in text:
            continue
        errors.append(
            f"{where}: declared CRS {value!r} is not EPSG:4326 — this ingest "
            "accepts unprojected WGS84 lon/lat only; reproject the upload first."
        )


def _validate_feature(index: int, feature: object, doc: dict, errors: list[str]) -> tuple[str, dict, dict] | None:
    """Return (field_id, properties, geometry) when the feature is valid; append
    named sentences to *errors* otherwise. Re-runs INDEPENDENTLY of the plugin
    gate (defense in depth)."""
    label = f"feature {index}"
    if not isinstance(feature, dict):
        errors.append(f"{label}: not a JSON object")
        return None
    props = feature.get("properties")
    props = props if isinstance(props, dict) else {}
    fid = props.get("field_id")
    if isinstance(fid, str) and fid.strip():
        label = f"feature {index} ({fid.strip()})"
    for key in ("field_id", "country"):
        value = props.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"{label}: missing required property '{key}' — every feature "
                f"must carry {key} (hard requirement of the ingest contract)"
            )
    _check_crs_declared(doc, props, label, errors)
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        errors.append(f"{label}: missing geometry object")
        return None
    rings = _rings_of(geom)
    if rings is None:
        errors.append(
            f"{label}: geometry must be Polygon or MultiPolygon, not "
            f"{geom.get('type')!r} — non-polygon shapes carry no field area"
        )
        return None
    if not rings:
        errors.append(f"{label}: polygon has no rings")
        return None
    for r_idx, ring in enumerate(rings):
        if not isinstance(ring, list) or len(ring) < 4:
            errors.append(
                f"{label}: ring {r_idx} needs >= 4 vertices (a closed GeoJSON "
                "ring repeats its first vertex)"
            )
            continue
        if list(ring[0])[:2] != list(ring[-1])[:2]:
            errors.append(
                f"{label}: ring {r_idx} is open — first vertex != last vertex; "
                "close the ring before upload"
            )
        for p_idx, pos in enumerate(ring):
            ok = (
                isinstance(pos, list) and len(pos) >= 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pos[:2])
            )
            if ok:
                ok = -180.0 <= pos[0] <= 180.0 and -90.0 <= pos[1] <= 90.0
            if not ok:
                errors.append(
                    f"{label}: ring {r_idx} vertex {p_idx} is not a WGS84 "
                    "[lon, lat] pair in range — projected coordinates "
                    "(metres) in the upload? This ingest is EPSG:4326 only"
                )
                break
    if any(e.startswith(label) for e in errors):
        return None
    return str(props["field_id"]).strip(), props, geom


def validate_feature_collection(doc: object) -> list[str]:
    """Independent re-validation of the plugin gate (defense in depth).
    Returns the list of named human sentences; empty list == accepted."""
    errors: list[str] = []
    if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection":
        return ["upload is not a GeoJSON FeatureCollection — the boundary "
                "ingest takes one FeatureCollection of field polygons"]
    features = doc.get("features")
    if not isinstance(features, list) or not features:
        return ["FeatureCollection carries no features — upload at least one field polygon"]
    seen: dict[str, int] = {}
    for index, feature in enumerate(features):
        got = _validate_feature(index, feature, doc, errors)
        if got:
            fid = got[0]
            if fid in seen:
                errors.append(
                    f"feature {index} ({fid}): duplicate field_id — one feature "
                    "per field_id per upload"
                )
            seen[fid] = index
    return errors


# ---------------------------------------------------------------- area math


def _area_ha(geometry: dict) -> float:
    """Equal-area recomputation of a validated Polygon/MultiPolygon (ha).

    pyproj (a declared dependency of the data-pipeline stack, and what the CSB
    ingest relies on for the same law: 'projected CRS is equal-area,
    poly.area/10000 is directly ha'). EPSG:6933 is global so non-US uploads
    are honest too."""
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as shp_transform

    transformer = Transformer.from_crs(EPSG_4326, EQUAL_AREA_CRS, always_xy=True)

    def _project(x, y):
        return transformer.transform(x, y)

    projected = shp_transform(_project, shape(geometry))
    return projected.area / 10000.0


# ---------------------------------------------------------------- county lookup


def _country_for_layer_file(path: Path) -> str:
    stem = path.stem
    if stem in _LAYER_COUNTRY_BY_STEM:
        return _LAYER_COUNTRY_BY_STEM[stem]
    match = _COUNTIES_FILENAME_RE.match(path.name)
    if match and len(match.group("iso")) == 3:
        return match.group("iso").upper()
    return stem.upper()


def _county_echo(row: dict, layer_file: str, geoadmin_admin) -> tuple[str, str, str]:
    """(county, state, country) human-readable echo for one assigned county row.

    country: an explicit ``country`` column when the layer carries one (GADM
    layers do), else the layer filename (counties_usa -> US). state: explicit
    state_name/state_code, else TIGER state_fips -> USPS, else Canada PRUID ->
    province abbreviation via geoadmin_admin's own table. NaN cells (layers
    concatenated with differing columns) must not masquerade as values.
    """
    def _clean(key: str) -> str:
        value = row.get(key)
        if value is None or str(value).strip().lower() in {"", "nan"}:
            return ""
        return str(value).strip()

    country = _clean("country").upper() or _country_for_layer_file(Path(layer_file))
    state = (_clean("state_code") or _clean("state_name")).upper()
    if not state:
        state_fips = _clean("state_fips")
        if len(state_fips) == 2:
            state = STATE_ABBR_BY_FIPS.get(state_fips, "")
        elif state_fips.startswith("CA") and len(state_fips) == 4:
            abbr = getattr(geoadmin_admin, "CAN_ABBR_BY_PRUID", {})
            state = abbr.get(state_fips[2:], "")
    county = _clean("county_name_full") or _clean("county_name")
    return county, state, country


def _states_agree(declared: str, derived: str) -> bool:
    if not declared or not derived:
        return True  # optional property; absence can't contradict
    declared_n = declared.strip().upper()
    derived_n = derived.strip().upper()
    if declared_n == derived_n:
        return True
    full = _STATE_NAME_BY_ABBR.get(derived_n, "").upper()
    if full and declared_n == full:
        return True
    return False


def match_counties(
    features: list[tuple[str, dict, dict]],
    slugs: dict[str, str],
    counties_dir: Path,
) -> tuple[dict[str, dict], list[str]]:
    """FIPS assignment via the assign_field_fips.py lookup mechanism: the same
    ``geoadmin_admin.assign_fields_to_counties`` the script drives, on the same
    shared geoadmin l2_counties layers (USA + Canada, concatenated verbatim as
    assign_field_fips.py does). Returns per-field echo info and named failures."""
    layer_files = [counties_dir / "counties_usa.geojson"]
    for extra in sorted(counties_dir.glob("counties_*.geojson")):
        if extra not in layer_files:
            layer_files.append(extra)
    present = [p for p in layer_files if p.exists()]
    if not present:
        raise FileNotFoundError(
            f"county lookup layer missing under {counties_dir}: no counties_*.geojson. "
            "Real fix: run `python src/scripts/ingest/download_geoadmin.py --levels "
            "l2_counties` (add `--gadm-iso <ISO3>` per non-US country), or point "
            "--counties-dir at an installed layer root."
        )

    import geopandas as gpd
    import pandas as pd

    from reporting_bootstrap import ensure_skill_path

    ensure_skill_path("geoadmin-admin")
    geoadmin_admin = importlib.import_module("geoadmin_admin")

    frames = []
    for path in present:
        frame = gpd.read_file(path)
        frame["_layer_file"] = path.name
        frames.append(frame)
    # concatenate the county layers exactly as assign_field_fips.py does
    counties = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326"
    )
    fields = gpd.GeoDataFrame.from_features(
        [
            {"type": "Feature", "properties": {"field_id": fid}, "geometry": geom}
            for fid, _props, geom in features
        ],
        crs=EPSG_4326,
    )
    mapping_df, _ambiguity_df = geoadmin_admin.assign_fields_to_counties(
        fields, counties, field_slug_map=slugs
    )
    county_rows = counties.set_index("fips")
    echoes: dict[str, dict] = {}
    failures: list[str] = []
    declared = {fid: props for fid, props, _g in features}
    for record in mapping_df.to_dict("records"):
        fid = str(record.get("field_id", ""))
        props = declared.get(fid, {})
        want_country = _COUNTRY_ALIASES.get(
            str(props.get("country", "")).strip().upper(),
            str(props.get("country", "")).strip().upper(),
        )
        fips = str(record.get("fips", ""))
        if not fips or record.get("ambiguity_reason") == "no_county_match":
            failures.append(
                f"field {fid} ({props.get('field_name') or 'unnamed'}): geometry matches no "
                f"county polygon in the installed admin layers — declared country "
                f"{props.get('country')!r}; wrong-country uploads (or coverage gaps) fail here, "
                "before any downstream leg consumes the routing key"
            )
            continue
        layer_file = str(county_rows.loc[fips].get("_layer_file", "counties_usa.geojson"))
        county, state, country = _county_echo(
            county_rows.loc[fips].to_dict(), layer_file, geoadmin_admin
        )
        if country != want_country:
            failures.append(
                f"field {fid}: declared country {props.get('country')!r} but the geometry "
                f"sits in {county}, {state}, {country} — wrong-country uploads fail at the "
                "counties_matched checkpoint; fix the country property or the geometry"
            )
            continue
        if not _states_agree(str(props.get("state", "")), state):
            failures.append(
                f"field {fid}: declared state {props.get('state')!r} but the geometry "
                f"sits in {county}, {state}, {country} — sanity-check county names "
                "against the farm's state before accepting fields"
            )
            continue
        echoes[fid] = {
            "fips": fips,
            "county_fips": str(record.get("county_fips", "")),
            "county": county,
            "state": state,
            "country": country,
            "assignment_method": str(record.get("assignment_method", "")),
        }
    return echoes, failures


# ---------------------------------------------------------------- write set


def _feature_json(fid: str, props: dict, geom: dict, area_ha: float, echo: dict) -> dict:
    routed = {
        "field_id": fid,
        "country": str(props["country"]).strip().upper(),
        "source": "user_upload",
    }
    for key in ("state", "year", "crop"):
        if props.get(key) not in (None, ""):
            routed[key] = props[key]
    routed["area_ha_est"] = round(area_ha, 2)
    routed["area_acres"] = round(area_ha * 2.47105, 1)
    routed["county"] = echo["county"]
    routed["county_fips"] = echo["county_fips"]
    routed["fips"] = echo["fips"]
    if echo.get("state"):
        routed["state"] = echo["state"]
    return {"type": "Feature", "properties": routed, "geometry": geom, "id": fid}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _merge_features(existing: dict | None, new_features: list[dict], prune_ids: set[str] | None) -> dict:
    """Merge by field_id — features of other sources and untouched uploads
    survive verbatim; uploaded field_ids are replaced. Never wholesale-replace."""
    keep: dict[str, dict] = {}
    order: list[str] = []
    for feature in (existing or {}).get("features", []) if isinstance(existing, dict) else []:
        props = feature.get("properties") or {}
        fid = str(props.get("field_id", ""))
        if not fid:
            continue
        keep[fid] = feature
        order.append(fid)
    for feature in new_features:
        fid = feature["properties"]["field_id"]
        if fid not in keep:
            order.append(fid)
        keep[fid] = feature
    if prune_ids is not None:
        order = [fid for fid in order if fid in keep and (fid in prune_ids or keep[fid].get("properties", {}).get("source") != "user_upload")]
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": EPSG_4326}},
        "features": [keep[fid] for fid in order],
    }


def _merge_inventory(existing_path: Path, rows: list[tuple[str, str]], drop_ids: set[str] | None) -> list[tuple[str, str]]:
    merged: dict[str, str] = {}
    if existing_path.exists():
        lines = existing_path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) == 2 and parts[0].strip():
                merged[parts[0].strip()] = parts[1].strip()
    for fid, slug in rows:
        merged[fid] = slug
    if drop_ids:
        merged = {fid: slug for fid, slug in merged.items() if fid not in drop_ids}
    return list(merged.items())


# ---------------------------------------------------------------- handoff


def _pipeline_command(scripts_dir: Path, grower_slug: str, farm_slug: str, boundaries: Path) -> list[str]:
    """run_farm_pipeline.py MINUS the field-sampling leg. The orchestrator
    itself already passes --allow-live-downloads to the DEM step, so the
    wrapper must not re-add it (contract law) — note its absence here."""
    return [
        sys.executable,
        str(scripts_dir / "run_farm_pipeline.py"),
        "--grower-slug", grower_slug,
        "--farm-slug", farm_slug,
        "--boundaries", str(boundaries),
        "--skip-field-sampling",
    ]


# ---------------------------------------------------------------- main


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest user-uploaded field boundaries (plugin onboarding exec leg)")
    parser.add_argument("--data-root", default=None, help="writer data root (absolute); preferred over DATA_PIPELINE_DATA_ROOT")
    parser.add_argument("--job-id", default=None, help="64-hex sha256 of the canonical GeoJSON (plugin-computed)")
    parser.add_argument("--geojson", required=True, help="path to the canonical FeatureCollection JSON on disk")
    parser.add_argument("--grower-slug", default="default-grower")
    parser.add_argument("--farm-slug", default="default-farm")
    parser.add_argument("--counties-dir", default=None, help="override the shared geoadmin l2_counties layer root (offline fixtures)")
    parser.add_argument("--handoff", choices=("detach", "sync", "off"), default="detach")
    parser.add_argument("--prune-missing", action="store_true", help="delete previously user-uploaded fields absent from this upload (explicit opt-in; never implicit)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    env_root = os.environ.get("DATA_PIPELINE_DATA_ROOT", "").strip()
    flag_root = (str(Path(args.data_root).expanduser()) if args.data_root else "").strip()
    if flag_root and env_root and Path(env_root).expanduser() != Path(flag_root):
        print(
            f"warning: DATA_PIPELINE_DATA_ROOT={env_root!r} diverges from --data-root="
            f"{flag_root!r}; the flag wins (invocation contract)",
            file=sys.stderr,
        )
    resolved_root = flag_root or env_root
    if not resolved_root:
        return _fail("startup",
                     "no data root: pass --data-root <abs path> or export DATA_PIPELINE_DATA_ROOT "
                     "(see data-pipeline/scripts/install.sh --data-root)")
    if not Path(resolved_root).is_absolute():
        return _fail("startup", f"data root must be absolute, got {resolved_root!r}")
    os.environ["DATA_PIPELINE_DATA_ROOT"] = str(Path(resolved_root).expanduser())

    # Spill self-verification (fossil law, 2026-11-14): when the boundaries
    # file is named <64-hex>.geojson the name IS the content hash — the
    # plugin door spills exactly that way. A truncated or rewritten spill
    # must fail loudly at the door, not propagate a corpse's geometry;
    # a mismatch is never silently re-spilled over top (restitution belongs
    # to the poster, not the reader). Non-hex names (operator-authored
    # files, tests) skip the check.
    geo_path = Path(args.geojson)
    stem = geo_path.stem
    if len(stem) == 64 and all(c in "0123456789abcdef" for c in stem.lower()):
        got = hashlib.sha256(geo_path.read_bytes()).hexdigest()
        if got != stem.lower():
            return _fail(
                "startup",
                f"spill checksum mismatch: sha256({geo_path}) = {got} != name {stem}"
                " — truncated or altered spill; re-post the boundary",
            )

    # Deferred imports: lib.paths/reporting_bootstrap resolve DATA_PIPELINE_DATA_ROOT at import.
    from lib import naming
    from lib.paths import (
        DATA_ROOT,
        farm_boundary_path,
        farm_dir,
        farm_logs_dir,
        farm_manifest_dir,
        field_boundary_path,
        validate_path_slug,
    )
    from lib.runtime_paths import resolve_runtime_paths

    scripts_dir = resolve_runtime_paths().runtime_scripts
    if not scripts_dir.exists():
        scripts_dir = _SCRIPTS_DIR  # pre-install checkout runs

    geojson_path = Path(args.geojson).expanduser()
    if not geojson_path.is_absolute():
        geojson_path = Path.cwd() / geojson_path
    if not geojson_path.is_file():
        return _fail("startup", f"geojson payload not found: {geojson_path}")
    raw = geojson_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if args.job_id:
        if not re.fullmatch(r"[0-9a-f]{64}", args.job_id):
            print(f"warning: --job-id {args.job_id!r} is not a 64-hex sha256; trusting the computed file sha", file=sys.stderr)
        elif args.job_id != sha:
            print(
                f"warning: --job-id {args.job_id} != sha256 of the payload on disk {sha}; "
                "the computed sha256 governs idempotency",
                file=sys.stderr,
            )

    journal_path = DATA_ROOT / "shared" / "user_upload" / "manifests" / "sha256_journal.json"
    journal = _read_json(journal_path, {})
    if not isinstance(journal, dict):
        journal = {}
    if sha in journal or (args.job_id and args.job_id in journal):
        _out(f"checkpoint=accepted job_id={sha} noop=true reason=already-ingested")
        print(f"no-op: sha256 {sha} is already in the ingest journal; write set untouched", file=sys.stderr)
        return 0

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _fail("accepted", f"upload is not valid JSON: {exc}")

    errors = validate_feature_collection(doc)
    if errors:
        return _fail("accepted", *errors)

    parsed: list[tuple[str, dict, dict]] = []
    slugs: dict[str, str] = {}
    seen_slugs: dict[str, str] = {}
    for index, feature in enumerate(doc["features"]):
        fid = str(feature["properties"]["field_id"]).strip()
        slug = naming.field_slug_from_id(fid)
        try:
            validate_path_slug(slug, "field_slug")
        except ValueError as exc:
            errors.append(f"feature {index} ({fid}): field_id produced an unsafe slug — {exc}")
            continue
        if slug in seen_slugs and seen_slugs[slug] != fid:
            errors.append(f"feature {index} ({fid}): field_slug {slug!r} collides with {seen_slugs[slug]!r}")
            continue
        seen_slugs[slug] = fid
        slugs[fid] = slug
        parsed.append((fid, feature["properties"], feature["geometry"]))
    if errors:
        return _fail("accepted", *errors)

    countries = {str(p.get("country", "")).strip().upper() for _f, p, _g in parsed}
    countries = {_COUNTRY_ALIASES.get(c, c) for c in countries}
    if len(countries) > 1:
        return _fail(
            "accepted",
            f"upload mixes countries {sorted(countries)!r} — one farm is one country; "
            "split the upload by farm",
        )
    upload_country = next(iter(countries))

    _out(f"checkpoint=accepted job_id={sha} fields={len(parsed)} country={upload_country}")

    # ---- counties_matched (FIPS assignment via the assign_field_fips.py lookup)
    counties_dir = (
        Path(args.counties_dir).expanduser()
        if args.counties_dir
        else DATA_ROOT / "shared" / "geoadmin" / "l2_counties"
    )
    if not counties_dir.is_absolute():
        counties_dir = DATA_ROOT / counties_dir
    try:
        echoes, county_failures = match_counties(parsed, slugs, counties_dir)
    except FileNotFoundError as exc:
        return _fail("counties_matched", str(exc))
    if county_failures:
        return _fail("counties_matched", *county_failures)

    areas_ha: dict[str, float] = {}
    for fid, _props, geom in parsed:
        areas_ha[fid] = _area_ha(geom)
    for fid, props, _geom in parsed:
        echo = echoes[fid]
        _out(
            f"checkpoint=counties_matched job_id={sha} field_id={fid!r} "
            f"county={echo['county']!r} state={echo['state']!r} "
            f"country={echo['country']!r} fips={echo['fips']!r} "
            f"area_ha={areas_ha[fid]:.2f}"
        )
        print(
            f"field {fid}: {echo['county']}, {echo['state']}, {echo['country']} "
            f"(fips {echo['fips']}) — {areas_ha[fid]:.1f} ha recomputed",
            file=sys.stderr,
        )

    # ---- write set (exactly the repository contract, merged by field_id)
    grower_slug, farm_slug = args.grower_slug, args.farm_slug
    fdir = farm_dir(grower_slug, farm_slug)
    mdir = farm_manifest_dir(grower_slug, farm_slug)
    fdir.mkdir(parents=True, exist_ok=True)
    mdir.mkdir(parents=True, exist_ok=True)
    (fdir / "boundary").mkdir(parents=True, exist_ok=True)

    new_features = [
        _feature_json(fid, props, geom, areas_ha[fid], echoes[fid])
        for fid, props, geom in parsed
    ]
    boundaries_path = farm_boundary_path(grower_slug, farm_slug)
    existing = _read_json(boundaries_path, None) if boundaries_path.exists() else None
    uploaded_ids = {f["properties"]["field_id"] for f in new_features}
    prune_ids: set[str] | None = None
    if args.prune_missing:
        prune_ids = uploaded_ids
    merged = _merge_features(existing, new_features, prune_ids)

    kept_ids = {
        str((f.get("properties") or {}).get("field_id", ""))
        for f in merged.get("features", [])
    }
    pruned_ids: list[str] = []
    if existing:
        for feature in existing.get("features", []):
            props_old = feature.get("properties") or {}
            fid_old = str(props_old.get("field_id", ""))
            if fid_old and fid_old not in kept_ids and fid_old not in uploaded_ids:
                pruned_ids.append(fid_old)

    def _write_feature_collection(path: Path, feature: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": EPSG_4326}},
            "features": [feature],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for feature in new_features:
        _write_feature_collection(
            field_boundary_path(grower_slug, farm_slug, slugs[feature["properties"]["field_id"]]),
            feature,
        )
    for fid in pruned_ids:
        victim = fdir / "fields" / slugs.get(fid, naming.field_slug_from_id(fid))
        if victim.is_dir():
            shutil.rmtree(victim)
    boundaries_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    inventory_path = mdir / "field-inventory.csv"
    final_rows = _merge_inventory(
        inventory_path,
        [(f["properties"]["field_id"], slugs[f["properties"]["field_id"]]) for f in new_features],
        set(pruned_ids),
    )
    # keep rows for surviving other-source features
    surviving = {f["properties"]["field_id"] for f in merged["features"]}
    final_rows = [(fid, slug) for fid, slug in final_rows if fid in surviving or fid in uploaded_ids]
    inventory_path.write_text(
        _INVENTORY_HEADER + "\n" + "".join(f"{fid},{slug}\n" for fid, slug in final_rows),
        encoding="utf-8",
    )

    # farm.json country/state (merge — never clobber unrelated keys)
    farm_json_path = fdir / "farm.json"
    farm_json = _read_json(farm_json_path, {})
    if not isinstance(farm_json, dict):
        farm_json = {}
    states = sorted({echoes[fid]["state"] for fid, _p, _g in parsed if echoes[fid]["state"]})
    farm_json.update(
        {
            "grower_slug": grower_slug,
            "farm_slug": farm_slug,
            "country": upload_country,
            "default_crs": EPSG_4326,
        }
    )
    farm_json.setdefault("display_name", farm_slug)
    declared_states = {str(p.get("state", "")).strip().upper() for _f, p, _g in parsed if p.get("state")}
    if declared_states:
        farm_json["state"] = sorted(declared_states)[0]
    elif states:
        farm_json["state"] = states[0]
    farm_json_path.write_text(json.dumps(farm_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # provenance (per-farm, rewritten each ingest of this source) + journal (append-only)
    provenance = {
        "source": "user_upload (Hermes plugin onboarding POST /onboard/boundary)",
        "ingest": "src/scripts/ingest/ingest_user_boundaries.py",
        "area_recompute": f"equal-area reprojection {EQUAL_AREA_CRS}",
        "accessed_at": _now_iso(),
        "job_id": args.job_id or sha,
        "geojson_sha256": sha,
        "grower_slug": grower_slug,
        "farm_slug": farm_slug,
        "fields": [
            {
                "field_id": fid,
                "field_slug": slugs[fid],
                "declared": {
                    key: props.get(key)
                    for key in ("country", "state", "year", "crop", "area_ha_est", "area_acres")
                    if props.get(key) is not None
                },
                "county_echo": echoes[fid],
                "recomputed_area_ha": round(areas_ha[fid], 4),
            }
            for fid, props, _geom in parsed
        ],
        "pruned_field_ids": sorted(pruned_ids),
    }
    (mdir / "user_upload_fields_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    journal[sha] = {
        "sha256": sha,
        "job_id": provenance["job_id"],
        "accessed_at": provenance["accessed_at"],
        "grower_slug": grower_slug,
        "farm_slug": farm_slug,
        "field_ids": sorted(uploaded_ids),
        "pruned_field_ids": sorted(pruned_ids),
        "geojson_rel": Path(geojson_path).name,
    }
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if pruned_ids:
        print(f"pruned under --prune-missing: {sorted(pruned_ids)}", file=sys.stderr)

    # ---- legs_running: hand off to run_farm_pipeline.py minus field sampling
    if args.handoff == "off":
        _out(f"checkpoint=legs_running job_id={sha} handoff=off")
        return 0
    command = _pipeline_command(scripts_dir, grower_slug, farm_slug, boundaries_path)
    log_path = farm_logs_dir(grower_slug, farm_slug) / f"user_upload_handoff_{sha[:12]}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DATA_PIPELINE_DATA_ROOT"] = str(Path(resolved_root).expanduser().resolve(strict=False))
    env.update({"AG_GROWER_SLUG": grower_slug, "AG_FARM_SLUG": farm_slug})
    # NOTE: no --allow-live-downloads here — the orchestrator passes it to the
    # DEM step itself; re-adding it would fork that law into two places.
    with log_path.open("ab") as log_file:
        if args.handoff == "detach":
            proc = subprocess.Popen(
                command, cwd=str(DATA_ROOT), env=env,
                stdout=log_file, stderr=log_file, start_new_session=True,
            )
            _out(f"checkpoint=legs_running job_id={sha} handoff=detach pid={proc.pid} log={log_path}")
            return 0
        proc = subprocess.run(command, cwd=str(DATA_ROOT), env=env, stdout=log_file, stderr=log_file)
    if proc.returncode != 0:
        print(
            f"run_farm_pipeline.py handoff exited {proc.returncode}; see {log_path}",
            file=sys.stderr,
        )
        _out(f"checkpoint=legs_running job_id={sha} handoff=sync legs_status=failed log={log_path}")
        return _fail("legs_running", f"pipeline handoff failed (log: {log_path})")
    _out(f"checkpoint=legs_running job_id={sha} handoff=sync legs_status=ok log={log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
