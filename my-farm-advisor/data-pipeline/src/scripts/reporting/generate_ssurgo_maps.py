#!/usr/bin/env python3
# ruff: noqa: E402
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportArgumentType=false, reportCallIssue=false, reportReturnType=false
"""Generate SSURGO soil map overlays with basemap, soil polygons, and field boundaries.

Downloads SSURGO polygons from USDA API if not cached locally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely import wkt

matplotlib.use("Agg")

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from paths import (
    farm_boundary_path,
    farm_ssurgo_full_path,
    field_feature_path,
    field_soil_polygon_path,
)
from reporting_bootstrap import field_slug_map_from_inventory

_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")

PROPERTY_SPECS = [
    ("comppct_r", "Dominant Component", "%", "component_pct"),
    ("om_r", "Organic Matter", "%", "organic_matter"),
    ("ph1to1h2o_r", "pH", "", "ph"),
    ("awc_r", "Available Water Capacity", "cm/cm", "awc"),
    ("claytotal_r", "Clay", "%", "clay"),
    ("sandtotal_r", "Sand", "%", "sand"),
    ("silttotal_r", "Silt", "%", "silt"),
    ("dbthirdbar_r", "Bulk Density", "g/cm3", "bulk_density"),
    ("cec7_r", "CEC", "cmol(+)/kg", "cec"),
]

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"


def _query_sda_table(sql: str, timeout: int = 120) -> list[list[object]]:
    resp = requests.post(SDA_URL, data={"query": sql, "format": "JSON"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("Table", [])


def _fetch_mukey_attributes(mukeys: list[str]) -> pd.DataFrame:
    if not mukeys:
        return pd.DataFrame(
            columns=[
                "mukey",
                "compname",
                "comppct_r",
                "drainagecl",
                "om_r",
                "ph1to1h2o_r",
                "awc_r",
                "claytotal_r",
                "sandtotal_r",
                "silttotal_r",
                "dbthirdbar_r",
                "cec7_r",
            ]
        )

    mukey_sql = ", ".join(f"'{m}'" for m in sorted(set(str(m) for m in mukeys)))
    sql = f"""
    SELECT c.mukey, c.compname, c.comppct_r, c.drainagecl,
           ch.om_r, ch.ph1to1h2o_r, ch.awc_r, ch.claytotal_r, ch.sandtotal_r,
           ch.silttotal_r, ch.dbthirdbar_r, ch.cec7_r
    FROM component c
    LEFT JOIN chorizon ch ON c.cokey = ch.cokey
    WHERE c.mukey IN ({mukey_sql})
      AND c.majcompflag = 'Yes'
      AND (ch.hzdept_r < 30 OR ch.hzdept_r IS NULL)
    ORDER BY c.mukey, c.comppct_r DESC, ch.hzdept_r ASC
    """
    try:
        rows = _query_sda_table(sql)
    except Exception as e:
        print(f"    Warning: MUKEY attribute lookup failed: {e}")
        return pd.DataFrame(
            columns=[
                "mukey",
                "compname",
                "comppct_r",
                "drainagecl",
                "om_r",
                "ph1to1h2o_r",
                "awc_r",
                "claytotal_r",
                "sandtotal_r",
                "silttotal_r",
                "dbthirdbar_r",
                "cec7_r",
            ]
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "mukey",
                "compname",
                "comppct_r",
                "drainagecl",
                "om_r",
                "ph1to1h2o_r",
                "awc_r",
                "claytotal_r",
                "sandtotal_r",
                "silttotal_r",
                "dbthirdbar_r",
                "cec7_r",
            ]
        )

    attrs = pd.DataFrame(
        rows,
        columns=[
            "mukey",
            "compname",
            "comppct_r",
            "drainagecl",
            "om_r",
            "ph1to1h2o_r",
            "awc_r",
            "claytotal_r",
            "sandtotal_r",
            "silttotal_r",
            "dbthirdbar_r",
            "cec7_r",
        ],
    )
    attrs["mukey"] = attrs["mukey"].astype(str)
    for col in [
        "comppct_r",
        "om_r",
        "ph1to1h2o_r",
        "awc_r",
        "claytotal_r",
        "sandtotal_r",
        "silttotal_r",
        "dbthirdbar_r",
        "cec7_r",
    ]:
        attrs[col] = pd.to_numeric(attrs[col], errors="coerce")
    return (
        attrs.sort_values(["mukey", "comppct_r"], ascending=[True, False])
        .groupby("mukey", as_index=False)
        .agg(
            {
                "compname": "first",
                "comppct_r": "first",
                "drainagecl": "first",
                "om_r": "mean",
                "ph1to1h2o_r": "mean",
                "awc_r": "mean",
                "claytotal_r": "mean",
                "sandtotal_r": "mean",
                "silttotal_r": "mean",
                "dbthirdbar_r": "mean",
                "cec7_r": "mean",
            }
        )
    )


def download_ssurgo_polygons_for_field(
    field_gdf: gpd.GeoDataFrame, field_id: str
) -> gpd.GeoDataFrame:
    """Download SSURGO polygons from USDA API for a field boundary."""
    if field_gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    field_wgs84 = field_gdf.to_crs(epsg=4326)
    field_geom = field_wgs84.geometry.iloc[0]
    field_wkt = field_geom.wkt

    mukey_sql = f"""
    SELECT DISTINCT m.mukey
    FROM mupolygon m
    WHERE m.mupolygonkey IN (
        SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{field_wkt}')
    )
    """

    try:
        resp = requests.post(SDA_URL, data={"query": mukey_sql, "format": "JSON"}, timeout=60)
        resp.raise_for_status()
        mukey_rows = resp.json().get("Table", [])
        mukeys = [str(row[0]) for row in mukey_rows]
    except Exception as e:
        print(f"    Error querying MUKEYs: {e}")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    if not mukeys:
        print("    No SSURGO polygons found for field")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    print(f"    Found {len(mukeys)} map units")

    mukey_list = ", ".join(f"'{m}'" for m in mukeys)
    poly_sql = f"""
    SELECT m.mukey, m.mupolygonkey, m.mupolygongeo.STAsText() AS wkt
    FROM mupolygon m
    WHERE m.mukey IN ({mukey_list})
      AND m.mupolygonkey IN (
        SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{field_wkt}')
      )
    """

    try:
        resp = requests.post(SDA_URL, data={"query": poly_sql, "format": "JSON"}, timeout=120)
        resp.raise_for_status()
        rows = resp.json().get("Table", [])
    except Exception as e:
        print(f"    Error querying polygons: {e}")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    records = []
    for row in rows:
        try:
            records.append(
                {
                    "mukey": str(row[0]),
                    "mupolygonkey": str(row[1]),
                    "geometry": wkt.loads(row[2]),
                    "field_id": field_id,
                }
            )
        except Exception:
            continue

    if not records:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    return gpd.GeoDataFrame(records, crs="EPSG:4326")


def get_ssurgo_polygons_with_soil_data(
    field_gdf: gpd.GeoDataFrame, field_id: str
) -> gpd.GeoDataFrame:
    """Get SSURGO polygons merged with soil properties."""
    field_slug_map = field_slug_map_from_inventory()
    field_slug = field_slug_map.get(field_id)
    if not field_slug:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    cache_path = field_soil_polygon_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)

    polygons = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if cache_path.exists():
        print(f"    Loading cached polygons from {cache_path}")
        try:
            polygons = gpd.read_file(cache_path)
        except Exception as exc:
            print(f"    Warning: cached polygons unreadable ({exc}); refetching")
            polygons = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    if polygons.empty:
        print("    Downloading SSURGO polygons from USDA API...")
        polygons = download_ssurgo_polygons_for_field(field_gdf, field_id)

        if not polygons.empty:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            polygons.to_file(cache_path, driver="GeoJSON")
            print(f"    Cached polygons to {cache_path}")

    if polygons.empty:
        return polygons

    try:
        target_crs = polygons.crs or field_gdf.crs or "EPSG:4326"
        clip_target = field_gdf.to_crs(target_crs)
        polygons = gpd.clip(polygons, clip_target)
        polygons = polygons[~polygons.geometry.is_empty].copy()
    except Exception as e:
        print(f"    Warning: clipping failed, using uncut polygons: {e}")

    soil_csv = farm_ssurgo_full_path(_DEFAULT_GROWER, _DEFAULT_FARM)
    if soil_csv.exists():
        soil_df = pd.read_csv(soil_csv)
        soil_agg = (
            soil_df.groupby("mukey")
            .agg(
                {
                    "compname": "first",
                    "comppct_r": "first",
                    "drainagecl": "first",
                    "om_r": "mean",
                    "ph1to1h2o_r": "mean",
                    "awc_r": "mean",
                    "claytotal_r": "mean",
                    "sandtotal_r": "mean",
                    "silttotal_r": "mean",
                    "dbthirdbar_r": "mean",
                    "cec7_r": "mean",
                }
            )
            .reset_index()
        )
        soil_agg["mukey"] = soil_agg["mukey"].astype(str)

        polygons["mukey"] = polygons["mukey"].astype(str)
        polygons = polygons.merge(soil_agg, on="mukey", how="left")

    if "mukey" in polygons.columns:
        missing_attrs = (
            "om_r" not in polygons.columns
            or polygons["om_r"].isna().all()
            or "compname" not in polygons.columns
            or polygons["compname"].isna().all()
        )
        if missing_attrs:
            attrs = _fetch_mukey_attributes(polygons["mukey"].astype(str).tolist())
            if not attrs.empty:
                for col in [
                    "compname",
                    "comppct_r",
                    "drainagecl",
                    "om_r",
                    "ph1to1h2o_r",
                    "awc_r",
                    "claytotal_r",
                    "sandtotal_r",
                    "silttotal_r",
                    "dbthirdbar_r",
                    "cec7_r",
                ]:
                    if col in polygons.columns:
                        polygons = polygons.drop(columns=[col])
                polygons = polygons.merge(attrs, on="mukey", how="left")

    return gpd.GeoDataFrame(polygons, geometry="geometry", crs=polygons.crs)


def _add_basemap(ax, field_gdf: gpd.GeoDataFrame, zoom: int = 14):
    """Add contextily basemap to axes."""
    try:
        import contextily as ctx

        bounds = field_gdf.total_bounds
        margin_x = (bounds[2] - bounds[0]) * 0.2
        margin_y = (bounds[3] - bounds[1]) * 0.2

        ax.set_xlim(bounds[0] - margin_x, bounds[2] + margin_x)
        ax.set_ylim(bounds[1] - margin_y, bounds[3] + margin_y)

        esri = getattr(ctx.providers, "Esri")
        imagery = getattr(esri, "WorldImagery")
        ctx.add_basemap(ax, crs=field_gdf.crs, source=imagery, alpha=0.5)
        return True
    except Exception as e:
        print(f"    Basemap error: {e}")
        return False


def _classify_quantiles(values: pd.Series, class_count: int = 4) -> tuple[np.ndarray, list[str]]:
    arr = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    unique_values = np.sort(np.unique(arr))
    bins = max(1, min(class_count, unique_values.size))

    if arr.size == 0:
        return np.array([], dtype=int), []
    if bins == 1:
        v = float(arr[0]) if arr.size else 0.0
        return np.zeros(arr.size, dtype=int), [f"{v:.2f}"]

    edges = np.quantile(arr, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if edges.size < 2:
        v = float(arr[0]) if arr.size else 0.0
        return np.zeros(arr.size, dtype=int), [f"{v:.2f}"]

    class_ids = pd.cut(arr, bins=edges, labels=False, include_lowest=True)
    class_ids = pd.Series(class_ids).fillna(0).astype(int).to_numpy()
    labels = [f"Q{i + 1}: {edges[i]:.2f} to {edges[i + 1]:.2f}" for i in range(edges.size - 1)]
    class_ids = np.clip(class_ids, 0, max(0, len(labels) - 1))
    return class_ids, labels


def _render_map(
    field_gdf: gpd.GeoDataFrame,
    plot_source: gpd.GeoDataFrame,
    output_path: Path,
    title: str,
    legend_title: str,
    label_builder,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor("#fafaf9")

    if field_gdf.empty:
        ax.text(0.5, 0.5, "No field data", ha="center", va="center", transform=ax.transAxes)
        plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        return

    field_wm = field_gdf.to_crs(epsg=3857)
    use_basemap = _add_basemap(ax, field_wm, zoom=15)

    if not plot_source.empty:
        plot_target = plot_source.to_crs(epsg=3857) if use_basemap else plot_source
        max_class = int(pd.Series(plot_source["class_id"]).max()) if not plot_source.empty else 0
        # Categorical palette: adjacent soil components must be tellable apart
        # at a glance — a continuous green ramp fails the comparator test.
        _cmap = plt.get_cmap("tab20")
        colors = [_cmap(i % 20) for i in range(max(1, max_class + 1))]
        legend_elements: list[object] = [
            Line2D([0], [0], color="darkgreen", linewidth=3, label="Field Boundary")
        ]
        for class_id in sorted(plot_source["class_id"].unique()):
            class_slice = plot_target[plot_target["class_id"] == class_id]
            if class_slice.empty:
                continue
            class_slice.plot(
                ax=ax,
                color=colors[int(class_id)],
                alpha=0.62,
                edgecolor="#1f2937",
                linewidth=1.35,
            )
            legend_elements.append(
                Patch(
                    facecolor=colors[int(class_id)],
                    alpha=0.62,
                    edgecolor="#166534",
                    label=label_builder(plot_source[plot_source["class_id"] == class_id]),
                )
            )
        ax.legend(
            handles=legend_elements,
            loc="lower right",
            fontsize=7,
            framealpha=0.92,
            title=legend_title,
            title_fontsize=9,
        )
    else:
        ax.text(0.5, 0.5, "No soil data", transform=ax.transAxes, ha="center", va="center")

    boundary_target = field_wm if use_basemap else field_gdf
    boundary_target.plot(ax=ax, color="none", edgecolor="#0f7a20", linewidth=3.0)
    ax.set_title(title, fontsize=13)
    if not use_basemap:
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)



def _survey_label(ssurgo_gdf: gpd.GeoDataFrame) -> str:
    """Name the survey the polygons actually came from (SSURGO, Ontario
    Detailed Soil Survey, ...) instead of hard-coding SSURGO everywhere."""
    if ssurgo_gdf is not None and "soil_source" in getattr(ssurgo_gdf, "columns", []):
        vals = [v for v in ssurgo_gdf["soil_source"].dropna().unique() if isinstance(v, str)]
        if vals:
            v = vals[0]
            if v == "usda-sda":
                return "SSURGO"
            return " ".join(w.capitalize() for w in v.replace("_", " ").replace("-", " ").split())
    return "SSURGO"

def render_ssurgo_component_map(
    field_gdf: gpd.GeoDataFrame,
    ssurgo_gdf: gpd.GeoDataFrame,
    output_path: Path,
    field_id: str,
) -> None:
    plot_source = ssurgo_gdf.copy()
    if "mukey" in plot_source.columns:
        plot_source["mukey"] = plot_source["mukey"].astype(str)
        plot_source = plot_source.dissolve(by="mukey", as_index=False)
    if not plot_source.empty:
        plot_source["class_id"] = np.arange(len(plot_source))

    field_short = field_id or "Field"
    mukey_count = int(plot_source["mukey"].nunique()) if not plot_source.empty else 0

    def _label(part: gpd.GeoDataFrame) -> str:
        row = part.iloc[0]
        comp = row.get("compname", "Unknown")
        comp = comp if isinstance(comp, str) and comp else "Unknown"
        return f"{comp} (MUKEY {row['mukey']})"

    _render_map(
        field_gdf=field_gdf,
        plot_source=plot_source,
        output_path=output_path,
        title=f"Field {field_short} - {_survey_label(ssurgo_gdf)} Predominant Component\n({mukey_count} MUKEYs)",
        legend_title="Predominant component",
        label_builder=_label,
    )


def render_ssurgo_property_map(
    field_gdf: gpd.GeoDataFrame,
    ssurgo_gdf: gpd.GeoDataFrame,
    output_path: Path,
    field_id: str,
    property_col: str,
    property_label: str,
    property_units: str,
) -> bool:
    plot_source = ssurgo_gdf.copy()
    if "mukey" in plot_source.columns:
        plot_source["mukey"] = plot_source["mukey"].astype(str)
        plot_source = plot_source.dissolve(by="mukey", as_index=False)
    if property_col not in plot_source.columns:
        return False
    plot_source = plot_source.dropna(subset=[property_col]).copy()
    if plot_source.empty:
        return False
    class_ids, labels = _classify_quantiles(pd.Series(plot_source[property_col]), class_count=4)
    plot_source["class_id"] = class_ids
    field_short = field_id or "Field"
    mukey_count = int(plot_source["mukey"].nunique()) if "mukey" in plot_source.columns else 0

    def _label(part: gpd.GeoDataFrame) -> str:
        idx = int(part.iloc[0]["class_id"])
        mukeys = ", ".join(part["mukey"].astype(str).tolist()[:4])
        suffix = f" | MUKEY {mukeys}" if mukeys else ""
        return f"{property_label} {labels[idx]}{suffix}"

    legend_title = (
        f"{property_label} ({property_units}) Classes"
        if property_units
        else f"{property_label} Classes"
    )
    _render_map(
        field_gdf=field_gdf,
        plot_source=plot_source,
        output_path=output_path,
        title=f"Field {field_short} - SSURGO {property_label} (Quantiles)\n({mukey_count} MUKEYs)",
        legend_title=legend_title,
        label_builder=_label,
    )
    return True


def main() -> None:
    print("=" * 60)
    print("SSURGO Soil Map Generator")
    print("=" * 60)

    fields_path = farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)
    if not fields_path.exists():
        print(f"ERROR: Fields file not found: {fields_path}")
        sys.exit(1)

    fields = gpd.read_file(fields_path)
    field_slug_map = field_slug_map_from_inventory()
    print(f"Loaded {len(fields)} fields")

    for idx, field_row in enumerate(fields.itertuples(index=False), start=1):
        field_id = str(getattr(field_row, "field_id", f"field_{idx}"))
        field_slug = field_slug_map.get(field_id)
        if not field_slug:
            print(f"  skip {field_id} (no field slug)")
            continue
        field_short = field_id

        print(f"\nProcessing field: {field_short}")

        field_single = fields.iloc[[idx - 1]].copy()

        # Cached survey polygons (SSURGO or a national equivalent ingested in
        # the same schema, e.g. the Ontario Detailed Soil Survey) win over a
        # fresh query — this is what lets Canada render without SDA.
        cached = field_soil_polygon_path(_DEFAULT_GROWER, _DEFAULT_FARM, field_slug)
        if cached.exists():
            field_ssurgo = gpd.read_file(cached)
        else:
            field_ssurgo = get_ssurgo_polygons_with_soil_data(field_single, field_id)

        component_output = field_feature_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_component_map.png"
        )
        component_output.parent.mkdir(parents=True, exist_ok=True)
        render_ssurgo_component_map(
            field_single, field_ssurgo, component_output, field_id=field_short
        )
        print(f"  ✓ Component map saved: {component_output.name}")

        created = 0
        for prop, label, units, slug in PROPERTY_SPECS:
            output_path = field_feature_path(
                _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, f"soil_{slug}_map.png"
            )
            if render_ssurgo_property_map(
                field_single,
                field_ssurgo,
                output_path,
                field_id=field_short,
                property_col=prop,
                property_label=label,
                property_units=units,
            ):
                created += 1
        print(f"  ✓ Property maps saved: {created}")

    print("\n" + "=" * 60)
    print("SSURGO soil maps complete → canonical field feature paths")
    print("=" * 60)


if __name__ == "__main__":
    main()
