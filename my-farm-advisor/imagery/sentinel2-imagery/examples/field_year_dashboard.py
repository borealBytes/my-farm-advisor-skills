#!/usr/bin/env python3
"""Generate a field-year aligned dashboard PNG.

Usage:
    python field_year_dashboard.py --year 2022
    python field_year_dashboard.py --year 2022 --output ./my_dashboard.png
    python field_year_dashboard.py --all-years

Defaults to field osm-1499460321, farm il-grower-illinois, grower il-grower.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

matplotlib.use("Agg")

# Font configuration — modern sans-serif with fallbacks
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Source Sans Pro",
    "Helvetica",
    "Arial",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

# Add lib/ to path for align_field_year
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

from align_field_year import load_aligned_field_year, AlignedFieldYear, Event


# ---------------------------------------------------------------------------
# Panel colour palette (infographic style)
# ---------------------------------------------------------------------------
_PANEL_COLORS = {
    1: "#4E9A72",  # Forest Green — NDVI
    2: "#5A8DEE",  # Royal Blue — Precipitation
    3: "#F4A261",  # Soft Orange — Temperature
    4: "#63A35C",  # Dark Green — GDD
}


# ---------------------------------------------------------------------------
# Scientific annotation dataclass
# ---------------------------------------------------------------------------

@dataclass
class SciAnnotation:
    doy: int
    title: str
    subtitle: str = ""
    doy_range: str = ""  # e.g. "DOY 189–214"


# ---------------------------------------------------------------------------
# Helpers: size estimation (data ↔ display)
# ---------------------------------------------------------------------------

def _line_height_data(ax, font_size_pt: float = 10.5) -> float:
    """Approximate height of one text line in data coordinates."""
    y_min, y_max = ax.get_ylim()
    fig = ax.get_figure()
    bbox = ax.get_position()
    ax_height_in = bbox.height * fig.get_figheight()
    line_height_in = font_size_pt / 72.0 * 1.25  # 1.25× for comfortable leading
    return line_height_in / ax_height_in * (y_max - y_min)


def _text_width_data(ax, n_chars: int, font_size_pt: float = 10.5) -> float:
    """Approximate width of a text string in data coordinates."""
    x_min, x_max = ax.get_xlim()
    fig = ax.get_figure()
    bbox = ax.get_position()
    ax_width_in = bbox.width * fig.get_figwidth()
    char_width_in = font_size_pt / 72.0 * 0.52  # ~0.52 em for sans-serif
    text_width_in = n_chars * char_width_in
    return text_width_in / ax_width_in * (x_max - x_min)


# ---------------------------------------------------------------------------
# Infographic-style annotation renderer
# ---------------------------------------------------------------------------

def _draw_infographic_annotation(
    ax,
    anno: SciAnnotation,
    panel_color: str,
    box_x: float,
    box_top: float,
    target_x: float,
    target_y: float,
):
    """Draw a single publication-quality annotation with L-shaped leader."""

    line_h = _line_height_data(ax, 10.5)
    n_lines = 2 + (1 if anno.doy_range else 0)
    internal_pad = line_h * 0.35
    box_bottom = box_top - line_h * n_lines - internal_pad * 2
    box_height = box_top - box_bottom

    # Width: max of estimated text width + padding, or a minimum fraction
    x_min, x_max = ax.get_xlim()
    x_range = x_max - x_min
    title_w = _text_width_data(ax, len(anno.title), 10.5)
    sub_w = _text_width_data(ax, len(anno.subtitle), 8.5)
    doy_w = _text_width_data(ax, len(anno.doy_range), 8.5) if anno.doy_range else 0
    content_w = max(title_w, sub_w, doy_w)
    box_width = max(content_w + line_h * 1.2, x_range * 0.14)

    # Draw rounded rectangle background
    rect = FancyBboxPatch(
        (box_x - box_width / 2, box_bottom),
        box_width,
        box_height,
        boxstyle="round,pad=0.005,rounding_size=0.015",
        facecolor="white",
        edgecolor=panel_color,
        linewidth=1.0,
        alpha=0.95,
        zorder=15,
        clip_on=False,
        transform=ax.transData,
    )
    ax.add_patch(rect)

    # Draw multi-line text
    title_y = box_top - internal_pad - line_h * 0.25
    sub_y = title_y - line_h * 1.15
    doy_y = sub_y - line_h * 1.15 if anno.doy_range else None

    ax.text(
        box_x,
        title_y,
        anno.title,
        size=10.5,
        weight="semibold",
        color="#303030",
        ha="center",
        va="top",
        zorder=16,
        clip_on=False,
        family="sans-serif",
    )
    ax.text(
        box_x,
        sub_y,
        anno.subtitle,
        size=8.5,
        color="#5F5F5F",
        ha="center",
        va="top",
        zorder=16,
        clip_on=False,
        family="sans-serif",
    )
    if doy_y is not None:
        ax.text(
            box_x,
            doy_y,
            anno.doy_range,
            size=8.5,
            color="#5F5F5F",
            ha="center",
            va="top",
            zorder=16,
            clip_on=False,
            family="sans-serif",
        )

    # L-shaped leader: horizontal from box bottom-centre to target x,
    # then vertical down to target y
    leader_y = box_bottom
    ax.plot(
        [box_x, target_x, target_x],
        [leader_y, leader_y, target_y],
        color=panel_color,
        linewidth=0.8,
        alpha=0.45,
        solid_capstyle="butt",
        zorder=14,
        clip_on=False,
    )


def _place_annotations(
    ax,
    annotations: List[SciAnnotation],
    panel_color: str,
    data_df: pd.DataFrame,
    value_col: str,
    max_count: int = 5,
):
    """Evenly distribute annotations across panel width with aligned top edges."""
    if not annotations:
        return

    annotations = annotations[:max_count]
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    x_min, x_max = ax.get_xlim()
    x_range = x_max - x_min

    # All boxes share the same top edge
    box_top = y_max - 0.04 * y_range

    n = len(annotations)
    slot_width = x_range / n

    for i, anno in enumerate(annotations):
        # Target data value at event DOY
        target_x = float(anno.doy)
        rows = data_df[data_df["doy"] == anno.doy]
        if not rows.empty:
            target_y = float(rows.iloc[0][value_col])
        else:
            idx = (data_df["doy"] - anno.doy).abs().idxmin()
            target_y = float(data_df.loc[idx, value_col])

        # Box x: centre of slot, nudged toward DOY if DOY is near slot centre
        slot_centre = x_min + (i + 0.5) * slot_width
        # Clamp so box stays well inside its slot
        margin = slot_width * 0.12
        box_x = max(x_min + i * slot_width + margin,
                    min(slot_centre, target_x + slot_width * 0.25))
        box_x = min(box_x, x_min + (i + 1) * slot_width - margin)

        _draw_infographic_annotation(
            ax, anno, panel_color, box_x, box_top, target_x, target_y
        )


# ---------------------------------------------------------------------------
# Panel-specific scientific annotation builders (data-driven)
# ---------------------------------------------------------------------------

def _build_ndvi_phase_annotations(ndvi_df: pd.DataFrame) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    if ndvi_df.empty or len(ndvi_df) < 3:
        return annos

    df = ndvi_df.copy().sort_values("doy").reset_index(drop=True)
    peak_ndvi = float(df["mean_ndvi"].max())
    peak_idx = int(df["mean_ndvi"].idxmax())
    peak_doy = int(df.iloc[peak_idx]["doy"])

    # 1. Green-up Initiation
    greenup = df[(df["mean_ndvi"] > 0.20) & (df["doy"] > 100)]
    if not greenup.empty:
        doy = int(df.iloc[int(greenup.index[0])]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Green-up Initiation", subtitle="NDVI rise begins"))

    # 2. Rapid Canopy Development
    df["delta"] = df["mean_ndvi"].diff()
    rapid_start = None
    rapid_end = None
    max_rise = 0.0
    for i in range(1, len(df) - 1):
        if df.iloc[i]["delta"] > 0 and df.iloc[i + 1]["delta"] > 0:
            rise = df.iloc[i + 1]["mean_ndvi"] - df.iloc[i - 1]["mean_ndvi"]
            if rise > max_rise:
                max_rise = rise
                rapid_start = int(df.iloc[i - 1]["doy"])
                rapid_end = int(df.iloc[i + 1]["doy"])
    if rapid_start is not None and rapid_end is not None and rapid_end > rapid_start:
        annos.append(
            SciAnnotation(
                doy=rapid_start,
                title="Rapid Canopy Development",
                subtitle="Accelerated canopy growth",
                doy_range=f"DOY {rapid_start}–{rapid_end}",
            )
        )

    # 3. Peak Canopy Greenness
    if len(df) > 1:
        start_doy = int(df.iloc[max(0, peak_idx - 1)]["doy"])
        end_doy = int(df.iloc[min(len(df) - 1, peak_idx + 1)]["doy"])
        annos.append(
            SciAnnotation(
                doy=peak_doy,
                title="Peak Canopy Greenness",
                subtitle="Maximum vegetation vigor",
                doy_range=f"DOY {start_doy}–{end_doy}",
            )
        )

    # 4. Onset of Senescence
    post_peak = df.iloc[peak_idx + 1 :].copy()
    senescence = post_peak[post_peak["mean_ndvi"] < (peak_ndvi - 0.10)]
    if not senescence.empty:
        idx = int(senescence.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Onset of Senescence", subtitle="Declining canopy greenness"))

    # 5. Late-Season Senescence
    late = post_peak[post_peak["mean_ndvi"] < (peak_ndvi * 0.50)]
    if not late.empty:
        idx = int(late.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Late-Season Senescence", subtitle="Post-peak vegetation decline"))

    return annos[:5]


def _build_precip_annotations(weather_df: pd.DataFrame, events: List[Event]) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    heavy_rains = [e for e in events if e.event_type == "heavy_rain"]
    for ev in heavy_rains[:5]:
        val = ev.value if ev.value is not None else 0.0
        annos.append(
            SciAnnotation(
                doy=ev.doy,
                title="Major Rainfall Event",
                subtitle=f"{val:.1f} mm",
                doy_range=f"DOY {ev.doy}",
            )
        )
    return annos


def _build_temp_phase_annotations(weather_df: pd.DataFrame) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    if weather_df.empty:
        return annos

    df = weather_df.copy().sort_values("doy").reset_index(drop=True)
    median_t = float(df["T2M"].median())

    # Seasonal Warming
    df["t7"] = df["T2M"].rolling(window=7, min_periods=1).mean()
    warming = df[(df["t7"] > median_t) & (df["doy"] > 60)]
    if not warming.empty:
        doy = int(warming.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Seasonal Warming", subtitle="Sustained temperature increase"))

    # Warm Period
    max_t7_idx = int(df["t7"].idxmax())
    warm_doy = int(df.iloc[max_t7_idx]["doy"])
    annos.append(SciAnnotation(doy=warm_doy, title="Warm Period", subtitle="Elevated seasonal temperatures"))

    # Peak Seasonal Temperature
    max_idx = int(df["T2M_MAX"].idxmax())
    peak_doy = int(df.iloc[max_idx]["doy"])
    annos.append(SciAnnotation(doy=peak_doy, title="Peak Seasonal Temperature", subtitle="Maximum seasonal heat"))

    # Cooling Trend
    cooling = df[(df["t7"] < median_t) & (df["doy"] > warm_doy)]
    if not cooling.empty:
        doy = int(cooling.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Cooling Trend", subtitle="Declining temperatures"))

    # Autumn Temperature Decline
    late = df[(df["doy"] > 270) & (df["T2M_MAX"] < 15.0)]
    if not late.empty:
        doy = int(late.iloc[-1]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Autumn Temperature Decline", subtitle="Post-season cooling"))

    return annos[:5]


def _build_gdd_phase_annotations(weather_df: pd.DataFrame) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    if weather_df.empty:
        return annos

    df = weather_df.copy().sort_values("doy").reset_index(drop=True)
    max_gdd = float(df["gdd_cum"].max())
    if max_gdd <= 0:
        return annos

    init = df[df["gdd_cum"] > 200]
    if not init.empty:
        doy = int(init.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Thermal Accumulation Initiated", subtitle="Early-season heat accumulation"))

    half = df[df["gdd_cum"] > (max_gdd * 0.50)]
    if not half.empty:
        doy = int(half.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Accelerated Heat Accumulation", subtitle="Rapid GDD increase"))

    three_q = df[df["gdd_cum"] > (max_gdd * 0.75)]
    if not three_q.empty:
        doy = int(three_q.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Continued GDD Accumulation", subtitle="Sustained thermal accumulation"))

    df["low_gdd"] = df["gdd_daily"] < 5.0
    streak = 0
    plateau_doy = None
    for i, is_low in enumerate(df["low_gdd"]):
        if is_low:
            streak += 1
            if streak >= 5 and plateau_doy is None:
                plateau_doy = int(df.iloc[i]["doy"])
        else:
            streak = 0
    if plateau_doy is not None:
        annos.append(SciAnnotation(doy=plateau_doy, title="Thermal Accumulation Plateau", subtitle="Seasonal accumulation peak"))

    return annos[:5]


# ---------------------------------------------------------------------------
# Month / DOY helpers
# ---------------------------------------------------------------------------

def _month_ticks(start_doy: int, end_doy: int) -> tuple[list[int], list[str]]:
    ticks = []
    labels = []
    for doy in range(start_doy, end_doy + 1):
        d = pd.to_datetime(f"2022-{doy:03d}", format="%Y-%j")
        if d.day == 15:
            ticks.append(doy)
            labels.append(d.strftime("%b"))
    return ticks, labels


def _generate_caption(aligned: AlignedFieldYear) -> str:
    bullets = []
    ndf = aligned.ndvi_df
    wdf = aligned.weather_df

    if not ndf.empty and aligned.summary.get("ndvi_peak_doy"):
        peak_doy = aligned.summary["ndvi_peak_doy"]
        peak_ndvi = aligned.summary.get("ndvi_peak", 0)
        bullets.append(f"NDVI peaked at DOY {peak_doy} ({peak_ndvi:.2f}) — Panel 1")
        if not wdf.empty:
            window = wdf[(wdf["doy"] >= peak_doy - 7) & (wdf["doy"] <= peak_doy + 7)]
            if not window.empty:
                precip = window["PRECTOTCORR"].sum()
                tmax = window["T2M_MAX"].max()
                bullets.append(f"Week around peak: {precip:.0f} mm rain, {tmax:.1f}°C max — Panels 2–3")
        cum_gdd = wdf[wdf["doy"] == peak_doy]["gdd_cum"]
        if not cum_gdd.empty:
            gdd_val = float(cum_gdd.iloc[0])
            stage = ""
            if aligned.crop.name.lower() == "corn":
                if gdd_val >= 1200:
                    stage = "near VT"
                elif gdd_val >= 800:
                    stage = "near V12"
                elif gdd_val >= 500:
                    stage = "near V6"
            bullets.append(f"Cumulative GDD at peak: {gdd_val:.0f} °C·day{stage and ' (' + stage + ')' or ''} — Panel 4")

    return "\n".join(f"  • {b}" for b in bullets[:3])


# ---------------------------------------------------------------------------
# Dashboard plotter — ALL PLOT CODE PRESERVED EXACTLY
# ---------------------------------------------------------------------------

def plot_dashboard(aligned: AlignedFieldYear, output_path: Path) -> None:
    fig = plt.figure(figsize=(14, 20))
    fig.patch.set_facecolor("#fafaf9")

    loc = f"{aligned.summary.get('lat', 0):.4f}°N, {abs(aligned.summary.get('lon', 0)):.4f}°W"
    fig.suptitle(
        f"Field-Year Dashboard  ·  {aligned.field_id}  ·  {aligned.year}  ·  {aligned.crop.name} "
        f"({aligned.crop.pct:.1f}%)  ·  {loc}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
        color="#1e293b",
    )

    gs = fig.add_gridspec(4, 1, hspace=0.32, left=0.08, right=0.95, top=0.94, bottom=0.10)

    wdf = aligned.weather_df
    ndf = aligned.ndvi_df
    xlim = (aligned.season_start_doy, aligned.season_end_doy)

    major_doys = list(range(60, 321, 30))
    month_ticks, month_labels = _month_ticks(xlim[0], xlim[1])

    # -----------------------------------------------------------------
    # Panel 1: NDVI + cumulative GDD overlay
    # -----------------------------------------------------------------
    ax1 = fig.add_subplot(gs[0, 0])
    if not ndf.empty:
        ax1.errorbar(
            ndf["doy"],
            ndf["mean_ndvi"],
            yerr=ndf["std_ndvi"],
            fmt="o-",
            color="#166534",
            ecolor="#86efac",
            capsize=3,
            linewidth=1.5,
            markersize=5,
            label="Mean NDVI ± σ",
            zorder=3,
        )
        ax1.set_ylabel("NDVI (unitless)", fontsize=11, color="#166534")
        ax1.set_ylim(-0.05, 1.05)
        ax1.tick_params(axis="y", labelcolor="#166534")

        if not wdf.empty:
            ax1_gdd = ax1.twinx()
            ax1_gdd.plot(
                wdf["doy"],
                wdf["gdd_cum"],
                color="#86efac",
                linestyle="--",
                linewidth=1.0,
                alpha=0.7,
                label="Cum. GDD",
                zorder=2,
            )
            ax1_gdd.set_ylabel("Cumulative GDD (°C·day)", fontsize=10, color="#86efac")
            ax1_gdd.tick_params(axis="y", labelcolor="#86efac")
            ax1_gdd.set_ylim(0, wdf["gdd_cum"].max() * 1.3)
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax1_gdd.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
        else:
            ax1.legend(loc="upper left", fontsize=8)

        ndvi_annos = _build_ndvi_phase_annotations(ndf)
        _place_annotations(ax1, ndvi_annos, _PANEL_COLORS[1], ndf, "mean_ndvi", max_count=5)
    else:
        ax1.text(0.5, 0.5, "No NDVI data", ha="center", va="center", transform=ax1.transAxes)
    ax1.set_title(
        "Panel 1: NDVI (unitless) & Cumulative GDD overlay",
        fontsize=12, fontweight="bold", loc="left", pad=8,
    )
    ax1.set_xlim(*xlim)
    for d in major_doys:
        ax1.axvline(d, color="#e2e8f0", linewidth=0.5, zorder=1)
    ax1.tick_params(labelbottom=False)
    ax1.grid(True, alpha=0.3, axis="y")

    # -----------------------------------------------------------------
    # Panel 2: Precipitation
    # -----------------------------------------------------------------
    ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
    if not wdf.empty:
        ax2.bar(
            wdf["doy"],
            wdf["PRECTOTCORR"],
            color="#3b82f6",
            alpha=0.7,
            width=1.0,
            label="Daily",
            zorder=3,
        )
        ax2_twin = ax2.twinx()
        ax2_twin.plot(
            wdf["doy"],
            wdf["precip_cum"],
            color="#1e3a8a",
            linewidth=1.5,
            label="Cumulative",
            zorder=2,
        )
        ax2_twin.set_ylabel("Cumulative (mm)", fontsize=10, color="#1e3a8a")
        ax2_twin.tick_params(axis="y", labelcolor="#1e3a8a")
        ax2_twin.set_ylim(0, wdf["precip_cum"].max() * 1.2)
        ax2.set_ylabel("Daily precip (mm)", fontsize=11)
        ax2.set_ylim(0, wdf["PRECTOTCORR"].max() * 1.5 + 5)
        ax2.legend(loc="upper left", fontsize=8)
        ax2_twin.legend(loc="upper right", fontsize=8)

        precip_annos = _build_precip_annotations(wdf, aligned.events_weather)
        _place_annotations(ax2, precip_annos, _PANEL_COLORS[2], wdf, "PRECTOTCORR", max_count=5)
    else:
        ax2.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax2.transAxes)
    ax2.set_title(
        "Panel 2: Precipitation (mm)",
        fontsize=12, fontweight="bold", loc="left", pad=8,
    )
    for d in major_doys:
        ax2.axvline(d, color="#e2e8f0", linewidth=0.5, zorder=1)
    ax2.tick_params(labelbottom=False)
    ax2.grid(True, alpha=0.3, axis="y")

    # -----------------------------------------------------------------
    # Panel 3: Temperature & extremes
    # -----------------------------------------------------------------
    ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)
    if not wdf.empty:
        ax3.fill_between(
            wdf["doy"],
            wdf["T2M_MIN"],
            wdf["T2M_MAX"],
            alpha=0.25,
            color="#f97316",
            label="Daily range",
            zorder=2,
        )
        ax3.plot(wdf["doy"], wdf["T2M"], color="#1e293b", linewidth=0.8, label="Mean", zorder=3)
        ax3.plot(wdf["doy"], wdf["T2M_MAX"], color="#dc2626", linewidth=0.4, alpha=0.6, zorder=2)
        ax3.plot(wdf["doy"], wdf["T2M_MIN"], color="#2563eb", linewidth=0.4, alpha=0.6, zorder=2)
        ax3.axhline(0, color="#94a3b8", linestyle="--", linewidth=0.8, zorder=1)
        ax3.set_ylabel("Temperature (°C)", fontsize=11)
        ax3.set_ylim(
            wdf["T2M_MIN"].min() - 5,
            wdf["T2M_MAX"].max() + 5,
        )
        ax3.legend(loc="upper right", fontsize=8)

        temp_annos = _build_temp_phase_annotations(wdf)
        _place_annotations(ax3, temp_annos, _PANEL_COLORS[3], wdf, "T2M", max_count=5)
    else:
        ax3.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax3.transAxes)
    ax3.set_title(
        "Panel 3: Temperature & Extremes (°C)",
        fontsize=12, fontweight="bold", loc="left", pad=8,
    )
    for d in major_doys:
        ax3.axvline(d, color="#e2e8f0", linewidth=0.5, zorder=1)
    ax3.tick_params(labelbottom=False)
    ax3.grid(True, alpha=0.3)

    # -----------------------------------------------------------------
    # Panel 4: Cumulative GDD with growth-stage bands
    # -----------------------------------------------------------------
    ax4 = fig.add_subplot(gs[3, 0], sharex=ax1)
    if not wdf.empty:
        ax4.plot(
            wdf["doy"],
            wdf["gdd_cum"],
            color="#15803d",
            linewidth=2.0,
            label="Cumulative GDD (base 10°C)",
            zorder=3,
        )
        if aligned.crop.name.lower() == "corn":
            stages = [
                (500, "V6", "#86efac"),
                (800, "V12", "#bef264"),
                (1200, "VT", "#fde047"),
                (1600, "R2", "#fdba74"),
            ]
            for gdd_target, stage_name, color in stages:
                ax4.axhline(gdd_target, color=color, linestyle="--", linewidth=1.0, alpha=0.7, zorder=2)
                ax4.text(
                    xlim[1] - 3,
                    gdd_target + 40,
                    stage_name,
                    color="#374151",
                    fontsize=8,
                    ha="right",
                    va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.5, edgecolor="none"),
                    zorder=4,
                )
        ax4.set_ylabel("GDD (°C·day)", fontsize=11)
        ax4.set_xlabel("Day of Year", fontsize=11)
        ax4.legend(loc="upper left", fontsize=8)

        gdd_annos = _build_gdd_phase_annotations(wdf)
        _place_annotations(ax4, gdd_annos, _PANEL_COLORS[4], wdf, "gdd_cum", max_count=5)
    else:
        ax4.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax4.transAxes)
    ax4.set_title(
        "Panel 4: Cumulative Growing Degree Days (°C·day)",
        fontsize=12, fontweight="bold", loc="left", pad=8,
    )
    for d in major_doys:
        ax4.axvline(d, color="#e2e8f0", linewidth=0.5, zorder=1)
    ax4.grid(True, alpha=0.3)

    ax4.set_xticks(major_doys)
    ax4.set_xticklabels([str(d) for d in major_doys], fontsize=9)

    ax4_month = ax4.twiny()
    ax4_month.set_xlim(ax4.get_xlim())
    ax4_month.set_xticks(month_ticks)
    ax4_month.set_xticklabels(month_labels, fontsize=9, color="#64748b")
    ax4_month.tick_params(axis="x", labelcolor="#64748b")
    ax4_month.spines["top"].set_color("#cbd5e1")
    ax4_month.spines["top"].set_linewidth(0.5)

    # Synthesis caption
    caption = _generate_caption(aligned)
    if caption:
        fig.text(
            0.08,
            0.04,
            "Key observations:\n" + caption,
            fontsize=9,
            color="#334155",
            ha="left",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f1f5f9", alpha=0.8, edgecolor="#cbd5e1"),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved dashboard to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Field-year aligned dashboard")
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--field-slug", default="osm-1499460321")
    parser.add_argument("--farm", default="il-grower-illinois")
    parser.add_argument("--grower", default="il-grower")
    parser.add_argument("--output", default=None)
    parser.add_argument("--all-years", action="store_true")
    args = parser.parse_args()

    out_dir = _SCRIPT_DIR / "output"
    out_dir.mkdir(exist_ok=True)

    years = [2021, 2022, 2023, 2024, 2025] if args.all_years else [args.year]

    for year in years:
        print(f"\n--- Building dashboard for {args.field_slug} / {year} ---")
        aligned = load_aligned_field_year(
            grower=args.grower,
            farm=args.farm,
            field_slug=args.field_slug,
            year=year,
        )
        print(
            f"  Crop: {aligned.crop.name} ({aligned.crop.pct:.1f}%) | "
            f"Scenes: {aligned.summary['scene_count']} | "
            f"Weather complete: {aligned.quality.weather_complete} | "
            f"NDVI sufficient: {aligned.quality.ndvi_sufficient}"
        )

        if args.output and not args.all_years:
            out_path = Path(args.output)
        else:
            out_path = out_dir / f"{args.field_slug}_{year}_dashboard.png"

        plot_dashboard(aligned, out_path)

    if args.all_years:
        print(f"\nAll {len(years)} year dashboards saved to {out_dir}")


if __name__ == "__main__":
    main()
