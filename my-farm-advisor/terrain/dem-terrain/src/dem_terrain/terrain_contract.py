"""Runtime contract for field-level DEM terrain products.

This module defines names, path templates, and schema fields only. It must stay
safe to import in a checkout with no DATA_PIPELINE_DATA_ROOT configured and must
not create runtime directories, DEM rasters, summaries, manifests, or caches.
"""

from __future__ import annotations

from dataclasses import dataclass


TERRAIN_CONTRACT_VERSION = "0.1.0"

DATA_PIPELINE_DATA_ROOT_ENV = "DATA_PIPELINE_DATA_ROOT"
RUNTIME_BASE_TEMPLATE = "${DATA_PIPELINE_DATA_ROOT}/data-pipeline"

FIELD_DEM_ROOT_TEMPLATE = (
    "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/"
    "fields/<field_slug>/terrain/dem/"
)
DERIVED_TERRAIN_DIR_TEMPLATE = "fields/<field_slug>/derived/terrain/"
TERRAIN_TABLES_DIR_TEMPLATE = "fields/<field_slug>/derived/tables/"
SUMMARY_CSV_TEMPLATE = "fields/<field_slug>/derived/tables/dem_terrain_summary.csv"
SUMMARY_JSON_TEMPLATE = "fields/<field_slug>/derived/tables/dem_terrain_summary.json"
TERRAIN_MANIFEST_TEMPLATE = "fields/<field_slug>/manifests/dem_terrain_manifest.json"
SOURCE_CACHE_TEMPLATE = "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/dem/<adapter>/"

SOURCE_REFERENCE_FILENAME = "dem_source_reference.json"
CLIPPED_DEM_FILENAME = "dem_clipped.tif"
CONDITIONED_DEM_FILENAME = "dem_conditioned.tif"

DERIVED_RASTER_FILENAMES = (
    "slope_degrees.tif",
    "slope_percent.tif",
    "aspect_degrees.tif",
    "hillshade.tif",
    "profile_curvature.tif",
    "planform_curvature.tif",
    "tpi.tif",
    "tri.tif",
    "flow_direction.tif",
    "flow_accumulation.tif",
    "topographic_wetness_index.tif",
    "depression_depth.tif",
    "relative_elevation.tif",
    "erosion_proxy.tif",
)

DERIVED_RASTER_PRODUCT_NAMES = tuple(filename.removesuffix(".tif") for filename in DERIVED_RASTER_FILENAMES)

ALL_PRODUCT_FILENAMES = (
    SOURCE_REFERENCE_FILENAME,
    CLIPPED_DEM_FILENAME,
    CONDITIONED_DEM_FILENAME,
    *DERIVED_RASTER_FILENAMES,
)

SUMMARY_CSV_FILENAME = "dem_terrain_summary.csv"
SUMMARY_JSON_FILENAME = "dem_terrain_summary.json"
SUMMARY_FILENAMES = (SUMMARY_CSV_FILENAME, SUMMARY_JSON_FILENAME)

MANIFEST_FILENAME = "dem_terrain_manifest.json"

MANIFEST_SCHEMA_FIELDS = (
    "run_id",
    "field_id",
    "field_slug",
    "buffer_meters",
    "analysis_crs",
    "selected_source",
    "candidate_sources",
    "fallback_reason",
    "surface_type",
    "source_resolution_m",
    "source_horizontal_crs",
    "source_vertical_datum",
    "source_urls",
    "license",
    "citation",
    "acquisition_date",
    "publication_date",
    "processing_parameters",
    "warnings",
    "outputs",
    "checksums",
    "generated_at",
)

OUTPUT_SCHEMA_FIELDS = (
    "product_name",
    "filename",
    "href",
    "type",
    "roles",
    "summary",
    "unit",
    "data_type",
    "nodata",
    "resolution_m",
    "analysis_crs",
    "source_product",
    "surface_type",
    "warnings",
)

MANIFEST_ASSET_SCHEMA_FIELDS = (
    "href",
    "type",
    "roles",
    "title",
    "description",
    "proj:epsg",
    "proj:wkt2",
    "raster:bands",
    "raster:nodata",
    "raster:data_type",
    "raster:unit",
    "raster:resolution",
    "file:size",
    "checksum:sha256",
    "source:hrefs",
    "source:license",
    "source:citation",
    "source:acquisition_date",
    "source:publication_date",
    "dem:surface_type",
    "dem:dsm_dtm_warning",
)


@dataclass(frozen=True, slots=True)
class RuntimePathTemplates:
    """String templates for runtime-only DEM terrain locations."""

    runtime_base: str = RUNTIME_BASE_TEMPLATE
    field_dem_root: str = FIELD_DEM_ROOT_TEMPLATE
    derived_rasters: str = DERIVED_TERRAIN_DIR_TEMPLATE
    tables: str = TERRAIN_TABLES_DIR_TEMPLATE
    summary_csv: str = SUMMARY_CSV_TEMPLATE
    summary_json: str = SUMMARY_JSON_TEMPLATE
    manifest: str = TERRAIN_MANIFEST_TEMPLATE
    source_cache: str = SOURCE_CACHE_TEMPLATE


@dataclass(frozen=True, slots=True)
class ProductDefinition:
    """Deterministic product name and filename pair."""

    name: str
    filename: str
    role: str


@dataclass(frozen=True, slots=True)
class SummaryDefinition:
    """Deterministic summary table name and media type."""

    name: str
    filename: str
    media_type: str


@dataclass(frozen=True, slots=True)
class ManifestField:
    """Manifest field name with short implementation guidance."""

    name: str
    guidance: str


@dataclass(frozen=True, slots=True)
class OutputAssetSchemaField:
    """STAC-like asset field expected inside manifest outputs."""

    name: str
    guidance: str


PRODUCT_DEFINITIONS = (
    ProductDefinition("dem_source_reference", SOURCE_REFERENCE_FILENAME, "metadata"),
    ProductDefinition("dem_clipped", CLIPPED_DEM_FILENAME, "source-dem"),
    ProductDefinition("dem_conditioned", CONDITIONED_DEM_FILENAME, "conditioned-dem"),
    *(ProductDefinition(name, filename, "derived-terrain") for name, filename in zip(DERIVED_RASTER_PRODUCT_NAMES, DERIVED_RASTER_FILENAMES)),
)

SUMMARY_DEFINITIONS = (
    SummaryDefinition("dem_terrain_summary_csv", SUMMARY_CSV_FILENAME, "text/csv"),
    SummaryDefinition("dem_terrain_summary_json", SUMMARY_JSON_FILENAME, "application/json"),
)

MANIFEST_FIELD_DEFINITIONS = tuple(
    ManifestField(name, "Required DEM terrain manifest field from the Task 1 plan.")
    for name in MANIFEST_SCHEMA_FIELDS
)

OUTPUT_ASSET_SCHEMA_DEFINITIONS = tuple(
    OutputAssetSchemaField(name, "STAC-like output asset metadata for DEM terrain manifests.")
    for name in MANIFEST_ASSET_SCHEMA_FIELDS
)


def build_output_product_index() -> dict[str, str]:
    """Return deterministic product-name-to-filename mappings."""

    return {product.name: product.filename for product in PRODUCT_DEFINITIONS}
