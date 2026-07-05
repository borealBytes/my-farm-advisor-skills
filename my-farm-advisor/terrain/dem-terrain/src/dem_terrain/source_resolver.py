"""Source resolver interfaces and deterministic DEM candidate ranking.

This module is intentionally stdlib-only and import-safe. It defines the
interfaces, data records, adapter classes, and source-selection
policy. It does not prepare, cache, or write DEM rasters; provider discovery
returns metadata references unless an explicit adapter later downloads runtime assets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Protocol


SURFACE_DTM = "DTM"
SURFACE_DEM = "DEM"
SURFACE_DSM = "DSM"
SURFACE_UNKNOWN = "unknown"
SURFACE_TYPES = (SURFACE_DTM, SURFACE_DEM, SURFACE_DSM, SURFACE_UNKNOWN)

REGION_POLICY_US = "us"
REGION_POLICY_ILLINOIS = "illinois"
REGION_POLICY_NATIONAL = "national"
REGION_POLICY_REGIONAL = "regional"
REGION_POLICY_GLOBAL = "global"
REGION_POLICY_UNKNOWN = "unknown"

ADAPTER_USGS_TNM = "usgs_tnm_3dep"
ADAPTER_ILLINOIS_ILHMP = "illinois_ilhmp_isgs"
ADAPTER_NASADEM = "nasadem"
ADAPTER_COPERNICUS_GLO30 = "copernicus_glo30"
ADAPTER_ALOS_AW3D30 = "alos_aw3d30"
ADAPTER_SRTM_COMPATIBLE = "srtm_compatible"
ADAPTER_OPENTOPOGRAPHY = "opentopography"
ADAPTER_REGISTERED_REGIONAL = "registered_regional"

DSM_FALLBACK_WARNING = (
    "DSM fallback selected; elevations may include vegetation, buildings, or "
    "other above-ground objects and must not be represented as bare-earth DTM."
)
COARSE_FALLBACK_WARNING = (
    "Only coarse DEM coverage was selected; field-level terrain derivatives "
    "should be interpreted with reduced spatial confidence."
)


@dataclass(frozen=True, slots=True)
class SourceAOI:
    """Minimal AOI hints used by ranking without requiring geospatial packages."""

    country: str | None = None
    region: str | None = None
    intersects_illinois: bool = False
    bbox_wgs84: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """Candidate DEM source metadata used for ranking and provenance."""

    adapter_id: str
    adapter_name: str
    source_name: str
    source_urls: tuple[str, ...]
    metadata_urls: tuple[str, ...] = ()
    license: str = "unknown"
    citation: str = ""
    region_policy: str = REGION_POLICY_UNKNOWN
    country_hints: tuple[str, ...] = ()
    region_hints: tuple[str, ...] = ()
    resolution_m: float | None = None
    surface_type: str = SURFACE_UNKNOWN
    acquisition_date: str | None = None
    publication_date: str | None = None
    coverage_score: float = 0.0
    direct_no_auth: bool = False
    requires_auth: bool = False
    estimated_download_size_mb: float | None = None
    warnings: tuple[str, ...] = ()
    fallback_reason: str | None = None
    source_id: str | None = None
    bbox_wgs84: tuple[float, float, float, float] | None = None
    access_note: str = ""

    def provenance(self) -> "SourceProvenance":
        """Return the source-reference subset expected in downstream manifests."""

        return SourceProvenance(
            adapter_id=self.adapter_id,
            adapter_name=self.adapter_name,
            source_name=self.source_name,
            source_urls=self.source_urls,
            metadata_urls=self.metadata_urls,
            license=self.license,
            citation=self.citation,
            region_policy=self.region_policy,
            country_hints=self.country_hints,
            region_hints=self.region_hints,
            resolution_m=self.resolution_m,
            surface_type=self.surface_type,
            acquisition_date=self.acquisition_date,
            publication_date=self.publication_date,
            coverage_score=self.coverage_score,
            direct_no_auth=self.direct_no_auth,
            requires_auth=self.requires_auth,
            estimated_download_size_mb=self.estimated_download_size_mb,
            warnings=self.warnings,
            fallback_reason=self.fallback_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Serializable source provenance for selected and candidate sources."""

    adapter_id: str
    adapter_name: str
    source_name: str
    source_urls: tuple[str, ...]
    metadata_urls: tuple[str, ...]
    license: str
    citation: str
    region_policy: str
    country_hints: tuple[str, ...]
    region_hints: tuple[str, ...]
    resolution_m: float | None
    surface_type: str
    acquisition_date: str | None
    publication_date: str | None
    coverage_score: float
    direct_no_auth: bool
    requires_auth: bool
    estimated_download_size_mb: float | None
    warnings: tuple[str, ...]
    fallback_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceRankingPolicy:
    """Configuration switches for deterministic resolver behavior."""

    opentopography_enabled: bool = False
    coarse_warning_resolution_m: float = 30.0
    minimum_coverage_score: float = 0.0


@dataclass(frozen=True, slots=True)
class SourceSelection:
    """Selected candidate plus ranked alternatives and quality warnings."""

    selected: SourceCandidate
    ranked_candidates: tuple[SourceCandidate, ...]
    quality_warning: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for smoke evidence."""

        return {
            "selected": self.selected.to_dict(),
            "ranked_candidates": [candidate.to_dict() for candidate in self.ranked_candidates],
            "quality_warning": self.quality_warning,
            "warnings": self.warnings,
        }


class NoRasterSourceError(ValueError):
    """Raised only when no raster candidate can cover the AOI."""


class SourceAdapterProtocol(Protocol):
    """Interface implemented by future concrete DEM source adapters."""

    adapter_id: str
    adapter_name: str

    def discover(self, aoi: SourceAOI) -> tuple[SourceCandidate, ...]:
        """Discover candidate source records for an AOI without preparing rasters."""
        ...

    def rank(
        self,
        candidates: Iterable[SourceCandidate],
        *,
        aoi: SourceAOI | None = None,
        policy: SourceRankingPolicy | None = None,
    ) -> tuple[SourceCandidate, ...]:
        """Return candidates ordered by the shared resolver policy."""
        ...

    def download(self, candidate: SourceCandidate, cache: str | Path) -> Path:
        """Download a selected candidate into a runtime cache."""
        ...

    def prepare(self, candidate: SourceCandidate) -> Path:
        """Prepare a downloaded candidate for downstream raster processing."""
        ...

    def provenance(self, candidate: SourceCandidate) -> SourceProvenance:
        """Return provenance metadata for the selected candidate."""
        ...


class SourceAdapter:
    """Import-safe base class for placeholder provider adapters."""

    adapter_id = "source_adapter"
    adapter_name = "Source adapter"

    def discover(self, aoi: SourceAOI) -> tuple[SourceCandidate, ...]:
        raise NotImplementedError("Provider discovery is implemented in later adapter tasks.")

    def rank(
        self,
        candidates: Iterable[SourceCandidate],
        *,
        aoi: SourceAOI | None = None,
        policy: SourceRankingPolicy | None = None,
    ) -> tuple[SourceCandidate, ...]:
        return rank_candidates(candidates, aoi=aoi, policy=policy)

    def download(self, candidate: SourceCandidate, cache: str | Path) -> Path:
        raise NotImplementedError("Provider download is implemented in later adapter tasks.")

    def prepare(self, candidate: SourceCandidate) -> Path:
        raise NotImplementedError("Raster preparation is implemented in later adapter tasks.")

    def provenance(self, candidate: SourceCandidate) -> SourceProvenance:
        return candidate.provenance()


from .usgs_tnm import USGSTNMAdapter
from .illinois_ilhmp import IllinoisILHMPAdapter
from .global_adapters import ALOSAW3D30Adapter, CopernicusGLO30Adapter, NASADEMAdapter


class RegisteredRegionalAdapter(SourceAdapter):
    """Placeholder for configured national or regional providers."""

    adapter_id = ADAPTER_REGISTERED_REGIONAL
    adapter_name = "Registered national/regional DEM provider"



class SRTMCompatibleAdapter(SourceAdapter):
    """Placeholder for SRTM-compatible fallback source discovery."""

    adapter_id = ADAPTER_SRTM_COMPATIBLE
    adapter_name = "SRTM-compatible fallback"


class OpenTopographyAdapter(SourceAdapter):
    """Placeholder for optional configured OpenTopography source discovery."""

    adapter_id = ADAPTER_OPENTOPOGRAPHY
    adapter_name = "OpenTopography optional source"


ADAPTER_CLASSES = (
    USGSTNMAdapter,
    IllinoisILHMPAdapter,
    RegisteredRegionalAdapter,
    NASADEMAdapter,
    CopernicusGLO30Adapter,
    ALOSAW3D30Adapter,
    SRTMCompatibleAdapter,
    OpenTopographyAdapter,
)


def instantiate_default_adapters() -> tuple[SourceAdapter, ...]:
    """Instantiate all default adapters without network or credentials."""

    return tuple(adapter_class() for adapter_class in ADAPTER_CLASSES)


def rank_candidates(
    candidates: Iterable[SourceCandidate],
    *,
    aoi: SourceAOI | None = None,
    policy: SourceRankingPolicy | None = None,
) -> tuple[SourceCandidate, ...]:
    """Rank candidates deterministically without provider I/O.

    Ordering preserves the plan policy: valid coverage first, then bare-earth or
    DEM surfaces over DSM, finer resolution, configured source precedence,
    newest acquisition/publication date, direct no-auth root sources, smaller
    estimated downloads, and finally coverage score as a deterministic tie-break.
    """

    resolved_policy = policy or SourceRankingPolicy()
    allowed = [candidate for candidate in candidates if _candidate_allowed(candidate, resolved_policy)]
    return tuple(sorted(allowed, key=lambda candidate: _ranking_key(candidate, aoi, resolved_policy)))


def select_best_candidate(
    candidates: Iterable[SourceCandidate],
    *,
    aoi: SourceAOI | None = None,
    policy: SourceRankingPolicy | None = None,
) -> SourceSelection:
    """Select the best raster candidate or raise only when no source covers AOI."""

    resolved_policy = policy or SourceRankingPolicy()
    ranked = rank_candidates(candidates, aoi=aoi, policy=resolved_policy)
    covered = tuple(
        candidate
        for candidate in ranked
        if candidate.coverage_score > resolved_policy.minimum_coverage_score
    )
    if not covered:
        raise NoRasterSourceError("No raster source candidate can cover the AOI.")

    selected = _with_selection_warnings(covered[0], resolved_policy)
    warnings = selected.warnings
    quality_warning = _quality_warning(selected, resolved_policy)
    return SourceSelection(
        selected=selected,
        ranked_candidates=ranked,
        quality_warning=quality_warning,
        warnings=warnings,
    )


def candidate_provenance(candidate: SourceCandidate) -> SourceProvenance:
    """Return provenance metadata for a candidate."""

    return candidate.provenance()


def _candidate_allowed(candidate: SourceCandidate, policy: SourceRankingPolicy) -> bool:
    if candidate.adapter_id == ADAPTER_OPENTOPOGRAPHY and not policy.opentopography_enabled:
        return False
    return True


def _ranking_key(
    candidate: SourceCandidate,
    aoi: SourceAOI | None,
    policy: SourceRankingPolicy,
) -> tuple[Any, ...]:
    coverage_valid = candidate.coverage_score > policy.minimum_coverage_score
    return (
        0 if coverage_valid else 1,
        _surface_rank(candidate.surface_type),
        _resolution_rank(candidate.resolution_m),
        _source_precedence(candidate, aoi),
        -_date_rank(candidate.acquisition_date, candidate.publication_date),
        0 if candidate.direct_no_auth and not candidate.requires_auth else 1,
        _size_rank(candidate.estimated_download_size_mb),
        -candidate.coverage_score,
        candidate.adapter_id,
        candidate.source_name,
    )


def _surface_rank(surface_type: str) -> int:
    if surface_type == SURFACE_DTM:
        return 0
    if surface_type == SURFACE_DEM:
        return 1
    if surface_type == SURFACE_DSM:
        return 2
    return 3


def _resolution_rank(resolution_m: float | None) -> float:
    if resolution_m is None or resolution_m <= 0:
        return float("inf")
    return resolution_m


def _date_rank(acquisition_date: str | None, publication_date: str | None) -> int:
    best = max((_date_ordinal(acquisition_date), _date_ordinal(publication_date)))
    return best


def _date_ordinal(value: str | None) -> int:
    if not value:
        return 0
    try:
        return date.fromisoformat(value[:10]).toordinal()
    except ValueError:
        return 0


def _size_rank(size_mb: float | None) -> float:
    if size_mb is None or size_mb < 0:
        return float("inf")
    return size_mb


def _source_precedence(candidate: SourceCandidate, aoi: SourceAOI | None) -> int:
    if _is_us_candidate(candidate, aoi):
        return _us_source_precedence(candidate, aoi)
    return _global_source_precedence(candidate)


def _is_us_candidate(candidate: SourceCandidate, aoi: SourceAOI | None) -> bool:
    country_hints = {country.upper() for country in candidate.country_hints}
    if "US" in country_hints or "USA" in country_hints or "UNITED STATES" in country_hints:
        return True
    if candidate.region_policy in {REGION_POLICY_US, REGION_POLICY_ILLINOIS}:
        return True
    return bool(aoi and aoi.country and aoi.country.upper() in {"US", "USA", "UNITED STATES"})


def _us_source_precedence(candidate: SourceCandidate, aoi: SourceAOI | None) -> int:
    resolution = _resolution_rank(candidate.resolution_m)
    if candidate.adapter_id == ADAPTER_USGS_TNM and resolution <= 1.5:
        return 0
    if candidate.adapter_id == ADAPTER_ILLINOIS_ILHMP and _candidate_intersects_illinois(candidate, aoi):
        return 0
    if candidate.adapter_id == ADAPTER_USGS_TNM and resolution <= 10.5:
        return 2
    if candidate.adapter_id == ADAPTER_USGS_TNM and resolution <= 30.5:
        return 3
    if candidate.adapter_id == ADAPTER_OPENTOPOGRAPHY:
        return 4
    if candidate.region_policy in {REGION_POLICY_NATIONAL, REGION_POLICY_REGIONAL}:
        return 5
    return 20


def _candidate_intersects_illinois(candidate: SourceCandidate, aoi: SourceAOI | None) -> bool:
    region_hints = {region.upper() for region in candidate.region_hints}
    if "IL" in region_hints or "ILLINOIS" in region_hints:
        return True
    return bool(aoi and (aoi.intersects_illinois or (aoi.region or "").upper() in {"IL", "ILLINOIS"}))


def _global_source_precedence(candidate: SourceCandidate) -> int:
    if candidate.region_policy in {REGION_POLICY_NATIONAL, REGION_POLICY_REGIONAL}:
        return 10
    if candidate.adapter_id == ADAPTER_REGISTERED_REGIONAL:
        return 10
    if candidate.adapter_id == ADAPTER_NASADEM:
        return 11
    if candidate.adapter_id == ADAPTER_COPERNICUS_GLO30:
        return 12
    if candidate.adapter_id == ADAPTER_ALOS_AW3D30:
        return 13
    if candidate.adapter_id == ADAPTER_SRTM_COMPATIBLE:
        return 14
    if candidate.adapter_id == ADAPTER_OPENTOPOGRAPHY:
        return 15
    return 30


def _with_selection_warnings(candidate: SourceCandidate, policy: SourceRankingPolicy) -> SourceCandidate:
    warnings = list(candidate.warnings)
    fallback_reason = candidate.fallback_reason
    if candidate.surface_type == SURFACE_DSM and DSM_FALLBACK_WARNING not in warnings:
        warnings.append(DSM_FALLBACK_WARNING)
        fallback_reason = fallback_reason or "dsm_fallback"
    if (
        candidate.resolution_m is not None
        and candidate.resolution_m >= policy.coarse_warning_resolution_m
        and COARSE_FALLBACK_WARNING not in warnings
    ):
        warnings.append(COARSE_FALLBACK_WARNING)
        fallback_reason = fallback_reason or "coarse_resolution_fallback"
    return replace(candidate, warnings=tuple(warnings), fallback_reason=fallback_reason)


def _quality_warning(candidate: SourceCandidate, policy: SourceRankingPolicy) -> str | None:
    if candidate.surface_type == SURFACE_DSM:
        return DSM_FALLBACK_WARNING
    if candidate.resolution_m is not None and candidate.resolution_m >= policy.coarse_warning_resolution_m:
        return COARSE_FALLBACK_WARNING
    return None


__all__ = [
    "ADAPTER_ALOS_AW3D30",
    "ADAPTER_CLASSES",
    "ADAPTER_COPERNICUS_GLO30",
    "ADAPTER_ILLINOIS_ILHMP",
    "ADAPTER_NASADEM",
    "ADAPTER_OPENTOPOGRAPHY",
    "ADAPTER_REGISTERED_REGIONAL",
    "ADAPTER_SRTM_COMPATIBLE",
    "ADAPTER_USGS_TNM",
    "ALOSAW3D30Adapter",
    "COARSE_FALLBACK_WARNING",
    "CopernicusGLO30Adapter",
    "DSM_FALLBACK_WARNING",
    "IllinoisILHMPAdapter",
    "NASADEMAdapter",
    "NoRasterSourceError",
    "OpenTopographyAdapter",
    "REGION_POLICY_GLOBAL",
    "REGION_POLICY_ILLINOIS",
    "REGION_POLICY_NATIONAL",
    "REGION_POLICY_REGIONAL",
    "REGION_POLICY_UNKNOWN",
    "REGION_POLICY_US",
    "RegisteredRegionalAdapter",
    "SRTMCompatibleAdapter",
    "SURFACE_DEM",
    "SURFACE_DSM",
    "SURFACE_DTM",
    "SURFACE_TYPES",
    "SURFACE_UNKNOWN",
    "SourceAOI",
    "SourceAdapter",
    "SourceAdapterProtocol",
    "SourceCandidate",
    "SourceProvenance",
    "SourceRankingPolicy",
    "SourceSelection",
    "USGSTNMAdapter",
    "candidate_provenance",
    "instantiate_default_adapters",
    "rank_candidates",
    "select_best_candidate",
]
