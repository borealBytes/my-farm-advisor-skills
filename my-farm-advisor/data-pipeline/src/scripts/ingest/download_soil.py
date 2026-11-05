#!/usr/bin/env python3
# ruff: noqa: E402,I001
"""Download SSURGO soil data into canonical grower paths."""

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (  # pyright: ignore[reportMissingImports]
    farm_boundary_path,
    farm_manifest_dir,
    farm_soil_polygons_ontario_path,
    farm_soil_sample_path,
    farm_ssurgo_full_path,
    farm_ssurgo_restrictions_path,
    farm_ssurgo_summary_path,
    field_soil_full_path,
    field_soil_polygon_path,
    field_soil_restrictions_path,
    field_soil_summary_path,
    shared_soil_ontario_dir,
)
from reporting_bootstrap import (
    ensure_canonical_data_tree,
    ensure_skill_path,
    field_slug_map_from_inventory,
)

ensure_skill_path("ssurgo-soil")

from ssurgo_soil import download_soil  # pyright: ignore[reportMissingImports]
from ssurgo_workflows import query_mupolygons_for_field  # pyright: ignore[reportMissingImports]

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
ONTARIO_SOURCE_NAME = "ontario_detailed_soil_survey"


def _load_ontario_module():
    """Resolve the ontario-soil-survey skill module, or None when unavailable."""
    try:
        ensure_skill_path("ontario-soil-survey")
        import ontario_soil_survey as ontario_module

        return ontario_module
    except FileNotFoundError:
        print(
            "  warn  ontario-soil-survey skill not found; routing every field "
            "through SSURGO (Canadian fields will have no soil rows)"
        )
        return None


AUSTRALIA_PROPERTIES = ("CLAY", "SILT", "SAND", "CEC", "PHCALCIUMCHLORIDE", "CARBON", "BULKDENSITY")
AUSTRALIA_DEPTH = "0-5cm"


def _load_australia_module():
    """Resolve the australia-soil skill module, or None when unavailable."""
    try:
        ensure_skill_path("australia-soil")
        import australia_soil as australia_module  # pyright: ignore[reportMissingImports]

        return australia_module
    except FileNotFoundError:
        print(
            "  warn  australia-soil skill not found; AU fields will fall back "
            "to the SoilGrids grid step"
        )
        return None


def _australia_soil_rows(fields, *, field_slug_map, grower_slug, farm_slug):
    """Clip SLGA/ASF attributes + index ANSIS sites for AU fields (keyless DAP)."""
    au = _load_australia_module()
    if au is None:
        return pd.DataFrame()
    rows: list[dict] = []
    for _, row in fields.iterrows():
        field_id = str(row["field_id"])
        field_slug = field_slug_map.get(field_id, field_id)
        soil_dir = field_soil_summary_path(grower_slug, farm_slug, field_slug).parent
        # raster_rules: pad fetch bbox by >= one SLGA cell (coarsest grid is
        # 1 arc-second ~= 0.017 deg) so boundary cells are complete
        bbox = (row.geometry.bounds[0] - 0.017, row.geometry.bounds[1] - 0.017,
                row.geometry.bounds[2] + 0.017, row.geometry.bounds[3] + 0.017)
        for prop in AUSTRALIA_PROPERTIES:
            out_path = soil_dir / "slga_asf" / f"{prop.lower()}_{AUSTRALIA_DEPTH}.tif"
            try:
                prov = au.clip_field(bbox, out_path, prop=prop, depth=AUSTRALIA_DEPTH)
            except Exception as exc:
                print(f"  warn  SLGA/ASF clip failed for {field_slug} {prop}: {exc}")
                continue
            stat = (prov.get("stats") or [{}])[0]
            rows.append(
                {
                    "field_id": str(field_id),
                    "field_slug": field_slug,
                    "soil_source": prov["source"],
                    "property": prop,
                    "attribute": prov["attribute"],
                    "depth": prov["depth"],
                    "unit": prov["units"],
                    "source_kind": prov["source_kind"],
                    "mean": stat.get("mean"),
                    "min": stat.get("min"),
                    "max": stat.get("max"),
                    "n_pixels": stat.get("count"),
                    "doi": prov.get("doi"),
                    "url": prov["url"],
                    "accessed_at": prov["accessed_at"],
                }
            )
        try:
            sites = au.asris_profiles_near(
                bbox,
                radius_km=25.0,
                cache_dir=farm_manifest_dir(grower_slug, farm_slug) / "ansis_cache",
            )
            sites_out = soil_dir / "ansis_sites.geojson"
            sites_out.parent.mkdir(parents=True, exist_ok=True)
            sites.to_file(sites_out, driver="GeoJSON")
            print(
                f"  ANSIS site index: {len(sites)} profile sites within 25 km "
                f"of {field_slug} -> {sites_out.name}"
            )
        except Exception as exc:
            print(f"  warn  ANSIS site index failed for {field_slug}: {exc}")
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    farm_out = farm_manifest_dir(grower_slug, farm_slug) / "slga_asf_property_stats.csv"
    frame.to_csv(farm_out, index=False)
    for field_slug, group in frame.groupby("field_slug"):
        target = field_soil_summary_path(grower_slug, farm_slug, field_slug).parent
        target.mkdir(parents=True, exist_ok=True)
        group.to_csv(target / "slga_asf_property_stats.csv", index=False)
    print(f"  SLGA/ASF: {len(frame)} property rows for {frame['field_slug'].nunique()} fields -> {farm_out.name}")
    return frame


def _write_ontario_polygon_caches(
    polygons,
    *,
    field_slug_map: dict[str, str],
    grower_slug: str,
    farm_slug: str,
    force: bool,
) -> None:
    if polygons is None or polygons.empty:
        return
    for field_id, group in polygons.groupby("field_id"):
        field_slug = field_slug_map.get(str(field_id))
        if not field_slug:
            continue
        cache_path = field_soil_polygon_path(grower_slug, farm_slug, field_slug)
        if not force and _soil_polygon_cache_has_features(cache_path):
            continue
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        group.to_file(cache_path, driver="GeoJSON")


def _replay_ontario_polygon_caches(
    *,
    field_slug_map: dict[str, str],
    grower_slug: str,
    farm_slug: str,
    force: bool,
) -> None:
    cache = farm_soil_polygons_ontario_path(grower_slug, farm_slug)
    if not cache.exists():
        return
    try:
        polygons = gpd.read_file(cache)
    except Exception:
        return
    _write_ontario_polygon_caches(
        polygons,
        field_slug_map=field_slug_map,
        grower_slug=grower_slug,
        farm_slug=farm_slug,
        force=force,
    )


def _query_sda(sql: str, timeout: int = 120) -> list[list[object]]:
    response = requests.post(SDA_URL, data={"query": sql, "format": "JSON"}, timeout=timeout)
    response.raise_for_status()
    return response.json().get("Table", [])


def _fallback_field_soil(fields: gpd.GeoDataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    fields_wgs84 = fields.to_crs(epsg=4326)

    for _, field in fields_wgs84.iterrows():
        field_id = str(field["field_id"])
        field_wkt = field.geometry.wkt
        mukey_sql = f"""
        SELECT DISTINCT m.mukey
        FROM mupolygon m
        WHERE m.mupolygonkey IN (
            SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{field_wkt}')
        )
        """
        try:
            mukey_rows = _query_sda(mukey_sql, timeout=60)
        except Exception:
            mukey_rows = []
        mukeys = [str(row[0]) for row in mukey_rows if row and row[0] is not None]
        if not mukeys:
            continue

        attr_sql = f"""
        SELECT c.mukey, c.compname, c.comppct_r, c.drainagecl,
               ch.hzdept_r, ch.hzdepb_r, ch.om_r, ch.ph1to1h2o_r,
               ch.awc_r, ch.claytotal_r, ch.sandtotal_r, ch.silttotal_r,
               ch.dbthirdbar_r, ch.cec7_r
        FROM component c
        LEFT JOIN chorizon ch ON c.cokey = ch.cokey
        WHERE c.mukey IN ({", ".join(repr(m) for m in mukeys)})
          AND c.majcompflag = 'Yes'
          AND (ch.hzdept_r < 150 OR ch.hzdept_r IS NULL)
        ORDER BY c.mukey, c.comppct_r DESC, ch.hzdept_r ASC
        """
        try:
            attr_rows = _query_sda(attr_sql)
        except Exception:
            attr_rows = []

        for row in attr_rows:
            if len(row) < 14:
                continue
            rows.append(
                {
                    "field_id": field_id,
                    "mukey": str(row[0]),
                    "compname": row[1],
                    "comppct_r": row[2],
                    "drainagecl": row[3],
                    "hzdept_r": row[4],
                    "hzdepb_r": row[5],
                    "om_r": row[6],
                    "ph1to1h2o_r": row[7],
                    "awc_r": row[8],
                    "claytotal_r": row[9],
                    "sandtotal_r": row[10],
                    "silttotal_r": row[11],
                    "dbthirdbar_r": row[12],
                    "cec7_r": row[13],
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in [
        "comppct_r",
        "hzdept_r",
        "hzdepb_r",
        "om_r",
        "ph1to1h2o_r",
        "awc_r",
        "claytotal_r",
        "sandtotal_r",
        "silttotal_r",
        "dbthirdbar_r",
        "cec7_r",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _write_summary(soil_data: pd.DataFrame) -> None:
    if soil_data.empty:
        return
    raise RuntimeError("_write_summary requires an explicit output path")


def _soil_polygon_cache_has_features(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        polygons = gpd.read_file(path)
    except Exception:
        return False
    return not polygons.empty


def _write_field_polygon_caches(
    *,
    fields: gpd.GeoDataFrame,
    soil_data: pd.DataFrame,
    field_slug_map: dict[str, str],
    grower_slug: str,
    farm_slug: str,
    force: bool,
) -> None:
    if soil_data.empty or not field_slug_map:
        return

    fields_wgs84 = fields.to_crs(epsg=4326)
    soil_rows = soil_data.copy()
    if "mukey" not in soil_rows.columns:
        return
    # Ontario rows carry local POLY_IDs the SDA server cannot resolve; their
    # polygon caches are written straight from the Ontario provider payload.
    if "soil_source" in soil_rows.columns:
        soil_rows = soil_rows[soil_rows["soil_source"] != ONTARIO_SOURCE_NAME]
    soil_rows["mukey"] = soil_rows["mukey"].astype(str)

    for _, field in fields_wgs84.iterrows():
        field_id = str(field.get("field_id", "")).strip()
        field_slug = field_slug_map.get(field_id)
        if not field_slug:
            continue
        cache_path = field_soil_polygon_path(grower_slug, farm_slug, field_slug)
        if not force and _soil_polygon_cache_has_features(cache_path):
            continue
        mukeys = sorted(
            soil_rows.loc[soil_rows["field_id"].astype(str) == field_id, "mukey"].dropna().unique()
        )
        if not mukeys:
            continue
        polygons = query_mupolygons_for_field(field.geometry.wkt, mukeys)
        if polygons.empty:
            continue
        polygons["field_id"] = field_id
        field_boundary = gpd.GeoDataFrame(
            fields_wgs84[fields_wgs84["field_id"].astype(str) == field_id].copy(),
            geometry="geometry",
            crs=fields_wgs84.crs,
        )
        try:
            polygons = gpd.overlay(
                polygons,
                field_boundary,
                how="intersection",
            )
        except Exception:
            pass
        if polygons.empty:
            continue
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        polygons.to_file(cache_path, driver="GeoJSON")


def _enrich_ssurgo_horizons(df: "pd.DataFrame") -> "pd.DataFrame":
    """Add subsoil attributes SSURGO knows but the base fetch omits, published
    under the Ontario provider's column NAMES so one renderer serves both:
    ph_cacl2, ksat_cm_hr (SSURGO ksatb_r is mm/hr -> x0.1), base_sat_pct.
    """
    if df.empty or "mukey" not in df.columns:
        return df
    mukeys = sorted({str(m) for m in df["mukey"].dropna().unique()})
    if not mukeys:
        return df
    sql = f"""
    SELECT c.mukey, c.compname, ch.hzdept_r, ch.hzdepb_r,
           ch.phcacl2_r, ch.ksatb_r, ch.bysat
    FROM component c
    JOIN chorizon ch ON ch.cokey = c.cokey
    WHERE c.mukey IN ({", ".join(repr(m) for m in mukeys)})
    """
    try:
        rows = _query_sda(sql)
    except Exception:
        rows = []
    if not rows:
        for col in ("ph_cacl2", "ksat_cm_hr", "base_sat_pct"):
            df[col] = df.get(col, float("nan"))
        return df
    e = pd.DataFrame(rows, columns=["mukey", "compname", "hzdept_r", "hzdepb_r",
                                    "ph_cacl2", "ksat_mm_hr", "base_sat_pct"])
    e["mukey"] = e["mukey"].astype(str)
    e["ksat_cm_hr"] = pd.to_numeric(e.pop("ksat_mm_hr"), errors="coerce") * 0.1
    out = df.merge(e.drop(columns=["ksat_mm_hr"]),
                   on=["mukey", "compname", "hzdept_r", "hzdepb_r"], how="left")
    return out


def _write_restrictions(
    soil_data: pd.DataFrame,
    field_slug_map: dict,
    grower_slug: str,
    farm_slug: str,
) -> None:
    """Fetch SSURGO component restrictive features (corestrictions) for every
    mukey touched by this farm and write farm- + per-field CSVs. A restrictive
    layer (fragipan, claypan, bedrock, perched water table...) is exactly the
    kind of fact a depth profile must show, so it rides beside ssurgo_full.csv
    as ssurgo_restrictions.csv."""
    if soil_data is None or soil_data.empty or "mukey" not in soil_data.columns:
        return
    mukeys = sorted(soil_data.loc[soil_data["mukey"].notna(), "mukey"].astype(str).unique())
    if not mukeys:
        return
    sql = (
        "SELECT c.mukey, c.compname, s.reskind, s.resdept_r, s.resdepb_r, s.reshard "
        "FROM component c JOIN corestrictions s ON c.cokey = s.cokey "
        f"WHERE c.mukey IN ({', '.join(repr(m) for m in mukeys)}) "
        "ORDER BY c.mukey, s.resdept_r"
    )
    try:
        rows = _query_sda(sql, timeout=120)
    except Exception:
        rows = []
    cols = ["mukey", "compname", "reskind", "resdept_r", "resdepb_r", "reshard"]
    rdf = pd.DataFrame([r for r in rows if r and len(r) >= 6], columns=cols)
    if not rdf.empty:
        rdf["mukey"] = rdf["mukey"].astype(str)
        m2f = (soil_data.assign(mukey=soil_data["mukey"].astype(str))
                          [["field_id", "mukey"]].drop_duplicates())
        rdf = rdf.merge(m2f, on="mukey", how="inner")
        rdf["field_slug"] = rdf["field_id"].map(
            {str(k): v for k, v in field_slug_map.items()})
        rdf = rdf[rdf["field_slug"].notna()]
    else:
        for extra in ("field_id", "field_slug"):
            rdf[extra] = pd.Series(dtype=object)
    farm_path = farm_ssurgo_restrictions_path(grower_slug, farm_slug)
    farm_path.parent.mkdir(parents=True, exist_ok=True)
    rdf.drop(columns=["field_id"], errors="ignore").to_csv(farm_path, index=False)
    # every US field gets a (possibly empty) sidecar so the report can state
    # "no restrictive features recorded", not just go silent
    for slug in field_slug_map.values():
        target = field_soil_restrictions_path(grower_slug, farm_slug, str(slug))
        target.parent.mkdir(parents=True, exist_ok=True)
        sub = rdf[rdf["field_slug"] == str(slug)] if not rdf.empty else rdf
        sub.drop(columns=["field_id", "field_slug"], errors="ignore").to_csv(target, index=False)
    print(f"  restrictive features: {len(rdf)} rows -> {farm_path.name} (+ per-field)")


def main():
    print("=" * 60)
    print("Step 2: Download SSURGO Soil Data")
    print("=" * 60)

    grower_slug = os.environ.get("AG_GROWER_SLUG", "default-grower")
    farm_slug = os.environ.get("AG_FARM_SLUG", "default-farm")
    default_inventory = farm_manifest_dir(grower_slug, farm_slug) / "field-inventory.csv"
    inventory_path = Path(os.environ.get("AG_INVENTORY_CSV", str(default_inventory)))
    ensure_canonical_data_tree(
        grower_slug=grower_slug, farm_slug=farm_slug, inventory_path=inventory_path
    )
    field_slug_map = field_slug_map_from_inventory(
        inventory_path if inventory_path.exists() else None
    )

    boundaries_path = farm_boundary_path(grower_slug, farm_slug)
    fields = gpd.read_file(boundaries_path)
    print(f"Loaded {len(fields)} fields")

    farm_full_output = farm_ssurgo_full_path(grower_slug, farm_slug)
    farm_summary_output = farm_ssurgo_summary_path(grower_slug, farm_slug)
    farm_sample_output = farm_soil_sample_path(grower_slug, farm_slug)
    farm_sample_output.parent.mkdir(parents=True, exist_ok=True)
    force = os.environ.get("AG_FORCE") == "1"

    if (
        farm_full_output.exists()
        and farm_summary_output.exists()
        and farm_sample_output.exists()
        and not force
    ):
        soil_data = pd.read_csv(farm_sample_output)
        grouped = pd.read_csv(farm_summary_output)
        expected_field_ids = set(fields["field_id"].astype(str).tolist())
        cached_field_ids = (
            set(soil_data["field_id"].astype(str).tolist())
            if "field_id" in soil_data.columns
            else set()
        )
        missing_field_ids = sorted(expected_field_ids - cached_field_ids)
        if missing_field_ids:
            print(
                "  Cached SSURGO rows are missing field IDs; refreshing soil tables for: "
                + ", ".join(missing_field_ids)
            )
        else:
            if field_slug_map:
                for field_id, field_slug in field_slug_map.items():
                    field_rows = soil_data[
                        soil_data["field_id"].astype(str) == str(field_id)
                    ].copy()
                    if not field_rows.empty:
                        full_target = field_soil_full_path(grower_slug, farm_slug, field_slug)
                        full_target.parent.mkdir(parents=True, exist_ok=True)
                        field_rows.to_csv(full_target, index=False)
                    summary_rows = grouped[grouped["field_id"].astype(str) == str(field_id)].copy()
                    if not summary_rows.empty:
                        summary_target = field_soil_summary_path(grower_slug, farm_slug, field_slug)
                        summary_target.parent.mkdir(parents=True, exist_ok=True)
                        summary_rows.to_csv(summary_target, index=False)
                _write_field_polygon_caches(
                    fields=fields,
                    soil_data=soil_data,
                    field_slug_map=field_slug_map,
                    grower_slug=grower_slug,
                    farm_slug=farm_slug,
                    force=False,
                )
                _write_restrictions(soil_data, field_slug_map, grower_slug, farm_slug)
                _replay_ontario_polygon_caches(
                    field_slug_map=field_slug_map,
                    grower_slug=grower_slug,
                    farm_slug=farm_slug,
                    force=False,
                )
            print(f"skip  SSURGO API fetch (cached): {farm_sample_output}")
            return soil_data

    # Country-aware routing: Ontario survey fields use the ON provider,
    # Australian fields use SLGA/ASF (+ANSIS site index), everything else
    # SSURGO/SDA. Grid floor (SoilGrids 250 m) is a separate step:
    # ingest/download_soilgrids.py. See soil/soil-routing.md.
    ontario_module = _load_ontario_module()
    ontario_field_ids: set[str] = set()
    if ontario_module is not None:
        try:
            ontario_field_ids = set(
                ontario_module.fields_with_survey_coverage(fields, shared_soil_ontario_dir())
            )
        except Exception as exc:
            print(f"  warn  Ontario survey coverage check failed ({exc}); SSURGO-only routing")
    on_mask = fields["field_id"].astype(str).isin(ontario_field_ids)
    if "country" in fields.columns:
        country = fields["country"].fillna("US").astype(str).str.upper()
    else:
        country = pd.Series(["US"] * len(fields), index=fields.index)
    au_mask = country.eq("AU") & ~on_mask
    ontario_fields = fields[on_mask].copy()
    us_fields = fields[~on_mask & ~au_mask].copy()
    au_fields = fields[au_mask].copy()
    if not ontario_fields.empty:
        print(
            f"  routing {len(ontario_fields)} field(s) inside Ontario survey "
            "coverage to the Ontario Detailed Soil Survey"
        )
    if not au_fields.empty:
        print(
            f"  routing {len(au_fields)} field(s) in Australia to SLGA/ASF "
            "(CSIRO DAP keyless mirror) + ANSIS site index"
        )
        _australia_soil_rows(
            au_fields,
            field_slug_map=field_slug_map,
            grower_slug=grower_slug,
            farm_slug=farm_slug,
        )

    soil_data = download_soil(
        us_fields if not us_fields.empty else fields,
        field_id_column="field_id",
        # 150 cm, not 30: horizon tables and depth-interpolated profiles need
        # the subsoil — and restrictive layers — to say anything true
        max_depth_cm=150,
        output_path=str(farm_sample_output),
    ) if not us_fields.empty else pd.DataFrame()

    if soil_data.empty and not us_fields.empty:
        print("  Primary SSURGO download returned no rows; querying SDA fallback summaries...")
        soil_data = _fallback_field_soil(us_fields)
        if not soil_data.empty:
            soil_data.to_csv(farm_full_output, index=False)
            soil_data.to_csv(farm_sample_output, index=False)

    if not soil_data.empty and "soil_source" not in soil_data.columns:
        soil_data["soil_source"] = "ssurgo"
    if not soil_data.empty:
        soil_data = _enrich_ssurgo_horizons(soil_data)

    ontario_polygons = None
    if not ontario_fields.empty and ontario_module is not None:
        try:
            ontario_rows = ontario_module.download_soil_ontario(
                ontario_fields, shared_soil_ontario_dir(), max_depth_cm=150
            )
        except Exception as exc:
            print(f"  warn  Ontario soil provider failed: {exc}")
            ontario_rows = pd.DataFrame()
        if not ontario_rows.empty:
            print(
                f"  Ontario survey: {len(ontario_rows)} soil records for "
                f"{ontario_rows['field_id'].nunique()} fields"
            )
        try:
            ontario_polygons = ontario_module.field_polygon_intersections(
                ontario_fields, shared_soil_ontario_dir()
            )
        except Exception as exc:
            print(f"  warn  Ontario polygon intersections failed: {exc}")
        frames = [f for f in (soil_data, ontario_rows) if f is not None and not f.empty]
        if frames:
            soil_data = pd.concat(frames, ignore_index=True)

    if not soil_data.empty:
        soil_data.to_csv(farm_full_output, index=False)
        soil_data.to_csv(farm_sample_output, index=False)
        grouped = (
            soil_data.groupby("field_id", as_index=False)
            .agg(
                n_mukeys=("mukey", "nunique"),
                n_components=("compname", "nunique"),
                n_horizons=("mukey", "count"),
                avg_om_pct=("om_r", "mean"),
                avg_ph=("ph1to1h2o_r", "mean"),
                total_aws_inches=("awc_r", "sum"),
                avg_cec=("cec7_r", "mean"),
                avg_clay_pct=("claytotal_r", "mean"),
                avg_sand_pct=("sandtotal_r", "mean"),
                dominant_soil=("compname", "first"),
                drainage_class=("drainagecl", "first"),
                soil_source=("soil_source", "first"),
            )
            .assign(ph_constraint="none", erosion_risk="moderate")
        )
        grouped.to_csv(farm_summary_output, index=False)

        if field_slug_map:
            for field_id, field_slug in field_slug_map.items():
                field_rows = soil_data[soil_data["field_id"].astype(str) == str(field_id)].copy()
                if not field_rows.empty:
                    full_target = field_soil_full_path(grower_slug, farm_slug, field_slug)
                    full_target.parent.mkdir(parents=True, exist_ok=True)
                    field_rows.to_csv(full_target, index=False)
                summary_rows = grouped[grouped["field_id"].astype(str) == str(field_id)].copy()
                if not summary_rows.empty:
                    summary_target = field_soil_summary_path(grower_slug, farm_slug, field_slug)
                    summary_target.parent.mkdir(parents=True, exist_ok=True)
                    summary_rows.to_csv(summary_target, index=False)

            _write_field_polygon_caches(
                fields=fields,
                soil_data=soil_data,
                field_slug_map=field_slug_map,
                grower_slug=grower_slug,
                farm_slug=farm_slug,
                force=force,
            )
            _write_restrictions(soil_data, field_slug_map, grower_slug, farm_slug)
            if ontario_polygons is not None and not ontario_polygons.empty:
                farm_polygon_cache = farm_soil_polygons_ontario_path(grower_slug, farm_slug)
                farm_polygon_cache.parent.mkdir(parents=True, exist_ok=True)
                ontario_polygons.to_file(farm_polygon_cache, driver="GPKG", layer="soil_polygons")
                _write_ontario_polygon_caches(
                    ontario_polygons,
                    field_slug_map=field_slug_map,
                    grower_slug=grower_slug,
                    farm_slug=farm_slug,
                    force=force,
                )

    print(
        f"\n✓ Downloaded {len(soil_data)} soil records for "
        f"{soil_data['field_id'].nunique() if len(soil_data) else 0} fields"
    )
    print(f"  Output: {farm_sample_output}")

    return soil_data


if __name__ == "__main__":
    main()
