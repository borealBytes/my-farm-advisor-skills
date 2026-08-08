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
from typing import List, Tuple

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.text import Text
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
# Colour palette
# ---------------------------------------------------------------------------
_FOREST_GREEN = "#4E9A72"
_LIGHT_GREEN_FILL = "#E8F5E9"
_DARK_ORANGE = "#E87722"
_LIGHT_ORANGE_FILL = "#FFF3E0"
_ROYAL_BLUE = "#5A8DEE"
_LIGHT_BLUE_FILL = "#E3F2FD"
_SOFT_ORANGE = "#F4A261"
_LIGHT_YELLOW_FILL = "#FFF8E1"
_DARK_GREEN = "#63A35C"


# ---------------------------------------------------------------------------
# Scientific annotation dataclass (with per-annotation colours)
# ---------------------------------------------------------------------------

@dataclass
class SciAnnotation:
    doy: int
    title: str
    subtitle: str = ""
    doy_range: str = ""
    border_color: str = ""
    fill_color: str = ""


# ---------------------------------------------------------------------------
# Exact text measurement via matplotlib renderer
# ---------------------------------------------------------------------------

def _measure_text(ax, text: str, size: float, weight: str = "normal") -> Tuple[float, float]:
    """Return (width, height) of a text string in data coordinates."""
    fig = ax.get_figure()
    renderer = fig.canvas.get_renderer()
    t = Text(0, 0, text, size=size, weight=weight, family="sans-serif")
    t.set_figure(fig)
    t.set_transform(ax.transData)
    bbox = t.get_window_extent(renderer=renderer)
    inv = ax.transData.inverted()
    pts = inv.transform([[bbox.xmin, bbox.ymin], [bbox.xmax, bbox.ymax]])
    width = abs(pts[1][0] - pts[0][0])
    height = abs(pts[1][1] - pts[0][1])
    return width, height


# ---------------------------------------------------------------------------
# Infographic-style annotation renderer
# ---------------------------------------------------------------------------

def _draw_infographic_annotation(
    ax,
    anno: SciAnnotation,
    box_left: float,
    box_top: float,
    target_x: float,
    target_y: float,
):
    border = anno.border_color or "#374151"
    fill = anno.fill_color or "#ffffff"

    # Measure each line exactly
    title_w, title_h = _measure_text(ax, anno.title, 10.5, "semibold")
    sub_w, sub_h = _measure_text(ax, anno.subtitle, 8.5, "normal")
    doy_w, doy_h = (0.0, 0.0)
    if anno.doy_range:
        doy_w, doy_h = _measure_text(ax, anno.doy_range, 8.5, "normal")

    content_w = max(title_w, sub_w, doy_w)
    content_h = title_h + sub_h + doy_h

    # Padding proportional to font size (in data coords)
    pad_x = content_w * 0.10 + _measure_text(ax, "M", 10.5)[0] * 0.3
    pad_y = title_h * 0.35

    box_width = content_w + pad_x * 2
    box_height = content_h + pad_y * 2

    box_bottom = box_top - box_height

    # Draw rounded rectangle
    rect = FancyBboxPatch(
        (box_left, box_bottom),
        box_width,
        box_height,
        boxstyle="round,pad=0.003,rounding_size=0.012",
        facecolor=fill,
        edgecolor=border,
        linewidth=1.0,
        alpha=0.92,
        zorder=15,
        clip_on=False,
        transform=ax.transData,
    )
    ax.add_patch(rect)

    # Text placement
    text_x = box_left + box_width / 2
    y_cursor = box_top - pad_y

    ax.text(
        text_x,
        y_cursor,
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
    y_cursor -= title_h * 1.25

    ax.text(
        text_x,
        y_cursor,
        anno.subtitle,
        size=8.5,
        color="#5F5F5F",
        ha="center",
        va="top",
        zorder=16,
        clip_on=False,
        family="sans-serif",
    )
    y_cursor -= sub_h * 1.25

    if anno.doy_range:
        ax.text(
            text_x,
            y_cursor,
            anno.doy_range,
            size=8.5,
            color="#5F5F5F",
            ha="center",
            va="top",
            zorder=16,
            clip_on=False,
            family="sans-serif",
        )

    # L-shaped leader
    box_mid_x = box_left + box_width / 2
    box_mid_y = box_bottom
    ax.plot(
        [box_mid_x, target_x, target_x],
        [box_mid_y, box_mid_y, target_y],
        color=border,
        linewidth=0.8,
        alpha=0.35,
        solid_capstyle="butt",
        zorder=14,
        clip_on=False,
    )


# ---------------------------------------------------------------------------
# Smart placement with greedy non-overlap and vertical stagger
# ---------------------------------------------------------------------------

def _place_annotations(
    ax,
    annotations: List[SciAnnotation],
    data_df: pd.DataFrame,
    value_col: str,
    max_count: int = 5,
):
    if not annotations:
        return

    annotations = annotations[:max_count]
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    x_min, x_max = ax.get_xlim()

    # Measure all boxes first
    measured = []
    for anno in annotations:
        title_w, title_h = _measure_text(ax, anno.title, 10.5, "semibold")
        sub_w, sub_h = _measure_text(ax, anno.subtitle, 8.5, "normal")
        doy_w, doy_h = (0.0, 0.0)
        if anno.doy_range:
            doy_w, doy_h = _measure_text(ax, anno.doy_range, 8.5, "normal")
        content_w = max(title_w, sub_w, doy_w)
        content_h = title_h + sub_h + doy_h
        pad_x = content_w * 0.10 + _measure_text(ax, "M", 10.5)[0] * 0.3
        pad_y = title_h * 0.35
        box_w = content_w + pad_x * 2
        box_h = content_h + pad_y * 2
        measured.append((anno, box_w, box_h, title_h, sub_h, doy_h))

    # Greedy placement: sort by DOY, place left-to-right with overlap resolution
    placed = []  # list of (left, right, top, bottom)

    for i, (anno, bw, bh, th, sh, dh) in enumerate(measured):
        # Target DOY data point
        target_x = float(anno.doy)
        rows = data_df[data_df["doy"] == anno.doy]
        if not rows.empty:
            target_y = float(rows.iloc[0][value_col])
        else:
            idx = (data_df["doy"] - anno.doy).abs().idxmin()
            target_y = float(data_df.loc[idx, value_col])

        # Default top: stagger vertically to avoid the "one line" look
        # Alternate between two top levels for visual variety
        if i % 2 == 0:
            base_top = y_max - 0.04 * y_range
        else:
            base_top = y_max - 0.09 * y_range

        # Ensure box bottom stays above data and axis clutter
        min_bottom = y_min + y_range * 0.08
        if base_top - bh < min_bottom:
            base_top = min_bottom + bh + y_range * 0.02

        # Preferred x: centred on DOY
        preferred_left = target_x - bw / 2

        # Clamp to axis bounds
        left = max(x_min + (x_max - x_min) * 0.012, preferred_left)
        if left + bw > x_max - (x_max - x_min) * 0.012:
            left = x_max - (x_max - x_min) * 0.012 - bw

        right = left + bw
        top = base_top
        bottom = top - bh

        # Resolve horizontal overlaps by shifting right
        min_gap = (x_max - x_min) * 0.015
        for (pl, pr, pt, pb) in placed:
            if left < pr + min_gap and right > pl - min_gap:
                # Overlap detected — shift right
                if pr + min_gap + bw <= x_max - (x_max - x_min) * 0.012:
                    left = pr + min_gap
                    right = left + bw
                else:
                    # Can't shift right; try shifting left
                    if pl - min_gap - bw >= x_min + (x_max - x_min) * 0.012:
                        left = pl - min_gap - bw
                        right = left + bw
                    else:
                        # Still overlapping — nudge upward
                        top = pt + bh + y_range * 0.02
                        bottom = top - bh
                        # Re-check vertical bounds
                        if bottom < min_bottom:
                            top = min_bottom + bh + y_range * 0.02
                            bottom = min_bottom

        placed.append((left, right, top, bottom))

        # Adjust leader target so it's visible but not buried in data
        # For NDVI/precip: leader should point to data point directly
        # For GDD/temp: same
        _draw_infographic_annotation(ax, anno, left, top, target_x, target_y)


# ---------------------------------------------------------------------------
# Panel-specific annotation builders
# ---------------------------------------------------------------------------

def _build_ndvi_phase_annotations(ndvi_df: pd.DataFrame) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    if ndvi_df.empty or len(ndvi_df) < 3:
        return annos

    df = ndvi_df.copy().sort_values("doy").reset_index(drop=True)
    peak_ndvi = float(df["mean_ndvi"].max())
    peak_idx = int(df["mean_ndvi"].idxmax())
    peak_doy = int(df.iloc[peak_idx]["doy"])

    # 1. Early Vegetative (green)
    greenup = df[(df["mean_ndvi"] > 0.20) & (df["doy"] > 100)]
    if not greenup.empty:
        idx = int(greenup.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(
            SciAnnotation(
                doy=doy, title="Early Vegetative", subtitle="NDVI rise begins",
                doy_range=f"DOY {doy}",
                border_color=_FOREST_GREEN, fill_color=_LIGHT_GREEN_FILL,
            )
        )

    # 2. Rapid Canopy Development (green)
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
        start_ndvi = float(df[df["doy"] == rapid_start]["mean_ndvi"].iloc[0]) if not df[df["doy"] == rapid_start].empty else 0
        end_ndvi = float(df[df["doy"] == rapid_end]["mean_ndvi"].iloc[0]) if not df[df["doy"] == rapid_end].empty else 0
        annos.append(
            SciAnnotation(
                doy=rapid_start,
                title="Rapid Canopy Development",
                subtitle=f"NDVI +{start_ndvi:.2f} to +{end_ndvi:.2f}",
                doy_range=f"DOY {rapid_start}–{rapid_end}",
                border_color=_FOREST_GREEN, fill_color=_LIGHT_GREEN_FILL,
            )
        )

    # 3. Reproductive/Peak (green)
    if len(df) > 1:
        start_doy = int(df.iloc[max(0, peak_idx - 1)]["doy"])
        end_doy = int(df.iloc[min(len(df) - 1, peak_idx + 1)]["doy"])
        start_ndvi = float(df.iloc[max(0, peak_idx - 1)]["mean_ndvi"])
        annos.append(
            SciAnnotation(
                doy=peak_doy,
                title="Reproductive/Peak",
                subtitle=f"NDVI +{start_ndvi:.2f} to +{peak_ndvi:.2f}",
                doy_range=f"Peak NDVI = {peak_ndvi:.2f}",
                border_color=_FOREST_GREEN, fill_color=_LIGHT_GREEN_FILL,
            )
        )

    # 4. Early Senescence (orange)
    post_peak = df.iloc[peak_idx + 1 :].copy()
    senescence = post_peak[post_peak["mean_ndvi"] < (peak_ndvi - 0.10)]
    if not senescence.empty:
        idx = int(senescence.index[0])
        doy = int(df.iloc[idx]["doy"])
        end_ndvi = float(df.iloc[idx]["mean_ndvi"])
        annos.append(
            SciAnnotation(
                doy=doy,
                title="Early Senescence",
                subtitle=f"NDVI {end_ndvi:.2f} to {peak_ndvi:.2f}",
                doy_range=f"DOY {doy}",
                border_color=_DARK_ORANGE, fill_color=_LIGHT_ORANGE_FILL,
            )
        )

    # 5. Late Season (orange)
    late = post_peak[post_peak["mean_ndvi"] < (peak_ndvi * 0.50)]
    if not late.empty:
        idx = int(late.index[0])
        doy = int(df.iloc[idx]["doy"])
        end_ndvi = float(df.iloc[idx]["mean_ndvi"])
        annos.append(
            SciAnnotation(
                doy=doy,
                title="Late Season",
                subtitle=f"NDVI {end_ndvi:.2f} to {peak_ndvi:.2f}",
                doy_range=f"DOY {doy}",
                border_color=_DARK_ORANGE, fill_color=_LIGHT_ORANGE_FILL,
            )
        )

    return annos[:5]


def _build_precip_annotations(weather_df: pd.DataFrame, events: List[Event]) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    heavy_rains = [e for e in events if e.event_type == "heavy_rain"]
    for ev in heavy_rains[:4]:
        val = ev.value if ev.value is not None else 0.0
        annos.append(
            SciAnnotation(
                doy=ev.doy,
                title="Heavy Rain Event",
                subtitle=f"{val:.1f} mm",
                doy_range=f"DOY {ev.doy}",
                border_color=_ROYAL_BLUE, fill_color=_LIGHT_BLUE_FILL,
            )
        )
    return annos


def _build_temp_rain_annotations(weather_df: pd.DataFrame, events: List[Event]) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    heavy_rains = [e for e in events if e.event_type == "heavy_rain"]
    for ev in heavy_rains[:4]:
        val = ev.value if ev.value is not None else 0.0
        annos.append(
            SciAnnotation(
                doy=ev.doy,
                title="Heavy Rain Event",
                subtitle=f"{val:.1f} mm",
                doy_range=f"DOY {ev.doy}",
                border_color=_SOFT_ORANGE, fill_color=_LIGHT_YELLOW_FILL,
            )
        )
    return annos


def _build_gdd_phase_annotations(weather_df: pd.DataFrame) -> List[SciAnnotation]:
    annos: List[SciAnnotation] = []
    if weather_df.empty:
        return annos

    df = weather_df.copy().sort_values("doy").reset_index(drop=True)
    max_gdd = float(df["gdd_cum"].max())
    if max_gdd <= 0:
        return annos

    # 1. Accumulation Onset (green)
    init = df[df["gdd_cum"] > 200]
    if not init.empty:
        doy = int(init.iloc[0]["doy"])
        annos.append(
            SciAnnotation(
                doy=doy,
                title="Accumulation Onset",
                subtitle="Slow early-season",
                doy_range="GDD accumulation",
                border_color=_DARK_GREEN, fill_color=_LIGHT_GREEN_FILL,
            )
        )

    # 2. Accelerated Accumulation (green)
    half = df[df["gdd_cum"] > (max_gdd * 0.50)]
    if not half.empty:
        doy = int(half.iloc[0]["doy"])
        annos.append(
            SciAnnotation(
                doy=doy,
                title="Accelerated Accumulation",
                subtitle="Rapid increase in GDD",
                doy_range=f"DOY {doy}",
                border_color=_DARK_GREEN, fill_color=_LIGHT_GREEN_FILL,
            )
        )

    # 3. Continued Accumulation (orange)
    three_q = df[df["gdd_cum"] > (max_gdd * 0.75)]
    if not three_q.empty:
        doy = int(three_q.iloc[0]["doy"])
        annos.append(
            SciAnnotation(
                doy=doy,
                title="Continued Accumulation",
                subtitle="GDD accumulation continues",
                doy_range=f"DOY {doy}",
                border_color=_DARK_ORANGE, fill_color=_LIGHT_ORANGE_FILL,
            )
        )

    # 4. Accumulation Plateau (orange)
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
        annos.append(
            SciAnnotation(
                doy=plateau_doy,
                title="Accumulation Plateau",
                subtitle="GDD total approaches seasonal maximum",
                doy_range=f"DOY {plateau_doy}",
                border_color=_DARK_ORANGE, fill_color=_LIGHT_ORANGE_FILL,
            )
        )

    return annos[:5]


# ---------------------------------------------------------------------------
# Structured key-observations box
# ---------------------------------------------------------------------------

def _generate_structured_caption(aligned: AlignedFieldYear) -> str:
    lines = []
    ndf = aligned.ndvi_df
    wdf = aligned.weather_df

    if not ndf.empty and aligned.summary.get("ndvi_peak_doy"):
        peak_doy = aligned.summary["ndvi_peak_doy"]
        peak_ndvi = aligned.summary.get("ndvi_peak", 0)
        lines.append(f"NDVI peak: DOY {peak_doy} (NDVI = {peak_ndvi:.2f})")

    if not wdf.empty:
        df = wdf.copy().sort_values("doy").reset_index(drop=True)
        df["t7"] = df["T2M"].rolling(window=7, min_periods=1).mean()
        threshold = float(df["t7"].quantile(0.90))
        warm = df[df["t7"] >= threshold]
        if not warm.empty:
            warm_start = int(warm.iloc[0]["doy"])
            warm_end = int(warm.iloc[-1]["doy"])
            tmin = float(warm["T2M"].min())
            tmax = float(warm["T2M"].max())
            lines.append(f"Warmest Period: DOY {warm_start}–{warm_end} (Mean Temp = {tmin:.0f}–{tmax:.0f}°C)")

        heavy = [e for e in aligned.events_weather if e.event_type == "heavy_rain"]
        if heavy:
            doys = sorted([e.doy for e in heavy])
            compact = []
            start = doys[0]
            prev = doys[0]
            for d in doys[1:]:
                if d == prev + 1:
                    prev = d
                else:
                    compact.append(f"{start}–{prev}" if prev > start else f"{start}")
                    start = d
                    prev = d
            compact.append(f"{start}–{prev}" if prev > start else f"{start}")
            lines.append(f"Major rain events: DOY {', '.join(compact)}")

        max_gdd = float(df["gdd_cum"].max())
        gdd_peak_row = df[df["gdd_cum"] == max_gdd]
        if not gdd_peak_row.empty:
            gdd_peak_doy = int(gdd_peak_row.iloc[0]["doy"])
            lines.append(f"Peak Cumulative GDD: {max_gdd:.0f} °C·day at DOY {gdd_peak_doy}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Month / DOY helpers
# ---------------------------------------------------------------------------

def _month_ticks(start_doy: int, end_doy: int) -> Tuple[List[int], List[str]]:
    ticks = []
    labels = []
    for doy in range(start_doy, end_doy + 1):
        d = pd.to_datetime(f"2022-{doy:03d}", format="%Y-%j")
        if d.day == 15:
            ticks.append(doy)
            labels.append(d.strftime("%b"))
    return ticks, labels


# ---------------------------------------------------------------------------
# Dashboard plotter
# ---------------------------------------------------------------------------

def plot_dashboard(aligned: AlignedFieldYear, output_path: Path) -> None:
    fig = plt.figure(figsize=(14, 20))
    fig.patch.set_facecolor("#fafaf9")

    loc = f"{aligned.summary.get('lat', 0):.4f}°N, {abs(aligned.summary.get('lon', 0)):.4f}°W"
    fig.suptitle(
        f"Field–Year Dashboard  ·  {aligned.field_id}  ·  {aligned.year}  ·  {aligned.crop.name} "
        f"({aligned.crop.pct:.1f}%)  ·  {loc}",
        fontsize=16,
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
            label="Mean NDVI (±SD)",
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
                color=_DARK_ORANGE,
                linestyle="--",
                linewidth=1.2,
                alpha=0.85,
                label="Cumulative GDD (base 10°C)",
                zorder=2,
            )
            ax1_gdd.set_ylabel("Cumulative GDD (°C·day)", fontsize=10, color=_DARK_ORANGE)
            ax1_gdd.tick_params(axis="y", labelcolor=_DARK_ORANGE)
            ax1_gdd.set_ylim(0, wdf["gdd_cum"].max() * 1.3)
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax1_gdd.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
        else:
            ax1.legend(loc="upper left", fontsize=8)

        ndvi_annos = _build_ndvi_phase_annotations(ndf)
        _place_annotations(ax1, ndvi_annos, ndf, "mean_ndvi", max_count=5)
    else:
        ax1.text(0.5, 0.5, "No NDVI data", ha="center", va="center", transform=ax1.transAxes)
    ax1.set_title(
        "Panel 1: NDVI (unitless) with Cumulative Growing Degree Days (°C·day)",
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
            label="Daily precipitation",
            zorder=3,
        )
        ax2_twin = ax2.twinx()
        ax2_twin.plot(
            wdf["doy"],
            wdf["precip_cum"],
            color="#1e3a8a",
            linewidth=1.5,
            label="Cumulative precipitation",
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
        _place_annotations(ax2, precip_annos, wdf, "PRECTOTCORR", max_count=5)
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
            label="Daily Min–Max Range",
            zorder=2,
        )
        ax3.plot(wdf["doy"], wdf["T2M"], color="#1e293b", linewidth=0.8, label="Daily Mean Temperature", zorder=3)
        ax3.plot(wdf["doy"], wdf["T2M_MAX"], color="#dc2626", linewidth=0.4, alpha=0.6, zorder=2)
        ax3.plot(wdf["doy"], wdf["T2M_MIN"], color="#2563eb", linewidth=0.4, alpha=0.6, zorder=2)
        ax3.axhline(0, color="#94a3b8", linestyle="--", linewidth=0.8, zorder=1)
        ax3.set_ylabel("Temperature (°C)", fontsize=11)
        ax3.set_ylim(
            wdf["T2M_MIN"].min() - 5,
            wdf["T2M_MAX"].max() + 5,
        )
        ax3.legend(loc="upper left", fontsize=8)

        temp_annos = _build_temp_rain_annotations(wdf, aligned.events_weather)
        _place_annotations(ax3, temp_annos, wdf, "T2M", max_count=5)
    else:
        ax3.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax3.transAxes)
    ax3.set_title(
        "Panel 3: Temperature and Extremes (°C)",
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
        ax4.set_ylabel("Cumulative GDD (°C·day)", fontsize=11)
        ax4.set_xlabel("Day of Year", fontsize=11)
        ax4.legend(loc="upper left", fontsize=8)

        gdd_annos = _build_gdd_phase_annotations(wdf)
        _place_annotations(ax4, gdd_annos, wdf, "gdd_cum", max_count=5)
    else:
        ax4.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax4.transAxes)
    ax4.set_title(
        "Panel 4: Cumulative Growing Degree Days (°C·day, base 10°C)",
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

    caption = _generate_structured_caption(aligned)
    if caption:
        fig.text(
            0.08,
            0.04,
            caption,
            fontsize=9,
            color="#334155",
            ha="left",
            va="bottom",
            linespacing=1.4,
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

    # Default output to data-pipeline/dashboard for Assignment 3
    out_dir = Path("/home/coder/my-farm-advisor-runtime/data-pipeline/dashboard")
    out_dir.mkdir(parents=True, exist_ok=True)

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
