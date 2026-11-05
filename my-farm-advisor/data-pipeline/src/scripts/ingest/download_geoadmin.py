#!/usr/bin/env python3
"""Download and standardize shared geoadmin assets into canonical paths."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

GEOADMIN_LEVEL_CHOICES = (
    "l0_countries",
    "l1_states",
    "l2_counties",
    "l1_states_canada",
    "l2_counties_canada",
    "lakes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--levels",
        nargs="+",
        default=list(GEOADMIN_LEVEL_CHOICES),
        help="Geoadmin levels to build (plus l1_states_<iso>/l2_counties_<iso> via --gadm-iso)",
    )
    parser.add_argument(
        "--census-year",
        type=int,
        default=2025,
        help="TIGER/Line vintage year for US state and county layers",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download and overwrite outputs"
    )
    parser.add_argument(
        "--gadm-iso",
        nargs="+",
        default=[],
        metavar="ISO3",
        help="Build GADM 4.1 L1/L2 for any country (ISO3, e.g. AUS MEX DEU). "
             "Adds l1_states_<iso>/l2_counties_<iso> levels.",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="Print the resolved source catalog and exit",
    )
    return parser.parse_args()


def main() -> int:
    from reporting_bootstrap import ensure_canonical_data_tree, ensure_skill_path

    args = parse_args()
    ensure_canonical_data_tree(include_farm=False)
    ensure_skill_path("geoadmin-admin")

    geoadmin_admin = importlib.import_module("geoadmin_admin")

    import re as _re
    iso_levels = {
        level
        for iso3 in args.gadm_iso
        for level in geoadmin_admin.gadm_country_sources(iso3)
    }
    valid = set(GEOADMIN_LEVEL_CHOICES) | iso_levels
    bad = [level for level in args.levels if level not in valid]
    if bad:
        parser.error(f"unknown levels {bad}; valid: {sorted(valid)}")

    catalog = geoadmin_admin.build_source_catalog(args.census_year)
    for iso3 in args.gadm_iso:
        catalog.update(geoadmin_admin.gadm_country_sources(iso3))
    if args.gadm_iso and args.levels == list(GEOADMIN_LEVEL_CHOICES):
        # Sensible default when a country is requested: global context plus
        # that country's two levels — not every US/CA layer too.
        args.levels = ["l0_countries", "lakes"] + [
            level for level in catalog if any(level.endswith(f"_{iso3.lower()}") for iso3 in args.gadm_iso)
        ]
    if args.list_sources:
        printable = {
            level: {
                "source_name": source.source_name,
                "source_url": source.source_url,
                "archive_name": source.archive_name,
                "vintage": source.vintage,
            }
            for level, source in catalog.items()
            if level in args.levels
        }
        print(json.dumps(printable, indent=2, sort_keys=True))
        return 0

    results: dict[str, dict[str, str]] = {}
    for level in args.levels:
        source = catalog[level]
        print(f"Building {level} from {source.source_name} ({source.vintage})")
        archive_path = geoadmin_admin.download_source_archive(source, force=args.force)
        frame = geoadmin_admin.standardize_geoadmin_layer(source, archive_path)
        outputs = geoadmin_admin.write_standardized_outputs(source, frame)
        results[level] = {name: str(path) for name, path in outputs.items()}
        print(f"  Saved {level}: {results[level]}")

    if any(level.startswith("l2_counties") for level in args.levels):
        combined = geoadmin_admin.write_combined_fips_lookup()
        if combined is not None:
            results["fips_lookup_combined"] = {"lookup": str(combined)}
            print(f"  Combined county-role lookup (US + Canada): {combined}")

    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
