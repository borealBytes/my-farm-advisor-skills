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
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

# Add lib/ to path for align_field_year
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

from align_field_year import load_aligned_field_year, AlignedFieldYear


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _annotate_events(ax, events, color_map=None, y_offset=0.03):
    if color_map is None:
        color_map = {
            "heavy_rain": "#1e40af",
            "hot_day": "#dc2626",
            "cool_period": "#0891b2",
            "dry_spell": "#b45309",
            "ndvi_rapid_increase": "#16a34a",
            "ndvi_dip": "#ca8a04",
            "ndvi_peak": "#9333ea",
        }
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    placed = []
    for ev in events:
        doy = ev.doy
        color = color_map.get(ev.event_type, "#374151")
        text = ev.description
        # Simple collision avoidance: stagger y positions
        y_pos = y_max - y_offset * y_range
        for p in placed:
            if abs(p - doy) < 12:
                y_offset += 0.04
                y_pos = y_max - y_offset * y_range
        placed.append(doy)
        ax.axvline(doy, color=color, linestyle="--", linewidth=1.0, alpha=0.6)
        ax.text(
            doy + 1,
            y_pos,
            text,
            color=color,
            fontsize=6.5,
            rotation=0,
            va="top",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", alpha=0.75, edgecolor="none"),
        )


def plot_dashboard(aligned: AlignedFieldYear, output_path: Path) -> None:
    fig = plt.figure(figsize=(14, 18))
    fig.patch.set_facecolor("#fafaf9")

    # Title
    loc = f"{aligned.summary.get('lat', 0):.4f}°N, {abs(aligned.summary.get('lon', 0)):.4f}°W"
    fig.suptitle(
        f"Field-Year Dashboard  ·  {aligned.field_id}  ·  {aligned.year}  ·  {aligned.crop.name} "
        f"({aligned.crop.pct:.1f}%)  ·  {loc}",
        fontsize=14,
        fontweight="bold",
        y=0.98,
        color="#1e293b",
    )

    gs = fig.add_gridspec(4, 1, hspace=0.35, left=0.08, right=0.95, top=0.94, bottom=0.04)

    wdf = aligned.weather_df
    ndf = aligned.ndvi_df

    # Common x-limits
    xlim = (aligned.season_start_doy, aligned.season_end_doy)

    # -----------------------------------------------------------------
    # Panel 1: NDVI time series
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
        )
        ax1.set_ylabel("NDVI", fontsize=11)
        ax1.set_ylim(-0.05, 1.05)
        ax1.set_xlim(*xlim)
        ax1.grid(True, alpha=0.3)
        _annotate_events(ax1, aligned.events_ndvi)
    else:
        ax1.text(0.5, 0.5, "No NDVI data", ha="center", va="center", transform=ax1.transAxes)
    ax1.set_title("NDVI Time Series", fontsize=12, fontweight="bold", loc="left", pad=8)
    ax1.set_xticklabels([])

    # -----------------------------------------------------------------
    # Panel 2: Temperature
    # -----------------------------------------------------------------
    ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
    if not wdf.empty:
        ax2.fill_between(
            wdf["doy"],
            wdf["T2M_MIN"],
            wdf["T2M_MAX"],
            alpha=0.25,
            color="#f97316",
            label="Daily range",
        )
        ax2.plot(wdf["doy"], wdf["T2M"], color="#1e293b", linewidth=0.8, label="Mean temp")
        ax2.plot(wdf["doy"], wdf["T2M_MAX"], color="#dc2626", linewidth=0.4, alpha=0.6)
        ax2.plot(wdf["doy"], wdf["T2M_MIN"], color="#2563eb", linewidth=0.4, alpha=0.6)
        ax2.axhline(0, color="#94a3b8", linestyle="--", linewidth=0.8)
        ax2.set_ylabel("Temperature (°C)", fontsize=11)
        ax2.set_ylim(
            wdf["T2M_MIN"].min() - 5,
            wdf["T2M_MAX"].max() + 5,
        )
        ax2.set_xlim(*xlim)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper right", fontsize=8)
        _annotate_events(ax2, aligned.events_weather)
    else:
        ax2.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax2.transAxes)
    ax2.set_title("Temperature & Extremes", fontsize=12, fontweight="bold", loc="left", pad=8)
    ax2.set_xticklabels([])

    # -----------------------------------------------------------------
    # Panel 3: Precipitation
    # -----------------------------------------------------------------
    ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)
    if not wdf.empty:
        ax3.bar(
            wdf["doy"],
            wdf["PRECTOTCORR"],
            color="#3b82f6",
            alpha=0.7,
            width=1.0,
            label="Daily precip",
        )
        ax3_twin = ax3.twinx()
        ax3_twin.plot(
            wdf["doy"],
            wdf["precip_cum"],
            color="#1e3a8a",
            linewidth=1.5,
            label="Cumulative",
        )
        ax3_twin.set_ylabel("Cumulative (mm)", fontsize=10, color="#1e3a8a")
        ax3.set_ylabel("Daily precip (mm)", fontsize=11)
        ax3.set_ylim(0, wdf["PRECTOTCORR"].max() * 1.5 + 5)
        ax3_twin.set_ylim(0, wdf["precip_cum"].max() * 1.2)
        ax3.set_xlim(*xlim)
        ax3.grid(True, alpha=0.3, axis="y")
        ax3.legend(loc="upper left", fontsize=8)
        ax3_twin.legend(loc="upper right", fontsize=8)
        _annotate_events(ax3, aligned.events_weather)
    else:
        ax3.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax3.transAxes)
    ax3.set_title("Precipitation", fontsize=12, fontweight="bold", loc="left", pad=8)
    ax3.set_xticklabels([])

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
        )
        # Corn growth-stage reference bands (only if crop is Corn)
        if aligned.crop.name.lower() == "corn":
            stages = [
                (500, "V6", "#86efac"),
                (800, "V12", "#bef264"),
                (1200, "VT", "#fde047"),
                (1600, "R2", "#fdba74"),
            ]
            for gdd_target, stage_name, color in stages:
                ax4.axhline(gdd_target, color=color, linestyle="--", linewidth=1.0, alpha=0.7)
                ax4.text(
                    xlim[1] - 2,
                    gdd_target + 30,
                    stage_name,
                    color="#374151",
                    fontsize=8,
                    ha="right",
                    va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.4, edgecolor="none"),
                )
        ax4.set_ylabel("GDD (°C·day)", fontsize=11)
        ax4.set_xlabel("Day of Year", fontsize=11)
        ax4.set_xlim(*xlim)
        ax4.grid(True, alpha=0.3)
        ax4.legend(loc="upper left", fontsize=8)
        _annotate_events(ax4, aligned.events_linked)
    else:
        ax4.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax4.transAxes)
    ax4.set_title("Cumulative Growing Degree Days", fontsize=12, fontweight="bold", loc="left", pad=8)

    # Shared x-axis tick formatting
    for ax in [ax1, ax2, ax3]:
        ax.tick_params(labelbottom=False)
    ax4.set_xticks(range(aligned.season_start_doy, aligned.season_end_doy + 1, 30))

    # Save
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
