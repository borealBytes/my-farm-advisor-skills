# Runtime data-pipeline scripts/lib - Canonical helper modules for data tree operations
"""
Helper package for canonical path construction, naming utilities, and manifest management.

This package provides:
- paths.py: Canonical path builders for grower/farm/field/shared locations
- naming.py: Naming normalization utilities
- manifest.py: Manifest read/write helpers
"""

__version__ = "1.0.0"

from .manifest import append_jsonl, read_json, write_json
from .naming import ensure_osm_field_id, field_slug_from_id, slugify
