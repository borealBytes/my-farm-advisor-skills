from __future__ import annotations

import base64
import json
import os
import warnings
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
warnings.filterwarnings("ignore", category=UserWarning, module="rasterio")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

try:
    import geopandas as gpd
    import rasterio
    from rasterio.mask import mask as rio_mask
except ImportError as exc:
    raise ImportError(
        "Missing geospatial dependencies. Run from the data-pipeline .venv:\n"
        f"  {Path(os.environ.get('DATA_PIPELINE_VENV_DIR', '')) / 'bin' / 'python'} ..."
    ) from exc

try:
    from . import (
        CROP_STAGES,
        GDD_BASE_TEMP,
        GDD_CAP_TEMP,
        GDD_START_DOY,
        HEAVY_RAIN_THRESHOLD_MM,
        HOT_DAY_THRESHOLD_C,
        MAX_CLOUD_COVER_PCT,
        NDVI_SURGE_DELTA,
        WARNING_LEVELS,
    )
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from __init__ import (  # type: ignore[import-unused]
        CROP_STAGES,
        GDD_BASE_TEMP,
        GDD_CAP_TEMP,
        GDD_START_DOY,
        HEAVY_RAIN_THRESHOLD_MM,
        HOT_DAY_THRESHOLD_C,
        MAX_CLOUD_COVER_PCT,
        NDVI_SURGE_DELTA,
        WARNING_LEVELS,
    )

_PANEL_HEIGHTS = [1.0, 0.7, 0.7, 0.7]
_FIG_WIDTH = 10
_FIG_HEIGHT = 8.0
_DOY_MIN = 60
_DOY_MAX = 335
_COLORS = {
    "ndvi_marker": "#22c55e",
    "ndvi_line": "#16a34a",
    "ndvi_surge": "#7c3aed",
    "ndvi_dip": "#ef4444",
    "precip": "#3b82f6",
    "precip_heavy": "#1d4ed8",
    "temp_max": "#ef4444",
    "temp_min": "#3b82f6",
    "temp_ribbon": "#e2e8f0",
    "temp_mean": "#64748b",
    "gdd": "#f59e0b",
    "gdd_stage": "#94a3b8",
    "gdd_stage_label": "#475569",
}
_FONT = "DejaVu Sans"


def _resolve_data_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not raw:
        raise ValueError(
            "DATA_PIPELINE_DATA_ROOT is required. "
            "Export it before running, e.g.:\n"
            "  export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime"
        )
    return Path(raw).expanduser().resolve()


def _field_root(data_root: Path, grower: str, farm: str, field: str) -> Path:
    return data_root / "data-pipeline" / "growers" / grower / "farms" / farm / "fields" / field


def _read_crop_info(field_root: Path, year: int) -> dict[str, Any]:
    join_csv = field_root / "derived" / "tables" / "ndvi_year_crop_join.csv"
    if not join_csv.exists():
        return {"crop_name": "Unknown", "error": f"ndvi_year_crop_join.csv not found at {join_csv}"}
    df = pd.read_csv(join_csv)
    if df.empty:
        return {"crop_name": "Unknown", "error": "ndvi_year_crop_join.csv is empty"}
    row = df[df["year"] == year]
    if row.empty:
        available = sorted(df["year"].unique().tolist())
        return {
            "crop_name": "Unknown",
            "error": f"No crop entry for year {year}. Available: {available}",
        }
    return {"crop_name": str(row.iloc[0]["crop_name"]), "error": None}


def _read_boundary(field_root: Path) -> gpd.GeoDataFrame | None:
    path = field_root / "boundary" / "field_boundary.geojson"
    if not path.exists():
        return None
    try:
        return gpd.read_file(path)
    except Exception:
        return None


def _check_data_quality(
    field_root: Path,
    year: int,
    ndvi_scenes: list[dict[str, Any]],
    weather_df: pd.DataFrame | None,
) -> list[dict[str, str]]:
    warnings_list: list[dict[str, str]] = []

    if len(ndvi_scenes) < 2:
        warnings_list.append({
            "level": "warning",
            "message": f"Only {len(ndvi_scenes)} Sentinel scene(s) available for {year}. "
            "NDVI time series will be limited.",
        })
    cloud_excluded = sum(1 for s in ndvi_scenes if s.get("excluded", False))
    if cloud_excluded:
        warnings_list.append({
            "level": "info",
            "message": f"{cloud_excluded} scene(s) excluded due to cloud cover > {MAX_CLOUD_COVER_PCT:.0f}%.",
        })

    if weather_df is not None and not weather_df.empty:
        mar_nov = weather_df[
            (weather_df["date"].dt.month >= 3) & (weather_df["date"].dt.month <= 11)
        ]
        expected_days = (date(year, 11, 30) - date(year, 3, 1)).days + 1
        actual_days = len(mar_nov)
        gap_pct = (expected_days - actual_days) / expected_days * 100
        if gap_pct > 10:
            warnings_list.append({
                "level": "warning",
                "message": (
                    f"Sparse weather data in Mar–Nov: {actual_days}/{expected_days} days "
                    f"({gap_pct:.0f}% missing)."
                ),
            })
        elif gap_pct > 0:
            warnings_list.append({
                "level": "info",
                "message": (
                    f"Minor weather gaps: {actual_days}/{expected_days} days present "
                    f"({gap_pct:.0f}% missing)."
                ),
            })

    join_csv = field_root / "derived" / "tables" / "ndvi_year_crop_join.csv"
    if not join_csv.exists():
        warnings_list.append({
            "level": "error",
            "message": f"CDL crop join table not found at {join_csv}.",
        })

    manifest = field_root / "satellite" / "sentinel" / "manifest.json"
    if not manifest.exists():
        warnings_list.append({
            "level": "error",
            "message": "Sentinel manifest.json not found.",
        })

    boundary = field_root / "boundary" / "field_boundary.geojson"
    if not boundary.exists():
        warnings_list.append({
            "level": "error",
            "message": "Field boundary not found.",
        })

    return warnings_list


def _collect_sentinel_scenes(
    field_root: Path, year: int, data_root: Path
) -> list[dict[str, Any]]:
    manifest = field_root / "satellite" / "sentinel" / "manifest.json"
    if not manifest.exists():
        return []

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    year_entry = None
    for entry in data.get("years", []):
        if int(entry.get("year", 0)) == year:
            year_entry = entry
            break
    if not year_entry:
        return []

    scenes: list[dict[str, Any]] = []
    boundary = _read_boundary(field_root)
    if boundary is None:
        return []

    boundary_proj_cache: dict[str, Any] = {}

    for scene in year_entry.get("scenes", []):
        ndvi_rel = scene.get("ndvi_tif")
        if not ndvi_rel:
            continue
        ndvi_path = data_root / "data-pipeline" / ndvi_rel
        if not ndvi_path.exists():
            continue
        scene_date_str = scene.get("scene_date", "")
        cloud_cover = float(scene.get("cloud_cover", 0))
        excluded = cloud_cover > MAX_CLOUD_COVER_PCT
        mean_ndvi = None
        if not excluded:
            mean_ndvi = _compute_scene_mean_ndvi(ndvi_path, boundary, boundary_proj_cache)
        scenes.append({
            "date": scene_date_str,
            "cloud_cover": cloud_cover,
            "mean_ndvi": mean_ndvi,
            "excluded": excluded,
            "ndvi_path": str(ndvi_path),
        })
    return scenes


def _compute_scene_mean_ndvi(
    ndvi_path: Path,
    boundary: gpd.GeoDataFrame,
    proj_cache: dict[str, Any],
) -> float | None:
    cache_key = str(ndvi_path)
    if cache_key in proj_cache:
        return proj_cache[cache_key]
    try:
        with rasterio.open(ndvi_path) as src:
            boundary_proj = boundary.to_crs(src.crs)
            out_image, _ = rio_mask(src, boundary_proj.geometry, crop=True, filled=False)
        array = np.ma.filled(out_image[0], np.nan).astype(float)
        valid = array[np.isfinite(array)]
        if valid.size == 0:
            proj_cache[cache_key] = None
            return None
        mean_val = float(np.nanmean(valid))
        proj_cache[cache_key] = mean_val
        return mean_val
    except Exception:
        proj_cache[cache_key] = None
        return None


def _load_weather_for_year(field_root: Path, year: int) -> pd.DataFrame | None:
    wth_path = field_root / "weather" / "daily_weather.csv"
    if not wth_path.exists():
        return None
    try:
        df = pd.read_csv(wth_path, parse_dates=["date"])
    except Exception:
        return None
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _compute_gdd(weather_df: pd.DataFrame) -> pd.Series:
    tmax = weather_df["T2M_MAX"].values
    tmin = weather_df["T2M_MIN"].values
    daily_gdd = np.clip((tmax + tmin) / 2.0 - GDD_BASE_TEMP, 0, GDD_CAP_TEMP - GDD_BASE_TEMP)
    cumulative = np.cumsum(daily_gdd)
    return pd.Series(cumulative, index=weather_df.index, name="cumulative_gdd")


def _detect_heavy_rain(weather_df: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    heavy = weather_df[weather_df["PRECTOTCORR"] >= HEAVY_RAIN_THRESHOLD_MM]
    for _, row in heavy.iterrows():
        events.append({
            "date": row["date"],
            "doy": row["date"].dayofyear,
            "label": "Heavy Rain",
            "value": round(float(row["PRECTOTCORR"]), 1),
            "detail": f"{row['PRECTOTCORR']:.0f} mm",
            "color": _COLORS["precip_heavy"],
            "icon": "\u2602",
        })
    return events


def _detect_hot_days(weather_df: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    hot = weather_df[weather_df["T2M_MAX"] >= HOT_DAY_THRESHOLD_C]
    for _, row in hot.iterrows():
        events.append({
            "date": row["date"],
            "doy": row["date"].dayofyear,
            "label": "Hot Day",
            "value": round(float(row["T2M_MAX"]), 1),
            "detail": f"{row['T2M_MAX']:.0f}\u00b0C max",
            "color": "#ef4444",
            "icon": "\u2600",
        })
    return events


def _detect_cool_periods(weather_df: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if weather_df.empty:
        return events
    tmin_10th = weather_df["T2M_MIN"].quantile(0.10)
    below_mask = (weather_df["T2M_MIN"] < tmin_10th) | (weather_df["T2M_MIN"] < 0)
    consecutive: list[pd.Timestamp] = []
    for idx, row in weather_df.iterrows():
        if below_mask.loc[idx]:
            consecutive.append(row["date"])
        else:
            if len(consecutive) >= 3:
                events.append({
                    "date": consecutive[0],
                    "doy": consecutive[0].dayofyear,
                    "label": "Cool Period",
                    "value": len(consecutive),
                    "detail": f"{len(consecutive)} days",
                    "color": "#3b82f6",
                    "icon": "\u2744",
                    "end_date": consecutive[-1],
                })
            consecutive = []
    if len(consecutive) >= 3:
        events.append({
            "date": consecutive[0],
            "doy": consecutive[0].dayofyear,
            "label": "Cool Period",
            "value": len(consecutive),
            "detail": f"{len(consecutive)} days",
            "color": "#3b82f6",
            "icon": "\u2744",
            "end_date": consecutive[-1],
        })
    return events


def _detect_ndvi_events(ndvi_df: pd.DataFrame) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if ndvi_df.empty or len(ndvi_df) < 3:
        return events
    vals = ndvi_df["mean_ndvi"].values
    dates = ndvi_df["date"].values
    for i in range(1, len(vals) - 1):
        if vals[i] < vals[i - 1] - 0.05 and vals[i] < vals[i + 1] - 0.05:
            events.append({
                "date": pd.Timestamp(dates[i]),
                "doy": pd.Timestamp(dates[i]).dayofyear,
                "label": "NDVI Dip",
                "value": round(float(vals[i]), 3),
                "detail": f"NDVI {vals[i]:.2f}",
                "color": _COLORS["ndvi_dip"],
                "icon": "\u2193",
                "type": "dip",
            })
    for i in range(1, len(vals)):
        delta = vals[i] - vals[i - 1]
        if delta >= NDVI_SURGE_DELTA:
            events.append({
                "date": pd.Timestamp(dates[i]),
                "doy": pd.Timestamp(dates[i]).dayofyear,
                "label": "Rapid NDVI Rise",
                "value": round(float(delta), 3),
                "detail": f"+{delta:.2f}",
                "color": _COLORS["ndvi_surge"],
                "icon": "\u2191",
                "type": "surge",
            })
    return events


def _render_figure(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame | None,
    gdd_series: pd.Series | None,
    events: list[dict[str, Any]],
    crop_name: str,
    year: int,
    field_slug: str,
    boundary: gpd.GeoDataFrame | None,
) -> bytes:
    fig, axes = plt.subplots(
        4, 1,
        figsize=(_FIG_WIDTH, _FIG_HEIGHT),
        sharex=True,
        gridspec_kw={"height_ratios": _PANEL_HEIGHTS},
    )
    fig.patch.set_facecolor("#fafaf9")

    ax_ndvi, ax_precip, ax_temp, ax_gdd = axes

    _plot_ndvi(ax_ndvi, ndvi_df, events, crop_name)
    _plot_precipitation(ax_precip, weather_df, events)
    _plot_temperature(ax_temp, weather_df, events, year)
    _plot_gdd(ax_gdd, gdd_series, weather_df, crop_name, year)
    _format_xaxis(ax_gdd, year)

    for ev in events:
        ev_dt = ev["date"] if isinstance(ev["date"], datetime) else pd.Timestamp(ev["date"])
        ev_color = ev.get("color", "#94a3b8")
        for ax in axes:
            ax.axvline(x=ev_dt, color=ev_color, linewidth=0.8, linestyle="--", alpha=0.3, zorder=1)

    fig.text(
        0.5, 0.96,
        f"{year} {crop_name} \u00b7 {field_slug}",
        fontsize=15, fontweight="bold", color="#0f172a",
        ha="center", va="top", fontfamily=_FONT,
    )

    buf = BytesIO()
    fig.subplots_adjust(hspace=0.30, left=0.08, right=0.94, top=0.94, bottom=0.08)
    fig.savefig(buf, dpi=150, facecolor=fig.get_facecolor(),
                edgecolor="none", format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _format_xaxis(ax: plt.Axes, year: int) -> None:
    start = datetime(year, 3, 1)
    end = datetime(year, 11, 30)
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.tick_params(labelsize=9)
    ax.set_xlabel("Date", fontsize=10, color="#475569")


def _stagger_annotations(events: list[dict[str, Any]], doy_key: str = "doy", min_gap: int = 30) -> dict[int, tuple[int, int]]:
    sorted_idx = sorted(range(len(events)), key=lambda i: events[i].get(doy_key, 0))
    offsets: dict[int, tuple[int, int]] = {i: (0, 0) for i in range(len(events))}
    for a in range(len(sorted_idx)):
        for b in range(a + 1, len(sorted_idx)):
            ia, ib = sorted_idx[a], sorted_idx[b]
            gap = abs(events[ib].get(doy_key, 0) - events[ia].get(doy_key, 0))
            if gap <= min_gap:
                if (a % 2) == 0:
                    offsets[ib] = (-50, 0)
                else:
                    offsets[ib] = (50, 0)
    return offsets


def _plot_ndvi(
    ax: plt.Axes,
    ndvi_df: pd.DataFrame,
    events: list[dict[str, Any]],
    crop_name: str,
) -> None:
    ax.set_facecolor("#ffffff")
    ax.set_ylabel("NDVI", fontsize=10, color="#475569")
    ax.tick_params(axis="y", labelsize=9)
    ax.set_ylim(-0.1, 1.05)
    ax.grid(True, alpha=0.15)

    if ndvi_df.empty:
        ax.text(0.5, 0.5, "No Sentinel NDVI scenes available",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="#94a3b8", fontstyle="italic")
        return

    valid = ndvi_df[ndvi_df["mean_ndvi"].notna()].sort_values("date")
    if valid.empty:
        ax.text(0.5, 0.5, "All scenes excluded (cloud cover or missing data)",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="#94a3b8", fontstyle="italic")
        return

    ax.scatter(
        valid["date"], valid["mean_ndvi"],
        color=_COLORS["ndvi_marker"], s=45, zorder=5, edgecolors="#166534", linewidth=0.5,
    )
    if len(valid) >= 2:
        ax.plot(
            valid["date"], valid["mean_ndvi"],
            color=_COLORS["ndvi_line"], linewidth=1.5, alpha=0.7, zorder=3,
        )

    ax.set_title(
        "Sentinel-2 NDVI",
        fontsize=11, fontweight="bold", color="#0f172a", loc="left", pad=14,
    )

    ndvi_events = [e for e in events if e.get("type") in ("dip", "surge")]
    ndvi_offsets = _stagger_annotations(ndvi_events)
    for ei, ev in enumerate(ndvi_events):
        dt = ev["date"] if isinstance(ev["date"], datetime) else pd.Timestamp(ev["date"])
        y = ev["value"]
        xoff, yoff = ndvi_offsets.get(ei, (0, 0))
        xoff = max(xoff, 6)
        color = _COLORS["ndvi_dip"] if ev["type"] == "dip" else _COLORS["ndvi_surge"]
        bg = "#fef2f2" if ev["type"] == "dip" else "#f5f3ff"
        ax.annotate(
            f"{'\u2193' if ev['type'] == 'dip' else '\u2191'} {ev['detail']}",
            xy=(dt, y), xytext=(xoff, 14 + yoff),
            textcoords="offset points", fontsize=7.5,
            color=color, fontweight="bold",
            ha="left", va="bottom",
            bbox=dict(boxstyle="round,pad=0.15", facecolor=bg, edgecolor=color, lw=0.5),
        )


def _plot_precipitation(
    ax: plt.Axes,
    weather_df: pd.DataFrame | None,
    events: list[dict[str, Any]],
) -> None:
    ax.set_facecolor("#ffffff")
    ax.set_ylabel("Precip (mm)", fontsize=10, color="#475569")
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(True, alpha=0.15)

    if weather_df is None or weather_df.empty:
        ax.text(0.5, 0.5, "No weather data", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color="#94a3b8", fontstyle="italic")
        return

    ax.set_title("Precipitation", fontsize=11, fontweight="bold", color="#0f172a", loc="left", pad=14)
    mar_nov_p = weather_df[(weather_df["date"].dt.month >= 3) & (weather_df["date"].dt.month <= 11)]
    mean_precip = float(mar_nov_p["PRECTOTCORR"].mean())
    ax.bar(
        weather_df["date"], weather_df["PRECTOTCORR"],
        width=0.8, color=_COLORS["precip"], alpha=0.7, edgecolor="none",
    )
    ax.axhline(y=mean_precip, color="#64748b", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.text(weather_df["date"].iloc[0], mean_precip, f"  Mean {mean_precip:.1f} mm",
            fontsize=7.5, color="#64748b", va="bottom")
    heavy = weather_df[weather_df["PRECTOTCORR"] >= HEAVY_RAIN_THRESHOLD_MM]
    if not heavy.empty:
        ax.bar(
            heavy["date"], heavy["PRECTOTCORR"],
            width=0.8, color=_COLORS["precip_heavy"], alpha=0.9, edgecolor="none",
        )

    max_precip = float(weather_df["PRECTOTCORR"].max())
    if max_precip > 0:
        ax.set_ylim(0, max(max_precip * 1.25, 10))
    else:
        ax.set_ylim(0, 10)

    rain_events = [e for e in events if e["label"] == "Heavy Rain"]
    rain_offsets = _stagger_annotations(rain_events)
    for ei, ev in enumerate(rain_events):
        dt = ev["date"] if isinstance(ev["date"], datetime) else pd.Timestamp(ev["date"])
        xoff, yoff = rain_offsets.get(ei, (0, 0))
        xoff = max(xoff, 6)
        ax.annotate(
            f"\u26a1{ev['detail']}",
            xy=(dt, ev["value"]), xytext=(xoff, 12 + yoff),
            textcoords="offset points", fontsize=7.5,
            color=_COLORS["precip_heavy"], fontweight="bold",
            ha="left", va="bottom",
            arrowprops=dict(arrowstyle="->", color=_COLORS["precip_heavy"], lw=0.8),
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#eff6ff", edgecolor=_COLORS["precip_heavy"], lw=0.5),
        )


def _plot_temperature(
    ax: plt.Axes,
    weather_df: pd.DataFrame | None,
    events: list[dict[str, Any]],
    year: int,
) -> None:
    ax.set_facecolor("#ffffff")
    ax.set_ylabel("Temp (\u00b0C)", fontsize=10, color="#475569")
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(True, alpha=0.15)

    if weather_df is None or weather_df.empty:
        ax.text(0.5, 0.5, "No weather data", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color="#94a3b8", fontstyle="italic")
        return

    ax.set_title("Temperature", fontsize=11, fontweight="bold", color="#0f172a", loc="left", pad=14)

    _gdd_base = 10.0
    _gdd_cap = 30.0
    _gdd_label_dt = datetime(year, 3, 1)
    ax.axhline(y=_gdd_base, color="#f59e0b", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.text(_gdd_label_dt, _gdd_base, f"  GDD base {_gdd_base:.0f}\u00b0C",
            fontsize=7.5, color="#f59e0b", va="bottom")
    ax.axhline(y=_gdd_cap, color="#ef4444", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.text(_gdd_label_dt, _gdd_cap, f"  GDD cap {_gdd_cap:.0f}\u00b0C",
            fontsize=7.5, color="#ef4444", va="bottom")

    ax.fill_between(
        weather_df["date"], weather_df["T2M_MIN"], weather_df["T2M_MAX"],
        color=_COLORS["temp_ribbon"], alpha=0.5, linewidth=0,
    )
    ax.plot(
        weather_df["date"], weather_df["T2M_MAX"],
        color=_COLORS["temp_max"], linewidth=1.0, alpha=0.8, label="Max",
    )
    ax.plot(
        weather_df["date"], weather_df["T2M_MIN"],
        color=_COLORS["temp_min"], linewidth=1.0, alpha=0.8, label="Min",
    )
    ax.plot(
        weather_df["date"], weather_df["T2M"],
        color=_COLORS["temp_mean"], linewidth=0.8, alpha=0.5, label="Mean",
    )

    all_temps = pd.concat([weather_df["T2M_MAX"], weather_df["T2M_MIN"]])
    t_min, t_max = float(all_temps.min()), float(all_temps.max())
    margin = max(5, (t_max - t_min) * 0.1)
    ax.set_ylim(t_min - margin, t_max + margin)

    ax.legend(fontsize=7, loc="upper right", ncol=3)

    hot_events = [e for e in events if e["label"] == "Hot Day"]
    hot_offsets = _stagger_annotations(hot_events)
    for ei, ev in enumerate(hot_events):
        dt = ev["date"] if isinstance(ev["date"], datetime) else pd.Timestamp(ev["date"])
        xoff, yoff = hot_offsets.get(ei, (0, 0))
        xoff = max(xoff, 6)
        ax.annotate(
            f"\u2600{ev['detail']}",
            xy=(dt, ev["value"]), xytext=(xoff, 12 + yoff),
            textcoords="offset points", fontsize=7.5,
            color=_COLORS["temp_max"], fontweight="bold",
            ha="left", va="bottom",
            arrowprops=dict(arrowstyle="->", color=_COLORS["temp_max"], lw=0.8),
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#fef2f2", edgecolor=_COLORS["temp_max"], lw=0.5),
        )

    cool_events = [e for e in events if e["label"] == "Cool Period"]
    cool_offsets = _stagger_annotations(cool_events)
    for ei, ev in enumerate(cool_events):
        dt = ev["date"] if isinstance(ev["date"], datetime) else pd.Timestamp(ev["date"])
        end_dt = ev.get("end_date", dt)
        if isinstance(end_dt, (pd.Timestamp, datetime)):
            ax.axvspan(dt, end_dt, alpha=0.12, color=_COLORS["temp_min"], zorder=0)
            mid = dt + (end_dt - dt) / 2
            _, yoff = cool_offsets.get(ei, (0, 0))
            ax.annotate(
                f"\u2744 {ev['detail']}",
                xy=(mid, 0.92), xytext=(0, -12 + yoff),
                textcoords=("data", "axes fraction"),
                fontsize=7.5, color=_COLORS["temp_min"], fontweight="bold",
                ha="center", va="top",
            )


def _plot_gdd(
    ax: plt.Axes,
    gdd_series: pd.Series | None,
    weather_df: pd.DataFrame | None,
    crop_name: str,
    year: int,
) -> None:
    ax.set_facecolor("#ffffff")
    ax.set_ylabel("Cumul. GDD", fontsize=10, color="#475569")
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(True, alpha=0.15)

    if gdd_series is None or weather_df is None or weather_df.empty:
        ax.text(0.5, 0.5, "GDD data unavailable",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="#94a3b8", fontstyle="italic")
        return

    ax.set_title("Cumulative Growing Degree Days", fontsize=11, fontweight="bold",
                 color="#0f172a", loc="left", pad=14)
    ax.plot(
        weather_df["date"], gdd_series,
        color=_COLORS["gdd"], linewidth=2.0, zorder=4,
    )

    final_gdd = float(gdd_series.iloc[-1])
    ax.text(
        0.98, 0.95, f"{final_gdd:.0f} GDD",
        transform=ax.transAxes, fontsize=9, fontweight="bold",
        color=_COLORS["gdd"], ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#fffbeb", edgecolor=_COLORS["gdd"], lw=0.5),
    )

    stages = CROP_STAGES.get(crop_name, CROP_STAGES.get("Corn", []))
    for stage in stages:
        stage_gdd = float(stage["gdd"])
        stage_name = str(stage["name"])
        ax.axhline(y=stage_gdd, color=_COLORS["gdd_stage"], linewidth=0.8,
                   linestyle="--", alpha=0.5, zorder=1)
        ax.text(
            1.0, stage_gdd, f"  {stage_name}",
            transform=ax.get_xaxis_transform(), fontsize=7.5,
            color=_COLORS["gdd_stage_label"], va="center", ha="left",
            alpha=0.8,
        )


def _build_html(
    chart_png_bytes: bytes,
    events: list[dict[str, Any]],
    warnings_list: list[dict[str, str]],
    crop_name: str,
    year: int,
    field_slug: str,
    field_info: dict[str, Any],
    ndvi_count: int,
) -> str:
    chart_b64 = base64.b64encode(chart_png_bytes).decode("utf-8")
    event_cards_html = _build_event_cards(events)
    warnings_html = _build_warnings(warnings_list)

    county = field_info.get("county_name", "")
    state = field_info.get("state_fips", "")
    area = field_info.get("area_acres", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{year} {crop_name} \u00b7 {field_slug}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f1f5f9; color: #0f172a; line-height: 1.5;
}}
.dashboard {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.header {{
  background: linear-gradient(135deg, #166534, #15803d);
  color: white; border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
}}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
.header .sub {{ font-size: 14px; opacity: 0.9; }}
.header .meta {{ font-size: 13px; opacity: 0.75; margin-top: 6px; }}
.chart-container {{
  background: white; border-radius: 12px; padding: 16px; margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
.chart-container img {{ width: 100%; height: auto; display: block; }}
.events-section {{
  background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
.events-section h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: #0f172a; }}
.events-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }}
.event-card {{
  border-radius: 8px; padding: 12px 14px;
  display: flex; align-items: flex-start; gap: 10px;
}}
.event-card .icon {{ font-size: 20px; flex-shrink: 0; }}
.event-card .body {{ flex: 1; }}
.event-card .body .ev-label {{ font-weight: 600; font-size: 13px; }}
.event-card .body .ev-date {{ font-size: 11px; color: #64748b; }}
.event-card .body .ev-detail {{ font-size: 12px; color: #334155; margin-top: 2px; }}
.event-empty {{ text-align: center; padding: 20px; color: #94a3b8; font-style: italic; }}
.warnings {{ margin-bottom: 20px; }}
.warning-item {{
  border-radius: 8px; padding: 10px 14px; margin-bottom: 6px;
  font-size: 13px; display: flex; align-items: center; gap: 8px;
}}
.warning-item .w-icon {{ font-size: 16px; flex-shrink: 0; }}
.warning-info {{ background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }}
.warning-warning {{ background: #fefce8; color: #854d0e; border: 1px solid #fde68a; }}
.warning-error {{ background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }}
.footer {{
  text-align: center; font-size: 11px; color: #94a3b8; padding: 16px;
}}
.data-badge {{
  display: inline-block; background: white; border-radius: 6px;
  padding: 4px 10px; font-size: 12px; margin-right: 6px; margin-bottom: 4px;
}}
</style>
</head>
<body>
<div class="dashboard">
  <div class="header">
    <h1>{year} {crop_name} \u00b7 {field_slug}</h1>
    <div class="sub">{county}{", " + state if state else ""}{f" \u00b7 {area:.1f} ac" if area else ""}</div>
    <div class="meta">
      <span class="data-badge" style="color:#0f172a;">&#x1F4C8; {ndvi_count} Sentinel scenes</span>
      <span class="data-badge" style="color:#0f172a;">&#x1F326; NASA POWER weather</span>
      <span class="data-badge" style="color:#0f172a;">&#x1F4CD; CDL crop: {crop_name}</span>
    </div>
  </div>
  {warnings_html}
  <div class="chart-container">
    <img src="data:image/png;base64,{chart_b64}" alt="{year} {crop_name} dashboard">
  </div>
  <div class="events-section">
    <h2>Notable Events</h2>
    {event_cards_html}
  </div>
  <div class="footer">
    Generated by ndvi-weather-dashboard &middot; Data: CDL, Sentinel-2, NASA POWER
  </div>
</div>
</body>
</html>"""


def _build_event_cards(events: list[dict[str, Any]]) -> str:
    if not events:
        return '<div class="event-empty">No notable events detected for this season.</div>'
    cards = []
    for ev in events:
        bg = ev.get("color", "#64748b")
        dt = ev["date"] if isinstance(ev["date"], (datetime, pd.Timestamp)) else pd.Timestamp(ev["date"])
        date_str = dt.strftime("%b %d")
        icon = ev.get("icon", "\u2022")
        detail = ev.get("detail", "")
        end_date = ev.get("end_date")
        end_str = ""
        if end_date:
            end = end_date if isinstance(end_date, (datetime, pd.Timestamp)) else pd.Timestamp(end_date)
            end_str = f" \u2013 {end.strftime('%b %d')}"
        cards.append(
            f'<div class="event-card" style="background:{bg}10;border-left:3px solid {bg};">'
            f'<div class="icon">{icon}</div>'
            f'<div class="body">'
            f'<div class="ev-label" style="color:{bg};">{ev["label"]}</div>'
            f'<div class="ev-date">{date_str}{end_str}</div>'
            f'<div class="ev-detail">{detail}</div>'
            f'</div></div>'
        )
    return f'<div class="events-grid">{"".join(cards)}</div>'


def _build_warnings(warnings_list: list[dict[str, str]]) -> str:
    if not warnings_list:
        return ""
    items = []
    for w in warnings_list:
        level = w.get("level", "info")
        msg = w.get("message", "")
        icons = {"info": "\u2139", "warning": "\u26a0", "error": "\u274c"}
        items.append(
            f'<div class="warning-item warning-{level}">'
            f'<span class="w-icon">{icons.get(level, "\u2139")}</span>'
            f'<span>{msg}</span>'
            f'</div>'
        )
    return f'<div class="warnings">{"".join(items)}</div>'


def _read_field_boundary_properties(field_root: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    boundary = _read_boundary(field_root)
    if boundary is not None and not boundary.empty:
        props = boundary.iloc[0]
        for key in ["county_name", "state_fips", "county_fips", "area_acres", "source"]:
            if key in props:
                info[key] = props[key]
    field_json = field_root / "field.json"
    if field_json.exists():
        try:
            meta = json.loads(field_json.read_text(encoding="utf-8"))
            info.setdefault("display_name", meta.get("display_name", ""))
        except (json.JSONDecodeError, OSError):
            pass
    return info


def _filter_events_for_display(events: list[dict[str, Any]], max_per_type: int = 5, min_doy: int = 60) -> list[dict[str, Any]]:
    events = [e for e in events if e.get("doy", 0) >= min_doy]
    if not events:
        return []
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_type.setdefault(ev.get("label", ""), []).append(ev)
    result: list[dict[str, Any]] = []
    for label, evs in by_type.items():
        sort_key = "value" if label in ("Heavy Rain", "Hot Day") else "date"
        reverse = label in ("Heavy Rain", "Hot Day")
        sorted_evs = sorted(evs, key=lambda e: e.get(sort_key, 0) if sort_key == "value" else str(e.get(sort_key, "")), reverse=reverse)
        result.extend(sorted_evs[:max_per_type])
    result.sort(key=lambda e: e.get("doy", 0))
    return result


def generate_dashboard(
    field_slug: str,
    year: int,
    grower_slug: str = "il-grower",
    farm_slug: str = "il-grower-illinois",
    output_dir: str | None = None,
) -> str:
    data_root = _resolve_data_root()
    froot = _field_root(data_root, grower_slug, farm_slug, field_slug)

    crop_info = _read_crop_info(froot, year)
    crop_name = crop_info["crop_name"]
    boundary = _read_boundary(froot)
    field_info = _read_field_boundary_properties(froot)

    ndvi_scenes = _collect_sentinel_scenes(froot, year, data_root)
    ndvi_df = pd.DataFrame([
        {"date": pd.Timestamp(s["date"]), "mean_ndvi": s["mean_ndvi"], "cloud_cover": s["cloud_cover"]}
        for s in ndvi_scenes if not s["excluded"]
    ])
    if not ndvi_df.empty:
        ndvi_df = ndvi_df.sort_values("date").reset_index(drop=True)

    weather_df = _load_weather_for_year(froot, year)
    gdd_series = _compute_gdd(weather_df) if weather_df is not None else None

    quality_warnings = _check_data_quality(froot, year, ndvi_scenes, weather_df)

    events: list[dict[str, Any]] = []
    if weather_df is not None:
        events.extend(_detect_heavy_rain(weather_df))
        events.extend(_detect_hot_days(weather_df))
        events.extend(_detect_cool_periods(weather_df))
    if not ndvi_df.empty:
        events.extend(_detect_ndvi_events(ndvi_df))

    display_events = _filter_events_for_display(events, min_doy=60)
    chart_png = _render_figure(
        ndvi_df, weather_df, gdd_series,
        display_events, crop_name, year, field_slug, boundary,
    )

    ndvi_count = len([s for s in ndvi_scenes if not s["excluded"]])
    html = _build_html(
        chart_png, display_events, quality_warnings,
        crop_name, year, field_slug, field_info, ndvi_count,
    )

    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = froot / "derived" / "dashboards"
    out_path.mkdir(parents=True, exist_ok=True)

    output_file = out_path / f"ndvi_weather_dashboard_{year}.html"
    output_file.write_text(html, encoding="utf-8")
    return str(output_file)


def cli() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate an NDVI + weather dashboard HTML for a field-year."
    )
    parser.add_argument("field_slug", help="Field slug (e.g. osm-1499317763)")
    parser.add_argument("--year", type=int, default=2023, help="Target year")
    parser.add_argument("--grower", default="il-grower", help="Grower slug")
    parser.add_argument("--farm", default="il-grower-illinois", help="Farm slug")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: field's derived/dashboards/)")
    args = parser.parse_args()

    path = generate_dashboard(
        field_slug=args.field_slug,
        year=args.year,
        grower_slug=args.grower,
        farm_slug=args.farm,
        output_dir=args.output_dir,
    )
    print(f"\u2713 Dashboard generated: {path}")


if __name__ == "__main__":
    cli()
