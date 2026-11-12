#!/usr/bin/env python3
"""Generate one lightweight interactive HTML field map per My Farm Advisor grower.

Reads the installed runtime tree and writes, for each grower:

    <runtime>/data-pipeline/growers/<grower>/derived/maps/<grower>_fields_map.html
    <runtime>/data-pipeline/growers/<grower>/derived/maps/<grower>_fields_map.manifest.json

Every displayed area is hectares, converted from the boundary file's
``area_acres`` with 1 acre = 4046.8564224 m^2.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT / "src"))

from grower_web_map import (  # noqa: E402
    ACRE_TO_HECTARE,
    GrowerMapError,
    list_growers,
    resolve_runtime_base,
    write_grower_map,
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a lightweight interactive HTML map for each grower in the "
            "My Farm Advisor runtime. Areas are reported in hectares."
        )
    )
    parser.add_argument(
        "--grower-slug",
        action="append",
        metavar="SLUG",
        help=(
            "Grower to render. Repeat for several growers. "
            "Defaults to every grower under the runtime."
        ),
    )
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_PIPELINE_DATA_ROOT"),
        help=(
            "Runtime root, e.g. ~/my-farm-advisor-runtime. Defaults to "
            "DATA_PIPELINE_DATA_ROOT."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "Directory for the generated HTML and manifest. Only valid with one "
            "grower; defaults to <runtime>/data-pipeline/growers/<grower>/derived/maps."
        ),
    )
    parser.add_argument(
        "--title",
        help="Optional HTML map title. Defaults to '<grower name> — field map'.",
    )
    parser.add_argument(
        "--area-decimals",
        type=_positive_int,
        default=1,
        help="Decimal places for hectares in the console summary (default: 1).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors and the final summary line.",
    )
    return parser


def _format_bytes(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.data_root:
        print(
            "ERROR: no runtime root. Set DATA_PIPELINE_DATA_ROOT or pass --data-root.",
            file=sys.stderr,
        )
        return 2

    try:
        base = resolve_runtime_base(Path(args.data_root))
    except GrowerMapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    available = list_growers(base)
    if not available:
        print(f"ERROR: no growers found under {base / 'growers'}", file=sys.stderr)
        return 2

    requested = args.grower_slug or available
    if args.output_dir and len(requested) != 1:
        print("ERROR: --output-dir requires exactly one --grower-slug.", file=sys.stderr)
        return 2

    missing = [slug for slug in requested if slug not in available]
    if missing:
        print(
            f"ERROR: unknown grower(s): {', '.join(missing)}. "
            f"Available: {', '.join(available)}",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    if not args.quiet:
        print(f"Runtime: {base}")
        print(f"Growers: {', '.join(requested)}")
        print(
            "Area conversion: hectares = acres x "
            f"{ACRE_TO_HECTARE:.11f} (1 acre = 4046.8564224 m2)"
        )

    failures = 0
    rows: list[dict[str, object]] = []
    for slug in requested:
        try:
            result = write_grower_map(
                base=base,
                grower_slug=slug,
                output_dir=output_dir,
                title=args.title,
            )
        except GrowerMapError as exc:
            failures += 1
            print(f"FAILED {slug}: {exc}", file=sys.stderr)
            continue
        rows.append(result)
        if not args.quiet:
            print(
                f"  wrote {slug}: {result['field_count']} fields, "
                f"{result['farm_count']} farms, "
                f"{result['area_ha']:.{args.area_decimals}f} ha, "
                f"{_format_bytes(int(result['html_bytes']))}"
            )
            print(f"         {result['html_path']}")
        if result["skipped_features"]:
            print(
                f"  WARN {slug}: skipped {result['skipped_features']} unusable feature(s); "
                f"see {result['manifest_path']}",
                file=sys.stderr,
            )

    if rows:
        width = max(len(str(row["grower_slug"])) for row in rows)
        print()
        print(
            f"{'grower'.ljust(width)}  farms  fields   area_ha  html"
        )
        for row in rows:
            print(
                f"{str(row['grower_slug']).ljust(width)}  "
                f"{int(row['farm_count']):>5}  {int(row['field_count']):>6}  "
                f"{float(row['area_ha']):>8.{args.area_decimals}f}  "
                f"{_format_bytes(int(row['html_bytes']))}"
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
