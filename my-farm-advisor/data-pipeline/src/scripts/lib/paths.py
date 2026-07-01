from __future__ import annotations

import os
import re
from pathlib import Path

try:
    from .runtime_paths import resolve_runtime_paths
except ImportError:  # Support scripts that import this module as top-level "paths".
    from runtime_paths import resolve_runtime_paths


_RUNTIME_PATHS = resolve_runtime_paths()

DATA_ROOT = _RUNTIME_PATHS.runtime_base
SCRIPTS_ROOT = _RUNTIME_PATHS.runtime_scripts
GROWERS_ROOT = DATA_ROOT / "growers"
SHARED_ROOT = DATA_ROOT / "shared"
_SAFE_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_path_slug(value: str, label: str = "slug") -> str:
    slug = str(value)
    if not slug:
        raise ValueError(f"{label} must not be empty")
    if slug in {".", ".."}:
        raise ValueError(f"{label} must not be '.' or '..'")
    if "/" in slug or "\\" in slug:
        raise ValueError(f"{label} must not contain path separators: {slug!r}")
    if Path(slug).is_absolute():
        raise ValueError(f"{label} must not be an absolute path: {slug!r}")
    if "://" in slug or not _SAFE_SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            f"{label} contains unsafe characters: {slug!r}; "
            "use only letters, digits, dot, underscore, and hyphen"
        )
    return slug


def ensure_data_root_path(path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = DATA_ROOT / candidate
    resolved_root = DATA_ROOT.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Path escapes data-pipeline runtime root: {candidate}") from exc
    return resolved_candidate


def _data_root_path(*parts: str) -> Path:
    return ensure_data_root_path(DATA_ROOT.joinpath(*parts))


def grower_dir(grower_slug: str) -> Path:
    return _data_root_path("growers", validate_path_slug(grower_slug, "grower_slug"))


def grower_manifest_dir(grower_slug: str) -> Path:
    return grower_dir(grower_slug) / "manifests"


def grower_manifest_path(grower_slug: str, filename: str = "pipeline_schedule.json") -> Path:
    return grower_manifest_dir(grower_slug) / filename


def grower_logs_dir(grower_slug: str) -> Path:
    return grower_dir(grower_slug) / "logs"


def farm_dir(grower_slug: str, farm_slug: str) -> Path:
    return ensure_data_root_path(
        grower_dir(grower_slug) / "farms" / validate_path_slug(farm_slug, "farm_slug")
    )


def farm_manifest_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_dir(grower_slug, farm_slug) / "manifests"


def farm_boundary_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_dir(grower_slug, farm_slug) / "boundary"


def farm_boundary_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_boundary_dir(grower_slug, farm_slug) / "field_boundaries.geojson"


def farm_logs_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_dir(grower_slug, farm_slug) / "logs"


def farm_logs_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_logs_dir(grower_slug, farm_slug) / "pipeline_runs.jsonl"


def farm_derived_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_dir(grower_slug, farm_slug) / "derived"


def farm_reports_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_derived_dir(grower_slug, farm_slug) / "reports"


def farm_summaries_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_derived_dir(grower_slug, farm_slug) / "summaries"


def farm_dashboards_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_derived_dir(grower_slug, farm_slug) / "dashboards"


def farm_tables_dir(grower_slug: str, farm_slug: str) -> Path:
    return farm_derived_dir(grower_slug, farm_slug) / "tables"


def farm_table_path(grower_slug: str, farm_slug: str, filename: str) -> Path:
    return farm_tables_dir(grower_slug, farm_slug) / filename


def _normalized_farm_artifact_prefix(farm_slug: str) -> str:
    normalized = validate_path_slug(farm_slug, "farm_slug").replace("-", "_")
    if normalized == "iowa_demo_farm":
        return "iowa"
    if normalized.endswith("_farm"):
        normalized = normalized[: -len("_farm")]
    return normalized


def farm_report_basename(farm_slug: str, extension: str) -> str:
    return f"{_normalized_farm_artifact_prefix(farm_slug)}_farm_report.{extension}"


def farm_weather_basename(
    farm_slug: str,
    start_year: int = 2021,
    end_year: int = 2025,
) -> str:
    prefix = _normalized_farm_artifact_prefix(farm_slug)
    return f"{prefix}_weather_{start_year}_{end_year}.csv"


def farm_ssurgo_full_basename(farm_slug: str) -> str:
    return f"{_normalized_farm_artifact_prefix(farm_slug)}_full_ssurgo.csv"


def farm_ssurgo_summary_basename(farm_slug: str) -> str:
    return f"{_normalized_farm_artifact_prefix(farm_slug)}_ssurgo_summary.csv"


def farm_soil_sample_basename(farm_slug: str) -> str:
    return f"{_normalized_farm_artifact_prefix(farm_slug)}_fields_soil.csv"


def _weather_year_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def farm_weather_path(
    grower_slug: str,
    farm_slug: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> Path:
    start_year = start_year or _weather_year_from_env("AG_WEATHER_START_YEAR", 2021)
    end_year = end_year or _weather_year_from_env("AG_WEATHER_END_YEAR", 2025)
    return farm_table_path(
        grower_slug, farm_slug, farm_weather_basename(farm_slug, start_year, end_year)
    )


def farm_ssurgo_full_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_table_path(grower_slug, farm_slug, farm_ssurgo_full_basename(farm_slug))


def farm_ssurgo_summary_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_table_path(grower_slug, farm_slug, farm_ssurgo_summary_basename(farm_slug))


def farm_soil_sample_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_table_path(grower_slug, farm_slug, farm_soil_sample_basename(farm_slug))


def farm_report_asset_path(grower_slug: str, farm_slug: str, extension: str) -> Path:
    return farm_report_path(grower_slug, farm_slug, farm_report_basename(farm_slug, extension))


def field_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return ensure_data_root_path(
        farm_dir(grower_slug, farm_slug) / "fields" / validate_path_slug(field_slug, "field_slug")
    )


def field_boundary_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "boundary"


def field_boundary_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_boundary_dir(grower_slug, farm_slug, field_slug) / "field_boundary.geojson"


def field_soil_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "soil"


def field_soil_polygon_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_soil_dir(grower_slug, farm_slug, field_slug) / "ssurgo_soil_types.geojson"


def field_soil_full_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_soil_dir(grower_slug, farm_slug, field_slug) / "ssurgo_full.csv"


def field_soil_summary_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_soil_dir(grower_slug, farm_slug, field_slug) / "ssurgo_summary.csv"


def field_weather_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "weather"


def field_weather_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_weather_dir(grower_slug, farm_slug, field_slug) / "daily_weather.csv"


def field_satellite_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "satellite"


def field_terrain_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "terrain"


def field_dem_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_terrain_dir(grower_slug, farm_slug, field_slug) / "dem"


def field_manifest_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "manifests"


def field_derived_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "derived"


def field_terrain_derived_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_derived_dir(grower_slug, farm_slug, field_slug) / "terrain"


def field_reports_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_derived_dir(grower_slug, farm_slug, field_slug) / "reports"


def field_summaries_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_derived_dir(grower_slug, farm_slug, field_slug) / "summaries"


def field_features_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_derived_dir(grower_slug, farm_slug, field_slug) / "features"


def field_tables_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_derived_dir(grower_slug, farm_slug, field_slug) / "tables"


def field_logs_dir(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_dir(grower_slug, farm_slug, field_slug) / "logs"


def field_logs_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_logs_dir(grower_slug, farm_slug, field_slug) / "pipeline_runs.jsonl"


def field_feature_path(grower_slug: str, farm_slug: str, field_slug: str, filename: str) -> Path:
    return field_features_dir(grower_slug, farm_slug, field_slug) / filename


def field_summary_path(grower_slug: str, farm_slug: str, field_slug: str, filename: str) -> Path:
    return field_summaries_dir(grower_slug, farm_slug, field_slug) / filename


def field_report_path(grower_slug: str, farm_slug: str, field_slug: str, filename: str) -> Path:
    return field_reports_dir(grower_slug, farm_slug, field_slug) / filename


def field_dem_manifest_path(grower_slug: str, farm_slug: str, field_slug: str) -> Path:
    return field_manifest_dir(grower_slug, farm_slug, field_slug) / "dem_terrain_manifest.json"


def farm_report_path(grower_slug: str, farm_slug: str, filename: str) -> Path:
    return farm_reports_dir(grower_slug, farm_slug) / filename


def farm_summary_path(grower_slug: str, farm_slug: str, filename: str) -> Path:
    return farm_summaries_dir(grower_slug, farm_slug) / filename


def farm_cdl_year_table_path(grower_slug: str, farm_slug: str, year: int) -> Path:
    return farm_table_path(
        grower_slug, farm_slug, f"{_normalized_farm_artifact_prefix(farm_slug)}_{year}_cdl.csv"
    )


def farm_cdl_rotation_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_table_path(
        grower_slug, farm_slug, f"{_normalized_farm_artifact_prefix(farm_slug)}_crop_rotation.csv"
    )


def farm_dem_summary_table_path(grower_slug: str, farm_slug: str) -> Path:
    return farm_table_path(
        grower_slug, farm_slug, f"{_normalized_farm_artifact_prefix(farm_slug)}_dem_summary.csv"
    )


def farm_cdl_full_composition_path(
    grower_slug: str,
    farm_slug: str,
    start_year: int = 2021,
    end_year: int = 2025,
) -> Path:
    prefix = _normalized_farm_artifact_prefix(farm_slug)
    return farm_table_path(
        grower_slug, farm_slug, f"{prefix}_cdl_{start_year}_{end_year}_full_composition.csv"
    )


def farm_cdl_preferred_full_composition_path(
    grower_slug: str,
    farm_slug: str,
    preferred_ranges: tuple[tuple[int, int], ...] = ((2021, 2025), (2020, 2024), (2021, 2024)),
) -> Path:
    for start_year, end_year in preferred_ranges:
        candidate = farm_cdl_full_composition_path(grower_slug, farm_slug, start_year, end_year)
        if candidate.exists():
            return candidate
    first_start, first_end = preferred_ranges[0]
    return farm_cdl_full_composition_path(grower_slug, farm_slug, first_start, first_end)


def shared_cdl_dir() -> Path:
    return SHARED_ROOT / "cdl"


def shared_dem_dir() -> Path:
    return SHARED_ROOT / "dem"


def shared_dem_cache_path(adapter_slug: str) -> Path:
    return ensure_data_root_path(shared_dem_dir() / validate_path_slug(adapter_slug, "adapter_slug"))


def shared_cdl_raster_dir() -> Path:
    return shared_cdl_dir() / "rasters"


def shared_cdl_state_raster_path(year: int, state_fips: str) -> Path:
    return shared_cdl_raster_dir() / f"CDL_{year}_{state_fips.zfill(2)}.tif"


def shared_cdl_conus_raster_path(year: int) -> Path:
    return shared_cdl_raster_dir() / f"CDL_{year}_CONUS.tif"


def shared_cdl_derived_dir() -> Path:
    return shared_cdl_dir() / "derived"


def shared_cdl_tables_dir() -> Path:
    return shared_cdl_derived_dir() / "tables"


def shared_cdl_reports_dir() -> Path:
    return shared_cdl_derived_dir() / "reports"


def shared_cdl_year_table_path(year: int) -> Path:
    return shared_cdl_tables_dir() / f"iowa_{year}_cdl.csv"


def shared_cdl_rotation_path() -> Path:
    return shared_cdl_tables_dir() / "iowa_crop_rotation.csv"


def shared_cdl_full_composition_path(start_year: int = 2021, end_year: int = 2025) -> Path:
    return shared_cdl_tables_dir() / f"iowa_cdl_{start_year}_{end_year}_full_composition.csv"


def shared_cdl_preferred_full_composition_path(
    preferred_ranges: tuple[tuple[int, int], ...] = ((2021, 2025), (2020, 2024), (2021, 2024)),
) -> Path:
    for start_year, end_year in preferred_ranges:
        candidate = shared_cdl_full_composition_path(start_year, end_year)
        if candidate.exists():
            return candidate
    first_start, first_end = preferred_ranges[0]
    return shared_cdl_full_composition_path(first_start, first_end)


def shared_cdl_metadata_dir() -> Path:
    return shared_cdl_dir() / "metadata"


def shared_cdl_manifest_dir() -> Path:
    return shared_cdl_dir() / "manifests"


def shared_cdl_logs_dir() -> Path:
    return shared_cdl_dir() / "logs"


def shared_manifest_dir() -> Path:
    return SHARED_ROOT / "manifests"


def shared_logs_dir() -> Path:
    return SHARED_ROOT / "logs"


def shared_reference_dir() -> Path:
    return SHARED_ROOT / "reference"


def shared_weather_dir() -> Path:
    return SHARED_ROOT / "weather"


def shared_weather_source_dir(source_slug: str) -> Path:
    return shared_weather_dir() / source_slug


def shared_weather_year_dir(source_slug: str, year: int) -> Path:
    return shared_weather_source_dir(source_slug) / str(year)


def shared_weather_county_table_path(source_slug: str, year: int, filename: str) -> Path:
    return shared_weather_year_dir(source_slug, year) / filename


def shared_geoadmin_dir() -> Path:
    return SHARED_ROOT / "geoadmin"


def shared_geoadmin_countries_dir() -> Path:
    return shared_geoadmin_dir() / "l0_countries"


def shared_geoadmin_states_dir() -> Path:
    return shared_geoadmin_dir() / "l1_states"


def shared_geoadmin_counties_dir() -> Path:
    return shared_geoadmin_dir() / "l2_counties"


def shared_geoadmin_raw_dir(level_slug: str) -> Path:
    return shared_geoadmin_dir() / level_slug / "raw"


def shared_geoadmin_metadata_path(level_slug: str, filename: str = "metadata.json") -> Path:
    return shared_geoadmin_dir() / level_slug / filename


def shared_corn_maturity_dir() -> Path:
    return SHARED_ROOT / "corn_maturity"


def shared_corn_maturity_tables_dir() -> Path:
    return shared_corn_maturity_dir() / "tables"


def shared_corn_maturity_reports_dir() -> Path:
    return shared_corn_maturity_dir() / "reports"


def shared_corn_maturity_metadata_dir() -> Path:
    return shared_corn_maturity_dir() / "metadata"


def shared_corn_maturity_manifest_dir() -> Path:
    return shared_corn_maturity_dir() / "manifests"


def shared_corn_maturity_logs_dir() -> Path:
    return shared_corn_maturity_dir() / "logs"


def shared_corn_gdd_table_path(year: int) -> Path:
    return shared_corn_maturity_tables_dir() / f"gdd_by_fips_{year}.parquet"


def shared_corn_rm_table_path(year: int) -> Path:
    return shared_corn_maturity_tables_dir() / f"rm_by_fips_{year}.parquet"


def shared_corn_rm_csv_path(year: int) -> Path:
    return shared_corn_maturity_tables_dir() / f"rm_by_fips_{year}.csv"


def shared_corn_rm_average_table_path(start_year: int, end_year: int) -> Path:
    return shared_corn_maturity_tables_dir() / f"rm_by_fips_{start_year}_{end_year}_average.parquet"


def shared_corn_rm_average_csv_path(start_year: int, end_year: int) -> Path:
    return shared_corn_maturity_tables_dir() / f"rm_by_fips_{start_year}_{end_year}_average.csv"


def shared_soybean_maturity_dir() -> Path:
    return SHARED_ROOT / "soybean_maturity"


def shared_soybean_maturity_tables_dir() -> Path:
    return shared_soybean_maturity_dir() / "tables"


def shared_soybean_maturity_reports_dir() -> Path:
    return shared_soybean_maturity_dir() / "reports"


def shared_soybean_maturity_metadata_dir() -> Path:
    return shared_soybean_maturity_dir() / "metadata"


def shared_soybean_maturity_manifest_dir() -> Path:
    return shared_soybean_maturity_dir() / "manifests"


def shared_soybean_maturity_logs_dir() -> Path:
    return shared_soybean_maturity_dir() / "logs"


def shared_soybean_mg_table_path(year: int) -> Path:
    return shared_soybean_maturity_tables_dir() / f"mg_by_fips_{year}.parquet"


def shared_soybean_mg_csv_path(year: int) -> Path:
    return shared_soybean_maturity_tables_dir() / f"mg_by_fips_{year}.csv"


def shared_soybean_mg_average_table_path(start_year: int, end_year: int) -> Path:
    return shared_soybean_maturity_tables_dir() / f"mg_by_fips_{start_year}_{end_year}_average.parquet"


def shared_soybean_mg_average_csv_path(start_year: int, end_year: int) -> Path:
    return shared_soybean_maturity_tables_dir() / f"mg_by_fips_{start_year}_{end_year}_average.csv"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
