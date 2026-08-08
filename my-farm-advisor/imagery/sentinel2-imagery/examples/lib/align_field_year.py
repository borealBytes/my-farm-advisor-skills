#!/usr/bin/env python3
"""Reusable field-year alignment logic for NDVI + weather + CDL dashboards.

Pure data-preparation module. No plotting here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask


# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------
_DEFAULT_SEASON_START_DOY = 60
_DEFAULT_SEASON_END_DOY = 320
_DEFAULT_GDD_BASE = 10.0

_DEFAULT_HEAVY_RAIN_MM = 25.0
_DEFAULT_HOT_DAY_C = 35.0
_DEFAULT_COOL_PERIOD_DAYS = 3
_DEFAULT_COOL_PERIOD_MAX_C = 10.0
_DEFAULT_DRY_SPELL_DAYS = 14
_DEFAULT_DRY_SPELL_MM = 1.0

_DEFAULT_NDVI_RAPID_INCREASE = 0.15
_DEFAULT_NDVI_SIGNIFICANT_DIP = 0.10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CropInfo:
    name: str
    code: int
    pixel_count: int
    pct: float


@dataclass
class Event:
    event_type: str
    doy: int
    value: float | None = None
    description: str = ""
    panels: List[str] = field(default_factory=list)


@dataclass
class QualityFlags:
    weather_complete: bool = False
    ndvi_sufficient: bool = False
    ndvi_gap_critical: bool = False
    low_coverage_scenes: List[int] = field(default_factory=list)


@dataclass
class AlignedFieldYear:
    field_id: str
    year: int
    crop: CropInfo
    season_start_doy: int
    season_end_doy: int
    weather_df: pd.DataFrame
    ndvi_df: pd.DataFrame
    events_weather: List[Event]
    events_ndvi: List[Event]
    events_linked: List[Event]
    quality: QualityFlags
    summary: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _runtime_root() -> Path:
    return Path("/home/coder/my-farm-advisor-runtime/data-pipeline")


def _field_dir(grower: str, farm: str, field_slug: str) -> Path:
    return _runtime_root() / "growers" / grower / "farms" / farm / "fields" / field_slug


def _boundary_path(grower: str, farm: str, field_slug: str) -> Path:
    return _field_dir(grower, farm, field_slug) / "boundary" / "field_boundary.geojson"


def _weather_path(grower: str, farm: str, field_slug: str) -> Path:
    return _field_dir(grower, farm, field_slug) / "weather" / "daily_weather.csv"


def _cdl_path(grower: str, farm: str, year: int) -> Path:
    farm_slug = farm
    prefix = farm_slug.replace("-", "_")
    if prefix.endswith("_farm"):
        prefix = prefix[: -len("_farm")]
    return (
        _runtime_root()
        / "growers"
        / grower
        / "farms"
        / farm
        / "derived"
        / "tables"
        / f"{prefix}_{year}_cdl.csv"
    )


def _satellite_dirs(grower: str, farm: str, field_slug: str, year: int) -> List[Path]:
    base = _field_dir(grower, farm, field_slug) / "satellite"
    candidates = []
    for source in ("sentinel", "landsat"):
        d = base / source / str(year)
        if d.exists():
            candidates.append((source, d))
    return candidates


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_cdl_crop(grower: str, farm: str, field_id: str, year: int) -> CropInfo:
    path = _cdl_path(grower, farm, year)
    df = pd.read_csv(path)
    fc = df[df["field_id"] == field_id].copy()
    if fc.empty:
        raise ValueError(f"No CDL records for {field_id} in {year}")
    # Pick the row with highest percentage
    dominant = fc.loc[fc["pct"].idxmax()]
    return CropInfo(
        name=str(dominant["crop_name"]),
        code=int(dominant["crop_code"]),
        pixel_count=int(dominant["pixel_count"]),
        pct=float(dominant["pct"]),
    )


def load_weather(grower: str, farm: str, field_slug: str, year: int) -> pd.DataFrame:
    path = _weather_path(grower, farm, field_slug)
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df = df[df["year"] == year].copy()
    df["doy"] = df["date"].dt.dayofyear
    df = df.sort_values("date").reset_index(drop=True)
    return df


def extract_ndvi_scenes(
    grower: str,
    farm: str,
    field_slug: str,
    year: int,
    boundary_gdf: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    """Scan per-scene TIFFs and return mean NDVI per scene."""
    if boundary_gdf is None:
        boundary_gdf = gpd.read_file(_boundary_path(grower, farm, field_slug))

    rows: List[Dict[str, Any]] = []
    for source, root_dir in _satellite_dirs(grower, farm, field_slug, year):
        for scene_dir in sorted(root_dir.iterdir()):
            if not scene_dir.is_dir():
                continue
            # Parse date from dirname like sentinel_20220530 or landsat_20220530
            name = scene_dir.name
            try:
                date_str = name.split("_")[1]  # yyyymmdd
                scene_date = date(
                    int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
                )
            except Exception:
                continue

            tif_files = list(scene_dir.glob("*_ndvi.tif"))
            if not tif_files:
                continue
            tif = tif_files[0]

            try:
                with rasterio.open(tif) as src:
                    boundary_crs = boundary_gdf.to_crs(src.crs)
                    clipped, _ = mask(
                        src, boundary_crs.geometry, crop=True, filled=False
                    )
                    arr = clipped[0]
                    valid = arr[np.isfinite(arr) & (arr > -1) & (arr < 1)]
                    if len(valid) == 0:
                        continue
                    rows.append(
                        {
                            "date": scene_date,
                            "doy": scene_date.timetuple().tm_yday,
                            "mean_ndvi": float(np.nanmean(valid)),
                            "std_ndvi": float(np.nanstd(valid)),
                            "pixel_count": int(len(valid)),
                            "source": source,
                        }
                    )
            except Exception as exc:
                print(f"  WARNING: skipping {tif}: {exc}")
                continue

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Prefer sentinel when both sources have same date
    df = df.sort_values(["date", "source"])
    df = df.drop_duplicates(subset=["date"], keep="first")
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_weather_metrics(
    weather_df: pd.DataFrame, gdd_base: float = _DEFAULT_GDD_BASE
) -> pd.DataFrame:
    df = weather_df.copy()
    t_avg = (df["T2M_MAX"] + df["T2M_MIN"]) / 2.0
    df["gdd_daily"] = np.maximum(0.0, t_avg - gdd_base)
    df["gdd_cum"] = df["gdd_daily"].cumsum()
    df["precip_cum"] = df["PRECTOTCORR"].cumsum()
    df["t_range"] = df["T2M_MAX"] - df["T2M_MIN"]
    return df


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

def detect_weather_events(
    weather_df: pd.DataFrame,
    *,
    heavy_rain_mm: float = _DEFAULT_HEAVY_RAIN_MM,
    hot_day_c: float = _DEFAULT_HOT_DAY_C,
    cool_period_days: int = _DEFAULT_COOL_PERIOD_DAYS,
    cool_period_max_c: float = _DEFAULT_COOL_PERIOD_MAX_C,
    dry_spell_days: int = _DEFAULT_DRY_SPELL_DAYS,
    dry_spell_mm: float = _DEFAULT_DRY_SPELL_MM,
) -> List[Event]:
    events: List[Event] = []
    df = weather_df.copy().sort_values("doy").reset_index(drop=True)

    # Heavy rain
    for _, row in df[df["PRECTOTCORR"] >= heavy_rain_mm].iterrows():
        events.append(
            Event(
                event_type="heavy_rain",
                doy=int(row["doy"]),
                value=float(row["PRECTOTCORR"]),
                description=f"Heavy rain: {row['PRECTOTCORR']:.1f} mm",
                panels=["precipitation"],
            )
        )

    # Hot days
    for _, row in df[df["T2M_MAX"] >= hot_day_c].iterrows():
        events.append(
            Event(
                event_type="hot_day",
                doy=int(row["doy"]),
                value=float(row["T2M_MAX"]),
                description=f"Hot day: {row['T2M_MAX']:.1f}°C max",
                panels=["temperature"],
            )
        )

    # Cool periods (consecutive)
    cool = df["T2M_MAX"] < cool_period_max_c
    in_streak = False
    streak_start = 0
    for i, is_cool in enumerate(cool):
        if is_cool and not in_streak:
            in_streak = True
            streak_start = i
        elif not is_cool and in_streak:
            in_streak = False
            streak_len = i - streak_start
            if streak_len >= cool_period_days:
                doy_start = int(df.iloc[streak_start]["doy"])
                doy_end = int(df.iloc[i - 1]["doy"])
                events.append(
                    Event(
                        event_type="cool_period",
                        doy=doy_start,
                        value=None,
                        description=f"Cool period: {streak_len} days (DOY {doy_start}–{doy_end})",
                        panels=["temperature"],
                    )
                )
    if in_streak:
        streak_len = len(cool) - streak_start
        if streak_len >= cool_period_days:
            doy_start = int(df.iloc[streak_start]["doy"])
            doy_end = int(df.iloc[-1]["doy"])
            events.append(
                Event(
                    event_type="cool_period",
                    doy=doy_start,
                    value=None,
                    description=f"Cool period: {streak_len} days (DOY {doy_start}–{doy_end})",
                    panels=["temperature"],
                )
            )

    # Dry spells
    dry = df["PRECTOTCORR"] < dry_spell_mm
    in_streak = False
    streak_start = 0
    for i, is_dry in enumerate(dry):
        if is_dry and not in_streak:
            in_streak = True
            streak_start = i
        elif not is_dry and in_streak:
            in_streak = False
            streak_len = i - streak_start
            if streak_len >= dry_spell_days:
                doy_start = int(df.iloc[streak_start]["doy"])
                doy_end = int(df.iloc[i - 1]["doy"])
                events.append(
                    Event(
                        event_type="dry_spell",
                        doy=doy_start,
                        value=None,
                        description=f"Dry spell: {streak_len} days (DOY {doy_start}–{doy_end})",
                        panels=["precipitation"],
                    )
                )
    if in_streak:
        streak_len = len(dry) - streak_start
        if streak_len >= dry_spell_days:
            doy_start = int(df.iloc[streak_start]["doy"])
            doy_end = int(df.iloc[-1]["doy"])
            events.append(
                Event(
                    event_type="dry_spell",
                    doy=doy_start,
                    value=None,
                    description=f"Dry spell: {streak_len} days (DOY {doy_start}–{doy_end})",
                    panels=["precipitation"],
                )
            )

    return events


def detect_ndvi_events(
    ndvi_df: pd.DataFrame,
    *,
    rapid_increase: float = _DEFAULT_NDVI_RAPID_INCREASE,
    significant_dip: float = _DEFAULT_NDVI_SIGNIFICANT_DIP,
) -> List[Event]:
    events: List[Event] = []
    df = ndvi_df.copy().sort_values("doy").reset_index(drop=True)
    if len(df) < 2:
        return events

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        delta = float(curr["mean_ndvi"]) - float(prev["mean_ndvi"])
        doy = int(curr["doy"])

        if delta > rapid_increase:
            events.append(
                Event(
                    event_type="ndvi_rapid_increase",
                    doy=doy,
                    value=float(curr["mean_ndvi"]),
                    description=f"NDVI rapid increase: +{delta:.2f} to {curr['mean_ndvi']:.2f}",
                    panels=["ndvi"],
                )
            )
        elif delta < -significant_dip:
            events.append(
                Event(
                    event_type="ndvi_dip",
                    doy=doy,
                    value=float(curr["mean_ndvi"]),
                    description=f"NDVI dip: {delta:.2f} to {curr['mean_ndvi']:.2f}",
                    panels=["ndvi"],
                )
            )

    # Peak plateau: sustained max across ≥2 scenes
    max_ndvi = df["mean_ndvi"].max()
    peak_rows = df[df["mean_ndvi"] >= max_ndvi - 0.03]
    if len(peak_rows) >= 2:
        events.append(
            Event(
                event_type="ndvi_peak",
                doy=int(peak_rows.iloc[0]["doy"]),
                value=float(max_ndvi),
                description=f"NDVI peak plateau: {max_ndvi:.2f} sustained",
                panels=["ndvi"],
            )
        )

    return events


def link_events(
    ndvi_events: List[Event],
    weather_events: List[Event],
    window_days: int = 7,
) -> List[Event]:
    linked: List[Event] = []
    for ne in ndvi_events:
        for we in weather_events:
            if abs(ne.doy - we.doy) <= window_days:
                linked.append(
                    Event(
                        event_type=f"linked_{ne.event_type}_{we.event_type}",
                        doy=ne.doy,
                        value=ne.value,
                        description=f"{ne.description} near {we.description}",
                        panels=["ndvi", "temperature", "precipitation", "gdd"],
                    )
                )
    return linked


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

def run_quality_checks(
    weather_df: pd.DataFrame, ndvi_df: pd.DataFrame
) -> QualityFlags:
    q = QualityFlags()

    # Weather completeness
    expected_days = 366 if pd.to_datetime(f"{weather_df['year'].iloc[0]}-12-31").year % 4 == 0 else 365
    q.weather_complete = (
        len(weather_df) == expected_days
        and weather_df[["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]].notna().all().all()
        and weather_df["date"].nunique() == len(weather_df)
    )

    # NDVI sufficiency
    q.ndvi_sufficient = len(ndvi_df) >= 5

    # Critical gaps during DOY 90–280
    if len(ndvi_df) >= 2:
        critical = ndvi_df[
            (ndvi_df["doy"] >= 90) & (ndvi_df["doy"] <= 280)
        ].copy()
        if len(critical) >= 2:
            gaps = critical["doy"].diff().dropna()
            q.ndvi_gap_critical = (gaps > 30).any()

    # Low coverage
    q.low_coverage_scenes = ndvi_df[ndvi_df["pixel_count"] < 100]["doy"].tolist()

    return q


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def load_aligned_field_year(
    grower: str,
    farm: str,
    field_slug: str,
    year: int,
    *,
    season_start_doy: int = _DEFAULT_SEASON_START_DOY,
    season_end_doy: int = _DEFAULT_SEASON_END_DOY,
    gdd_base: float = _DEFAULT_GDD_BASE,
    heavy_rain_mm: float = _DEFAULT_HEAVY_RAIN_MM,
    hot_day_c: float = _DEFAULT_HOT_DAY_C,
    cool_period_days: int = _DEFAULT_COOL_PERIOD_DAYS,
    cool_period_max_c: float = _DEFAULT_COOL_PERIOD_MAX_C,
    dry_spell_days: int = _DEFAULT_DRY_SPELL_DAYS,
    dry_spell_mm: float = _DEFAULT_DRY_SPELL_MM,
    ndvi_rapid_increase: float = _DEFAULT_NDVI_RAPID_INCREASE,
    ndvi_significant_dip: float = _DEFAULT_NDVI_SIGNIFICANT_DIP,
    link_window_days: int = 7,
) -> AlignedFieldYear:
    """Load and align all inputs for a single field-year."""

    field_id = field_slug  # runtime uses slug == id in this dataset

    # 1. CDL crop
    crop = load_cdl_crop(grower, farm, field_id, year)

    # 2. Weather
    weather_raw = load_weather(grower, farm, field_slug, year)
    weather = compute_weather_metrics(weather_raw, gdd_base=gdd_base)

    # 3. NDVI scenes
    boundary_gdf = gpd.read_file(_boundary_path(grower, farm, field_slug))
    ndvi = extract_ndvi_scenes(grower, farm, field_slug, year, boundary_gdf=boundary_gdf)

    # 4. Season filter
    weather = weather[
        (weather["doy"] >= season_start_doy) & (weather["doy"] <= season_end_doy)
    ].copy()
    ndvi = ndvi[
        (ndvi["doy"] >= season_start_doy) & (ndvi["doy"] <= season_end_doy)
    ].copy()

    # 5. Events
    events_w = detect_weather_events(
        weather,
        heavy_rain_mm=heavy_rain_mm,
        hot_day_c=hot_day_c,
        cool_period_days=cool_period_days,
        cool_period_max_c=cool_period_max_c,
        dry_spell_days=dry_spell_days,
        dry_spell_mm=dry_spell_mm,
    )
    events_n = detect_ndvi_events(
        ndvi,
        rapid_increase=ndvi_rapid_increase,
        significant_dip=ndvi_significant_dip,
    )
    events_l = link_events(events_n, events_w, window_days=link_window_days)

    # 6. Quality
    quality = run_quality_checks(weather_raw, ndvi)

    # 7. Summary
    summary = {
        "total_precip_mm": float(weather["PRECTOTCORR"].sum()),
        "avg_gdd_daily": float(weather["gdd_daily"].mean()),
        "max_cum_gdd": float(weather["gdd_cum"].max()),
        "ndvi_peak": float(ndvi["mean_ndvi"].max()) if not ndvi.empty else np.nan,
        "ndvi_peak_doy": int(ndvi.loc[ndvi["mean_ndvi"].idxmax(), "doy"]) if not ndvi.empty else None,
        "scene_count": int(len(ndvi)),
        "lat": float(weather["lat"].iloc[0]) if not weather.empty else None,
        "lon": float(weather["lon"].iloc[0]) if not weather.empty else None,
    }

    return AlignedFieldYear(
        field_id=field_id,
        year=year,
        crop=crop,
        season_start_doy=season_start_doy,
        season_end_doy=season_end_doy,
        weather_df=weather,
        ndvi_df=ndvi,
        events_weather=events_w,
        events_ndvi=events_n,
        events_linked=events_l,
        quality=quality,
        summary=summary,
    )
