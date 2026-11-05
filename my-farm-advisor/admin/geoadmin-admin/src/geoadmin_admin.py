from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import geopandas as gpd
import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_SCRIPTS_ROOT = REPO_ROOT / "data" / "scripts"
if str(DATA_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS_ROOT))

GEOADMIN_LEVELS = ("l0_countries", "l1_states", "l2_counties")

# Canada's "state/county" analogs. GADM 4.1 CAN ADM1 = provinces/territories
# (matches StatCan exactly), ADM2 = census divisions (the county-role unit used
# for weather/maturity aggregation; 53 in Ontario including Waterloo).
# Downloaded 2026-11-02 and verified: 293 national ADM2 features.
# License: GADM Terms of Use (free for use; redistribution restricted — cite
# GADM, do not rehost). Determinism comes from the pinned URL + re-download
# checksum journal in metadata.json.
GADM_CAN_SHP_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_CAN_shp.zip"
GADM_CAN_ARCHIVE = "gadm41_CAN_shp.zip"
GADM_SHP_URL_TEMPLATE = "https://geodata.ucdavis.edu/gadm/gadm4.1/shp/gadm41_{iso3}_shp.zip"


def gadm_country_sources(iso3: str) -> dict:
    """Standardized L1/L2 sources for ANY country from the GADM 4.1 archive.

    Canada (the first implementation) keeps its canonical slugs and its
    StatCan PRUID enrichment. Every other ISO3 gets its own per-country level
    roots (l1_states_<iso>, l2_counties_<iso>) and deterministic synthetic
    codes ISO3+index in the FIPS slots, with raw GID_1/GID_2 preserved for
    cross-reference. GADM Terms of Use: free to use, cite GADM, no
    redistribution of the boundaries themselves.
    """
    iso3 = iso3.strip().upper()
    if len(iso3) != 3 or not iso3.isalpha():
        raise ValueError(f"--gadm-iso wants ISO3 codes, got {iso3!r}")
    iso = iso3.lower()
    suffix = "" if iso3 == "CAN" else f"_{iso}"
    url = GADM_SHP_URL_TEMPLATE.format(iso3=iso3)
    archive = f"gadm41_{iso3}_shp.zip"
    return {
        f"l1_states{suffix or '_canada'}": GeoadminSource(
            level_slug=f"l1_states{suffix}" if iso3 != "CAN" else "l1_states",
            source_name="gadm",
            source_url=url,
            archive_name=archive,
            output_geojson=f"states{'_canada' if iso3 == 'CAN' else '_' + iso}.geojson",
            output_parquet=f"states{'_canada' if iso3 == 'CAN' else '_' + iso}.parquet",
            vintage="gadm-4.1",
        ),
        f"l2_counties{suffix or '_canada'}": GeoadminSource(
            level_slug=f"l2_counties{suffix}" if iso3 != "CAN" else "l2_counties",
            source_name="gadm",
            source_url=url,
            archive_name=archive,
            output_geojson=f"counties{'_canada' if iso3 == 'CAN' else '_' + iso}.geojson",
            output_parquet=f"counties{'_canada' if iso3 == 'CAN' else '_' + iso}.parquet",
            vintage="gadm-4.1",
        ),
    }
# Water overlay cutoff: keep lakes/reservoirs at or above this area so the
# layer stays tiny while every lake a continental map can see survives.
MIN_LAKE_KM2 = 150.0

# Statistics Canada PRUID (province/territory FIPS-equivalent) by name.
CAN_PRUID_BY_NAME = {
    "Alberta": "48",
    "British Columbia": "59",
    "Manitoba": "46",
    "New Brunswick": "13",
    "Newfoundland and Labrador": "10",
    "Northwest Territories": "61",
    "Nova Scotia": "12",
    "Nunavut": "62",
    "Ontario": "35",
    "Prince Edward Island": "11",
    "Québec": "24",
    "Quebec": "24",
    "Saskatchewan": "47",
    "Yukon": "60",
}
CAN_ABBR_BY_PRUID = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT",
    "62": "NU",
}


def _shared_root() -> Path:
    runtime_base = _runtime_base()
    if runtime_base is not None:
        return runtime_base / "shared"
    return REPO_ROOT / "data" / "shared"


def _geoadmin_root() -> Path:
    return _shared_root() / "geoadmin"


def _geoadmin_level_root(level_slug: str) -> Path:
    return _geoadmin_root() / level_slug


def _runtime_base() -> Path | None:
    raw_data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not raw_data_root:
        return None
    data_root = Path(raw_data_root).expanduser()
    if not data_root.is_absolute():
        raise ValueError(f"DATA_PIPELINE_DATA_ROOT must be absolute, got: {raw_data_root}")
    return data_root.resolve(strict=False) / "data-pipeline"


def _repo_relative(path: Path) -> str:
    resolved = path.resolve(strict=False)
    for root in (_runtime_base(), REPO_ROOT):
        if root is None:
            continue
        try:
            return str(resolved.relative_to(root.resolve(strict=False)))
        except ValueError:
            continue
    return str(resolved)


@dataclass(frozen=True, slots=True)
class GeoadminSource:
    level_slug: str
    source_name: str
    source_url: str
    archive_name: str
    output_geojson: str
    output_parquet: str
    vintage: str


def geoadmin_level_roots() -> dict[str, Path]:
    roots = {
        "l0_countries": _geoadmin_level_root("l0_countries"),
        "l1_states": _geoadmin_level_root("l1_states"),
        "l2_counties": _geoadmin_level_root("l2_counties"),
        "lakes": _geoadmin_level_root("lakes"),
    }
    base = _geoadmin_root()
    if base.exists():
        for extra in sorted(base.iterdir()):
            if extra.is_dir() and (extra.name.startswith("l1_states_") or extra.name.startswith("l2_counties_")):
                roots[extra.name] = extra
    return roots


def build_source_catalog(census_year: int) -> dict[str, GeoadminSource]:
    return {
        "l0_countries": GeoadminSource(
            level_slug="l0_countries",
            source_name="natural-earth",
            source_url="https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
            archive_name="ne_10m_admin_0_countries.zip",
            output_geojson="countries.geojson",
            output_parquet="countries.parquet",
            vintage="natural-earth-10m",
        ),
        "l1_states": GeoadminSource(
            level_slug="l1_states",
            source_name="census-tiger-line",
            source_url=f"https://www2.census.gov/geo/tiger/TIGER{census_year}/STATE/tl_{census_year}_us_state.zip",
            archive_name=f"tl_{census_year}_us_state.zip",
            output_geojson="states_usa.geojson",
            output_parquet="states_usa.parquet",
            vintage=str(census_year),
        ),
        "l2_counties": GeoadminSource(
            level_slug="l2_counties",
            source_name="census-tiger-line",
            source_url=f"https://www2.census.gov/geo/tiger/TIGER{census_year}/COUNTY/tl_{census_year}_us_county.zip",
            archive_name=f"tl_{census_year}_us_county.zip",
            output_geojson="counties_usa.geojson",
            output_parquet="counties_usa.parquet",
            vintage=str(census_year),
        ),
        # Canada mirrors l1/l2 roles: provinces as "states", census
        # divisions as "counties" (GADM 4.1 built from StatCan boundaries).
        "l1_states_canada": GeoadminSource(
            level_slug="l1_states",
            source_name="gadm",
            source_url=GADM_CAN_SHP_URL,
            archive_name=GADM_CAN_ARCHIVE,
            output_geojson="states_canada.geojson",
            output_parquet="states_canada.parquet",
            vintage="gadm-4.1",
        ),
        "l2_counties_canada": GeoadminSource(
            level_slug="l2_counties",
            source_name="gadm",
            source_url=GADM_CAN_SHP_URL,
            archive_name=GADM_CAN_ARCHIVE,
            output_geojson="counties_canada.geojson",
            output_parquet="counties_canada.parquet",
            vintage="gadm-4.1",
        ),
        # Base-map context: administrative polygons are LAND-only, so
        # cartography must overlay water or lakes read as missing data.
        "lakes": GeoadminSource(
            level_slug="lakes",
            source_name="natural-earth",
            source_url="https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
            archive_name="ne_10m_lakes.zip",
            output_geojson="lakes.geojson",
            output_parquet="lakes.parquet",
            vintage="natural-earth-10m",
        ),
    }


def download_source_archive(source: GeoadminSource, *, force: bool = False) -> Path:
    target = _geoadmin_level_root(source.level_slug) / "raw" / source.archive_name
    if target.exists() and not force:
        return target
    # The Canada zip feeds both the l1 and l2 levels; reuse the copy fetched
    # for the sibling level instead of pulling 138 MB twice (real copy — no
    # symlinks in project data).
    base = source.level_slug.split("_states_")[0] if "_states_" in source.level_slug else None
    iso = source.level_slug.split("_")[-1] if source.level_slug.split("_")[-1] not in ("states", "counties") else None
    siblings = ["l1_states", "l2_counties"]
    if iso and iso != "usa":
        siblings += [f"l1_states_{iso}", f"l2_counties_{iso}"]
    for sibling in siblings:
        sibling_target = _geoadmin_level_root(sibling) / "raw" / source.archive_name
        if sibling_target != target and sibling_target.exists() and not force:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sibling_target, target)
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(source.source_url, timeout=180)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def _keep_columns(frame: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    keep = [column for column in columns if column in frame.columns]
    keep.append("geometry")
    filtered = gpd.GeoDataFrame(frame.loc[:, keep].copy(), geometry="geometry", crs=frame.crs)
    return cast(gpd.GeoDataFrame, filtered)


def standardize_geoadmin_layer(source: GeoadminSource, archive_path: Path) -> gpd.GeoDataFrame:
    if source.output_geojson in ("states_canada.geojson", "counties_canada.geojson"):
        return _standardize_canada_layer(source, archive_path)
    if source.source_name == "gadm":
        return _standardize_gadm_layer(source, archive_path)
    if source.level_slug == "lakes":
        return _standardize_lakes_layer(source, archive_path)
    frame = gpd.read_file(archive_path)
    frame = frame.to_crs("EPSG:4326")
    if source.level_slug == "l0_countries":
        frame = _keep_columns(frame, ["ADM0_A3", "ISO_A3", "NAME", "CONTINENT", "REGION_UN"])
        frame = gpd.GeoDataFrame(
            frame.rename(
                columns={
                    "ADM0_A3": "adm0_a3",
                    "ISO_A3": "iso_a3",
                    "NAME": "name",
                    "CONTINENT": "continent",
                    "REGION_UN": "region_un",
                }
            ),
            geometry="geometry",
            crs="EPSG:4326",
        )
    elif source.level_slug == "l1_states":
        frame = _keep_columns(frame, ["STATEFP", "STUSPS", "NAME", "REGION", "DIVISION"])
        frame = gpd.GeoDataFrame(
            frame.rename(
                columns={
                    "STATEFP": "state_fips",
                    "STUSPS": "state_code",
                    "NAME": "state_name",
                    "REGION": "region_code",
                    "DIVISION": "division_code",
                }
            ),
            geometry="geometry",
            crs="EPSG:4326",
        )
    else:
        frame = _keep_columns(frame, ["GEOID", "STATEFP", "COUNTYFP", "NAME", "NAMELSAD"])
        frame = gpd.GeoDataFrame(
            frame.rename(
                columns={
                    "GEOID": "fips",
                    "STATEFP": "state_fips",
                    "COUNTYFP": "county_fips",
                    "NAME": "county_name",
                    "NAMELSAD": "county_name_full",
                }
            ),
            geometry="geometry",
            crs="EPSG:4326",
        )
    frame["source_name"] = source.source_name
    frame["source_vintage"] = source.vintage
    return cast(gpd.GeoDataFrame, frame)


def _standardize_lakes_layer(source: GeoadminSource, archive_path: Path) -> gpd.GeoDataFrame:
    """Natural Earth 10m lakes -> compact water overlay for base maps.

    Administrative polygons are land-only; every map drawn from them needs a
    water overlay or the Great Lakes read as missing data. Keep named open
    water >= MIN_LAKE_KM2 (equal-area computed); reservoirs included.
    """
    frame = gpd.read_file(archive_path).to_crs("EPSG:4326")
    area_km2 = frame.to_crs("EPSG:6933").area / 1_000_000.0
    keep = area_km2 >= MIN_LAKE_KM2
    out = gpd.GeoDataFrame(
        {
            "name": frame.loc[keep, "name"],
            "feature_class": frame.loc[keep, "featurecla"],
            "wikidata_id": frame.loc[keep, "wikidataid"],
            "area_km2": area_km2[keep].round(1),
            "geometry": frame.loc[keep, "geometry"],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )
    out["source_name"] = source.source_name
    out["source_vintage"] = source.vintage
    return cast(gpd.GeoDataFrame, out)


def _canada_pruid(name: object) -> str | float:
    """Map GADM province names to StatCan PRUID, tolerant of DBF mojibake.

    GADM .dbf files disagree on encoding ("Québec" can arrive as UTF-8 bytes
    decoded as latin-1 -> 'QuÃ©bec'); repair before mapping so builds are
    deterministic regardless of fiona/GDAL versions.
    """
    text = str(name)
    for candidate in (text, text.strip(), text.encode("latin-1", "ignore").decode("utf-8", "ignore")):
        if candidate in CAN_PRUID_BY_NAME:
            return CAN_PRUID_BY_NAME[candidate]
    return float("nan")


def _standardize_gadm_layer(source: GeoadminSource, archive_path: Path) -> gpd.GeoDataFrame:
    """GADM 4.1 for any ISO3 -> the same standardized schemas as TIGER/StatCan."""
    iso3 = source.archive_name.split("_")[1]
    layer = "1" if source.level_slug.startswith("l1") else "2"
    frame = gpd.read_file(archive_path, layer=f"gadm41_{iso3}_{layer}")
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    frame = frame.to_crs("EPSG:4326")
    if layer == "1":
        names = sorted(frame["NAME_1"].astype(str).unique())
        code = {n: f"{iso3}{i:03d}" for i, n in enumerate(names, start=1)}
        out = gpd.GeoDataFrame(
            {
                "state_fips": frame["NAME_1"].map(code),
                "state_code": "",
                "state_name": frame["NAME_1"],
                "region_code": "",
                "division_code": "",
                "gadm_gid_1": frame["GID_1"],
                "country": iso3,
            },
            geometry=frame.geometry,
            crs="EPSG:4326",
        )
    else:
        parents = sorted(frame["NAME_1"].astype(str).unique())
        pcode = {n: f"{iso3}{i:03d}" for i, n in enumerate(parents, start=1)}
        frame = frame.sort_values(["NAME_1", "NAME_2"])
        child = frame.groupby("NAME_1").cumcount() + 1
        ccode = frame["NAME_1"].map(pcode) + child.astype(str).str.zfill(3)
        out = gpd.GeoDataFrame(
            {
                "fips": ccode,
                "state_fips": frame["NAME_1"].map(pcode),
                "county_fips": child.astype(str).str.zfill(3),
                "county_name": frame["NAME_2"],
                "county_name_full": frame["NAME_2"].astype(str) + " (" + frame["TYPE_2"].fillna("Division").astype(str) + ")",
                "gadm_gid_2": frame["GID_2"],
                "country": iso3,
            },
            geometry=frame.geometry,
            crs="EPSG:4326",
        )
    out["source_name"] = source.source_name
    out["source_vintage"] = source.vintage
    return cast(gpd.GeoDataFrame, out)


def _standardize_canada_layer(source: GeoadminSource, archive_path: Path) -> gpd.GeoDataFrame:
    """GADM 4.1 Canada -> the same standardized schemas as TIGER l1/l2.

    FIPS-slot codes: ``state_fips = "CA"+PRUID`` (StatCan province code),
    ``county_fips`` = the census-division index inside GADM's GID_2 zero-padded
    to 3 digits (stable for the pinned archive; raw ``gadm_gid_2`` is kept in
    every row for cross-reference).
    """
    layer = "gadm41_CAN_1" if source.output_geojson == "states_canada.geojson" else "gadm41_CAN_2"
    frame = gpd.read_file(archive_path, layer=layer)
    if frame.crs is None:
        # GADM ships WGS84 (.prj can be invisible through /vsizip); assert it.
        frame = frame.set_crs("EPSG:4326")
    frame = frame.to_crs("EPSG:4326")
    if layer == "gadm41_CAN_1":
        pruid = frame["NAME_1"].map(_canada_pruid)
        if pruid.isna().any():
            unmapped = sorted(frame.loc[pruid.isna(), "NAME_1"].unique())
            raise ValueError(f"GADM province names missing PRUID mapping: {unmapped}")
        state_fips = "CA" + pruid
        out = gpd.GeoDataFrame(
            {
                "state_fips": state_fips,
                "state_code": pruid.map(CAN_ABBR_BY_PRUID),
                "state_name": frame["NAME_1"],
                "region_code": "",
                "division_code": "",
                "gadm_gid_1": frame["GID_1"],
                "country": "CA",
            },
            geometry=frame.geometry,
            crs="EPSG:4326",
        )
    else:
        pruid = frame["NAME_1"].map(_canada_pruid)
        if pruid.isna().any():
            unmapped = sorted(frame.loc[pruid.isna(), "NAME_1"].unique())
            raise ValueError(f"GADM province names missing PRUID mapping: {unmapped}")
        cd_index = (
            frame["GID_2"].astype(str).str.split(".").str[2].str.split("_").str[0]
        )
        if cd_index.isna().any() or not cd_index.str.isdigit().all():
            raise ValueError("Unexpected GADM GID_2 format; cannot derive census-division codes")
        out = gpd.GeoDataFrame(
            {
                "fips": ("CA" + pruid + cd_index.str.zfill(3)),
                "state_fips": "CA" + pruid,
                "county_fips": cd_index.str.zfill(3),
                "county_name": frame["NAME_2"],
                "county_name_full": frame["NAME_2"].astype(str)
                + " ("
                + frame["TYPE_2"].fillna("Census Division").astype(str)
                + ")",
                "gadm_gid_2": frame["GID_2"],
                "country": "CA",
            },
            geometry=frame.geometry,
            crs="EPSG:4326",
        )
    out["source_name"] = source.source_name
    out["source_vintage"] = source.vintage
    return cast(gpd.GeoDataFrame, out)


def _county_lookup(frame: gpd.GeoDataFrame) -> pd.DataFrame:
    projected = frame.to_crs("EPSG:5070")
    centroids = gpd.GeoSeries(projected.geometry.centroid, crs="EPSG:5070").to_crs("EPSG:4326")
    return pd.DataFrame(
        {
            "fips": frame["fips"],
            "state_fips": frame["state_fips"],
            "county_fips": frame["county_fips"],
            "county_name": frame["county_name"],
            "county_name_full": frame["county_name_full"],
            "centroid_lon": centroids.x,
            "centroid_lat": centroids.y,
        }
    )


def assign_fields_to_counties(
    fields: gpd.GeoDataFrame,
    counties: gpd.GeoDataFrame,
    *,
    field_slug_map: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    field_slug_map = field_slug_map or {}
    fields_proj = fields.to_crs("EPSG:5070")
    counties_proj = counties.to_crs("EPSG:5070")
    mapping_rows: list[dict[str, object]] = []
    ambiguity_rows: list[dict[str, object]] = []

    for _, field_row in fields_proj.iterrows():
        field_id = str(field_row.get("field_id", ""))
        field_slug = field_slug_map.get(field_id, "")
        geometry = field_row.geometry
        centroid = geometry.centroid

        containing = counties_proj[counties_proj.contains(centroid)].copy()
        intersecting = counties_proj[counties_proj.intersects(geometry)].copy()
        assigned = containing.iloc[0] if len(containing) == 1 else None
        assignment_method = "centroid"
        ambiguity_reason = ""

        if assigned is None and not intersecting.empty:
            intersecting["overlap_area_m2"] = intersecting.geometry.intersection(geometry).area
            overlap_areas = pd.Series(intersecting["overlap_area_m2"], dtype="float64")
            overlap_index = overlap_areas.index[int(overlap_areas.to_numpy().argmax())]
            assigned = intersecting.loc[overlap_index]
            assignment_method = "largest_overlap"
        elif assigned is None:
            ambiguity_reason = "no_county_match"

        overlap_count = int(len(intersecting))
        ambiguity_flag = overlap_count > 1 or assigned is None
        if overlap_count > 1 and not ambiguity_reason:
            ambiguity_reason = "multi_county_intersection"

        mapping_row = {
            "field_id": field_id,
            "field_slug": field_slug,
            "assignment_method": assignment_method,
            "ambiguity_flag": ambiguity_flag,
            "ambiguity_reason": ambiguity_reason,
            "county_overlap_count": overlap_count,
        }
        if assigned is not None:
            mapping_row.update(
                {
                    "fips": str(assigned.get("fips", "")),
                    "state_fips": str(assigned.get("state_fips", "")),
                    "county_fips": str(assigned.get("county_fips", "")),
                    "county_name": str(assigned.get("county_name", "")),
                    "county_name_full": str(assigned.get("county_name_full", "")),
                }
            )
        else:
            mapping_row.update(
                {
                    "fips": "",
                    "state_fips": "",
                    "county_fips": "",
                    "county_name": "",
                    "county_name_full": "",
                }
            )
        mapping_rows.append(mapping_row)

        if ambiguity_flag:
            ambiguity_rows.append(mapping_row.copy())

    return pd.DataFrame(mapping_rows), pd.DataFrame(ambiguity_rows)


def write_standardized_outputs(
    source: GeoadminSource,
    frame: gpd.GeoDataFrame,
    *,
    write_lookup: bool = True,
) -> dict[str, Path]:
    level_root = _geoadmin_level_root(source.level_slug)
    level_root.mkdir(parents=True, exist_ok=True)
    geojson_path = level_root / source.output_geojson
    parquet_path = level_root / source.output_parquet
    frame.to_file(geojson_path, driver="GeoJSON")
    frame.to_parquet(parquet_path, index=False)
    metadata_path = _geoadmin_level_root(source.level_slug) / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                **asdict(source),
                "feature_count": int(len(frame)),
                "columns": [column for column in frame.columns if column != "geometry"],
                "output_geojson": _repo_relative(geojson_path),
                "output_parquet": _repo_relative(parquet_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    outputs = {"geojson": geojson_path, "parquet": parquet_path, "metadata": metadata_path}
    if source.level_slug.startswith("l2_counties") and write_lookup:
        country_suffix = Path(source.output_geojson).stem.replace("counties_", "")
        lookup_name = (
            "fips_lookup.parquet" if country_suffix == "usa" else f"fips_lookup_{country_suffix}.parquet"
        )
        lookup_path = level_root / lookup_name
        _county_lookup(frame).to_parquet(lookup_path, index=False)
        outputs["lookup"] = lookup_path
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["lookup_parquet"] = _repo_relative(lookup_path)
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return outputs


def write_combined_fips_lookup() -> Path | None:
    """Merge per-country l2 lookups into ``fips_lookup.parquet``.

    ``aggregate_weather_by_fips.py`` and the maturity chain read this single
    file; it must contain every country's county-role units (US counties +
    Canadian census divisions), never just whichever layer was built last.
    """
    level_root = geoadmin_level_roots()["l2_counties"]
    frames: list[pd.DataFrame] = []
    usa = level_root / "fips_lookup.parquet"
    if usa.exists():
        frames.append(pd.read_parquet(usa))
    roots = [level_root] + sorted(
        root for slug, root in geoadmin_level_roots().items() if slug != "l2_counties"
    )
    # Per-country GADM levels write to their own roots (l2_counties_<iso>).
    roots += [r for r in _geoadmin_root().glob("l2_counties_*") if r.is_dir()]
    seen: set = set()
    for root in roots:
        for extra in sorted(root.glob("fips_lookup_*.parquet")):
            if extra.resolve() in seen:
                continue
            seen.add(extra.resolve())
            frames.append(pd.read_parquet(extra))
    if not frames:
        return None
    combined = cast(
        pd.DataFrame,
        pd.concat(frames, ignore_index=True).drop_duplicates(subset=["fips"], keep="first"),
    )
    combined = cast(pd.DataFrame, combined.sort_values("fips").reset_index(drop=True))
    combined.to_parquet(level_root / "fips_lookup_combined.parquet", index=False)
    combined.to_parquet(usa, index=False)
    return usa
