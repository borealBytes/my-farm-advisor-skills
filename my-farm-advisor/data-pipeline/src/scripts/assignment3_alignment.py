#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false
"""
Assignment 3 - Weather & NDVI alignment for single field-year.

Loads daily_weather.csv and Sentinel-2 NDVI rasters for the selected field-year,
aligns them on a shared date axis, computes derived variables (precipitation,
temperature extremes, cumulative soybean GDD), detects notable seasonal events,
and saves aligned outputs for dashboard use.

Input:  Field-level daily_weather.csv + Sentinel-2 per-date NDVI TIFs.
Output: Aligned CSV table + event records JSON under field derived/reports/.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from lib.paths import (  # noqa: E402
    field_boundary_path,
    field_reports_dir,
    field_satellite_dir,
    field_weather_path,
    ensure_parent,
)

# -- Approved field-year constants --
GROWER = "northern-illinois-grower"
FARM = "northern-illinois-grower-illinois"
FIELD = "osm-1499474531"
YEAR = 2025
CROP = "Soybeans"

# -- GDD parameters --
GDD_BASE = 10.0

# -- Soybean growth-stage GDD thresholds (literature-based, Pedersen / ISU extension) --
SOYBEAN_STAGES = {
    "VE (emergence)": 130,
    "V1 (1st trifoliate)": 230,
    "R1 (beginning bloom)": 500,
    "R3 (beginning pod)": 700,
    "R5 (beginning seed)": 900,
    "R7 (beginning maturity)": 1400,
}


def load_weather_2025() -> pd.DataFrame:
    weather_path = field_weather_path(GROWER, FARM, FIELD)
    if not weather_path.exists():
        raise FileNotFoundError(f"Weather file not found: {weather_path}")

    df = pd.read_csv(weather_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df_2025 = df[df["date"].dt.year == YEAR].copy()
    return df_2025


def load_sentinel_ndvi() -> pd.DataFrame:
    sentinel_dir = field_satellite_dir(GROWER, FARM, FIELD) / "sentinel" / str(YEAR)
    if not sentinel_dir.exists():
        raise FileNotFoundError(f"Sentinel directory not found: {sentinel_dir}")

    records = []
    for date_dir in sorted(sentinel_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        ndvi_tif = date_dir / f"{date_dir.name}_ndvi.tif"
        if not ndvi_tif.exists():
            records.append(
                {
                    "date_dir": date_dir.name,
                    "date": None,
                    "mean_ndvi": None,
                    "valid_pixels": 0,
                    "error": "NDVI TIF missing",
                }
            )
            continue

        try:
            with rasterio.open(ndvi_tif) as src:
                data = src.read(1, masked=True)
                valid = data.count()
                mean_val = float(data.mean()) if valid > 0 else float("nan")
                dt_str = date_dir.name.split("_", 1)[1]
                try:
                    dt = pd.Timestamp(f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}")
                except (ValueError, IndexError):
                    dt = None
                records.append(
                    {
                        "date_dir": date_dir.name,
                        "date": dt,
                        "mean_ndvi": mean_val,
                        "valid_pixels": valid,
                        "error": None,
                    }
                )
        except Exception as e:
            records.append(
                {
                    "date_dir": date_dir.name,
                    "date": None,
                    "mean_ndvi": None,
                    "valid_pixels": 0,
                    "error": str(e),
                }
            )

    ndvi_df = pd.DataFrame(records)
    ndvi_df["date"] = pd.to_datetime(ndvi_df["date"])
    return ndvi_df


def validate_weather(weather: pd.DataFrame) -> list[str]:
    warnings = []

    expected = pd.date_range(start=f"{YEAR}-01-01", end=f"{YEAR}-12-31", freq="D")
    missing = expected.difference(weather["date"])
    if len(missing) > 0:
        warnings.append(
            f"Missing weather dates ({len(missing)}): "
            + ", ".join(d.strftime("%Y-%m-%d") for d in sorted(missing)[:10])
            + ("..." if len(missing) > 10 else "")
        )

    null_cols = {}
    for col in ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]:
        null_count = weather[col].isna().sum()
        if null_count > 0:
            null_cols[col] = int(null_count)
    if null_cols:
        warnings.append(f"Null values in weather columns: {null_cols}")

    dups = weather["date"].duplicated()
    if dups.any():
        warnings.append(f"Duplicate weather dates: {int(dups.sum())}")

    return warnings


def validate_ndvi(ndvi: pd.DataFrame) -> list[str]:
    warnings = []
    valid_ndvi = ndvi[ndvi["date"].notna() & ndvi["mean_ndvi"].notna()]
    n_valid = len(valid_ndvi)

    if n_valid == 0:
        warnings.append("No valid NDVI observations found")
    else:
        coverage_months = sorted(int(m) for m in valid_ndvi["date"].dt.month.unique())
        warnings.append(
            f"NDVI coverage: {n_valid} scenes across months {coverage_months}"
            f" ({valid_ndvi['date'].min().date()} to {valid_ndvi['date'].max().date()})"
        )

    errors = ndvi[ndvi["error"].notna()]
    if len(errors) > 0:
        for _, row in errors.iterrows():
            warnings.append(f"NDVI raster error [{row['date_dir']}]: {row['error']}")

    dups = ndvi[ndvi["date"].notna()]
    if dups["date"].duplicated().any():
        warnings.append("Duplicate NDVI observation dates detected")

    return warnings


def compute_derived(weather: pd.DataFrame) -> pd.DataFrame:
    df = weather.copy()

    df["precip_mm"] = df["PRECTOTCORR"]
    df["temp_avg_c"] = df["T2M"]
    df["temp_max_c"] = df["T2M_MAX"]
    df["temp_min_c"] = df["T2M_MIN"]

    df["GDD"] = np.maximum(0, (df["T2M_MAX"] + df["T2M_MIN"]) / 2 - GDD_BASE)
    df["GDD_cumsum"] = df["GDD"].cumsum()

    return df


def detect_events(
    weather: pd.DataFrame, ndvi_valid: pd.DataFrame
) -> tuple[list[dict], list[str]]:
    events = []
    warnings = []

    precip = weather["PRECTOTCORR"].values
    tmax = weather["T2M_MAX"].values
    tmin = weather["T2M_MIN"].values
    dates = weather["date"]

    # -- Precipitation events --
    precip_95 = float(np.percentile(precip, 95))
    heavy_idx = np.where(precip >= precip_95)[0]
    for i in heavy_idx:
        if precip[i] > 0:
            events.append(
                {
                    "date": str(dates.iloc[i].date()),
                    "event_type": "heavy_rainfall",
                    "value": round(float(precip[i]), 2),
                    "unit": "mm/day",
                    "annotation": f"Heavy rain: {precip[i]:.1f} mm",
                    "threshold": round(precip_95, 2),
                }
            )

    # -- Hot days --
    tmax_90 = float(np.percentile(tmax, 90))
    hot_idx = np.where(tmax >= tmax_90)[0]
    for i in hot_idx:
        events.append(
            {
                "date": str(dates.iloc[i].date()),
                "event_type": "hot_day",
                "value": round(float(tmax[i]), 2),
                "unit": "°C",
                "annotation": f"Hot day: {tmax[i]:.1f}°C",
                "threshold": round(tmax_90, 2),
            }
        )

    # -- Cool periods: 3+ consecutive days with T2M_MIN < 5th percentile --
    tmin_5 = float(np.percentile(tmin, 5))
    cool_mask = tmin < tmin_5
    n = len(cool_mask)
    i = 0
    while i < n:
        if cool_mask[i]:
            start = i
            while i < n and cool_mask[i]:
                i += 1
            length = i - start
            if length >= 3:
                start_date = str(dates.iloc[start].date())
                end_date = str(dates.iloc[i - 1].date())
                vals = [round(float(tmin[j]), 1) for j in range(start, i)]
                events.append(
                    {
                        "date_start": start_date,
                        "date_end": end_date,
                        "event_type": "cool_period",
                        "value": round(float(np.mean(vals)), 2),
                        "unit": "°C",
                        "annotation": (
                            f"Cool spell ({length}d): "
                            f"mean Tmin {np.mean(vals):.1f}°C"
                        ),
                        "threshold": round(tmin_5, 2),
                        "duration_days": length,
                    }
                )
            i += 1
        else:
            i += 1

    # -- NDVI events --
    if len(ndvi_valid) >= 2:
        ndvi_sorted = ndvi_valid.sort_values("date").reset_index(drop=True)
        ndvi_vals = ndvi_sorted["mean_ndvi"].values
        ndvi_dates = ndvi_sorted["date"]

        # Rapid NDVI increase (max positive delta)
        deltas = np.diff(ndvi_vals)
        delta_pairs = [(deltas[j], j) for j in range(len(deltas))]
        delta_pairs.sort(key=lambda x: x[0], reverse=True)

        for delta, idx in delta_pairs[:3]:
            if delta > 0.01:
                events.append(
                    {
                        "date_start": str(ndvi_dates.iloc[idx].date()),
                        "date_end": str(ndvi_dates.iloc[idx + 1].date()),
                        "event_type": "rapid_ndvi_increase",
                        "value": round(float(delta), 4),
                        "unit": "ΔNDVI",
                        "annotation": f"Rapid NDVI increase: +{delta:.3f}",
                    }
                )

        # NDVI peak
        peak_idx = int(np.argmax(ndvi_vals))
        events.append(
            {
                "date": str(ndvi_dates.iloc[peak_idx].date()),
                "event_type": "ndvi_peak",
                "value": round(float(ndvi_vals[peak_idx]), 4),
                "unit": "NDVI",
                "annotation": f"Peak NDVI: {ndvi_vals[peak_idx]:.3f}",
            }
        )

        # Sustained NDVI decline (after peak, find first drop that continues)
        if peak_idx < len(ndvi_vals) - 1:
            decline_idx = None
            for j in range(peak_idx, len(ndvi_vals) - 1):
                if ndvi_vals[j + 1] < ndvi_vals[j]:
                    decline_idx = j
                    break
            if decline_idx is not None:
                events.append(
                    {
                        "date_start": str(ndvi_dates.iloc[decline_idx].date()),
                        "date_end": str(ndvi_dates.iloc[-1].date()),
                        "event_type": "ndvi_decline",
                        "value": round(float(ndvi_vals[decline_idx] - ndvi_vals[-1]), 4),
                        "unit": "ΔNDVI",
                        "annotation": (
                            f"Sustained NDVI decline: "
                            f"{ndvi_vals[decline_idx]:.3f} → {ndvi_vals[-1]:.3f}"
                        ),
                    }
                )
    else:
        warnings.append("Too few NDVI observations for event detection")

    return events, warnings


def confirm_cdl_crop() -> tuple[str, str]:
    import csv as _csv

    base_path = Path(field_weather_path(GROWER, FARM, FIELD)).parents[1]
    ndvi_join = base_path / "derived" / "tables" / "ndvi_year_crop_join.csv"
    if not ndvi_join.exists():
        return CROP, f"CDL join table not found at {ndvi_join}"

    with open(ndvi_join) as f:
        for row in _csv.DictReader(f):
            if int(row["year"]) == YEAR:
                return row["crop_name"], ""

    return CROP, f"No CDL entry for year {YEAR}"


def main():
    print("=" * 60)
    print(f"Assignment 3: Weather & NDVI Alignment")
    print(f"  Grower: {GROWER}")
    print(f"  Farm:   {FARM}")
    print(f"  Field:  {FIELD}")
    print(f"  Year:   {YEAR}")
    print("=" * 60)

    reports_dir = field_reports_dir(GROWER, FARM, FIELD)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ---- Confirm CDL crop ----
    print("\n[1] Confirming CDL crop...")
    detected_crop, cdl_warning = confirm_cdl_crop()
    print(f"    CDL crop: {detected_crop}")
    if cdl_warning:
        print(f"    WARNING: {cdl_warning}")

    # ---- Load weather ----
    print("\n[2] Loading daily weather for 2025...")
    weather = load_weather_2025()
    print(f"    Loaded {len(weather)} weather records")
    print(f"    Date range: {weather['date'].min().date()} to {weather['date'].max().date()}")

    # ---- Load Sentinel NDVI ----
    print("\n[3] Loading Sentinel-2 NDVI observations...")
    ndvi = load_sentinel_ndvi()
    ndvi_valid = ndvi[ndvi["date"].notna() & ndvi["mean_ndvi"].notna()].copy()
    n_total = len(ndvi)
    n_valid = len(ndvi_valid)
    print(f"    Total scene dirs found: {n_total}")
    print(f"    Successfully extracted: {n_valid}")
    if n_valid > 0:
        print(f"    NDVI range: {ndvi_valid['mean_ndvi'].min():.4f} - {ndvi_valid['mean_ndvi'].max():.4f}")
        print(f"    Dates: {[d.strftime('%Y-%m-%d') for d in sorted(ndvi_valid['date'])]}")

    # ---- Validate ----
    print("\n[4] Running validation checks...")
    all_warnings = []
    weather_warnings = validate_weather(weather)
    ndvi_warnings = validate_ndvi(ndvi)
    all_warnings.extend(weather_warnings)
    all_warnings.extend(ndvi_warnings)
    for w in all_warnings:
        print(f"    ⚠  {w}")

    # ---- Compute derived variables ----
    print("\n[5] Computing derived weather variables...")
    weather = compute_derived(weather)
    seasonal_gdd = weather["GDD_cumsum"].max()
    print(f"    Cumulative seasonal GDD (base {GDD_BASE}°C): {seasonal_gdd:.1f}")
    print(f"    Soybean growth stage estimates:")
    for stage_name, gdd_thresh in SOYBEAN_STAGES.items():
        reached = weather[weather["GDD_cumsum"] >= gdd_thresh]
        if len(reached) > 0:
            stage_date = reached.iloc[0]["date"].strftime("%Y-%m-%d")
            print(f"      {stage_name:30s} ≈ {stage_date}  ({gdd_thresh} GDD)")

    # ---- Detect events ----
    print("\n[6] Detecting notable seasonal events...")
    events, event_warnings = detect_events(weather, ndvi_valid)
    all_warnings.extend(event_warnings)
    for w in event_warnings:
        print(f"    ⚠  {w}")

    event_types = {}
    for ev in events:
        et = ev["event_type"]
        event_types[et] = event_types.get(et, 0) + 1
    print(f"    Events detected: {len(events)}")
    for et, count in sorted(event_types.items()):
        print(f"      {et}: {count}")

    # ---- Align on shared date axis ----
    print("\n[7] Building aligned time-series table...")
    aligned = weather[["date", "precip_mm", "temp_avg_c", "temp_max_c",
                        "temp_min_c", "GDD", "GDD_cumsum"]].copy()
    ndvi_map = dict(zip(ndvi_valid["date"], ndvi_valid["mean_ndvi"]))
    aligned["ndvi"] = aligned["date"].map(ndvi_map)

    # ---- Save outputs ----
    print("\n[8] Saving outputs...")
    aligned_path = reports_dir / "assignment3_aligned_data.csv"
    aligned.to_csv(aligned_path, index=False)
    print(f"    Aligned data: {aligned_path} ({len(aligned)} rows)")

    events_path = reports_dir / "assignment3_events.json"
    with open(events_path, "w") as f:
        json.dump(
            {
                "field": FIELD,
                "grower": GROWER,
                "year": YEAR,
                "crop": detected_crop,
                "seasonal_gdd": round(seasonal_gdd, 1),
                "gdd_base": GDD_BASE,
                "n_weather_records": len(weather),
                "n_ndvi_scenes": n_total,
                "n_ndvi_valid": n_valid,
                "n_events": len(events),
                "events": events,
                "warnings": all_warnings,
            },
            f,
            indent=2,
        )
    print(f"    Event records: {events_path}")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Weather records loaded:      {len(weather)}")
    print(f"  NDVI scenes extracted:       {n_valid} (of {n_total} dirs)")
    print(f"  Seasonal GDD (base {GDD_BASE}°C): {seasonal_gdd:.1f}")
    print(f"  Events detected:             {len(events)}")
    print(f"  Warnings:                    {len(all_warnings)}")
    print(f"  Files created:")
    print(f"    {aligned_path}")
    print(f"    {events_path}")
    print()

    if all_warnings:
        print("WARNINGS:")
        for w in all_warnings:
            print(f"  ⚠  {w}")

    print("\n✓ Alignment complete.")


if __name__ == "__main__":
    main()
