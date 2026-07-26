#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
"""Generate aligned field-year NDVI + weather mini-dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.dates import DateFormatter
from matplotlib.patches import FancyArrowPatch
from rasterio.mask import mask

matplotlib.use("Agg")

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from reporting_bootstrap import ensure_skill_path  # noqa: E402

ensure_skill_path("farm-intelligence-reporting")

from pipeline import (  # noqa: E402
    FieldReportingConfig,
    build_step_manifest,
    load_manifest,
    step_is_stale,
)
from paths import (  # noqa: E402
    field_boundary_path,
    field_dir,
    field_report_path,
    field_satellite_dir,
    field_weather_path,
    farm_boundary_path,
)

_SCRIPT = Path(__file__)

# ---------------------------------------------------------------------------
# Thresholds / tuning knobs
# ---------------------------------------------------------------------------
_RAIN_THRESHOLD_MM = 25.0
_HEAT_THRESHOLD_C = 35.0
_COOL_THRESHOLD_C = 10.0
_COOL_CONSECUTIVE_DAYS = 3
_DRY_SPELL_DAYS = 14
_DRY_SPELL_MM = 1.0
_NDVI_DIP_DELTA = -0.15
_NDVI_RAPID_RISE_DELTA = 0.20
_CLOUD_WARNING_PCT = 20.0
_GDD_BASE_C = 10.0
_GDD_CAP_C = 30.0
_GS_START_DOY = 100
_GS_END_DOY = 280
_GS_BAND_COLOR = "#dcfce7"
_DISPLAY_START_DOY = 60
_DISPLAY_END_DOY = 320

_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "iowa-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "iowa-grower-iowa")


# ---------------------------------------------------------------------------
# NDVI helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_ndvi_timeseries(
    field_slug: str,
    year: int,
    grower: str = _DEFAULT_GROWER,
    farm: str = _DEFAULT_FARM,
) -> pd.DataFrame:
    """Read Sentinel manifest, mask each NDVI scene to the field, return mean NDVI per scene."""
    manifest_path = field_satellite_dir(grower, farm, field_slug) / "sentinel" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Sentinel manifest not found: {manifest_path}")

    manifest = _load_json(manifest_path)
    boundary_path = field_boundary_path(grower, farm, field_slug)
    if not boundary_path.exists():
        raise FileNotFoundError(f"Field boundary not found: {boundary_path}")

    boundary = gpd.read_file(boundary_path)

    rows: list[dict[str, Any]] = []
    for year_entry in manifest.get("years", []):
        if year_entry.get("year") != year:
            continue
        for scene in year_entry.get("scenes", []):
            ndvi_rel = scene.get("ndvi_tif")
            scene_date = scene.get("scene_date")
            cloud_cover = scene.get("cloud_cover", 0.0)
            if not ndvi_rel or not scene_date:
                continue
            ndvi_path = _REPO / str(ndvi_rel)
            if not ndvi_path.exists():
                continue
            try:
                with rasterio.open(ndvi_path) as src:
                    boundary_proj = boundary.to_crs(src.crs)
                    clipped, _ = mask(src, boundary_proj.geometry, crop=True, filled=False)
                arr = np.ma.filled(clipped[0], np.nan).astype(float)
                valid = arr[np.isfinite(arr)]
                if valid.size == 0:
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(scene_date),
                        "doy": int(pd.Timestamp(scene_date).dayofyear),
                        "mean_ndvi": float(np.nanmean(valid)),
                        "cloud_cover": float(cloud_cover),
                        "scene_id": str(scene.get("scene_id", "")),
                    }
                )
            except Exception:
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------
def _load_weather_year(
    field_slug: str,
    year: int,
    grower: str = _DEFAULT_GROWER,
    farm: str = _DEFAULT_FARM,
) -> pd.DataFrame:
    """Load daily weather for a single year, compute GDD, rolling stats, cumulatives."""
    weather_path = field_weather_path(grower, farm, field_slug)
    if not weather_path.exists():
        raise FileNotFoundError(f"Weather CSV not found: {weather_path}")

    df = pd.read_csv(weather_path, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        return df

    df["doy"] = df["date"].dt.dayofyear
    df = df.sort_values("date").reset_index(drop=True)

    # GDD (base 10, cap 30)
    t_avg = (df["T2M_MAX"] + df["T2M_MIN"]) / 2.0
    df["gdd"] = np.maximum(0.0, np.minimum(t_avg, _GDD_CAP_C) - _GDD_BASE_C)
    df["gdd_cumulative"] = df["gdd"].cumsum()

    # Cumulative precip
    df["precip_cumulative"] = df["PRECTOTCORR"].cumsum()

    # 7-day rolling mean temperature
    df["t2m_7d"] = df["T2M"].rolling(7, min_periods=1).mean()

    return df


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------
def _detect_weather_events(weather_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect notable weather events within the growing-season window."""
    events: list[dict[str, Any]] = []
    gs = weather_df[
        (weather_df["doy"] >= _GS_START_DOY) & (weather_df["doy"] <= _GS_END_DOY)
    ].copy()
    if gs.empty:
        return events

    # Heavy rain
    heavy = gs[gs["PRECTOTCORR"] >= _RAIN_THRESHOLD_MM]
    for _, row in heavy.iterrows():
        events.append(
            {
                "type": "heavy_rain",
                "date": row["date"],
                "doy": int(row["doy"]),
                "value": float(row["PRECTOTCORR"]),
                "label": f"Heavy rain: {row['PRECTOTCORR']:.1f} mm",
                "panel": "precip",
            }
        )

    # Heat stress
    hot = gs[gs["T2M_MAX"] >= _HEAT_THRESHOLD_C]
    for _, row in hot.iterrows():
        events.append(
            {
                "type": "heat_stress",
                "date": row["date"],
                "doy": int(row["doy"]),
                "value": float(row["T2M_MAX"]),
                "label": f"Heat stress: {row['T2M_MAX']:.1f}°C",
                "panel": "temp",
            }
        )

    # Cool periods (3+ consecutive days T2M < 10°C)
    gs["cool"] = gs["T2M"] < _COOL_THRESHOLD_C
    cool_streaks: list[tuple[int, int]] = []
    streak_start: int | None = None
    for i, is_cool in enumerate(gs["cool"]):
        if is_cool and streak_start is None:
            streak_start = i
        elif not is_cool and streak_start is not None:
            if i - streak_start >= _COOL_CONSECUTIVE_DAYS:
                cool_streaks.append((streak_start, i - 1))
            streak_start = None
    if streak_start is not None and len(gs) - streak_start >= _COOL_CONSECUTIVE_DAYS:
        cool_streaks.append((streak_start, len(gs) - 1))

    for start, end in cool_streaks:
        row_start = gs.iloc[start]
        row_end = gs.iloc[end]
        events.append(
            {
                "type": "cool_snap",
                "date": row_start["date"],
                "doy": int(row_start["doy"]),
                "end_doy": int(row_end["doy"]),
                "value": int(end - start + 1),
                "label": f"Cold snap: {end - start + 1} days <{_COOL_THRESHOLD_C}°C",
                "panel": "temp",
            }
        )

    # Dry spells (14+ consecutive days < 1 mm)
    gs["dry"] = gs["PRECTOTCORR"] < _DRY_SPELL_MM
    dry_streaks: list[tuple[int, int]] = []
    streak_start = None
    for i, is_dry in enumerate(gs["dry"]):
        if is_dry and streak_start is None:
            streak_start = i
        elif not is_dry and streak_start is not None:
            if i - streak_start >= _DRY_SPELL_DAYS:
                dry_streaks.append((streak_start, i - 1))
            streak_start = None
    if streak_start is not None and len(gs) - streak_start >= _DRY_SPELL_DAYS:
        dry_streaks.append((streak_start, len(gs) - 1))

    for start, end in dry_streaks:
        row_start = gs.iloc[start]
        row_end = gs.iloc[end]
        events.append(
            {
                "type": "dry_spell",
                "date": row_start["date"],
                "doy": int(row_start["doy"]),
                "end_doy": int(row_end["doy"]),
                "value": int(end - start + 1),
                "label": f"Dry spell: {end - start + 1} days <{_DRY_SPELL_MM} mm",
                "panel": "precip",
            }
        )

    return events


def _detect_ndvi_events(ndvi_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect notable NDVI changes."""
    events: list[dict[str, Any]] = []
    if len(ndvi_df) < 2:
        return events

    gs = ndvi_df[
        (ndvi_df["doy"] >= _GS_START_DOY) & (ndvi_df["doy"] <= _GS_END_DOY)
    ].copy()

    # Rapid green-up & dips
    for i in range(1, len(gs)):
        prev = gs.iloc[i - 1]
        curr = gs.iloc[i]
        delta = float(curr["mean_ndvi"] - prev["mean_ndvi"])
        if delta >= _NDVI_RAPID_RISE_DELTA:
            events.append(
                {
                    "type": "rapid_greenup",
                    "date": curr["date"],
                    "doy": int(curr["doy"]),
                    "value": delta,
                    "label": f"Rapid green-up: +{delta:.2f}",
                    "panel": "ndvi",
                }
            )
        elif delta <= _NDVI_DIP_DELTA:
            events.append(
                {
                    "type": "ndvi_dip",
                    "date": curr["date"],
                    "doy": int(curr["doy"]),
                    "value": delta,
                    "label": f"NDVI dip: {delta:.2f}",
                    "panel": "ndvi",
                }
            )

    # Peak NDVI
    if not gs.empty:
        peak_idx = gs["mean_ndvi"].idxmax()
        peak_row = gs.loc[peak_idx]
        if _GS_START_DOY <= peak_row["doy"] <= _GS_END_DOY:
            events.append(
                {
                    "type": "peak_ndvi",
                    "date": peak_row["date"],
                    "doy": int(peak_row["doy"]),
                    "value": float(peak_row["mean_ndvi"]),
                    "label": f"Peak NDVI: {peak_row['mean_ndvi']:.2f} (DOY {int(peak_row['doy'])})",
                    "panel": "ndvi",
                }
            )

    # Late-season decline after peak
    peak_event = next((e for e in events if e["type"] == "peak_ndvi"), None)
    if peak_event:
        peak_doy = peak_event["doy"]
        post_peak = gs[gs["doy"] > peak_doy]
        if not post_peak.empty:
            last = post_peak.iloc[-1]
            decline = float(peak_event["value"] - last["mean_ndvi"])
            if decline >= 0.20:
                events.append(
                    {
                        "type": "senescence",
                        "date": last["date"],
                        "doy": int(last["doy"]),
                        "value": decline,
                        "label": f"Senescence: -{decline:.2f}",
                        "panel": "ndvi",
                    }
                )

    return events


def _link_cross_events(
    weather_events: list[dict[str, Any]], ndvi_events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Link weather events to nearby NDVI events within ±7 days."""
    linked: list[dict[str, Any]] = []
    for we in weather_events:
        if we["type"] not in {"heavy_rain", "heat_stress", "dry_spell"}:
            continue
        for ne in ndvi_events:
            if ne["type"] not in {"ndvi_dip", "rapid_greenup"}:
                continue
            delta_doy = abs(we["doy"] - ne["doy"])
            if delta_doy <= 7:
                linked.append(
                    {
                        "type": "cross",
                        "doy": ne["doy"],
                        "label": f"{ne['label']} — after {we['label'].split(':')[0]} by {delta_doy}d",
                        "panel": "ndvi",
                    }
                )
    return linked


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------
def _build_dashboard(
    field_slug: str,
    year: int,
    crop: str,
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    events: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Build the 4-panel aligned dashboard PNG."""

    fig = plt.figure(figsize=(14, 20))
    fig.patch.set_facecolor("#fafaf9")

    # Title block
    lat = float(weather_df["lat"].iloc[0]) if "lat" in weather_df.columns else 0.0
    lon = float(weather_df["lon"].iloc[0]) if "lon" in weather_df.columns else 0.0
    scene_count = len(ndvi_df)
    weather_days = len(weather_df)

    title_text = (
        f"Field {field_slug}  ·  {year}  ·  {crop}\n"
        f"Lat {lat:.4f}°N, Lon {abs(lon):.4f}°W  ·  "
        f"{scene_count} Sentinel scenes  ·  {weather_days} weather days"
    )
    fig.suptitle(
        title_text,
        fontsize=14,
        fontweight="bold",
        y=0.98,
        color="#1e293b",
    )

    gs = fig.add_gridspec(
        4, 1, hspace=0.35, left=0.08, right=0.92, top=0.93, bottom=0.06
    )

    # Shared x-axis limits
    xlim = (_DISPLAY_START_DOY, _DISPLAY_END_DOY)

    # Color palette
    NDVI_COLOR = "#059669"
    PRECIP_BAR = "#93c5fd"
    PRECIP_LINE = "#1e40af"
    TEMP_FILL = "#cbd5e1"
    TEMP_LINE = "#475569"
    GDD_COLOR = "#ea580c"
    GS_BAND = _GS_BAND_COLOR

    # ---------------------------------------------------------------
    # Panel 1: NDVI
    # ---------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#ffffff")

    # Growing-season band
    ax1.axvspan(_GS_START_DOY, _GS_END_DOY, color=GS_BAND, alpha=0.6, zorder=0)

    # NDVI line + points
    if not ndvi_df.empty:
        ax1.plot(
            ndvi_df["doy"],
            ndvi_df["mean_ndvi"],
            color=NDVI_COLOR,
            linewidth=2,
            zorder=2,
            label="Mean NDVI",
        )
        for _, row in ndvi_df.iterrows():
            color = NDVI_COLOR
            if row["cloud_cover"] > _CLOUD_WARNING_PCT:
                color = "#f59e0b"
            ax1.scatter(
                row["doy"],
                row["mean_ndvi"],
                color=color,
                s=60,
                zorder=3,
                edgecolors="white",
                linewidths=0.5,
            )
            if row["cloud_cover"] > _CLOUD_WARNING_PCT:
                ax1.annotate(
                    f"⚠ {row['cloud_cover']:.0f}%",
                    (row["doy"], row["mean_ndvi"]),
                    textcoords="offset points",
                    xytext=(0, 12),
                    fontsize=7,
                    color="#b45309",
                    ha="center",
                )

    # NDVI event annotations
    ndvi_events = [e for e in events if e.get("panel") == "ndvi"]
    for evt in ndvi_events:
        doy = evt["doy"]
        # Find y position
        match = ndvi_df[ndvi_df["doy"] == doy]
        y = float(match["mean_ndvi"].iloc[0]) if not match.empty else 0.5
        ax1.annotate(
            evt["label"],
            (doy, y),
            textcoords="offset points",
            xytext=(10, 15),
            fontsize=8,
            fontweight="bold",
            color="#065f46" if "greenup" in evt["type"] else "#9a3412",
            arrowprops=dict(arrowstyle="->", color="#64748b", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f0fdf4" if "greenup" in evt["type"] else "#fff7ed", edgecolor="none", alpha=0.9),
        )

    ax1.set_xlim(xlim)
    ax1.set_ylim(-0.05, 1.05)
    ax1.set_ylabel("NDVI", fontsize=10, fontweight="bold")
    ax1.set_title("NDVI Time-Series", fontsize=12, fontweight="bold", loc="left", pad=10)
    ax1.grid(True, alpha=0.25)
    ax1.tick_params(axis="both", labelsize=9)

    # ---------------------------------------------------------------
    # Panel 2: Precipitation
    # ---------------------------------------------------------------
    ax2 = fig.add_subplot(gs[1])
    ax2.set_facecolor("#ffffff")
    ax2.axvspan(_GS_START_DOY, _GS_END_DOY, color=GS_BAND, alpha=0.6, zorder=0)

    if not weather_df.empty:
        # Daily bars
        ax2.bar(
            weather_df["doy"],
            weather_df["PRECTOTCORR"],
            color=PRECIP_BAR,
            width=1.0,
            zorder=1,
            label="Daily precip",
        )
        # Cumulative line on secondary axis
        ax2_twin = ax2.twinx()
        ax2_twin.plot(
            weather_df["doy"],
            weather_df["precip_cumulative"],
            color=PRECIP_LINE,
            linewidth=1.5,
            zorder=2,
            label="Cumulative",
        )
        ax2_twin.set_ylabel("Cumulative (mm)", fontsize=9, color=PRECIP_LINE)
        ax2_twin.tick_params(axis="y", labelsize=9, labelcolor=PRECIP_LINE)

    # Precip event annotations
    precip_events = [e for e in events if e.get("panel") == "precip"]
    for evt in precip_events:
        doy = evt["doy"]
        match = weather_df[weather_df["doy"] == doy]
        y = float(match["PRECTOTCORR"].iloc[0]) if not match.empty else 20
        ax2.annotate(
            evt["label"],
            (doy, y),
            textcoords="offset points",
            xytext=(10, 15),
            fontsize=8,
            fontweight="bold",
            color="#1e40af",
            arrowprops=dict(arrowstyle="->", color="#64748b", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#eff6ff", edgecolor="none", alpha=0.9),
        )

    ax2.set_xlim(xlim)
    ax2.set_ylabel("Precipitation (mm/day)", fontsize=10, fontweight="bold")
    ax2.set_title("Daily Precipitation & Cumulative Total", fontsize=12, fontweight="bold", loc="left", pad=10)
    ax2.grid(True, axis="y", alpha=0.25)
    ax2.tick_params(axis="both", labelsize=9)

    # ---------------------------------------------------------------
    # Panel 3: Temperature & Extremes
    # ---------------------------------------------------------------
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor("#ffffff")
    ax3.axvspan(_GS_START_DOY, _GS_END_DOY, color=GS_BAND, alpha=0.6, zorder=0)

    if not weather_df.empty:
        ax3.fill_between(
            weather_df["doy"],
            weather_df["T2M_MIN"],
            weather_df["T2M_MAX"],
            color=TEMP_FILL,
            alpha=0.5,
            zorder=1,
            label="Min–Max range",
        )
        ax3.plot(
            weather_df["doy"],
            weather_df["T2M"],
            color=TEMP_LINE,
            linewidth=1.0,
            zorder=2,
            label="Mean temp",
        )

    # Frost lines (full-year, not just GS)
    frost_df = weather_df.copy()
    cold = frost_df[frost_df["T2M_MIN"] <= 0]
    spring_frost = cold[cold["doy"] <= 180]
    fall_frost = cold[cold["doy"] > 180]
    if not spring_frost.empty:
        last_frost = int(spring_frost["doy"].max())
        ax3.axvline(last_frost, color="#2563eb", linestyle="--", linewidth=1.0, alpha=0.7)
        ax3.text(last_frost + 2, ax3.get_ylim()[1] * 0.9, f"Last frost\nDOY {last_frost}", fontsize=7, color="#1d4ed8", va="top")
    if not fall_frost.empty:
        first_frost = int(fall_frost["doy"].min())
        ax3.axvline(first_frost, color="#b45309", linestyle="--", linewidth=1.0, alpha=0.7)
        ax3.text(first_frost + 2, ax3.get_ylim()[1] * 0.75, f"First frost\nDOY {first_frost}", fontsize=7, color="#92400e", va="top")

    # Temp event annotations
    temp_events = [e for e in events if e.get("panel") == "temp"]
    for evt in temp_events:
        doy = evt["doy"]
        match = weather_df[weather_df["doy"] == doy]
        y = float(match["T2M_MAX"].iloc[0]) if not match.empty else 30
        color = "#dc2626" if evt["type"] == "heat_stress" else "#7c3aed"
        facecolor = "#fef2f2" if evt["type"] == "heat_stress" else "#faf5ff"
        ax3.annotate(
            evt["label"],
            (doy, y),
            textcoords="offset points",
            xytext=(10, 12),
            fontsize=8,
            fontweight="bold",
            color=color,
            arrowprops=dict(arrowstyle="->", color="#64748b", lw=0.8),
            bbox=dict(boxstyle="round,pad=0.3", facecolor=facecolor, edgecolor="none", alpha=0.9),
        )

    ax3.set_xlim(xlim)
    ax3.set_ylabel("Temperature (°C)", fontsize=10, fontweight="bold")
    ax3.set_title("Temperature & Extremes", fontsize=12, fontweight="bold", loc="left", pad=10)
    ax3.grid(True, alpha=0.25)
    ax3.tick_params(axis="both", labelsize=9)

    # ---------------------------------------------------------------
    # Panel 4: Cumulative GDD
    # ---------------------------------------------------------------
    ax4 = fig.add_subplot(gs[3])
    ax4.set_facecolor("#ffffff")
    ax4.axvspan(_GS_START_DOY, _GS_END_DOY, color=GS_BAND, alpha=0.6, zorder=0)

    if not weather_df.empty:
        ax4.plot(
            weather_df["doy"],
            weather_df["gdd_cumulative"],
            color=GDD_COLOR,
            linewidth=2,
            zorder=2,
            label="Cumulative GDD",
        )

    ax4.set_xlim(xlim)
    ax4.set_ylabel("Cumulative GDD (base 10°C)", fontsize=10, fontweight="bold")
    ax4.set_title("Cumulative Growing Degree Days", fontsize=12, fontweight="bold", loc="left", pad=10)
    ax4.grid(True, alpha=0.25)
    ax4.tick_params(axis="both", labelsize=9)

    # Shared X label on bottom panel only
    ax4.set_xlabel("Day of year (Mar – Nov)", fontsize=10, fontweight="bold")

    # Month tick labels
    for ax in [ax1, ax2, ax3, ax4]:
        ax.set_xticks([60, 91, 121, 152, 182, 213, 244, 274, 305, 335])
        ax.set_xticklabels(["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", ""])

    # ---------------------------------------------------------------
    # Bottom caption
    # ---------------------------------------------------------------
    caption_lines = _generate_caption(events, ndvi_df, weather_df)
    fig.text(
        0.5,
        0.02,
        "\n".join(caption_lines),
        ha="center",
        va="bottom",
        fontsize=9,
        color="#475569",
        wrap=True,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f8fafc", edgecolor="#e2e8f0", alpha=0.9),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Dashboard saved: {output_path}")


def _generate_caption(
    events: list[dict[str, Any]], ndvi_df: pd.DataFrame, weather_df: pd.DataFrame
) -> list[str]:
    """Generate 2–3 concise caption lines summarizing key changes."""
    lines: list[str] = []

    # Peak NDVI
    peak = next((e for e in events if e["type"] == "peak_ndvi"), None)
    if peak:
        lines.append(
            f"NDVI peaked at {peak['value']:.2f} by DOY {peak['doy']} — supported by strong GDD accumulation through mid-season."
        )

    # Rapid green-up
    greenup = next((e for e in events if e["type"] == "rapid_greenup"), None)
    if greenup:
        lines.append(
            f"Rapid green-up (+{greenup['value']:.2f}) around DOY {greenup['doy']} coincides with warming temperatures and adequate moisture."
        )

    # Key weather event
    heavy_rain = next((e for e in events if e["type"] == "heavy_rain"), None)
    heat = next((e for e in events if e["type"] == "heat_stress"), None)
    if heavy_rain:
        lines.append(
            f"Heavy rainfall event ({heavy_rain['value']:.1f} mm) at DOY {heavy_rain['doy']} — check Panel 2 for timing against NDVI response."
        )
    elif heat:
        lines.append(
            f"Heat stress reached {heat['value']:.1f}°C at DOY {heat['doy']} — scan Panel 3 and Panel 1 for linked NDVI response."
        )

    if not lines:
        lines.append("Growing season NDVI and weather aligned. No extreme events detected in the selected thresholds.")

    return lines[:3]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate field-year NDVI + weather dashboard")
    parser.add_argument("--field-slug", required=True, help="Field identifier")
    parser.add_argument("--year", type=int, required=True, help="Crop year")
    parser.add_argument("--grower", default=_DEFAULT_GROWER, help="Grower slug")
    parser.add_argument("--farm", default=_DEFAULT_FARM, help="Farm slug")
    parser.add_argument("--force", action="store_true", help="Regenerate even if cached")
    args = parser.parse_args()

    field_slug = args.field_slug
    year = args.year
    grower = args.grower
    farm = args.farm
    force = args.force or os.environ.get("AG_FORCE") == "1"

    print("=" * 60)
    print("Field-Year Dashboard")
    print("=" * 60)
    print(f"Field: {field_slug}  |  Year: {year}")

    # Verify inputs exist
    weather_path = field_weather_path(grower, farm, field_slug)
    manifest_path = field_satellite_dir(grower, farm, field_slug) / "sentinel" / "manifest.json"
    if not weather_path.exists():
        raise FileNotFoundError(f"Weather missing: {weather_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest missing: {manifest_path}")

    # Load data
    ndvi_df = _extract_ndvi_timeseries(field_slug, year, grower, farm)
    weather_df = _load_weather_year(field_slug, year, grower, farm)

    print(f"  NDVI scenes: {len(ndvi_df)}")
    print(f"  Weather days: {len(weather_df)}")

    if ndvi_df.empty:
        raise RuntimeError("No NDVI scenes found for this field-year.")
    if weather_df.empty:
        raise RuntimeError("No weather records found for this field-year.")

    # Quality checks
    if len(ndvi_df) < 3:
        raise RuntimeError(f"Too few NDVI scenes ({len(ndvi_df)}); minimum is 3.")
    if len(weather_df) < 365:
        print(f"  ⚠ Warning: only {len(weather_df)} weather days (expected 365).")

    gs_ndvi = ndvi_df[(ndvi_df["doy"] >= _GS_START_DOY) & (ndvi_df["doy"] <= _GS_END_DOY)]
    for i in range(1, len(gs_ndvi)):
        gap = int(gs_ndvi.iloc[i]["doy"] - gs_ndvi.iloc[i - 1]["doy"])
        if gap > 45:
            print(f"  ⚠ Warning: NDVI gap of {gap} days around DOY {int(gs_ndvi.iloc[i-1]['doy'])}")

    # Determine crop from CDL join table
    cdl_join_path = (
        field_dir(grower, farm, field_slug)
        / "derived"
        / "tables"
        / "ndvi_year_crop_join.csv"
    )
    crop = "Unknown"
    if cdl_join_path.exists():
        cdl_join = pd.read_csv(cdl_join_path)
        match = cdl_join[(cdl_join["field_slug"] == field_slug) & (cdl_join["year"] == year)]
        if not match.empty:
            crop = str(match.iloc[0]["crop_name"])
    print(f"  CDL crop: {crop}")

    # Detect events
    weather_events = _detect_weather_events(weather_df)
    ndvi_events = _detect_ndvi_events(ndvi_df)
    cross_events = _link_cross_events(weather_events, ndvi_events)
    all_events = weather_events + ndvi_events + cross_events
    print(f"  Events detected: {len(all_events)}")

    # Build dashboard
    output_path = field_report_path(
        grower, farm, field_slug, f"field_year_dashboard_{year}.png"
    )

    # Simple idempotency via file existence unless forced
    if output_path.exists() and not force:
        print(f"  Cached dashboard exists. Use --force to regenerate.")
        print(f"  {output_path}")
        return

    _build_dashboard(field_slug, year, crop, ndvi_df, weather_df, all_events, output_path)

    print("Done.")


if __name__ == "__main__":
    main()
