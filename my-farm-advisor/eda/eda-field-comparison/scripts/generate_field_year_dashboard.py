#!/usr/bin/env python3
"""Generate a 4-panel field-year dashboard: NDVI, Precipitation, Temperature, Cumulative GDD."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.gridspec import GridSpec

GDD_BASE_CORN = 10.0
GDD_BASE_SOYBEAN = 10.0


def _resolve_data_root() -> Path:
    root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if root:
        return Path(root).expanduser() / "data-pipeline"
    return Path(__file__).resolve().parents[5]


def load_weather(
    data_root: Path, grower: str, farm: str, field_id: str, year: int
) -> pd.DataFrame:
    path = (
        data_root
        / "growers"
        / grower
        / "farms"
        / farm
        / "fields"
        / field_id
        / "weather"
        / "daily_weather.csv"
    )
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy().reset_index(drop=True)
    return df


def load_ndvi_scenes(
    data_root: Path, grower: str, farm: str, field_id: str, year: int
) -> pd.DataFrame:
    manifest_path = (
        data_root
        / "growers"
        / grower
        / "farms"
        / farm
        / "fields"
        / field_id
        / "satellite"
        / "sentinel"
        / "manifest.json"
    )
    if not manifest_path.exists():
        print(f"  Warning: no sentinel manifest at {manifest_path}", file=sys.stderr)
        return pd.DataFrame()

    manifest = json.loads(manifest_path.read_text())
    records = []
    for year_entry in manifest.get("years", []):
        if year_entry.get("year") != year:
            continue
        for scene in year_entry.get("scenes", []):
            scene_date = scene.get("scene_date")
            ndvi_tif = scene.get("ndvi_tif")
            if not scene_date or not ndvi_tif:
                continue
            ndvi_path = data_root / ndvi_tif
            if ndvi_path.exists():
                try:
                    with rasterio.open(ndvi_path) as src:
                        arr = src.read(1).astype("float32")
                        arr[arr == src.nodata] = np.nan
                        valid = arr[np.isfinite(arr)]
                        if len(valid) > 0:
                            records.append(
                                {
                                    "date": pd.to_datetime(scene_date),
                                    "ndvi_mean": float(np.nanmean(valid)),
                                    "ndvi_median": float(np.nanmedian(valid)),
                                    "ndvi_max": float(np.nanmax(valid)),
                                    "ndvi_min": float(np.nanmin(valid)),
                                    "ndvi_std": float(np.nanstd(valid)),
                                }
                            )
                except Exception as e:
                    print(f"  Warning: failed to read {ndvi_path}: {e}", file=sys.stderr)
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def compute_gdd(weather: pd.DataFrame, base_temp: float = 10.0) -> pd.DataFrame:
    df = weather.copy()
    df["gdd_daily"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2.0 - base_temp).clip(lower=0)
    df["gdd_cumulative"] = df["gdd_daily"].cumsum()
    return df


def _group_consecutive(
    dates: pd.Series, max_gap_days: int = 1
) -> list[pd.Series]:
    if dates.empty:
        return []
    sorted_dates = dates.sort_values().reset_index(drop=True)
    groups = []
    current = [sorted_dates.iloc[0]]
    for i in range(1, len(sorted_dates)):
        if (sorted_dates.iloc[i] - sorted_dates.iloc[i - 1]).days <= max_gap_days:
            current.append(sorted_dates.iloc[i])
        else:
            groups.append(pd.Series(current))
            current = [sorted_dates.iloc[i]]
    groups.append(pd.Series(current))
    return groups


def detect_events(weather: pd.DataFrame, ndvi: pd.DataFrame) -> list[dict]:
    events = []

    gs = weather[weather["date"].dt.month.isin([4, 5, 6, 7, 8, 9, 10])]

    heavy_rain = gs[gs["PRECTOTCORR"] > 25]
    for _, row in heavy_rain.iterrows():
        events.append(
            {
                "type": "heavy_rain",
                "date": row["date"],
                "panel": "precip",
                "label": f"{row['PRECTOTCORR']:.0f} mm",
            }
        )

    hot_days = gs[gs["T2M_MAX"] > 35]
    hot_groups = _group_consecutive(hot_days["date"])
    for grp in hot_groups:
        peak_temp = gs.loc[gs["date"].isin(grp), "T2M_MAX"].max()
        label = f"{peak_temp:.0f}°C"
        if len(grp) > 1:
            label = f"{grp.iloc[0].strftime('%b %d')}–{grp.iloc[-1].strftime('%b %d')} Heat"
        events.append(
            {
                "type": "heat_wave",
                "date": grp.iloc[len(grp) // 2],
                "panel": "temp",
                "label": label,
            }
        )

    cool = gs[gs["T2M_MIN"] < 5]
    cool_groups = _group_consecutive(cool["date"], max_gap_days=2)
    for grp in cool_groups:
        if len(grp) >= 3:
            events.append(
                {
                    "type": "cool_period",
                    "date": grp.iloc[len(grp) // 2],
                    "panel": "temp",
                    "label": f"{grp.iloc[0].strftime('%b %d')}–{grp.iloc[-1].strftime('%b %d')} Cool",
                }
            )

    if len(ndvi) > 1:
        ndvi_sorted = ndvi.sort_values("date").reset_index(drop=True)
        ndvi_sorted["ndvi_change"] = ndvi_sorted["ndvi_mean"].diff()
        rapid_up = ndvi_sorted[ndvi_sorted["ndvi_change"] > 0.15]
        for _, row in rapid_up.iterrows():
            prev_mean = ndvi_sorted.loc[
                ndvi_sorted["date"] < row["date"], "ndvi_mean"
            ].iloc[-1] if not ndvi_sorted[ndvi_sorted["date"] < row["date"]].empty else 0
            events.append(
                {
                    "type": "ndvi_rapid_increase",
                    "date": row["date"],
                    "panel": "ndvi",
                    "label": f"+{row['ndvi_change']:.2f} ({prev_mean:.2f}→{row['ndvi_mean']:.2f})",
                }
            )
        rapid_down = ndvi_sorted[ndvi_sorted["ndvi_change"] < -0.10]
        for _, row in rapid_down.iterrows():
            events.append(
                {
                    "type": "ndvi_dip",
                    "date": row["date"],
                    "panel": "ndvi",
                    "label": f"{row['ndvi_change']:.2f} ({row['ndvi_mean']:.2f})",
                }
            )
        peak = ndvi_sorted.loc[ndvi_sorted["ndvi_mean"].idxmax()]
        events.append(
            {
                "type": "ndvi_peak",
                "date": peak["date"],
                "panel": "ndvi",
                "label": f"Peak NDVI {peak['ndvi_mean']:.2f}",
            }
        )

        first_green = ndvi_sorted[ndvi_sorted["ndvi_mean"] > 0.3]
        if not first_green.empty:
            events.append(
                {
                    "type": "canopy_greenup",
                    "date": first_green.iloc[0]["date"],
                    "panel": "ndvi",
                    "label": f"Canopy >0.3",
                }
            )

    return events


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 4-panel field-year dashboard image"
    )
    parser.add_argument("--field-id", default="osm-1157043055")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--grower", default="ia-northern-grower")
    parser.add_argument("--farm", default="ia-northern-grower-farm")
    parser.add_argument("--crop", default=None)
    parser.add_argument("--gdd-base", type=float, default=10.0)
    parser.add_argument("--output", default=None)
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    data_root = Path(args.data_root) if args.data_root else _resolve_data_root()

    print(f"Loading data for {args.field_id}, {args.year}...")

    weather = load_weather(data_root, args.grower, args.farm, args.field_id, args.year)
    ndvi = load_ndvi_scenes(data_root, args.grower, args.farm, args.field_id, args.year)
    weather = compute_gdd(weather, args.gdd_base)
    events = detect_events(weather, ndvi)

    crop_label = args.crop or ""
    print(f"  Weather days: {len(weather)}")
    print(f"  NDVI scenes: {len(ndvi)}")
    print(f"  Events detected: {len(events)}")
    for e in events:
        print(f"    [{e['panel']}] {e['date'].strftime('%Y-%m-%d')}: {e['label']}")

    gs_start = pd.Timestamp(f"{args.year}-04-01")
    gs_end = pd.Timestamp(f"{args.year}-11-01")
    gs_weather = weather[weather["date"].between(gs_start, gs_end)].copy()

    fig = plt.figure(figsize=(14, 12), constrained_layout=False)
    gs = GridSpec(4, 1, figure=fig, height_ratios=[1, 1, 1, 1], hspace=0.08)

    colors = {
        "ndvi_line": "#1b7837",
        "ndvi_fill": "#1b7837",
        "precip_bar": "#2c7bb6",
        "precip_cumul": "#d7191c",
        "temp_max": "#e74c3c",
        "temp_min": "#3498db",
        "temp_mean": "#2c3e50",
        "gdd_fill": "#f1a340",
        "gdd_line": "#d6604d",
    }

    # --- Panel 1: NDVI ---
    ax_ndvi = fig.add_subplot(gs[0])
    if not ndvi.empty:
        ax_ndvi.plot(
            ndvi["date"],
            ndvi["ndvi_mean"],
            marker="s",
            linestyle="-",
            color=colors["ndvi_line"],
            linewidth=2,
            markersize=5,
            label="Mean NDVI",
            zorder=3,
        )
        ax_ndvi.fill_between(
            ndvi["date"],
            ndvi["ndvi_min"],
            ndvi["ndvi_max"],
            alpha=0.2,
            color=colors["ndvi_fill"],
            label="Min–Max",
        )
        for e in events:
            if e["panel"] != "ndvi":
                continue
            row = ndvi[ndvi["date"] == e["date"]]
            if row.empty:
                continue
            y = row.iloc[0]["ndvi_mean"]
            if e["type"] == "ndvi_peak":
                ax_ndvi.axvline(x=e["date"], color=colors["ndvi_line"], linestyle="--", alpha=0.5, linewidth=1)
                ax_ndvi.annotate(
                    e["label"],
                    xy=(e["date"], y),
                    xytext=(10, 10),
                    textcoords="offset points",
                    fontsize=7,
                    color=colors["ndvi_line"],
                    fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=colors["ndvi_line"], lw=0.8),
                )
            elif "dip" in e["type"]:
                ax_ndvi.annotate(
                    e["label"],
                    xy=(e["date"], y),
                    xytext=(0, -14),
                    textcoords="offset points",
                    fontsize=6,
                    ha="center",
                    color="#c0392b",
                    fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color="#c0392b", lw=0.8),
                )
            elif "increase" in e["type"]:
                ax_ndvi.annotate(
                    e["label"],
                    xy=(e["date"], y),
                    xytext=(0, 10),
                    textcoords="offset points",
                    fontsize=6,
                    ha="center",
                    color=colors["ndvi_line"],
                    arrowprops=dict(arrowstyle="->", color=colors["ndvi_line"], lw=0.8),
                )
            elif "greenup" in e["type"]:
                ax_ndvi.annotate(
                    e["label"],
                    xy=(e["date"], y),
                    xytext=(0, 12),
                    textcoords="offset points",
                    fontsize=6,
                    ha="center",
                    color="#27ae60",
                    style="italic",
                    arrowprops=dict(arrowstyle="->", color="#27ae60", lw=0.8),
                )
    ax_ndvi.set_ylabel("NDVI")
    ax_ndvi.set_ylim(-0.1, 1.05)
    ax_ndvi.set_xlim(gs_start, gs_end)
    ax_ndvi.grid(True, alpha=0.3)
    ax_ndvi.legend(loc="upper left", fontsize=7, ncol=2)
    ax_ndvi.tick_params(labelbottom=False)
    ax_ndvi.set_title(
        f"NDVI Time Series — {args.field_id} {args.year}",
        fontsize=12,
        fontweight="bold",
        loc="left",
    )

    # --- Panel 2: Precipitation ---
    ax_precip = fig.add_subplot(gs[1], sharex=ax_ndvi)
    ax_precip.bar(
        gs_weather["date"],
        gs_weather["PRECTOTCORR"],
        color=colors["precip_bar"],
        alpha=0.7,
        width=2,
        label="Daily (mm)",
    )
    ax_precip_twin = ax_precip.twinx()
    cumsum = gs_weather["PRECTOTCORR"].cumsum()
    ax_precip_twin.plot(
        gs_weather["date"],
        cumsum,
        color=colors["precip_cumul"],
        linewidth=2,
        label="Cumulative",
    )
    ax_precip_twin.set_ylabel("Cumulative (mm)", color=colors["precip_cumul"])
    ax_precip_twin.tick_params(axis="y", labelcolor=colors["precip_cumul"])
    total_precip = cumsum.iloc[-1] if not cumsum.empty else 0

    for e in events:
        if e["panel"] != "precip":
            continue
        ax_precip.annotate(
            e["label"],
            xy=(e["date"], 0),
            xytext=(0, 10),
            textcoords="offset points",
            fontsize=6,
            ha="center",
            color=colors["precip_cumul"],
            fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=colors["precip_cumul"], lw=0.8),
        )
    ax_precip.set_ylabel("Precipitation (mm)")
    ax_precip.set_xlim(gs_start, gs_end)
    ax_precip.grid(True, alpha=0.3)
    ax_precip.legend(loc="upper left", fontsize=7)
    ax_precip.tick_params(labelbottom=False)
    ax_precip.set_title(
        f"Precipitation — Season total {total_precip:.0f} mm",
        fontsize=12,
        fontweight="bold",
        loc="left",
    )

    # --- Panel 3: Temperature ---
    ax_temp = fig.add_subplot(gs[2], sharex=ax_ndvi)
    ax_temp.plot(
        gs_weather["date"],
        gs_weather["T2M_MAX"],
        color=colors["temp_max"],
        alpha=0.5,
        linewidth=0.8,
        label="Max",
    )
    ax_temp.plot(
        gs_weather["date"],
        gs_weather["T2M_MIN"],
        color=colors["temp_min"],
        alpha=0.5,
        linewidth=0.8,
        label="Min",
    )
    ax_temp.plot(
        gs_weather["date"],
        gs_weather["T2M"],
        color=colors["temp_mean"],
        linewidth=1.5,
        label="Mean",
    )
    ax_temp.fill_between(
        gs_weather["date"],
        gs_weather["T2M_MIN"],
        gs_weather["T2M_MAX"],
        alpha=0.08,
        color="#7f8c8d",
    )

    for e in events:
        if e["panel"] != "temp":
            continue
        if "heat" in e["type"]:
            y_annot = gs_weather.loc[gs_weather["date"] == e["date"], "T2M_MAX"]
            if not y_annot.empty:
                ax_temp.annotate(
                    e["label"],
                    xy=(e["date"], y_annot.iloc[0]),
                    xytext=(0, 12),
                    textcoords="offset points",
                    fontsize=6,
                    ha="center",
                    color=colors["temp_max"],
                    fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=colors["temp_max"], lw=0.8),
                )
        elif "cool" in e["type"]:
            ax_temp.annotate(
                e["label"],
                xy=(e["date"], 2),
                fontsize=6,
                ha="center",
                color=colors["temp_min"],
                style="italic",
                arrowprops=dict(arrowstyle="->", color=colors["temp_min"], lw=0.8),
            )
    ax_temp.set_ylabel("Temperature (°C)")
    ax_temp.set_xlim(gs_start, gs_end)
    ax_temp.grid(True, alpha=0.3)
    ax_temp.legend(loc="upper left", fontsize=7, ncol=3)
    ax_temp.tick_params(labelbottom=False)
    ax_temp.set_title("Temperature — Daily Max, Min, Mean", fontsize=12, fontweight="bold", loc="left")

    # --- Panel 4: Cumulative GDD ---
    ax_gdd = fig.add_subplot(gs[3], sharex=ax_ndvi)
    ax_gdd.fill_between(
        gs_weather["date"],
        gs_weather["gdd_cumulative"],
        color=colors["gdd_fill"],
        alpha=0.4,
        step="mid",
    )
    ax_gdd.plot(
        gs_weather["date"],
        gs_weather["gdd_cumulative"],
        color=colors["gdd_line"],
        linewidth=2,
    )
    total_gdd = gs_weather["gdd_cumulative"].iloc[-1] if not gs_weather.empty else 0
    ax_gdd.set_ylabel("Cumulative GDD (°C·day)")
    ax_gdd.set_xlabel("Date")
    ax_gdd.set_xlim(gs_start, gs_end)
    ax_gdd.grid(True, alpha=0.3)
    ax_gdd.set_title(
        f"Cumulative GDD (base {args.gdd_base:.0f}°C) — Total {total_gdd:.0f} °C·day",
        fontsize=12,
        fontweight="bold",
        loc="left",
    )
    ax_gdd.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax_gdd.xaxis.set_major_locator(mdates.MonthLocator())

    caption_parts = []
    for e in events:
        if e["panel"] == "precip":
            caption_parts.append(f"Rain: {e['label']} ({e['date'].strftime('%b %d')})")
        elif e["panel"] == "temp" and "heat" in e["type"]:
            caption_parts.append(f"Heat: {e['label']}")
        elif e["panel"] == "temp" and "cool" in e["type"]:
            caption_parts.append(f"Cool: {e['label']}")
        elif e["panel"] == "ndvi" and "peak" in e["type"]:
            caption_parts.append(f"NDVI peak {e['date'].strftime('%b %d')}")
        elif e["panel"] == "ndvi" and "increase" in e["type"]:
            caption_parts.append(f"Canopy fill {e['date'].strftime('%b %d')}")
        elif e["panel"] == "ndvi" and "dip" in e["type"]:
            caption_parts.append(f"Senescence {e['date'].strftime('%b %d')}")
    if caption_parts:
        fig.text(
            0.5,
            0.004,
            "  |  ".join(caption_parts[:6]),
            ha="center",
            fontsize=6.5,
            color="#555",
            style="italic",
        )

    fig.suptitle(
        f"{args.field_id}  ·  {args.year}{'  ·  ' + crop_label if crop_label else ''}",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )

    fig.subplots_adjust(left=0.08, right=0.88, bottom=0.06, top=0.93, hspace=0.08)
    output = args.output or str(
        data_root
        / "eda"
        / "field-comparison"
        / "plots"
        / f"field_year_dashboard_{args.field_id}_{args.year}.png"
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
