from __future__ import annotations

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from shapely.geometry import mapping

matplotlib.use("Agg")

C_TO_F = 9.0 / 5.0
GDD_BASE_C = 10.0
GDD_BASE_F = 50.0

YEAR_COLORS = {
    2021: "#1b9e77",
    2022: "#d95f02",
    2023: "#7570b3",
    2024: "#e7298a",
    2025: "#66a61e",
}


def extract_ndvi_scene_metrics(field_dir: Path) -> pd.DataFrame:
    sentinel_dir = field_dir / "satellite" / "sentinel"
    boundary_path = field_dir / "boundary" / "field_boundary.geojson"
    if not boundary_path.exists():
        raise FileNotFoundError(f"Field boundary not found: {boundary_path}")

    boundary_gdf = gpd.read_file(boundary_path)
    if boundary_gdf.crs is None:
        boundary_gdf = boundary_gdf.set_crs("EPSG:4326")
    boundary_geom = boundary_gdf.geometry.iloc[0]

    records: list[dict] = []
    if not sentinel_dir.is_dir():
        return pd.DataFrame(records)

    for year_dir in sorted(sentinel_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        for scene_dir in sorted(year_dir.iterdir()):
            if not scene_dir.is_dir():
                continue
            scene_name = scene_dir.name
            ndvi_path = scene_dir / f"{scene_name}_ndvi.tif"
            if not ndvi_path.exists():
                continue
            date_str = scene_name.replace("sentinel_", "")
            try:
                month = int(date_str[4:6])
                day = int(date_str[6:8])
            except (IndexError, ValueError):
                continue
            try:
                with rasterio.open(ndvi_path) as src:
                    out_image, _ = rasterio.mask.mask(
                        src, [mapping(boundary_geom)], crop=True,
                        nodata=np.nan, all_touched=True,
                    )
                    data = out_image[0]
                valid = data[~np.isnan(data)]
                if len(valid) == 0:
                    continue
                records.append({
                    "date_str": date_str,
                    "year": year,
                    "month": month,
                    "day": day,
                    "doy": int(pd.Timestamp(f"{year}-{month:02d}-{day:02d}").dayofyear),
                    "scene_name": scene_name,
                    "ndvi_mean": float(np.mean(valid)),
                    "ndvi_median": float(np.median(valid)),
                    "ndvi_std": float(np.std(valid)),
                    "ndvi_min": float(np.min(valid)),
                    "ndvi_max": float(np.max(valid)),
                    "valid_pixels": int(len(valid)),
                })
            except Exception:
                continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(["year", "doy"]).reset_index(drop=True)
    return df


def load_weather_for_field(csv_path: Path, field_id: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df[df["field_id"] == field_id].copy()
    df["year"] = df["date"].dt.year
    df["doy"] = df["date"].dt.dayofyear
    # Metric (original)
    df["gdd_c"] = np.maximum(0, (df["T2M_MAX"] + df["T2M_MIN"]) / 2.0 - GDD_BASE_C)
    df["cum_gdd_c"] = df.groupby("year")["gdd_c"].cumsum()
    df["cum_precip_mm"] = df.groupby("year")["PRECTOTCORR"].cumsum()
    # US customary
    df["T2M_MAX_F"] = df["T2M_MAX"] * C_TO_F + 32
    df["T2M_MIN_F"] = df["T2M_MIN"] * C_TO_F + 32
    df["T2M_F"] = df["T2M"] * C_TO_F + 32
    df["PRECTOTCORR_IN"] = df["PRECTOTCORR"] / 25.4
    df["gdd_f"] = np.maximum(0, (df["T2M_MAX_F"] + df["T2M_MIN_F"]) / 2.0 - GDD_BASE_F)
    df["cum_gdd_f"] = df.groupby("year")["gdd_f"].cumsum()
    df["cum_precip_in"] = df.groupby("year")["PRECTOTCORR_IN"].cumsum()
    return df


def load_crop_history(rotation_csv: Path, field_id: str) -> dict[int, str]:
    if not rotation_csv.exists():
        return {}
    df = pd.read_csv(rotation_csv)
    row = df[df["field_id"] == field_id]
    if row.empty:
        return {}
    crops: dict[int, str] = {}
    seq = str(row.iloc[0].get("rotation_sequence", ""))
    parts = [s.strip() for s in seq.split("->")]
    start = int(row.iloc[0].get("history_start_year", 2021))
    for i, crop in enumerate(parts):
        crops[start + i] = crop
    return crops


def _prefix(farm_slug: str) -> str:
    return farm_slug.strip().replace("-", "_")


def detect_events(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    year: int,
    ndvi_dip_thresh: float = 0.15,
    ndvi_jump_thresh: float = 0.25,
    heavy_rain_thresh_in: float = 1.18,
    hot_day_thresh_f: float = 95.0,
) -> list[dict]:
    events: list[dict] = []
    w = weather_df[weather_df["year"] == year]
    ndvi_yr = ndvi_df[ndvi_df["year"] == year].sort_values("doy")

    # Heavy rain days (inches)
    heavy = w[w["PRECTOTCORR_IN"] > heavy_rain_thresh_in]
    for _, row in heavy.iterrows():
        events.append({
            "doy": row["doy"], "date": row["date"],
            "type": "heavy_rain", "label": f"{row['PRECTOTCORR_IN']:.1f}\" rain",
            "severity": "high" if row["PRECTOTCORR_IN"] > 2.0 else "medium",
        })

    # Hot days (°F)
    hot = w[w["T2M_MAX_F"] > hot_day_thresh_f]
    for _, row in hot.iterrows():
        events.append({
            "doy": row["doy"], "date": row["date"],
            "type": "hot_day", "label": f"{row['T2M_MAX_F']:.0f}°F max",
            "severity": "high" if row["T2M_MAX_F"] > 100 else "medium",
        })

    # Cool periods (May-Aug: T2M_F < 32°F indicates frost risk)
    growing = w[(w["doy"] >= 120) & (w["doy"] <= 240)]
    cool = growing[growing["T2M_F"] < 32]
    if not cool.empty:
        for _, row in cool.iterrows():
            events.append({
                "doy": row["doy"], "date": row["date"],
                "type": "cool_period", "label": f"{row['T2M_MIN_F']:.0f}°F min",
                "severity": "medium",
            })

    # NDVI dips and rapid increases
    if len(ndvi_yr) >= 2:
        ndvi_vals = ndvi_yr["ndvi_mean"].values
        doy_vals = ndvi_yr["doy"].values
        for i in range(1, len(ndvi_vals)):
            diff = ndvi_vals[i] - ndvi_vals[i - 1]
            days_between = doy_vals[i] - doy_vals[i - 1]
            if diff < -ndvi_dip_thresh:
                events.append({
                    "doy": doy_vals[i], "date": None,
                    "type": "ndvi_dip",
                    "label": f"NDVI -{abs(diff):.2f}",
                    "severity": "high" if abs(diff) > 0.25 else "medium",
                })
            elif diff > ndvi_jump_thresh:
                events.append({
                    "doy": doy_vals[i], "date": None,
                    "type": "ndvi_jump",
                    "label": f"NDVI +{diff:.2f}",
                    "severity": "high",
                })

    events.sort(key=lambda e: e["doy"])
    return events


def _caption_text(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    events: list[dict],
    crop: str,
    year: int,
    coverage: dict | None = None,
) -> str:
    w = weather_df[weather_df["year"] == year]
    ndvi_yr = ndvi_df[ndvi_df["year"] == year]
    peak = ndvi_yr["ndvi_mean"].max() if not ndvi_yr.empty else 0
    precip_in = w["PRECTOTCORR_IN"].sum() if not w.empty else 0
    mean_t_f = w["T2M_F"].mean() if not w.empty else 0
    hot_cnt = sum(1 for e in events if e["type"] == "hot_day")
    rain_cnt = sum(1 for e in events if e["type"] == "heavy_rain")
    ndvi_rise = sum(1 for e in events if e["type"] == "ndvi_jump")
    ndvi_drop = sum(1 for e in events if e["type"] == "ndvi_dip")
    n_scenes = len(ndvi_yr)
    missing_months = coverage["missing_months"] if coverage else []
    warning = coverage["warning"] if coverage else None
    peak_gdd = w["cum_gdd_f"].max() if not w.empty else 0

    cap = (
        f"{year} {crop} \u2014 {n_scenes} Sentinel scenes \u00b7 "
        f"Peak NDVI {peak:.3f} \u00b7 {precip_in:.1f}\" precip \u00b7 "
        f"{mean_t_f:.0f}\u00b0F mean temp \u00b7 "
        f"{peak_gdd:.0f} GDD\u00b0F"
    )
    if hot_cnt or rain_cnt or ndvi_rise or ndvi_drop:
        cap += f" \u00b7 {hot_cnt} hot days \u00b7 {rain_cnt} heavy rain \u00b7 {ndvi_rise} NDVI rises \u00b7 {ndvi_drop} dips"
    if missing_months:
        cap += f" \u00b7 MISSING: month(s) {missing_months}"
    if warning:
        cap += f" \u00b7 COVERAGE WARNING: {warning[:80]}"
    return cap


def check_coverage(ndvi_df: pd.DataFrame, year: int) -> dict:
    ndvi_yr = ndvi_df[ndvi_df["year"] == year].sort_values("doy")
    if ndvi_yr.empty:
        return {"scene_count": 0, "max_gap_days": None,
                "months_covered": [], "missing_months": [],
                "warning": "No NDVI scenes found for this year"}
    growing_months = list(range(4, 11))  # Apr–Oct
    months_with_scenes = sorted(ndvi_yr["month"].unique())
    missing = [m for m in growing_months if m not in months_with_scenes]
    doys = ndvi_yr["doy"].values
    gaps = [doys[i] - doys[i - 1] for i in range(1, len(doys))]
    max_gap = max(gaps) if gaps else 0
    warnings = []
    if len(ndvi_yr) < 6:
        warnings.append(f"Only {len(ndvi_yr)} scenes in growing season (recommend >= 6)")
    if max_gap > 45:
        warnings.append(f"Max gap between scenes is {max_gap} days (recommend <= 45)")
    if missing:
        month_names = ", ".join(str(m) for m in missing)
        warnings.append(f"Missing coverage in month(s): {month_names}")
    return {
        "scene_count": len(ndvi_yr),
        "max_gap_days": max_gap,
        "months_covered": [int(m) for m in months_with_scenes],
        "missing_months": missing,
        "warning": "; ".join(warnings) if warnings else None,
    }


def plot_storyline(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    crop_history: dict[int, str],
    field_id: str,
    farm_name: str,
    output_path: Path,
    year: int,
    events: list[dict] | None = None,
    caption: str | None = None,
) -> Path:
    color = YEAR_COLORS.get(year, "#333333")
    GR = (60, 320)
    grow_start, grow_end = GR

    event_colors = {"heavy_rain": "#1f78b4", "hot_day": "#e31a1c",
                    "cool_period": "#6a3d9a", "ndvi_dip": "#ff7f00",
                    "ndvi_jump": "#33a02c"}
    event_labels = {"heavy_rain": "Rain", "hot_day": "Hot", "cool_period": "Cool",
                    "ndvi_dip": "Dip", "ndvi_jump": "Rise"}

    MONTH_DOYS = [60, 91, 121, 152, 182, 213, 244, 274, 305]
    MONTH_LABELS = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]

    fig, axes = plt.subplots(4, 1, figsize=(9, 12), sharex=False)
    fig.subplots_adjust(left=0.12, right=0.88, top=0.86, bottom=0.10, hspace=0.12)

    fig.text(0.5, 0.97, f"Field-Season Weather and NDVI Storyline \u2014 {field_id}/{year}",
             ha="center", fontsize=12, fontweight="bold")

    ax_ndvi, ax_precip, ax_temp, ax_gdd = axes

    for ax in [ax_ndvi, ax_temp, ax_gdd]:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    w_yr = weather_df[weather_df["year"] == year]
    ndvi_yr = ndvi_df[ndvi_df["year"] == year]
    ndvi_gs = ndvi_yr[(ndvi_yr["doy"] >= grow_start) & (ndvi_yr["doy"] <= grow_end)] if not ndvi_yr.empty else pd.DataFrame()
    w_gs = w_yr[(w_yr["doy"] >= grow_start) & (w_yr["doy"] <= grow_end)].copy() if not w_yr.empty else pd.DataFrame()

    # ----- helper: draw event lines -----
    def _draw_event_lines(ax):
        if not events:
            return
        for ev in events:
            if ev["doy"] < grow_start or ev["doy"] > grow_end:
                continue
            ecolor = event_colors.get(ev["type"], "#999")
            ax.axvline(ev["doy"], color=ecolor, linewidth=1.2, linestyle="--", alpha=0.5, zorder=3)

    # ===== PANEL 1: Mean NDVI =====
    if not ndvi_gs.empty:
        ax_ndvi.plot(ndvi_gs["doy"], ndvi_gs["ndvi_mean"], marker="o", color=color,
                     linewidth=1.8, markersize=5)
        crop = crop_history.get(year, "")
        for _, row in ndvi_gs.iterrows():
            ax_ndvi.annotate(crop, (row["doy"], row["ndvi_mean"]),
                             fontsize=6, alpha=0.6, ha="left", va="bottom",
                             xytext=(3, 3), textcoords="offset points")
    if events:
        _draw_event_lines(ax_ndvi)
        for ev in events:
            if ev["doy"] < grow_start or ev["doy"] > grow_end:
                continue
            ecolor = event_colors.get(ev["type"], "#999")
            ax_ndvi.annotate(ev["label"], (ev["doy"], 0.85),
                             fontsize=7, color=ecolor, ha="center", va="top",
                             fontweight="bold",
                             bbox=dict(facecolor="white", edgecolor=ecolor,
                                       boxstyle="round,pad=0.15", alpha=0.85),
                             rotation=30)
    ax_ndvi.set_xlim(GR)
    ax_ndvi.set_xticks(MONTH_DOYS)
    ax_ndvi.set_xticklabels(MONTH_LABELS, fontsize=6.5)
    ax_ndvi.set_ylabel("Mean NDVI")
    ax_ndvi.set_title(f"Mean NDVI \u2014 {year}", loc="left")
    ax_ndvi.grid(True, alpha=0.3, axis="y")

    # ===== PANEL 2: Precip. (in) =====
    if not w_gs.empty:
        w_gs["cum_in"] = w_gs["PRECTOTCORR_IN"].cumsum()
        ax_precip.bar(w_gs["doy"], w_gs["PRECTOTCORR_IN"], width=0.7,
                      color="#1f78b4", alpha=0.4, label="Daily")
        ax_p2 = ax_precip.twinx()
        ax_p2.plot(w_gs["doy"], w_gs["cum_in"], color="#084594",
                   linewidth=1.5, label="Cumulative")
        ax_p2.set_ylabel("Cumulative (in)", color="#084594")
        ax_p2.tick_params(axis="y", colors="#084594")
        ax_p2.set_ylim(0, max(w_gs["cum_in"]) * 1.15 if len(w_gs) > 0 else 10)
        # Rain event callouts
        if events:
            for ev in events:
                if ev["doy"] < grow_start or ev["doy"] > grow_end or ev["type"] != "heavy_rain":
                    continue
                yv = w_gs[w_gs["doy"] == ev["doy"]]["PRECTOTCORR_IN"].values
                ypos = yv[0] + 0.1 if len(yv) > 0 else 1.0
                ax_precip.annotate(f"\u2601{ev['label']}", (ev["doy"], ypos),
                                   fontsize=7, color="#1f78b4", ha="center",
                                   fontweight="bold",
                                   bbox=dict(facecolor="white", edgecolor="#1f78b4",
                                             boxstyle="round,pad=0.12", alpha=0.85),
                                   rotation=30)
    if events:
        _draw_event_lines(ax_precip)
    ax_precip.set_xlim(GR)
    ax_precip.set_xticks(MONTH_DOYS)
    ax_precip.set_xticklabels(MONTH_LABELS, fontsize=6.5)
    ax_precip.set_ylabel("Precip. (in)", color="#1f78b4")
    ax_precip.set_title("Precip. (in)", loc="left")
    ax_precip.legend(fontsize=6, loc="upper left")
    ax_precip.grid(True, alpha=0.3, axis="y")

    # ===== PANEL 3: Temp. (°F) =====
    if not w_gs.empty:
        ax_temp.fill_between(w_gs["doy"], w_gs["T2M_MIN_F"], w_gs["T2M_MAX_F"],
                             alpha=0.15, color=color)
        ax_temp.plot(w_gs["doy"], w_gs["T2M_MAX_F"], color=color, linewidth=1.0)
        ax_temp.plot(w_gs["doy"], w_gs["T2M_MIN_F"], color=color, linewidth=1.0, alpha=0.7)
    ax_temp.axhline(95, color="#e31a1c", linewidth=0.6, linestyle=":", alpha=0.5)
    ax_temp.text(GR[0] + 2, 96, "95\u00b0F threshold", fontsize=5.5, color="#e31a1c", alpha=0.6)
    if events:
        _draw_event_lines(ax_temp)
        for ev in events:
            if ev["doy"] < grow_start or ev["doy"] > grow_end:
                continue
            ecolor = event_colors.get(ev["type"], "#999")
            if ev["type"] == "hot_day":
                ax_temp.annotate(f"\u2600{ev['label']}", (ev["doy"], 100),
                                 fontsize=7, color=ecolor, ha="center",
                                 fontweight="bold",
                                 bbox=dict(facecolor="white", edgecolor=ecolor,
                                           boxstyle="round,pad=0.12", alpha=0.85),
                                 rotation=30)
    ax_temp.set_xlim(GR)
    ax_temp.set_xticks(MONTH_DOYS)
    ax_temp.set_xticklabels(MONTH_LABELS, fontsize=6.5)
    ax_temp.set_ylabel("Temp. (\u00b0F)")
    ax_temp.set_title("Temp. (\u00b0F)", loc="left")
    ax_temp.grid(True, alpha=0.3)

    # ===== PANEL 4: Cumulative GDD (°F-days) =====
    if not w_gs.empty:
        ax_gdd.plot(w_gs["doy"], w_gs["cum_gdd_f"], color=color, linewidth=1.8)
        # Scene marker overlay
        if not ndvi_gs.empty:
            for _, srow in ndvi_gs.iterrows():
                gdd_val = w_gs[w_gs["doy"] == srow["doy"]]["cum_gdd_f"].values
                if len(gdd_val) > 0:
                    ax_gdd.scatter(srow["doy"], gdd_val[0], c=color, s=20, zorder=5)
    if events:
        _draw_event_lines(ax_gdd)
    ax_gdd.set_xlim(GR)
    ax_gdd.set_xticks(MONTH_DOYS)
    ax_gdd.set_xticklabels(MONTH_LABELS, fontsize=6.5)
    ax_gdd.set_ylabel("Cumulative GDD (\u00b0F-days)")
    ax_gdd.set_title("Cumulative GDD (\u00b0F-days)", loc="left")
    ax_gdd.grid(True, alpha=0.3, axis="y")

    # ----- Common x-axis label -----
    fig.text(0.5, 0.02, "Shared Growing Season Timeline", ha="center",
             fontsize=9, fontweight="bold", color="#333")

    # ----- Caption above the top panel (gap maintained) -----
    if caption:
        fig.text(0.5, 0.90, caption, ha="center", fontsize=7.5,
                 style="italic", color="#444", wrap=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]


def generate_storyline(
    grower_slug: str,
    farm_slug: str,
    field_id: str,
    field_dir: Path,
    farm_weather_csv: Path,
    farm_rotation_csv: Path,
    output_dir: Path,
    year: int,
) -> dict:
    ndvi_df = extract_ndvi_scene_metrics(field_dir)
    weather_df = load_weather_for_field(farm_weather_csv, field_id)
    crop_history = load_crop_history(farm_rotation_csv, field_id)
    events = detect_events(ndvi_df, weather_df, year=year)
    coverage = check_coverage(ndvi_df, year)
    crop = crop_history.get(year, "")
    caption = _caption_text(ndvi_df, weather_df, events, crop, year, coverage=coverage)
    farm_name = farm_slug.replace("-", " ").title()

    output_path = output_dir / f"{year}_field_season_storyline.png"
    plot_storyline(ndvi_df, weather_df, crop_history, field_id, farm_name,
                   output_path, year=year, events=events, caption=caption)

    peak_ndvi = ndvi_df[ndvi_df["year"] == year]["ndvi_mean"].max() if not ndvi_df.empty else 0
    total_precip_in = weather_df[weather_df["year"] == year]["PRECTOTCORR_IN"].sum() if not weather_df.empty else 0
    peak_gdd = weather_df[weather_df["year"] == year]["cum_gdd_f"].max() if not weather_df.empty else 0

    return {
        "field_id": field_id,
        "year": year,
        "crop": crop,
        "ndvi_scenes": len(ndvi_df[ndvi_df["year"] == year]) if not ndvi_df.empty else 0,
        "peak_ndvi": round(float(peak_ndvi), 3),
        "total_precip_in": round(float(total_precip_in), 1),
        "peak_gdd_f": round(float(peak_gdd), 0),
        "coverage": coverage,
        "detected_events": len(events),
        "storyline_png": str(output_path),
    }
