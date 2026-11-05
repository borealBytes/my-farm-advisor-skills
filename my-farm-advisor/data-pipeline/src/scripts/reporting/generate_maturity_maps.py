#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""Render static county maturity maps from canonical corn and soybean tables."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# TIGER/GADM county geojsons contain multi-megabyte multipolygons that trip
# GDAL's single-feature object guard (see references/canada-shared-geodata.md).
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--country",
        choices=["usa", "canada", "north-america"],
        default="usa",
        help="Map extent: contiguous U.S. (default, unchanged paths), Canadian "
        "census divisions, or both combined as North America.",
    )
    return parser.parse_args()


def _render_map(
    counties: gpd.GeoDataFrame,
    *,
    value_column: str,
    title: str,
    subtitle: str,
    output_path: Path,
    cmap: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 9))
    counties.boundary.plot(ax=ax, linewidth=0.15, color="#d1d5db")
    counties.plot(
        ax=ax,
        column=value_column,
        cmap=cmap,
        linewidth=0.2,
        edgecolor="#f9fafb",
        legend=True,
        legend_kwds={"shrink": 0.7, "label": value_column},
        missing_kwds={"color": "#e5e7eb", "label": "No county output"},
    )
    # Great Lakes etc. painted over the choropleth (Natural Earth 10 m lakes,
    # cached by the geoadmin ingest) so water reads as water.
    try:
        from paths import shared_geoadmin_dir

        lakes_p = shared_geoadmin_dir() / "lakes" / "lakes.geojson"
        if lakes_p.exists():
            lakes = gpd.read_file(lakes_p)
            # clip to map extent to avoid drawing Antarctic lakes at continental scale
            minx, miny, maxx, maxy = counties.total_bounds
            lakes = lakes.cx[minx:minx + (maxx - minx) * 1.15, miny - (maxy - miny) * 0.15:maxy + (maxy - miny) * 0.15]
            lakes.plot(ax=ax, facecolor="#bfdbfe", edgecolor="#93c5fd", linewidth=0.3, zorder=3)
    except Exception:
        pass
    ax.set_title(f"{title}\n{subtitle}", fontsize=14, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


_REGION_TITLES = {
    "usa": "Contiguous U.S.",
    "canada": "Canada (Census Divisions)",
    "north-america": "North America",
}
# Empty suffix keeps the historical US-only output paths byte-identical.
_OUTPUT_SUFFIXES = {"usa": "", "canada": "_canada", "north-america": "_northamerica"}


def _load_region_counties(country: str, counties_dir: Path) -> gpd.GeoDataFrame:
    from maturity_by_fips import contiguous_us_counties

    frames: list[gpd.GeoDataFrame] = []
    if country in ("usa", "north-america"):
        usa = gpd.read_file(Path(counties_dir) / "counties_usa.geojson")
        usa = contiguous_us_counties(usa)
        frames.append(gpd.GeoDataFrame(usa[["fips", "geometry"]]))
    if country in ("canada", "north-america"):
        canada = gpd.read_file(Path(counties_dir) / "counties_canada.geojson")
        frames.append(gpd.GeoDataFrame(canada[["fips", "geometry"]]))
    if len(frames) > 1:
        region = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    else:
        region = frames[0]
    region["fips"] = region["fips"].astype(str)
    return region


def main() -> int:
    from paths import (
        shared_corn_maturity_reports_dir,
        shared_corn_rm_table_path,
        shared_geoadmin_counties_dir,
        shared_soybean_maturity_reports_dir,
        shared_soybean_mg_table_path,
    )
    from reporting_bootstrap import ensure_canonical_data_tree, ensure_skill_path

    args = parse_args()
    ensure_canonical_data_tree(include_farm=False)
    ensure_skill_path("maturity-by-fips")

    counties = _load_region_counties(args.country, shared_geoadmin_counties_dir())

    corn = pd.read_parquet(shared_corn_rm_table_path(args.year))
    soy = pd.read_parquet(shared_soybean_mg_table_path(args.year))
    corn["fips"] = corn["fips"].astype(str)
    soy["fips"] = soy["fips"].astype(str)

    corn_map = counties.merge(corn[["fips", "rm_relative_maturity"]], on="fips", how="left")
    soy_map = counties.merge(soy[["fips", "mg_optimal"]], on="fips", how="left")
    region_title = _REGION_TITLES[args.country]
    suffix = _OUTPUT_SUFFIXES[args.country]

    _render_map(
        corn_map,
        value_column="rm_relative_maturity",
        title=f"Heuristic Corn RM by FIPS - {region_title} ({args.year})",
        subtitle="Planning layer only - derived from county GDD, not recommendation-grade guidance",
        output_path=shared_corn_maturity_reports_dir() / f"rm_by_fips_{args.year}{suffix}.png",
        cmap="YlGn",
    )
    _render_map(
        soy_map,
        value_column="mg_optimal",
        title=f"Heuristic Soybean MG by FIPS - {region_title} ({args.year})",
        subtitle="Planning layer only - latitude-based maturity heuristic, not a planting prescription",
        output_path=shared_soybean_maturity_reports_dir() / f"mg_by_fips_{args.year}{suffix}.png",
        cmap="YlOrBr",
    )
    resolved_corn = int(corn_map["rm_relative_maturity"].notna().sum())
    resolved_soy = int(soy_map["mg_optimal"].notna().sum())
    print(
        f"country={args.country} year={args.year} units={len(corn_map)} "
        f"corn_rm_resolved={resolved_corn} soybean_mg_resolved={resolved_soy}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
