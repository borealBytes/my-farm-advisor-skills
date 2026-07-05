"""Illinois ILHMP/ISGS DEM source discovery metadata and guards.

This adapter is stdlib-only and import-safe. It uses maintained provider
reference records and AOI hints to expose Illinois Height Modernization Program
candidate metadata without scraping web pages or downloading county archives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .source_resolver import (
    ADAPTER_ILLINOIS_ILHMP,
    REGION_POLICY_ILLINOIS,
    SURFACE_DEM,
    SURFACE_DTM,
    SURFACE_UNKNOWN,
    SourceAOI,
    SourceAdapter,
    SourceCandidate,
)


DEFAULT_MAX_DEFAULT_DOWNLOAD_SIZE_MB = 512.0
FALLBACK_MANUAL_OR_SERVICE_LIMITED = "available_but_manual_or_service_limited"
FALLBACK_LARGE_DOWNLOAD_BLOCKED = "large_download_blocked_by_default_policy"

ILHMP_DATA_PAGE_URL = "https://clearinghouse.isgs.illinois.edu/data/elevation/illinois-height-modernization-ilhmp"
ILHMP_DATA_PAGE_LEGACY_URL = "https://clearinghouse.isgs.illinois.edu/webdocs/ilhmp/data.html"
ILHMP_ISGS_PROGRAM_URL = "https://isgs.illinois.edu/research/height-modernization/"
ILHMP_DERIVATIVES_URL = "https://isgs.illinois.edu/illinois-height-modernization-lidar-derivatives"
ILHMP_TERMS_URL = "https://clearinghouse.isgs.illinois.edu/webdocs/license.html"

ILLINOIS_BBOX_WGS84 = (-91.55, 36.95, -87.00, 42.55)
DEKALB_COUNTY_CONTEXT_BBOX_WGS84 = (-89.10, 41.70, -88.55, 42.20)

ILHMP_LICENSE = (
    "Illinois Geospatial Data Clearinghouse terms of use; verify dataset-level "
    "citation and restrictions before operational use."
)
ILHMP_CITATION = (
    "Illinois Height Modernization Program, Illinois State Geological Survey, "
    "and Illinois Department of Transportation."
)
ILHMP_ACCESS_NOTE = (
    "ISGS identifies high-resolution lidar elevation data for Illinois counties; "
    "default discovery records provider references only and does not download "
    "full county archives."
)


@dataclass(frozen=True, slots=True)
class IllinoisAOIContext:
    """Illinois-specific AOI interpretation without geospatial dependencies."""

    intersects_illinois: bool
    region_hint: str | None = None
    county_contexts: tuple[str, ...] = ()
    bbox_wgs84: tuple[float, float, float, float] | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class IllinoisILHMPCatalogRecord:
    """Maintained Illinois ILHMP/ISGS provider-reference metadata."""

    source_id: str
    source_name: str
    source_urls: tuple[str, ...]
    metadata_urls: tuple[str, ...]
    access_kind: str
    access_note: str
    region_hints: tuple[str, ...]
    resolution_m: float | None = None
    surface_type: str = SURFACE_UNKNOWN
    estimated_download_size_mb: float | None = None
    bbox_wgs84: tuple[float, float, float, float] | None = None
    acquisition_date: str | None = None
    publication_date: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""

        return asdict(self)


DEFAULT_ILLINOIS_ILHMP_CATALOG = (
    IllinoisILHMPCatalogRecord(
        source_id="ilhmp_statewide_provider_reference",
        source_name="Illinois Height Modernization Program lidar elevation data",
        source_urls=(ILHMP_DATA_PAGE_URL, ILHMP_ISGS_PROGRAM_URL),
        metadata_urls=(ILHMP_DERIVATIVES_URL, ILHMP_TERMS_URL, ILHMP_DATA_PAGE_LEGACY_URL),
        access_kind="manual_viewer_or_service_limited",
        access_note=ILHMP_ACCESS_NOTE,
        region_hints=("IL", "Illinois"),
        resolution_m=1.0,
        surface_type=SURFACE_UNKNOWN,
        bbox_wgs84=ILLINOIS_BBOX_WGS84,
        warnings=(
            "provider_reference_only=no_safe_direct_raster_url_identified",
            "access_mode=manual_viewer_or_service_limited",
        ),
    ),
    IllinoisILHMPCatalogRecord(
        source_id="ilhmp_dekalb_county_archive_reference",
        source_name="Illinois ILHMP/ISGS DeKalb County lidar derivative archive reference",
        source_urls=(ILHMP_DATA_PAGE_URL, ILHMP_DATA_PAGE_LEGACY_URL),
        metadata_urls=(ILHMP_ISGS_PROGRAM_URL, ILHMP_DERIVATIVES_URL, ILHMP_TERMS_URL),
        access_kind="county_archive",
        access_note=(
            "County-level ILHMP derivative archives can be bulky; default adapter "
            "policy blocks archive downloads unless allow_large_downloads=True."
        ),
        region_hints=("IL", "Illinois", "DeKalb County", "Northern Illinois"),
        resolution_m=1.0,
        surface_type=SURFACE_DTM,
        estimated_download_size_mb=2048.0,
        bbox_wgs84=DEKALB_COUNTY_CONTEXT_BBOX_WGS84,
        warnings=("county_context=DeKalb", "archive_scope=county_level"),
    ),
)


class IllinoisILHMPAdapter(SourceAdapter):
    """Illinois ILHMP/ISGS source metadata adapter with default size guards."""

    adapter_id = ADAPTER_ILLINOIS_ILHMP
    adapter_name = "Illinois ILHMP/ISGS"

    def __init__(
        self,
        *,
        catalog: Iterable[IllinoisILHMPCatalogRecord] | None = None,
        allow_large_downloads: bool = False,
        max_default_download_size_mb: float = DEFAULT_MAX_DEFAULT_DOWNLOAD_SIZE_MB,
    ) -> None:
        self.catalog = tuple(catalog or DEFAULT_ILLINOIS_ILHMP_CATALOG)
        self.allow_large_downloads = allow_large_downloads
        self.max_default_download_size_mb = max(0.0, max_default_download_size_mb)
        self.last_context: IllinoisAOIContext | None = None

    def discover(self, aoi: SourceAOI) -> tuple[SourceCandidate, ...]:
        """Discover Illinois provider-reference candidates without downloads."""

        context = discover_illinois_context(aoi)
        self.last_context = context
        if not context.intersects_illinois:
            return ()

        candidates: list[SourceCandidate] = []
        for record in self.catalog:
            if not _record_applies_to_context(record, context):
                continue
            candidates.append(
                catalog_record_to_candidate(
                    record,
                    aoi=aoi,
                    context=context,
                    allow_large_downloads=self.allow_large_downloads,
                    max_default_download_size_mb=self.max_default_download_size_mb,
                )
            )
        return tuple(candidates)

    def download(self, candidate: SourceCandidate, cache: str | Path) -> Path:
        """Refuse default county/manual downloads; later ingest tasks own exports."""

        del cache
        if candidate.fallback_reason == FALLBACK_LARGE_DOWNLOAD_BLOCKED:
            raise PermissionError(
                "Illinois ILHMP county archive downloads are blocked by default; "
                "instantiate IllinoisILHMPAdapter(allow_large_downloads=True) and use "
                "a runtime cache outside the repository for explicit large downloads."
            )
        raise NotImplementedError(
            "Illinois ILHMP/ISGS discovery currently returns provider references only; "
            "direct export/download handling is implemented only after a safe direct "
            "raster service or tile URL is identified."
        )

    def prepare(self, candidate: SourceCandidate) -> Path:
        """Raster preparation is owned by later DEM terrain ingest tasks."""

        del candidate
        raise NotImplementedError("Illinois ILHMP raster preparation is implemented in a later raster task.")


def discover_illinois_context(aoi: SourceAOI) -> IllinoisAOIContext:
    """Interpret SourceAOI country/region/bbox hints for Illinois discovery."""

    region = (aoi.region or "").strip()
    region_upper = region.upper()
    country_upper = (aoi.country or "").strip().upper()
    notes: list[str] = []
    county_contexts: list[str] = []

    region_says_illinois = region_upper in {"IL", "ILLINOIS"} or "ILLINOIS" in region_upper
    bbox_intersects_illinois = bool(aoi.bbox_wgs84 and bbox_intersects(aoi.bbox_wgs84, ILLINOIS_BBOX_WGS84))
    intersects = bool(aoi.intersects_illinois or region_says_illinois or bbox_intersects_illinois)
    if country_upper and country_upper not in {"US", "USA", "UNITED STATES"} and not intersects:
        return IllinoisAOIContext(False, region_hint=aoi.region, bbox_wgs84=aoi.bbox_wgs84)

    if aoi.intersects_illinois:
        notes.append("SourceAOI.intersects_illinois=True")
    if region_says_illinois:
        notes.append(f"region_hint={region}")
    if bbox_intersects_illinois:
        notes.append("bbox_intersects_illinois")

    if estimate_county_context(aoi.bbox_wgs84, region_hint=region):
        county_contexts.append("DeKalb County")
        notes.append("county_context_estimate=DeKalb County")

    return IllinoisAOIContext(
        intersects_illinois=intersects,
        region_hint=aoi.region,
        county_contexts=tuple(county_contexts),
        bbox_wgs84=aoi.bbox_wgs84,
        notes=tuple(notes),
    )


def estimate_county_context(
    bbox_wgs84: tuple[float, float, float, float] | None,
    *,
    region_hint: str | None = None,
) -> str | None:
    """Return a conservative county context label for known northern Illinois fixtures."""

    if region_hint and "DEKALB" in region_hint.upper():
        return "DeKalb County"
    if bbox_wgs84 and bbox_intersects(bbox_wgs84, DEKALB_COUNTY_CONTEXT_BBOX_WGS84):
        return "DeKalb County"
    return None


def apply_size_guard(
    record: IllinoisILHMPCatalogRecord,
    *,
    allow_large_downloads: bool = False,
    max_default_download_size_mb: float = DEFAULT_MAX_DEFAULT_DOWNLOAD_SIZE_MB,
) -> tuple[str | None, tuple[str, ...]]:
    """Return fallback reason and warnings imposed by default download guards."""

    warnings: list[str] = list(record.warnings)
    size_mb = record.estimated_download_size_mb
    if (
        record.access_kind == "county_archive"
        and size_mb is not None
        and size_mb > max_default_download_size_mb
        and not allow_large_downloads
    ):
        warnings.extend(
            (
                f"size_guard=blocked_default_limit_{max_default_download_size_mb:g}_mb",
                "large_download_opt_in_required=True",
            )
        )
        return FALLBACK_LARGE_DOWNLOAD_BLOCKED, tuple(warnings)

    if record.access_kind in {"manual_viewer_or_service_limited", "county_archive"}:
        warnings.append(f"fallback_reason={FALLBACK_MANUAL_OR_SERVICE_LIMITED}")
        return FALLBACK_MANUAL_OR_SERVICE_LIMITED, tuple(warnings)

    return None, tuple(warnings)


def catalog_record_to_candidate(
    record: IllinoisILHMPCatalogRecord,
    *,
    aoi: SourceAOI,
    context: IllinoisAOIContext | None = None,
    allow_large_downloads: bool = False,
    max_default_download_size_mb: float = DEFAULT_MAX_DEFAULT_DOWNLOAD_SIZE_MB,
) -> SourceCandidate:
    """Convert one Illinois catalog record into resolver candidate metadata."""

    resolved_context = context or discover_illinois_context(aoi)
    fallback_reason, warnings = apply_size_guard(
        record,
        allow_large_downloads=allow_large_downloads,
        max_default_download_size_mb=max_default_download_size_mb,
    )
    warning_list = list(warnings)
    warning_list.append(f"access_note={record.access_note}")
    warning_list.extend(resolved_context.notes)
    if resolved_context.county_contexts:
        warning_list.append("county_contexts=" + ",".join(resolved_context.county_contexts))

    coverage_score = 0.0
    if fallback_reason is None:
        coverage_score = _coverage_score(record.bbox_wgs84, aoi.bbox_wgs84)

    return SourceCandidate(
        adapter_id=ADAPTER_ILLINOIS_ILHMP,
        adapter_name="Illinois ILHMP/ISGS",
        source_name=_source_name_with_context(record, resolved_context),
        source_urls=record.source_urls,
        metadata_urls=record.metadata_urls,
        license=ILHMP_LICENSE,
        citation=ILHMP_CITATION,
        access_note=record.access_note,
        region_policy=REGION_POLICY_ILLINOIS,
        country_hints=("US",),
        region_hints=_merge_region_hints(record.region_hints, resolved_context),
        resolution_m=record.resolution_m,
        surface_type=record.surface_type,
        acquisition_date=record.acquisition_date,
        publication_date=record.publication_date,
        coverage_score=coverage_score,
        direct_no_auth=fallback_reason is None and record.access_kind in {"direct_geotiff", "image_service_export"},
        requires_auth=False,
        estimated_download_size_mb=record.estimated_download_size_mb,
        warnings=tuple(dict.fromkeys(warning_list)),
        fallback_reason=fallback_reason,
        source_id=record.source_id,
        bbox_wgs84=record.bbox_wgs84,
    )


def bbox_intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    """Return True when two WGS84 bounding boxes overlap."""

    west1, south1, east1, north1 = first
    west2, south2, east2, north2 = second
    if west1 > east1 or south1 > north1 or west2 > east2 or south2 > north2:
        raise ValueError("bbox_wgs84 must be ordered as west, south, east, north")
    return west1 <= east2 and east1 >= west2 and south1 <= north2 and north1 >= south2


def _record_applies_to_context(record: IllinoisILHMPCatalogRecord, context: IllinoisAOIContext) -> bool:
    hints = {hint.upper() for hint in record.region_hints}
    if "DEKALB COUNTY" in hints and "DeKalb County" not in context.county_contexts:
        return False
    return True


def _source_name_with_context(record: IllinoisILHMPCatalogRecord, context: IllinoisAOIContext) -> str:
    if context.county_contexts and "DeKalb County" in record.region_hints:
        return f"{record.source_name} ({', '.join(context.county_contexts)})"
    return record.source_name


def _merge_region_hints(record_hints: tuple[str, ...], context: IllinoisAOIContext) -> tuple[str, ...]:
    hints = list(record_hints)
    hints.extend(context.county_contexts)
    return tuple(dict.fromkeys(hints))


def _coverage_score(
    product_bbox: tuple[float, float, float, float] | None,
    aoi_bbox: tuple[float, float, float, float] | None,
) -> float:
    if not product_bbox:
        return 0.75 if aoi_bbox else 0.5
    if not aoi_bbox:
        return 0.5
    west = max(product_bbox[0], aoi_bbox[0])
    south = max(product_bbox[1], aoi_bbox[1])
    east = min(product_bbox[2], aoi_bbox[2])
    north = min(product_bbox[3], aoi_bbox[3])
    if west >= east or south >= north:
        return 0.0
    aoi_area = max((aoi_bbox[2] - aoi_bbox[0]) * (aoi_bbox[3] - aoi_bbox[1]), 0.0)
    if aoi_area <= 0:
        return 0.0
    overlap_area = (east - west) * (north - south)
    return max(0.0, min(1.0, overlap_area / aoi_area))


__all__ = [
    "DEFAULT_ILLINOIS_ILHMP_CATALOG",
    "DEFAULT_MAX_DEFAULT_DOWNLOAD_SIZE_MB",
    "DEKALB_COUNTY_CONTEXT_BBOX_WGS84",
    "FALLBACK_LARGE_DOWNLOAD_BLOCKED",
    "FALLBACK_MANUAL_OR_SERVICE_LIMITED",
    "ILLINOIS_BBOX_WGS84",
    "ILHMP_ACCESS_NOTE",
    "ILHMP_CITATION",
    "ILHMP_DATA_PAGE_LEGACY_URL",
    "ILHMP_DATA_PAGE_URL",
    "ILHMP_DERIVATIVES_URL",
    "ILHMP_ISGS_PROGRAM_URL",
    "ILHMP_LICENSE",
    "ILHMP_TERMS_URL",
    "IllinoisAOIContext",
    "IllinoisILHMPAdapter",
    "IllinoisILHMPCatalogRecord",
    "apply_size_guard",
    "bbox_intersects",
    "catalog_record_to_candidate",
    "discover_illinois_context",
    "estimate_county_context",
]
