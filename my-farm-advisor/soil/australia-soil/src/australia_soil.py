#!/usr/bin/env python3
"""Australian national soil provider for the My Farm Advisor data pipeline.

Australian counterpart of the SSURGO step: the Soil and Landscape Grid of
Australia (SLGA) / Australian Soil Fabric (ASF) national attribute grids
(modelling resolution 90 m, delivered nationally at 3 arc-second and 30 m
grid sizes, with 5 %/95 % confidence-interval bands and an extrapolation-risk
band where noted), plus soil profile/site records via ANSIS (the successor of
the retired ASRIS website).

Every URL and HTTP status quoted below was probed live on 2026-11-03.

Access matrix (verified 2026-11-03):

* Raster metadata + canonical COG URLs — keyless JSON API:
  GET https://esoil.io/TERNLandscapes/RasterProductsAPI/ProductInfo?format=json&product=SLGA&isCurrentVersion=1
      -> HTTP 200, list of records (Code, Attribute, Units, UpperDepth_m,
         LowerDepth_m, COGsPath, MetadataLink, Component, Version).
  GET .../QueryParameterValues?format=json&parameter=Attribute
      -> HTTP 200.
* Raster bytes (Cloud-Optimized GeoTIFFs) — TWO paths:
  (a) canonical store https://data.tern.org.au/model-derived/slga/NationalMaps/SoilAndLandscapeGrid/...
      GET -> HTTP 401 keyless (HTML login wall); needs a free TERN API key
      sent as the ``x-api-key`` HTTP header (or via the optional
      SLGA_TERN_API_KEY environment variable). Key signup:
      https://account.tern.org.au/authenticated_user/apikeys (instructions:
      https://ternaus.atlassian.net/wiki/spaces/TERNSup/pages/2353496065/Creating+API+Keys).
      The official COGs page states the requirement verbatim: "To access the
      SLGA data products you need to generate an API key."
      (https://esoil.io/TERNLandscapes/Public/Pages/SLGA/GetData-COGSDataStore.html,
      HTTP 200 2026-11-03).
  (b) keyless mirror — same released files as public CSIRO Data Access
      Portal (DAP) collections, one GeoTIFF per attribute/depth/band:
      GET https://data.csiro.au/dap/ws/v2/collections/{COLL}/data?format=json
          -> HTTP 200 file list with presigned S3 links;
      GET https://data.csiro.au/dap/ws/v2/collections/{COLL}/data/{FILE_ID}
          -> HTTP 302 to a presigned s3.data.csiro.au URL that honours
             Range requests (HTTP 206, verified), so rasterio ``/vsicurl/``
             streams a field-sized clip without downloading the whole file.
      License CC BY 4.0 (record-level ``licence`` field).
* Profile/site records (ASRIS successor, ANSIS HTTP API) — keyless:
  GET https://apim-ansis-app-prod-ac.azure-api.net/site-catalogue/v1/catalogue-summary
      -> HTTP 200, 13 provider catalogues (JSON: id, name, lastModified,
         lengthBytes).
  GET .../site-catalogue/v1/provider/{ID}
      -> HTTP 200, GeoJSON FeatureCollection of soil sites (Point geometry;
         properties: site, provider, project, state, years, entryCount,
         isRestricted, isHydrated, properties=[ANSIS property codes]).
  GET .../site-catalogue/v1/definitions
      -> HTTP 200, 242 property-code definitions.
  Full horizon/lab JSON per site (SDR "SingleSite", query-request POSTs)
  requires an ANSIS account token via the Authorize endpoint (username /
  password HTTP headers); the site-level catalogue above is keyless.

* Retired paths (do NOT use): www.asris.csiro.au (HTTP 500 proxy error on
  ``/``, ``/arcgis/rest/services?f=json``, ``/mapping/view_au.php``; the
  cgi-bin WCS returns 403), the old raster mirror
  https://esoil.io/TERNLandscapes/Public/Products/TERN/ (HTTP 404), and DAP
  ``/dap/ws2/...`` (HTTP 404 — use ``/dap/ws/v2/``).

Storage conventions (verified by opening the 0-5 cm EV grids via
``/vsicurl/`` on 2026-11-03): grids are BigTIFF Cloud-Optimized GeoTIFFs
(``II+`` magic, 256x256 internal tiling) in EPSG:4326, pixel value == the
physical unit from ``Units`` (scale 1.0, offset 0.0, float32); Release-1
(2014, "NAT_C") files are striped float32 with nodata -9999.0, Release-2
files are tiled float32 with nodata NaN. ``clip_field`` returns the actual
per-band scale/offset/nodata/dtype in its provenance record — never
hardcode them.

Naming convention: ``CODE_Upper_Lower_COMPONENT_F_AU_[TRN|NAT]_[N|C]_DATE``
with CODE in (CLY, SLT, SND, CEC, PHC/pHc, SOC, BDW, ...),
COMPONENT in (EV = modelled value, 05/95 = lower/upper confidence interval,
EXT = extrapolation risk), e.g. CLY_000_005_EV_N_P_AU_TRN_N_20210902.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.enums
import rasterio.windows
import requests
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

SOURCE_NAME = "slga_asf"
ACCESS_DATE = "2026-11-03"  # all pinned URLs/statuses below were checked this day
LICENSE = "CC-BY-4.0"
API_KEY_ENV = "SLGA_TERN_API_KEY"

API_ROOT = "https://esoil.io/TERNLandscapes/RasterProductsAPI"
COG_STORE = "https://data.tern.org.au/model-derived/slga/NationalMaps/SoilAndLandscapeGrid"
DAP_API = "https://data.csiro.au/dap/ws/v2"
ANSIS_API = "https://apim-ansis-app-prod-ac.azure-api.net/site-catalogue/v1"
API_KEY_SIGNUP = "https://account.tern.org.au/authenticated_user/apikeys"
SOURCE_PAGES = {
    "slga_home": "https://esoil.io/TERNLandscapes/Public/Pages/SLGA/index.html",
    "cogs_access": "https://esoil.io/TERNLandscapes/Public/Pages/SLGA/GetData-COGSDataStore.html",
    "covariate_metadata_doi": "https://doi.org/10.25919/jr32-yq58",
}

DEPTH_LABELS = {
    "0-5cm": ("000_005", 0.0, 0.05),
    "5-15cm": ("005_015", 0.05, 0.15),
    "15-30cm": ("015_030", 0.15, 0.30),
    "30-60cm": ("030_060", 0.30, 0.60),
    "60-100cm": ("060_100", 0.60, 1.00),
    "100-200cm": ("100_200", 1.00, 2.00),
}

# Canonical grid URLs for the seven contract properties at the two top depth
# slabs. "cog" = canonical TERN data store (x-api-key required; GET -> 401
# keyless on 2026-11-03). "dap" = keyless CSIRO DAP mirror of the same file
# (collection, file id, bytes; GET -> 302 -> presigned S3 206 on 2026-11-03).
# "units" is the ProductInfo `Units` field (verified keyless, 2026-11-03).
PROPERTY_URLS: dict[str, dict[str, Any]] = {
    "CLAY": {
        "code": "CLY",
        "attribute": "Clay",
        "units": "%",
        "doi": "https://doi.org/10.25919/hc4s-3130",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/CLY/v2/CLY_000_005_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63379/data/63820524",
                "dap_collection": 63379,
                "dap_file_id": 63820524,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/CLY/v2/CLY_005_015_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63379/data/63820526",
                "dap_collection": 63379,
                "dap_file_id": 63820526,
            },
        },
    },
    "SILT": {
        "code": "SLT",
        "attribute": "Silt",
        "units": "%",
        "doi": "https://doi.org/10.25919/2ew1-0w57",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/SLT/v2/SLT_000_005_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63365/data/64206508",
                "dap_collection": 63365,
                "dap_file_id": 64206508,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/SLT/v2/SLT_005_015_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63365/data/64206511",
                "dap_collection": 63365,
                "dap_file_id": 64206511,
            },
        },
    },
    "SAND": {
        "code": "SND",
        "attribute": "Sand",
        "units": "%",
        "doi": "https://doi.org/10.25919/rjmy-pa10",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/SND/v2/SND_000_005_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63366/data/63820449",
                "dap_collection": 63366,
                "dap_file_id": 63820449,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/SND/v2/SND_005_015_EV_N_P_AU_TRN_N_20210902.tif",
                "dap": f"{DAP_API}/collections/63366/data/63820452",
                "dap_collection": 63366,
                "dap_file_id": 63820452,
            },
        },
    },
    "CEC": {
        "code": "CEC",
        "attribute": "Cation Exchange Capacity",
        "units": "meq/100g",
        "doi": "https://doi.org/10.25919/pkva-gf85",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/CEC/v1/CEC_000_005_EV_N_P_AU_TRN_N_20220826.tif",
                "dap": f"{DAP_API}/collections/63381/data/63828030",
                "dap_collection": 63381,
                "dap_file_id": 63828030,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/CEC/v1/CEC_005_015_EV_N_P_AU_TRN_N_20220826.tif",
                "dap": f"{DAP_API}/collections/63381/data/63828033",
                "dap_collection": 63381,
                "dap_file_id": 63828033,
            },
        },
    },
    "PHCALCIUMCHLORIDE": {
        "code": "PHC",
        "attribute": "pH - Calcium Chloride",
        "units": "pH (1:5 CaCl2, dimensionless)",
        "doi": "https://doi.org/10.25919/7320-hw30",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/pHc/v2/PHC_000_005_EV_N_P_AU_NAT_C_20210913.tif",
                "dap": f"{DAP_API}/collections/62186/data/74114805",
                "dap_collection": 62186,
                "dap_file_id": 74114805,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/pHc/v2/PHC_005_015_EV_N_P_AU_NAT_C_20210913.tif",
                "dap": f"{DAP_API}/collections/62186/data/74114808",
                "dap_collection": 62186,
                "dap_file_id": 74114808,
            },
        },
    },
    "CARBON": {
        "code": "SOC",
        "attribute": "Organic Carbon / Soil Organic Carbon (1\" resolution)",
        "units": "%",
        "doi": "https://doi.org/10.25919/ejhm-c070",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/SOC/90m/v2/SOC_000_005_EV_N_P_AU_TRN_N_20220727.tif",
                "dap": f"{DAP_API}/collections/58215/data/63825310",
                "dap_collection": 58215,
                "dap_file_id": 63825310,
                "dap_note": "DAP mirror is the same-date SOC_000_005_EV_N_P_AU_NAT_N build; "
                            "Release-1 striped 3\" mirror at collections/63374 (CLY-era vintage)",
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/SOC/90m/v2/SOC_005_015_EV_N_P_AU_TRN_N_20220727.tif",
                "dap": f"{DAP_API}/collections/58215/data/63825313",
                "dap_collection": 58215,
                "dap_file_id": 63825313,
                "dap_note": "DAP mirror is the same-date SOC_005_015_EV_N_P_AU_NAT_N build",
            },
        },
    },
    "BULKDENSITY": {
        "code": "BDW",
        "attribute": "Bulk Density (whole earth)",
        "units": "g/cm3",
        "doi": "https://doi.org/10.25919/gxyn-pd07",
        "depths": {
            "0-5cm": {
                "cog": f"{COG_STORE}/BDW/v2/BDW_000_005_EV_N_P_AU_TRN_N_20230607.tif",
                "dap": f"{DAP_API}/collections/63382/data/65273479",
                "dap_collection": 63382,
                "dap_file_id": 65273479,
            },
            "5-15cm": {
                "cog": f"{COG_STORE}/BDW/v2/BDW_005_015_EV_N_P_AU_TRN_N_20230607.tif",
                "dap": f"{DAP_API}/collections/63382/data/65273482",
                "dap_collection": 63382,
                "dap_file_id": 65273482,
            },
        },
    },
}

# ANSIS providers with keyless site catalogues (HTTP 200 on the
# catalogue-summary, 2026-11-03). Default set for asris_profiles_near:
# jurisdiction custodians + the CSIRO ANSA/CSIRO Soil Information System
# programme (the ASRIS-era harmonised profiles).
ANSIS_PROVIDERS = (
    "NewSouthWales",
    "NorthernTerritory",
    "Queensland",
    "SouthAustralia",
    "Tasmania",
    "Victoria",
    "WesternAustralia",
    "CSIRO_CSIS",
)
_CATALOGUE_SIZES = {  # lengthBytes from the live catalogue-summary, 2026-11-03
    "CSIRO_CSIS": 11_326_535,
    "NewSouthWales": 23_204_613,
    "NorthernTerritory": 14_180_677,
    "Queensland": 40_989_945,
    "SouthAustralia": 7_626_025,
    "Tasmania": 2_283_808,
    "Victoria": 1_507_772,
    "WesternAustralia": 17_349_558,
}


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_entry(prop: str, depth: str) -> dict[str, Any]:
    """PROPERTY_URLS depth entry for a contract property name and depth label."""
    try:
        property_entry = PROPERTY_URLS[prop]
    except KeyError:
        raise KeyError(
            f"unknown property {prop!r}; valid: {', '.join(sorted(PROPERTY_URLS))}"
        ) from None
    try:
        return property_entry["depths"][depth]
    except KeyError:
        raise KeyError(
            f"unknown depth {depth!r} for {prop}; valid: "
            f"{', '.join(sorted(property_entry['depths']))}"
        ) from None


def product_metadata(
    datatype: str = "Soil",
    product: str = "SLGA",
    current_only: bool = True,
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Keyless ProductInfo records — the machine-readable source of the
    canonical COGsPath/Units/depth metadata mirrored in PROPERTY_URLS."""
    params = {"format": "json", "product": product, "datatype": datatype}
    if current_only:
        params["isCurrentVersion"] = "1"
    response = requests.get(f"{API_ROOT}/ProductInfo", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _gdal_env_options(api_key: str | None) -> tuple[dict[str, str], list[Any]]:
    """GDAL config + open stack for an optional x-api-key header."""
    stack: list[Any] = []
    options: dict[str, str] = {"GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_RETRY_DELAY": "1"}
    if api_key:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".httpheader", delete=False, encoding="utf-8"
        )
        handle.write(f"x-api-key: {api_key}\r\n")
        handle.close()
        os.chmod(handle.name, 0o600)
        options["GDAL_HTTP_HEADER_FILE"] = handle.name
        stack.append(handle)
    return options, stack


def clip_field(
    bbox: tuple[float, float, float, float],
    out_path: str | Path,
    prop: str = "CLAY",
    depth: str = "0-5cm",
    api_key: str | None = None,
    source: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Stream-clip one SLGA attribute grid for a WGS84 bounding box.

    bbox is (min_lon, min_lat, max_lon, max_lat) in EPSG:4326. Uses
    ``/vsicurl/`` (HTTP range requests) + a WarpedVRT so the output is always
    reprojected to EPSG:4326. ``source`` is "dap" (keyless CSIRO mirror — the
    default when no TERN key is present) or "cog" (canonical data.tern.org.au
    store; needs the free key via argument or the SLGA_TERN_API_KEY env var).
    Returns an explicit provenance dict.
    """
    property_entry = PROPERTY_URLS[prop]
    entry = resolve_entry(prop, depth)
    api_key = api_key or os.environ.get(API_KEY_ENV) or None
    if source is None:
        source = "cog" if api_key else "dap"
    if source not in ("dap", "cog"):
        raise ValueError(f"source must be 'dap' or 'cog', got {source!r}")
    if source == "cog" and not api_key:
        probe = requests.get(entry["cog"], timeout=timeout)
        raise RuntimeError(
            "Canonical SLGA COG store returned HTTP "
            f"{probe.status_code} (keyless GET tested {ACCESS_DATE}): {entry['cog']} — "
            f"supply a free TERN API key via api_key= or the {API_KEY_ENV} env var "
            f"(signup: {API_KEY_SIGNUP}), or pass source='dap' for the keyless "
            "CSIRO DAP mirror of the same file."
        )
    url = entry["cog"] if source == "cog" else entry["dap"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    options, stack = _gdal_env_options(api_key if source == "cog" else None)
    try:
        with rasterio.Env(**options):
            with rasterio.open(f"/vsicurl/{url}") as raw:
                with WarpedVRT(
                    raw,
                    dst_crs="EPSG:4326",
                    resampling=rasterio.enums.Resampling.bilinear,
                ) as src:
                    window = from_bounds(*bbox, transform=src.transform)
                    col_off = max(0, int(math.floor(window.col_off)))
                    row_off = max(0, int(math.floor(window.row_off)))
                    width = min(src.width - col_off, int(math.ceil(window.width)))
                    height = min(src.height - row_off, int(math.ceil(window.height)))
                    if width <= 0 or height <= 0:
                        raise ValueError(f"bbox {bbox} falls outside the grid")
                    window = rasterio.windows.Window(col_off, row_off, width, height)
                    data = src.read(masked=True, window=window)
                    nodata = src.nodata
                    transform = rasterio.windows.transform(window, src.transform)
                    bands = []
                    for band_index in range(1, data.shape[0] + 1):
                        kept = data[band_index - 1].compressed()
                        bands.append(
                            {
                                "band": band_index,
                                "count": int(kept.size),
                                "mean": float(kept.mean()) if kept.size else None,
                                "min": float(kept.min()) if kept.size else None,
                                "max": float(kept.max()) if kept.size else None,
                                "std": float(kept.std()) if kept.size > 1 else None,
                            }
                        )
                    meta = {
                        "driver": "GTiff",
                        "height": int(height),
                        "width": int(width),
                        "count": src.count,
                        "dtype": src.dtypes[0],
                        "crs": "EPSG:4326",
                        "transform": transform,
                        "tiled": True,
                        "nodata": nodata if nodata is not None else float(np.nan),
                    }
                    if meta["nodata"] != meta["nodata"]:  # NaN nodata for float
                        out = data.filled(np.nan)
                    else:
                        out = data.filled(meta["nodata"])
                    with rasterio.open(out_path, "w", **meta) as dst:
                        dst.write(out)
                    provenance = {
                        "source": SOURCE_NAME,
                        "property": prop,
                        "attribute": property_entry["attribute"],
                        "code": property_entry["code"],
                        "depth": depth,
                        "depth_m": DEPTH_LABELS[depth][1:],
                        "units": property_entry["units"],
                        "source_kind": source,
                        "url": url,
                        "accessed_at": _utcnow(),
                        "license": LICENSE,
                        "doi": property_entry.get("doi"),
                        "dtype": src.dtypes[0],
                        "nodata": meta["nodata"],
                        "scale": src.scales,
                        "offset": src.offsets,
                        "res_deg": src.res,
                        "out_path": str(out_path),
                        "out_bytes": out_path.stat().st_size,
                        "window": [col_off, row_off, int(width), int(height)],
                        "bbox": list(bbox),
                        "stats": bands,
                    }
                    if "dap_note" in entry:
                        provenance["dap_note"] = entry["dap_note"]
                    return provenance
    finally:
        for handle in stack:
            try:
                os.unlink(handle.name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Profile/site records (ANSIS — the ASRIS successor)
# ---------------------------------------------------------------------------


def ansis_catalogue_summary(timeout: float = 60.0) -> list[dict[str, Any]]:
    """Keyless inventory of ANSIS site catalogues (id, name, lastModified,
    lengthBytes). HTTP 200 without any credential, verified 2026-11-03."""
    response = requests.get(f"{ANSIS_API}/catalogue-summary", timeout=timeout)
    response.raise_for_status()
    return response.json()


def _default_cache_dir() -> Path:
    root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if root:
        return Path(root) / "data-pipeline" / "shared" / "soil_australia" / "ansis"
    return Path(tempfile.mkdtemp(prefix="ansis_catalogues_"))


def asris_profiles_near(
    bbox: tuple[float, float, float, float],
    radius_km: float = 10.0,
    cache_dir: str | Path | None = None,
    providers: tuple[str, ...] = ANSIS_PROVIDERS,
    force: bool = False,
    timeout: float = 300.0,
) -> gpd.GeoDataFrame:
    """Soil profile/site records within radius_km of a WGS84 bbox.

    Returns a site-level GeoDataFrame (point per soil site) from the keyless
    ANSIS provider catalogues — the successor of the retired ASRIS map tool.
    Catalogues are cached per provider under ``cache_dir`` (the payload is
    one JSON per provider, see _CATALOGUE_SIZES for the byte cost). Columns
    carry custodian (provider), project, state, observation years, entry
    count, restriction flags and the raw ANSIS property codes observed at the
    site. Full horizon/lab detail per site (ANSIS "SDR SingleSite" and
    create-query-request) additionally needs an ANSIS account token — see the
    Authorize endpoint in the module docstring; these rows are the site
    index, not redacted lab tables.
    """
    minx, miny, maxx, maxy = bbox
    cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    lat_pad = radius_km / 111.32
    centre_lat = (miny + maxy) / 2.0
    lon_pad = radius_km / (111.32 * max(0.01, math.cos(math.radians(centre_lat))))
    rows: list[dict[str, Any]] = []
    for provider in providers:
        target = cache_dir / f"catalogue_{provider}.json"
        if force or not target.exists():
            response = requests.get(f"{ANSIS_API}/provider/{provider}", timeout=timeout)
            if response.status_code != 200:
                raise RuntimeError(
                    f"ANSIS catalogue {provider!r}: HTTP {response.status_code} for "
                    f"{response.url} (endpoint live on {ACCESS_DATE}; a non-200 here "
                    "means an upstream outage or a renamed provider id — check "
                    f"{ANSIS_API}/catalogue-summary)"
                )
            target.write_bytes(response.content)
        payload = json.loads(target.read_text())
        features = payload if isinstance(payload, list) else payload.get("features", [])
        for feature in features:
            coords = feature["geometry"]["coordinates"]
            if minx - lon_pad <= coords[0] <= maxx + lon_pad and (
                miny - lat_pad <= coords[1] <= maxy + lat_pad
            ):
                props = feature["properties"]
                rows.append(
                    {
                        "provider": props.get("provider", provider),
                        "site": str(props.get("site")),
                        "project": props.get("project"),
                        "state": props.get("state"),
                        "first_year": (props.get("years") or [None, None])[0],
                        "last_year": (props.get("years") or [None, None])[-1],
                        "entry_count": props.get("entryCount"),
                        "is_restricted": props.get("isRestricted"),
                        "is_hydrated": props.get("isHydrated"),
                        "property_codes": json.dumps(props.get("properties", [])),
                        "lon": coords[0],
                        "lat": coords[1],
                    }
                )
    if not rows:
        return gpd.GeoDataFrame(
            columns=["provider", "site", "geometry"],
            geometry="geometry",
            crs="EPSG:4326",
        )
    frame = gpd.GeoDataFrame(
        rows,
        geometry=gpd.points_from_xy([r.pop("lon") for r in rows], [r.pop("lat") for r in rows]),
        crs="EPSG:4326",
    )
    return frame
