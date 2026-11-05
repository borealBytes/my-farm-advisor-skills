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
    # Country (L0) and state/province (L1) borders, clipped to the plotted
    # extent, so a multi-country choropleth says what is US and what is
    # Canada without needing a basemap.
    minx, miny, maxx, maxy = counties.total_bounds
    vis_bbox = (minx - 1, miny - 1, maxx + 1, maxy + 1)
    try:
        from paths import shared_geoadmin_dir

        # Natural Earth country polygons exceed pyogrio's default GeoJSON
        # object size cap; lift it for these reads.
        os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")
        gd_root = shared_geoadmin_dir()
        # White lines with a thin dark casing: the standard trick so borders
        # stay visible over BOTH the dark end of the choropleth ramp and the
        # pale end (black vanishes on dark greens, white alone vanishes on
        # pale yellows — the casing carries it on light fills).
        for rel, lw in (
            ("l1_states/states_usa.geojson", 0.7),
            ("l1_states/states_canada.geojson", 0.7),
            ("l0_countries/countries.geojson", 1.5),
        ):
            border_path = gd_root / rel
            if not border_path.exists():
                continue
            _b = gpd.read_file(border_path).to_crs("EPSG:4326")
            lines = _b.cx[vis_bbox[0]:vis_bbox[2], vis_bbox[1]:vis_bbox[3]]
            if lines.empty:
                continue
            lines.boundary.plot(ax=ax, color="#1f2937", linewidth=lw + 0.9,
                                zorder=4, alpha=0.85)
            lines.boundary.plot(ax=ax, color="#ffffff", linewidth=lw, zorder=5)
        ax.set_xlim(minx - 0.4, maxx + 0.4)
        ax.set_ylim(miny - 0.4, maxy + 0.4)
    except Exception:  # noqa: BLE001 — borders are cosmetic
        pass
    # Keep the title narrower than the map so the tight-bbox crop does not
    # stretch the canvas into white side margins.
    import textwrap

    ax.set_title(
        "\n".join(textwrap.wrap(title, 58))
        + "\n"
        + "\n".join(textwrap.wrap(subtitle, 64)),
        fontsize=13,
        fontweight="bold",
    )
    ax.tick_params(labelbottom=False, labelleft=False, bottom=False, left=False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


_REGION_TITLES = {
    "usa": "Contiguous U.S.",
    "canada": "Canada (Census Divisions)",
    "north-america": "U.S. + Southern Canada",
}
# Empty suffix keeps the historical US-only output paths byte-identical.
_OUTPUT_SUFFIXES = {"usa": "", "canada": "_canada", "north-america": "_northamerica"}

# North-America maps stop ~250 mi north of the contiguous-U.S. northern border
# (49 N + 250 mi ≈ 52.6 N): the Canadian Prairies' corn/soy belt is in, the
# boreal waste is not, and the picture stays about what corn actually grows.
_NORTH_AMERICA_LAT_CAP = 52.6


def _load_region_counties(country: str, counties_dir: Path) -> gpd.GeoDataFrame:
    from maturity_by_fips import contiguous_us_counties

    frames: list[gpd.GeoDataFrame] = []
    if country in ("usa", "north-america"):
        usa = gpd.read_file(Path(counties_dir) / "counties_usa.geojson")
        usa = contiguous_us_counties(usa)
        frames.append(gpd.GeoDataFrame(usa[["fips", "geometry"]]))
    if country in ("canada", "north-america"):
        canada = gpd.read_file(Path(counties_dir) / "counties_canada.geojson")
        canada = gpd.GeoDataFrame(canada[["fips", "geometry"]]).to_crs("EPSG:4326")
        if country == "north-america":
            inside = canada[canada.geometry.centroid.y <= _NORTH_AMERICA_LAT_CAP]
            canada = gpd.GeoDataFrame(inside[["fips", "geometry"]], crs="EPSG:4326").to_crs(
                gpd.read_file(Path(counties_dir) / "counties_usa.geojson").crs
            )
        frames.append(canada[["fips", "geometry"]] if hasattr(canada, "crs") else canada)
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
    geo_note = ""
    if args.country != "usa":
        geo_note = (
            " | Geography: L2 U.S. counties + Canadian census divisions north of the border, "
            "capped ~250 mi (400 km) into Canada"
        )

    _render_map(
        corn_map,
        value_column="rm_relative_maturity",
        title=f"Heuristic Corn RM by FIPS - {region_title} ({args.year})",
        subtitle="Planning layer only - derived from county GDD, not recommendation-grade guidance" + geo_note,
        output_path=shared_corn_maturity_reports_dir() / f"rm_by_fips_{args.year}{suffix}.png",
        cmap="YlGn",
    )
    _render_map(
        soy_map,
        value_column="mg_optimal",
        title=f"Heuristic Soybean MG by FIPS - {region_title} ({args.year})",
        subtitle="Planning layer only - latitude-based maturity heuristic, not a planting prescription" + geo_note,
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
