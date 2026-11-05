#!/usr/bin/env python3
"""Field-level weather charts from the cached daily POWER records.

Emits three report-grade PNGs per field so each component can stand on its
own (README grids, PDFs, dashboards) instead of only living inside the
one-page poster:

  weather_daily_temperature.png   — daily mean temperature per season with
                                    frost windows computed from the same file
  weather_gdd.png                 — cumulative GDD (base 10, mean method)
                                    per year + per-season totals
  weather_monthly_precipitation.png — month-by-month precipitation for the
                                    last two complete years

Every title states the year range present in the data (never hard-coded),
and every number is recomputable from the cached CSV.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_SRC = pathlib.Path(__file__).resolve()
_SCRIPTS = _SRC.parents[1]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

from paths import field_weather_dir  # noqa: E402


def _load(field: str) -> pd.DataFrame:
    df = pd.read_csv(field_weather_dir(_GROWER, _FARM, field) / "daily_weather.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["doy"] = df["date"].dt.dayofyear
    return df.sort_values("date")


def _frost_windows(df: pd.DataFrame) -> tuple[float, float]:
    """Median last spring freeze DOY and first autumn freeze DOY."""
    last_spring, first_fall = [], []
    for _, g in df.groupby("year"):
        frozen = g[g["T2M_MIN"] <= 0]
        if frozen.empty:
            continue
        spring = frozen[frozen["doy"] <= 182]
        autumn = frozen[frozen["doy"] > 182]
        if not spring.empty:
            last_spring.append(spring["doy"].max())
        if not autumn.empty:
            first_fall.append(autumn["doy"].min())
    return (float(np.median(last_spring)) if last_spring else np.nan,
            float(np.median(first_fall)) if first_fall else np.nan)


def chart_temperature(df: pd.DataFrame, out: pathlib.Path) -> None:
    years = sorted(df["year"].unique())
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for year in years:
        g = df[df["year"] == year].sort_values("doy")
        ax.plot(g["doy"], g["T2M"], lw=0.6, alpha=0.38)
        roll = g["T2M"].rolling(7, min_periods=1).mean()
        ax.plot(g["doy"], roll, lw=1.8, label=str(year))
    lsf, fff = _frost_windows(df)
    if not np.isnan(lsf):
        ax.axvline(lsf, color="tab:red", ls="--", lw=1)
        ax.text(lsf + 2, ax.get_ylim()[1] * 0.92, f"last spring frost DOY {lsf:.0f}",
                fontsize=8, color="tab:red")
    if not np.isnan(fff):
        ax.axvline(fff, color="tab:blue", ls="--", lw=1)
        ax.text(fff + 2, ax.get_ylim()[1] * 0.92, f"first autumn frost DOY {fff:.0f}",
                fontsize=8, color="tab:blue")
    ax.set_title(
        f"Daily mean temperature {years[0]}–{years[-1]} with frost windows\n"
        f"(thin: raw daily; bold: 7-day mean; NASA POWER field record)"
    )
    ax.set_xlabel("Day of year")
    ax.set_ylabel("T2M °C")
    ax.legend(ncol=len(years), fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _gdd(row) -> float:
    tmean = (row["T2M_MAX"] + row["T2M_MIN"]) / 2.0
    return max(0.0, tmean - 10.0)


def chart_gdd(df: pd.DataFrame, out: pathlib.Path) -> None:
    years = sorted(df["year"].unique())
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), width_ratios=[2.1, 1])
    totals = {}
    for year in years:
        g = df[df["year"] == year].sort_values("doy")
        gdd = g.apply(_gdd, axis=1).cumsum()
        totals[year] = float(gdd.iloc[-1])
        ax.plot(g["doy"], gdd, lw=1.6, label=str(year))
    ax.set_title(
        f"Cumulative GDD (base 10 °C, mean method) {years[0]}–{years[-1]}\n"
        "from the cached daily POWER record"
    )
    ax.set_xlabel("Day of year")
    ax.set_ylabel("GDD (°C-day)")
    ax.legend(fontsize=8)
    ys = sorted(totals)
    ax2.bar([str(y) for y in ys], [totals[y] for y in ys], color="tab:green", alpha=0.75)
    ax2.set_title("Season totals")
    ax2.set_ylabel("GDD")
    ax2.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def chart_precip(df: pd.DataFrame, out: pathlib.Path) -> None:
    complete = [y for y in sorted(df["year"].unique())
                if len(df[df["year"] == y]) >= 360]
    pick = complete[-2:] if len(complete) >= 2 else sorted(df["year"].unique())[-2:]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    months = np.arange(1, 13)
    width = 0.38
    for i, year in enumerate(pick):
        g = df[df["year"] == year].copy()
        g["m"] = g["date"].dt.month
        totals = g.groupby("m")["PRECTOTCORR"].sum()
        vals = [float(totals.get(m, 0.0)) for m in months]
        ax.bar(months + (i - 0.5) * width, vals, width, label=str(year),
               color=["tab:blue", "tab:cyan"][i % 2], alpha=0.8)
    ax.set_title(
        f"Monthly precipitation, {' vs '.join(str(y) for y in pick)} — "
        "every bar recomputable from the daily CSV"
    )
    ax.set_xlabel("Month")
    ax.set_xticks(months)
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J",
                        "J", "A", "S", "O", "N", "D"])
    ax.set_ylabel("mm")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> None:
    global _GROWER, _FARM
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grower", default=os.environ.get("AG_GROWER_SLUG", ""))
    parser.add_argument("--farm", default=os.environ.get("AG_FARM_SLUG", ""))
    parser.add_argument("--field", required=True)
    parser.add_argument("--out", type=pathlib.Path, default=None,
                        help="defaults to the field's derived/reports/")
    args = parser.parse_args()
    _GROWER, _FARM = args.grower, args.farm
    if not _GROWER or not _FARM:
        raise SystemExit("--grower/--farm or AG_GROWER_SLUG/AG_FARM_SLUG required")
    df = _load(args.field)
    out = args.out
    if out is None:
        out = field_weather_dir(_GROWER, _FARM, args.field).parent / "derived" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    chart_temperature(df, out / "weather_daily_temperature.png")
    chart_gdd(df, out / "weather_gdd.png")
    chart_precip(df, out / "weather_monthly_precipitation.png")
    print(f"weather charts -> {out} (years {sorted(df['year'].unique())})")


if __name__ == "__main__":
    main()
