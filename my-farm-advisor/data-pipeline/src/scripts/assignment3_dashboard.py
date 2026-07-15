#!/usr/bin/env python3
# pyright: reportAttributeAccessIssue=false
"""
Assignment 3 - Aligned mini-dashboard for single field-year.

Generates a 4-panel dashboard (NDVI, precipitation, temperature, cumulative GDD)
with concise event annotations from the Step 5 alignment outputs.

Input:  Step 5 aligned CSV + events JSON.
Output: Single PNG dashboard under field derived/reports/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from lib.paths import ensure_parent, field_reports_dir  # noqa: E402

GROWER = "northern-illinois-grower"
FARM = "northern-illinois-grower-illinois"
FIELD = "osm-1499474531"
YEAR = 2025
CROP = "Soybeans"
GDD_BASE = 10.0

# -- Soybean GDD milestones to annotate (name, threshold) --
GDD_MILESTONES = [
    ("VE emergence", 130),
    ("R1 flowering", 500),
    ("R5 seed-fill", 900),
    ("R7 maturity", 1400),
]

# -- Season window for display --
DISPLAY_START = f"{YEAR}-03-01"
DISPLAY_END = f"{YEAR}-11-10"

# -- Colour palette --
C_NDVI = "#228B22"
C_PRECIP_BAR = "#4682B4"
C_PRECIP_LINE = "#003f5c"
C_TMAX = "#d62728"
C_TMIN = "#1f77b4"
C_TAVG = "#333333"
C_GDD = "#2ca02c"
C_ANNOT = "#8B0000"
C_FILL_TEMP = "#ffcc80"


def load_inputs(reports_dir: Path) -> tuple[pd.DataFrame, dict]:
    aligned_path = reports_dir / "assignment3_aligned_data.csv"
    events_path = reports_dir / "assignment3_events.json"

    if not aligned_path.exists():
        raise FileNotFoundError(f"Missing aligned data: {aligned_path}")
    if not events_path.exists():
        raise FileNotFoundError(f"Missing events: {events_path}")

    df = pd.read_csv(aligned_path, parse_dates=["date"])
    df = df[(df["date"] >= DISPLAY_START) & (df["date"] <= DISPLAY_END)].copy()

    with open(events_path) as f:
        events_data = json.load(f)

    return df, events_data


def pick_key_events(events_data: dict, df: pd.DataFrame) -> list[dict]:
    events = events_data.get("events", [])
    annotations = []

    # -- 1. Largest rainfall --
    heavy = [e for e in events if e["event_type"] == "heavy_rainfall"]
    if heavy:
        heavy.sort(key=lambda e: e["value"], reverse=True)
        top = heavy[0]
        annotations.append(
            {
                "panel": "precip",
                "date": top["date"],
                "value": top["value"],
                "text": f"{top['value']:.0f} mm",
                "kind": "max_rain",
            }
        )

    # -- 2. Hottest day --
    hot = [e for e in events if e["event_type"] == "hot_day"]
    if hot:
        hot.sort(key=lambda e: e["value"], reverse=True)
        top = hot[0]
        annotations.append(
            {
                "panel": "temp",
                "date": top["date"],
                "value": top["value"],
                "text": f"{top['value']:.1f}\u00b0C",
                "kind": "max_hot",
            }
        )

    # -- 3. Rapid NDVI increase (largest delta) --
    ndvi_inc = [e for e in events if e["event_type"] == "rapid_ndvi_increase"]
    if ndvi_inc:
        ndvi_inc.sort(key=lambda e: e["value"], reverse=True)
        top = ndvi_inc[0]
        annotations.append(
            {
                "panel": "ndvi",
                "date": top["date_end"],
                "value": top["value"],
                "text": f"+{top['value']:.2f} NDVI",
                "kind": "ndvi_rise",
            }
        )

    # -- 4. NDVI peak --
    for e in events:
        if e["event_type"] == "ndvi_peak":
            annotations.append(
                {
                    "panel": "ndvi",
                    "date": e["date"],
                    "value": e["value"],
                    "text": f"peak {e['value']:.2f}",
                    "kind": "ndvi_peak",
                }
            )

    # -- 5. NDVI decline onset --
    for e in events:
        if e["event_type"] == "ndvi_decline":
            annotations.append(
                {
                    "panel": "ndvi",
                    "date": e["date_start"],
                    "value": e["value"],
                    "text": "senescence",
                    "kind": "ndvi_decline",
                }
            )

    # -- 6. GDD milestones --
    for label, thresh in GDD_MILESTONES:
        reached = df[df["GDD_cumsum"] >= thresh]
        if len(reached) > 0:
            stage_date = reached.iloc[0]["date"]
            if pd.Timestamp(DISPLAY_START) <= stage_date <= pd.Timestamp(DISPLAY_END):
                annotations.append(
                    {
                        "panel": "gdd",
                        "date": str(stage_date.date()),
                        "value": thresh,
                        "text": label,
                        "kind": "gdd_stage",
                    }
                )

    return annotations


def build_dashboard(df: pd.DataFrame, annotations: list[dict], output_path: Path):
    ndvi_mask = df["ndvi"].notna()
    ndvi_dates = df.loc[ndvi_mask, "date"]
    ndvi_vals = df.loc[ndvi_mask, "ndvi"]

    fig = plt.figure(figsize=(16, 13))
    fig.suptitle(
        f"{FIELD}  |  {YEAR}  |  {CROP}",
        fontsize=16,
        fontweight="bold",
        y=0.985,
    )

    gs = fig.add_gridspec(4, 1, hspace=0.30, left=0.08, right=0.93, top=0.94, bottom=0.05)

    # ---- shared x-axis formatter ----
    month_locator = mdates.MonthLocator(interval=1)
    month_fmt = mdates.DateFormatter("%b")

    # ============================================================
    # PANEL 1: NDVI
    # ============================================================
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(ndvi_dates, ndvi_vals, color=C_NDVI, linewidth=2, marker="o",
             markersize=7, markerfacecolor="white", markeredgecolor=C_NDVI,
             markeredgewidth=1.5, zorder=5)
    ax1.set_ylabel("NDVI", fontsize=11)
    ax1.set_title("Sentinel-2 NDVI (field mean)", fontsize=12, fontweight="bold", loc="left")
    ax1.set_ylim(0, 0.85)
    ax1.yaxis.set_major_locator(ticker.MultipleLocator(0.2))
    ax1.grid(True, alpha=0.3, axis="y")
    ax1.tick_params(axis="x", labelbottom=False)

    for ann in annotations:
        if ann["panel"] == "ndvi":
            dt = pd.Timestamp(ann["date"])
            val = df.loc[df["date"] == dt, "ndvi"]
            if len(val) > 0 and not val.isna().iloc[0]:
                y = val.iloc[0]
            else:
                y = ndvi_vals.max() * 0.6
            if ann["kind"] == "ndvi_peak":
                y_pos = y + 0.06
            elif ann["kind"] == "ndvi_decline":
                y_pos = y - 0.10
            else:
                y_pos = y + 0.08
            ax1.annotate(
                ann["text"],
                xy=(dt, y),
                xytext=(dt, y_pos),
                fontsize=8, fontweight="bold", color=C_ANNOT,
                ha="center", va="bottom",
                arrowprops=dict(arrowstyle="->", color=C_ANNOT, lw=0.8),
            )

    # ============================================================
    # PANEL 2: Precipitation (bars) + cumulative precipitation
    # ============================================================
    ax2 = fig.add_subplot(gs[1])
    bars = ax2.bar(df["date"], df["precip_mm"], width=0.8, color=C_PRECIP_BAR,
                   alpha=0.7, edgecolor="none", zorder=2)
    ax2.set_ylabel("Precipitation (mm/day)", fontsize=11, color=C_PRECIP_BAR)
    ax2.set_title("Daily Precipitation", fontsize=12, fontweight="bold", loc="left")
    ax2.grid(True, alpha=0.3, axis="y")
    ax2.tick_params(axis="x", labelbottom=False)
    ax2.tick_params(axis="y", colors=C_PRECIP_BAR)

    # Cumulative precip line on twin axis
    ax2b = ax2.twinx()
    df["precip_cum"] = df["precip_mm"].cumsum()
    ax2b.plot(df["date"], df["precip_cum"], color=C_PRECIP_LINE, linewidth=1.5, alpha=0.7)
    ax2b.set_ylabel("Cumulative (mm)", fontsize=10, color=C_PRECIP_LINE)
    ax2b.tick_params(axis="y", colors=C_PRECIP_LINE)

    for ann in annotations:
        if ann["panel"] == "precip":
            dt = pd.Timestamp(ann["date"])
            row = df[df["date"] == dt]
            if len(row) > 0:
                ax2.annotate(
                    ann["text"],
                    xy=(dt, row.iloc[0]["precip_mm"]),
                    xytext=(dt + pd.Timedelta(days=5), row.iloc[0]["precip_mm"] + 10),
                    fontsize=8, fontweight="bold", color=C_ANNOT,
                    ha="left", va="bottom",
                    arrowprops=dict(arrowstyle="->", color=C_ANNOT, lw=0.8),
                )

    # ============================================================
    # PANEL 3: Temperature
    # ============================================================
    ax3 = fig.add_subplot(gs[2])
    ax3.fill_between(df["date"], df["temp_min_c"], df["temp_max_c"],
                     alpha=0.25, color=C_FILL_TEMP, label="Min\u2013Max range")
    ax3.plot(df["date"], df["temp_max_c"], color=C_TMAX, linewidth=0.7, alpha=0.6,
             label="Tmax")
    ax3.plot(df["date"], df["temp_min_c"], color=C_TMIN, linewidth=0.7, alpha=0.6,
             label="Tmin")
    ax3.plot(df["date"], df["temp_avg_c"], color=C_TAVG, linewidth=1.2,
             label="Tavg")
    ax3.axhline(y=GDD_BASE, color="green", linestyle="--", linewidth=0.8, alpha=0.5)
    ax3.text(df["date"].iloc[5], GDD_BASE + 1.0, f"{GDD_BASE}\u00b0C GDD base",
             fontsize=7, color="green", alpha=0.7)
    ax3.set_ylabel("Temperature (\u00b0C)", fontsize=11)
    ax3.set_title("Daily Temperature", fontsize=12, fontweight="bold", loc="left")
    ax3.legend(fontsize=8, loc="upper left", ncol=3, framealpha=0.5)
    ax3.grid(True, alpha=0.3, axis="y")
    ax3.tick_params(axis="x", labelbottom=False)

    for ann in annotations:
        if ann["panel"] == "temp":
            dt = pd.Timestamp(ann["date"])
            row = df[df["date"] == dt]
            if len(row) > 0:
                ax3.annotate(
                    ann["text"],
                    xy=(dt, row.iloc[0]["temp_max_c"]),
                    xytext=(dt + pd.Timedelta(days=3), row.iloc[0]["temp_max_c"] + 2),
                    fontsize=8, fontweight="bold", color=C_ANNOT,
                    ha="left", va="bottom",
                    arrowprops=dict(arrowstyle="->", color=C_ANNOT, lw=0.8),
                )

    # ============================================================
    # PANEL 4: Cumulative GDD
    # ============================================================
    ax4 = fig.add_subplot(gs[3])
    ax4.plot(df["date"], df["GDD_cumsum"], color=C_GDD, linewidth=2, zorder=2)
    ax4.fill_between(df["date"], 0, df["GDD_cumsum"], alpha=0.08, color=C_GDD)
    ax4.set_ylabel(f"GDD (\u00b0C-days, base {GDD_BASE}\u00b0C)", fontsize=11)
    ax4.set_title(f"Cumulative Growing Degree Days (base {GDD_BASE}\u00b0C)",
                  fontsize=12, fontweight="bold", loc="left")
    ax4.grid(True, alpha=0.3, axis="y")
    ax4.set_xlabel("2025", fontsize=11)
    ax4.xaxis.set_major_locator(month_locator)
    ax4.xaxis.set_major_formatter(month_fmt)

    # GDD milestone annotations
    milestone_positions = []
    for ann in annotations:
        if ann["panel"] == "gdd":
            dt = pd.Timestamp(ann["date"])
            row = df[df["date"] == dt]
            if len(row) > 0:
                gdd_val = row.iloc[0]["GDD_cumsum"]
            else:
                gdd_val = ann["value"]
            milestone_positions.append((dt, gdd_val, ann["text"]))

    milestone_positions.sort(key=lambda x: x[1])
    last_y = 0
    for dt, gdd_val, label in milestone_positions:
        offset = 180
        if gdd_val - last_y < 250:
            offset = -180
            if dt > pd.Timestamp(f"{YEAR}-10-01"):
                offset = -280
        ax4.annotate(
            label,
            xy=(dt, gdd_val),
            xytext=(dt + pd.Timedelta(days=1), gdd_val + offset),
            fontsize=8, fontweight="bold", color=C_ANNOT,
            ha="left", va="center",
            arrowprops=dict(arrowstyle="->", color=C_ANNOT, lw=0.8),
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7, edgecolor=C_ANNOT),
        )
        last_y = gdd_val

    # ---- Apply shared x-limits ----
    for ax in [ax1, ax2, ax3, ax4]:
        ax.set_xlim(pd.Timestamp(DISPLAY_START), pd.Timestamp(DISPLAY_END))
        ax.xaxis.set_major_locator(month_locator)
        ax.xaxis.set_major_formatter(month_fmt)
        for label in ax.get_xticklabels():
            label.set_rotation(0)
            label.set_fontsize(9)

    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    reports_dir = field_reports_dir(GROWER, FARM, FIELD)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"Assignment 3 Dashboard: {FIELD} / {YEAR} / {CROP}")
    print("=" * 60)

    print("\n[1] Loading Step 5 aligned data and events...")
    df, events_data = load_inputs(reports_dir)
    print(f"    Rows: {len(df)} ({df['date'].min().date()} to {df['date'].max().date()})")
    print(f"    NDVI observations: {df['ndvi'].notna().sum()}")

    print("\n[2] Selecting key annotation events...")
    annotations = pick_key_events(events_data, df)
    for ann in annotations:
        print(f"    [{ann['panel']:>6s}] {ann['date']:>12s}  {ann['text']}")

    print("\n[3] Building dashboard...")
    output_path = reports_dir / "assignment3_dashboard_2025.png"
    build_dashboard(df, annotations, output_path)
    print(f"    Saved: {output_path}")

    # Validation summary
    ndvi_count = df["ndvi"].notna().sum()
    print("\n" + "=" * 60)
    print("DASHBOARD VALIDATION")
    print("=" * 60)
    print(f"  File:          {output_path}")
    print(f"  Panels:        NDVI, Precipitation, Temperature, Cumulative GDD")
    print(f"  Date range:    {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  NDVI points:   {ndvi_count} (original Sentinel dates only)")
    print(f"  Annotations:   {len(annotations)}")
    print(f"  Resolution:    200 dpi, 16x13 inches")
    print()
    print(f"  Annotations included:")
    for ann in annotations:
        print(f"    [{ann['panel']:>6s}] {ann['date']:>12s}  {ann['text']}")

    print("\n✓ Dashboard complete.")


if __name__ == "__main__":
    main()
