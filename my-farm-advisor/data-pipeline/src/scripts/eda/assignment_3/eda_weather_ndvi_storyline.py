#!/usr/bin/env python3
"""
eda_weather_ndvi_storyline.py — Field-Season Weather & NDVI Storyline

Generates a four-panel dashboard for one field and year:
  1. NDVI (mean per Sentinel scene)
  2. Precipitation (daily bars + cumulative line)
  3. Temperature / extremes (daily T2M, T2M_MAX, T2M_MIN)
  4. Cumulative GDD (base 10°C)

Notable-event annotations: heavy rain (>= 25.4 mm), hot days (T2M_MAX >= 35°C),
large NDVI changes (|delta| >= 0.15).

Usage:
  <runtime-python> eda_weather_ndvi_storyline.py \
    --grower-slug ne-grower \
    --farm-slug ne-grower-nebraska \
    --farm-name "Nebraska Farm" \
    --field-slug osm-549149202 \
    --year 2023
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

matplotlib = None
plt = None


def _ensure_imports():
    global matplotlib, plt
    if matplotlib is None:
        import matplotlib as _mpl
        _mpl.use("Agg")
        import matplotlib.pyplot as _plt
        matplotlib = _mpl
        plt = _plt


_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR / "lib"))

from paths import (
    farm_cdl_year_table_path,
    field_reports_dir,
    field_satellite_dir,
    field_weather_path,
)
from runtime_paths import resolve_runtime_paths


_GDD_BASE_C = 10.0
_HEAVY_RAIN_MM = 25.4
_HOT_DAY_C = 35.0
_NDVI_DELTA_THRESHOLD = 0.15
_GROWING_SEASON_START = (3, 1)
_GROWING_SEASON_END = (11, 30)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Field-Season Weather & NDVI Storyline Dashboard"
    )
    parser.add_argument("--grower-slug", required=True)
    parser.add_argument("--farm-slug", required=True)
    parser.add_argument("--farm-name", required=True)
    parser.add_argument("--field-slug", required=True)
    parser.add_argument("--year", type=int, required=True)
    return parser.parse_args(argv)


def read_cdl(grower: str, farm: str, year: int) -> pd.DataFrame:
    path = farm_cdl_year_table_path(grower, farm, year)
    if not path.exists():
        print(f"WARNING: CDL table not found at {path}")
        return pd.DataFrame()
    return pd.read_csv(path)


def dominant_crop(cdl: pd.DataFrame, field_slug: str) -> str:
    if cdl.empty:
        return "Unknown"
    field_data = cdl[cdl["field_id"] == field_slug]
    if field_data.empty:
        field_data = cdl
    top = field_data.loc[field_data["pct"].idxmax()]
    return f"{top['crop_name']} ({top['crop_code']})"


def read_weather(grower: str, farm: str, field: str, year: int) -> pd.DataFrame:
    path = field_weather_path(grower, farm, field)
    if not path.exists():
        print(f"ERROR: Weather file not found at {path}")
        sys.exit(1)
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        print(f"ERROR: No weather data for year {year} at {path}")
        sys.exit(1)
    return df.sort_values("date").reset_index(drop=True)


def compute_gdd(tmax: pd.Series, tmin: pd.Series) -> pd.Series:
    avg = (tmax + tmin) / 2.0
    return np.maximum(0.0, avg - _GDD_BASE_C)


def read_ndvi_scenes(grower: str, farm: str, field: str, year: int) -> pd.DataFrame:
    import rasterio

    sentinel_dir = field_satellite_dir(grower, farm, field) / "sentinel" / str(year)
    if not sentinel_dir.is_dir():
        print(f"WARNING: Sentinel directory not found at {sentinel_dir}")
        return pd.DataFrame(columns=["date", "ndvi"])

    records = []
    scene_pat = re.compile(r"sentinel_(\d{8})$")
    for entry in sorted(sentinel_dir.iterdir()):
        if not entry.is_dir():
            continue
        m = scene_pat.match(entry.name)
        if not m:
            continue
        scene_date = datetime.strptime(m.group(1), "%Y%m%d").date()
        ndvi_path = entry / f"{entry.name}_ndvi.tif"
        if not ndvi_path.exists():
            print(f"WARNING: NDVI TIFF not found for {entry.name}, skipping")
            continue
        with rasterio.open(ndvi_path) as src:
            data = src.read(1).astype(np.float32)
            valid = np.isfinite(data) & (data >= -1.0) & (data <= 1.0)
            if valid.sum() == 0:
                print(f"WARNING: No valid NDVI pixels in {entry.name}, skipping")
                continue
            mean_ndvi = float(data[valid].mean())
            records.append({"date": pd.Timestamp(scene_date), "ndvi": mean_ndvi})

    if not records:
        print(f"WARNING: No valid NDVI scenes found for {field} in {year}")
        return pd.DataFrame(columns=["date", "ndvi"])

    result = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    print(f"  NDVI scenes loaded: {len(result)} dates from {result['date'].min().date()} to {result['date'].max().date()}")
    return result


def detect_events(weather: pd.DataFrame, ndvi: pd.DataFrame) -> dict:
    events = {
        "heavy_rain": weather[weather["PRECTOTCORR"] >= _HEAVY_RAIN_MM].index.tolist(),
        "hot_days": weather[weather["T2M_MAX"] >= _HOT_DAY_C].index.tolist(),
        "ndvi_deltas": [],
    }
    if len(ndvi) >= 2:
        ndvi["delta"] = ndvi["ndvi"].diff().abs()
        large_deltas = ndvi[ndvi["delta"] >= _NDVI_DELTA_THRESHOLD]
        events["ndvi_deltas"] = large_deltas.index.tolist()
    return events


def build_dashboard(
    weather: pd.DataFrame,
    ndvi: pd.DataFrame,
    gdd_cum: np.ndarray,
    events: dict,
    crop_name: str,
    grower: str,
    farm_name: str,
    field: str,
    year: int,
    output_path: Path,
):
    _ensure_imports()
    import matplotlib.dates as mdates

    fig, axes = plt.subplots(4, 1, figsize=(20, 16), sharex=True)
    fig.suptitle(
        f"{farm_name} — Field {field} — {year} Season Storyline",
        fontsize=18,
        fontweight="bold",
        y=0.98,
    )

    dates = weather["date"]
    date_range_str = f"{dates.min().date()} – {dates.max().date()}"

    has_ndvi = not ndvi.empty
    ndvi_dates = ndvi["date"] if has_ndvi else pd.Series(dtype="datetime64[ns]")
    ndvi_values = ndvi["ndvi"] if has_ndvi else pd.Series(dtype="float64")

    # ---- Panel 1: NDVI ----
    ax1 = axes[0]
    if has_ndvi:
        ax1.plot(ndvi_dates, ndvi_values, "go-", markersize=8, linewidth=1.5, label="Mean NDVI")
        for idx in events["ndvi_deltas"]:
            row = ndvi.loc[idx]
            ax1.annotate(
                f"\u0394={row['delta']:.2f}",
                xy=(row["date"], row["ndvi"]),
                xytext=(5, 15),
                textcoords="offset points",
                fontsize=8,
                color="red",
                arrowprops=dict(arrowstyle="->", color="red", lw=0.8),
            )
    else:
        ax1.text(0.5, 0.5, "No NDVI data available", transform=ax1.transAxes,
                 ha="center", va="center", fontsize=14, color="gray")
    ax1.set_ylabel("NDVI", fontsize=12)
    ax1.set_title("Panel 1: Sentinel-2 NDVI", fontsize=13, fontweight="bold")
    ax1.legend(loc="lower right", fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-0.1, 1.05)

    # ---- Panel 2: Precipitation ----
    ax2 = axes[1]
    ax2.bar(dates, weather["PRECTOTCORR"], width=0.8, color="steelblue", alpha=0.7, label="Daily Precip (mm)")
    cum_precip = weather["PRECTOTCORR"].cumsum()
    ax2_cum = ax2.twinx()
    ax2_cum.plot(dates, cum_precip, "b-", linewidth=1.5, alpha=0.8, label="Cumulative (mm)")
    ax2_cum.set_ylabel("Cumulative Precip (mm)", fontsize=10, color="blue")

    for idx in events["heavy_rain"]:
        row = weather.loc[idx]
        ax2.annotate(
            f"{row['PRECTOTCORR']:.0f} mm",
            xy=(row["date"], row["PRECTOTCORR"]),
            xytext=(0, 10),
            textcoords="offset points",
            fontsize=7,
            color="darkred",
            ha="center",
            arrowprops=dict(arrowstyle="->", color="darkred", lw=0.6),
        )

    ax2.set_ylabel("Precipitation (mm)", fontsize=12)
    ax2.set_title("Panel 2: Precipitation", fontsize=13, fontweight="bold")
    ax2.legend(loc="upper left", fontsize=10)
    ax2.grid(True, alpha=0.3)

    # ---- Panel 3: Temperature / Extremes ----
    ax3 = axes[2]
    ax3.plot(dates, weather["T2M"], "k-", linewidth=0.8, alpha=0.6, label="Mean Temp (°C)")
    ax3.plot(dates, weather["T2M_MAX"], "r-", linewidth=1.0, alpha=0.8, label="Max Temp (°C)")
    ax3.plot(dates, weather["T2M_MIN"], "b-", linewidth=1.0, alpha=0.8, label="Min Temp (°C)")
    ax3.axhline(y=_HOT_DAY_C, color="red", linestyle="--", linewidth=0.7, alpha=0.5, label=f"{_HOT_DAY_C}°C")

    for idx in events["hot_days"]:
        row = weather.loc[idx]
        ax3.annotate(
            f"{row['T2M_MAX']:.0f}°C",
            xy=(row["date"], row["T2M_MAX"]),
            xytext=(0, 8),
            textcoords="offset points",
            fontsize=6,
            color="red",
            ha="center",
            arrowprops=dict(arrowstyle="->", color="red", lw=0.5),
        )

    ax3.set_ylabel("Temperature (°C)", fontsize=12)
    ax3.set_title("Panel 3: Temperature / Extremes", fontsize=13, fontweight="bold")
    ax3.legend(loc="upper right", fontsize=9)
    ax3.grid(True, alpha=0.3)

    # ---- Panel 4: Cumulative GDD ----
    ax4 = axes[3]
    ax4.fill_between(dates, 0, gdd_cum, color="orange", alpha=0.4, label="Cumulative GDD")
    ax4.plot(dates, gdd_cum, "orange", linewidth=1.5)
    total_gdd = gdd_cum[-1] if len(gdd_cum) > 0 else 0
    ax4.set_ylabel("Cumulative GDD (base 10°C)", fontsize=12)
    ax4.set_title(f"Panel 4: Cumulative Growing Degree Days (Total: {total_gdd:.0f})", fontsize=13, fontweight="bold")
    ax4.legend(loc="upper left", fontsize=10)
    ax4.grid(True, alpha=0.3)

    # ---- Shared x-axis formatting ----
    ax4.set_xlabel("Date", fontsize=12)
    ax4.xaxis.set_major_locator(mdates.MonthLocator())
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=0, ha="center")

    # ---- Figure caption ----
    n_heavy = len(events["heavy_rain"])
    n_hot = len(events["hot_days"])
    caption = (
        f"Crop: {crop_name}  |  "
        f"Period: {date_range_str}  |  "
        f"Heavy rain days (\u2265{_HEAVY_RAIN_MM} mm): {n_heavy}  |  "
        f"Hot days (\u2265{_HOT_DAY_C}°C): {n_hot}  |  "
        f"Growing degree days (base {_GDD_BASE_C}°C): {total_gdd:.0f}"
    )
    fig.text(0.5, 0.01, caption, ha="center", fontsize=10, style="italic", color="gray")

    plt.tight_layout(rect=[0, 0.04, 1, 0.95])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard saved: {output_path}")


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    print("=" * 60)
    print("Field-Season Weather & NDVI Storyline")
    print("=" * 60)
    print(f"  Grower: {args.grower_slug}")
    print(f"  Farm:   {args.farm_slug} ({args.farm_name})")
    print(f"  Field:  {args.field_slug}")
    print(f"  Year:   {args.year}")
    print()

    cdl = read_cdl(args.grower_slug, args.farm_slug, args.year)
    crop_name = dominant_crop(cdl, args.field_slug)
    print(f"  Dominant crop: {crop_name}")
    print()

    weather = read_weather(args.grower_slug, args.farm_slug, args.field_slug, args.year)
    print(f"  Weather records: {len(weather)} days")
    print(f"  Date range: {weather['date'].min().date()} to {weather['date'].max().date()}")
    print()

    gdd_daily = compute_gdd(weather["T2M_MAX"], weather["T2M_MIN"])
    gdd_cumulative = gdd_daily.cumsum().values
    print(f"  GDD total (base {_GDD_BASE_C}°C): {gdd_cumulative[-1]:.0f}")
    print()

    ndvi = read_ndvi_scenes(args.grower_slug, args.farm_slug, args.field_slug, args.year)
    print()

    events = detect_events(weather, ndvi)
    print(f"  Heavy rain days (\u2265{_HEAVY_RAIN_MM} mm): {len(events['heavy_rain'])}")
    print(f"  Hot days (\u2265{_HOT_DAY_C}°C): {len(events['hot_days'])}")
    print(f"  Large NDVI changes (\u2265{_NDVI_DELTA_THRESHOLD}): {len(events['ndvi_deltas'])}")
    print()

    output_path = (
        field_reports_dir(args.grower_slug, args.farm_slug, args.field_slug)
        / f"{args.field_slug}_{args.year}_storyline.png"
    )

    build_dashboard(
        weather=weather,
        ndvi=ndvi,
        gdd_cum=gdd_cumulative,
        events=events,
        crop_name=crop_name,
        grower=args.grower_slug,
        farm_name=args.farm_name,
        field=args.field_slug,
        year=args.year,
        output_path=output_path,
    )

    print("Done.")


if __name__ == "__main__":
    main()
