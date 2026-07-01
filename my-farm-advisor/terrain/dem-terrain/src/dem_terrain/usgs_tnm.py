"""USGS TNMAccess 3DEP DEM discovery and runtime-cache download helpers.

The adapter is intentionally stdlib-only and import-safe. Importing this module
does not read environment variables, create cache directories, or perform
network I/O. Discovery is separated from download so smoke tests can inject
mock TNMAccess JSON and runtime downloads only happen when explicitly called.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .source_resolver import (
    ADAPTER_USGS_TNM,
    REGION_POLICY_US,
    SURFACE_DEM,
    SourceAOI,
    SourceAdapter,
    SourceCandidate,
)


DEFAULT_TNM_PRODUCTS_ENDPOINT = "https://tnmaccess.nationalmap.gov/api/v1/products"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 0.5
DEFAULT_BBOX_BUFFER_DEGREES = 0.0005

TNM_DATASETS = (
    "Digital Elevation Model (DEM) 1 meter",
    "1/3 arc-second DEM",
    "1 arc-second DEM",
)

DATASET_RESOLUTION_METERS = {
    "Digital Elevation Model (DEM) 1 meter": 1.0,
    "1/3 arc-second DEM": 10.0,
    "1 arc-second DEM": 30.0,
}

USGS_TNM_LICENSE = "Public domain (USGS 3DEP)"
USGS_TNM_CITATION = "U.S. Geological Survey 3D Elevation Program (3DEP), The National Map."


FetchJson = Callable[[str], Any]
FetchBytes = Callable[[str], bytes]


@dataclass(frozen=True, slots=True)
class USGSTNMProduct:
    """Parsed subset of one TNMAccess DEM product."""

    dataset: str
    title: str
    source_id: str | None
    download_url: str
    metadata_url: str | None
    publication_date: str | None
    updated_date: str | None
    bbox_wgs84: tuple[float, float, float, float] | None
    resolution_m: float | None
    estimated_download_size_mb: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class USGSTNMDownloadRecord:
    """Runtime-cache download result with checksum and file size."""

    path: str
    url: str
    bytes: int
    sha256: str
    attempts: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


class USGSTNMAdapter(SourceAdapter):
    """USGS TNMAccess adapter for 3DEP 1m, 1/3 arc-second, and 1 arc-second DEMs."""

    adapter_id = ADAPTER_USGS_TNM
    adapter_name = "USGS TNM 3DEP"

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_TNM_PRODUCTS_ENDPOINT,
        fetch_json: FetchJson | None = None,
        network_enabled: bool = True,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        bbox_buffer_degrees: float = DEFAULT_BBOX_BUFFER_DEGREES,
    ) -> None:
        self.endpoint = endpoint
        self.fetch_json = fetch_json
        self.network_enabled = network_enabled
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.timeout_seconds = timeout_seconds
        self.bbox_buffer_degrees = max(0.0, bbox_buffer_degrees)
        self.last_errors: tuple[dict[str, Any], ...] = ()

    def discover(self, aoi: SourceAOI) -> tuple[SourceCandidate, ...]:
        """Discover USGS 3DEP DEM candidates for an AOI without downloading rasters."""

        if not aoi.bbox_wgs84:
            reason = "SourceAOI.bbox_wgs84 is required for TNMAccess products discovery"
            error = self._error_record(endpoint=self.endpoint, dataset=None, reason=reason)
            self.last_errors = (error,)
            return (self._error_candidate(aoi=aoi, endpoint=self.endpoint, reason=reason),)

        query_bbox = buffer_wgs84_bbox(aoi.bbox_wgs84, self.bbox_buffer_degrees)
        candidates: list[SourceCandidate] = []
        errors: list[dict[str, Any]] = []

        for dataset in TNM_DATASETS:
            url = build_tnm_products_url(self.endpoint, bbox_wgs84=query_bbox, dataset=dataset)
            if not self.network_enabled:
                reason = "network disabled for USGS TNMAccess discovery"
                errors.append(self._error_record(endpoint=url, dataset=dataset, reason=reason))
                candidates.append(self._error_candidate(aoi=aoi, endpoint=url, dataset=dataset, reason=reason))
                continue

            try:
                payload = self._fetch_json_with_retries(url)
            except Exception as exc:  # structured adapter error, not traceback
                reason = _exception_reason(exc)
                errors.append(self._error_record(endpoint=url, dataset=dataset, reason=reason))
                candidates.append(self._error_candidate(aoi=aoi, endpoint=url, dataset=dataset, reason=reason))
                continue

            candidates.extend(parse_tnm_products(payload, dataset=dataset, aoi_bbox_wgs84=aoi.bbox_wgs84))

        self.last_errors = tuple(errors)
        return tuple(candidates)

    def download(self, candidate: SourceCandidate, cache: str | Path) -> Path:
        """Download a selected direct GeoTIFF candidate into a runtime cache."""

        if not candidate.source_urls:
            raise ValueError("USGS TNM candidate has no source URL to download")
        record = download_with_retries(
            candidate.source_urls[0],
            cache,
            retries=self.retries,
            backoff_seconds=self.backoff_seconds,
        )
        return Path(record.path)

    def prepare(self, candidate: SourceCandidate) -> Path:
        """Raster mosaic/crop/conditioning is owned by later DEM terrain tasks."""

        raise NotImplementedError("USGS TNM raster preparation is implemented in a later raster task.")

    def _fetch_json_with_retries(self, url: str) -> Any:
        fetcher = self.fetch_json or (lambda request_url: _http_get_json(request_url, self.timeout_seconds))
        attempts = self.retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return fetcher(url)
            except Exception as exc:  # caller converts final failure into error candidate
                last_error = exc
                if attempt < attempts:
                    time.sleep(self.backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    def _error_record(
        self,
        *,
        endpoint: str,
        dataset: str | None,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "endpoint": endpoint,
            "dataset": dataset,
            "reason": reason,
            "retries": self.retries,
        }

    def _error_candidate(
        self,
        *,
        aoi: SourceAOI,
        endpoint: str,
        reason: str,
        dataset: str | None = None,
    ) -> SourceCandidate:
        source_name = self.adapter_name if dataset is None else f"{self.adapter_name} {dataset}"
        return SourceCandidate(
            adapter_id=self.adapter_id,
            adapter_name=self.adapter_name,
            source_name=f"{source_name} adapter error",
            source_urls=(endpoint,),
            metadata_urls=(),
            license=USGS_TNM_LICENSE,
            citation=USGS_TNM_CITATION,
            region_policy=REGION_POLICY_US,
            country_hints=("US",),
            region_hints=(),
            resolution_m=DATASET_RESOLUTION_METERS.get(dataset or ""),
            surface_type=SURFACE_DEM,
            coverage_score=0.0,
            direct_no_auth=False,
            requires_auth=False,
            warnings=(f"adapter_error={reason}", f"endpoint={endpoint}"),
            fallback_reason=f"adapter_error: {reason}",
            source_id=dataset,
            bbox_wgs84=aoi.bbox_wgs84,
        )


def buffer_wgs84_bbox(
    bbox_wgs84: tuple[float, float, float, float],
    buffer_degrees: float = DEFAULT_BBOX_BUFFER_DEGREES,
) -> tuple[float, float, float, float]:
    """Return a conservatively buffered WGS84 bbox clamped to world bounds."""

    west, south, east, north = bbox_wgs84
    if west > east or south > north:
        raise ValueError("bbox_wgs84 must be ordered as west, south, east, north")
    return (
        max(-180.0, west - buffer_degrees),
        max(-90.0, south - buffer_degrees),
        min(180.0, east + buffer_degrees),
        min(90.0, north + buffer_degrees),
    )


def build_tnm_products_url(
    endpoint: str = DEFAULT_TNM_PRODUCTS_ENDPOINT,
    *,
    bbox_wgs84: tuple[float, float, float, float],
    dataset: str,
    max_items: int = 100,
) -> str:
    """Build a TNMAccess products URL for one 3DEP dataset and WGS84 bbox."""

    bbox_value = ",".join(_format_coord(value) for value in bbox_wgs84)
    params = {
        "datasets": dataset,
        "bbox": bbox_value,
        "prodFormats": "GeoTIFF",
        "outputFormat": "JSON",
        "max": str(max_items),
    }
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{urlencode(params)}"


def parse_tnm_products(
    payload: Any,
    *,
    dataset: str | None = None,
    aoi_bbox_wgs84: tuple[float, float, float, float] | None = None,
) -> tuple[SourceCandidate, ...]:
    """Parse TNMAccess products JSON into SourceCandidate records."""

    records = tuple(_iter_product_records(payload))
    candidates: list[SourceCandidate] = []
    for record in records:
        product_dataset = _first_text(record, "dataset", "datasets", "sourceDataset", "productType") or dataset or "USGS 3DEP DEM"
        if dataset and product_dataset != dataset:
            product_dataset = dataset
        product = _parse_product_record(record, product_dataset)
        if product is None:
            continue
        candidates.append(_product_to_candidate(product, aoi_bbox_wgs84=aoi_bbox_wgs84))
    return tuple(candidates)


def download_with_retries(
    url: str,
    cache: str | Path,
    *,
    filename: str | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    fetch_bytes: FetchBytes | None = None,
) -> USGSTNMDownloadRecord:
    """Download a URL into a runtime cache atomically and return checksum metadata."""

    cache_path = Path(cache)
    target_name = filename or _filename_from_url(url)
    target_path = cache_path / target_name
    temp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.part")
    attempts = max(0, retries) + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            cache_path.mkdir(parents=True, exist_ok=True)
            data = fetch_bytes(url) if fetch_bytes else _http_get_bytes(url, timeout_seconds)
            with temp_path.open("wb") as handle:
                handle.write(data)
            os.replace(temp_path, target_path)
            return USGSTNMDownloadRecord(
                path=str(target_path),
                url=url,
                bytes=target_path.stat().st_size,
                sha256=sha256_file(target_path),
                attempts=attempt,
            )
        except Exception as exc:
            last_error = exc
            if temp_path.exists():
                temp_path.unlink()
            if attempt < attempts:
                time.sleep(max(0.0, backoff_seconds) * attempt)

    assert last_error is not None
    raise last_error


def sha256_file(path: str | Path) -> str:
    """Return a SHA256 checksum for a local file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _http_get_json(url: str, timeout_seconds: float) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "my-farm-advisor-dem-terrain/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_bytes(url: str, timeout_seconds: float) -> bytes:
    request = Request(url, headers={"User-Agent": "my-farm-advisor-dem-terrain/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _iter_product_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if not isinstance(payload, dict):
        return
    for key in ("items", "products", "results", "features"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if key == "features" and isinstance(item.get("properties"), dict):
                        merged = dict(item["properties"])
                        if "bbox" in item:
                            merged.setdefault("bbox", item["bbox"])
                        yield merged
                    else:
                        yield item


def _parse_product_record(record: dict[str, Any], dataset: str) -> USGSTNMProduct | None:
    download_url = _first_text(record, "downloadURL", "downloadUrl", "download_url", "url", "URL")
    if not download_url or not _looks_like_geotiff(record, download_url):
        return None

    title = _first_text(record, "title", "name", "productName") or dataset
    source_id = _first_text(record, "sourceId", "sourceID", "id", "identifier", "source_id")
    metadata_url = _first_text(record, "metadataUrl", "metadataURL", "metaUrl", "metaURL", "scienceBaseMetadataUrl")
    publication_date = _normalize_date(_first_text(record, "publicationDate", "published", "pubDate", "datePublished"))
    updated_date = _normalize_date(_first_text(record, "lastUpdated", "updated", "updateDate", "modified", "dateUpdated"))
    bbox_wgs84 = _parse_bbox(record)

    return USGSTNMProduct(
        dataset=dataset,
        title=title,
        source_id=source_id,
        download_url=download_url,
        metadata_url=metadata_url,
        publication_date=publication_date,
        updated_date=updated_date,
        bbox_wgs84=bbox_wgs84,
        resolution_m=_parse_resolution_m(record, dataset),
        estimated_download_size_mb=_parse_size_mb(record),
    )


def _product_to_candidate(
    product: USGSTNMProduct,
    *,
    aoi_bbox_wgs84: tuple[float, float, float, float] | None,
) -> SourceCandidate:
    name = product.title
    if product.source_id and product.source_id not in name:
        name = f"{name} [{product.source_id}]"
    metadata_urls = (product.metadata_url,) if product.metadata_url else ()
    return SourceCandidate(
        adapter_id=ADAPTER_USGS_TNM,
        adapter_name="USGS TNM 3DEP",
        source_name=name,
        source_urls=(product.download_url,),
        metadata_urls=metadata_urls,
        license=USGS_TNM_LICENSE,
        citation=USGS_TNM_CITATION,
        region_policy=REGION_POLICY_US,
        country_hints=("US",),
        region_hints=(),
        resolution_m=product.resolution_m,
        surface_type=SURFACE_DEM,
        acquisition_date=product.updated_date,
        publication_date=product.publication_date,
        coverage_score=_coverage_score(product.bbox_wgs84, aoi_bbox_wgs84),
        direct_no_auth=True,
        requires_auth=False,
        estimated_download_size_mb=product.estimated_download_size_mb,
        warnings=(),
        fallback_reason=None,
        source_id=product.source_id,
        bbox_wgs84=product.bbox_wgs84,
    )


def _looks_like_geotiff(record: dict[str, Any], download_url: str) -> bool:
    fields = " ".join(
        str(value)
        for key, value in record.items()
        if key.lower() in {"format", "formats", "prodformat", "prodformats", "productformat"}
    ).lower()
    url_path = urlparse(download_url).path.lower()
    return "geotiff" in fields or url_path.endswith((".tif", ".tiff", ".tif.zip", ".tiff.zip"))


def _first_text(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if item not in (None, ""):
                    return str(item)
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def _parse_bbox(record: dict[str, Any]) -> tuple[float, float, float, float] | None:
    for key in ("bbox", "boundingBox", "bounding_box", "extent"):
        value = record.get(key)
        bbox = _bbox_from_value(value)
        if bbox:
            return bbox
    keys = {
        "west": ("minX", "xmin", "west", "westBoundLongitude"),
        "south": ("minY", "ymin", "south", "southBoundLatitude"),
        "east": ("maxX", "xmax", "east", "eastBoundLongitude"),
        "north": ("maxY", "ymax", "north", "northBoundLatitude"),
    }
    values: list[float] = []
    for aliases in keys.values():
        raw = _first_text(record, *aliases)
        if raw is None:
            return None
        try:
            values.append(float(raw))
        except ValueError:
            return None
    return tuple(values)  # type: ignore[return-value]


def _bbox_from_value(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict):
        aliases = (
            ("minX", "minY", "maxX", "maxY"),
            ("xmin", "ymin", "xmax", "ymax"),
            ("west", "south", "east", "north"),
            ("westBoundLongitude", "southBoundLatitude", "eastBoundLongitude", "northBoundLatitude"),
        )
        for names in aliases:
            try:
                return tuple(float(value[name]) for name in names)  # type: ignore[return-value]
            except (KeyError, TypeError, ValueError):
                continue
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        try:
            return tuple(float(part) for part in value[:4])  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
        if len(parts) >= 4:
            try:
                return tuple(float(part) for part in parts[:4])  # type: ignore[return-value]
            except ValueError:
                return None
    return None


def _parse_resolution_m(record: dict[str, Any], dataset: str) -> float | None:
    for key in ("resolution_m", "resolution", "cellSize", "cell_size", "gridResolution"):
        value = record.get(key)
        if value is None:
            continue
        parsed = _first_number(value)
        if parsed is not None and parsed > 0:
            text = str(value).lower()
            if "arc" in text and parsed <= 1.1:
                return 30.0 if parsed >= 1.0 else 10.0
            return parsed
    return DATASET_RESOLUTION_METERS.get(dataset)


def _parse_size_mb(record: dict[str, Any]) -> float | None:
    for key in ("sizeInBytes", "fileSizeBytes", "bytes", "size", "downloadSize"):
        value = record.get(key)
        if value is None:
            continue
        number = _first_number(value)
        if number is None:
            continue
        text = str(value).lower()
        if "gb" in text:
            return number * 1024.0
        if "mb" in text:
            return number
        if "kb" in text:
            return number / 1024.0
        if number > 1024 * 1024:
            return number / (1024.0 * 1024.0)
        return number
    return None


def _first_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    text = str(value)
    token = ""
    for char in text:
        if char.isdigit() or char in ".-":
            token += char
        elif token:
            break
    if not token:
        return None
    try:
        number = float(token)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


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


def _filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    if not name:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return f"usgs_tnm_{digest}.tif"
    return name


def _format_coord(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _exception_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, URLError):
        return f"URL error: {exc.reason}"
    return f"{exc.__class__.__name__}: {exc}"


__all__ = [
    "DATASET_RESOLUTION_METERS",
    "DEFAULT_TNM_PRODUCTS_ENDPOINT",
    "TNM_DATASETS",
    "USGSTNMAdapter",
    "USGSTNMDownloadRecord",
    "USGSTNMProduct",
    "build_tnm_products_url",
    "buffer_wgs84_bbox",
    "download_with_retries",
    "parse_tnm_products",
    "sha256_file",
]
