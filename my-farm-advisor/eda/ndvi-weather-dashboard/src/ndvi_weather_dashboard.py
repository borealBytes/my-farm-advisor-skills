from __future__ import annotations

import json
import os
import urllib.request
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
warnings.filterwarnings("ignore", category=UserWarning, module="rasterio")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

pio.templates.default = "none"

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
_FIG_HEIGHT = 800
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
            "message": f"Only {len(ndvi_scenes)} satellite scene(s) available for {year}. "
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

    for sensor in ("sentinel", "landsat"):
        manifest = field_root / "satellite" / sensor / "manifest.json"
        if not manifest.exists():
            warnings_list.append({
                "level": "error",
                "message": f"{sensor.capitalize()} manifest.json not found.",
            })

    boundary = field_root / "boundary" / "field_boundary.geojson"
    if not boundary.exists():
        warnings_list.append({
            "level": "error",
            "message": "Field boundary not found.",
        })

    return warnings_list


def _collect_sensor_scenes(
    field_root: Path, year: int, data_root: Path, sensor: str
) -> list[dict[str, Any]]:
    manifest = field_root / "satellite" / sensor / "manifest.json"
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
            "source": sensor,
            "ndvi_path": str(ndvi_path),
        })
    return scenes


def _collect_all_scenes(field_root: Path, year: int, data_root: Path) -> list[dict[str, Any]]:
    scenes = _collect_sensor_scenes(field_root, year, data_root, "sentinel")
    scenes.extend(_collect_sensor_scenes(field_root, year, data_root, "landsat"))
    return scenes


def _collect_sentinel_scenes(
    field_root: Path, year: int, data_root: Path
) -> list[dict[str, Any]]:
    return _collect_sensor_scenes(field_root, year, data_root, "sentinel")


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


def _fig_subtitle(fig: go.Figure, year: int, crop_name: str, field_slug: str) -> None:
    fig.add_annotation(
        x=0.5, y=1.0, xref="paper", yref="paper",
        text=f"{year} {crop_name} - {field_slug}",
        font=dict(size=15, color="#0f172a", family=_FONT),
        showarrow=False, xanchor="center", yanchor="bottom",
        yshift=8,
    )


def _render_figure(
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame | None,
    gdd_series: pd.Series | None,
    events: list[dict[str, Any]],
    crop_name: str,
    year: int,
    field_slug: str,
    boundary: gpd.GeoDataFrame | None,
) -> go.Figure:
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=_PANEL_HEIGHTS,
    )
    fig.update_layout(
        paper_bgcolor="#fafaf9",
        plot_bgcolor="#ffffff",
        height=_FIG_HEIGHT,
        margin=dict(l=50, r=30, t=50, b=30),
        font=dict(family=_FONT, size=10, color="#475569"),
        hovermode="x unified",
    )

    _plot_gdd(fig, gdd_series, weather_df, crop_name, year)
    _plot_temperature(fig, weather_df, events, year)
    _plot_precipitation(fig, weather_df, events, year)
    _plot_ndvi(fig, ndvi_df, events, crop_name, year)
    _fig_subtitle(fig, year, crop_name, field_slug)

    return fig


def _plot_ndvi(
    fig: go.Figure,
    ndvi_df: pd.DataFrame,
    events: list[dict[str, Any]],
    crop_name: str,
    year: int,
) -> None:
    if ndvi_df.empty:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="No satellite NDVI scenes available",
                           showarrow=False, font=dict(size=11, color="#94a3b8"), row=1, col=1)
        return

    valid = ndvi_df[ndvi_df["mean_ndvi"].notna()].sort_values("date")
    if valid.empty:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="All scenes excluded (cloud cover or missing data)",
                           showarrow=False, font=dict(size=11, color="#94a3b8"), row=1, col=1)
        return

    for src, ln_color, mk_color, symbol, label in [
        ("sentinel", _COLORS["ndvi_line"], _COLORS["ndvi_marker"], "circle", "Sentinel-2"),
        ("landsat", "#d97706", "#f97316", "triangle-up", "Landsat 8/9"),
    ]:
        subset = valid[valid["source"] == src].sort_values("date")
        if subset.empty:
            continue
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["mean_ndvi"],
            mode="lines+markers",
            line=dict(color=ln_color, width=1.5),
            marker=dict(color=mk_color, size=6, symbol=symbol, line=dict(color="white", width=0.5)),
            opacity=0.85,
            name=label,
            hovertemplate="%{x|%b %d}<br>NDVI: %{y:.3f}<br>Source: " + src.capitalize() + "<extra></extra>",
        ), row=1, col=1)

    ndvi_evts = [e for e in events if e.get("type") in ("dip", "surge")]
    if ndvi_evts:
        fig.add_trace(go.Scatter(
            x=[e["date"] for e in ndvi_evts],
            y=[e["value"] for e in ndvi_evts],
            mode="markers", marker=dict(opacity=0, size=14),
            showlegend=False,
            hovertext=[f'⚠️ <b>Key event!</b><br>{e["detail"]}' for e in ndvi_evts],
            hoverinfo="text",
            hoverlabel=dict(bgcolor="#fef3c7", bordercolor="#d97706"),
        ), row=1, col=1)

    fig.update_yaxes(title_text="NDVI", range=[-0.1, 1.05], row=1, col=1)
    fig.update_xaxes(title_text="", row=1, col=1)


def _plot_precipitation(
    fig: go.Figure,
    weather_df: pd.DataFrame | None,
    events: list[dict[str, Any]],
    year: int,
) -> None:
    if weather_df is None or weather_df.empty:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="No weather data", showarrow=False,
                           font=dict(size=11, color="#94a3b8"), row=2, col=1)
        return

    mar_nov = weather_df[(weather_df["date"].dt.month >= 3) & (weather_df["date"].dt.month <= 11)]
    mean_precip = float(mar_nov["PRECTOTCORR"].mean())

    fig.add_trace(go.Bar(
        x=weather_df["date"], y=weather_df["PRECTOTCORR"],
        marker=dict(color=_COLORS["precip"], opacity=0.7),
        name="Precipitation",
        hovertemplate="%{x|%b %d}<br>%{y:.1f} mm<extra></extra>",
    ), row=2, col=1)

    fig.add_hline(y=mean_precip, line=dict(color="#64748b", width=0.8, dash="dash"), opacity=0.7, row=2, col=1)

    heavy = weather_df[weather_df["PRECTOTCORR"] >= HEAVY_RAIN_THRESHOLD_MM]
    if not heavy.empty:
        fig.add_trace(go.Bar(
            x=heavy["date"], y=heavy["PRECTOTCORR"],
            marker=dict(color=_COLORS["precip_heavy"]),
            name="Heavy Rain",
            hovertemplate="%{x|%b %d}<br>%{y:.1f} mm<extra></extra>",
            showlegend=False,
        ), row=2, col=1)

    rain_evts = [e for e in events if e["label"] == "Heavy Rain"]
    if rain_evts:
        fig.add_trace(go.Scatter(
            x=[e["date"] for e in rain_evts],
            y=[e["value"] for e in rain_evts],
            mode="markers", marker=dict(opacity=0, size=14),
            showlegend=False,
            hovertext=[f'⚠️ <b>Key event!</b><br>{e["detail"]}' for e in rain_evts],
            hoverinfo="text",
            hoverlabel=dict(bgcolor="#fef3c7", bordercolor="#d97706"),
        ), row=2, col=1)

    max_p = float(weather_df["PRECTOTCORR"].max())
    fig.update_yaxes(title_text="Precip (mm)", range=[0, max(max_p * 1.3, 10)], row=2, col=1)


def _plot_temperature(
    fig: go.Figure,
    weather_df: pd.DataFrame | None,
    events: list[dict[str, Any]],
    year: int,
) -> None:
    if weather_df is None or weather_df.empty:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="No weather data", showarrow=False,
                           font=dict(size=11, color="#94a3b8"), row=3, col=1)
        return

    fig.add_trace(go.Scatter(
        x=weather_df["date"], y=weather_df["T2M_MAX"],
        mode="lines",
        line=dict(color=_COLORS["temp_max"], width=1),
        name="T2M_MAX",
        hovertemplate="%{x|%b %d}<br>Max: %{y:.1f}°C<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=weather_df["date"], y=weather_df["T2M"],
        mode="lines",
        line=dict(color=_COLORS["temp_mean"], width=0.8, dash="dot"),
        name="T2M",
        hovertemplate="%{x|%b %d}<br>Mean: %{y:.1f}°C<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=weather_df["date"], y=weather_df["T2M_MIN"],
        mode="lines",
        line=dict(color=_COLORS["temp_min"], width=1),
        fill="tonexty", fillcolor="rgba(226,232,240,0.4)",
        name="T2M_MIN",
        hovertemplate="%{x|%b %d}<br>Min: %{y:.1f}°C<extra></extra>",
    ), row=3, col=1)

    all_temps = pd.concat([weather_df["T2M_MAX"], weather_df["T2M_MIN"]])
    t_min, t_max = float(all_temps.min()), float(all_temps.max())
    margin = max(5, (t_max - t_min) * 0.1)
    fig.update_yaxes(title_text="Temp (°C)", range=[t_min - margin, t_max + margin], row=3, col=1)

    hot_evts = [e for e in events if e["label"] == "Hot Day"]
    if hot_evts:
        fig.add_trace(go.Scatter(
            x=[e["date"] for e in hot_evts],
            y=[e["value"] for e in hot_evts],
            mode="markers", marker=dict(opacity=0, size=14),
            showlegend=False,
            hovertext=[f'⚠️ <b>Key event!</b><br>{e["detail"]}' for e in hot_evts],
            hoverinfo="text",
            hoverlabel=dict(bgcolor="#fef3c7", bordercolor="#d97706"),
        ), row=3, col=1)


def _plot_gdd(
    fig: go.Figure,
    gdd_series: pd.Series | None,
    weather_df: pd.DataFrame | None,
    crop_name: str,
    year: int,
) -> None:
    if gdd_series is None or weather_df is None or weather_df.empty:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="GDD data unavailable", showarrow=False,
                           font=dict(size=11, color="#94a3b8"), row=4, col=1)
        return

    daily_gdd = np.clip(
        (weather_df["T2M_MAX"] + weather_df["T2M_MIN"]) / 2.0 - GDD_BASE_TEMP,
        0, GDD_CAP_TEMP - GDD_BASE_TEMP,
    )
    fig.add_trace(go.Scatter(
        x=weather_df["date"], y=gdd_series,
        mode="lines",
        line=dict(color=_COLORS["gdd"], width=2),
        name="Cumul. GDD",
        customdata=np.column_stack([daily_gdd.round(1)]),
        hovertemplate="%{x|%b %d}<br>%{y:.0f} GDD (+%{customdata[0]:.1f})<extra></extra>",
    ), row=4, col=1)

    final_gdd = float(gdd_series.iloc[-1])
    fig.add_annotation(
        x=1.0, y=final_gdd, xref="x domain", yref="y",
        text=f"{final_gdd:.0f} GDD",
        showarrow=False, font=dict(size=11, color=_COLORS["gdd"]),
        bgcolor="#fffbeb", bordercolor=_COLORS["gdd"], borderwidth=0.5, borderpad=3,
        xanchor="right", yanchor="bottom",
        row=4, col=1,
    )

    stages = CROP_STAGES.get(crop_name, CROP_STAGES.get("Corn", []))
    for stage in stages:
        stage_gdd = float(stage["gdd"])
        stage_name = str(stage["name"])
        fig.add_hline(y=stage_gdd, line=dict(color=_COLORS["gdd_stage"], width=0.8, dash="dash"), opacity=0.5,
                      row=4, col=1)
        fig.add_annotation(
            xref="paper", y=stage_gdd,
            text=stage_name,
            showarrow=False, font=dict(size=9, color=_COLORS["gdd_stage_label"]),
            xanchor="left", x=1.0,
            row=4, col=1,
        )

    fig.update_yaxes(title_text="Cumul. GDD", row=4, col=1)
    fig.update_xaxes(title_text="Date", dtick="M1", tickformat="%b", row=4, col=1)
    for row in range(1, 5):
        fig.update_xaxes(range=[datetime(year, 3, 1), datetime(year, 11, 30)], row=row, col=1)


def _compute_spi(lat: float, lon: float, year: int) -> str | None:
    try:
        url = f"https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=RE&longitude={lon}&latitude={lat}&start=2000&end={year}&format=JSON"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as f:
            data = json.loads(f.read())
        precip = data["properties"]["parameter"]["PRECTOTCORR"]
    except Exception:
        return None

    apr_sep_totals: list[float] = []
    for y in range(2000, year + 1):
        months = []
        for m in range(4, 10):
            key = f"{y}{m:02d}"
            val = precip.get(key)
            if val is None or val < 0:
                break
            months.append(val)
        if len(months) == 6:
            apr_sep_totals.append(sum(months))
    if len(apr_sep_totals) < 5:
        return None

    current = apr_sep_totals[-1]
    historical = np.array(apr_sep_totals[:-1])
    mean = float(np.mean(historical))
    std = float(np.std(historical, ddof=1))
    if std == 0:
        return None

    spi = (current - mean) / std
    if spi >= 2.0:
        cat = "W4 - Exceptionally Wet"
    elif spi >= 1.6:
        cat = "W3 - Extremely Wet"
    elif spi >= 1.3:
        cat = "W2 - Severely Wet"
    elif spi >= 0.8:
        cat = "W1 - Moderately Wet"
    elif spi >= 0.5:
        cat = "W0 - Abnormally Wet"
    elif spi >= -0.5:
        cat = "Normal"
    elif spi >= -0.8:
        cat = "D0 - Abnormally Dry"
    elif spi >= -1.3:
        cat = "D1 - Moderate Drought"
    elif spi >= -1.6:
        cat = "D2 - Severe Drought"
    elif spi >= -2.0:
        cat = "D3 - Extreme Drought"
    else:
        cat = "D4 - Exceptional Drought"
    return f"{cat} ({spi:+.2f})"


def _check_yield_constraints(
    crop_name: str,
    weather_df: pd.DataFrame | None,
    gdd_series: pd.Series | None,
    year: int,
    spi_category: str | None,
) -> list[str]:
    constraints: list[str] = []

    if gdd_series is not None:
        final_gdd = float(gdd_series.iloc[-1])
        if final_gdd < 2000:
            constraints.append(f"Low GDD ({final_gdd:.0f} < 2000) — insufficient thermal time for full maturity")

    if weather_df is not None and not weather_df.empty:
        april_heavy = weather_df[(weather_df["date"].dt.month == 4) & (weather_df["PRECTOTCORR"] > 44.7)]
        if not april_heavy.empty:
            n = len(april_heavy)
            constraints.append(f"Early crop flooding risk: {n} heavy rainfall event{'s' if n > 1 else ''} in April ({april_heavy.iloc[0]['PRECTOTCORR']:.0f} mm{'–' + str(int(april_heavy.iloc[-1]['PRECTOTCORR'])) + ' mm' if n > 1 else ''})")

        hot_days = int((weather_df["T2M_MAX"] > 30).sum())
        if hot_days > 40:
            constraints.append(f"Heat stress: {hot_days} days with max temp above 30°C")

        cold_days = int((weather_df["T2M_MAX"] < 10).sum())
        if cold_days > 110:
            constraints.append(f"Not enough heat: {cold_days} days with max temp below 10°C")

    if spi_category:
        if any(cat in spi_category for cat in ["D2 -", "D3 -", "D4 -"]):
            constraints.append(f"Severe drought ({spi_category}) — high water stress risk")

    return constraints


def _build_year_overview(
    crop_name: str,
    events: list[dict[str, Any]],
    ndvi_df: pd.DataFrame,
    weather_df: pd.DataFrame | None,
    year: int,
    gdd_series: pd.Series | None,
    spi_category: str | None = None,
) -> str:
    parts: list[str] = []
    parts.append(f"In {year}, <strong>{crop_name}</strong> was grown on this field.")

    if ndvi_df is not None and not ndvi_df.empty:
        valid = ndvi_df[ndvi_df["mean_ndvi"].notna()].sort_values("date")
        if len(valid) >= 2:
            growing = valid[(valid["mean_ndvi"] >= 0.3) & (valid["date"].dt.dayofyear >= 60)]
            if len(growing) >= 2:
                emergence = growing.iloc[0]["date"].strftime("%b %-d")
                maturity = growing.iloc[-1]["date"].strftime("%b %-d")
                parts.append(f"The crop emerged around <strong>{emergence}</strong> (NDVI reached 0.3) and reached maturity around <strong>{maturity}</strong>.")

    if weather_df is not None and not weather_df.empty:
        mar_nov = weather_df[(weather_df["date"].dt.month >= 3) & (weather_df["date"].dt.month <= 11)]
        total_precip = mar_nov["PRECTOTCORR"].sum()
        parts.append(f"The growing season (Mar–Nov) accumulated <strong>{total_precip:.0f} mm</strong> of precipitation.")

    if gdd_series is not None:
        final_gdd = float(gdd_series.iloc[-1])
        parts.append(f"Total GDD accumulation was <strong>{final_gdd:.0f}</strong> (base 10°C, cap 30°C).")

    constraints = _check_yield_constraints(crop_name, weather_df, gdd_series, year, spi_category)
    if constraints:
        parts.append("")
        parts.append("<strong>⚠️ Potential Yield Constraints:</strong>")
        for c in constraints:
            parts.append(f"&nbsp;&nbsp;\u2022 {c}")

    sorted_events = sorted(events, key=lambda e: e.get("doy", 0))
    if sorted_events:
        parts.append("")
        parts.append("<strong>Key events:</strong>")
        for ev in sorted_events:
            dt = ev["date"] if isinstance(ev["date"], (datetime, pd.Timestamp)) else pd.Timestamp(ev["date"])
            ds = dt.strftime("%b %-d")
            if ev["label"] == "Heavy Rain":
                parts.append(f"&nbsp;&nbsp;\u2022 {ds}: Heavy rainfall of {ev['detail']}")
            elif ev["label"] == "Hot Day":
                parts.append(f"&nbsp;&nbsp;\u2022 {ds}: Hot day with a high of {ev['detail']}")
            elif ev.get("type") == "dip":
                parts.append(f"&nbsp;&nbsp;\u2022 {ds}: NDVI dip detected ({ev['detail']})")
            elif ev.get("type") == "surge":
                parts.append(f"&nbsp;&nbsp;\u2022 {ds}: Rapid NDVI increase ({ev['detail']})")
            elif ev["label"] == "Cool Period":
                end_dt = ev.get("end_date", dt)
                if isinstance(end_dt, (pd.Timestamp, datetime)):
                    parts.append(f"&nbsp;&nbsp;\u2022 {ds} \u2013 {end_dt.strftime('%b %-d')}: Cool period lasting {ev['detail']}")

    return "<br>".join(parts)


def _build_html(
    fig: go.Figure,
    events: list[dict[str, Any]],
    warnings_list: list[dict[str, str]],
    crop_name: str,
    year: int,
    field_slug: str,
    field_info: dict[str, Any],
    ndvi_count: int,
    weather_df: pd.DataFrame | None = None,
    ndvi_df: pd.DataFrame | None = None,
    gdd_series: pd.Series | None = None,
    all_events: list[dict[str, Any]] | None = None,
    spi_category: str | None = None,
) -> str:
    chart_div = fig.to_html(full_html=False, include_plotlyjs="cdn", default_width="100%", default_height=f"{_FIG_HEIGHT}px")
    event_cards_html = _build_year_overview(crop_name, all_events or events, ndvi_df, weather_df, year, gdd_series, spi_category)
    warnings_html = _build_warnings(warnings_list)

    county = field_info.get("county_name", "")
    state = field_info.get("state_fips", "")
    area = field_info.get("area_acres", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{year} {crop_name} - {field_slug}</title>
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
.overview-text {{ font-size: 13px; line-height: 1.7; color: #334155; }}
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
    <h1>{year} {crop_name} - {field_slug}</h1>
    <div class="sub">{county}{", " + state if state else ""}{f" \u00b7 {area:.1f} ac" if area else ""}</div>
    <div class="meta">
      <span class="data-badge" style="color:#0f172a;">&#x1F4C8; {ndvi_count} satellite scenes</span>
      <span class="data-badge" style="color:#0f172a;">&#x1F326; NASA POWER weather</span>
      <span class="data-badge" style="color:#0f172a;">&#x1F4CD; CDL crop: {crop_name}</span>
    </div>
  </div>
  {warnings_html}
  <div class="chart-container">
    {chart_div}
  </div>
  <div class="events-section">
    <h2>Year Overview</h2>
    <div class="overview-text">{event_cards_html}</div>
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

    ndvi_scenes = _collect_all_scenes(froot, year, data_root)
    ndvi_df = pd.DataFrame([
        {"date": pd.Timestamp(s["date"]), "mean_ndvi": s["mean_ndvi"], "cloud_cover": s["cloud_cover"], "source": s.get("source", "sentinel")}
        for s in ndvi_scenes if not s["excluded"]
    ])
    if not ndvi_df.empty:
        ndvi_df = ndvi_df.sort_values("date").reset_index(drop=True)

    weather_df = _load_weather_for_year(froot, year)
    gdd_series = _compute_gdd(weather_df) if weather_df is not None else None

    spi_category: str | None = None
    if weather_df is not None and not weather_df.empty:
        lat = float(weather_df["lat"].iloc[0])
        lon = float(weather_df["lon"].iloc[0])
        spi_category = _compute_spi(lat, lon, year)

    quality_warnings = _check_data_quality(froot, year, ndvi_scenes, weather_df)

    events: list[dict[str, Any]] = []
    if weather_df is not None:
        events.extend(_detect_heavy_rain(weather_df))
        events.extend(_detect_hot_days(weather_df))
        events.extend(_detect_cool_periods(weather_df))
    if not ndvi_df.empty:
        events.extend(_detect_ndvi_events(ndvi_df))

    display_events = _filter_events_for_display(events, min_doy=60)
    fig = _render_figure(
        ndvi_df, weather_df, gdd_series,
        display_events, crop_name, year, field_slug, boundary,
    )

    ndvi_count = len([s for s in ndvi_scenes if not s["excluded"]])
    html = _build_html(
        fig, display_events, quality_warnings,
        crop_name, year, field_slug, field_info, ndvi_count,
        weather_df=weather_df,
        ndvi_df=ndvi_df,
        gdd_series=gdd_series,
        all_events=display_events,
        spi_category=spi_category,
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
