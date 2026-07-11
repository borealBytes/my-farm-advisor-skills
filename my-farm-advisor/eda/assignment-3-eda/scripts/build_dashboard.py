#!/usr/bin/env python3
"""build_dashboard.py — Assignment 3 EDA Dashboard

Produces a 4-panel aligned dashboard for a single field-year:
  1. NDVI time series
  2. Daily precipitation
  3. Temperature extremes
  4. Cumulative GDD (base 50°F)

Usage:
  export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
  python3 build_dashboard.py
"""

import os
import sys
import json
import math
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask
from rasterio.crs import CRS
from rasterio.warp import transform_geom
from shapely.geometry import shape, box, mapping
from shapely.ops import transform as shapely_transform
import pyproj

from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

# ---------------------------------------------------------------------------
# CONFIGURATION  (change these for a different field-year)
# ---------------------------------------------------------------------------
FIELD_SLUG = "osm-1467726055"
YEAR = 2024
GROWER_SLUG = "nebraska-grower"
FARM_SLUG = "nebraska-farm"

DATA_ROOT = Path(
    os.environ.get("DATA_PIPELINE_DATA_ROOT", os.path.expanduser("~/my-farm-advisor-runtime"))
)
PIPELINE = DATA_ROOT / "data-pipeline"
FIELD_DIR = PIPELINE / "growers" / GROWER_SLUG / "farms" / FARM_SLUG / "fields" / FIELD_SLUG
FARM_DIR = PIPELINE / "growers" / GROWER_SLUG / "farms" / FARM_SLUG
OUTPUT_DIR = Path(os.path.expanduser("~/my-farm-advisor-runtime")) / "eda-outputs" / "assignment-3"

# Event detection thresholds
HEAVY_RAIN_MM = 20
HOT_DAY_C = 35
COOL_DAY_C = 0
NDVI_DROP = 0.15
NDVI_GAIN = 0.20
NDVI_GAP_DAYS = 40

# Corn growth stage GDD targets (base 50°F)
GROWTH_STAGES = [
    ("Planting",   150),
    ("Emergence",  250),
    ("V6",         475),
    ("V12",        750),
    ("VT",        1200),
    ("R1",        1400),
    ("R2",        1700),
    ("R5",        2300),
    ("R6",        2700),
]

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def gdd_f(tmax_c, tmin_c):
    """Growing degree days base 50°F."""
    tmax_f = tmax_c * 9.0 / 5.0 + 32.0
    tmin_f = tmin_c * 9.0 / 5.0 + 32.0
    return max(0.0, (tmax_f + tmin_f) / 2.0 - 50.0)


def parse_scene_date(folder_name):
    """Extract date from folder like sentinel_20240317 → date(2024,3,17)."""
    parts = folder_name.split("_")
    for p in parts:
        if len(p) == 8 and p.isdigit():
            return datetime.strptime(p, "%Y%m%d").date()
    return None


def load_geojson(path):
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------

def load_weather(field_dir, year):
    """Return DataFrame with daily weather for the given year."""
    path = field_dir / "weather" / "daily_weather.csv"
    if not path.exists():
        print(f"[ERROR] Weather file not found: {path}")
        sys.exit(1)
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df = df[df["year"] == year].copy()
    df = df.sort_values("date").reset_index(drop=True)
    return df


def load_ndvi_scenes(field_dir, year):
    """Walk sentinel folder, read each NDVI raster, return per-scene DataFrame."""
    sentinel_dir = field_dir / "satellite" / "sentinel" / str(year)
    if not sentinel_dir.exists():
        print(f"[ERROR] Sentinel dir not found: {sentinel_dir}")
        sys.exit(1)

    rows = []
    folders = sorted(sentinel_dir.iterdir())
    for fpath in folders:
        if not fpath.is_dir():
            continue
        scene_date = parse_scene_date(fpath.name)
        if scene_date is None:
            continue
        ndvi_files = list(fpath.glob("*_ndvi.tif"))
        if not ndvi_files:
            continue
        ndvi_path = ndvi_files[0]
        try:
            with rasterio.open(ndvi_path) as src:
                arr = src.read(1, masked=True)
                valid = arr[~arr.mask]
                if len(valid) == 0:
                    continue
                rows.append({
                    "date": scene_date,
                    "ndvi_mean": float(valid.mean()),
                    "ndvi_std": float(valid.std()),
                    "ndvi_min": float(valid.min()),
                    "ndvi_max": float(valid.max()),
                    "ndvi_count": int(valid.size - arr.mask.sum()),
                    "scene": fpath.name,
                })
        except Exception as e:
            print(f"  [WARN] Could not read {ndvi_path}: {e}")

    out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return out


def load_cdl(farm_dir, field_id, year):
    """Return CDL crop dict for the field-year."""
    tables_dir = farm_dir / "derived" / "tables"
    if not tables_dir.exists():
        print(f"[WARN] Tables dir not found: {tables_dir}")
        return None
    # CDL files follow pattern: {farm_slug}_{year}_cdl.csv or {grower}_{year}_cdl.csv
    candidates = sorted(tables_dir.glob(f"*_{year}_cdl.csv"))
    if not candidates:
        print(f"[WARN] No CDL file found for year {year} in {tables_dir}")
        return None
    path = candidates[0]
    df = pd.read_csv(path)
    row = df[df["field_id"] == field_id]
    if row.empty:
        print(f"[WARN] Field {field_id} not found in CDL table {path.name}")
        return None
    dominant = row.loc[row["pct"].idxmax()]
    return {
        "crop_code": int(dominant["crop_code"]),
        "crop_name": dominant["crop_name"],
        "pct": float(dominant["pct"]),
        "pixel_count": int(dominant["pixel_count"]),
    }


def load_soil(field_dir):
    """Return dict of soil summary values."""
    path = field_dir / "soil" / "ssurgo_summary.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    r = df.iloc[0]
    return {
        "om": r.get("avg_om_pct", "—"),
        "ph": r.get("avg_ph", "—"),
        "cec": r.get("avg_cec", "—"),
        "clay": r.get("avg_clay_pct", "—"),
        "sand": r.get("avg_sand_pct", "—"),
        "aws": r.get("total_aws_inches", "—"),
        "drainage": r.get("drainage_class", "—"),
        "dominant_soil": r.get("dominant_soil", "—"),
    }


def load_field_boundary(field_dir):
    """Load field boundary, return centroid coords and acres."""
    path = field_dir / "boundary" / "field_boundary.geojson"
    if not path.exists():
        return None, None
    fc = load_geojson(path)
    if not fc["features"]:
        return None, None
    geom_wgs84 = shape(fc["features"][0]["geometry"])
    centroid = (geom_wgs84.centroid.y, geom_wgs84.centroid.x)
    # Reproject to UTM for accurate area
    lon, lat = geom_wgs84.centroid.x, geom_wgs84.centroid.y
    utm_zone = int((lon + 180) / 6) + 1
    crs_wgs84 = CRS.from_epsg(4326)
    crs_utm = CRS.from_epsg(32600 + utm_zone)  # Northern hemisphere
    project = pyproj.Transformer.from_crs(crs_wgs84, crs_utm, always_xy=True).transform
    geom_utm = shapely_transform(project, geom_wgs84)
    acres = geom_utm.area * 0.000247105  # sq meters to acres
    return centroid, acres


# ---------------------------------------------------------------------------
# METRICS & EVENTS
# ---------------------------------------------------------------------------

def compute_metrics(df):
    """Add GDD, cumulative, and rolling columns."""
    df = df.copy()
    df["gdd_f"] = df.apply(lambda r: gdd_f(r["T2M_MAX"], r["T2M_MIN"]), axis=1)
    df["cum_gdd"] = df["gdd_f"].cumsum()
    df["cum_precip"] = df["PRECTOTCORR"].cumsum()
    df["precip_7d"] = df["PRECTOTCORR"].rolling(7, min_periods=1).sum()
    return df


def detect_events(weather_df, ndvi_df):
    """Return list of event dicts."""
    events = []

    # Heavy rain — top 3 events by volume
    heavy = weather_df[weather_df["PRECTOTCORR"] >= HEAVY_RAIN_MM].nlargest(3, "PRECTOTCORR")
    labels = ["heaviest", "2nd heaviest", "3rd heaviest"]
    for i, (_, r) in enumerate(heavy.iterrows()):
        events.append({
            "type": "heavy_rain",
            "date": r["date"],
            "label": f'{r["PRECTOTCORR"]:.0f}mm — {labels[i]} rainfall',
        })

    # Hot days — report hottest single day and heat waves (3+ consecutive)
    hot = weather_df[weather_df["T2M_MAX"] >= HOT_DAY_C].copy()
    if not hot.empty:
        hottest = hot.loc[hot["T2M_MAX"].idxmax()]
        events.append({
            "type": "hot_day",
            "date": hottest["date"],
            "label": f'{hottest["T2M_MAX"]:.1f}°C max — hottest day',
        })
        # Heat waves: 3+ consecutive hot days
        hot["is_hot"] = True
        groups = (hot["date"].diff() != pd.Timedelta(days=1)).cumsum()
        for _, grp in hot.groupby(groups):
            if len(grp) >= 3:
                events.append({
                    "type": "hot_wave",
                    "date": grp["date"].iloc[0],
                    "label": f'{len(grp)}-day heat wave (≥35°C max)',
                })

    # Cool periods (3+ consecutive days with min <= 0°C, Mar–May only)
    spring = weather_df[weather_df["date"].dt.month.isin([3, 4, 5])].copy()
    spring["cool"] = spring["T2M_MIN"] <= COOL_DAY_C
    if spring["cool"].any():
        groups = (spring["cool"] != spring["cool"].shift()).cumsum()
        for _, grp in spring[spring["cool"]].groupby(groups):
            if len(grp) >= 3:
                events.append({
                    "type": "cool_period",
                    "date": grp["date"].iloc[0],
                    "label": f'{len(grp)} days ≤0°C min (late frost risk)',
                })

    # NDVI events
    if len(ndvi_df) >= 2:
        for i in range(1, len(ndvi_df)):
            prev = ndvi_df.iloc[i - 1]
            cur = ndvi_df.iloc[i]
            delta = cur["ndvi_mean"] - prev["ndvi_mean"]
            days = (cur["date"] - prev["date"]).days
            if delta >= NDVI_GAIN:
                events.append({
                    "type": "ndvi_gain",
                    "date": cur["date"],
                    "label": f'NDVI +{delta:.2f} in {days}d — rapid increase',
                })
            elif delta <= -NDVI_DROP:
                events.append({
                    "type": "ndvi_drop",
                    "date": cur["date"],
                    "label": f'NDVI {delta:.2f} in {days}d — decline',
                })
            if days >= NDVI_GAP_DAYS:
                window = f"{prev['date'].strftime('%b %d')}–{cur['date'].strftime('%b %d')}"
                events.append({
                    "type": "ndvi_gap",
                    "date": cur["date"],
                    "label": f'{days}d scene gap ({window}) — grain fill unobserved',
                })

    return events


def find_growth_stage_dates(df):
    """Given daily DataFrame with cum_gdd, find approx dates for each stage."""
    results = []
    for stage_name, target_gdd in GROWTH_STAGES:
        subset = df[df["cum_gdd"] >= target_gdd]
        if not subset.empty:
            row = subset.iloc[0]
            results.append((stage_name, target_gdd, row["date"]))
        else:
            results.append((stage_name, target_gdd, None))
    return results


def compute_drought_context(field_dir, target_year):
    """Compute monthly precip anomaly for target_year vs 5-year baseline.
    
    Returns (month_name, anomaly_pct, label) or None if insufficient data.
    Uses available weather record (2021-2025) — not a 30-yr climatology.
    """
    path = field_dir / "weather" / "daily_weather.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    years_avail = sorted(df["year"].unique())
    if target_year not in years_avail or len(years_avail) < 2:
        return None

    monthly = df.groupby(["year", "month"])["PRECTOTCORR"].sum().reset_index()
    baseline = monthly[monthly["year"] != target_year].groupby("month")["PRECTOTCORR"].mean()
    this_year = monthly[monthly["year"] == target_year].set_index("month")["PRECTOTCORR"]

    anomalies = []
    for m in sorted(set(baseline.index) & set(this_year.index)):
        avg = baseline[m]
        val = this_year[m]
        if avg > 0:
            pct = (val - avg) / avg * 100
            anomalies.append((m, pct, val, avg))

    if not anomalies:
        return None

    # Pick the most extreme anomaly, preferring growing season (Apr–Sep)
    month_map = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                 7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    growing = [a for a in anomalies if a[0] in range(4, 10)]
    other = [a for a in anomalies if a[0] not in range(4, 10)]
    best = max(growing, key=lambda x: abs(x[1])) if growing else max(other, key=lambda x: abs(x[1]))
    adverb = "wettest" if best[1] > 0 else "driest"
    season_note = "" if best[0] in range(4, 10) else " (post-season)"
    label = (f"{month_map[best[0]]}: {best[2]:.0f}mm ({best[1]:+.0f}% vs "
             f"5-yr avg {best[3]:.0f}mm) — {adverb} month{season_note}")
    return (month_map[best[0]], best[1], label)


def save_events_json(events, output_dir, field_slug, year):
    """Save detected events as machine-readable JSON."""
    records = []
    for ev in events:
        d = ev["date"]
        records.append({
            "type": ev["type"],
            "date": d.strftime("%Y-%m-%d"),
            "doy": d.timetuple().tm_yday,
            "label": ev["label"],
        })
    path = output_dir / f"events_{field_slug}_{year}.json"
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"  Events saved: {path}")


# ---------------------------------------------------------------------------
# DASHBOARD BUILDER
# ---------------------------------------------------------------------------

def build_dashboard(weather_df, ndvi_df, cdl_info, soil_info, centroid, acres,
                    events, stage_dates, output_path, drought_ctx=None):
    """Generate 4-panel aligned dashboard and save to output_path."""

    fig, axes = plt.subplots(4, 1, figsize=(14, 18), sharex=True,
                             gridspec_kw={"hspace": 0.08})
    (ax_ndvi, ax_precip, ax_temp, ax_gdd) = axes

    # -- date axis helpers --
    date_arr = weather_df["date"].values
    date_num = mdates.date2num(date_arr)
    doy_arr = np.array([d.timetuple().tm_yday for d in weather_df["date"]])

    # ------------------------------------------------------------------
    # PANEL 1: NDVI
    # ------------------------------------------------------------------
    ax = ax_ndvi
    ax.plot(ndvi_df["date"], ndvi_df["ndvi_mean"], "o-", color="#2e7d32",
            linewidth=2, markersize=8, zorder=5, label="Mean NDVI")
    ax.fill_between(ndvi_df["date"],
                    ndvi_df["ndvi_mean"] - ndvi_df["ndvi_std"],
                    ndvi_df["ndvi_mean"] + ndvi_df["ndvi_std"],
                    alpha=0.2, color="#2e7d32", label="±1σ")

    # Growth stage vertical lines
    stage_colors = {"VT": "#e65100", "R1": "#f57c00", "R5": "#ffb74d", "R6": "#a1887f"}
    for sname, sgdd, sdate in stage_dates:
        if sdate and sname in stage_colors:
            ax.axvline(sdate, color=stage_colors[sname], linestyle="--",
                       alpha=0.7, linewidth=1.2)
            ax.annotate(sname, xy=(sdate, ax.get_ylim()[1]),
                        xytext=(0, 6), textcoords="offset points",
                        fontsize=8, color=stage_colors[sname],
                        ha="center", fontweight="bold")

    # NDVI event annotations on the plot
    ndvi_events = [e for e in events if e["type"] in ("ndvi_gain", "ndvi_drop", "ndvi_gap")]
    for ev in ndvi_events:
        y_at_date = None
        if ev["type"] in ("ndvi_gain", "ndvi_drop"):
            match = ndvi_df[ndvi_df["date"] == ev["date"]]
            if not match.empty:
                y_at_date = match.iloc[0]["ndvi_mean"]
        if y_at_date is not None:
            ax.annotate(ev["label"], xy=(ev["date"], y_at_date),
                        xytext=(12, -12), textcoords="offset points",
                        fontsize=7, color="#1b5e20",
                        arrowprops=dict(arrowstyle="->", color="#1b5e20", lw=0.8),
                        bbox=dict(boxstyle="round,pad=0.2", fc="#e8f5e9", ec="#a5d6a7",
                                  alpha=0.9))

    ax.set_ylabel("NDVI (unitless)", fontsize=11)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    ax.set_title(f"1. NDVI Time Series — {FIELD_SLUG} ({YEAR})", loc="left",
                 fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    # NDVI gap shading
    ndvi_events_gap = [e for e in events if e["type"] == "ndvi_gap"]
    for ev in ndvi_events_gap:
        # Find prev scene date
        idx = ndvi_df[ndvi_df["date"] == ev["date"]].index
        if len(idx) > 0 and idx[0] > 0:
            prev_date = ndvi_df.iloc[idx[0] - 1]["date"]
            ax.axvspan(prev_date, ev["date"], color="gray", alpha=0.08)

    # ------------------------------------------------------------------
    # PANEL 2: Precipitation
    # ------------------------------------------------------------------
    ax = ax_precip
    bars = ax.bar(date_arr, weather_df["PRECTOTCORR"].values, width=0.8,
                  color="#1565c0", alpha=0.8, label="Daily precip")
    ax.set_ylabel("Precipitation (mm/day)", fontsize=11)
    ax.set_title("2. Daily Precipitation", loc="left", fontsize=12, fontweight="bold")
    # Cumulative precip as secondary axis
    ax_precip2 = ax.twinx()
    ax_precip2.plot(date_arr, weather_df["cum_precip"].values, color="#004d40",
                    linewidth=1.5, linestyle="--", alpha=0.7, label="Cumulative")
    ax_precip2.set_ylabel("Cumulative (mm)", fontsize=9, color="#004d40")
    ax_precip2.tick_params(axis="y", labelcolor="#004d40", labelsize=8)

    # Heavy rain annotations
    for ev in events:
        if ev["type"] == "heavy_rain":
            y_val = weather_df.loc[weather_df["date"] == ev["date"], "PRECTOTCORR"].values
            if len(y_val) > 0:
                ax.annotate(ev["label"], xy=(ev["date"], y_val[0]),
                            xytext=(0, 14), textcoords="offset points",
                            fontsize=7, color="#0d47a1", ha="center",
                            arrowprops=dict(arrowstyle="->", color="#0d47a1", lw=0.8),
                            bbox=dict(boxstyle="round,pad=0.2", fc="#e3f2fd",
                                      ec="#90caf9", alpha=0.9))
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Drought context annotation (monthly precip anomaly vs 5-yr baseline)
    if drought_ctx is not None:
        _, _, ctx_label = drought_ctx
        ax.annotate(ctx_label, xy=(0.02, 0.95), xycoords="axes fraction",
                    fontsize=7.5, color="#004d40", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#e0f2f1",
                              ec="#80cbc4", alpha=0.9))

    # ------------------------------------------------------------------
    # PANEL 3: Temperature
    # ------------------------------------------------------------------
    ax = ax_temp
    ax.plot(date_arr, weather_df["T2M_MAX"].values, color="#d32f2f", linewidth=1.5,
            label="Tmax", alpha=0.9)
    ax.plot(date_arr, weather_df["T2M_MIN"].values, color="#1976d2", linewidth=1.5,
            label="Tmin", alpha=0.9)
    ax.plot(date_arr, weather_df["T2M"].values, color="#757575", linewidth=1.0,
            label="Tavg", alpha=0.7, linestyle="--")
    ax.axhline(HOT_DAY_C, color="#e53935", linestyle=":", alpha=0.5, linewidth=0.8)
    ax.annotate("35°C heat stress", xy=(date_arr[len(date_arr)//2], HOT_DAY_C),
                fontsize=7, color="#e53935", alpha=0.6, ha="right",
                xytext=(-4, 4), textcoords="offset points")

    ax.set_ylabel("Temperature (°C)", fontsize=11)
    ax.set_title("3. Temperature Extremes", loc="left", fontsize=12, fontweight="bold")

    for ev in events:
        if ev["type"] == "hot_day":
            y_val = weather_df.loc[weather_df["date"] == ev["date"], "T2M_MAX"].values
            if len(y_val) > 0:
                ax.annotate(ev["label"], xy=(ev["date"], y_val[0]),
                            xytext=(8, -14), textcoords="offset points",
                            fontsize=7, color="#b71c1c",
                            arrowprops=dict(arrowstyle="->", color="#b71c1c", lw=0.8),
                            bbox=dict(boxstyle="round,pad=0.2", fc="#ffebee",
                                      ec="#ef9a9a", alpha=0.9))
        elif ev["type"] == "hot_wave":
            y_val = weather_df.loc[weather_df["date"] == ev["date"], "T2M_MAX"].values
            if len(y_val) > 0:
                ax.annotate(ev["label"], xy=(ev["date"], y_val[0]),
                            xytext=(8, -30), textcoords="offset points",
                            fontsize=7, color="#bf360c",
                            arrowprops=dict(arrowstyle="->", color="#bf360c", lw=0.8),
                            bbox=dict(boxstyle="round,pad=0.2", fc="#fbe9e7",
                                      ec="#ffab91", alpha=0.9))
        elif ev["type"] == "cool_period":
            y_val = weather_df.loc[weather_df["date"] == ev["date"], "T2M_MIN"].values
            if len(y_val) > 0:
                ax.annotate(ev["label"], xy=(ev["date"], y_val[0]),
                            xytext=(8, 12), textcoords="offset points",
                            fontsize=7, color="#0d47a1",
                            arrowprops=dict(arrowstyle="->", color="#0d47a1", lw=0.8),
                            bbox=dict(boxstyle="round,pad=0.2", fc="#e8eaf6",
                                      ec="#9fa8da", alpha=0.9))
    ax.legend(loc="upper left", fontsize=9, ncol=3)
    ax.grid(True, alpha=0.3)

    # ------------------------------------------------------------------
    # PANEL 4: Cumulative GDD
    # ------------------------------------------------------------------
    ax = ax_gdd
    ax.fill_between(date_arr, 0, weather_df["cum_gdd"].values,
                    color="#e65100", alpha=0.2)
    ax.plot(date_arr, weather_df["cum_gdd"].values, color="#e65100",
            linewidth=2, label="Cumulative GDD (base 50°F)")

    # Stage markers
    marker_colors = {"Planting": "#795548", "Emergence": "#8d6e63",
                     "V6": "#a1887f", "V12": "#6d4c41",
                     "VT": "#e65100", "R1": "#f57c00",
                     "R2": "#ff9800", "R5": "#ffb74d", "R6": "#a1887f"}
    for sname, sgdd, sdate in stage_dates:
        if sdate:
            ax.axvline(sdate, color=marker_colors.get(sname, "#888"),
                       linestyle="--", alpha=0.5, linewidth=0.8)
            ax.annotate(f"{sname}\n{sgdd} GDD", xy=(sdate, sgdd),
                        xytext=(-8, -22), textcoords="offset points",
                        fontsize=6.5, color=marker_colors.get(sname, "#555"),
                        ha="center", fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color="#888", lw=0.5))

    ax.set_ylabel("Cumulative GDD (°F days)", fontsize=11)
    ax.set_xlabel("Date (2024)", fontsize=11)
    ax.set_title("4. Cumulative Growing Degree Days (Base 50°F)", loc="left",
                 fontsize=12, fontweight="bold")

    # Final GDD annotation
    final_gdd = weather_df["cum_gdd"].iloc[-1]
    ax.annotate(f"Season total: {final_gdd:.0f} GDD",
                xy=(weather_df["date"].iloc[-1], final_gdd),
                xytext=(-120, -18), textcoords="offset points",
                fontsize=8, color="#bf360c", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="#fbe9e7", ec="#ffab91"))

    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    # ------------------------------------------------------------------
    # Date axis formatting (only bottom panel shows labels)
    # ------------------------------------------------------------------
    ax_gdd.xaxis.set_major_locator(mdates.MonthLocator())
    ax_gdd.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax_gdd.xaxis.set_minor_locator(mdates.WeekdayLocator(interval=2))
    ax_gdd.tick_params(axis="x", labelsize=9)

    # ------------------------------------------------------------------
    # HEADER / SUPER TITLE
    # ------------------------------------------------------------------
    cdl_text = f"CDL: {cdl_info['crop_name']} {cdl_info['pct']:.0f}%" if cdl_info else "CDL: —"
    soil_text = ""
    if soil_info:
        soil_text = (f"Soil: {soil_info['dominant_soil']} | "
                     f"OM {soil_info['om']}% | pH {soil_info['ph']} | "
                     f"CEC {soil_info['cec']} | Clay {soil_info['clay']}% | "
                     f"AWC {soil_info['aws']}\" | {soil_info['drainage']}")
    cent_text = f"NE Merrick Co. | {acres:.1f} ac" if acres else "NE Merrick Co."
    fig.suptitle(
        f"Field: {FIELD_SLUG}  |  {cent_text}  |  {cdl_text}\n{soil_text}",
        fontsize=11, fontweight="bold", y=0.975, linespacing=1.4
    )

    # ------------------------------------------------------------------
    # KEY CALLOUTS (footer text box)
    # ------------------------------------------------------------------
    callout_lines = []
    # Pick most notable events (limit to 5, one per type, most impactful)
    event_order = ["ndvi_gain", "ndvi_drop", "ndvi_gap", "heavy_rain",
                   "hot_day", "hot_wave", "cool_period"]
    event_rank = {t: i for i, t in enumerate(event_order)}
    notable = sorted(events, key=lambda e: (event_rank.get(e["type"], 99), e["date"]))
    seen_types = set()
    for ev in notable:
        key = ev["type"]
        if key not in seen_types and len(callout_lines) < 5:
            seen_types.add(key)
            callout_lines.append(f"• {ev['label']} ({ev['date'].strftime('%b %d')})")
    callout_text = "\n".join(callout_lines) if callout_lines else ""
    if callout_text:
        fig.text(0.5, 0.01, callout_text, fontsize=8, ha="center", va="bottom",
                 bbox=dict(boxstyle="round,pad=0.4", fc="#f5f5f5", ec="#bdbdbd",
                           alpha=0.9))

    plt.savefig(output_path, dpi=300, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    # Convert RGBA → RGB to keep file size reasonable
    im = Image.open(output_path)
    if im.mode == "RGBA":
        rgb = Image.new("RGB", im.size, (255, 255, 255))
        rgb.paste(im, mask=im.split()[3])
        rgb.save(output_path)
    print(f"  Dashboard saved: {output_path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Assignment 3 — EDA Dashboard Builder")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Weather
    print(f"\n[1/6] Loading weather data...")
    weather = load_weather(FIELD_DIR, YEAR)
    print(f"  Records: {len(weather)} days ({weather['date'].iloc[0].date()} → "
          f"{weather['date'].iloc[-1].date()})")
    nulls = weather[["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR"]].isnull().sum().sum()
    print(f"  Null values in critical columns: {nulls}")
    expected = 366 if YEAR % 4 == 0 and (YEAR % 100 != 0 or YEAR % 400 == 0) else 365
    completeness = len(weather) / expected * 100
    print(f"  Completeness: {len(weather)}/{expected} days ({completeness:.0f}%)")

    # 2. NDVI
    print(f"\n[2/6] Loading NDVI scenes...")
    ndvi = load_ndvi_scenes(FIELD_DIR, YEAR)
    print(f"  Scenes found: {len(ndvi)}")
    for _, r in ndvi.iterrows():
        print(f"    {r['date']}: mean NDVI={r['ndvi_mean']:.3f} ± {r['ndvi_std']:.3f}"
              f"  ({r['ndvi_count']} px)")

    # 3. CDL
    print(f"\n[3/6] Confirming CDL crop...")
    cdl = load_cdl(FARM_DIR, FIELD_SLUG, YEAR)
    if cdl:
        print(f"  Crop: {cdl['crop_name']} (code {cdl['crop_code']}) — "
              f"{cdl['pct']:.1f}% of {cdl['pixel_count']} pixels")
    else:
        print("  [WARN] No CDL data found")

    # 4. Soil
    print(f"\n[4/6] Loading soil summary...")
    soil = load_soil(FIELD_DIR)
    if soil:
        print(f"  Soil: {soil['dominant_soil']} | OM {soil['om']}% | "
              f"pH {soil['ph']} | CEC {soil['cec']} | "
              f"Clay {soil['clay']}% | AWC {soil['aws']}\"")
    else:
        print("  [WARN] No soil data found")

    # 5. Boundary
    centroid, acres = load_field_boundary(FIELD_DIR)
    if centroid:
        print(f"\n  Boundary: {acres:.1f} ac @ ({centroid[0]:.4f}, {centroid[1]:.4f})")
    else:
        print("  [WARN] No boundary found")

    # 6. Compute metrics & events
    print(f"\n[5/6] Computing metrics and detecting events...")
    weather = compute_metrics(weather)
    events = detect_events(weather, ndvi)
    stage_dates = find_growth_stage_dates(weather)

    print(f"  Final GDD (50°F): {weather['cum_gdd'].iloc[-1]:.0f}")
    print(f"  Total precip: {weather['cum_precip'].iloc[-1]:.1f} mm")
    print(f"  Events detected: {len(events)}")
    for ev in events:
        print(f"    {ev['date'].strftime('%b %d')}: {ev['label']}")
    print(f"  Growth stages identified: {len([s for s in stage_dates if s[2] is not None])}")
    for sname, sgdd, sdate in stage_dates:
        if sdate:
            print(f"    {sname}: {sgdd} GDD ≈ {sdate.strftime('%b %d')}")

    # 7. Drought context (monthly precip anomaly vs 5-yr baseline)
    print(f"\n[6/7] Computing drought context...")
    drought_ctx = compute_drought_context(FIELD_DIR, YEAR)
    if drought_ctx:
        print(f"  {drought_ctx[2]}")
    else:
        print("  Insufficient data for drought context")

    # 8. Build dashboard
    print(f"\n[7/7] Building dashboard...")
    output_path = OUTPUT_DIR / f"dashboard_{FIELD_SLUG}_{YEAR}.png"
    build_dashboard(weather, ndvi, cdl, soil, centroid, acres,
                    events, stage_dates, output_path, drought_ctx)

    # 9. Save machine-readable events JSON
    save_events_json(events, OUTPUT_DIR, FIELD_SLUG, YEAR)

    print(f"\n{'=' * 60}")
    print(f"Dashboard complete: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
