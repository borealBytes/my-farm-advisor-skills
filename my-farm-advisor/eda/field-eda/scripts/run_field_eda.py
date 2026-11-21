#!/usr/bin/env python3
"""Run the field-level EDA over an installed My Farm Advisor runtime.

Examples
--------
    export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
    python run_field_eda.py --check-only
    python run_field_eda.py
    python run_field_eda.py --grower ne-york-grower --category cdl
    python run_field_eda.py --category signals
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

CATEGORIES = ("boundaries", "cdl", "weather", "signals")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-grower field EDA for boundary, CDL, weather, and field-signal "
            "data."
        )
    )
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_PIPELINE_DATA_ROOT", ""),
        help="runtime root (default: $DATA_PIPELINE_DATA_ROOT)",
    )
    parser.add_argument(
        "--grower", action="append", default=None,
        help="grower slug to include; repeatable (default: every grower)",
    )
    parser.add_argument(
        "--category", action="append", choices=CATEGORIES, default=None,
        help="category to run; repeatable (default: all)",
    )
    parser.add_argument(
        "--out", default=None,
        help="output directory (default: <runtime>/data-pipeline/eda/field-eda)",
    )
    parser.add_argument("--dpi", type=int, default=150, help="figure DPI (default: 150)")
    parser.add_argument("--season-start-month", type=int, default=4)
    parser.add_argument("--season-end-month", type=int, default=9)
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument(
        "--check-only", action="store_true",
        help="validate discovery and schemas, then exit without writing anything",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="allow writing into a non-empty output directory",
    )
    return parser.parse_args(argv)


def _versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "geopandas", "shapely", "scipy", "matplotlib"):
        try:
            module = __import__(name)
        except ImportError:  # pragma: no cover - environment issue
            versions[name] = "missing"
        else:
            versions[name] = str(getattr(module, "__version__", "unknown"))
    return versions


def _field_metrics(analysis) -> "object":
    import pandas as pd

    from field_eda import metrics

    fields = analysis.fields.drop(columns="geometry").copy()
    columns = [
        "grower", "grower_slug", "farm_slug", "state", "field_id", "source_key",
        "area_ha", "perimeter_m", "compactness", "bearing_deg", "vertices",
    ]
    table = fields[[column for column in columns if column in fields.columns]].copy()

    crops = metrics.field_crop_summary(analysis.cdl, analysis.dominant)
    keep = ["grower", "field_id", "rotation", "crop_diversity", "corn_years",
            "soybean_years", "dominant_crop_2023"]
    table = table.merge(crops[keep], on=["grower", "field_id"], how="left")

    coverage = metrics.cdl_coverage(analysis.cdl, analysis.fields)
    table = table.merge(
        coverage[["grower", "field_id", "coverage"]].rename(columns={"coverage": "cdl_coverage"}),
        on=["grower", "field_id"], how="left",
    )

    weather = (
        analysis.field_year_weather.groupby(["grower", "field_id"], sort=True)
        .agg(
            mean_precip_mm=("precip_mm", "mean"),
            mean_gdd=("gdd", "mean"),
            mean_heat_days=("heat_days", "mean"),
        )
        .reset_index()
    )
    table = table.merge(weather, on=["grower", "field_id"], how="left")

    runs = metrics.corn_run_lengths(analysis.dominant)
    table = table.merge(
        runs[["grower", "field_id", "longest_corn_run", "current_corn_run"]],
        on=["grower", "field_id"], how="left",
    )

    fit = analysis.field_maturity
    maturity = (
        fit.groupby(["grower", "field_id"], sort=True)
        .agg(
            gdd_required_c=("gdd_required_c", "first"),
            mean_maturity_gdd=("gdd_maturity", "mean"),
            seasons_below_maturity_target=("shortfall_c", lambda values: int((values > 0).sum())),
            max_gdd_shortfall_c=("shortfall_c", "max"),
        )
        .reset_index()
    )
    table = table.merge(maturity, on=["grower", "field_id"], how="left")

    risk = (
        analysis.risk.groupby(["grower", "field_id"], sort=True)
        .agg(
            mean_dry_spell_days=("dry_spell_days", "mean"),
            mean_july_heat_days=("july_heat_days", "mean"),
            mean_jul_aug_precip_mm=("jul_aug_precip_mm", "mean"),
        )
        .reset_index()
    )
    table = table.merge(risk, on=["grower", "field_id"], how="left")

    counties = {
        farm.farm_slug: (farm.county_fips, farm.county_name)
        for farm in analysis.dataset.farms
    }
    table["county_fips"] = table["farm_slug"].map(
        lambda slug: counties.get(slug, ("", ""))[0]
    )
    table["county_name"] = table["farm_slug"].map(
        lambda slug: counties.get(slug, ("", ""))[1]
    )

    numeric = table.select_dtypes("number").columns
    table[numeric] = table[numeric].round(4)
    table = table.sort_values(["grower", "field_id"]).reset_index(drop=True)
    return table


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.data_root:
        print("error: pass --data-root or set DATA_PIPELINE_DATA_ROOT", file=sys.stderr)
        return 2

    root = Path(args.data_root).expanduser().resolve()
    runtime_src = root / "data-pipeline" / "src"
    if runtime_src.is_dir():
        sys.path.insert(0, str(runtime_src))

    from field_eda import boundaries, cdl, signals, weather
    from field_eda.context import Analysis
    from field_eda.discover import RunConfig, describe, discover

    config = RunConfig(
        season_start_month=args.season_start_month,
        season_end_month=args.season_end_month,
        dpi=args.dpi,
        seed=args.seed,
        bootstrap=args.bootstrap,
    )
    dataset = discover(root, growers=args.grower, config=config)
    print(describe(dataset))

    if args.check_only:
        print(
            "inputs valid: boundary, weather, CDL, and county maturity tables "
            "present; no soil input"
        )
        return 0

    out_dir = Path(args.out).expanduser() if args.out else root / "data-pipeline" / "eda" / "field-eda"
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        print(
            f"error: {out_dir} is not empty; pass --force to overwrite its contents",
            file=sys.stderr,
        )
        return 2

    analysis = Analysis(dataset=dataset, out_dir=out_dir, dpi=args.dpi)
    analysis.ensure_dirs()

    selected = args.category or list(CATEGORIES)
    modules = {
        "boundaries": boundaries,
        "cdl": cdl,
        "weather": weather,
        "signals": signals,
    }
    written: list[Path] = []
    for name in CATEGORIES:
        if name not in selected:
            continue
        print(f"running {name} ...")
        result = modules[name].run(analysis)
        for group in result.values():
            written += group

    metrics_table = _field_metrics(analysis)
    metrics_path = analysis.tables_dir / "field_metrics.csv"
    metrics_table.to_csv(metrics_path, index=False)
    written.append(metrics_path)

    captions = [path.with_suffix(".caption.md") for path in written if path.suffix == ".png"]
    written += [path for path in captions if path.is_file()]

    maturity_inputs = []
    if dataset.maturity is not None:
        maturity_paths = sorted(dataset.maturity.annual.values()) + [
            dataset.maturity.average,
            dataset.maturity.soybean_average,
        ]
        maturity_inputs = [
            {"path": str(path), "kind": "maturity", "sha256": _sha256(path)}
            for path in maturity_paths
        ]

    manifest = {
        "skill": "field-eda",
        "version": "0.2.0",
        "runtime": str(root),
        "output_dir": str(out_dir),
        "categories": selected,
        "config": {
            "season_start_month": config.season_start_month,
            "season_end_month": config.season_end_month,
            "gdd_base_c": 10.0,
            "gdd_cap_c": 30.0,
            "gdd_per_rm_c": 20.0,
            "dpi": config.dpi,
            "seed": config.seed,
            "bootstrap": config.bootstrap,
        },
        "environment": _versions(),
        "growers": [
            {
                "slug": grower.slug,
                "label": grower.label,
                "state": grower.state,
                "fields": len(grower.fields),
                "farms": [farm.farm_slug for farm in grower.farms],
                "grid_cells": grower.grid_cells,
                "counties": [
                    {
                        "fips": farm.county_fips,
                        "name": farm.county_name,
                    }
                    for farm in grower.farms
                ],
            }
            for grower in dataset.growers
        ],
        "counts": {
            "growers": len(dataset.growers),
            "fields": dataset.field_count,
            "farms": len(dataset.farms),
            "field_years_cdl": int(len(analysis.dominant)),
            "field_years_weather": int(len(analysis.field_year_weather)),
            "field_years_maturity": int(len(analysis.field_maturity)),
        },
        "inputs": [
            {
                "path": str(farm.boundary_path),
                "kind": "boundaries",
                "sha256": _sha256(farm.boundary_path),
            }
            for farm in dataset.farms
        ]
        + [
            {
                "path": str(farm.weather_path),
                "kind": "weather",
                "sha256": _sha256(farm.weather_path),
            }
            for farm in dataset.farms
        ]
        + [
            {
                "path": str(farm.cdl_path),
                "kind": "cdl",
                "sha256": _sha256(farm.cdl_path),
            }
            for farm in dataset.farms
        ]
        + maturity_inputs,
        "outputs": [
            {"path": str(path.relative_to(out_dir)), "sha256": _sha256(path)}
            for path in sorted(written)
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")

    print(f"wrote {len(written)} outputs + manifest to {out_dir}")
    for path in sorted(written):
        print(f"  {path.relative_to(out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
