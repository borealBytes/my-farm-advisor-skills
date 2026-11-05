#!/usr/bin/env python3
"""Ontario Detailed Soil Survey provider for the My Farm Advisor data pipeline.

Source: AAFC / Government of Canada open data, "Ontario Detailed Soil Survey"
(dataset a75c3d6c-354d-436d-999d-431fb3a9de79, 1:20k-1:50k polygons linked to
component, criteria, parent-material, soil-name, and horizon tables).
Base URL pinned in RESOURCES; payload hashes pinned at the values observed
2026-11-02 (dataset metadata updated 2026-01-06, i.e. public before the
The 2026 external-data cutoff 2026-02-01).

Relational structure (join keys):
    on_dtl_50k (GPKG polygons, key POLY_ID)
      -> on_dtl_50k.csv (geometry attributes, POLY_ID)
      -> on_dtl_cmp  (mapunit components, POLY_ID; component % PERCENT,
                      SOIL_ID, slope, stoniness, PROFILE drained flag)
           -> on_dtl_crt (component criteria, CMP_ID: CLI class, drainage,
                         hydric, surface texture class)
      -> on_dtl_prt  (polygon parent/material, POLY_ID: MAPUNITNOM mapunit
                      name, SLC_V3R2 cross-reference key into Soil Landscapes
                      of Canada v3.2)
    on_dtl_slt (horizon layers, SOIL_ID: depth bounds, texture fractions,
                organic carbon, pH CaCl2/H2O, CEC, saturated hydraulic
                conductivity, water retention at 0/10/33/1500 kPa, bulk
                density, EC, lime)
    on_dtl_snt (soil series registry, SOIL_ID: name, Canadian soil order,
                drainage, parent material, rooting restrictions)

The output DataFrame mirrors the SSURGO sample schema consumed by
ingest/download_soil.py (field_id, mukey, compname, comppct_r, drainagecl,
hzdept_r, hzdepb_r, om_r, ph1to1h2o_r, awc_r, claytotal_r, sandtotal_r,
silttotal_r, dbthirdbar_r, cec7_r) plus Ontario-native extra columns and
soil_source / soil_flags provenance columns (derived values are flagged,
never silently filled — gNATSGO's tested/method-flag rule).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

SOURCE_NAME = "ontario_detailed_soil_survey"
SOURCE_URL_BASE = (
    "https://agriculture.canada.ca/atlas/data_donnees/detailedSoilSurvey/data_donnees"
)
DATASET_PAGE = "https://open.canada.ca/data/en/dataset/a75c3d6c-354d-436d-999d-431fb3a9de79"

# filename -> (relative URL path, sha256 observed 2026-11-02)
RESOURCES: dict[str, tuple[str, str]] = {
    "on_dtl_soil.gpkg": (
        "geoPackage/on_dtl_soil.gpkg",
        "af791c1daa043e2da5af7e9b712d55789816f8934d1c45e0278c373155e0b8a1",
    ),
    "on_dtl_50k.csv": (
        "csv/on_dtl_soil_sol/on_dtl_50k.csv",
        "f7d1f64d210668c5b7c6f12af646760dcca669ecda4c13faa4b89f05be23b71f",
    ),
    "on_dtl_cmp.csv": (
        "csv/on_dtl_soil_sol/on_dtl_cmp.csv",
        "45ce94492c46950af5f1a4aaad8b0da8cd8115622081109f0b9d1f02432d1fc5",
    ),
    "on_dtl_crt.csv": (
        "csv/on_dtl_soil_sol/on_dtl_crt.csv",
        "b5445b6305bf81fa04a1d1706483ef40abb2bead48c25c8aac0168c65fe99a09",
    ),
    "on_dtl_prt.csv": (
        "csv/on_dtl_soil_sol/on_dtl_prt.csv",
        "61fba5aaa56ff54d151bde59c1234c649924947c2b80fa79353f307bf5ab2096",
    ),
    "on_dtl_slt.csv": (
        "csv/on_dtl_soil_sol/on_dtl_slt.csv",
        "c5652b08ff0f845f88b1c0a1e4200fbdcbc6fe53f330dba155889b0d90169469",
    ),
    "on_dtl_snt.csv": (
        "csv/on_dtl_soil_sol/on_dtl_snt.csv",
        "7b0bd5e19439f20b8d561f742814075d68000aede43cb44ebbf14dccc5bb8b84",
    ),
}

SURVEY_GPKG_LAYER = "on_dtl_50k"  # CRS EPSG:4269 (NAD83 geographic degrees)

# Ontario legacy legend codes -> human-readable (raw codes always retained).
DRAINAGE_CLASSES = {
    "R": "rapid",
    "W": "well",
    "MW": "moderately well",
    "I": "imperfect",
    "P": "poorly",
    "VP": "very poorly",
}
# Only the USDA/Canada standard texture classes are decoded; anything else
# (ORG, GRAV, R, GL*, VA, ...) is kept raw and left undecoded.
TEXTURE_CLASSES = {
    "S": "sand",
    "LS": "loamy sand",
    "FS": "loamy fine sand",
    "LFS": "loamy fine sand",
    "VFSL": "very fine sandy loam",
    "FSL": "fine sandy loam",
    "SL": "sandy loam",
    "L": "loam",
    "SIL": "silt loam",
    "SICL": "silt clay loam",
    "SIC": "silty clay",
    "CL": "clay loam",
    "C": "clay",
}
# Organic-matter from organic-carbon conversion (Walkley-Black divisor).
OC_TO_OM = 1.724
SENTINELS = {-9, -99}

SENTINEL_NUMERIC = [
    "PERCENT", "SLOPE_P", "SLOPE_LEN", "UDEPTH", "LDEPTH", "COFRAG", "TSAND",
    "TSILT", "TCLAY", "ORGCARB", "PHCA", "PH2", "BASES", "CEC", "KSAT", "KP0",
    "KP10", "KP33", "KP1500", "BD", "EC", "CACO3",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_payload(cache_dir: Path, force: bool = False) -> Path:
    """Download (or reuse) the survey payload; verify pinned sha256.

    Writes metadata.json provenance record alongside the payload. Raises
    RuntimeError on checksum mismatch; set AG_SOIL_ONTARIO_ALLOW_CHECKSUM_SKIP=1
    to downgrade the mismatch to a warning (documented escape hatch).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for filename, (rel_path, expected_sha) in RESOURCES.items():
        target = cache_dir / filename
        url = f"{SOURCE_URL_BASE}/{rel_path}"
        status = "cached"
        if force or not target.exists():
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                tmp = target.with_suffix(target.suffix + ".part")
                with open(tmp, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        handle.write(chunk)
                tmp.replace(target)
            status = "downloaded"
        actual = _sha256(target)
        if actual != expected_sha:
            if (
                __import__("os").environ.get("AG_SOIL_ONTARIO_ALLOW_CHECKSUM_SKIP")
                == "1"
            ):
                print(f"  warn  sha256 drift for {filename} (upstream reissue?): {actual}")
            else:
                raise RuntimeError(
                    f"sha256 mismatch for {filename}: expected {expected_sha}, "
                    f"got {actual}. Re-pin RESOURCES after reviewing the dataset page, "
                    f"or set AG_SOIL_ONTARIO_ALLOW_CHECKSUM_SKIP=1."
                )
        records.append(
            {
                "file": filename,
                "url": url,
                "sha256": actual,
                "bytes": target.stat().st_size,
                "status": status,
            }
        )
    metadata = {
        "source": SOURCE_NAME,
        "dataset_page": DATASET_PAGE,
        "accessed_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "crs": "EPSG:4269 (NAD83 geographic)",
        "resources": records,
    }
    (cache_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    return cache_dir


# --------------------------------------------------------------------------
# Attribute-table loading (module-level cache per process)
# --------------------------------------------------------------------------

_ATTR_CACHE: dict[str, tuple[Path, dict[str, pd.DataFrame]]] = {}


def _load_tables(cache_dir: Path) -> dict[str, pd.DataFrame]:
    cache_dir = Path(cache_dir)
    key = "tables"
    if key in _ATTR_CACHE and _ATTR_CACHE[key][0] == cache_dir:
        return _ATTR_CACHE[key][1]
    ensure_payload(cache_dir)
    tables: dict[str, pd.DataFrame] = {}
    for name in ("cmp", "crt", "prt", "slt", "snt"):
        df = pd.read_csv(cache_dir / f"on_dtl_{name}.csv", low_memory=False)
        tables[name] = df
    # cmp joined with criteria (CMP_ID) and series registry (SOIL_ID).
    # Right-table duplicate descriptor columns are dropped so the crt drainage
    # / profile codes keep their names (series-level values are redundant with
    # component level; classification columns like ORDER2/MDEP1 are unique).
    cmp = tables["cmp"].merge(
        tables["crt"].drop(columns=["geodb_oid", "OBJECTID"]), on="CMP_ID", how="left"
    )
    cmp = cmp.merge(
        tables["snt"].drop(
            columns=["geodb_oid", "OBJECTID", "PROVINCE", "MODIFIER", "PROFILE", "DRAINAGE"]
        ),
        on="SOIL_ID",
        how="left",
    )
    for col in SENTINEL_NUMERIC:
        if col in cmp.columns:
            cmp[col] = pd.to_numeric(cmp[col], errors="coerce").where(
                lambda s: ~s.isin(SENTINELS)
            )
    cmp["drainage_decoded"] = cmp["DRAINAGE"].map(DRAINAGE_CLASSES)
    cmp["atexture_decoded"] = cmp["ATEXTURE"].map(TEXTURE_CLASSES)
    tables["cmp_joined"] = cmp.set_index("POLY_ID", drop=False)

    horizons = tables["slt"].copy()
    for col in SENTINEL_NUMERIC:
        if col in horizons.columns:
            horizons[col] = pd.to_numeric(horizons[col], errors="coerce").where(
                lambda s: ~s.isin(SENTINELS)
            )
    tables["horizons"] = horizons

    prts = tables["prt"].copy()
    tables["prt_joined"] = prts.set_index("POLY_ID", drop=False)
    _ATTR_CACHE[key] = (cache_dir, tables)
    return tables


def survey_polygons(cache_dir: Path) -> gpd.GeoDataFrame:
    """Survey polygon layer in EPSG:4326 (keyed by POLY_ID)."""
    cache_dir = Path(cache_dir)
    ensure_payload(cache_dir)
    polygons = gpd.read_file(
        cache_dir / "on_dtl_soil.gpkg", layer=SURVEY_GPKG_LAYER
    ).to_crs(epsg=4326)
    polygons["POLY_ID"] = polygons["POLY_ID"].astype(str)
    return polygons


def fields_with_survey_coverage(fields: gpd.GeoDataFrame, cache_dir: Path) -> list[str]:
    """Field ids whose geometry intersects at least one survey polygon."""
    polygons = survey_polygons(cache_dir)
    fields_4326 = fields.to_crs(epsg=4326)
    lhs = gpd.GeoDataFrame(
        {"field_id": fields_4326["field_id"].astype(str).tolist()},
        geometry=list(fields_4326.geometry),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(
        lhs,
        polygons[["POLY_ID", "geometry"]],
        predicate="intersects",
    )
    return sorted(joined["field_id"].unique().tolist())


# --------------------------------------------------------------------------
# Sample-schema production (SSURGO-compatible columns + Ontario extras)
# --------------------------------------------------------------------------

SAMPLE_COLUMNS = [
    "field_id", "mukey", "compname", "comppct_r", "drainagecl",
    "hzdept_r", "hzdepb_r", "om_r", "ph1to1h2o_r", "awc_r",
    "claytotal_r", "sandtotal_r", "silttotal_r", "dbthirdbar_r", "cec7_r",
]


def download_soil_ontario(
    fields: gpd.GeoDataFrame,
    cache_dir: Path,
    field_id_column: str = "field_id",
    max_depth_cm: int = 30,
) -> pd.DataFrame:
    """Build SSURGO-schema soil rows for fields covered by the Ontario survey.

    Returns rows keyed by (field_id, POLY_ID, CMP_ID, layer) with the canonical
    sample columns plus Ontario-native context columns and soil_source/
    soil_flags provenance. Fields with no survey polygons yield no rows.
    """
    polygons = survey_polygons(cache_dir)
    tables = _load_tables(cache_dir)
    cmp_joined = tables["cmp_joined"]
    horizons = tables["horizons"]
    prts = tables["prt_joined"]

    fields_4326 = fields.to_crs(epsg=4326)
    rows: list[dict[str, object]] = []
    for field in fields_4326.to_dict("records"):
        field_id = str(field[field_id_column])
        field_geom = gpd.GeoDataFrame([field], geometry="geometry").geometry.iloc[0]
        candidates = polygons.sindex.query(field_geom)
        if len(candidates) == 0:
            continue
        field_area_m2 = None  # metric area via planar approx on 4326 is unstable;
        # use the ratio of intersection to field area (unit-consistent, same CRS)
        for pos in candidates:
            poly = polygons.iloc[pos]
            inter = field_geom.intersection(poly.geometry)
            if inter.is_empty or inter.area <= 0:
                continue
            if field_area_m2 is None:
                field_area_m2 = field_geom.area
            area_frac = inter.area / field_area_m2
            poly_id = str(poly["POLY_ID"])
            components = cmp_joined[cmp_joined["POLY_ID"] == poly_id]
            mapunit_name, slc_key = "", ""
            if poly_id in prts.index:
                prow = prts.loc[poly_id]
                mapunit_name = str(prow.get("MAPUNITNOM", ""))
                slc_key = str(prow.get("SLC_V3R2", ""))
            for _, comp in components.iterrows():
                base_flags: list[str] = []
                compname = str(comp.get("SOILNAME") or comp.get("SOIL_ID") or "")
                drainagecl = comp.get("drainage_decoded")
                if not isinstance(drainagecl, str):
                    drainagecl = ""
                comp_pct = comp.get("PERCENT")
                weight_field_pct = (
                    round(float(comp_pct) * area_frac, 4)
                    if pd.notna(comp_pct)
                    else None
                )
                soil_id = str(comp.get("SOIL_ID", ""))
                layers = horizons[horizons["SOIL_ID"] == soil_id]
                layers = layers[layers["UDEPTH"] < max_depth_cm] if not layers.empty else layers
                common = {
                    "field_id": field_id,
                    "mukey": poly_id,
                    "compname": compname,
                    "comppct_r": comp_pct,
                    "drainagecl": drainagecl,
                    "soil_source": SOURCE_NAME,
                    # Ontario-native context (raw codes preserved)
                    "ont_soil_id": soil_id,
                    "ont_cmp_id": str(comp.get("CMP_ID", "")),
                    "ont_survey": str(comp.get("SURVEY", "")).strip(),
                    "mapunit_name": mapunit_name,
                    "slc_v3r2": slc_key,
                    "cli_class": str(comp.get("CLI", "")).strip(),
                    "cli_sub1": str(comp.get("CLI_1", "")).strip(),
                    "cli_sub2": str(comp.get("CLI_2", "")).strip(),
                    "drainage_code": str(comp.get("DRAINAGE", "")).strip(),
                    "artificially_drained": str(comp.get("PROFILE", "")).strip(),
                    "stoniness_code": str(comp.get("STONINESS", "")).strip(),
                    "slope_pct": comp.get("SLOPE_P"),
                    "atexture": str(comp.get("ATEXTURE", "")).strip(),
                    "atexture_decoded": comp.get("atexture_decoded") or "",
                    "soil_order_ca": str(comp.get("ORDER2", "")).strip(),
                    "parent_material_ca": str(comp.get("MDEP1", "")).strip(),
                    "polygon_area_frac_field": round(area_frac, 4),
                    "weight_field_pct": weight_field_pct,
                }
                if layers.empty:
                    rows.append({**common, "soil_flags": "no_horizon_layers_for_soil_id"})
                    continue
                for _, lay in layers.iterrows():
                    flags = list(base_flags)
                    om_r = None
                    orgcarbon = lay.get("ORGCARB")
                    if pd.notna(orgcarbon):
                        om_r = round(float(orgcarbon) * OC_TO_OM, 3)
                        flags.append("om_r=ORGCARB*1.724")
                    awc_r = None
                    kp33, kp1500 = lay.get("KP33"), lay.get("KP1500")
                    if pd.notna(kp33) and pd.notna(kp1500):
                        awc_r = round(max(0.0, (float(kp33) - float(kp1500)) / 100.0), 4)
                        flags.append("awc_r=(kPa33-kPa1500)/100")
                    rows.append(
                        {
                            **common,
                            "hzdept_r": lay.get("UDEPTH"),
                            "hzdepb_r": lay.get("LDEPTH"),
                            "om_r": om_r,
                            "ph1to1h2o_r": lay.get("PH2"),
                            "awc_r": awc_r,
                            "claytotal_r": lay.get("TCLAY"),
                            "sandtotal_r": lay.get("TSAND"),
                            "silttotal_r": lay.get("TSILT"),
                            "dbthirdbar_r": lay.get("BD"),
                            "cec7_r": lay.get("CEC"),
                            # raw extras
                            "org_carbon_pct": orgcarbon,
                            "ph_cacl2": lay.get("PHCA"),
                            "kpa_0": lay.get("KP0"),
                            "kpa_10": lay.get("KP10"),
                            "kpa_33": kp33,
                            "kpa_1500": kp1500,
                            "ksat_cm_hr": lay.get("KSAT"),
                            "co_fragments_pct": lay.get("COFRAG"),
                            "layer_no": lay.get("LAYER_NO"),
                            "hzn_master": str(lay.get("HZN_MAS", "")).strip(),
                            "hzn_suffix": str(lay.get("HZN_SUF", "")).strip(),
                            "soil_flags": ";".join(flags),
                        }
                    )
    if not rows:
        return pd.DataFrame(columns=SAMPLE_COLUMNS + ["soil_source", "soil_flags"])
    result = pd.DataFrame(rows)
    # dominant components first, top layers first (so groupby-first picks the
    # dominant soil the way the farm summary expects)
    result = result.sort_values(
        ["field_id", "weight_field_pct", "comppct_r", "hzdept_r"],
        ascending=[True, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    ordered = SAMPLE_COLUMNS[:5] + ["soil_source"] + SAMPLE_COLUMNS[5:] + ["soil_flags"]
    return result[ordered + [c for c in result.columns if c not in ordered]]


def field_polygon_intersections(
    fields: gpd.GeoDataFrame,
    cache_dir: Path,
    field_id_column: str = "field_id",
) -> gpd.GeoDataFrame:
    """Per-field survey-polygon intersections with component context attached.

    One row per (field, POLY_ID); geometry is the clipped polygon. Written by
    ingest/download_soil.py into the farm-level polygon cache and split to the
    per-field soil polygon cache consumed by reporting.
    """
    polygons = survey_polygons(cache_dir)
    tables = _load_tables(cache_dir)
    cmp_joined = tables["cmp_joined"]
    prts = tables["prt_joined"]
    fields_4326 = fields.to_crs(epsg=4326)
    out_rows: list[dict[str, object]] = []
    for _, field in fields_4326.iterrows():
        field_id = str(field[field_id_column])
        field_geom = field.geometry
        candidates = polygons.sindex.query(field_geom)
        if len(candidates) == 0:
            continue
        for pos in candidates:
            poly = polygons.iloc[pos]
            inter = field_geom.intersection(poly.geometry)
            if inter.is_empty or inter.area <= 0:
                continue
            poly_id = str(poly["POLY_ID"])
            dominant = ""
            if poly_id in cmp_joined["POLY_ID"].values:
                comps = cmp_joined[cmp_joined["POLY_ID"] == poly_id]
                comps = comps.sort_values("PERCENT", ascending=False)
                dominant = str(comps.iloc[0].get("SOILNAME") or comps.iloc[0].get("SOIL_ID") or "")
            mapunit_name = ""
            if poly_id in prts.index:
                mapunit_name = str(prts.loc[poly_id].get("MAPUNITNOM", ""))
            out_rows.append(
                {
                    "field_id": field_id,
                    "mukey": poly_id,
                    "compname": dominant,
                    "mapunit_name": mapunit_name,
                    "soil_source": SOURCE_NAME,
                    "polygon_area_frac_field": round(inter.area / field_geom.area, 4),
                    "geometry": inter,
                }
            )
    if not out_rows:
        return gpd.GeoDataFrame(columns=["field_id", "mukey", "geometry"], crs="EPSG:4326")
    return gpd.GeoDataFrame(out_rows, geometry="geometry", crs="EPSG:4326")
