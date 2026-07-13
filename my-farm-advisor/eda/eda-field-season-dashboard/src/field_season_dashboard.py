#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask

matplotlib.use("Agg")

SOYBEAN_GDD_THRESHOLDS = {
    "VE Emergence": 125,
    "R1 Flowering": 800,
    "R5 Seed Fill": 1400,
    "R7 Maturity": 2200,
}
GDD_BASE = 10.0
GDD_CAP = 30.0
HEAVY_RAIN_PCTILE = 95
HOT_DAY_C = 32
COOL_PERIOD_C = 20
NDVI_GREENING_THRESHOLD = 0.15
NDVI_SENESCENCE_THRESHOLD = 0.1


def _resolve_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    return (Path(raw) / "data-pipeline") if raw else Path.home() / "my-farm-advisor-runtime" / "data-pipeline"


def _resolve_dominant_crop(comp: pd.DataFrame, field_id: str, year: int) -> str:
    row = comp[(comp["field_id"] == field_id) & (comp["year"] == year)]
    if row.empty:
        raise ValueError(f"No CDL record for {field_id}/{year}")
    dominant = row.loc[row["pct"].idxmax()]
    return str(dominant["crop_name"])


import geopandas as gpd


def _load_boundary_geom(boundary_path: Path):
    gdf = gpd.read_file(str(boundary_path))
    return gdf.to_crs("EPSG:4326").geometry.iloc[0]


def _extract_ndvi_time_series(data_root: Path, grower: str, farm: str, field_id: str, year: int) -> list[dict]:
    manifest_path = data_root / "growers" / grower / "farms" / farm / "fields" / field_id / "satellite" / "sentinel" / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text())
    year_data = None
    for yr in manifest.get("years", []):
        if yr.get("year") == year:
            year_data = yr
            break
    if not year_data:
        return []

    boundary_path = data_root / "growers" / grower / "farms" / farm / "fields" / field_id / "boundary" / "field_boundary.geojson"
    boundary_geom = _load_boundary_geom(boundary_path)
    boundary_geom_geojson = [boundary_geom.__geo_interface__]

    results = []
    for scene in year_data.get("scenes", []):
        ndvi_rel = scene.get("ndvi_tif", "")
        if not ndvi_rel:
            continue
        ndvi_path = (data_root / ndvi_rel) if not Path(ndvi_rel).is_absolute() else Path(ndvi_rel)
        if not ndvi_path.exists():
            continue
        try:
            with rasterio.open(str(ndvi_path)) as ndvi_src:
                ndvi_crs = ndvi_src.crs
                if ndvi_crs:
                    geom_proj = gpd.GeoSeries([boundary_geom], crs="EPSG:4326").to_crs(ndvi_crs).iloc[0]
                else:
                    geom_proj = boundary_geom
                masked, _ = rio_mask(ndvi_src, [geom_proj.__geo_interface__], crop=True, nodata=ndvi_src.nodata)
                valid = masked[~np.isnan(masked) & (masked != (ndvi_src.nodata if ndvi_src.nodata else -9999))]
                if valid.size == 0:
                    continue
                mean_ndvi = float(np.mean(valid))
        except Exception:
            continue
        results.append({
            "date": scene["scene_date"],
            "mean_ndvi": mean_ndvi,
            "cloud_cover": scene.get("cloud_cover", 0),
        })
    return sorted(results, key=lambda x: x["date"])


def _load_weather(data_root: Path, grower: str, farm: str, field_id: str, year: int) -> pd.DataFrame:
    path = data_root / "growers" / grower / "farms" / farm / "fields" / field_id / "weather" / "daily_weather.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    return df.sort_values("date").reset_index(drop=True)


def _load_cdl(data_root: Path, grower: str, farm: str) -> pd.DataFrame:
    prefix = grower.replace("-", "_") + "_" + farm[len(grower) + 1:]
    path = data_root / "growers" / grower / "farms" / farm / "derived" / "tables" / f"{prefix}_cdl_2021_2025_full_composition.csv"
    return pd.read_csv(path)


def _compute_daily_metrics(weather: pd.DataFrame) -> pd.DataFrame:
    df = weather.copy()
    tmax_capped = df["T2M_MAX"].clip(upper=GDD_CAP)
    tmin_floored = df["T2M_MIN"].clip(lower=GDD_BASE)
    daily_gdd = ((tmax_capped + tmin_floored) / 2.0) - GDD_BASE
    df["daily_gdd"] = daily_gdd.clip(lower=0.0)
    df["cumulative_gdd"] = df["daily_gdd"].cumsum()
    heavy_thresh = df[df["PRECTOTCORR"] > 0]["PRECTOTCORR"].quantile(HEAVY_RAIN_PCTILE / 100)
    df["heavy_rain"] = df["PRECTOTCORR"] > heavy_thresh
    df["hot_day"] = df["T2M_MAX"] > HOT_DAY_C
    df["cool_day"] = (df["T2M_MAX"] < COOL_PERIOD_C) & (df["date"].dt.month.between(5, 9))
    return df


def _detect_events(ndvi_series: list[dict], weather: pd.DataFrame) -> list[dict]:
    events = []

    # NDVI events
    if len(ndvi_series) >= 2:
        for i in range(1, len(ndvi_series)):
            prev, cur = ndvi_series[i - 1], ndvi_series[i]
            diff = cur["mean_ndvi"] - prev["mean_ndvi"]
            if diff >= NDVI_GREENING_THRESHOLD:
                events.append({
                    "panel": "ndvi", "date": cur["date"], "label": f"Rapid greening\n+{diff:.2f} NDVI",
                    "color": "#2ca02c", "arrow": True,
                })
        peak = max(ndvi_series, key=lambda x: x["mean_ndvi"])
        events.append({
            "panel": "ndvi", "date": peak["date"],
            "label": f"Peak NDVI\n{peak['mean_ndvi']:.2f}",
            "color": "#d62728", "arrow": False,
        })
        peak_idx = ndvi_series.index(peak)
        for i in range(peak_idx + 1, len(ndvi_series)):
            if peak["mean_ndvi"] - ndvi_series[i]["mean_ndvi"] >= NDVI_SENESCENCE_THRESHOLD:
                events.append({
                    "panel": "ndvi", "date": ndvi_series[i]["date"],
                    "label": "Senescence\nbegins",
                    "color": "#ff7f0e", "arrow": True,
                })
                break

    # Heavy rain events
    heavy = weather[weather["heavy_rain"]]
    if not heavy.empty:
        top = heavy.nlargest(1, "PRECTOTCORR").iloc[0]
        events.append({
            "panel": "precip", "date": top["date"].strftime("%Y-%m-%d"),
            "label": f"Heavy rain\n{top['PRECTOTCORR']:.0f}mm",
            "color": "#1f77b4", "arrow": False,
        })

    # Hot day
    hot = weather[weather["hot_day"]]
    if not hot.empty:
        hottest = hot.nlargest(1, "T2M_MAX").iloc[0]
        events.append({
            "panel": "temp", "date": hottest["date"].strftime("%Y-%m-%d"),
            "label": f"Hottest day\n{hottest['T2M_MAX']:.0f}°C",
            "color": "#d62728", "arrow": False,
        })

    # Cool spell
    cool = weather[weather["cool_day"]]
    if not cool.empty:
        coldest = cool.nsmallest(1, "T2M_MAX").iloc[0]
        events.append({
            "panel": "temp", "date": coldest["date"].strftime("%Y-%m-%d"),
            "label": f"Cool spell\n{coldest['T2M_MAX']:.0f}°C max",
            "color": "#1f77b4", "arrow": False,
        })

    return events


def _build_dashboard(
    ndvi_series: list[dict], weather: pd.DataFrame, events: list[dict],
    field_id: str, year: int, crop: str, output_dir: Path, data_root: Path,
) -> None:
    dates_w = pd.to_datetime(weather["date"].values)
    precip = weather["PRECTOTCORR"].values
    tmin = weather["T2M_MIN"].values
    tmax = weather["T2M_MAX"].values
    tmean = weather["T2M"].values
    cum_gdd = weather["cumulative_gdd"].values

    ndvi_dates = [pd.Timestamp(e["date"]).to_pydatetime() for e in ndvi_series]
    ndvi_vals = [e["mean_ndvi"] for e in ndvi_series]

    fig, axes = plt.subplots(4, 1, figsize=(14, 13), sharex=True,
                             gridspec_kw={"hspace": 0.08, "height_ratios": [1.2, 1, 1, 1]})

    colors = {"ndvi": "#2ca02c", "precip": "#1f77b4", "temp_fill": "#ffb07c",
              "temp_line": "#d62728", "gdd": "#9467bd"}

    ax_ndvi = axes[0]
    ax_ndvi.scatter(ndvi_dates, ndvi_vals, color=colors["ndvi"], s=40, zorder=5, label="Mean NDVI")
    ax_ndvi.plot(ndvi_dates, ndvi_vals, color=colors["ndvi"], linewidth=1.5, alpha=0.7)
    ax_ndvi.set_ylabel("NDVI", fontsize=11)
    ax_ndvi.set_ylim(-0.05, 1.05)
    ax_ndvi.axhline(0, color="gray", linewidth=0.5, alpha=0.5)
    ax_ndvi.set_title(f"{field_id} — {year} {crop} Season Dashboard", fontsize=14, fontweight="bold")
    ax_ndvi.legend(loc="upper left", fontsize=8)

    ax_precip = axes[1]
    ax_precip.bar(dates_w, precip, width=0.8, color=colors["precip"], alpha=0.7, label="Daily precip")
    heavy = weather[weather["heavy_rain"]]
    if not heavy.empty:
        ax_precip.bar(heavy["date"].values, heavy["PRECTOTCORR"].values, width=0.8,
                      color="#d62728", alpha=0.8, label="Heavy rain")
    ax_precip.set_ylabel("Precip (mm)", fontsize=11)
    ax_precip.legend(loc="upper left", fontsize=8)

    ax_temp = axes[2]
    ax_temp.fill_between(dates_w, tmin, tmax, color=colors["temp_fill"], alpha=0.3, label="Min–Max range")
    ax_temp.plot(dates_w, tmean, color=colors["temp_line"], linewidth=1.2, label="Mean temp")
    ax_temp.axhline(GDD_BASE, color="green", linewidth=0.7, linestyle="--", alpha=0.5)
    ax_temp.axhline(GDD_CAP, color="red", linewidth=0.7, linestyle="--", alpha=0.5)
    ax_temp.set_ylabel("Temp (°C)", fontsize=11)
    ax_temp.legend(loc="upper left", fontsize=8)
    ax_temp.set_ylim(min(tmin) - 5, max(tmax) + 5)

    ax_gdd = axes[3]
    ax_gdd.plot(dates_w, cum_gdd, color=colors["gdd"], linewidth=2, label="Cumulative GDD")
    gdd_start = cum_gdd[weather["date"].dt.month >= 4].min() if any(weather["date"].dt.month >= 4) else 0
    for stage, gdd_val in sorted(SOYBEAN_GDD_THRESHOLDS.items(), key=lambda x: x[1]):
        cross_idx = np.searchsorted(cum_gdd, gdd_val)
        if cross_idx < len(cum_gdd):
            cross_date = pd.Timestamp(dates_w[cross_idx])
            ax_gdd.axhline(gdd_val, color="gray", linewidth=0.5, linestyle=":", alpha=0.3)
            ax_gdd.text(cross_date, gdd_val, f"  {stage} ~{cross_date.strftime('%b %d')}",
                       fontsize=8, color="#555", va="center", ha="left", fontweight="bold")
    ax_gdd.set_ylabel("Cumul. GDD (base 10°C)", fontsize=11)
    ax_gdd.set_xlabel("Date (2023)", fontsize=11)
    ax_gdd.legend(loc="upper left", fontsize=8)

    for ax in axes:
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=9)

    from collections import defaultdict

    ndvi_lookup = {e["date"]: e["mean_ndvi"] for e in ndvi_series}
    ndvi_ev = [(idx, e) for idx, e in enumerate(events) if e["panel"] == "ndvi"]
    ndvi_ypos: dict[int, float] = {}
    ndvi_below: set[int] = set()
    if ndvi_ev:
        ndvi_sorted = sorted(ndvi_ev, key=lambda x: x[1]["date"])
        groups: list[list[tuple[int, dict]]] = []
        cur = [ndvi_sorted[0]]
        for item in ndvi_sorted[1:]:
            gap = abs(pd.Timestamp(item[1]["date"]) - pd.Timestamp(cur[-1][1]["date"]))
            if gap <= pd.Timedelta(days=30):
                cur.append(item)
            else:
                groups.append(cur)
                cur = [item]
        groups.append(cur)
        ndvi_y_range = ax_ndvi.get_ylim()[1] - ax_ndvi.get_ylim()[0]
        ndvi_offset = 0.14 * ndvi_y_range
        MAX_NDVI_LABEL = 0.95
        for group in groups:
            n = len(group)
            max_anchor = max(ndvi_lookup.get(gev["date"], 0) for _, gev in group)
            top = min(MAX_NDVI_LABEL, max_anchor + n * ndvi_offset)
            for gi, (gidx, gev) in enumerate(group):
                label = gev.get("label", "")
                extra = 1 if "Peak" in label else 0
                y_pos = top - (gi + extra) * ndvi_offset
                anchor_y = ndvi_lookup.get(gev["date"], 0)
                if "Peak" in label:
                    y_pos = max(y_pos, anchor_y - 0.05)
                else:
                    y_pos = max(y_pos, anchor_y + 0.02)
                y_pos = min(y_pos, MAX_NDVI_LABEL)
                ndvi_ypos[gidx] = y_pos
                if y_pos < anchor_y:
                    ndvi_below.add(gidx)

    stack_counts: dict[str, int] = defaultdict(int)

    for ev_idx, ev in enumerate(events):
        ev_date = pd.Timestamp(ev["date"]).to_pydatetime()
        panel_map = {"ndvi": ax_ndvi, "precip": ax_precip, "temp": ax_temp, "gdd": ax_gdd}
        ax = panel_map.get(ev["panel"])
        if ax is None:
            continue

        ls = ":" if "Peak" in ev.get("label", "") else "--"
        ax.axvline(ev_date, color=ev["color"], linewidth=1.2, linestyle=ls, alpha=0.6)

        ndvi_va_below = ev["panel"] == "ndvi" and ev_idx in ndvi_below
        if ev["panel"] == "ndvi" and ev_idx in ndvi_ypos:
            y_pos = ndvi_ypos[ev_idx]
        else:
            stack_idx = stack_counts[ev["panel"]]
            stack_counts[ev["panel"]] += 1
            y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
            base_y = ax.get_ylim()[1] * 0.92
            y_pos = base_y - stack_idx * 0.07 * y_range

        va = "top" if ndvi_va_below else "center"
        ax.annotate(ev["label"], xy=(ev_date, y_pos), fontsize=7.5, color=ev["color"],
                   ha="center", va=va, fontweight="bold",
                   bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=ev["color"], alpha=0.8))

    ax_gdd.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_gdd.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    plt.setp(ax_gdd.xaxis.get_majorticklabels(), rotation=0, ha="center")

    fig.align_ylabels(axes)
    out_path = output_dir / f"{field_id}_{year}_season_dashboard.png"
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close()
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Field-season dashboard for one field and one growing season")
    parser.add_argument("--grower-slug", default=None)
    parser.add_argument("--farm-slug", default=None)
    parser.add_argument("--field-id", default="osm-1360316062")
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    data_root = Path(args.data_root) if args.data_root else _resolve_root()
    output_dir = Path(args.output_dir) if args.output_dir else data_root / "eda" / "season-dashboard" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    grower = args.grower_slug or "ia-grower"
    farm = args.farm_slug or "ia-grower-iowa"
    field_id = args.field_id
    year = args.year

    print(f"Field-season dashboard: {field_id}, {year}")
    print(f"Grower: {grower}, Farm: {farm}")
    print(f"Output: {output_dir}")
    print()

    print("[1/5] Loading CDL data...")
    cdl = _load_cdl(data_root, grower, farm)
    crop = _resolve_dominant_crop(cdl, field_id, year)
    print(f"  CDL crop for {field_id} / {year}: {crop}")
    print()

    print("[2/5] Loading weather data...")
    weather = _load_weather(data_root, grower, farm, field_id, year)
    print(f"  {len(weather)} daily records ({weather['date'].min().date()} to {weather['date'].max().date()})")
    print()

    print("[3/5] Extracting Sentinel NDVI time series...")
    ndvi_series = _extract_ndvi_time_series(data_root, grower, farm, field_id, year)
    print(f"  {len(ndvi_series)} valid scenes")
    for ns in ndvi_series:
        print(f"    {ns['date']}: NDVI={ns['mean_ndvi']:.3f} (cloud={ns['cloud_cover']:.1f}%)")
    print()

    print("[4/5] Computing metrics and detecting events...")
    weather = _compute_daily_metrics(weather)
    events = _detect_events(ndvi_series, weather)
    print(f"  {len(events)} notable events detected:")
    for ev in events:
        print(f"    {ev['panel'].upper()}: {ev['date']} — {ev['label'].replace(chr(10), ' ')}")
    print()

    print("[5/5] Building dashboard...")
    out_path = _build_dashboard(ndvi_series, weather, events, field_id, year, crop, output_dir, data_root)
    print(f"  Dashboard saved: {out_path}")


if __name__ == "__main__":
    main()
