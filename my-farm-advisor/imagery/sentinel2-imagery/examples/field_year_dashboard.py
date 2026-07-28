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

from align_field_year import load_aligned_field_year, AlignedFieldYear, Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_top_events(events: list[Event], n: int = 5) -> list[Event]:
    """Keep only the top N most significant events to avoid overcrowding."""
    if len(events) <= n:
        return events

    def _score(ev: Event) -> float:
        # Score by magnitude of the event's numeric value
        val = ev.value if ev.value is not None else 0.0
        # Boost linked events slightly so cross-panel correlations survive filtering
        boost = 10.0 if ev.event_type.startswith("linked_") else 0.0
        return abs(val) + boost

    scored = sorted(events, key=_score, reverse=True)
    return scored[:n]


def _annotate_events(ax, events, color_map=None, y_offset=0.03, n_max=5):
    events = _filter_top_events(events, n=n_max)
    if not events:
        return

    if color_map is None:
        color_map = {
            "heavy_rain": "#1e40af",
            "hot_day": "#dc2626",
            "cool_period": "#0891b2",
            "dry_spell": "#b45309",
            "ndvi_rapid_increase": "#16a34a",
            "ndvi_dip": "#ca8a04",
            "ndvi_peak": "#9333ea",
            "linked_ndvi_rapid_increase_heavy_rain": "#7c3aed",
            "linked_ndvi_rapid_increase_hot_day": "#7c3aed",
            "linked_ndvi_dip_heavy_rain": "#7c3aed",
            "linked_ndvi_dip_hot_day": "#7c3aed",
        }

    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    placed = []
    for ev in events:
        doy = ev.doy
        color = color_map.get(ev.event_type, "#374151")
        text = ev.description
        # Stagger positions to avoid overlap
        y_pos = y_max - y_offset * y_range
        for p in placed:
            if abs(p - doy) < 15:
                y_offset += 0.05
                y_pos = y_max - y_offset * y_range
                if y_offset > 0.35:
                    y_offset = 0.03  # reset to avoid running off plot
        placed.append(doy)
        ax.axvline(doy, color=color, linestyle="--", linewidth=0.8, alpha=0.5)
        ax.text(
            doy + 2,
            y_pos,
            text,
            color=color,
            fontsize=7,
            rotation=0,
            va="top",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.8, edgecolor="none"),
        )


def _doy_to_month(doy: int) -> str:
    """Approximate month label from DOY (non-leap year)."""
    try:
        d = pd.to_datetime(f"2022-{doy:03d}", format="%Y-%j")
        return d.strftime("%b")
    except Exception:
        return ""


def _month_ticks(start_doy: int, end_doy: int) -> tuple[list[int], list[str]]:
    """Generate DOY positions and month labels for the bottom x-axis."""
    ticks = []
    labels = []
    for doy in range(start_doy, end_doy + 1):
        d = pd.to_datetime(f"2022-{doy:03d}", format="%Y-%j")
        if d.day == 15:
            ticks.append(doy)
            labels.append(d.strftime("%b"))
    return ticks, labels


def _generate_caption(aligned: AlignedFieldYear) -> str:
    """Auto-generate 2-3 concise synthesis bullets from the data."""
    bullets = []
    ndf = aligned.ndvi_df
    wdf = aligned.weather_df

    if not ndf.empty and aligned.summary.get("ndvi_peak_doy"):
        peak_doy = aligned.summary["ndvi_peak_doy"]
        peak_ndvi = aligned.summary.get("ndvi_peak", 0)
        bullets.append(
            f"NDVI peaked at DOY {peak_doy} ({peak_ndvi:.2f}) — Panel 1"
        )
        # Find weather around peak
        if not wdf.empty:
            window = wdf[(wdf["doy"] >= peak_doy - 7) & (wdf["doy"] <= peak_doy + 7)]
            if not window.empty:
                precip = window["PRECTOTCORR"].sum()
                tmax = window["T2M_MAX"].max()
                bullets.append(
                    f"Week around peak: {precip:.0f} mm rain, {tmax:.1f}°C max — Panels 2–3"
                )
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
            bullets.append(
                f"Cumulative GDD at peak: {gdd_val:.0f} °C·day{stage and ' (' + stage + ')' or ''} — Panel 4"
            )

    return "\n".join(f"  • {b}" for b in bullets[:3])


def plot_dashboard(aligned: AlignedFieldYear, output_path: Path) -> None:
    fig = plt.figure(figsize=(14, 20))
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

    # Leave room at bottom for caption
    gs = fig.add_gridspec(
        4, 1, hspace=0.32, left=0.08, right=0.95, top=0.94, bottom=0.10
    )

    wdf = aligned.weather_df
    ndf = aligned.ndvi_df
    xlim = (aligned.season_start_doy, aligned.season_end_doy)

    # Major DOY grid positions
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

        # GDD overlay on twin axis
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
            # Combine legends
            lines1, labels1 = ax1.get_legend_handles_labels()
            lines2, labels2 = ax1_gdd.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)
        else:
            ax1.legend(loc="upper left", fontsize=8)

        _annotate_events(ax1, aligned.events_ndvi, n_max=5)
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
        _annotate_events(ax2, aligned.events_weather, n_max=5)
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
        _annotate_events(ax3, aligned.events_weather, n_max=5)
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
        _annotate_events(ax4, aligned.events_linked, n_max=5)
    else:
        ax4.text(0.5, 0.5, "No weather data", ha="center", va="center", transform=ax4.transAxes)
    ax4.set_title(
        "Panel 4: Cumulative Growing Degree Days (°C·day)",
        fontsize=12, fontweight="bold", loc="left", pad=8,
    )
    for d in major_doys:
        ax4.axvline(d, color="#e2e8f0", linewidth=0.5, zorder=1)
    ax4.grid(True, alpha=0.3)

    # Bottom x-axis: DOY + month names
    ax4.set_xticks(major_doys)
    ax4.set_xticklabels([str(d) for d in major_doys], fontsize=9)

    # Secondary x-axis with month names
    ax4_month = ax4.twiny()
    ax4_month.set_xlim(ax4.get_xlim())
    ax4_month.set_xticks(month_ticks)
    ax4_month.set_xticklabels(month_labels, fontsize=9, color="#64748b")
    ax4_month.tick_params(axis="x", labelcolor="#64748b")
    ax4_month.spines["top"].set_color("#cbd5e1")
    ax4_month.spines["top"].set_linewidth(0.5)

    # -----------------------------------------------------------------
    # Synthesis caption at bottom
    # -----------------------------------------------------------------
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
