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
import numpy as np
import pandas as pd

matplotlib.use("Agg")

# Add lib/ to path for align_field_year
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

from align_field_year import load_aligned_field_year, AlignedFieldYear, Event


# ---------------------------------------------------------------------------
# Scientific annotation dataclass
# ---------------------------------------------------------------------------

@dataclass
class SciAnnotation:
    doy: int
    title: str
    subtitle: str = ""
    doy_range: str = ""  # e.g. "DOY 189–210"


# ---------------------------------------------------------------------------
# Panel-specific scientific annotation builders (data-driven)
# ---------------------------------------------------------------------------

def _build_ndvi_phase_annotations(ndvi_df: pd.DataFrame) -> List[SciAnnotation]:
    """Derive phenological phases from actual NDVI curve."""
    annos: List[SciAnnotation] = []
    if ndvi_df.empty or len(ndvi_df) < 3:
        return annos

    df = ndvi_df.copy().sort_values("doy").reset_index(drop=True)
    peak_ndvi = float(df["mean_ndvi"].max())
    peak_idx = int(df["mean_ndvi"].idxmax())
    peak_doy = int(df.iloc[peak_idx]["doy"])

    # 1. Green-up Initiation: first scene with NDVI > 0.20 and DOY > 100
    greenup = df[(df["mean_ndvi"] > 0.20) & (df["doy"] > 100)]
    if not greenup.empty:
        idx = int(greenup.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Green-up Initiation", subtitle="NDVI rise begins"))

    # 2. Rapid Canopy Development: steepest sustained rise (≥2 consecutive positive slopes)
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

    # 3. Peak Canopy Greenness: around maximum NDVI
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

    # 4. Onset of Senescence: first drop > 0.10 from peak
    post_peak = df.iloc[peak_idx + 1 :].copy()
    senescence = post_peak[post_peak["mean_ndvi"] < (peak_ndvi - 0.10)]
    if not senescence.empty:
        idx = int(senescence.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Onset of Senescence", subtitle="Declining canopy greenness"))

    # 5. Late-Season Senescence: first scene below 50% of peak after peak
    late = post_peak[post_peak["mean_ndvi"] < (peak_ndvi * 0.50)]
    if not late.empty:
        idx = int(late.index[0])
        doy = int(df.iloc[idx]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Late-Season Senescence", subtitle="Post-peak vegetation decline"))

    return annos[:5]


def _build_precip_annotations(weather_df: pd.DataFrame, events: List[Event]) -> List[SciAnnotation]:
    """Format heavy rain events with scientific wording."""
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
    """Derive seasonal temperature phases from full growing season data."""
    annos: List[SciAnnotation] = []
    if weather_df.empty:
        return annos

    df = weather_df.copy().sort_values("doy").reset_index(drop=True)
    median_t = float(df["T2M"].median())

    # 1. Seasonal Warming: first sustained rise above median (7-day window)
    df["t7"] = df["T2M"].rolling(window=7, min_periods=1).mean()
    warming = df[(df["t7"] > median_t) & (df["doy"] > 60)]
    if not warming.empty:
        doy = int(warming.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Seasonal Warming", subtitle="Sustained temperature increase"))

    # 2. Warm Period: DOY of maximum 7-day rolling mean
    max_t7_idx = int(df["t7"].idxmax())
    warm_doy = int(df.iloc[max_t7_idx]["doy"])
    annos.append(SciAnnotation(doy=warm_doy, title="Warm Period", subtitle="Elevated seasonal temperatures"))

    # 3. Peak Seasonal Temperature: DOY of absolute max T2M_MAX
    max_idx = int(df["T2M_MAX"].idxmax())
    peak_doy = int(df.iloc[max_idx]["doy"])
    annos.append(SciAnnotation(doy=peak_doy, title="Peak Seasonal Temperature", subtitle="Maximum seasonal heat"))

    # 4. Cooling Trend: first sustained drop below median
    cooling = df[(df["t7"] < median_t) & (df["doy"] > warm_doy)]
    if not cooling.empty:
        doy = int(cooling.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Cooling Trend", subtitle="Declining temperatures"))

    # 5. Autumn Temperature Decline: last day with T2M_MAX < 15°C in late season
    late = df[(df["doy"] > 270) & (df["T2M_MAX"] < 15.0)]
    if not late.empty:
        doy = int(late.iloc[-1]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Autumn Temperature Decline", subtitle="Post-season cooling"))

    return annos[:5]


def _build_gdd_phase_annotations(weather_df: pd.DataFrame) -> List[SciAnnotation]:
    """Derive thermal accumulation phases from cumulative GDD."""
    annos: List[SciAnnotation] = []
    if weather_df.empty:
        return annos

    df = weather_df.copy().sort_values("doy").reset_index(drop=True)
    max_gdd = float(df["gdd_cum"].max())
    if max_gdd <= 0:
        return annos

    # 1. Thermal Accumulation Initiated: GDD > 200
    init = df[df["gdd_cum"] > 200]
    if not init.empty:
        doy = int(init.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Thermal Accumulation Initiated", subtitle="Early-season heat accumulation"))

    # 2. Accelerated Heat Accumulation: GDD > 50% of max
    half = df[df["gdd_cum"] > (max_gdd * 0.50)]
    if not half.empty:
        doy = int(half.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Accelerated Heat Accumulation", subtitle="Rapid GDD increase"))

    # 3. Continued GDD Accumulation: GDD > 75% of max
    three_quarter = df[df["gdd_cum"] > (max_gdd * 0.75)]
    if not three_quarter.empty:
        doy = int(three_quarter.iloc[0]["doy"])
        annos.append(SciAnnotation(doy=doy, title="Continued GDD Accumulation", subtitle="Sustained thermal accumulation"))

    # 4. Thermal Accumulation Plateau: daily GDD < 5 for ≥5 consecutive days
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
# Scientific annotation renderer (publication-quality)
# ---------------------------------------------------------------------------

def _wrap_annotation_text(anno: SciAnnotation) -> str:
    """Build multi-line annotation text with wrapping."""
    lines = [f"{anno.title}"]
    if anno.subtitle:
        lines.append(f"{anno.subtitle}")
    if anno.doy_range:
        lines.append(f"{anno.doy_range}")
    return "\n".join(lines)


def _scientific_annotate(ax, annotations: List[SciAnnotation], panel_color: str, max_count: int = 5):
    """Draw publication-quality scientific annotation boxes."""
    if not annotations:
        return

    annotations = annotations[:max_count]
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    placed_doys: List[int] = []

    for i, anno in enumerate(annotations):
        doy = anno.doy
        text = _wrap_annotation_text(anno)

        # Stagger y positions to avoid overlap
        base_offset = 0.06
        y_pos = y_max - (base_offset + i * 0.07) * y_range
        for p in placed_doys:
            if abs(p - doy) < 20:
                y_pos -= 0.05 * y_range
        placed_doys.append(doy)

        # Ensure we stay within plot bounds
        if y_pos < y_min + 0.1 * y_range:
            y_pos = y_min + 0.1 * y_range

        ax.annotate(
            text,
            xy=(doy, y_pos),
            xytext=(doy + 8, y_pos + 0.04 * y_range),
            fontsize=7.5,
            fontweight="normal",
            color="#1e293b",
            ha="left",
            va="bottom",
            bbox=dict(
                boxstyle="round,pad=0.3,rounding_size=0.2",
                facecolor="white",
                edgecolor=panel_color,
                linewidth=0.8,
                alpha=0.92,
            ),
            arrowprops=dict(
                arrowstyle="-",
                color=panel_color,
                lw=0.6,
                ls="--",
                connectionstyle="arc3,rad=0.1",
            ),
            zorder=10,
        )


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
# Dashboard plotter (PRESERVE ALL PLOTS, AXES, COLORS, LAYOUT EXACTLY)
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

        # SCIENTIFIC ANNOTATIONS: NDVI phases
        ndvi_annos = _build_ndvi_phase_annotations(ndf)
        _scientific_annotate(ax1, ndvi_annos, panel_color="#166534", max_count=5)
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

        # SCIENTIFIC ANNOTATIONS: Major rainfall events
        precip_annos = _build_precip_annotations(wdf, aligned.events_weather)
        _scientific_annotate(ax2, precip_annos, panel_color="#3b82f6", max_count=5)
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

        # SCIENTIFIC ANNOTATIONS: Seasonal temperature phases (no rainfall)
        temp_annos = _build_temp_phase_annotations(wdf)
        _scientific_annotate(ax3, temp_annos, panel_color="#f97316", max_count=5)
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

        # SCIENTIFIC ANNOTATIONS: GDD accumulation phases (no NDVI/rainfall refs)
        gdd_annos = _build_gdd_phase_annotations(wdf)
        _scientific_annotate(ax4, gdd_annos, panel_color="#15803d", max_count=5)
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
