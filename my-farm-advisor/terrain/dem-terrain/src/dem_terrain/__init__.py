"""Import-safe DEM terrain contract and source resolver surface."""
# pyright: reportUnsupportedDunderAll=false

from . import source_resolver as _source_resolver
from . import terrain_contract as _terrain_contract

_CONTRACT_EXPORTS = (
    "ALL_PRODUCT_FILENAMES",
    "CLIPPED_DEM_FILENAME",
    "CONDITIONED_DEM_FILENAME",
    "DATA_PIPELINE_DATA_ROOT_ENV",
    "DERIVED_RASTER_FILENAMES",
    "DERIVED_RASTER_PRODUCT_NAMES",
    "DERIVED_TERRAIN_DIR_TEMPLATE",
    "FIELD_DEM_ROOT_TEMPLATE",
    "MANIFEST_ASSET_SCHEMA_FIELDS",
    "MANIFEST_FIELD_DEFINITIONS",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_FIELDS",
    "OUTPUT_ASSET_SCHEMA_DEFINITIONS",
    "OUTPUT_SCHEMA_FIELDS",
    "PRODUCT_DEFINITIONS",
    "RUNTIME_BASE_TEMPLATE",
    "SOURCE_CACHE_TEMPLATE",
    "SOURCE_REFERENCE_FILENAME",
    "SUMMARY_CSV_FILENAME",
    "SUMMARY_CSV_TEMPLATE",
    "SUMMARY_DEFINITIONS",
    "SUMMARY_FILENAMES",
    "SUMMARY_JSON_FILENAME",
    "SUMMARY_JSON_TEMPLATE",
    "TERRAIN_CONTRACT_VERSION",
    "TERRAIN_MANIFEST_TEMPLATE",
    "TERRAIN_TABLES_DIR_TEMPLATE",
    "ManifestField",
    "OutputAssetSchemaField",
    "ProductDefinition",
    "RuntimePathTemplates",
    "SummaryDefinition",
    "build_output_product_index",
)

for _name in _CONTRACT_EXPORTS:
    globals()[_name] = getattr(_terrain_contract, _name)

for _name in _source_resolver.__all__:
    globals()[_name] = getattr(_source_resolver, _name)

__all__ = sorted((*_CONTRACT_EXPORTS, *_source_resolver.__all__))
