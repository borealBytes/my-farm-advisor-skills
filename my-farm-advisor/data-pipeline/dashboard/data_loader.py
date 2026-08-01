"""Data loader for the Row Crop Intelligence Dashboard.

Reads runtime data from Assignments 1-3 and computes KPIs.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

RUNTIME_ROOT = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")
GROWERS_DIR = RUNTIME_ROOT / "growers"

GROWER_CONFIGS = [
    {
        "grower_slug": "il-grower",
        "farm_slug": "il-grower-illinois",
        "state": "Illinois",
        "abbr": "IL",
    },
    {
        "grower_slug": "ia-grower",
        "farm_slug": "ia-grower-iowa",
        "state": "Iowa",
        "abbr": "IA",
    },
    {
        "grower_slug": "ne-grower",
        "farm_slug": "ne-grower-nebraska",
        "state": "Nebraska",
        "abbr": "NE",
    },
]


def _farm_dir(grower_slug: str, farm_slug: str) -> Path:
    return GROWERS_DIR / grower_slug / "farms" / farm_slug


def _tables_dir(grower_slug: str, farm_slug: str) -> Path:
    return _farm_dir(grower_slug, farm_slug) / "derived" / "tables"


def _reports_dir(grower_slug: str, farm_slug: str) -> Path:
    return _farm_dir(grower_slug, farm_slug) / "derived" / "reports"


def load_boundaries() -> gpd.GeoDataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        path = _farm_dir(cfg["grower_slug"], cfg["farm_slug"]) / "boundary" / "field_boundaries.geojson"
        if path.exists():
            gdf = gpd.read_file(path)
            gdf["grower"] = cfg["grower_slug"]
            gdf["state"] = cfg["state"]
            gdf["state_abbr"] = cfg["abbr"]
            frames.append(gdf)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame()


def load_weather() -> pd.DataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        tables = _tables_dir(cfg["grower_slug"], cfg["farm_slug"])
        prefix = f"{cfg['grower_slug'].replace('-', '_')}_{cfg['state'].lower()}"
        path = tables / f"{prefix}_weather_2021_2025.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["date"])
            df["state"] = cfg["state"]
            df["grower"] = cfg["grower_slug"]
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def load_ssurgo_summary() -> pd.DataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        tables = _tables_dir(cfg["grower_slug"], cfg["farm_slug"])
        prefix = f"{cfg['grower_slug'].replace('-', '_')}_{cfg['state'].lower()}"
        path = tables / f"{prefix}_ssurgo_summary.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["state"] = cfg["state"]
            df["grower"] = cfg["grower_slug"]
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def load_cdl_composition() -> pd.DataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        tables = _tables_dir(cfg["grower_slug"], cfg["farm_slug"])
        prefix = f"{cfg['grower_slug'].replace('-', '_')}_{cfg['state'].lower()}"
        path = tables / f"{prefix}_cdl_2021_2025_full_composition.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["state"] = cfg["state"]
            df["grower"] = cfg["grower_slug"]
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def load_crop_rotation() -> pd.DataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        tables = _tables_dir(cfg["grower_slug"], cfg["farm_slug"])
        prefix = f"{cfg['grower_slug'].replace('-', '_')}_{cfg['state'].lower()}"
        path = tables / f"{prefix}_crop_rotation.csv"
        if path.exists():
            df = pd.read_csv(path)
            df["state"] = cfg["state"]
            df["grower"] = cfg["grower_slug"]
            frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def load_ndvi_joins() -> pd.DataFrame:
    frames = []
    for cfg in GROWER_CONFIGS:
        farm = _farm_dir(cfg["grower_slug"], cfg["farm_slug"])
        fields_dir = farm / "fields"
        if not fields_dir.exists():
            continue
        for field_dir in sorted(fields_dir.iterdir()):
            if not field_dir.is_dir():
                continue
            ndvi_path = field_dir / "derived" / "tables" / "ndvi_year_crop_join.csv"
            if ndvi_path.exists():
                df = pd.read_csv(ndvi_path)
                df["state"] = cfg["state"]
                df["grower"] = cfg["grower_slug"]
                df["farm_slug"] = cfg["farm_slug"]
                frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def compute_sustainability_score(row: pd.Series) -> float:
    """Compute a 0-100 soil sustainability score from SSURGO summary data.

    Components (weighted):
      - Organic matter (20%): higher is better, capped at 6%
      - pH (15%): ideal range 6.0-7.0, penalty outside
      - CEC (15%): higher is better, capped at 35
      - Available water storage (20%): higher is better, capped at 6 inches
      - Erosion risk (15%): low=100, moderate=60, high=20
      - Drainage (15%): well drained=100, mod well=80, somewhat poor=50, poor=20
    """
    score = 0.0

    om = row.get("avg_om_pct", 2.0)
    om_score = min(om / 6.0, 1.0) * 100
    score += om_score * 0.20

    ph = row.get("avg_ph", 6.5)
    if 6.0 <= ph <= 7.0:
        ph_score = 100
    elif 5.5 <= ph < 6.0 or 7.0 < ph <= 7.5:
        ph_score = 70
    else:
        ph_score = 40
    score += ph_score * 0.15

    cec = row.get("avg_cec", 20.0)
    cec_score = min(cec / 35.0, 1.0) * 100
    score += cec_score * 0.15

    aws = row.get("total_aws_inches", 3.0)
    aws_score = min(aws / 6.0, 1.0) * 100
    score += aws_score * 0.20

    erosion = str(row.get("erosion_risk", "moderate")).lower()
    erosion_map = {"low": 100, "moderate": 60, "high": 20, "very high": 10}
    erosion_score = erosion_map.get(erosion, 50)
    score += erosion_score * 0.15

    drainage = str(row.get("drainage_class", "")).lower()
    if "well drained" in drainage and "somewhat" not in drainage and "poorly" not in drainage:
        drainage_score = 100
    elif "moderately well" in drainage:
        drainage_score = 80
    elif "somewhat poorly" in drainage:
        drainage_score = 50
    elif "poorly" in drainage:
        drainage_score = 20
    elif "excessively" in drainage:
        drainage_score = 40
    else:
        drainage_score = 60
    score += drainage_score * 0.15

    return round(score, 1)


def compute_kpis() -> dict:
    boundaries = load_boundaries()
    weather = load_weather()
    ssurgo = load_ssurgo_summary()
    ndvi = load_ndvi_joins()

    total_fields = len(boundaries) if not boundaries.empty else 0
    total_acreage = round(boundaries["area_acres"].sum(), 1) if not boundaries.empty and "area_acres" in boundaries.columns else 0

    avg_ndvi = 0.0
    if not ndvi.empty and "scene_count" in ndvi.columns:
        ndvi_with_data = ndvi[ndvi["scene_count"] > 0]
        if not ndvi_with_data.empty:
            avg_ndvi = round(ndvi_with_data["scene_count"].mean(), 1)

    avg_rainfall_mm = 0.0
    if not weather.empty and "PRECTOTCORR" in weather.columns:
        avg_rainfall_mm = round(weather["PRECTOTCORR"].mean(), 2)

    sustainability_score = 0.0
    if not ssurgo.empty:
        scores = ssurgo.apply(compute_sustainability_score, axis=1)
        sustainability_score = round(scores.mean(), 1)

    return {
        "total_fields": total_fields,
        "total_acreage": total_acreage,
        "avg_ndvi_scenes": avg_ndvi,
        "avg_rainfall_mm": avg_rainfall_mm,
        "sustainability_score": sustainability_score,
    }
