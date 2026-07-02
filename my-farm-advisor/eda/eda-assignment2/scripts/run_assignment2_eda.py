#!/usr/bin/env python3
"""Assignment 2 field-level EDA — boundaries, CDL, weather across 3 growers.

Produces 11 outputs under ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda-assignment2/:
  1. field_area_comparison.png       — grouped bar chart
  2. field_latitude_extents.png      — vertical lat range chart
  3. estimated_corn_acres.png         — corn acreage line graph
  4. estimated_soybean_acres.png      — soybean acreage line graph
  5. field_plant_harvest_timeline.png — crop-type Gantt timeline
  6. precip_offseason_cumulative.png — rolling cumulative precip
  7. temperature_growing_season.png  — daily farm-average temp
  8. field_area_boxplot.png          — five-number area summary
  9. crop_area_comparison.png        — corn/soy vs total area
  10. growing_degree_days.png        — cumulative GDD by farm & crop
  11. all_farms_map.html              — combined geospatial map

Usage:
    python scripts/run_assignment2_eda.py [--grower-slug ne-grower]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

DATA_ROOT: Path = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", ""))
if not DATA_ROOT.is_absolute():
    print("ERROR: DATA_PIPELINE_DATA_ROOT must be an absolute path")
    sys.exit(1)

PIPELINE_ROOT = DATA_ROOT / "data-pipeline"
GROWERS_ROOT = PIPELINE_ROOT / "growers"
OUTPUT_DIR = PIPELINE_ROOT / "eda-assignment2"

FARMS = {
    "il-grower": {"slug": "il-grower-illinois", "prefix": "il_grower_illinois"},
    "ia-grower": {"slug": "ia-grower-iowa", "prefix": "ia_grower_iowa"},
    "ne-grower": {"slug": "ne-grower-nebraska", "prefix": "ne_grower_nebraska"},
}

# ---------------------------------------------------------------------------
# Crop calendars
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference"))
from crop_calendars import lookup as _lookup_calendar  # noqa: E402

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _boundary_path(grower: str, farm: str) -> Path:
    return GROWERS_ROOT / grower / "farms" / farm / "boundary" / "field_boundaries.geojson"


def _weather_path(grower: str, farm: str) -> Path:
    prefix = FARMS[grower]["prefix"]
    return (
        GROWERS_ROOT / grower / "farms" / farm / "derived" / "tables"
        / f"{prefix}_weather_2021_2025.csv"
    )


def _cdl_composition_path(grower: str, farm: str) -> Path:
    prefix = FARMS[grower]["prefix"]
    return (
        GROWERS_ROOT / grower / "farms" / farm / "derived" / "tables"
        / f"{prefix}_cdl_2021_2025_full_composition.csv"
    )


def load_boundaries(growers: list[str]) -> pd.DataFrame:
    rows = []
    for grower in growers:
        farm = FARMS[grower]["slug"]
        gdf = gpd.read_file(_boundary_path(grower, farm))
        for _, feat in gdf.iterrows():
            geom = feat.geometry
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            rows.append({
                "grower": grower,
                "farm": farm,
                "field_id": str(feat["field_id"]),
                "area_acres": float(feat["area_acres"]),
                "northmost_lat": bounds[3],
                "southmost_lat": bounds[1],
            })
    return pd.DataFrame(rows)


def load_weather(growers: list[str]) -> pd.DataFrame:
    frames = []
    for grower in growers:
        farm = FARMS[grower]["slug"]
        df = pd.read_csv(_weather_path(grower, farm), parse_dates=["date"])
        df["grower"] = grower
        df["farm"] = farm
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def load_cdl(growers: list[str]) -> pd.DataFrame:
    frames = []
    for grower in growers:
        farm = FARMS[grower]["slug"]
        df = pd.read_csv(_cdl_composition_path(grower, farm))
        df["grower"] = grower
        df["farm"] = farm
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Deliverable 1 — Field area bar chart
# ---------------------------------------------------------------------------


def render_area_chart(boundaries: pd.DataFrame) -> None:
    farms_ordered = sorted(boundaries["farm"].unique())
    grower_colors = {
        "il-grower": "#2E7D32",
        "ia-grower": "#1565C0",
        "ne-grower": "#E65100",
    }

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
    fig.suptitle("Field Area by Farm and Grower", fontsize=14, fontweight="bold")

    for ax, farm in zip(axes, farms_ordered):
        farm_data = boundaries[boundaries["farm"] == farm].copy()
        farm_data = farm_data.sort_values("area_acres", ascending=False)
        grower = farm_data["grower"].iloc[0]
        bars = ax.bar(
            range(len(farm_data)),
            farm_data["area_acres"],
            color=grower_colors.get(grower, "#757575"),
            edgecolor="white",
            linewidth=0.5,
        )
        ax.set_title(farm.replace("-", " ").title(), fontsize=11)
        ax.set_xticks(range(len(farm_data)))
        ax.set_xticklabels(
            [fid.replace("osm-", "")[-6:] for fid in farm_data["field_id"]],
            rotation=45,
            ha="right",
            fontsize=7,
        )
        for bar, acres in zip(bars, farm_data["area_acres"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 5,
                f"{acres:.0f}",
                ha="center",
                va="bottom",
                fontsize=6,
            )

        avg_area = farm_data["area_acres"].mean()
        med_area = farm_data["area_acres"].median()
        ax.axhline(avg_area, color="#333", linestyle="--", linewidth=1, alpha=0.7)
        ax.axhline(med_area, color="#666", linestyle=":", linewidth=1, alpha=0.7)
        x_right = len(farm_data) - 0.5
        ax.text(x_right, avg_area, f" avg {avg_area:.0f}", fontsize=7, color="#333", va="center", ha="left")
        ax.text(x_right, med_area, f" med {med_area:.0f}", fontsize=7, color="#666", va="center", ha="left")

    axes[0].set_ylabel("Area (acres)")
    fig.text(0.5, 0.01, "Field ID (last 6 chars of OSM ID)", ha="center", fontsize=9)
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    output = OUTPUT_DIR / "field_area_comparison.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 2 — Latitude extents chart
# ---------------------------------------------------------------------------


def render_latitude_chart(boundaries: pd.DataFrame) -> None:
    grower_colors = {
        "il-grower": "#2E7D32",
        "ia-grower": "#1565C0",
        "ne-grower": "#E65100",
    }

    fig, ax = plt.subplots(figsize=(18, 5.5))
    fig.suptitle("Field Latitude Extents by Grower", fontsize=14, fontweight="bold")

    df = boundaries.copy()
    # Group by grower, sort fields north-to-south within each group
    df = df.sort_values(["grower", "northmost_lat"], ascending=[True, False])
    df = df.reset_index(drop=True)

    tick_labels: list[str] = []
    tick_positions: list[int] = []
    grower_boundaries: list[tuple[float, str]] = []  # x-pos, label

    for idx, (_, row) in enumerate(df.iterrows()):
        grower = row["grower"]
        color = grower_colors.get(grower, "#757575")
        short_id = str(row["field_id"]).replace("osm-", "")[-6:]

        ax.vlines(
            idx,
            row["southmost_lat"],
            row["northmost_lat"],
            colors=color,
            linewidth=2.5,
            alpha=0.85,
        )
        ax.scatter(
            [idx, idx],
            [row["southmost_lat"], row["northmost_lat"]],
            color=color,
            s=25,
            zorder=3,
        )
        tick_labels.append(short_id)
        tick_positions.append(idx)

    # Draw grower-group separators and labels
    prev_grower = None
    group_starts: dict[str, int] = {}
    group_ends: dict[str, int] = {}
    for idx, (_, row) in enumerate(df.iterrows()):
        g = row["grower"]
        if g != prev_grower:
            group_starts[g] = idx
            if prev_grower is not None:
                group_ends[prev_grower] = idx - 1
                ax.axvline(idx - 0.5, color="#bbb", linestyle="--", linewidth=0.8)
        prev_grower = g
    if prev_grower is not None:
        group_ends[prev_grower] = len(df) - 1

    # Group labels
    for grower, start in group_starts.items():
        end = group_ends.get(grower, len(df) - 1)
        mid = (start + end) / 2
        ax.text(
            mid,
            ax.get_ylim()[0] - 0.15,
            grower.replace("-", " ").title(),
            ha="center",
            fontsize=10,
            fontweight="bold",
            color=grower_colors.get(grower, "#757575"),
        )
        # Average latitude for this grower's fields
        grower_df = df.iloc[start:end + 1]
        avg_north = grower_df["northmost_lat"].mean()
        avg_south = grower_df["southmost_lat"].mean()
        avg_mid = (avg_north + avg_south) / 2
        ax.plot(
            [start - 0.3, end + 0.3],
            [avg_mid, avg_mid],
            linestyle="--",
            linewidth=1.2,
            color=grower_colors.get(grower, "#757575"),
            alpha=0.7,
        )
        ax.text(
            end + 0.5,
            avg_mid,
            f"avg {avg_mid:.2f}\u00b0",
            fontsize=7,
            color=grower_colors.get(grower, "#757575"),
            va="center",
            ha="left",
        )

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=90, ha="center", fontsize=7)
    ax.set_ylabel("Latitude (decimal degrees)")
    ax.set_xlabel("Field (last 6 chars of OSM ID)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    output = OUTPUT_DIR / "field_latitude_extents.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# CDL composition helper — builds in-memory dominant-crop DataFrame
# ---------------------------------------------------------------------------


def _build_cdl_composition(cdl: pd.DataFrame, boundaries: pd.DataFrame) -> pd.DataFrame:
    area_map = boundaries.set_index(["grower", "farm", "field_id"])["area_acres"]
    cdl = cdl.copy()
    cdl["key"] = cdl.apply(lambda r: (r["grower"], r["farm"], r["field_id"]), axis=1)
    cdl["field_area_acres"] = cdl["key"].map(area_map)
    cdl["estimated_planted_acres"] = (
        cdl["pct"] / 100.0 * cdl["field_area_acres"]
    ).round(1)
    dominant = cdl.loc[cdl.groupby(["grower", "farm", "field_id", "year"])["pct"].idxmax()].copy()
    dominant = dominant.sort_values(["grower", "farm", "field_id", "year"])
    return dominant[["grower", "farm", "field_id", "year", "crop_name", "pct", "estimated_planted_acres"]].rename(
        columns={"crop_name": "dominant_crop", "pct": "crop_pct"}
    )


# ---------------------------------------------------------------------------
# Deliverable 3/4 — Corn & Soybean acreage line graphs
# ---------------------------------------------------------------------------


def render_yield_line(cdl_composition: pd.DataFrame, crop: str, output_name: str) -> None:
    grower_colors = {
        "il-grower": "#2E7D32",
        "ia-grower": "#1565C0",
        "ne-grower": "#E65100",
    }
    crop_data = cdl_composition[cdl_composition["dominant_crop"] == crop].copy()
    if crop_data.empty:
        print(f"  skip {output_name} — no {crop} data")
        return

    avg = crop_data.groupby(["grower", "farm", "year"])["estimated_planted_acres"].mean().reset_index()
    avg["year"] = avg["year"].astype(int)

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(f"{crop} — Mean Estimated Planted Acres by Farm", fontsize=13, fontweight="bold")

    for grower in sorted(avg["grower"].unique()):
        gdata = avg[avg["grower"] == grower].sort_values("year")
        color = grower_colors.get(grower, "#757575")
        ax.plot(
            gdata["year"],
            gdata["estimated_planted_acres"],
            marker="o",
            linewidth=2,
            markersize=8,
            color=color,
            alpha=0.85,
            label=grower.replace("-", " ").title(),
        )
        for _, row in gdata.iterrows():
            ax.text(
                row["year"],
                row["estimated_planted_acres"] + 15,
                f"{row['estimated_planted_acres']:.0f}",
                fontsize=7.5,
                ha="center",
                color=color,
            )

    ax.set_xlabel("Year")
    ax.set_ylabel("Estimated Planted Acres")
    ax.set_xticks(sorted(avg["year"].unique()))
    ax.set_xticklabels(sorted(avg["year"].unique()))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    output = OUTPUT_DIR / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Plant/harvest helper — builds in-memory estimates DataFrame
# ---------------------------------------------------------------------------


def _build_plant_harvest(cdl: pd.DataFrame, boundaries: pd.DataFrame) -> pd.DataFrame:
    area_map = boundaries.set_index(["grower", "farm", "field_id"])["area_acres"]
    cdl = cdl.copy()
    cdl["key"] = cdl.apply(lambda r: (r["grower"], r["farm"], r["field_id"]), axis=1)
    cdl["field_area_acres"] = cdl["key"].map(area_map)
    dominant = cdl.loc[cdl.groupby(["grower", "farm", "field_id", "year"])["pct"].idxmax()].copy()
    grower_state = {"il-grower": "17", "ia-grower": "19", "ne-grower": "31"}
    dominant["state_fips"] = dominant["grower"].map(grower_state)
    rows = []
    for _, row in dominant.iterrows():
        crop = str(row.get("crop_name", "")).strip()
        state = str(row.get("state_fips", "17"))
        plant_mm, plant_dd, harv_mm, harv_dd = _lookup_calendar(state, crop)
        rows.append({
            "grower": row["grower"],
            "farm": row["farm"],
            "field_id": row["field_id"],
            "year": int(row["year"]),
            "crop": crop,
            "plant_start": f"{int(row['year'])}-{plant_mm:02d}-{plant_dd:02d}",
            "harvest_end": f"{int(row['year'])}-{harv_mm:02d}-{harv_dd:02d}",
            "source": "USDA NASS typical crop progress (state-level)",
        })
    return pd.DataFrame(rows).sort_values(["grower", "farm", "field_id", "year"])


# ---------------------------------------------------------------------------
# Deliverable 5 — Plant/harvest timeline chart
# ---------------------------------------------------------------------------


def render_plant_harvest_chart(plant_harvest: pd.DataFrame) -> None:
    grower_colors = {
        "il-grower": "#2E7D32",
        "ia-grower": "#1565C0",
        "ne-grower": "#E65100",
    }

    ph = plant_harvest.copy()
    ph = ph[ph["crop"] != "Forest"]
    ph["plant_dt"] = pd.to_datetime(ph["plant_start"])
    ph["harvest_dt"] = pd.to_datetime(ph["harvest_end"])
    ph["plant_doy"] = ph["plant_dt"].dt.dayofyear
    ph["harvest_doy"] = ph["harvest_dt"].dt.dayofyear

    # Average across all years per (grower, crop)
    avg = ph.groupby(["grower", "crop"]).agg(
        plant_doy=("plant_doy", "mean"),
        harvest_doy=("harvest_doy", "mean"),
    ).reset_index()
    avg["plant_doy"] = avg["plant_doy"].round().astype(int)
    avg["harvest_doy"] = avg["harvest_doy"].round().astype(int)

    _ref = 2000
    avg["plant_dt"] = avg["plant_doy"].apply(lambda d: pd.Timestamp(_ref, 1, 1) + pd.Timedelta(days=d - 1))
    avg["harvest_dt"] = avg["harvest_doy"].apply(lambda d: pd.Timestamp(_ref, 1, 1) + pd.Timedelta(days=d - 1))

    crop_order = ["Corn", "Soybeans", "Grass/Pasture"]
    crop_present = [c for c in crop_order if c in avg["crop"].unique()]
    if not crop_present:
        crop_present = crop_order
    y_map = {c: i for i, c in enumerate(crop_present)}

    fig, ax = plt.subplots(figsize=(14, 3.8))
    fig.suptitle(
        "Average Planting–Harvest Timeline by Grower and Crop",
        fontsize=13,
        fontweight="bold",
    )

    ax.set_ylim(-0.8, len(crop_present) - 0.2)
    ax.set_yticks(range(len(crop_present)))
    ax.set_yticklabels(crop_present, fontsize=11)

    grower_offset = {"il-grower": -0.18, "ia-grower": 0.0, "ne-grower": 0.18}

    for _, row in avg.iterrows():
        crop = row["crop"]
        grower = row["grower"]
        color = grower_colors.get(grower, "#757575")
        base_y = y_map[crop]
        y = base_y + grower_offset.get(grower, 0)
        plant = row["plant_dt"]
        harvest = row["harvest_dt"]
        duration = (harvest - plant).days

        ax.barh(
            y,
            duration,
            left=plant,
            height=0.15,
            color=color,
            alpha=0.7,
            edgecolor=color,
            linewidth=0.5,
        )

        # Plant date label (left side)
        ax.text(
            plant,
            y + 0.08,
            plant.strftime("%b %d"),
            fontsize=6.5,
            color="#333",
            ha="right",
            va="center",
        )
        # Harvest date label (right side)
        ax.text(
            harvest,
            y + 0.08,
            harvest.strftime("%b %d"),
            fontsize=6.5,
            color="#333",
            ha="left",
            va="center",
        )

    ax.set_xlabel("")
    ax.xaxis.set_major_locator(plt.matplotlib.dates.MonthLocator())
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b"))
    ax.set_xlim(pd.Timestamp(f"{_ref}-04-01"), pd.Timestamp(f"{_ref}-11-30"))
    ax.grid(axis="x", alpha=0.3)

    from matplotlib.patches import Patch
    legend_patches = [
        Patch(color=grower_colors[g], label=g.replace("-", " ").title(), alpha=0.7)
        for g in sorted(avg["grower"].unique())
    ]
    ax.legend(handles=legend_patches, fontsize=9, loc="upper right")

    fig.tight_layout()
    output = OUTPUT_DIR / "field_plant_harvest_timeline.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 6 — Offseason precipitation cumulative chart
# ---------------------------------------------------------------------------


def _precip_daily_cumulative(weather: pd.DataFrame, plant_harvest: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute daily cumulative precipitation for each field × year in the offseason window."""
    results: dict[str, list[dict]] = {}

    for grower in weather["grower"].unique():
        farm = FARMS[grower]["slug"]
        w = weather[(weather["grower"] == grower) & (weather["farm"] == farm)].copy()
        ph = plant_harvest[
            (plant_harvest["grower"] == grower) & (plant_harvest["farm"] == farm)
        ].copy()
        ph["plant_dt"] = pd.to_datetime(ph["plant_start"])
        ph["harvest_dt"] = pd.to_datetime(ph["harvest_end"])
        grower_rows: list[dict] = []

        for field_id in w["field_id"].unique():
            wf = w[w["field_id"] == field_id].set_index("date").sort_index()
            field_ph = ph[ph["field_id"] == field_id]

            for _, ph_row in field_ph.iterrows():
                year = int(ph_row["year"])
                if year <= 2021:
                    continue
                harv_end = pd.Timestamp(
                    year=year - 1,
                    month=ph_row["harvest_dt"].month,
                    day=ph_row["harvest_dt"].day,
                )
                plant_start = ph_row["plant_dt"]
                window = wf.loc[harv_end:plant_start].copy()
                if len(window) == 0:
                    continue
                window = window.reset_index()
                window["cumul_precip_mm"] = window["PRECTOTCORR"].cumsum()
                window["day_index"] = range(len(window))
                window["field_id"] = field_id
                window["year"] = year
                grower_rows.extend(window.to_dict("records"))

        if grower_rows:
            results[grower] = pd.DataFrame(grower_rows)

    return results


def render_precip_chart(weather: pd.DataFrame, plant_harvest: pd.DataFrame) -> None:
    daily_data = _precip_daily_cumulative(weather, plant_harvest)
    if not daily_data:
        print("  skip precip_offseason_cumulative — no data in window")
        return

    grower_colors = {"il-grower": "#2E7D32", "ia-grower": "#1565C0", "ne-grower": "#E65100"}

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), sharey=True)
    fig.suptitle(
        "Off-Season Cumulative Precipitation (Harvest \u2192 Next Planting)",
        fontsize=13,
        fontweight="bold",
    )

    for ax, grower in zip(axes, sorted(daily_data.keys())):
        df = daily_data[grower]
        color = grower_colors.get(grower, "#757575")
        for (field_id, year), group in df.groupby(["field_id", "year"]):
            ax.plot(
                group["day_index"],
                group["cumul_precip_mm"],
                linewidth=0.6,
                alpha=0.45,
                color=color,
            )
        ax.set_title(grower, fontsize=11)
        ax.set_xlabel("Days since previous harvest", fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Cumulative Precipitation (mm)")
    fig.tight_layout()
    output = OUTPUT_DIR / "precip_offseason_cumulative.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 7 — Growing-season daily temperature (farm-level averages)
# ---------------------------------------------------------------------------


def render_temperature_chart(weather: pd.DataFrame, plant_harvest: pd.DataFrame) -> None:
    grower_colors = {"il-grower": "#2E7D32", "ia-grower": "#1565C0", "ne-grower": "#E65100"}

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), sharey=True)
    fig.suptitle("Growing-Season Daily Temperature (Farm-Level Average)", fontsize=13, fontweight="bold")

    for ax, grower in zip(axes, sorted(weather["grower"].unique())):
        farm = FARMS[grower]["slug"]
        w = weather[(weather["grower"] == grower) & (weather["farm"] == farm)].copy()
        ph = plant_harvest[
            (plant_harvest["grower"] == grower) & (plant_harvest["farm"] == farm)
        ].copy()
        ph["plant_dt"] = pd.to_datetime(ph["plant_start"])
        ph["harvest_dt"] = pd.to_datetime(ph["harvest_end"])
        color = grower_colors.get(grower, "#757575")

        # Compute season day-of-year averages across all fields
        season_records = []
        for _, ph_row in ph.iterrows():
            year = int(ph_row["year"])
            season = w[(w["date"] >= ph_row["plant_dt"]) & (w["date"] <= ph_row["harvest_dt"])]
            for _, srow in season.iterrows():
                season_records.append({
                    "doy": srow["date"].dayofyear,
                    "T2M_MAX": srow["T2M_MAX"],
                    "T2M_MIN": srow["T2M_MIN"],
                    "field_id": srow["field_id"],
                })

        if not season_records:
            ax.set_title(f"{grower} (no data)", fontsize=11)
            continue

        sdf = pd.DataFrame(season_records)
        daily = sdf.groupby("doy").agg(
            T2M_MAX_avg=("T2M_MAX", "mean"),
            T2M_MIN_avg=("T2M_MIN", "mean"),
        ).reset_index()
        daily["T2M_AVG_avg"] = (daily["T2M_MAX_avg"] + daily["T2M_MIN_avg"]) / 2
        daily = daily.sort_values("doy")

        ax.fill_between(
            daily["doy"],
            daily["T2M_MIN_avg"],
            daily["T2M_MAX_avg"],
            alpha=0.15,
            color=color,
        )
        ax.plot(daily["doy"], daily["T2M_MAX_avg"], linewidth=1.2, color="#C62828", label="Max")
        ax.plot(daily["doy"], daily["T2M_AVG_avg"], linewidth=1.5, color="#1e3a5f", label="Avg")
        ax.plot(daily["doy"], daily["T2M_MIN_avg"], linewidth=1.2, color="#1565C0", label="Min")
        ax.set_title(grower, fontsize=11)
        ax.set_xlabel("Day of Year", fontsize=8)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="upper right")

    axes[0].set_ylabel("Temperature (°C)")
    fig.tight_layout()
    output = OUTPUT_DIR / "temperature_growing_season.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 8 — Field area box plot (five-number summary)
# ---------------------------------------------------------------------------


def render_area_boxplot(boundaries: pd.DataFrame) -> None:
    grower_colors = {
        "il-grower": "#2E7D32",
        "ia-grower": "#1565C0",
        "ne-grower": "#E65100",
    }
    farms_ordered = sorted(boundaries["farm"].unique())
    box_data = [boundaries[boundaries["farm"] == f]["area_acres"].dropna().tolist() for f in farms_ordered]
    labels = [f.replace("-", " ").title() for f in farms_ordered]
    colors = [grower_colors.get(boundaries[boundaries["farm"] == f]["grower"].iloc[0], "#757575") for f in farms_ordered]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.suptitle("Field Area Distribution — Five-Number Summary", fontsize=13, fontweight="bold")

    bp = ax.boxplot(box_data, patch_artist=True, widths=0.5,
                     medianprops={"color": "#333", "linewidth": 2},
                     whiskerprops={"linewidth": 1.2},
                     capprops={"linewidth": 1.2},
                     boxprops={"linewidth": 1.2})
    ax.set_xticklabels(labels)

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)

    for i, (farm, data) in enumerate(zip(farms_ordered, box_data)):
        if not data:
            continue
        s = sorted(data)
        n = len(s)
        mn, q1, med, q3, mx = s[0], s[n // 4], s[n // 2], s[3 * n // 4], s[-1]
        stats = [("Min", mn), ("Q1", q1), ("Med", med), ("Q3", q3), ("Max", mx)]
        for label, val in stats:
            ax.annotate(f"{label}\n{val:.0f}", xy=(i + 1, val),
                        xytext=(15, 0), textcoords="offset points",
                        fontsize=7, color="#333", va="center",
                        arrowprops=dict(arrowstyle="-", color="#ccc", lw=0.5))

    ax.set_ylabel("Area (acres)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    output = OUTPUT_DIR / "field_area_boxplot.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 9 — Crop area vs total area stacked bar chart
# ---------------------------------------------------------------------------


def render_crop_area_comparison(cdl_composition: pd.DataFrame, boundaries: pd.DataFrame) -> None:
    total_area = boundaries.groupby("farm")["area_acres"].sum()
    grower_colors = {"il-grower": "#2E7D32", "ia-grower": "#1565C0", "ne-grower": "#E65100"}
    crop_colors = {"Corn": "#F9A825", "Soybeans": "#2E7D32", "Other": "#BDBDBD"}
    farms_ordered = sorted(cdl_composition["farm"].unique())
    years = sorted(cdl_composition["year"].unique())

    fig, axes = plt.subplots(len(farms_ordered), 1, figsize=(14, 3 * len(farms_ordered)), sharex=True)
    if len(farms_ordered) == 1:
        axes = [axes]
    fig.suptitle("Estimated Crop Acres vs Total Farm Area", fontsize=13, fontweight="bold")

    for ax, farm in zip(axes, farms_ordered):
        farm_data = cdl_composition[cdl_composition["farm"] == farm]
        total = total_area.get(farm, 0)
        grower = farm_data["grower"].iloc[0] if len(farm_data) else ""

        corn_vals, soy_vals, other_vals = [], [], []
        for y in years:
            yd = farm_data[farm_data["year"] == y]
            corn = yd[yd["dominant_crop"] == "Corn"]["estimated_planted_acres"].sum()
            soy = yd[yd["dominant_crop"] == "Soybeans"]["estimated_planted_acres"].sum()
            corn_vals.append(corn)
            soy_vals.append(soy)
            other_vals.append(max(0, total - corn - soy))

        x = range(len(years))
        w = 0.6
        b1 = ax.bar(x, corn_vals, w, color=crop_colors["Corn"], alpha=0.8, label="Corn")
        b2 = ax.bar(x, soy_vals, w, bottom=corn_vals, color=crop_colors["Soybeans"], alpha=0.8, label="Soybeans")
        bottom_other = [c + s for c, s in zip(corn_vals, soy_vals)]
        b3 = ax.bar(x, other_vals, w, bottom=bottom_other, color=crop_colors["Other"], alpha=0.6, label="Other")

        ax.axhline(total, color=grower_colors.get(grower, "#333"), linestyle="--", linewidth=1.2, alpha=0.7)
        ax.text(4.6, total, f"total {total:.0f}", fontsize=8, color=grower_colors.get(grower, "#333"), va="bottom", ha="right")

        for i, (c, s) in enumerate(zip(corn_vals, soy_vals)):
            if c > 0:
                ax.text(i, c / 2, f"{c:.0f}", ha="center", va="center", fontsize=7, color="white", fontweight="bold")
            if s > 0:
                ax.text(i, c + s / 2, f"{s:.0f}", ha="center", va="center", fontsize=7, color="white", fontweight="bold")

        ax.set_ylabel(farm.replace("-", " ").title(), fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([str(y) for y in years])
        ax.grid(axis="y", alpha=0.3)

    axes[0].legend(fontsize=9, ncol=3, loc="upper right")
    axes[-1].set_xlabel("Year")
    fig.tight_layout()
    output = OUTPUT_DIR / "crop_area_comparison.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 10 — Growing degree days line chart
# ---------------------------------------------------------------------------


def render_gdd_chart(weather: pd.DataFrame, plant_harvest: pd.DataFrame, cdl_composition: pd.DataFrame) -> None:
    grower_colors = {"il-grower": "#2E7D32", "ia-grower": "#1565C0", "ne-grower": "#E65100"}

    ph = plant_harvest.copy()
    ph["plant_dt"] = pd.to_datetime(ph["plant_start"])
    ph["harvest_dt"] = pd.to_datetime(ph["harvest_end"])
    ph["crop"] = ph["crop"].fillna("Unknown")

    cdl_map = cdl_composition.set_index(["grower", "farm", "field_id", "year"])["dominant_crop"]
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"])
    w["key"] = w.apply(lambda r: (r["grower"], r["farm"], r["field_id"], r["date"].year), axis=1)
    w["crop"] = w["key"].map(cdl_map)

    # GDD: Tmax capped at 30, Tmin floored at 10, base 10°C
    w["tmax_cap"] = w["T2M_MAX"].clip(upper=30)
    w["tmin_floor"] = w["T2M_MIN"].clip(lower=10)
    w["gdd"] = ((w["tmax_cap"] + w["tmin_floor"]) / 2 - 10).clip(lower=0)

    records = []
    for grower in sorted(w["grower"].unique()):
        wg = w[w["grower"] == grower]
        phg = ph[ph["grower"] == grower].copy()
        for crop in ["Corn", "Soybeans"]:
            wc = wg[wg["crop"] == crop].copy()
            if wc.empty:
                continue
            for year in sorted(wc["date"].dt.year.unique()):
                wcy = wc[wc["date"].dt.year == year]
                phgy = phg[(phg["year"] == year) & (phg["crop"] == crop)]
                if phgy.empty or wcy.empty:
                    continue
                # Days between earliest plant and latest harvest for this crop-grower-year
                plant_d = phgy["plant_dt"].min()
                harv_d = phgy["harvest_dt"].max()
                season = wcy[(wcy["date"] >= plant_d) & (wcy["date"] <= harv_d)]
                if season.empty:
                    continue
                total_gdd = season.groupby("field_id")["gdd"].sum().mean()
                records.append({"grower": grower, "crop": crop, "year": year, "gdd": total_gdd})

    if not records:
        print("  skip growing_degree_days — no season data")
        return

    gdf = pd.DataFrame(records)
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle("Cumulative Growing Degree Days (GDD) by Farm and Crop", fontsize=13, fontweight="bold")

    for grower in sorted(gdf["grower"].unique()):
        gd = gdf[gdf["grower"] == grower]
        color = grower_colors.get(grower, "#757575")
        for crop, ls in [("Corn", "-"), ("Soybeans", "--")]:
            cd = gd[gd["crop"] == crop].sort_values("year")
            if cd.empty:
                continue
            ax.plot(cd["year"], cd["gdd"], marker="o", linewidth=2, markersize=8,
                    color=color, linestyle=ls, alpha=0.85,
                    label=f"{grower.replace('-', ' ').title()} {crop}")
            for _, row in cd.iterrows():
                ax.text(row["year"], row["gdd"] + 12, f"{row['gdd']:.0f}",
                        fontsize=7, ha="center", color=color)

    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative GDD (°C-days)")
    ax.set_xticks(sorted(gdf["year"].unique()))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    output = OUTPUT_DIR / "growing_degree_days.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Deliverable 11 — Combined all-farms geospatial map
# ---------------------------------------------------------------------------


def render_all_farms_map(growers: list[str]) -> None:

    farm_colors = {
        "il-grower-illinois": "#2E7D32",
        "ia-grower-iowa": "#1565C0",
        "ne-grower-nebraska": "#E65100",
    }
    farm_names = {
        "il-grower-illinois": "IL Grower — Iroquois County",
        "ia-grower-iowa": "IA Grower — Kossuth County",
        "ne-grower-nebraska": "NE Grower — Phelps County",
    }
    grower_by_farm = {
        "il-grower-illinois": "il-grower",
        "ia-grower-iowa": "ia-grower",
        "ne-grower-nebraska": "ne-grower",
    }

    all_features = []
    for grower in growers:
        farm = FARMS[grower]["slug"]
        path = _boundary_path(grower, farm)
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            feat = copy.deepcopy(feat)
            feat["properties"]["farm_slug"] = farm
            feat["properties"]["grower_slug"] = grower
            feat["properties"]["farm_display"] = farm_names.get(farm, farm)
            feat["properties"]["color"] = farm_colors.get(farm, "#757575")
            all_features.append(feat)

    if not all_features:
        print("  skip all_farms_map — no features found")
        return

    geojson = {"type": "FeatureCollection", "features": all_features}

    field_list_entries = []
    field_js_lookup = []
    for idx, feat in enumerate(all_features):
        props = feat["properties"]
        fid = props.get("field_id", f"field_{idx}")
        color = props["color"]
        area = round(float(props.get("area_acres", 0)), 1)
        field_list_entries.append(
            f'<li class="field-item" style="border-left:4px solid {color}" '
            f'onclick="zoomToField(\'{fid}\')">'
            f'<span class="field-name">{fid}</span>'
            f'<span class="field-acres">{area} ac</span></li>'
        )
        field_js_lookup.append(f'"{fid}":{{"color":"{color}","index":{idx}}},')

    sidebar_farms = {}
    for feat in all_features:
        farm = feat["properties"]["farm_slug"]
        if farm not in sidebar_farms:
            sidebar_farms[farm] = []
        sidebar_farms[farm].append(feat["properties"]["field_id"])

    total_fields = len(all_features)
    sidebar_lines = []
    for farm, fids in sidebar_farms.items():
        sidebar_lines.append(
            f'<div class="farm-group"><div class="farm-group-header" '
            f'style="border-left:4px solid {farm_colors.get(farm, "#757575")}">'
            f'{farm_names.get(farm, farm)} ({len(fids)} fields)</div></div>'
        )
        for fid in fids:
            for entry in field_list_entries:
                if fid in entry:
                    sidebar_lines.append(entry)
                    break

    geojson_json = json.dumps(geojson)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>All Farms — Field Boundaries Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
#container {{ display:flex; height:100vh; }}
#sidebar {{ width:300px; min-width:240px; background:#f8fafc; border-right:1px solid #e2e8f0; display:flex; flex-direction:column; overflow:hidden; }}
#sidebar-header {{ padding:16px; border-bottom:1px solid #e2e8f0; background:white; }}
#sidebar-header h1 {{ font-size:1.1em; color:#1e293b; margin:0; }}
#sidebar-header .sub {{ font-size:0.8em; color:#64748b; margin-top:4px; }}
#field-list {{ flex:1; overflow-y:auto; padding:8px 0; }}
.farm-group-header {{ padding:8px 16px; font-size:0.82em; font-weight:600; color:#475569; background:#f1f5f9; margin-top:4px; }}
.field-item {{ display:flex; justify-content:space-between; align-items:center; padding:8px 16px; cursor:pointer; transition:background 0.15s; border-bottom:1px solid #f1f5f9; }}
.field-item:hover {{ background:#e2e8f0; }}
.field-name {{ font-size:0.78em; font-weight:500; color:#334155; }}
.field-acres {{ font-size:0.72em; color:#64748b; white-space:nowrap; }}
#map {{ flex:1; }}
.leaflet-popup-content {{ font-size:0.88em; line-height:1.5; }}
.leaflet-popup-content b {{ color:#1e293b; }}
@media (max-width:600px) {{ #container {{ flex-direction:column; }} #sidebar {{ width:100%; max-height:40vh; }} }}
</style>
</head>
<body>
<div id="container">
<div id="sidebar">
<div id="sidebar-header">
<h1>All Farms — Field Boundaries</h1>
<div class="sub">{len(growers)} growers &middot; {len(sidebar_farms)} farms &middot; {total_fields} fields</div>
</div>
<div id="field-list">
{chr(10).join("    " + line for line in sidebar_lines)}
</div>
</div>
<div id="map"></div>
</div>
<script>
var fieldColors = {{
{chr(10).join("    " + entry for entry in field_js_lookup)}
}};

var geojson = {geojson_json};

var map = L.map('map', {{ zoomControl: true }});

var osmLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
}});

var satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    maxZoom: 19,
}});

satelliteLayer.addTo(map);

var baseMaps = {{ "Street Map": osmLayer, "Satellite": satelliteLayer }};
L.control.layers(baseMaps).addTo(map);

var fieldLayer = L.geoJSON(geojson, {{
    style: function(feature) {{
        var fid = feature.properties.field_id || '';
        var cinfo = fieldColors[fid];
        return {{
            color: cinfo ? cinfo.color : '#757575',
            weight: 2,
            opacity: 0.9,
            fillOpacity: 0.25,
            fillColor: cinfo ? cinfo.color : '#757575',
        }};
    }},
    onEachFeature: function(feature, layer) {{
        var p = feature.properties;
        var popup = '<b>Grower:</b> ' + (p.grower_slug || '—') + '<br>'
                  + '<b>Farm:</b> ' + (p.farm_display || '—') + '<br>'
                  + '<b>Field:</b> ' + (p.field_id || '—') + '<br>'
                  + '<b>Area:</b> ' + (p.area_acres != null ? p.area_acres.toFixed(1) : '—') + ' acres<br>'
                  + '<b>County:</b> ' + (p.county_name || '—') + '<br>'
                  + '<b>Crop:</b> ' + (p.crop_name || '—');
        layer.bindPopup(popup);

        layer.on('mouseover', function() {{ layer.setStyle({{ weight:4, fillOpacity:0.45 }}); }});
        layer.on('mouseout', function() {{ fieldLayer.resetStyle(layer); }});
    }}
}}).addTo(map);

map.fitBounds(fieldLayer.getBounds().pad(0.1));

function zoomToField(fieldId) {{
    fieldLayer.eachLayer(function(layer) {{
        if (layer.feature && layer.feature.properties.field_id === fieldId) {{
            map.fitBounds(layer.getBounds().pad(0.3));
            layer.openPopup();
        }}
    }});
}}
</script>
</body>
</html>"""

    output = OUTPUT_DIR / "all_farms_map.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"  ok  {output.relative_to(PIPELINE_ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Assignment 2 field-level EDA")
    parser.add_argument("--grower-slug", default=None, help="Process a single grower")
    args = parser.parse_args()

    growers = [args.grower_slug] if args.grower_slug else list(FARMS.keys())
    print(f"Assignment 2 EDA — growers: {growers}")
    print(f"Output dir: {OUTPUT_DIR}")

    # Load
    print("\nLoading data ...")
    boundaries = load_boundaries(growers)
    print(f"  boundaries: {len(boundaries)} fields")
    weather = load_weather(growers)
    print(f"  weather: {len(weather)} rows")
    cdl = load_cdl(growers)
    print(f"  CDL: {len(cdl)} rows")

    # 1 — Area chart
    print("\n[1/6] Field area comparison ...")
    render_area_chart(boundaries)

    # 2 — Latitude chart
    print("[2/7] Latitude extents chart ...")
    render_latitude_chart(boundaries)

    # Build CDL composition
    print("[3/7] Building CDL composition ...")
    cdl_composition = _build_cdl_composition(cdl, boundaries)

    # 3 — Corn yield line graph
    print("[3b/7] Corn acreage line graph ...")
    render_yield_line(cdl_composition, "Corn", "estimated_corn_acres.png")

    # 4 — Soybean yield line graph
    print("[4/7] Soybean acreage line graph ...")
    render_yield_line(cdl_composition, "Soybeans", "estimated_soybean_acres.png")

    # Build plant/harvest estimates
    print("[5/7] Building plant/harvest estimates ...")
    plant_harvest = _build_plant_harvest(cdl, boundaries)

    # 5 — Plant/harvest timeline chart
    print("[5b/7] Plant/harvest timeline chart ...")
    render_plant_harvest_chart(plant_harvest)

    # 6 — Precipitation chart
    print("[6/7] Offseason precipitation ...")
    render_precip_chart(weather, plant_harvest)

    # 7 — Temperature chart
    print("[7/10] Growing-season temperature ...")
    render_temperature_chart(weather, plant_harvest)

    # 8 — Five-number summary box plot
    print("[8/10] Field area box plot ...")
    render_area_boxplot(boundaries)

    # 9 — Crop area vs total area comparison
    print("[9/10] Crop area comparison ...")
    render_crop_area_comparison(cdl_composition, boundaries)

    # 10 — Growing degree days
    print("[10/11] Growing degree days ...")
    render_gdd_chart(weather, plant_harvest, cdl_composition)

    # 11 — Combined all-farms map
    print("[11/11] All-farms geospatial map ...")
    render_all_farms_map(growers)

    print(f"\nDone — {len(growers)} grower(s) processed.")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
