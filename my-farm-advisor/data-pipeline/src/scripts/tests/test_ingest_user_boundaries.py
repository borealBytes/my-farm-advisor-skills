"""Offline pytest suite for ingest_user_boundaries.py (plugin onboarding exec leg).

Convention note: src/scripts/tests/ is the repo's existing script-test dir
(smoke_dem_pipeline.py). This is the first true pytest file for ingest scripts
(the checkout carries no pytest config; the sibling hermes plugin keeps its
stdlib pytest suite under tests/) — so these tests are pytest-style, adjacent
to the smoke, and run OFFLINE against a temp writer data root with a fixture
county layer. No network, no installs, no live downloads.

Run: uv run --with pytest --with geopandas --with requests python -m pytest \
        src/scripts/tests/test_ingest_user_boundaries.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ingest" / "ingest_user_boundaries.py"


# --------------------------------------------------------------- fixtures

def _square(west: float, south: float, east: float, north: float) -> dict:
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def _county_props(fips, state_fips, county_fips, name, full, **extra):
    row = {
        "fips": fips,
        "state_fips": state_fips,
        "county_fips": county_fips,
        "county_name": name,
        "county_name_full": full,
    }
    row.update(extra)
    return row


def _layer(features):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": p, "geometry": _square(*bb)}
            for p, bb in features
        ],
    }


USA_LAYERS = _layer([
    (_county_props("19169", "19", "169", "Story", "Story County, Iowa"),
     (-93.8, 41.7, -93.1, 42.5)),
    (_county_props("19153", "19", "153", "Polk", "Polk County, Iowa"),
     (-93.8, 41.4, -93.1, 41.7)),
])
CAN_LAYERS = _layer([
    (_county_props("CA35001", "CA35", "001", "Chatham-Kent",
                   "Chatham-Kent (Census Division)", country="CA"),
     (-82.8, 42.2, -81.9, 42.9)),
])


@pytest.fixture()
def data_root(tmp_path):
    root = tmp_path / "root"
    counties = root / "data-pipeline" / "shared" / "geoadmin" / "l2_counties"
    counties.mkdir(parents=True)
    (counties / "counties_usa.geojson").write_text(json.dumps(USA_LAYERS))
    (counties / "counties_canada.geojson").write_text(json.dumps(CAN_LAYERS))
    return root


def _fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def _feature(fid, country, geom, **props):
    properties = {"field_id": fid, "country": country}
    properties.update(props)
    return {"type": "Feature", "id": fid, "properties": properties, "geometry": geom}


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def _run(root, doc, extra=(), env=None, job_id=None):
    payload = _canonical(doc)
    sha = job_id or hashlib.sha256(payload).hexdigest()
    geo = root / f"{sha}.geojson"
    geo.write_bytes(payload)
    child_env = {k: v for k, v in os.environ.items() if k != "DATA_PIPELINE_DATA_ROOT"}
    child_env.update(env or {})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-root", str(root),
         "--job-id", sha, "--geojson", str(geo), "--handoff", "off", *extra],
        capture_output=True, text=True, env=child_env, timeout=300,
    )
    return proc, sha


def _farm(root, grower="default-grower", farm="default-farm"):
    return root / "data-pipeline" / "growers" / grower / "farms" / farm


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- tests


def test_happy_path_two_fields_same_county(data_root):
    doc = _fc(
        _feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1),
                 state="IA", year=2025, crop="corn", area_ha_est=999, area_acres=123),
        _feature("f-b", "US", _square(-93.3, 42.2, -93.1, 42.3), state="IA"),
    )
    proc, sha = _run(data_root, doc)
    assert proc.returncode == 0, proc.stderr
    assert "checkpoint=accepted" in proc.stdout
    matched = [line for line in proc.stdout.splitlines() if line.startswith("checkpoint=counties_matched")]
    assert len(matched) == 2
    assert all("county='Story County, Iowa'" in line and "country='US'" in line
               and "state='IA'" in line for line in matched)
    assert "checkpoint=legs_running" in proc.stdout

    farm = _farm(data_root)
    boundaries = _load(farm / "boundary" / "field_boundaries.geojson")
    by_id = {f["properties"]["field_id"]: f for f in boundaries["features"]}
    assert set(by_id) == {"f-a", "f-b"}
    for fid, feature in by_id.items():
        assert feature["properties"]["source"] == "user_upload"
    # the user claimed 999 ha; the equal-area recompute (0.2 deg x 0.1 deg at
    # lat 42 ~ 16.5 km x 11.1 km ~ 18.4k ha) is the routed value, never the claim
    assert by_id["f-a"]["properties"]["area_ha_est"] != 999
    assert by_id["f-a"]["properties"]["area_ha_est"] == pytest.approx(18390.8, rel=0.02)
    assert by_id["f-a"]["properties"]["area_acres"] == pytest.approx(
        by_id["f-a"]["properties"]["area_ha_est"] * 2.47105, abs=0.2)
    assert (farm / "fields" / "f-a" / "boundary" / "field_boundary.geojson").is_file()
    assert (farm / "fields" / "f-b" / "boundary" / "field_boundary.geojson").is_file()

    inventory = (farm / "manifests" / "field-inventory.csv").read_text().splitlines()
    assert inventory[0] == "field_id,field_slug"
    assert {line.split(",")[0] for line in inventory[1:]} == {"f-a", "f-b"}

    farm_json = _load(farm / "farm.json")
    assert farm_json["country"] == "US"
    assert farm_json["state"] == "IA"

    prov = _load(farm / "manifests" / "user_upload_fields_provenance.json")
    declared = {row["field_id"]: row["declared"] for row in prov["fields"]}
    # user areas are JOURNALED, never routed on
    assert declared["f-a"]["area_ha_est"] == 999
    assert declared["f-a"]["area_acres"] == 123

    journal = _load(data_root / "data-pipeline" / "shared" / "user_upload" / "manifests" / "sha256_journal.json")
    assert journal[sha]["sha256"] == sha
    assert journal[sha]["field_ids"] == ["f-a", "f-b"]


def test_wrong_country_fails_visibly_at_counties_matched(data_root):
    doc = _fc(_feature("f-on", "US", _square(-82.5, 42.4, -82.2, 42.6), state="ON"))
    proc, sha = _run(data_root, doc)
    assert proc.returncode != 0
    assert "f-on" in proc.stderr
    assert "wrong-country" in proc.stderr.lower()
    assert "Chatham-Kent" in proc.stderr
    assert "checkpoint=failed stage=counties_matched" in proc.stdout
    # nothing was written: the gate rejects BEFORE the write set
    assert not _farm(data_root).exists()
    journal = data_root / "data-pipeline" / "shared" / "user_upload" / "manifests" / "sha256_journal.json"
    assert not journal.exists() or sha not in _load(journal)

    # same geometry, honest country declaration -> passes (the claim failed, not coverage)
    proc2, _ = _run(data_root, _fc(_feature("f-on", "CA", _square(-82.5, 42.4, -82.2, 42.6), state="ON")))
    assert proc2.returncode == 0, proc2.stderr
    assert "country='CA'" in proc2.stdout


def test_repost_same_sha_is_noop(data_root):
    doc = _fc(_feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"))
    _run(data_root, doc)
    boundaries = _farm(data_root) / "boundary" / "field_boundaries.geojson"
    journal_path = data_root / "data-pipeline" / "shared" / "user_upload" / "manifests" / "sha256_journal.json"
    before_mt = boundaries.stat().st_mtime_ns
    before_journal = journal_path.read_bytes()
    before_lines = len(before_journal.decode().splitlines())

    proc, _ = _run(data_root, doc)
    assert proc.returncode == 0
    assert "noop=true reason=already-ingested" in proc.stdout
    assert boundaries.stat().st_mtime_ns == before_mt
    assert journal_path.read_bytes() == before_journal
    assert len(before_journal.decode().splitlines()) == before_lines


def _seed_foreign_feature(root, sha_payload=True):
    """Place a usda_csb field directly in the farm boundary file + inventory."""
    farm = _farm(root)
    (farm / "boundary").mkdir(parents=True)
    csb = _feature("c-csb", "US", _square(-93.75, 41.75, -93.65, 41.85),
                   source="usda_csb_fiboa", csb_id="x1", state="IA",
                   area_ha_est=10.0, area_acres=24.7)
    (farm / "boundary" / "field_boundaries.geojson").write_text(json.dumps(_fc(csb)))
    (farm / "manifests").mkdir(parents=True, exist_ok=True)
    (farm / "manifests" / "field-inventory.csv").write_text(
        "field_id,field_slug\nc-csb,c-csb\n")


def test_plain_reupload_merges_never_prunes(data_root):
    _seed_foreign_feature(data_root)
    doc_ab = _fc(
        _feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"),
        _feature("f-b", "US", _square(-93.3, 42.2, -93.1, 42.3), state="IA"),
    )
    _run(data_root, doc_ab)
    # re-upload WITHOUT f-b in the payload, no --prune-missing: f-b stays
    proc, _ = _run(data_root, _fc(_feature("f-a", "US",
                                           _square(-93.6, 42.0, -93.4, 42.1),
                                           state="IA", year=2026)))
    assert proc.returncode == 0, proc.stderr
    ids = {f["properties"]["field_id"]
           for f in _load(_farm(data_root) / "boundary" / "field_boundaries.geojson")["features"]}
    assert ids == {"f-a", "f-b", "c-csb"}  # merge, never wholesale replace
    assert (_farm(data_root) / "fields" / "f-b").is_dir()


def test_prune_missing_removes_absent_user_fields_only(data_root):
    _seed_foreign_feature(data_root)
    _run(data_root, _fc(
        _feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"),
        _feature("f-b", "US", _square(-93.3, 42.2, -93.1, 42.3), state="IA"),
    ))
    # same single-field payload as the merge test but different content (extra
    # prop) so the sha-idempotency law doesn't short-circuit the prune run
    proc, _ = _run(data_root, _fc(_feature("f-a", "US",
                                           _square(-93.6, 42.0, -93.4, 42.1),
                                           state="IA", year=2027)),
                   extra=("--prune-missing",))
    assert proc.returncode == 0, proc.stderr
    doc = _load(_farm(data_root) / "boundary" / "field_boundaries.geojson")
    ids = {f["properties"]["field_id"] for f in doc["features"]}
    assert ids == {"f-a", "c-csb"}  # user_upload f-b pruned; other source untouched
    assert not (_farm(data_root) / "fields" / "f-b").exists()
    inventory = (_farm(data_root) / "manifests" / "field-inventory.csv").read_text()
    assert "f-b" not in inventory and "f-a" in inventory and "c-csb" in inventory
    prov = _load(_farm(data_root) / "manifests" / "user_upload_fields_provenance.json")
    assert prov["pruned_field_ids"] == ["f-b"]


@pytest.mark.parametrize("broken, needle", [
    # open ring
    ({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"field_id": "f-x", "country": "US"},
        "geometry": {"type": "Polygon", "coordinates": [
            [[-93.6, 42.0], [-93.4, 42.0], [-93.4, 42.1], [-93.6, 42.05]]]}}]},
     "open"),
    # LineString geometry
    ({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"field_id": "f-x", "country": "US"},
        "geometry": {"type": "LineString",
                     "coordinates": [[-93.6, 42.0], [-93.4, 42.1]]}}]},
     "Polygon or MultiPolygon"),
    # missing field_id
    ({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"country": "US"},
        "geometry": _square(-93.6, 42.0, -93.4, 42.1)}]},
     "field_id"),
    # missing country
    ({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"field_id": "f-x"},
        "geometry": _square(-93.6, 42.0, -93.4, 42.1)}]},
     "country"),
    # CRS claimed via the filename field (task law: other-CRS string -> reject)
    ({"type": "FeatureCollection", "filename": "fields_epsg_3857.geojson", "features": [{
        "type": "Feature", "properties": {"field_id": "f-x", "country": "US"},
        "geometry": _square(-93.6, 42.0, -93.4, 42.1)}]},
     "EPSG:4326"),
    # 3-vertex ring (below the closed-ring minimum of 4 positions)
    ({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"field_id": "f-x", "country": "US"},
        "geometry": {"type": "Polygon", "coordinates": [
            [[-93.6, 42.0], [-93.4, 42.0], [-93.5, 42.1]]]}}]},
     ">= 4 vertices"),
])
def test_validation_rejects_before_any_write(data_root, broken, needle):
    proc, sha = _run(data_root, broken)
    assert proc.returncode != 0
    assert needle in proc.stderr
    assert "checkpoint=failed stage=accepted" in proc.stdout
    assert not _farm(data_root).exists()


def test_counties_dir_injection_runs_offline(data_root, tmp_path):
    alt = tmp_path / "county-fixtures"
    alt.mkdir()
    (alt / "counties_usa.geojson").write_text(json.dumps(USA_LAYERS))
    doc = _fc(_feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"))
    proc, _ = _run(data_root, doc, extra=("--counties-dir", str(alt)))
    assert proc.returncode == 0, proc.stderr
    assert "Story County" in proc.stderr


def test_missing_county_layer_names_the_fix_not_a_traceback(data_root):
    import shutil as _sh
    _sh.rmtree(data_root / "data-pipeline" / "shared" / "geoadmin" / "l2_counties")
    doc = _fc(_feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"))
    proc, _ = _run(data_root, doc)
    assert proc.returncode != 0
    assert "download_geoadmin.py" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_env_divergence_warns_flag_wins(data_root):
    doc = _fc(_feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"))
    proc, _ = _run(data_root, doc, env={"DATA_PIPELINE_DATA_ROOT": str(data_root / "other")})
    assert proc.returncode == 0, proc.stderr
    assert "diverges" in proc.stderr
    assert (_farm(data_root) / "boundary" / "field_boundaries.geojson").is_file()
    assert not (data_root / "other" / "data-pipeline" / "growers").exists()


def test_handoff_command_minus_field_sampling(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_PIPELINE_DATA_ROOT", str(tmp_path))
    import importlib.util
    spec = importlib.util.spec_from_file_location("iub", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cmd = mod._pipeline_command(Path("scripts"), "g", "f", Path("b.geojson"))
    assert cmd[1].endswith("run_farm_pipeline.py")
    assert "--skip-field-sampling" in cmd
    assert "--allow-live-downloads" not in cmd  # the orchestrator owns that flag


def test_detach_handoff_starts_legs_and_returns_zero(data_root):
    doc = _fc(_feature("f-a", "US", _square(-93.6, 42.0, -93.4, 42.1), state="IA"))
    payload = _canonical(doc)
    sha = hashlib.sha256(payload).hexdigest()
    geo = data_root / "payload.geojson"
    geo.write_bytes(payload)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-root", str(data_root),
         "--job-id", sha, "--geojson", str(geo), "--handoff", "detach"],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    m = re.search(r"checkpoint=legs_running job_id=\S+ handoff=detach pid=(\d+)", proc.stdout)
    assert m, proc.stdout
    pid = int(m.group(1))
    log = next((_farm(data_root) / "logs").glob("user_upload_handoff_*.log"))
    assert log.exists()
    try:  # the detached orchestrator keeps running; reap its process group
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
