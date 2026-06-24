#!/usr/bin/env python3
# ruff: noqa: E402
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportReturnType=false, reportGeneralTypeIssues=false
"""Download and summarize CDL crop composition for the active farm."""

import argparse
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from requests import HTTPError

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (
    ensure_parent,
    farm_boundary_path,
    farm_cdl_full_composition_path,
    farm_cdl_rotation_path,
    farm_cdl_year_table_path,
    shared_cdl_conus_raster_path,
    shared_cdl_state_raster_path,
)
from reporting_bootstrap import ensure_skill_path

ensure_skill_path("cdl-cropland")

from cdl_reporting import extract_crop_composition, summarize_crop_history

DEFAULT_CDL_LATEST_YEAR = 2025
DEFAULT_CDL_WINDOW_YEARS = 5


def _cdl_coverage_label(*, conus: bool, state_fips: str | None = None) -> str:
    return "CONUS" if conus else str(state_fips or "19").zfill(2)


def _cdl_raster_path(year: int, *, conus: bool, state_fips: str | None = None) -> Path:
    if conus:
        return shared_cdl_conus_raster_path(year)
    return shared_cdl_state_raster_path(year, str(state_fips or "19"))


def _download_cdl_raster(
    year: int,
    *,
    conus: bool = False,
    state_fips: str | None = None,
    force: bool = False,
) -> Path:
    """Download one shared CDL raster and return its canonical runtime path."""
    label = _cdl_coverage_label(conus=conus, state_fips=state_fips)
    cdl_path = _cdl_raster_path(year, conus=conus, state_fips=state_fips)
    if cdl_path.exists() and not force:
        print(f"  Cached CDL {year} {label}: {cdl_path}")
        return cdl_path

    cdl_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_{year}_{label}.tif"
    print(f"  Downloading CDL {year} {label}...")
    with requests.get(url, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        with open(cdl_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    print(f"  Downloaded CDL {year} {label}: {cdl_path}")
    return cdl_path


def download_cdl(year, state_fips="19"):
    """Return a CDL raster for a farm state, preferring shared CONUS rasters."""
    state_path = shared_cdl_state_raster_path(year, str(state_fips))
    if state_path.exists():
        return state_path
    conus_path = shared_cdl_conus_raster_path(year)
    if conus_path.exists():
        return conus_path
    return _download_cdl_raster(year, state_fips=str(state_fips))


def _target_cdl_years(
    window_years: int = DEFAULT_CDL_WINDOW_YEARS,
    latest_year: int = DEFAULT_CDL_LATEST_YEAR,
) -> list[int]:
    years: list[int] = []
    candidate_year = latest_year
    while candidate_year >= max(2010, latest_year - window_years - 5):
        years.append(candidate_year)
        candidate_year -= 1
    return years


def _parse_years(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    years = sorted({int(part.strip()) for part in raw.split(",") if part.strip()}, reverse=True)
    return years or None


def _parse_state_fips_values(raw: str | None) -> list[str]:
    if not raw:
        return ["19"]
    return sorted({part.strip().zfill(2) for part in raw.split(",") if part.strip()})


def prepare_shared_cdl_rasters(
    *,
    scope: str = "conus",
    years: list[int] | None = None,
    latest_year: int = DEFAULT_CDL_LATEST_YEAR,
    window_years: int = DEFAULT_CDL_WINDOW_YEARS,
    state_fips_values: list[str] | None = None,
    force: bool = False,
) -> list[Path]:
    """Download shared CDL rasters for runtime initialization."""
    candidates = years or _target_cdl_years(window_years=window_years, latest_year=latest_year)
    state_fips_values = state_fips_values or ["19"]
    completed: list[Path] = []
    completed_years: set[int] = set()
    for year in candidates:
        if len(completed_years) >= window_years and years is None:
            break
        try:
            if scope == "conus":
                completed.append(_download_cdl_raster(year, conus=True, force=force))
            elif scope == "state":
                for state_fips in state_fips_values:
                    completed.append(
                        _download_cdl_raster(year, state_fips=state_fips, force=force)
                    )
            else:
                raise ValueError("scope must be conus or state")
        except HTTPError as exc:
            response = getattr(exc, "response", None)
            status = response.status_code if response is not None else 0
            if status in {404, 503} and years is None:
                reason = "not available yet" if status == 404 else "server temporarily unavailable"
                print(f"  Warning: CDL {year} {scope} {reason}; trying older year")
                continue
            raise
        completed_years.add(year)
    return completed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raster-only",
        action="store_true",
        help="Initialize shared CDL rasters without farm boundary extraction",
    )
    parser.add_argument(
        "--cdl-scope",
        choices=["conus", "state"],
        default="conus",
        help="Shared raster coverage for --raster-only. Defaults to CONUS.",
    )
    parser.add_argument(
        "--cdl-state-fips",
        default=None,
        help="Comma-separated state FIPS values for --cdl-scope state",
    )
    parser.add_argument(
        "--cdl-years",
        default=None,
        help="Comma-separated explicit CDL years. Overrides latest/window fallback.",
    )
    parser.add_argument(
        "--cdl-latest-year",
        type=int,
        default=DEFAULT_CDL_LATEST_YEAR,
        help="Latest CDL candidate year for --raster-only fallback search",
    )
    parser.add_argument(
        "--cdl-window-years",
        type=int,
        default=DEFAULT_CDL_WINDOW_YEARS,
        help="Number of available CDL years to initialize when --cdl-years is omitted",
    )
    parser.add_argument("--force", action="store_true", help="Redownload CDL rasters")
    return parser.parse_args()


def _state_fips_values(fields: gpd.GeoDataFrame) -> list[str]:
    if "state_fips" not in fields.columns:
        return ["19"]
    values = (
        pd.Series(fields["state_fips"], dtype="object").fillna("").astype(str).str.strip().tolist()
    )
    unique_values = sorted({value.zfill(2) for value in values if value})
    return unique_values or ["19"]


def _table_field_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    frame = pd.read_csv(csv_path, usecols=["field_id"])
    if "field_id" not in frame.columns:
        return set()
    return set(frame["field_id"].astype(str).tolist())


def main():
    args = parse_args()
    if args.raster_only:
        paths = prepare_shared_cdl_rasters(
            scope=args.cdl_scope,
            years=_parse_years(args.cdl_years),
            latest_year=args.cdl_latest_year,
            window_years=args.cdl_window_years,
            state_fips_values=_parse_state_fips_values(args.cdl_state_fips),
            force=args.force,
        )
        print(
            json.dumps(
                {
                    "scope": args.cdl_scope,
                    "raster_count": len(paths),
                    "rasters": [str(path) for path in paths],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return tuple(paths)

    print("=" * 60)
    print("Step 4: Download CDL Crop Type Data")
    print("=" * 60)

    grower_slug = os.environ.get("AG_GROWER_SLUG", "default-grower")
    farm_slug = os.environ.get("AG_FARM_SLUG", "default-farm")
    force = args.force or os.environ.get("AG_FORCE") == "1"
    fields = gpd.read_file(farm_boundary_path(grower_slug, farm_slug))
    print(f"Loaded {len(fields)} fields")
    state_fips_values = _state_fips_values(fields)
    print("State CDL coverage:", ", ".join(state_fips_values))

    target_years = _target_cdl_years()
    cached_years = [
        year
        for year in target_years
        if farm_cdl_year_table_path(grower_slug, farm_slug, year).exists()
    ]
    if (
        not force
        and len(cached_years) >= 5
        and farm_cdl_rotation_path(grower_slug, farm_slug).exists()
    ):
        selected_years = sorted(cached_years[:5], reverse=True)
        composition_path = farm_cdl_full_composition_path(
            grower_slug,
            farm_slug,
            min(selected_years),
            max(selected_years),
        )
        if composition_path.exists():
            expected_field_ids = set(fields["field_id"].astype(str).tolist())
            missing_by_year: dict[int, list[str]] = {}
            for year in selected_years:
                table_ids = _table_field_ids(farm_cdl_year_table_path(grower_slug, farm_slug, year))
                missing_ids = sorted(expected_field_ids - table_ids)
                if missing_ids:
                    missing_by_year[year] = missing_ids
            if missing_by_year:
                preview = "; ".join(
                    f"{year}: {', '.join(ids[:4])}" for year, ids in missing_by_year.items()
                )
                print(f"  Cached CDL tables missing field IDs; refreshing: {preview}")
            else:
                frames = [
                    pd.read_csv(farm_cdl_year_table_path(grower_slug, farm_slug, year))
                    for year in selected_years
                ]
                rotation = pd.read_csv(farm_cdl_rotation_path(grower_slug, farm_slug))
                print(
                    "skip  CDL API fetch (cached years): "
                    + ", ".join(str(year) for year in sorted(selected_years))
                )
                return (*frames, rotation)

    crop_mix_frames = []
    completed_years: list[int] = []
    for year in target_years:
        print(f"\n--- {year} CDL ---")
        state_frames: list[pd.DataFrame] = []
        for state_fips in state_fips_values:
            if "state_fips" in fields.columns:
                state_mask = fields["state_fips"].astype(str).str.zfill(2) == state_fips
            else:
                state_mask = pd.Series([True] * len(fields), index=fields.index)
            state_fields = fields.loc[state_mask].copy()
            if state_fields.empty:
                continue
            try:
                cdl_year_path = download_cdl(year, state_fips=state_fips)
            except HTTPError as exc:
                response = getattr(exc, "response", None)
                status = response.status_code if response is not None else 0
                if status in {404, 503}:
                    reason = "not available yet" if status == 404 else "server temporarily unavailable"
                    print(f"  Warning: CDL {year} state {state_fips} {reason}; skipping")
                    continue
                raise
            state_frames.append(extract_crop_composition(state_fields, cdl_year_path, year=year))
        if not state_frames:
            print(f"  Warning: no CDL composition rows were available for {year}; skipping")
            continue
        cdl_year = pd.concat(state_frames, ignore_index=True)
        year_output = ensure_parent(farm_cdl_year_table_path(grower_slug, farm_slug, year))
        cdl_year.to_csv(year_output, index=False)
        print(f"  Saved: {year_output}")
        crop_mix_frames.append(cdl_year)
        completed_years.append(year)
        if len(completed_years) >= 5:
            break

    if not crop_mix_frames:
        print("  Warning: No CDL years were available for download; skipping CDL analysis")
        return tuple()

    # Create rotation analysis
    print("\n--- Crop Rotation ---")
    crop_mix = pd.concat(crop_mix_frames, ignore_index=True)
    rotation = summarize_crop_history(crop_mix)
    rotation_output = ensure_parent(farm_cdl_rotation_path(grower_slug, farm_slug))
    rotation.to_csv(rotation_output, index=False)
    print(f"  Saved: {rotation_output}")
    composition_output = ensure_parent(
        farm_cdl_full_composition_path(
            grower_slug,
            farm_slug,
            min(completed_years),
            max(completed_years),
        )
    )
    crop_mix.to_csv(composition_output, index=False)
    print(f"  Saved: {composition_output}")

    print("\n✓ CDL analysis complete")
    for year, frame in zip(completed_years, crop_mix_frames):
        print(
            f"  {year} crops: {frame.sort_values('pct', ascending=False).groupby('field_id').first()['crop_name'].value_counts().to_dict()}"
        )

    return (*crop_mix_frames, rotation)


if __name__ == "__main__":
    main()
