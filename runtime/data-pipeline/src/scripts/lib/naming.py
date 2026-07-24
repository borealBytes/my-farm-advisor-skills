from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    normalized = _NON_ALNUM.sub("-", normalized)
    normalized = normalized.strip("-")
    if not normalized:
        raise ValueError("slugify produced empty slug")
    return normalized


def field_slug_from_id(field_id: str) -> str:
    return slugify(field_id)


def ensure_osm_field_id(field_id: str) -> str:
    value = field_id.strip()
    if not value.startswith("OSM_"):
        raise ValueError(f"Unsupported field id format: {field_id}")
    return value
