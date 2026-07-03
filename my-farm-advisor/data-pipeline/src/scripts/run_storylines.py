#!/usr/bin/env python3
"""Generate per-year field-season weather & NDVI storyline dashboards.

Usage:
    python scripts/run_storylines.py \
        --grower-slug ia-grower \
        --farm-slug ia-grower-iowa \
        --field-id osm-1360330515

Output:
    fields/<field>/derived/storylines/<year>_field_season_storyline.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _find_skill_root(runtime_base: Path) -> Path:
    locator = runtime_base / ".my-farm-advisor-source.json"
    if locator.exists():
        try:
            info = json.loads(locator.read_text(encoding="utf-8"))
            root = Path(info["my_farm_advisor_skill_root"])
            if root.is_dir():
                return root
        except Exception:
            pass
    return runtime_base.parent.parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-year weather & NDVI storyline")
    parser.add_argument("--grower-slug", required=True)
    parser.add_argument("--farm-slug", required=True)
    parser.add_argument("--field-id", required=True)
    parser.add_argument("--years", default=None,
                        help="Comma-separated years (default: 2021-2025)")
    args = parser.parse_args()

    try:
        from lib.runtime_paths import resolve_runtime_paths
    except ImportError:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        sys.path.insert(0, str(scripts_dir / "lib"))
        from lib.runtime_paths import resolve_runtime_paths

    _paths = resolve_runtime_paths()
    runtime_base = _paths.runtime_base
    prefix = args.farm_slug.strip().replace("-", "_")

    subskill_src = (
        runtime_base / "src" / "eda-assignment3"
        if (runtime_base / "src" / "eda-assignment3").is_dir()
        else _find_skill_root(runtime_base) / "eda" / "eda-assignment3" / "src"
    )
    if subskill_src.is_dir():
        sys.path.insert(0, str(subskill_src))

    from weather_ndvi_storylines import generate_storyline, DEFAULT_YEARS

    field_dir = (
        runtime_base / "growers" / args.grower_slug / "farms" / args.farm_slug
        / "fields" / args.field_id
    )
    if not field_dir.is_dir():
        print(f"ERROR: field directory not found: {field_dir}", file=sys.stderr)
        sys.exit(1)

    tables_dir = (
        runtime_base / "growers" / args.grower_slug / "farms" / args.farm_slug
        / "derived" / "tables"
    )
    weather_csv = tables_dir / f"{prefix}_weather_2021_2025.csv"
    rotation_csv = tables_dir / f"{prefix}_crop_rotation.csv"

    if not weather_csv.exists():
        print(f"ERROR: weather CSV not found: {weather_csv}", file=sys.stderr)
        sys.exit(1)

    output_dir = field_dir / "derived" / "storylines"

    if args.years:
        years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    else:
        years = DEFAULT_YEARS

    results = []
    for year in years:
        result = generate_storyline(
            grower_slug=args.grower_slug,
            farm_slug=args.farm_slug,
            field_id=args.field_id,
            field_dir=field_dir,
            farm_weather_csv=weather_csv,
            farm_rotation_csv=rotation_csv,
            output_dir=output_dir,
            year=year,
        )
        results.append(result)
        rel = Path(result["storyline_png"]).relative_to(runtime_base)
        size_kb = Path(result["storyline_png"]).stat().st_size / 1024
        cov = result["coverage"]["warning"] or "OK"
        print(f"  {result['year']} {result['crop']:10s}  scenes={result['ndvi_scenes']}  "
              f"peak_NDVI={result['peak_ndvi']:.3f}  precip={result['total_precip_in']}\"  "
              f"GDD={result['peak_gdd_f']:.0f}  {cov[:40]}  {rel}  ({size_kb:.0f} KB)")

    print(f"\nGenerated {len(results)} dashboard(s) in {output_dir}")


if __name__ == "__main__":
    main()
