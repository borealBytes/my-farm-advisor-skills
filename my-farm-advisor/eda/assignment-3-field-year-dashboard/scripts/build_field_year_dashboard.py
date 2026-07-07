#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false
"""
Build a reusable field-year dashboard combining NDVI time-series, weather,
and event annotations.  Sentinel-2 is the default NDVI source.

Example:
    python build_field_year_dashboard.py \
        --grower il-grower \
        --farm il-grower-illinois \
        --field osm-1263365647 \
        --year 2023 \
        --sensor sentinel
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
import rasterio

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ---------------------------------------------------------------------------
# Resolve runtime paths
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from lib.paths import (  # noqa: E402
    DATA_ROOT,
    farm_dir,
    field_dir,
    farm_table_path,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GDD_BASE = 10.0
GDD_CAP = 30.0
PLANTING_GDD_THRESHOLD = 50.0
PLANTING_DOY_MIN = 90
HEAVY_RAIN_MM = 25.0
HOT_DAY_C = 35.0
COOL_PERIOD_C = 10.0
COOL_PERIOD_DAYS = 3
NDVI_DIP = -0.10
NDVI_SURGE = 0.15
MAX_ANNOTATIONS_PER_PANEL = 6

SENSOR_LABEL = {"sentinel": "S2", "landsat": "L8"}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Field-year aligned dashboard")
    p.add_argument("--grower", required=True)
    p.add_argument("--farm", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--sensor", default="sentinel", choices=["sentinel", "landsat"])
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--no-events", action="store_true", help="Skip event annotations")
    p.add_argument("--multi-year", action="store_true", help="Build multi-year overlay (2021-2025)")
    p.add_argument("--annotated", action="store_true", help="Build annotated dashboard with concise captions")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_weather(grower: str, farm: str, field: str, year: int) -> pd.DataFrame:
    weather_csv = field_dir(grower, farm, field) / "weather" / "daily_weather.csv"
    if not weather_csv.exists():
        raise FileNotFoundError(f"Weather file not found: {weather_csv}")
    df = pd.read_csv(weather_csv, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        raise ValueError(f"No weather records for year {year}")
    df = df.sort_values("date").reset_index(drop=True)
    df["doy"] = df["date"].dt.dayofyear
    return df


def extract_ndvi_scenes(grower: str, farm: str, field: str, year: int, sensor: str) -> pd.DataFrame:
    scene_root = field_dir(grower, farm, field) / "satellite" / sensor / str(year)
    if not scene_root.exists():
        raise FileNotFoundError(f"Scene directory not found: {scene_root}")

    rows: list[dict[str, Any]] = []
    for scene_dir in sorted(scene_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        ndvi_tif = scene_dir / f"{scene_dir.name}_ndvi.tif"
        if not ndvi_tif.exists():
            continue
        # Parse date from directory name: sentinel_20230314 or landsat_20230314
        date_str = scene_dir.name.split("_", 1)[1]  # 20230314
        scene_date = datetime.strptime(date_str, "%Y%m%d")
        with rasterio.open(ndvi_tif) as src:
            arr = src.read(1).astype("float32")
            # Assume nodata is nan or <= -1
            arr = np.where(arr <= -1, np.nan, arr)
            mean_ndvi = float(np.nanmean(arr))
        rows.append(
            {
                "date": scene_date,
                "doy": scene_date.timetuple().tm_yday,
                "mean_ndvi": mean_ndvi,
                "source": SENSOR_LABEL.get(sensor, sensor.upper()),
            }
        )
    df = pd.DataFrame(rows).sort_values("doy").reset_index(drop=True)
    return df


def load_cdl_crop(grower: str, farm: str, field: str, year: int) -> dict[str, Any]:
    # Farm-level CDL composition is under derived/tables/
    # Discover CDL full-composition table by glob (filename varies by naming convention)
    tables_dir = farm_dir(grower, farm) / "derived" / "tables"
    candidates = list(tables_dir.glob("*cdl*full_composition.csv"))
    cdl_csv = candidates[0] if candidates else None
    if cdl_csv is None or not cdl_csv.exists():
        # Fallback: shared CDL table
        cdl_csv = DATA_ROOT / "shared" / "cdl" / "tables" / f"cdl_{year}_full_composition.csv"
    if not cdl_csv.exists():
        return {"crop_name": "Unknown", "pct": None, "pixel_count": None}

    df = pd.read_csv(cdl_csv)
    mask = (df["field_id"] == field) & (df["year"] == year)
    subset = df[mask].sort_values("pct", ascending=False)
    if subset.empty:
        return {"crop_name": "Unknown", "pct": None, "pixel_count": None}
    top = subset.iloc[0]
    return {
        "crop_name": str(top["crop_name"]),
        "pct": float(top["pct"]),
        "pixel_count": int(top["pixel_count"]) if "pixel_count" in top else None,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def calculate_gdd(weather_df: pd.DataFrame) -> pd.DataFrame:
    df = weather_df.copy()
    t_avg = (df["T2M_MAX"] + df["T2M_MIN"]) / 2.0
    t_avg = t_avg.clip(upper=GDD_CAP)
    df["gdd"] = (t_avg - GDD_BASE).clip(lower=0)
    df["cum_gdd"] = df["gdd"].cumsum()
    return df


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

def detect_events(weather_df: pd.DataFrame, ndvi_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    events: dict[str, list[dict[str, Any]]] = {
        "heavy_rain": [],
        "hot_day": [],
        "cool_period": [],
        "ndvi_dip": [],
        "ndvi_surge": [],
        "planting_window": [],
        "peak_ndvi": [],
    }

    # Weather events
    for _, row in weather_df.iterrows():
        if row["PRECTOTCORR"] >= HEAVY_RAIN_MM:
            events["heavy_rain"].append(
                {"doy": int(row["doy"]), "value": float(row["PRECTOTCORR"]), "label": f"Rain\n{row['PRECTOTCORR']:.0f} mm"}
            )
        if row["T2M_MAX"] >= HOT_DAY_C:
            events["hot_day"].append(
                {"doy": int(row["doy"]), "value": float(row["T2M_MAX"]), "label": f"Hot\n{row['T2M_MAX']:.0f}°C"}
            )

    # Cool periods (3-day rolling mean T2M < 10°C during growing season)
    weather_df = weather_df.copy()
    weather_df["t2m_roll3"] = weather_df["T2M"].rolling(window=COOL_PERIOD_DAYS, min_periods=COOL_PERIOD_DAYS).mean()
    cool_mask = (
        (weather_df["t2m_roll3"] < COOL_PERIOD_C)
        & (weather_df["doy"] >= 120)
        & (weather_df["doy"] <= 270)
    )
    cool_starts = weather_df[cool_mask & (~cool_mask.shift(1).fillna(False))]
    for _, row in cool_starts.head(MAX_ANNOTATIONS_PER_PANEL).iterrows():
        events["cool_period"].append(
            {"doy": int(row["doy"]), "value": float(row["T2M"]), "label": "Cool\nperiod"}
        )

    # NDVI dips and surges
    if len(ndvi_df) >= 2:
        ndvi_df = ndvi_df.copy()
        ndvi_df["delta"] = ndvi_df["mean_ndvi"].diff()
        for _, row in ndvi_df.iterrows():
            if pd.notna(row["delta"]):
                if row["delta"] <= NDVI_DIP:
                    events["ndvi_dip"].append(
                        {"doy": int(row["doy"]), "value": float(row["mean_ndvi"]), "delta": float(row["delta"]), "label": "NDVI\ndip"}
                    )
                elif row["delta"] >= NDVI_SURGE:
                    events["ndvi_surge"].append(
                        {"doy": int(row["doy"]), "value": float(row["mean_ndvi"]), "delta": float(row["delta"]), "label": "NDVI\nsurge"}
                    )

    # Peak NDVI
    if not ndvi_df.empty:
        peak_idx = ndvi_df["mean_ndvi"].idxmax()
        peak_row = ndvi_df.loc[peak_idx]
        events["peak_ndvi"].append(
            {"doy": int(peak_row["doy"]), "value": float(peak_row["mean_ndvi"]), "label": f"Peak\n{peak_row['mean_ndvi']:.2f}"}
        )

    # Planting window (first cum_gdd > 50 after DOY 90)
    post_april = weather_df[weather_df["doy"] >= PLANTING_DOY_MIN]
    if not post_april.empty and "cum_gdd" in post_april.columns:
        plant_candidates = post_april[post_april["cum_gdd"] >= PLANTING_GDD_THRESHOLD]
        if not plant_candidates.empty:
            plant_row = plant_candidates.iloc[0]
            events["planting_window"].append(
                {"doy": int(plant_row["doy"]), "value": None, "label": "Plant\nwindow"}
            )

    return events


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Annotated dashboard helpers
# ---------------------------------------------------------------------------

_ANNOTATION_COLORS = {
    "ndvi": ("#d3f9d8", "#2b8a3e", "#2b8a3e"),      # face, edge, arrow
    "precip": ("#e7f5ff", "#1971c2", "#1971c2"),
    "temp": ("#fff5f5", "#c92a2a", "#c92a2a"),
    "gdd": ("#e6fcf5", "#087f5b", "#087f5b"),
}

_EVENT_PANEL = {
    "peak_ndvi": ("P1", "ndvi"),
    "ndvi_dip": ("P1", "ndvi"),
    "ndvi_surge": ("P1", "ndvi"),
    "heavy_rain": ("P2", "precip"),
    "hot_day": ("P3", "temp"),
    "cool_period": ("P3", "temp"),
    "planting_window": ("P4", "gdd"),
}


def _format_caption(event_type: str, doy: int, value: float | None) -> str:
    """Return a concise caption: Event Value (Panel, DOY)."""
    panel, _ = _EVENT_PANEL.get(event_type, ("P?", "ndvi"))
    if event_type == "peak_ndvi":
        return f"Peak NDVI {value:.2f}\n({panel}, DOY {doy})"
    elif event_type == "ndvi_dip":
        return f"NDVI dip {value:.2f}\n({panel}, DOY {doy})"
    elif event_type == "ndvi_surge":
        return f"NDVI surge {value:.2f}\n({panel}, DOY {doy})"
    elif event_type == "heavy_rain":
        return f"Rain {value:.0f} mm\n({panel}, DOY {doy})"
    elif event_type == "hot_day":
        return f"Heat {value:.0f}°C\n({panel}, DOY {doy})"
    elif event_type == "cool_period":
        return f"Cool period\n({panel}, DOY {doy})"
    elif event_type == "planting_window":
        return f"Planting DOY {doy}\n({panel}, GDD>50)"
    return f"Event ({panel}, DOY {doy})"


def _place_annotated(
    ax,
    events_list: list[dict[str, Any]],
    event_type: str,
    y_ref: float,
    y_offset_factor: float = 0.12,
    panel_height: float = 1.0,
    max_n: int = 3,
):
    """Place color-coded annotations with concise captions."""
    if not events_list:
        return
    panel, color_key = _EVENT_PANEL.get(event_type, ("P?", "ndvi"))
    facecolor, edgecolor, arrowcolor = _ANNOTATION_COLORS[color_key]

    # Sort by absolute magnitude (largest first) and truncate
    if event_type in ("ndvi_dip", "ndvi_surge"):
        # For dips/surges, sort by delta magnitude stored in value
        events_sorted = sorted(events_list, key=lambda e: abs(e.get("delta", 0)), reverse=True)
    elif event_type == "heavy_rain":
        events_sorted = sorted(events_list, key=lambda e: e.get("value", 0), reverse=True)
    elif event_type == "hot_day":
        events_sorted = sorted(events_list, key=lambda e: e.get("value", 0), reverse=True)
    else:
        events_sorted = sorted(events_list, key=lambda e: e["doy"])

    events_sorted = events_sorted[:max_n]

    for i, ev in enumerate(events_sorted):
        doy = ev["doy"]
        val = ev.get("value", y_ref)
        caption = _format_caption(event_type, doy, val)
        # Stagger vertically
        offset = (i % 3 + 1) * y_offset_factor * panel_height
        ax.annotate(
            caption,
            xy=(doy, val),
            xytext=(doy, val + offset),
            fontsize=7.5,
            ha="center",
            va="bottom",
            fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=arrowcolor, lw=0.8),
            bbox=dict(boxstyle="round,pad=0.25", facecolor=facecolor, edgecolor=edgecolor, alpha=0.95),
        )


def _generate_summary_text(events: dict[str, list[dict[str, Any]]], cdl_info: dict[str, Any], year: int) -> str:
    """Generate a concise summary of the most important events."""
    lines: list[str] = []
    lines.append(f"Key events {year}:")

    # Planting window
    plant = events.get("planting_window", [])
    if plant:
        p = plant[0]
        lines.append(f"• Planting window opens at DOY {p['doy']} — P4")

    # Peak NDVI
    peak = events.get("peak_ndvi", [])
    if peak:
        p = peak[0]
        lines.append(f"• Peak NDVI {p['value']:.2f} at DOY {p['doy']} — P1")

    # Heaviest rain
    rain = sorted(events.get("heavy_rain", []), key=lambda e: e.get("value", 0), reverse=True)
    if rain:
        r = rain[0]
        lines.append(f"• Heaviest rain: {r['value']:.0f} mm at DOY {r['doy']} — P2")

    # NDVI dip
    dips = events.get("ndvi_dip", [])
    if dips:
        d = dips[0]
        lines.append(f"• NDVI dip {d['value']:.2f} at DOY {d['doy']} — P1")

    # NDVI surge
    surges = events.get("ndvi_surge", [])
    if surges:
        s = surges[0]
        lines.append(f"• NDVI surge {s['value']:.2f} at DOY {s['doy']} — P1")

    # Hot day
    hot = sorted(events.get("hot_day", []), key=lambda e: e.get("value", 0), reverse=True)
    if hot:
        h = hot[0]
        lines.append(f"• Hottest day: {h['value']:.0f}°C at DOY {h['doy']} — P3")

    return "\n".join(lines)


def _place_annotations(ax, events_list, y_ref, y_offset_factor=0.12, panel_height=1.0):
    """Algorithmically place annotations with vertical staggering."""
    if not events_list:
        return
    # Sort by DOY
    events_sorted = sorted(events_list, key=lambda e: e["doy"])
    n = len(events_sorted)
    # Take top N to avoid clutter
    events_sorted = events_sorted[:MAX_ANNOTATIONS_PER_PANEL]
    for i, ev in enumerate(events_sorted):
        doy = ev["doy"]
        val = ev.get("value", y_ref)
        label = ev["label"]
        # Stagger vertically
        offset = (i % 3 + 1) * y_offset_factor * panel_height
        ax.annotate(
            label,
            xy=(doy, val),
            xytext=(doy, val + offset),
            fontsize=7.5,
            ha="center",
            va="bottom",
            arrowprops=dict(arrowstyle="->", color="#333333", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#fff3cd", edgecolor="#ffc107", alpha=0.9),
        )


def build_dashboard(
    weather_df: pd.DataFrame,
    ndvi_df: pd.DataFrame,
    cdl_info: dict[str, Any],
    events: dict[str, list[dict[str, Any]]],
    grower: str,
    farm: str,
    field: str,
    year: int,
    out_path: Path,
    dpi: int = 300,
) -> Path:
    fig, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True, gridspec_kw={"hspace": 0.08})
    fig.patch.set_facecolor("#ffffff")

    # Super-title
    crop_str = cdl_info.get("crop_name", "Unknown")
    pct_str = f"({cdl_info['pct']:.1f}%)" if cdl_info.get("pct") else ""
    scenes_str = f"{len(ndvi_df)} {SENSOR_LABEL.get('sentinel', 'S2')} scenes"
    fig.suptitle(
        f"Field {field} | {year} | {crop_str} {pct_str} | Adams County, IL | {scenes_str}",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    # Shared x-axis limits
    doy_min, doy_max = 0, 366
    for ax in axes:
        ax.set_xlim(doy_min, doy_max)

    # ------------------------------------------------------------------
    # Panel 1: NDVI
    # ------------------------------------------------------------------
    ax_ndvi = axes[0]
    ax_ndvi.plot(ndvi_df["doy"], ndvi_df["mean_ndvi"], color="#2ca02c", linewidth=1.5, zorder=2)
    ax_ndvi.scatter(ndvi_df["doy"], ndvi_df["mean_ndvi"], color="#2ca02c", s=50, zorder=3, label="Sentinel-2 NDVI")
    ax_ndvi.set_ylabel("NDVI", fontsize=12)
    ax_ndvi.set_ylim(-0.1, 1.0)
    ax_ndvi.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_ndvi.set_title("NDVI Time-Series", fontsize=13, fontweight="bold", loc="left")
    ax_ndvi.legend(loc="lower right", fontsize=9)
    ax_ndvi.grid(True, alpha=0.25)

    # NDVI events
    ndvi_events = events.get("ndvi_dip", []) + events.get("ndvi_surge", []) + events.get("peak_ndvi", [])
    _place_annotations(ax_ndvi, ndvi_events, y_ref=0.5, y_offset_factor=0.10, panel_height=1.0)

    # Sparse scene check
    if len(ndvi_df) >= 2:
        gaps = ndvi_df["doy"].diff().dropna()
        large_gaps = gaps[gaps > 45]
        if not large_gaps.empty:
            ax_ndvi.text(
                0.02, 0.95,
                f"Warning: {len(large_gaps)} gap(s) > 45 days",
                transform=ax_ndvi.transAxes,
                fontsize=8,
                color="red",
                va="top",
                bbox=dict(boxstyle="round", facecolor="white", edgecolor="red", alpha=0.8),
            )

    # ------------------------------------------------------------------
    # Panel 2: Precipitation
    # ------------------------------------------------------------------
    ax_precip = axes[1]
    ax_precip.bar(weather_df["doy"], weather_df["PRECTOTCORR"], color="#4dabf7", width=1.0, alpha=0.7, edgecolor="none")
    ax_precip.set_ylabel("Precipitation (mm)", fontsize=12)
    ax_precip.set_ylim(0, max(weather_df["PRECTOTCORR"].max() * 1.2, 10))
    ax_precip.set_title("Daily Precipitation", fontsize=13, fontweight="bold", loc="left")
    ax_precip.grid(True, alpha=0.25, axis="y")

    _place_annotations(ax_precip, events.get("heavy_rain", []), y_ref=weather_df["PRECTOTCORR"].max() * 0.5, y_offset_factor=0.12, panel_height=weather_df["PRECTOTCORR"].max())

    # ------------------------------------------------------------------
    # Panel 3: Temperature envelope
    # ------------------------------------------------------------------
    ax_temp = axes[2]
    ax_temp.fill_between(
        weather_df["doy"],
        weather_df["T2M_MIN"],
        weather_df["T2M_MAX"],
        color="#ff922b",
        alpha=0.25,
        label="Min–Max range",
    )
    ax_temp.plot(weather_df["doy"], weather_df["T2M"], color="#d9480f", linewidth=0.8, label="Mean temp")
    ax_temp.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_temp.axhline(GDD_BASE, color="green", linewidth=0.5, linestyle="--", alpha=0.5, label=f"{GDD_BASE}°C base")
    ax_temp.set_ylabel("Temperature (°C)", fontsize=12)
    ax_temp.set_title("Daily Temperature", fontsize=13, fontweight="bold", loc="left")
    ax_temp.legend(loc="upper right", fontsize=9)
    ax_temp.grid(True, alpha=0.25, axis="y")

    # Hot / cool annotations
    temp_events = events.get("hot_day", []) + events.get("cool_period", [])
    _place_annotations(ax_temp, temp_events, y_ref=weather_df["T2M_MAX"].max() * 0.8, y_offset_factor=0.10, panel_height=weather_df["T2M_MAX"].max() - weather_df["T2M_MIN"].min())

    # ------------------------------------------------------------------
    # Panel 4: Cumulative GDD
    # ------------------------------------------------------------------
    ax_gdd = axes[3]
    ax_gdd.plot(weather_df["doy"], weather_df["cum_gdd"], color="#2b8a3e", linewidth=2.0, label="Cumulative GDD")
    ax_gdd.axhline(1500, color="#5c940d", linewidth=0.8, linestyle="--", alpha=0.6, label="1,500 GDD (maturity ref)")
    ax_gdd.set_ylabel("Cumulative GDD", fontsize=12)
    ax_gdd.set_xlabel("Day of Year", fontsize=12)
    ax_gdd.set_title("Growing Degree Days (base 10°C, cap 30°C)", fontsize=13, fontweight="bold", loc="left")
    ax_gdd.legend(loc="upper left", fontsize=9)
    ax_gdd.grid(True, alpha=0.25, axis="y")

    # Planting window annotation
    plant_events = events.get("planting_window", [])
    for ev in plant_events:
        ax_gdd.axvline(ev["doy"], color="#5c940d", linewidth=1.0, linestyle="-.", alpha=0.7)
        ax_gdd.annotate(
            ev["label"],
            xy=(ev["doy"], weather_df["cum_gdd"].max() * 0.9),
            fontsize=8,
            ha="center",
            va="top",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#d3f9d8", edgecolor="#2b8a3e", alpha=0.9),
        )

    # Month ticks on bottom axis
    month_ticks = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax_gdd.set_xticks(month_ticks)
    ax_gdd.set_xticklabels(month_labels, fontsize=10)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"✓ Saved dashboard: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Annotated dashboard (new file, preserves original)
# ---------------------------------------------------------------------------

def build_dashboard_annotated(
    weather_df: pd.DataFrame,
    ndvi_df: pd.DataFrame,
    cdl_info: dict[str, Any],
    events: dict[str, list[dict[str, Any]]],
    field: str,
    year: int,
    out_path: Path,
    dpi: int = 300,
) -> Path:
    fig, axes = plt.subplots(4, 1, figsize=(16, 20), sharex=True)
    fig.patch.set_facecolor("#ffffff")

    # Super-title
    crop_str = cdl_info.get("crop_name", "Unknown")
    pct_str = f"({cdl_info['pct']:.1f}%)" if cdl_info.get("pct") else ""
    scenes_str = f"{len(ndvi_df)} {SENSOR_LABEL.get('sentinel', 'S2')} scenes"
    fig.suptitle(
        f"Field {field} | {year} | {crop_str} {pct_str} | Adams County, IL | {scenes_str}",
        fontsize=16,
        fontweight="bold",
        y=0.97,
    )

    # Summary text box (below suptitle)
    summary_text = _generate_summary_text(events, cdl_info, year)
    fig.text(
        0.08, 0.945,
        summary_text,
        fontsize=9.5,
        verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8f9fa", edgecolor="#dee2e6", alpha=0.95),
    )

    # Explicit layout (no tight_layout warning)
    fig.subplots_adjust(left=0.08, right=0.95, top=0.90, bottom=0.04, hspace=0.10)

    doy_min, doy_max = 0, 366
    for ax in axes:
        ax.set_xlim(doy_min, doy_max)

    # ------------------------------------------------------------------
    # Panel 1: NDVI
    # ------------------------------------------------------------------
    ax_ndvi = axes[0]
    ax_ndvi.plot(ndvi_df["doy"], ndvi_df["mean_ndvi"], color="#2ca02c", linewidth=1.5, zorder=2)
    ax_ndvi.scatter(ndvi_df["doy"], ndvi_df["mean_ndvi"], color="#2ca02c", s=50, zorder=3, label="Sentinel-2 NDVI")
    ax_ndvi.set_ylabel("NDVI", fontsize=12)
    ax_ndvi.set_ylim(-0.1, 1.0)
    ax_ndvi.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_ndvi.set_title("P1 — NDVI Time-Series (Sentinel-2)", fontsize=13, fontweight="bold", loc="left")
    ax_ndvi.legend(loc="lower right", fontsize=9)
    ax_ndvi.grid(True, alpha=0.25)

    # NDVI events: peak, dip, surge (max 3)
    _place_annotated(ax_ndvi, events.get("peak_ndvi", []), "peak_ndvi", y_ref=0.5, y_offset_factor=0.10, panel_height=1.0, max_n=1)
    _place_annotated(ax_ndvi, events.get("ndvi_dip", []), "ndvi_dip", y_ref=0.5, y_offset_factor=0.10, panel_height=1.0, max_n=1)
    _place_annotated(ax_ndvi, events.get("ndvi_surge", []), "ndvi_surge", y_ref=0.5, y_offset_factor=0.10, panel_height=1.0, max_n=1)

    # Sparse scene check
    if len(ndvi_df) >= 2:
        gaps = ndvi_df["doy"].diff().dropna()
        large_gaps = gaps[gaps > 45]
        if not large_gaps.empty:
            ax_ndvi.text(
                0.02, 0.95,
                f"Warning: {len(large_gaps)} gap(s) > 45 days",
                transform=ax_ndvi.transAxes,
                fontsize=8,
                color="red",
                va="top",
                bbox=dict(boxstyle="round", facecolor="white", edgecolor="red", alpha=0.8),
            )

    # ------------------------------------------------------------------
    # Panel 2: Precipitation
    # ------------------------------------------------------------------
    ax_precip = axes[1]
    ax_precip.bar(weather_df["doy"], weather_df["PRECTOTCORR"], color="#4dabf7", width=1.0, alpha=0.7, edgecolor="none")
    ax_precip.set_ylabel("Precipitation (mm)", fontsize=12)
    ax_precip.set_ylim(0, max(weather_df["PRECTOTCORR"].max() * 1.2, 10))
    ax_precip.set_title("P2 — Daily Precipitation", fontsize=13, fontweight="bold", loc="left")
    ax_precip.grid(True, alpha=0.25, axis="y")

    _place_annotated(ax_precip, events.get("heavy_rain", []), "heavy_rain", y_ref=weather_df["PRECTOTCORR"].max() * 0.5, y_offset_factor=0.12, panel_height=weather_df["PRECTOTCORR"].max(), max_n=2)

    # ------------------------------------------------------------------
    # Panel 3: Temperature envelope
    # ------------------------------------------------------------------
    ax_temp = axes[2]
    ax_temp.fill_between(
        weather_df["doy"],
        weather_df["T2M_MIN"],
        weather_df["T2M_MAX"],
        color="#ff922b",
        alpha=0.25,
        label="Min–Max range",
    )
    ax_temp.plot(weather_df["doy"], weather_df["T2M"], color="#d9480f", linewidth=0.8, label="Mean temp")
    ax_temp.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_temp.axhline(GDD_BASE, color="green", linewidth=0.5, linestyle="--", alpha=0.5, label=f"{GDD_BASE}°C base")
    ax_temp.set_ylabel("Temperature (°C)", fontsize=12)
    ax_temp.set_title("P3 — Daily Temperature", fontsize=13, fontweight="bold", loc="left")
    ax_temp.legend(loc="upper right", fontsize=9)
    ax_temp.grid(True, alpha=0.25, axis="y")

    # Temp events: hot day, cool period (max 3)
    _place_annotated(ax_temp, events.get("hot_day", []), "hot_day", y_ref=weather_df["T2M_MAX"].max() * 0.8, y_offset_factor=0.10, panel_height=weather_df["T2M_MAX"].max() - weather_df["T2M_MIN"].min(), max_n=2)
    _place_annotated(ax_temp, events.get("cool_period", []), "cool_period", y_ref=weather_df["T2M_MIN"].min(), y_offset_factor=0.10, panel_height=weather_df["T2M_MAX"].max() - weather_df["T2M_MIN"].min(), max_n=1)

    # ------------------------------------------------------------------
    # Panel 4: Cumulative GDD
    # ------------------------------------------------------------------
    ax_gdd = axes[3]
    ax_gdd.plot(weather_df["doy"], weather_df["cum_gdd"], color="#2b8a3e", linewidth=2.0, label="Cumulative GDD")
    ax_gdd.axhline(1500, color="#5c940d", linewidth=0.8, linestyle="--", alpha=0.6, label="1,500 GDD (maturity ref)")
    ax_gdd.set_ylabel("Cumulative GDD", fontsize=12)
    ax_gdd.set_xlabel("Day of Year", fontsize=12)
    ax_gdd.set_title("P4 — Growing Degree Days (base 10°C, cap 30°C)", fontsize=13, fontweight="bold", loc="left")
    ax_gdd.legend(loc="upper left", fontsize=9)
    ax_gdd.grid(True, alpha=0.25, axis="y")

    # Planting window annotation (vertical line + label)
    plant_events = events.get("planting_window", [])
    for ev in plant_events:
        ax_gdd.axvline(ev["doy"], color="#087f5b", linewidth=1.2, linestyle="-.", alpha=0.7)
        ax_gdd.annotate(
            f"Planting DOY {ev['doy']}\n(P4, GDD>50)",
            xy=(ev["doy"], weather_df["cum_gdd"].max() * 0.9),
            fontsize=8,
            ha="center",
            va="top",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#e6fcf5", edgecolor="#087f5b", alpha=0.95),
        )

    # Month ticks on bottom axis
    month_ticks = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax_gdd.set_xticks(month_ticks)
    ax_gdd.set_xticklabels(month_labels, fontsize=10)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"✓ Saved annotated dashboard: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Multi-year overlay
# ---------------------------------------------------------------------------

def build_multi_year_overlay(
    grower: str,
    farm: str,
    field: str,
    years: list[int],
    sensor: str,
    out_path: Path,
    dpi: int = 300,
) -> Path:
    """Build a multi-year overlay dashboard for all requested years."""
    fig, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True, gridspec_kw={"hspace": 0.08})
    fig.patch.set_facecolor("#ffffff")

    fig.suptitle(
        f"Field {field} | Multi-Year Overlay ({min(years)}-{max(years)}) | Adams County, IL",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    doy_min, doy_max = 0, 366
    for ax in axes:
        ax.set_xlim(doy_min, doy_max)

    # Colormap for years
    colors = plt.cm.tab10(np.linspace(0, 1, len(years)))
    year_color = {year: colors[i] for i, year in enumerate(sorted(years))}

    # Collect data for all years
    all_ndvi: list[pd.DataFrame] = []
    all_weather: list[pd.DataFrame] = []
    prototype_year = 2023  # Use 2023 as prototype for weather panels

    for year in years:
        try:
            ndvi = extract_ndvi_scenes(grower, farm, field, year, sensor)
            weather = load_weather(grower, farm, field, year)
            weather = calculate_gdd(weather)
            ndvi["year"] = year
            weather["year"] = year
            all_ndvi.append(ndvi)
            all_weather.append(weather)
        except Exception as exc:
            print(f"    Warning: skipping {year}: {exc}")
            continue

    # ------------------------------------------------------------------
    # Panel 1: NDVI overlay (all years)
    # ------------------------------------------------------------------
    ax_ndvi = axes[0]
    for ndvi_df in all_ndvi:
        year = int(ndvi_df["year"].iloc[0])
        ax_ndvi.plot(
            ndvi_df["doy"],
            ndvi_df["mean_ndvi"],
            color=year_color[year],
            linewidth=1.5,
            marker="o",
            markersize=4,
            label=str(year),
        )
    ax_ndvi.set_ylabel("NDVI", fontsize=12)
    ax_ndvi.set_ylim(-0.1, 1.0)
    ax_ndvi.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_ndvi.set_title("NDVI Time-Series (all years)", fontsize=13, fontweight="bold", loc="left")
    ax_ndvi.legend(title="Year", loc="lower right", fontsize=9, title_fontsize=9)
    ax_ndvi.grid(True, alpha=0.25)

    # ------------------------------------------------------------------
    # Panel 2: Precipitation (prototype year only)
    # ------------------------------------------------------------------
    ax_precip = axes[1]
    proto_weather = next((w for w in all_weather if int(w["year"].iloc[0]) == prototype_year), None)
    if proto_weather is not None:
        ax_precip.bar(
            proto_weather["doy"],
            proto_weather["PRECTOTCORR"],
            color="#4dabf7",
            width=1.0,
            alpha=0.7,
            edgecolor="none",
        )
        ax_precip.set_title(f"Daily Precipitation ({prototype_year})", fontsize=13, fontweight="bold", loc="left")
    else:
        ax_precip.set_title("Daily Precipitation (prototype year unavailable)", fontsize=13, fontweight="bold", loc="left")
    ax_precip.set_ylabel("Precipitation (mm)", fontsize=12)
    ax_precip.set_ylim(0, max(proto_weather["PRECTOTCORR"].max() * 1.2, 10) if proto_weather is not None else 10)
    ax_precip.grid(True, alpha=0.25, axis="y")

    # ------------------------------------------------------------------
    # Panel 3: Temperature envelope (prototype year only)
    # ------------------------------------------------------------------
    ax_temp = axes[2]
    if proto_weather is not None:
        ax_temp.fill_between(
            proto_weather["doy"],
            proto_weather["T2M_MIN"],
            proto_weather["T2M_MAX"],
            color="#ff922b",
            alpha=0.25,
            label="Min–Max range",
        )
        ax_temp.plot(proto_weather["doy"], proto_weather["T2M"], color="#d9480f", linewidth=0.8, label="Mean temp")
        ax_temp.axhline(0, color="grey", linewidth=0.5, linestyle="--")
        ax_temp.axhline(GDD_BASE, color="green", linewidth=0.5, linestyle="--", alpha=0.5, label=f"{GDD_BASE}°C base")
        ax_temp.set_title(f"Daily Temperature ({prototype_year})", fontsize=13, fontweight="bold", loc="left")
        ax_temp.legend(loc="upper right", fontsize=9)
    else:
        ax_temp.set_title("Daily Temperature (prototype year unavailable)", fontsize=13, fontweight="bold", loc="left")
    ax_temp.set_ylabel("Temperature (°C)", fontsize=12)
    ax_temp.grid(True, alpha=0.25, axis="y")

    # ------------------------------------------------------------------
    # Panel 4: Cumulative GDD overlay (all years)
    # ------------------------------------------------------------------
    ax_gdd = axes[3]
    for weather_df in all_weather:
        year = int(weather_df["year"].iloc[0])
        ax_gdd.plot(
            weather_df["doy"],
            weather_df["cum_gdd"],
            color=year_color[year],
            linewidth=2.0,
            label=str(year),
        )
    ax_gdd.axhline(1500, color="#5c940d", linewidth=0.8, linestyle="--", alpha=0.6, label="1,500 GDD (maturity ref)")
    ax_gdd.set_ylabel("Cumulative GDD", fontsize=12)
    ax_gdd.set_xlabel("Day of Year", fontsize=12)
    ax_gdd.set_title("Growing Degree Days (base 10°C, cap 30°C)", fontsize=13, fontweight="bold", loc="left")
    ax_gdd.legend(title="Year", loc="upper left", fontsize=9, title_fontsize=9)
    ax_gdd.grid(True, alpha=0.25, axis="y")

    # Month ticks
    month_ticks = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ax_gdd.set_xticks(month_ticks)
    ax_gdd.set_xticklabels(month_labels, fontsize=10)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"✓ Saved multi-year overlay: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    out_dir = args.out_dir
    if out_dir is None:
        out_dir = field_dir(args.grower, args.farm, args.field) / "derived" / "dashboards"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.multi_year:
        years = [2021, 2022, 2023, 2024, 2025]
        print(f"Building multi-year overlay for {args.field} | years={years} | sensor={args.sensor}")
        out_path = out_dir / "field_year_dashboard_multi_year_overlay.png"
        build_multi_year_overlay(
            grower=args.grower,
            farm=args.farm,
            field=args.field,
            years=years,
            sensor=args.sensor,
            out_path=out_path,
            dpi=args.dpi,
        )
        print("\n✓ Multi-year overlay complete")
        return

    print(f"Building dashboard for {args.field} | {args.year} | sensor={args.sensor}")

    # 1. Load weather
    print("  Loading weather...")
    weather = load_weather(args.grower, args.farm, args.field, args.year)
    weather = calculate_gdd(weather)
    print(f"    {len(weather)} daily records")

    # 2. Load NDVI
    print("  Loading NDVI scenes...")
    ndvi = extract_ndvi_scenes(args.grower, args.farm, args.field, args.year, args.sensor)
    print(f"    {len(ndvi)} scenes")

    # 3. Confirm CDL crop
    print("  Confirming CDL crop...")
    cdl = load_cdl_crop(args.grower, args.farm, args.field, args.year)
    print(f"    {cdl['crop_name']} ({cdl.get('pct', 'N/A')}%)")

    # 4. Detect events
    events: dict[str, list[dict[str, Any]]] = {}
    if not args.no_events:
        print("  Detecting events...")
        events = detect_events(weather, ndvi)
        total_events = sum(len(v) for v in events.values())
        print(f"    {total_events} events detected")

    # 5. Build dashboard (original or annotated)
    if args.annotated:
        out_path = out_dir / f"field_year_dashboard_{args.year}_annotated.png"
        build_dashboard_annotated(
            weather_df=weather,
            ndvi_df=ndvi,
            cdl_info=cdl,
            events=events,
            field=args.field,
            year=args.year,
            out_path=out_path,
            dpi=args.dpi,
        )
        print("\n✓ Annotated dashboard complete")
    else:
        out_path = out_dir / f"field_year_dashboard_{args.year}.png"
        build_dashboard(
            weather_df=weather,
            ndvi_df=ndvi,
            cdl_info=cdl,
            events=events,
            grower=args.grower,
            farm=args.farm,
            field=args.field,
            year=args.year,
            out_path=out_path,
            dpi=args.dpi,
        )
        print("\n✓ Dashboard complete")


if __name__ == "__main__":
    main()
