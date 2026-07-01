"""Global DEM/DSM adapter metadata for NASADEM, Copernicus GLO-30, and ALOS AW3D30.

The adapters in this module are stdlib-only and import-safe. Default discovery
uses deterministic AOI tile/STAC references and does not perform network I/O,
create cache directories, or download raster assets. Callers that need live STAC
metadata can inject JSON payloads or an explicit fetch_json callable.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .source_resolver import (
    ADAPTER_ALOS_AW3D30,
    ADAPTER_COPERNICUS_GLO30,
    ADAPTER_NASADEM,
    DSM_FALLBACK_WARNING,
    REGION_POLICY_GLOBAL,
    SURFACE_DEM,
    SURFACE_DSM,
    SourceAOI,
    SourceAdapter,
    SourceCandidate,
)


PLANETARY_COMPUTER_STAC_ROOT = "https://planetarycomputer.microsoft.com/api/stac/v1"
NASADEM_COLLECTION_URL = f"{PLANETARY_COMPUTER_STAC_ROOT}/collections/nasadem"
NASADEM_ITEMS_URL = f"{NASADEM_COLLECTION_URL}/items"
NASADEM_DATASET_URL = "https://planetarycomputer.microsoft.com/dataset/nasadem"
NASADEM_EARTHDATA_CATALOG_URL = "https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001"
NASADEM_LPDAAC_URL = "https://lpdaac.usgs.gov/products/nasadem_hgtv001/"
NASADEM_LICENSE_URL = "https://lpdaac.usgs.gov/data/data-citation-and-policies/"
NASADEM_COG_ROOT = "https://nasademeuwest.blob.core.windows.net/nasadem-cog/v001"

COPERNICUS_GLO30_README_URL = "https://copernicus-dem-30m.s3.amazonaws.com/readme.html"
COPERNICUS_GLO30_BUCKET_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
COPERNICUS_GLO30_TILE_LIST_URL = "https://copernicus-dem-30m.s3.amazonaws.com/tileList.txt"
COPERNICUS_GLO30_GRID_URL = "https://copernicus-dem-30m.s3.amazonaws.com/grid.zip"
COPERNICUS_GLO30_DATASPACE_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/"
    "copernicus-contributing-missions/collections-description/COP-DEM"
)
COPERNICUS_GLO30_LICENSE_URL = (
    "https://spacedata.copernicus.eu/en/web/guest/collections/"
    "copernicus-digital-elevation-model/"
)

ALOS_COLLECTION_URL = f"{PLANETARY_COMPUTER_STAC_ROOT}/collections/alos-dem"
ALOS_ITEMS_URL = f"{ALOS_COLLECTION_URL}/items"
ALOS_DATASET_URL = "https://planetarycomputer.microsoft.com/dataset/alos-dem"
ALOS_JAXA_URL = "https://www.eorc.jaxa.jp/ALOS/en/aw3d30/index.htm"
ALOS_PRODUCT_DESCRIPTION_URL = "https://www.eorc.jaxa.jp/ALOS/en/aw3d30/aw3d30v3.2_product_e_e1.2.pdf"
ALOS_LICENSE_URL = "https://earth.jaxa.jp/policy/en.html"
ALOS_COG_ROOT = "https://ai4edataeuwest.blob.core.windows.net/alos-dem/AW3D30_global"

GLOBAL_REQUEST_TIMEOUT_SECONDS = 30.0
GLOBAL_DEFAULT_RETRIES = 1
GLOBAL_DEFAULT_BACKOFF_SECONDS = 0.5
GLOBAL_MAX_DRY_RUN_TILES = 16
GLOBAL_30M_ACCESS_NOTE = (
    "Default discovery returns metadata and planned public asset references only; "
    "raster downloads must be explicitly performed later into an external runtime cache."
)
STAC_PLANNED_REFERENCE_WARNING = "planned_stac_asset_reference_no_download"
COG_PLANNED_REFERENCE_WARNING = "planned_cog_asset_reference_no_download"
COPERNICUS_PUBLIC_COVERAGE_WARNING = (
    "Copernicus GLO-30 Public has limited worldwide 30m coverage; verify tile presence "
    "against tileList.txt or provider metadata before operational download."
)

FetchJson = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class GlobalDEMAssetReference:
    """Planned or catalog-discovered global DEM/DSM asset reference."""

    source_id: str
    source_name: str
    source_url: str
    metadata_urls: tuple[str, ...]
    bbox_wgs84: tuple[float, float, float, float]
    resolution_m: float
    surface_type: str
    direct_no_auth: bool
    requires_auth: bool
    license: str
    citation: str
    acquisition_date: str | None = None
    publication_date: str | None = None
    estimated_download_size_mb: float | None = None
    warnings: tuple[str, ...] = ()
    access_note: str = GLOBAL_30M_ACCESS_NOTE

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


class _GlobalReferenceAdapter(SourceAdapter):
    """Shared behavior for global metadata-only adapters."""

    source_name: str
    metadata_urls: tuple[str, ...]
    license: str
    citation: str
    resolution_m = 30.0
    surface_type: str
    direct_no_auth = True
    requires_auth = False
    acquisition_date: str | None = None
    publication_date: str | None = None
    extra_warnings: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        stac_payload: Any | None = None,
        network_enabled: bool = False,
        retries: int = GLOBAL_DEFAULT_RETRIES,
        backoff_seconds: float = GLOBAL_DEFAULT_BACKOFF_SECONDS,
        timeout_seconds: float = GLOBAL_REQUEST_TIMEOUT_SECONDS,
        max_dry_run_tiles: int = GLOBAL_MAX_DRY_RUN_TILES,
    ) -> None:
        self.fetch_json = fetch_json
        self.stac_payload = stac_payload
        self.network_enabled = network_enabled
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.timeout_seconds = timeout_seconds
        self.max_dry_run_tiles = max(1, max_dry_run_tiles)
        self.last_errors: tuple[dict[str, Any], ...] = ()

    def discover(self, aoi: SourceAOI) -> tuple[SourceCandidate, ...]:
        """Discover global source metadata for an AOI without downloading rasters."""

        if not aoi.bbox_wgs84:
            reason = "SourceAOI.bbox_wgs84 is required for global DEM discovery"
            self.last_errors = (self._error_record(reason=reason, endpoint=self._query_url(None)),)
            return (self._error_candidate(aoi=aoi, reason=reason, endpoint=self._query_url(None)),)

        try:
            references = self._discover_references(aoi.bbox_wgs84)
        except Exception as exc:
            reason = _exception_reason(exc)
            endpoint = self._query_url(aoi.bbox_wgs84)
            self.last_errors = (self._error_record(reason=reason, endpoint=endpoint),)
            return (self._error_candidate(aoi=aoi, reason=reason, endpoint=endpoint),)

        self.last_errors = ()
        if not references:
            return ()
        return (self._references_to_candidate(references, aoi=aoi),)

    def download(self, candidate: SourceCandidate, cache: str | Path) -> Path:
        """Refuse default global raster downloads; later ingest tasks own downloads."""

        del cache
        raise NotImplementedError(
            f"{self.adapter_name} discovery returns metadata/asset references only; "
            "download must be an explicit later ingest step using a runtime cache outside the repository."
        )

    def prepare(self, candidate: SourceCandidate) -> Path:
        """Raster preparation is owned by later DEM terrain ingest tasks."""

        del candidate
        raise NotImplementedError(f"{self.adapter_name} raster preparation is implemented in a later raster task.")

    def _discover_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        payload = self.stac_payload
        if payload is None and (self.fetch_json or self.network_enabled):
            payload = self._fetch_json_with_retries(self._query_url(bbox_wgs84))
        if payload is not None:
            references = self._references_from_payload(payload, bbox_wgs84)
            if references:
                return references
        return self._planned_references(bbox_wgs84)

    def _query_url(self, bbox_wgs84: tuple[float, float, float, float] | None) -> str:
        return ""

    def _planned_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        raise NotImplementedError

    def _references_from_payload(
        self,
        payload: Any,
        aoi_bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        return ()

    def _reference_to_candidate_warnings(self, references: tuple[GlobalDEMAssetReference, ...]) -> tuple[str, ...]:
        warnings: list[str] = list(self.extra_warnings)
        for reference in references:
            warnings.extend(reference.warnings)
        if self.surface_type == SURFACE_DSM and DSM_FALLBACK_WARNING not in warnings:
            warnings.append(DSM_FALLBACK_WARNING)
        warnings.append("asset_count=" + str(len(references)))
        warnings.append("access_note=" + GLOBAL_30M_ACCESS_NOTE)
        return tuple(dict.fromkeys(warnings))

    def _references_to_candidate(
        self,
        references: tuple[GlobalDEMAssetReference, ...],
        *,
        aoi: SourceAOI,
    ) -> SourceCandidate:
        source_urls = tuple(reference.source_url for reference in references)
        metadata_urls = tuple(dict.fromkeys(url for reference in references for url in reference.metadata_urls))
        bbox = _union_bbox(tuple(reference.bbox_wgs84 for reference in references))
        source_id = ",".join(reference.source_id for reference in references[:3])
        if len(references) > 3:
            source_id = f"{source_id},+{len(references) - 3}_more"
        return SourceCandidate(
            adapter_id=self.adapter_id,
            adapter_name=self.adapter_name,
            source_name=self.source_name if len(references) == 1 else f"{self.source_name} ({len(references)} AOI tiles)",
            source_urls=source_urls,
            metadata_urls=metadata_urls,
            license=self.license,
            citation=self.citation,
            region_policy=REGION_POLICY_GLOBAL,
            country_hints=(),
            region_hints=(),
            resolution_m=self.resolution_m,
            surface_type=self.surface_type,
            acquisition_date=self.acquisition_date,
            publication_date=self.publication_date,
            coverage_score=_coverage_score(bbox, aoi.bbox_wgs84),
            direct_no_auth=self.direct_no_auth,
            requires_auth=self.requires_auth,
            estimated_download_size_mb=_sum_known_sizes(references),
            warnings=self._reference_to_candidate_warnings(references),
            fallback_reason="dsm_fallback" if self.surface_type == SURFACE_DSM else None,
            source_id=source_id,
            bbox_wgs84=bbox,
            access_note=GLOBAL_30M_ACCESS_NOTE,
        )

    def _fetch_json_with_retries(self, url: str) -> Any:
        fetcher = self.fetch_json or (lambda request_url: _http_get_json(request_url, self.timeout_seconds))
        attempts = self.retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return fetcher(url)
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(self.backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    def _error_record(self, *, reason: str, endpoint: str) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "endpoint": endpoint,
            "reason": reason,
            "retries": self.retries,
        }

    def _error_candidate(self, *, aoi: SourceAOI, reason: str, endpoint: str) -> SourceCandidate:
        return SourceCandidate(
            adapter_id=self.adapter_id,
            adapter_name=self.adapter_name,
            source_name=f"{self.adapter_name} adapter error",
            source_urls=(endpoint,) if endpoint else (),
            metadata_urls=self.metadata_urls,
            license=self.license,
            citation=self.citation,
            region_policy=REGION_POLICY_GLOBAL,
            resolution_m=self.resolution_m,
            surface_type=self.surface_type,
            coverage_score=0.0,
            direct_no_auth=False,
            requires_auth=self.requires_auth,
            warnings=(f"adapter_error={reason}",),
            fallback_reason=f"adapter_error: {reason}",
            bbox_wgs84=aoi.bbox_wgs84,
            access_note=GLOBAL_30M_ACCESS_NOTE,
        )


class _PlanetaryComputerSTACAdapter(_GlobalReferenceAdapter):
    """Shared Planetary Computer STAC reference parsing."""

    items_url: str
    asset_key: str

    def _query_url(self, bbox_wgs84: tuple[float, float, float, float] | None) -> str:
        if not bbox_wgs84:
            return self.items_url
        params = {"bbox": _format_bbox(bbox_wgs84), "limit": str(self.max_dry_run_tiles)}
        return f"{self.items_url}?{urlencode(params)}"

    def _references_from_payload(
        self,
        payload: Any,
        aoi_bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        references: list[GlobalDEMAssetReference] = []
        for feature in _iter_stac_features(payload):
            reference = self._reference_from_stac_feature(feature, aoi_bbox_wgs84)
            if reference:
                references.append(reference)
        return tuple(references)

    def _reference_from_stac_feature(
        self,
        feature: dict[str, Any],
        aoi_bbox_wgs84: tuple[float, float, float, float],
    ) -> GlobalDEMAssetReference | None:
        assets = feature.get("assets")
        if not isinstance(assets, dict):
            return None
        asset = assets.get(self.asset_key)
        if not isinstance(asset, dict):
            return None
        href = asset.get("href")
        if not isinstance(href, str) or not href:
            return None
        bbox = _bbox_from_value(feature.get("bbox")) or _bbox_from_geometry(feature.get("geometry"))
        if not bbox or _coverage_score(bbox, aoi_bbox_wgs84) <= 0.0:
            return None
        item_id = str(feature.get("id") or href.rsplit("/", 1)[-1])
        metadata_urls = list(self.metadata_urls)
        for link in feature.get("links") or ():
            if isinstance(link, dict):
                href_value = link.get("href")
                if isinstance(href_value, str) and link.get("rel") in {"self", "collection", "license", "describedby", "handbook"}:
                    metadata_urls.append(href_value)
        return GlobalDEMAssetReference(
            source_id=item_id,
            source_name=f"{self.source_name} {item_id}",
            source_url=href,
            metadata_urls=tuple(dict.fromkeys(metadata_urls)),
            bbox_wgs84=bbox,
            resolution_m=self.resolution_m,
            surface_type=self.surface_type,
            direct_no_auth=True,
            requires_auth=False,
            license=self.license,
            citation=self.citation,
            acquisition_date=_stac_date(feature),
            publication_date=self.publication_date,
            warnings=(STAC_PLANNED_REFERENCE_WARNING,),
            access_note=GLOBAL_30M_ACCESS_NOTE,
        )


class NASADEMAdapter(_PlanetaryComputerSTACAdapter):
    """NASADEM HGT global 1 arc-second DEM adapter using STAC/COG references."""

    adapter_id = ADAPTER_NASADEM
    adapter_name = "NASADEM"
    source_name = "NASADEM HGT v001 global 1 arc-second DEM"
    items_url = NASADEM_ITEMS_URL
    asset_key = "elevation"
    metadata_urls = (
        NASADEM_COLLECTION_URL,
        NASADEM_DATASET_URL,
        NASADEM_EARTHDATA_CATALOG_URL,
        NASADEM_LPDAAC_URL,
        NASADEM_LICENSE_URL,
    )
    license = "Public domain / NASA LP DAAC data citation and policies; verify current provider terms."
    citation = "NASA JPL, NASADEM HGT v001, distributed by NASA LP DAAC and hosted as COG/STAC by Microsoft Planetary Computer."
    surface_type = SURFACE_DEM
    acquisition_date = "2000-02-20"

    def _planned_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        references: list[GlobalDEMAssetReference] = []
        for lat, lon in _iter_degree_tiles(bbox_wgs84, max_tiles=self.max_dry_run_tiles):
            if lat < -56 or lat > 60 or lon < -179 or lon > 179:
                continue
            references.append(build_nasadem_tile_reference(lat, lon))
        return tuple(references)


class CopernicusGLO30Adapter(_GlobalReferenceAdapter):
    """Copernicus GLO-30 Public DSM adapter using documented public COG tile names."""

    adapter_id = ADAPTER_COPERNICUS_GLO30
    adapter_name = "Copernicus GLO-30 DSM"
    source_name = "Copernicus DEM GLO-30 Public DSM COG"
    metadata_urls = (
        COPERNICUS_GLO30_README_URL,
        COPERNICUS_GLO30_TILE_LIST_URL,
        COPERNICUS_GLO30_GRID_URL,
        COPERNICUS_GLO30_DATASPACE_URL,
        COPERNICUS_GLO30_LICENSE_URL,
    )
    license = "Copernicus DEM GLO-30 Public free basis license; verify current Copernicus Programme terms."
    citation = "Copernicus DEM GLO-30 Public DSM, derived from COP-DEM_GLO-30-DGED and published as public COGs on AWS."
    surface_type = SURFACE_DSM
    acquisition_date = "2011-01-01"
    extra_warnings = (COPERNICUS_PUBLIC_COVERAGE_WARNING,)

    def _planned_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        return tuple(
            build_copernicus_glo30_tile_reference(lat, lon)
            for lat, lon in _iter_degree_tiles(bbox_wgs84, max_tiles=self.max_dry_run_tiles)
            if -90 <= lat <= 89 and -180 <= lon <= 179
        )

    def _discover_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        # Copernicus GLO-30 public COG access is documented by deterministic S3 tile names.
        # Optional tileList verification can be added later without changing this dry-run contract.
        return self._planned_references(bbox_wgs84)


class ALOSAW3D30Adapter(_PlanetaryComputerSTACAdapter):
    """ALOS AW3D30 global DSM adapter using Planetary Computer STAC/COG references."""

    adapter_id = ADAPTER_ALOS_AW3D30
    adapter_name = "ALOS AW3D30 DSM"
    source_name = "ALOS World 3D-30m AW3D30 DSM"
    items_url = ALOS_ITEMS_URL
    asset_key = "data"
    metadata_urls = (
        ALOS_COLLECTION_URL,
        ALOS_DATASET_URL,
        ALOS_JAXA_URL,
        ALOS_PRODUCT_DESCRIPTION_URL,
        ALOS_LICENSE_URL,
    )
    license = "JAXA Terms of Use of Research Data; verify current AW3D30 terms before operational use."
    citation = "Japan Aerospace Exploration Agency (JAXA), ALOS World 3D-30m (AW3D30) global DSM, hosted as STAC/COG by Microsoft Planetary Computer."
    surface_type = SURFACE_DSM
    acquisition_date = "2016-12-07"

    def _planned_references(
        self,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> tuple[GlobalDEMAssetReference, ...]:
        return tuple(
            build_alos_aw3d30_tile_reference(lat, lon)
            for lat, lon in _iter_degree_tiles(bbox_wgs84, max_tiles=self.max_dry_run_tiles)
            if -90 <= lat <= 89 and -180 <= lon <= 179
        )


def build_nasadem_tile_reference(lat: int, lon: int) -> GlobalDEMAssetReference:
    """Build a NASADEM Planetary Computer COG reference for one 1x1 degree tile."""

    tile_id = f"NASADEM_HGT_{_signed_tile(lat, lon, lower=True)}"
    return GlobalDEMAssetReference(
        source_id=tile_id,
        source_name=f"NASADEM HGT v001 {tile_id}",
        source_url=f"{NASADEM_COG_ROOT}/{tile_id}.tif",
        metadata_urls=(NASADEM_COLLECTION_URL, NASADEM_ITEMS_URL, NASADEM_LPDAAC_URL, NASADEM_LICENSE_URL),
        bbox_wgs84=_tile_bbox(lat, lon, pad=0.000139),
        resolution_m=30.0,
        surface_type=SURFACE_DEM,
        direct_no_auth=True,
        requires_auth=False,
        license=NASADEMAdapter.license,
        citation=NASADEMAdapter.citation,
        acquisition_date=NASADEMAdapter.acquisition_date,
        warnings=(STAC_PLANNED_REFERENCE_WARNING,),
    )


def build_copernicus_glo30_tile_reference(lat: int, lon: int) -> GlobalDEMAssetReference:
    """Build a Copernicus GLO-30 Public COG reference for one 1x1 degree tile."""

    tile = f"Copernicus_DSM_COG_10_{_hemisphere(lat, 'N', 'S')}{abs(lat):02d}_00_{_hemisphere(lon, 'E', 'W')}{abs(lon):03d}_00_DEM"
    return GlobalDEMAssetReference(
        source_id=tile,
        source_name=f"Copernicus DEM GLO-30 Public {tile}",
        source_url=f"{COPERNICUS_GLO30_BUCKET_URL}/{tile}/{tile}.tif",
        metadata_urls=(COPERNICUS_GLO30_README_URL, COPERNICUS_GLO30_TILE_LIST_URL, COPERNICUS_GLO30_DATASPACE_URL),
        bbox_wgs84=_tile_bbox(lat, lon),
        resolution_m=30.0,
        surface_type=SURFACE_DSM,
        direct_no_auth=True,
        requires_auth=False,
        license=CopernicusGLO30Adapter.license,
        citation=CopernicusGLO30Adapter.citation,
        acquisition_date=CopernicusGLO30Adapter.acquisition_date,
        estimated_download_size_mb=None,
        warnings=(COG_PLANNED_REFERENCE_WARNING, DSM_FALLBACK_WARNING, COPERNICUS_PUBLIC_COVERAGE_WARNING),
    )


def build_alos_aw3d30_tile_reference(lat: int, lon: int) -> GlobalDEMAssetReference:
    """Build an ALOS AW3D30 Planetary Computer COG reference for one 1x1 degree tile."""

    tile_id = f"ALPSMLC30_{_hemisphere(lat, 'N', 'S')}{abs(lat):03d}{_hemisphere(lon, 'E', 'W')}{abs(lon):03d}_DSM"
    return GlobalDEMAssetReference(
        source_id=tile_id,
        source_name=f"ALOS World 3D-30m AW3D30 {tile_id}",
        source_url=f"{ALOS_COG_ROOT}/{tile_id}.tif",
        metadata_urls=(ALOS_COLLECTION_URL, ALOS_ITEMS_URL, ALOS_JAXA_URL, ALOS_LICENSE_URL),
        bbox_wgs84=_tile_bbox(lat, lon),
        resolution_m=30.0,
        surface_type=SURFACE_DSM,
        direct_no_auth=True,
        requires_auth=False,
        license=ALOSAW3D30Adapter.license,
        citation=ALOSAW3D30Adapter.citation,
        acquisition_date=ALOSAW3D30Adapter.acquisition_date,
        warnings=(STAC_PLANNED_REFERENCE_WARNING, DSM_FALLBACK_WARNING),
    )


def build_stac_items_url(
    items_url: str,
    bbox_wgs84: tuple[float, float, float, float],
    *,
    limit: int = GLOBAL_MAX_DRY_RUN_TILES,
) -> str:
    """Build a metadata-only STAC items URL for an AOI bbox."""

    _validate_bbox(bbox_wgs84)
    params = {"bbox": _format_bbox(bbox_wgs84), "limit": str(max(1, limit))}
    return f"{items_url}?{urlencode(params)}"


def _iter_degree_tiles(
    bbox_wgs84: tuple[float, float, float, float],
    *,
    max_tiles: int,
) -> Iterable[tuple[int, int]]:
    west, south, east, north = _validate_bbox(bbox_wgs84)
    lon_start = math.floor(west)
    lon_stop = math.ceil(east)
    lat_start = math.floor(south)
    lat_stop = math.ceil(north)
    count = 0
    for lat in range(lat_start, lat_stop):
        for lon in range(lon_start, lon_stop):
            if count >= max_tiles:
                return
            count += 1
            yield lat, lon


def _validate_bbox(bbox_wgs84: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bbox_wgs84
    if west >= east or south >= north:
        raise ValueError("bbox_wgs84 must be ordered as west, south, east, north with non-zero area")
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise ValueError("bbox_wgs84 must be within WGS84 longitude/latitude bounds")
    return west, south, east, north


def _tile_bbox(lat: int, lon: int, *, pad: float = 0.0) -> tuple[float, float, float, float]:
    return (lon - pad, lat - pad, lon + 1 + pad, lat + 1 + pad)


def _signed_tile(lat: int, lon: int, *, lower: bool) -> str:
    ns = _hemisphere(lat, "N", "S")
    ew = _hemisphere(lon, "E", "W")
    value = f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"
    return value.lower() if lower else value


def _hemisphere(value: int, positive: str, negative: str) -> str:
    return positive if value >= 0 else negative


def _format_bbox(bbox_wgs84: tuple[float, float, float, float]) -> str:
    return ",".join(_format_coord(value) for value in bbox_wgs84)


def _format_coord(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _iter_stac_features(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict):
        features = payload.get("features")
        if isinstance(features, list):
            for feature in features:
                if isinstance(feature, dict):
                    yield feature
            return
        if payload.get("type") == "Feature":
            yield payload
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def _stac_date(feature: dict[str, Any]) -> str | None:
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return None
    value = properties.get("datetime") or properties.get("start_datetime")
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return None


def _bbox_from_geometry(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, dict):
        return None
    coords = value.get("coordinates")
    points: list[tuple[float, float]] = []

    def visit(node: Any) -> None:
        if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(part, (int, float)) for part in node[:2]):
            points.append((float(node[0]), float(node[1])))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                visit(child)

    visit(coords)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_from_value(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            return tuple(float(part) for part in value[:4])  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    return None


def _union_bbox(bboxes: tuple[tuple[float, float, float, float], ...]) -> tuple[float, float, float, float] | None:
    if not bboxes:
        return None
    return (
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    )


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


def _sum_known_sizes(references: tuple[GlobalDEMAssetReference, ...]) -> float | None:
    sizes = [reference.estimated_download_size_mb for reference in references]
    if not sizes or any(size is None for size in sizes):
        return None
    return sum(size for size in sizes if size is not None)


def _http_get_json(url: str, timeout_seconds: float) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "my-farm-advisor-dem-terrain/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, URLError):
        return f"URL error: {exc.reason}"
    return f"{exc.__class__.__name__}: {exc}"


__all__ = [
    "ALOS_COLLECTION_URL",
    "ALOS_ITEMS_URL",
    "ALOSAW3D30Adapter",
    "COPERNICUS_GLO30_BUCKET_URL",
    "COPERNICUS_GLO30_README_URL",
    "CopernicusGLO30Adapter",
    "GLOBAL_30M_ACCESS_NOTE",
    "GlobalDEMAssetReference",
    "NASADEM_COLLECTION_URL",
    "NASADEM_ITEMS_URL",
    "NASADEMAdapter",
    "PLANETARY_COMPUTER_STAC_ROOT",
    "build_alos_aw3d30_tile_reference",
    "build_copernicus_glo30_tile_reference",
    "build_nasadem_tile_reference",
    "build_stac_items_url",
]
