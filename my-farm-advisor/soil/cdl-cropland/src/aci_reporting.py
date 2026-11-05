"""AAFC Annual Crop Inventory (ACI) extraction utilities — Canada's CDL analog.

Produces the same row schema as ``cdl_reporting.extract_crop_composition``
(field_id, year, crop_code, crop_name, pixel_count, pct) so downstream
rotation summarization is source-agnostic. ACI per-year imagery is exposed as
public ArcGIS ImageServer endpoints on agriculture.canada.ca (verified
2026-11-02); we export a 30 m class raster clipped to each field's bounding
box, then run the identical categorical zonal stats used for CDL.

Provenance: rows carry the raw ACI class code in ``crop_code`` and a mapped
``crop_name`` aligned with CDL vocabulary where an agronomic equivalent
exists ("Corn" for 147 Corn for grain, "Soybeans" for 158, "Winter Wheat"
for 145, ...). ``crop_source`` distinguishes "aci" from "cdl" rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterstats import zonal_stats

# 2026 program data rule: external data must be public by 2026-02-01. ACI 2024 was
# published Sep 2025 (pre-cutoff) but CDL's shared default stays 2023; keep
# ACI on the same window so cross-country features are year-aligned.
ACI_LATEST_YEAR = 2023
ACI_MIN_YEAR = 2009
ACI_PIXEL_SIZE_M = 30.0

ACI_IMAGE_SERVER_URL = (
    "https://agriculture.canada.ca/imagery-images/rest/services/"
    "annual_crop_inventory/{year}/ImageServer/exportImage"
)
ACI_PROVINCE_ZIP_URL = (
    "https://agriculture.canada.ca/atlas/data_donnees/annualCropInventory/"
    "data_donnees/tif/{year}/aci_{year}_{province}_v5.zip"
)
ACI_LEGEND_URL = (
    "https://agriculture.canada.ca/atlas/data_donnees/annualCropInventory/"
    "supportdocument_documentdesupport/"
    "aci_crop_classifications_iac_classifications_des_cultures.csv"
)
ACI_DATASET_URL = "https://open.canada.ca/data/en/dataset/745c889d-347e-4847-befe-57154d1bc206"

# ACI class code -> crop_name (CDL-aligned names where an equivalent exists;
# "No Data" and unmapped-but-known codes never enter rotation summaries).
ACI_CODE_MAP: dict[int, str] = {
    0: "No Data",
    10: "No Data",  # Cloud
    20: "Open Water",
    30: "Other",
    34: "Urban",
    35: "Greenhouse",
    50: "Shrubland",
    60: "Other",  # forest fire/burnt
    80: "Wetland",
    85: "Wetland",
    110: "Grass/Pasture",
    120: "Other",  # agriculture undifferentiated
    121: "Other",  # cropland undifferentiated
    122: "Grass/Pasture",  # pasture/forages
    130: "Fallow/Idle",  # too wet to be seeded
    131: "Fallow/Idle",
    132: "Other",  # cereals undifferentiated
    133: "Barley",
    134: "Other",
    135: "Millet",
    136: "Oats",
    137: "Rye",
    138: "Spelt",
    139: "Triticale",
    140: "Wheat",
    141: "Switchgrass",
    142: "Sorghum",
    143: "Quinoa",
    145: "Winter Wheat",
    146: "Spring Wheat",
    147: "Corn",  # Corn for grain / Mixed grain — CDL name for code 1
    148: "Tobacco",
    149: "Other",  # ginseng
    150: "Other",  # oilseeds undifferentiated
    151: "Other",
    152: "Camelina",
    153: "Canola",
    154: "Flax",
    155: "Mustard",
    156: "Other",  # safflower
    157: "Sunflower",
    158: "Soybeans",
    159: "Other",
    160: "Other",  # pulses undifferentiated
    161: "Other",
    162: "Peas",
    163: "Chickpeas",
    167: "Beans",
    168: "Faba Beans",
    174: "Lentils",
    175: "Vegetables",
    176: "Vegetables",
    177: "Vegetables",
    178: "Sugarbeets",
    179: "Vegetables",
    180: "Fruits",
    181: "Berries",
    182: "Berries",
    183: "Berries",
    185: "Berries",
    188: "Orchards",
    189: "Fruits",
    190: "Vineyards",
    191: "Other",
    192: "Other",  # sod
    193: "Other",
    194: "Other",  # nursery
    195: "Buckwheat",
    196: "Canaryseed",
    197: "Hemp",
    198: "Other",  # vetch
    199: "Other",
    200: "Forest",
    210: "Forest",
    220: "Forest",
    230: "Forest",
}


def aci_crop_name(code: int) -> str:
    return ACI_CODE_MAP.get(int(code), "Other")


def aci_export_size_degrees(bbox_wgs84: tuple[float, float, float, float]) -> tuple[int, int]:
    """Pixel dimensions so one ACI pixel stays ~30 m at the field latitude."""
    x0, y0, x1, y1 = bbox_wgs84
    lat_mid = math.radians((y0 + y1) / 2.0)
    m_per_deg_lat = 110_540.0
    m_per_deg_lon = 111_320.0 * max(0.2, math.cos(lat_mid))
    width = int(math.ceil((x1 - x0) * m_per_deg_lon / ACI_PIXEL_SIZE_M))
    height = int(math.ceil((y1 - y0) * m_per_deg_lat / ACI_PIXEL_SIZE_M))
    clamp = lambda v: max(16, min(4096, v))
    return clamp(width), clamp(height)


def aci_export_bbox(field_geom_4326, buffer_m: float = 60.0) -> tuple[float, float, float, float]:
    """Field envelope widened by ``buffer_m`` so edge pixels exist for zonal stats."""
    minx, miny, maxx, maxy = field_geom_4326.bounds
    deg_lat = buffer_m / 110_540.0
    deg_lon = buffer_m / (111_320.0 * max(0.2, math.cos(math.radians((miny + maxy) / 2.0))))
    return (minx - deg_lon, miny - deg_lat, maxx + deg_lon, maxy + deg_lat)


def fetch_aci_field_raster(
    field: dict,
    year: int,
    cache_dir: Path,
    *,
    force: bool = False,
    timeout: int = 120,
    retries: int = 3,
) -> Path | None:
    """Download (or reuse) the ACI class raster for one field-year.

    Cache layout ``<cache_dir>/aci/<year>/<field_slug>.tif`` so repeat runs are
    byte-identical; provenance (url, sha256, fetch time) is journaled in
    ``<cache_dir>/aci/<year>/fetch_manifest.json``.
    """
    field_slug = str(field.get("field_slug") or field["field_id"])
    out_path = Path(cache_dir) / "aci" / str(year) / f"{field_slug}.tif"
    if out_path.exists() and not force:
        return out_path

    geom_4326 = gpd.GeoSeries([field["geometry"]], crs="EPSG:4326").iloc[0]
    x0, y0, x1, y1 = aci_export_bbox(geom_4326)
    width, height = aci_export_size_degrees((x0, y0, x1, y1))
    params = {
        "f": "image",
        "bbox": f"{x0:.7f},{y0:.7f},{x1:.7f},{y1:.7f}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "noInterpolation": "true",
    }
    url = ACI_IMAGE_SERVER_URL.format(year=year)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            content = resp.content
            if content[:4] not in (b"II*\x00", b"MM\x00*"):
                raise ValueError(f"ACI {year} export was not a TIFF: {content[:120]!r}")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(content)
            manifest_path = out_path.parent / "fetch_manifest.json"
            entries: dict[str, dict] = {}
            if manifest_path.exists():
                entries = json.loads(manifest_path.read_text())
            entries[out_path.name] = {
                "url": resp.url,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "AAFC Annual Crop Inventory ImageServer export",
                "legend": ACI_LEGEND_URL,
                "dataset": ACI_DATASET_URL,
            }
            manifest_path.write_text(json.dumps(entries, indent=2, sort_keys=True))
            return out_path
        except Exception as exc:  # noqa: BLE001 - retry any transport/parse failure
            last_error = exc
            if attempt < retries:
                time.sleep(2 * attempt)
    print(f"  warn  ACI {year} export failed for {field_slug}: {last_error}")
    return None


def extract_aci_crop_composition(
    fields: gpd.GeoDataFrame,
    cache_dir: Path,
    year: int,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Row schema identical to cdl_reporting.extract_crop_composition.

    Each field gets its own ~30 m ACI export over its buffered envelope; the
    zonal stats math is the CDL math. Fields with no usable raster or no
    pixels emit a ``No Data`` row (dropped by the shared category filter).
    """
    rows: list[dict[str, object]] = []
    fields_4326 = fields.to_crs(epsg=4326)
    for _, field in fields_4326.iterrows():
        record = field.to_dict()
        raster_path = fetch_aci_field_raster(record, year, cache_dir, force=force)
        field_id = field["field_id"]
        if raster_path is None:
            rows.append(
                {
                    "field_id": field_id,
                    "year": year,
                    "crop_code": 0,
                    "crop_name": "No Data",
                    "pixel_count": 0,
                    "pct": 0.0,
                }
            )
            continue
        counts: dict[int, int] = {}
        with rasterio.open(raster_path) as src:
            field_utm = field.geometry
            for shape_counts in zonal_stats([field_utm], str(raster_path), categorical=True):
                for code, count in (shape_counts or {}).items():
                    counts[int(code)] = counts.get(int(code), 0) + int(count)
        valid = {code: n for code, n in counts.items() if not math.isnan(float(code))}
        total = int(sum(valid.values()))
        if total <= 0:
            rows.append(
                {
                    "field_id": field_id,
                    "year": year,
                    "crop_code": 0,
                    "crop_name": "No Data",
                    "pixel_count": 0,
                    "pct": 0.0,
                }
            )
            continue
        for crop_code, pixel_count in sorted(valid.items(), key=lambda item: item[1], reverse=True):
            rows.append(
                {
                    "field_id": field_id,
                    "year": year,
                    "crop_code": crop_code,
                    "crop_name": aci_crop_name(crop_code),
                    "pixel_count": pixel_count,
                    "pct": round(pixel_count / total * 100.0, 2),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if float(np.asarray(frame["pixel_count"]).sum()) <= 0:
        return frame
    return frame


__all__ = [
    "ACI_CODE_MAP",
    "ACI_IMAGE_SERVER_URL",
    "ACI_LATEST_YEAR",
    "ACI_MIN_YEAR",
    "aci_crop_name",
    "aci_export_bbox",
    "aci_export_size_degrees",
    "extract_aci_crop_composition",
    "fetch_aci_field_raster",
]
