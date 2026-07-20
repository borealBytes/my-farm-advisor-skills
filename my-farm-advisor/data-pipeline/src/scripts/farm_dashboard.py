#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
"""One-command farm dashboard orchestration.

Subcommands:
  - create: bootstrap fields by geographic selector and run full pipeline
  - refresh: rerun pipeline for one farm, a grower, or all growers/farms
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import geopandas as gpd
import requests
import rasterio
from rasterstats import zonal_stats

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))

from naming import field_slug_from_id
from paths import (
    DATA_ROOT,
    GROWERS_ROOT,
    SCRIPTS_ROOT,
    farm_boundary_path,
    farm_manifest_dir,
    shared_cdl_conus_raster_path,
    shared_cdl_state_raster_path,
    shared_geoadmin_counties_dir,
)

COUNTIES_PATH = shared_geoadmin_counties_dir() / "counties_usa.geojson"
NON_CONTIGUOUS = {"02", "15", "60", "66", "69", "72", "78"}
CROP_CODE = {"corn": 1, "soybeans": 5, "wheat": 24, "cotton": 2}
STATE_FIPS: dict[str, tuple[str, str]] = {
    "01": ("AL", "Alabama"),
    "02": ("AK", "Alaska"),
    "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"),
    "06": ("CA", "California"),
    "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"),
    "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"),
    "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"),
    "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"),
    "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"),
    "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"),
    "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"),
    "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"),
    "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"),
    "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"),
}


def _runtime_relative(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def _slugify(value: str) -> str:
    return "-".join(value.strip().lower().replace("_", "-").split())


def _state_lookup() -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for fips, (abbr, name) in STATE_FIPS.items():
        record = {"fips": fips, "abbr": abbr, "name": name, "slug": _slugify(name)}
        lookup[fips] = record
        lookup[abbr.lower()] = record
        lookup[name.lower()] = record
        lookup[_slugify(name)] = record
    return lookup


def _resolve_state(
    *, state: str | None, state_fips: str | None, required: bool = False
) -> dict[str, str] | None:
    raw = state_fips or state
    if not raw:
        if required:
            raise ValueError("Provide --state or --state-fips")
        return None
    key = raw.strip()
    if key.isdigit():
        key = key.zfill(2)
    else:
        key = _slugify(key)
    match = _state_lookup().get(key) or _state_lookup().get(raw.strip().lower())
    if not match:
        raise ValueError(f"Unknown state selector: {raw}")
    return match


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=str(DATA_ROOT), check=True)


def _ensure_counties() -> None:
    if COUNTIES_PATH.exists():
        return
    _run(
        [
            sys.executable,
            str(SCRIPTS_ROOT / "ingest" / "download_geoadmin.py"),
            "--levels",
            "l2_counties",
        ]
    )


def _load_counties() -> gpd.GeoDataFrame:
    _ensure_counties()
    return gpd.read_file(COUNTIES_PATH)


def _download_cdl_if_missing(year: int, state_fips: str) -> Path:
    state_code = state_fips.zfill(2)
    out_path = shared_cdl_state_raster_path(year, state_code)
    if out_path.exists():
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    requested_years = list(range(year, 2009, -1))
    last_error: Exception | None = None
    for candidate in requested_years:
        candidate_path = shared_cdl_state_raster_path(candidate, state_code)
        if candidate_path.exists():
            return candidate_path
        conus_path = shared_cdl_conus_raster_path(candidate)
        if conus_path.exists():
            return conus_path
        url = f"https://nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_{candidate}_{state_code}.tif"
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            candidate_path.write_bytes(response.content)
            return candidate_path
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 503:
                print(f"  Warning: CDL {candidate} {state_code} server temporarily unavailable; trying older year")
                last_error = exc
                continue
            raise
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(
        f"Unable to download CDL raster for state_fips={state_code} through years {requested_years[0]}..{requested_years[-1]} ({last_error})"
    )


def _top_crop_county_in_state(
    *, state_fips: str, crop: str, year: int
) -> dict[str, str]:
    counties = _load_counties()
    state = counties[
        counties["state_fips"].astype(str).str.zfill(2) == state_fips.zfill(2)
    ].copy()
    if state.empty:
        raise ValueError(f"No counties found for state_fips={state_fips}")

    try:
        raster_path = _download_cdl_if_missing(year, state_fips)
        with rasterio.open(raster_path) as src:
            state_proj = state.to_crs(src.crs)
            stats = zonal_stats(
                state_proj.geometry,
                str(raster_path),
                categorical=True,
                nodata=0,
            )

        code = CROP_CODE[crop]
        ranked: list[tuple[int, str, str, str]] = []
        for row, categorical in zip(state.itertuples(index=False), stats, strict=False):
            category = categorical or {}
            score = int(category.get(code, 0))
            ranked.append(
                (
                    score,
                    str(getattr(row, "fips")),
                    str(getattr(row, "state_fips")).zfill(2),
                    str(getattr(row, "county_name")),
                )
            )

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if ranked and ranked[0][0] > 0:
            _, county_fips, state_code, county_name = ranked[0]
            return {"fips": county_fips, "state_fips": state_code, "county_name": county_name}
        print(f"  Warning: CDL not available for crop scoring; falling back to first county")
    except Exception as exc:
        print(f"  Warning: CDL unavailable for {state_fips} ({exc}); falling back to first county")

    first = state.sort_values("county_name").iloc[0]
    return {
        "fips": str(first.fips),
        "state_fips": str(first.state_fips).zfill(2),
        "county_name": str(first.county_name),
    }


def _resolve_counties_from_fips(
    *,
    fips_level: str,
    fips_codes: list[str],
    state_fips: str | None,
    county_limit: int | None,
) -> list[dict[str, str]]:
    counties = _load_counties()
    frame = counties.copy()

    if fips_level == "l2":
        targets = set()
        for code in fips_codes:
            value = code.strip()
            if not value:
                continue
            if len(value) == 3 and state_fips:
                targets.add(f"{state_fips.zfill(2)}{value.zfill(3)}")
            else:
                targets.add(value.zfill(5))
        frame = frame[frame["fips"].astype(str).isin(targets)].copy()
    elif fips_level == "l1":
        states = {code.strip().zfill(2) for code in fips_codes if code.strip()}
        frame = frame[frame["state_fips"].astype(str).str.zfill(2).isin(states)].copy()
    elif fips_level == "l0":
        value_set = {code.strip().lower() for code in fips_codes if code.strip()}
        if value_set and not ({"us", "usa", "lower48", "lower-48"} & value_set):
            raise ValueError("For l0, use one of: us, usa, lower48, lower-48")
        frame = frame[
            ~frame["state_fips"].astype(str).str.zfill(2).isin(NON_CONTIGUOUS)
        ].copy()
    else:
        raise ValueError(f"Unsupported fips level: {fips_level}")

    if frame.empty:
        raise RuntimeError("No counties resolved from provided FIPS selector")

    frame = frame.sort_values(["state_fips", "county_fips"]).reset_index(drop=True)
    if county_limit is not None and county_limit > 0:
        frame = frame.head(county_limit)

    return [
        {
            "fips": str(row.fips),
            "state_fips": str(row.state_fips).zfill(2),
            "county_name": str(row.county_name),
        }
        for row in frame.itertuples(index=False)
    ]


def _field_allocation(total_fields: int, county_count: int) -> list[int]:
    base = max(1, total_fields // county_count)
    remainder = max(0, total_fields - (base * county_count))
    values = [base] * county_count
    for idx in range(remainder):
        values[idx] += 1
    return values


def _inventory_path_for_farm(grower_slug: str, farm_slug: str) -> Path:
    return farm_manifest_dir(grower_slug, farm_slug) / "field-inventory.csv"


def _run_bootstrap_for_counties(
    *,
    counties: list[dict[str, str]],
    field_count: int,
    seed: int,
    grower_slug: str,
    farm_slug: str,
    farm_name: str,
) -> Path:
    inventory_path = _inventory_path_for_farm(grower_slug, farm_slug)
    distribution = _field_allocation(field_count, len(counties))

    for idx, county in enumerate(counties):
        cmd = [
            sys.executable,
            str(SCRIPTS_ROOT / "ingest" / "bootstrap_farm_from_county.py"),
            "--state-fips",
            county["state_fips"],
            "--county-name",
            county["county_name"],
            "--count",
            str(distribution[idx]),
            "--seed",
            str(seed + idx),
            "--grower-slug",
            grower_slug,
            "--farm-slug",
            farm_slug,
            "--farm-name",
            farm_name,
            "--inventory-csv",
            str(inventory_path),
        ]
        if idx > 0:
            cmd.append("--append")
        _run(cmd)

    return inventory_path


def _run_pipeline_for_farm(
    *,
    grower_slug: str,
    farm_slug: str,
    farm_name: str,
    inventory_path: Path,
    force: bool,
) -> None:
    cmd = [
        sys.executable,
        str(SCRIPTS_ROOT / "run_farm_pipeline.py"),
        "--boundaries",
        str(farm_boundary_path(grower_slug, farm_slug)),
        "--grower-slug",
        grower_slug,
        "--farm-slug",
        farm_slug,
        "--farm-name",
        farm_name,
        "--inventory-csv",
        str(inventory_path),
    ]
    if force:
        cmd.append("--force")
    _run(cmd)


def _run_shared_data_initializer(
    args: argparse.Namespace, *, state_fips: str | None = None
) -> None:
    cmd = [
        sys.executable,
        str(SCRIPTS_ROOT / "init_shared_data.py"),
        "--start-year",
        str(args.shared_start_year),
        "--end-year",
        str(args.shared_end_year),
        "--coverage",
        args.shared_coverage,
        "--weather-backend",
        args.shared_weather_backend,
        "--weather-time-standard",
        args.shared_weather_time_standard,
        "--cdl-scope",
        args.cdl_scope,
        "--cdl-latest-year",
        str(args.cdl_latest_year),
        "--cdl-window-years",
        str(args.cdl_window_years),
    ]
    if args.cdl_scope == "state" and state_fips:
        cmd.extend(["--cdl-state-fips", state_fips])
    if args.force:
        cmd.append("--force")
    _run(cmd)


def _parse_csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def create_command(args: argparse.Namespace) -> None:
    state = _resolve_state(
        state=args.state,
        state_fips=args.state_fips,
        required=args.selector == "top-crop-county",
    )
    state_fips = state["fips"] if state else None
    farm_slug = args.farm_slug or f"{args.grower_slug}-{state['slug'] if state else 'farm'}"
    farm_name = args.farm_name or f"{state['name'] if state else farm_slug.replace('-', ' ').title()} Farm"

    if args.prepare_shared_data:
        _run_shared_data_initializer(args, state_fips=state_fips)

    if args.selector == "top-crop-county":
        top = _top_crop_county_in_state(
            state_fips=state_fips or "",
            crop=args.crop,
            year=args.cdl_year,
        )
        counties = [top]
    else:
        fips_codes = _parse_csv_values(args.fips_codes)
        if not fips_codes:
            raise ValueError("--fips-codes is required for selector=fips")
        counties = _resolve_counties_from_fips(
            fips_level=args.fips_level,
            fips_codes=fips_codes,
            state_fips=state_fips,
            county_limit=args.county_limit,
        )

    inventory = _run_bootstrap_for_counties(
        counties=counties,
        field_count=args.field_count,
        seed=args.seed,
        grower_slug=args.grower_slug,
        farm_slug=farm_slug,
        farm_name=farm_name,
    )
    _run_pipeline_for_farm(
        grower_slug=args.grower_slug,
        farm_slug=farm_slug,
        farm_name=farm_name,
        inventory_path=inventory,
        force=args.force,
    )

    print(
        json.dumps(
            {
                "action": "create",
                "selector": args.selector,
                "counties": counties,
                "field_count_requested": args.field_count,
                "grower_slug": args.grower_slug,
                "farm_slug": farm_slug,
                "farm_name": farm_name,
                "state": state,
                "inventory_csv": _runtime_relative(inventory),
            },
            indent=2,
        )
    )


def _ensure_inventory_for_boundary(boundary_path: Path, inventory_path: Path) -> None:
    if inventory_path.exists():
        return
    frame = gpd.read_file(boundary_path)
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field_id", "field_slug"])
        for field_id in frame["field_id"].astype(str).tolist():
            writer.writerow([field_id, field_slug_from_id(field_id)])


def _discover_farms(
    scope: str, grower_slug: str | None, farm_slug: str | None
) -> list[dict[str, str]]:
    farms: list[dict[str, str]] = []
    for grower_dir in sorted(GROWERS_ROOT.glob("*")):
        if not grower_dir.is_dir():
            continue
        g_slug = grower_dir.name
        if scope in {"farm", "grower"} and grower_slug and g_slug != grower_slug:
            continue
        for farm_dir in sorted((grower_dir / "farms").glob("*")):
            if not farm_dir.is_dir():
                continue
            f_slug = farm_dir.name
            if scope == "farm" and farm_slug and f_slug != farm_slug:
                continue
            boundary = farm_dir / "boundary" / "field_boundaries.geojson"
            if not boundary.exists():
                continue
            farms.append(
                {
                    "grower_slug": g_slug,
                    "farm_slug": f_slug,
                    "farm_name": f_slug.replace("-", " ").title(),
                }
            )
    if not farms:
        raise RuntimeError("No farms discovered for refresh scope")
    return farms


def refresh_command(args: argparse.Namespace) -> None:
    farms = _discover_farms(args.scope, args.grower_slug, args.farm_slug)
    for item in farms:
        boundary = farm_boundary_path(item["grower_slug"], item["farm_slug"])
        inventory = _inventory_path_for_farm(item["grower_slug"], item["farm_slug"])
        _ensure_inventory_for_boundary(boundary, inventory)
        _run_pipeline_for_farm(
            grower_slug=item["grower_slug"],
            farm_slug=item["farm_slug"],
            farm_name=item["farm_name"],
            inventory_path=inventory,
            force=args.force,
        )

    print(
        json.dumps(
            {
                "action": "refresh",
                "scope": args.scope,
                "farm_count": len(farms),
                "farms": farms,
                "force": bool(args.force),
            },
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or refresh farm intelligence dashboards"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create/expand farm and run full pipeline")
    create.add_argument(
        "--selector", choices=["top-crop-county", "fips"], default="top-crop-county"
    )
    create.add_argument("--crop", choices=sorted(CROP_CODE.keys()), default="corn")
    create.add_argument("--cdl-year", type=int, default=2025)
    create.add_argument(
        "--state",
        default=None,
        help="State name, abbreviation, or FIPS. Example: Illinois, IL, or 17.",
    )
    create.add_argument("--state-fips", default=None)
    create.add_argument("--fips-level", choices=["l2", "l1", "l0"], default="l2")
    create.add_argument(
        "--fips-codes",
        default=None,
        help="Comma-separated FIPS codes for selector=fips",
    )
    create.add_argument("--county-limit", type=int, default=None)
    create.add_argument("--field-count", type=int, required=True)
    create.add_argument("--seed", type=int, default=42)
    create.add_argument("--grower-slug", required=True)
    create.add_argument("--farm-slug", default=None)
    create.add_argument("--farm-name", default=None)
    create.add_argument(
        "--prepare-shared-data",
        action="store_true",
        help="Initialize shared geoadmin, county weather, maturity, and CDL rasters first",
    )
    create.add_argument("--shared-start-year", type=int, default=2021)
    create.add_argument("--shared-end-year", type=int, default=2025)
    create.add_argument(
        "--shared-coverage",
        choices=["traditional-corn-belt", "lower48"],
        default="lower48",
    )
    create.add_argument(
        "--shared-weather-backend", choices=["zarr", "api"], default="zarr"
    )
    create.add_argument(
        "--shared-weather-time-standard", choices=["lst", "utc"], default="lst"
    )
    create.add_argument("--cdl-scope", choices=["conus", "state"], default="conus")
    create.add_argument("--cdl-latest-year", type=int, default=2025)
    create.add_argument("--cdl-window-years", type=int, default=5)
    create.add_argument("--force", action="store_true")
    create.set_defaults(handler=create_command)

    refresh = sub.add_parser(
        "refresh", help="Refresh one farm, one grower, or all farms"
    )
    refresh.add_argument("--scope", choices=["farm", "grower", "all"], default="farm")
    refresh.add_argument("--grower-slug", default=None)
    refresh.add_argument("--farm-slug", default=None)
    refresh.add_argument("--force", action="store_true")
    refresh.set_defaults(handler=refresh_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
