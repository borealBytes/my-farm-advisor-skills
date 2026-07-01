#!/usr/bin/env python3
"""
run_farm_pipeline.py — Master pipeline entrypoint.

Usage:
    python src/scripts/run_farm_pipeline.py \\
        --boundaries growers/<grower-slug>/farms/<farm-slug>/boundary/field_boundaries.geojson \\
        [--farm-name "Default Farm"] \\
        [--force]

Runs the full farm intelligence reporting pipeline from a single field
boundaries GeoJSON file.  Each step is idempotent and will be skipped if
inputs, code, and config are unchanged since the last run.

Outputs under the configured runtime root:
    growers/.../fields/.../derived/reports/    — one per field
    growers/.../derived/reports/               — farm poster, HTML, and Markdown
    growers/.../manifests/                     — canonical per-step manifests
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from bootstrap_runtime import ensure_runtime_environment

ensure_runtime_environment()

from lib.paths import farm_boundary_path, farm_manifest_dir, farm_report_asset_path, grower_manifest_path
from lib.runtime_paths import resolve_runtime_paths
from reporting_bootstrap import ensure_canonical_data_tree

_RUNTIME_PATHS = resolve_runtime_paths()
_RUNTIME_BASE = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts


def _runtime_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else _RUNTIME_BASE / candidate


def _runtime_relative(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(_RUNTIME_BASE))
    except ValueError:
        return str(path)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _init_grower_manifest(grower_slug: str, farm_slug: str, farm_name: str) -> Path:
    manifest_path = grower_manifest_path(grower_slug)
    payload = _load_json(manifest_path)
    raw_farms = payload.get("farms")
    farms: list[dict[str, Any]] = (
        [cast(dict[str, Any], item) for item in raw_farms if isinstance(item, dict)]
        if isinstance(raw_farms, list)
        else []
    )
    farm_exists = any(
        str(item.get("farm_slug")) == farm_slug for item in farms if isinstance(item, dict)
    )
    if not farm_exists:
        farms.append(
            {
                "farm_slug": farm_slug,
                "farm_name": farm_name,
                "last_run_started": None,
                "last_run_finished": None,
                "last_run_status": "unknown",
            }
        )
    now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload.update(
        {
            "grower_slug": grower_slug,
            "manifest_version": 1,
            "updated_at": now,
            "farms": farms,
        }
    )
    _write_json(manifest_path, payload)
    return manifest_path


def _update_grower_manifest(
    manifest_path: Path,
    *,
    farm_slug: str,
    run_status: str,
    active_step: str | None,
    step_results: list[dict[str, str]],
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    payload = _load_json(manifest_path)
    raw_farms = payload.get("farms")
    farms: list[dict[str, Any]] = (
        [cast(dict[str, Any], item) for item in raw_farms if isinstance(item, dict)]
        if isinstance(raw_farms, list)
        else []
    )
    for idx, item in enumerate(farms):
        if not isinstance(item, dict):
            continue
        if str(item.get("farm_slug")) != farm_slug:
            continue
        current = dict(item)
        if started_at is not None:
            current["last_run_started"] = started_at
        if finished_at is not None:
            current["last_run_finished"] = finished_at
        current["last_run_status"] = run_status
        current["active_step"] = active_step
        current["step_results"] = step_results
        farms[idx] = current
        break
    payload["farms"] = farms
    payload["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    _write_json(manifest_path, payload)


def _run(
    script: str,
    extra_env: dict | None = None,
    command_args: tuple[str, ...] = (),
) -> bool:
    cmd = [sys.executable, str(_SCRIPTS / script), *command_args]
    t0 = time.monotonic()
    env = os.environ.copy()
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    result = subprocess.run(cmd, cwd=str(_RUNTIME_BASE), capture_output=False, env=env)
    elapsed = time.monotonic() - t0
    status = "ok" if result.returncode == 0 else "FAILED"
    print(f"  {status}  ({elapsed:.1f}s)  {script}")
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Farm intelligence reporting pipeline")
    parser.add_argument(
        "--boundaries",
        default=None,
        help="Path to field boundaries GeoJSON",
    )
    parser.add_argument("--farm-name", default="Default Farm")
    parser.add_argument("--grower-slug", default="default-grower")
    parser.add_argument("--farm-slug", default="default-farm")
    parser.add_argument(
        "--inventory-csv",
        default=None,
        help="Path to field inventory CSV with field_id,field_slug",
    )
    parser.add_argument(
        "--weather-csv",
        default=None,
        help="Optional canonical weather CSV override",
    )
    parser.add_argument(
        "--weather-backend",
        choices=["zarr", "api"],
        default=os.environ.get("AG_WEATHER_BACKEND", "zarr"),
        help="Farm weather backend; zarr samples NASA POWER S3 at field centroids by default",
    )
    parser.add_argument(
        "--weather-start-year",
        type=int,
        default=_env_int("AG_WEATHER_START_YEAR", 2021),
        help="First farm weather year",
    )
    parser.add_argument(
        "--weather-end-year",
        type=int,
        default=_env_int("AG_WEATHER_END_YEAR", 2025),
        help="Last farm weather year",
    )
    parser.add_argument(
        "--weather-time-standard",
        choices=["lst", "utc"],
        default=os.environ.get("AG_WEATHER_TIME_STANDARD", "lst"),
        help="NASA POWER time standard for farm weather outputs",
    )
    parser.add_argument(
        "--dem-context-meters",
        type=float,
        default=20.0,
        help="DEM terrain context buffer in meters for explicit terrain runs",
    )
    parser.add_argument(
        "--dem-source-policy",
        choices=[
            "auto",
            "us",
            "global",
            "usgs-tnm",
            "illinois",
            "nasadem",
            "copernicus-glo30",
            "alos-aw3d30",
        ],
        default="auto",
        help="DEM terrain source policy for explicit terrain runs",
    )
    parser.add_argument(
        "--skip-dem-terrain",
        action="store_true",
        help="Skip DEM terrain ingestion when terrain is explicitly added to a pipeline run",
    )
    parser.add_argument("--force", action="store_true", help="Force rerun all steps")
    parser.add_argument(
        "--structure-test",
        action="store_true",
        help="Create and verify canonical data tree, then exit",
    )
    args = parser.parse_args()
    if args.weather_start_year > args.weather_end_year:
        print("ERROR: --weather-start-year must be <= --weather-end-year")
        sys.exit(1)
    inventory_path = (
        _runtime_path(args.inventory_csv)
        if args.inventory_csv
        else farm_manifest_dir(args.grower_slug, args.farm_slug) / "field-inventory.csv"
    )

    field_slugs = ensure_canonical_data_tree(
        grower_slug=args.grower_slug,
        farm_slug=args.farm_slug,
        farm_name=args.farm_name,
        inventory_path=inventory_path,
    )
    if field_slugs:
        print(f"Canonical tree ensured for {len(field_slugs)} fields")
    else:
        print("Canonical tree ensured (no field inventory found)")

    if args.structure_test:
        print("Structure test complete.")
        return

    boundaries = (
        _runtime_path(args.boundaries)
        if args.boundaries
        else farm_boundary_path(args.grower_slug, args.farm_slug)
    )
    if not boundaries.exists():
        print(f"ERROR: field boundaries not found: {boundaries}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Farm Intelligence Reporting Pipeline")
    print(f"  Farm: {args.farm_name}")
    print(f"  Boundaries: {boundaries}")
    print("=" * 60)

    run_started = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    grower_manifest = _init_grower_manifest(args.grower_slug, args.farm_slug, args.farm_name)
    step_results: list[dict[str, str]] = []
    _update_grower_manifest(
        grower_manifest,
        farm_slug=args.farm_slug,
        run_status="running",
        active_step="bootstrap",
        step_results=step_results,
        started_at=run_started,
        finished_at=None,
    )

    dem_command_args = (
        "--allow-live-downloads",
        "--context-meters",
        str(args.dem_context_meters),
        "--source-policy",
        args.dem_source_policy,
    )
    steps = [
        ("ingest/download_fields.py", "Canonical field boundaries", (), False),
        (
            "ingest/download_dem_terrain.py",
            "Live DEM terrain derivatives",
            dem_command_args,
            args.skip_dem_terrain,
        ),
        ("ingest/download_soil.py", "SSURGO field soil tables", (), False),
        ("ingest/download_weather.py", "Weather history tables", (), False),
        ("ingest/download_cdl.py", "Shared CDL history tables", (), False),
        ("ingest/download_satellite_imagery.py", "Raw satellite TIFFs", (), False),
        ("reporting/generate_ndvi_composites.py", "NDVI yearly composites", (), False),
        ("reporting/generate_ndvi_cards.py", "NDVI cached cards", (), False),
        ("reporting/generate_ssurgo_maps.py", "SSURGO soil maps with basemap", (), False),
        ("reporting/generate_field_posters.py", "Field posters", (), False),
        ("reporting/generate_aggregate_poster.py", "Farm portfolio poster", (), False),
        ("reporting/generate_ssurgo_cards.py", "SSURGO soil profile cards", (), False),
        ("reporting/generate_farm_html.py", "Self-contained HTML report", (), False),
        ("reporting/generate_farm_markdown.py", "Markdown report", (), False),
    ]

    all_ok = True
    extra_env = {
        "AG_GROWER_SLUG": args.grower_slug,
        "AG_FARM_SLUG": args.farm_slug,
        "AG_FARM_NAME": args.farm_name,
        "AG_INVENTORY_CSV": str(inventory_path),
        "AG_BOUNDARIES": str(boundaries),
        "AG_WEATHER_BACKEND": args.weather_backend,
        "AG_WEATHER_START_YEAR": str(args.weather_start_year),
        "AG_WEATHER_END_YEAR": str(args.weather_end_year),
        "AG_WEATHER_TIME_STANDARD": args.weather_time_standard,
    }
    if args.weather_csv:
        extra_env["AG_WEATHER_CSV"] = str(_runtime_path(args.weather_csv))
    if args.force:
        extra_env["AG_FORCE"] = "1"
    for script, label, command_args, skip_step in steps:
        _update_grower_manifest(
            grower_manifest,
            farm_slug=args.farm_slug,
            run_status="running",
            active_step=script,
            step_results=step_results,
        )
        print(f"\n[{label}]")
        if skip_step:
            print(f"  SKIPPED by operator request: {script}")
            step_results.append({"step": script, "status": "skipped", "reason": "operator_request"})
            continue
        ok = _run(script, extra_env=extra_env, command_args=command_args)
        step_results.append({"step": script, "status": "ok" if ok else "failed"})
        if not ok:
            all_ok = False
            _update_grower_manifest(
                grower_manifest,
                farm_slug=args.farm_slug,
                run_status="failed",
                active_step=script,
                step_results=step_results,
                finished_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
            print(f"  Pipeline halted at: {script}")
            print("  Fix the error above and rerun.")
            sys.exit(1)

    print()
    print("=" * 60)
    if all_ok:
        _update_grower_manifest(
            grower_manifest,
            farm_slug=args.farm_slug,
            run_status="complete",
            active_step=None,
            step_results=step_results,
            finished_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        print("  Pipeline complete.")
        print()
        print("  Outputs:")
        for extension in ("png", "html", "md"):
            output = farm_report_asset_path(args.grower_slug, args.farm_slug, extension)
            if output.exists():
                print(f"    {_runtime_relative(output)}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
