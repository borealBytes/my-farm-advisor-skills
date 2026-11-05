from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_SCRIPTS_ROOT = REPO_ROOT / "data" / "scripts"
DATA_SCRIPTS_LIB_ROOT = DATA_SCRIPTS_ROOT / "lib"
if str(DATA_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS_ROOT))
if str(DATA_SCRIPTS_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS_LIB_ROOT))


def _paths_module() -> Any:
    return importlib.import_module("paths")


_NON_CONTIGUOUS_STATE_FIPS = ("02", "15", "60", "66", "69", "72", "78")
_TRADITIONAL_CORN_STATE_FIPS = (
    "05",
    "17",
    "18",
    "19",
    "20",
    "21",
    "26",
    "27",
    "29",
    "31",
    "38",
    "39",
    "46",
    "55",
    # Ontario is Canada's corn belt (SW Ontario CHU zone 14-16, contiguous
    # with the Michigan/Iowa belt); "CA35" is the geoadmin Canada province
    # code (CA + StatCan PRUID 35). Added 2026-11-02 for Canadian parity.
    "CA35",
)


@dataclass(slots=True)
class AnnualMaturityConfig:
    year: int
    weather_source: str = "nasa-power"
    grower_slug: str = os.environ.get("AG_GROWER_SLUG", "default-grower")
    farm_slug: str = os.environ.get("AG_FARM_SLUG", "default-farm")

    @property
    def geoadmin_root(self) -> Path:
        return _paths_module().shared_geoadmin_dir()

    @property
    def corn_gdd_path(self) -> Path:
        return _paths_module().shared_corn_gdd_table_path(self.year)

    @property
    def field_fips_summary_path(self) -> Path:
        return _paths_module().farm_summary_path(
            self.grower_slug,
            self.farm_slug,
            "field_fips_mapping_summary.json",
        )

    @property
    def county_weather_path(self) -> Path:
        return _paths_module().shared_weather_county_table_path(
            self.weather_source, self.year, "daily_weather_by_fips.parquet"
        )

    @property
    def county_weather_summary_path(self) -> Path:
        return _paths_module().shared_weather_county_table_path(
            self.weather_source, self.year, "county_weather_coverage_summary.json"
        )

    @property
    def corn_rm_path(self) -> Path:
        return _paths_module().shared_corn_rm_table_path(self.year)

    @property
    def corn_rm_csv_path(self) -> Path:
        return _paths_module().shared_corn_rm_csv_path(self.year)

    @property
    def corn_map_path(self) -> Path:
        return _paths_module().shared_corn_maturity_reports_dir() / f"rm_by_fips_{self.year}.png"

    @property
    def soybean_mg_path(self) -> Path:
        return _paths_module().shared_soybean_mg_table_path(self.year)

    @property
    def soybean_mg_csv_path(self) -> Path:
        return _paths_module().shared_soybean_mg_csv_path(self.year)

    @property
    def soybean_map_path(self) -> Path:
        return _paths_module().shared_soybean_maturity_reports_dir() / f"mg_by_fips_{self.year}.png"


def build_year_output_index(config: AnnualMaturityConfig) -> dict[str, str]:
    return {
        "geoadmin_root": str(config.geoadmin_root),
        "field_fips_summary": str(config.field_fips_summary_path),
        "county_weather": str(config.county_weather_path),
        "county_weather_summary": str(config.county_weather_summary_path),
        "corn_gdd": str(config.corn_gdd_path),
        "corn_rm": str(config.corn_rm_path),
        "corn_rm_csv": str(config.corn_rm_csv_path),
        "corn_map": str(config.corn_map_path),
        "soybean_mg": str(config.soybean_mg_path),
        "soybean_mg_csv": str(config.soybean_mg_csv_path),
        "soybean_map": str(config.soybean_map_path),
    }


def contiguous_us_counties(counties: pd.DataFrame) -> pd.DataFrame:
    counties_frame = cast(pd.DataFrame, counties.copy())
    counties_frame["state_fips"] = counties_frame["state_fips"].astype(str).str.zfill(2)
    filtered = counties_frame[
        ~counties_frame["state_fips"].isin(list(_NON_CONTIGUOUS_STATE_FIPS))
    ].copy()
    return cast(pd.DataFrame, filtered)


def lower48_county_lookup(county_lookup: pd.DataFrame) -> pd.DataFrame:
    lookup = cast(pd.DataFrame, county_lookup.copy())
    lookup["fips"] = lookup["fips"].astype(str).str.zfill(5)
    lookup["state_fips"] = lookup["state_fips"].astype(str).str.zfill(2)
    lookup["county_fips"] = lookup["county_fips"].astype(str).str.zfill(3)
    return contiguous_us_counties(lookup)


def county_lookup_for_scope(county_lookup: pd.DataFrame, county_scope: str) -> pd.DataFrame:
    lookup = lower48_county_lookup(county_lookup)
    if county_scope == "lower48":
        return lookup
    if county_scope == "traditional-corn-belt":
        filtered = lookup[lookup["state_fips"].isin(list(_TRADITIONAL_CORN_STATE_FIPS))].copy()
        return cast(pd.DataFrame, filtered)
    if county_scope == "field-mapped":
        return lookup
    raise ValueError(f"Unsupported county scope: {county_scope}")


def aggregate_weather_to_counties(
    weather: pd.DataFrame,
    field_fips_mapping: pd.DataFrame,
) -> pd.DataFrame:
    mapping = cast(pd.DataFrame, field_fips_mapping.copy())
    mapping["field_id"] = mapping["field_id"].astype(str)
    mapping["fips"] = mapping["fips"].astype(str)
    mapping = cast(pd.DataFrame, mapping[mapping["fips"].str.len() > 0].copy())

    weather_frame = cast(pd.DataFrame, weather.copy())
    weather_frame["field_id"] = weather_frame["field_id"].astype(str)
    weather_frame["date"] = pd.to_datetime(weather_frame["date"])
    weather_frame["year"] = weather_frame["date"].dt.year.astype(int)

    mapping_fields = cast(
        pd.DataFrame,
        mapping[
            [
                "field_id",
                "field_slug",
                "fips",
                "state_fips",
                "county_fips",
                "county_name",
                "county_name_full",
            ]
        ].copy(),
    )

    joined = cast(pd.DataFrame, weather_frame.merge(mapping_fields, on="field_id", how="inner"))
    if joined.empty:
        return pd.DataFrame(
            {
                column: pd.Series(dtype="object")
                for column in [
                    "date",
                    "year",
                    "fips",
                    "state_fips",
                    "county_fips",
                    "county_name",
                    "county_name_full",
                    "field_count",
                    "source_field_ids",
                    "source_field_slugs",
                    "T2M",
                    "T2M_MAX",
                    "T2M_MIN",
                    "PRECTOTCORR",
                    "ALLSKY_SFC_SW_DWN",
                    "RH2M",
                    "WS10M",
                ]
            }
        )

    aggregated = (
        joined.groupby(
            [
                "date",
                "year",
                "fips",
                "state_fips",
                "county_fips",
                "county_name",
                "county_name_full",
            ],
            dropna=False,
        )
        .agg(
            field_count=("field_id", "nunique"),
            source_field_ids=("field_id", lambda values: sorted({str(value) for value in values})),
            source_field_slugs=(
                "field_slug",
                lambda values: sorted({str(value) for value in values if str(value)}),
            ),
            T2M=("T2M", "mean"),
            T2M_MAX=("T2M_MAX", "mean"),
            T2M_MIN=("T2M_MIN", "mean"),
            PRECTOTCORR=("PRECTOTCORR", "mean"),
            ALLSKY_SFC_SW_DWN=("ALLSKY_SFC_SW_DWN", "mean"),
            RH2M=("RH2M", "mean"),
            WS10M=("WS10M", "mean"),
        )
        .reset_index()
        .sort_values(["date", "fips"])
        .reset_index(drop=True)
    )
    return aggregated


def build_county_weather_coverage_summary(
    county_weather: pd.DataFrame,
    county_lookup: pd.DataFrame,
    *,
    weather_source: str,
    year: int,
    coverage_scope: str = "field-mapped",
    county_scope: str = "field-mapped",
    request_failure_count: int = 0,
) -> dict[str, object]:
    lookup = cast(pd.DataFrame, county_lookup.copy())
    lookup["fips"] = lookup["fips"].astype(str)
    county_weather_frame = cast(pd.DataFrame, county_weather.copy())
    if "fips" in county_weather_frame.columns:
        county_weather_frame["fips"] = county_weather_frame["fips"].astype(str)
    else:
        county_weather_frame["fips"] = pd.Series(dtype="object")

    covered = set(county_weather_frame["fips"].unique())
    all_counties = set(lookup["fips"].unique())
    uncovered = sorted(all_counties - covered)

    return {
        "weather_source": weather_source,
        "year": int(year),
        "coverage_scope": coverage_scope,
        "county_scope": county_scope,
        "county_count_total": int(len(all_counties)),
        "county_count_covered": int(len(covered)),
        "county_count_uncovered": int(len(uncovered)),
        "request_failure_count": int(request_failure_count),
        "coverage_policy": (
            "County weather is queried from NASA POWER once per shared grid cell and then joined back to counties in scope."
            if coverage_scope in {"traditional-corn-belt", "lower48"}
            else "Counties without mapped field weather remain absent from the daily county weather table."
        ),
        "uncovered_fips_sample": uncovered[:25],
    }


def compute_county_gdd(
    county_weather: pd.DataFrame,
    *,
    base_temp_c: float = 10.0,
    max_temp_c: float = 30.0,
) -> pd.DataFrame:
    weather = cast(pd.DataFrame, county_weather.copy())
    weather["date"] = pd.to_datetime(weather["date"])
    weather["year"] = weather["date"].dt.year.astype(int)

    tmax_capped = weather["T2M_MAX"].clip(upper=max_temp_c)
    tmin_capped = weather["T2M_MIN"].clip(lower=base_temp_c)
    daily_gdd = ((tmax_capped + tmin_capped) / 2.0) - base_temp_c
    weather["daily_gdd_c"] = daily_gdd.clip(lower=0.0)

    result = (
        weather.groupby(
            ["year", "fips", "state_fips", "county_fips", "county_name", "county_name_full"],
            dropna=False,
        )
        .agg(
            observation_days=("date", "nunique"),
            field_count_max=("field_count", "max"),
            gdd_total_c=("daily_gdd_c", "sum"),
            min_date=("date", "min"),
            max_date=("date", "max"),
        )
        .reset_index()
        .sort_values(["year", "fips"])
        .reset_index(drop=True)
    )
    result["base_temp_c"] = float(base_temp_c)
    result["max_temp_c"] = float(max_temp_c)
    return cast(pd.DataFrame, result)


def build_gdd_summary(
    county_gdd: pd.DataFrame,
    *,
    weather_source: str,
    year: int,
    base_temp_c: float,
    max_temp_c: float,
) -> dict[str, object]:
    return {
        "weather_source": weather_source,
        "year": int(year),
        "base_temp_c": float(base_temp_c),
        "max_temp_c": float(max_temp_c),
        "county_count": int(len(county_gdd)),
        "coverage_policy": "GDD is computed only for counties present in the canonical county weather table.",
    }


def compute_corn_rm(
    county_gdd: pd.DataFrame,
    *,
    gdd_per_rm_c: float = 20.0,
    min_rm: float = 65.0,
    max_rm: float = 130.0,
) -> pd.DataFrame:
    gdd = cast(pd.DataFrame, county_gdd.copy())
    gdd["rm_relative_maturity"] = (gdd["gdd_total_c"] / gdd_per_rm_c).clip(min_rm, max_rm).round(1)
    gdd["rm_band"] = (5 * (gdd["rm_relative_maturity"] / 5).round()).astype(int)
    return cast(pd.DataFrame, gdd)


def build_corn_rm_summary(
    county_rm: pd.DataFrame,
    *,
    year: int,
    gdd_per_rm_c: float,
) -> dict[str, object]:
    return {
        "year": int(year),
        "gdd_per_rm_c": float(gdd_per_rm_c),
        "county_count": int(len(county_rm)),
        "product_type": "heuristic",
        "caveat": "Corn RM outputs are planning heuristics derived from county GDD and are not recommendation-grade hybrid guidance.",
    }


def compute_soybean_mg(
    county_lookup: pd.DataFrame,
    county_gdd: pd.DataFrame,
    *,
    intercept: float = 7.5,
    latitude_slope: float = -0.11,
    min_mg: float = 0.0,
    max_mg: float = 7.0,
) -> pd.DataFrame:
    lookup = cast(pd.DataFrame, county_lookup.copy())
    gdd = cast(pd.DataFrame, county_gdd.copy())
    lookup["fips"] = lookup["fips"].astype(str)
    gdd["fips"] = gdd["fips"].astype(str)
    merged = cast(pd.DataFrame, gdd.merge(lookup[["fips", "centroid_lat"]], on="fips", how="left"))
    centroid_lat = cast(pd.Series, merged["centroid_lat"])
    mg_optimal = cast(pd.Series, intercept + latitude_slope * centroid_lat)
    mg_optimal = cast(pd.Series, mg_optimal.clip(min_mg, max_mg).round(1))
    merged["mg_optimal"] = mg_optimal
    merged["mg_early"] = (merged["mg_optimal"] - 0.4).clip(min_mg, max_mg).round(1)
    merged["mg_late"] = (merged["mg_optimal"] + 0.4).clip(min_mg, max_mg).round(1)
    merged["mg_band"] = (merged["mg_optimal"] * 2).round().div(2).round(1)
    return cast(pd.DataFrame, merged)


def build_soybean_mg_summary(
    county_mg: pd.DataFrame,
    *,
    year: int,
    intercept: float,
    latitude_slope: float,
) -> dict[str, object]:
    return {
        "year": int(year),
        "latitude_intercept": float(intercept),
        "latitude_slope": float(latitude_slope),
        "county_count": int(len(county_mg)),
        "product_type": "heuristic",
        "caveat": "Soybean MG outputs are latitude-based planning heuristics and are not recommendation-grade planting prescriptions.",
    }
