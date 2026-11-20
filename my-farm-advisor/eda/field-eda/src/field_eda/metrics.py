"""Derived measures and small-sample statistics.

Formulas are documented in ``references/metric-definitions.md``. If this module
and that file disagree, the file is authoritative.

Aggregation order is load-bearing: weather and crop totals are computed per
field first, then averaged across fields. Grouping a per-field table only by
grower would multiply precipitation by the field count.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .discover import Dataset, RunConfig

PIXEL_AREA_M2 = 900.0
SQ_M_PER_HA = 10_000.0
GDD_BASE_C = 10.0
HEAT_THRESHOLD_C = 35.0
SEASON_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

SOURCE_MAP = {"usda_csb_fiboa": "csb", "OpenStreetMap/Overpass": "osm"}


# --------------------------------------------------------------------------- #
# Boundaries
# --------------------------------------------------------------------------- #


def _bearing_deg(geom) -> float:
    """Bearing of the minimum rotated rectangle's long edge, (-90, 90]."""
    corners = list(geom.minimum_rotated_rectangle.exterior.coords)[:5]
    edges = list(zip(corners, corners[1:]))
    (x1, y1), (x2, y2) = max(
        edges, key=lambda e: (e[1][0] - e[0][0]) ** 2 + (e[1][1] - e[0][1]) ** 2
    )
    angle = math.degrees(math.atan2(x2 - x1, y2 - y1))
    while angle > 90:
        angle -= 180
    while angle <= -90:
        angle += 180
    return angle


def load_boundaries(dataset: Dataset) -> "object":
    """Return every field boundary in EPSG:5070 with geometry metrics."""

    import geopandas as gpd

    frames = []
    for grower in dataset.growers:
        for farm in grower.farms:
            frame = gpd.read_file(farm.boundary_path)
            frame["grower_slug"] = grower.slug
            frame["grower"] = grower.label
            frame["farm_slug"] = farm.farm_slug
            frame["state"] = farm.state or grower.state
            frame["field_id"] = frame["field_id"].astype(str)
            frames.append(frame)

    if not frames:
        raise ValueError("no boundary files discovered")

    fields = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    if fields.crs is None:
        fields = fields.set_crs("EPSG:4326")
    fields = fields.to_crs("EPSG:5070")
    fields["geometry"] = fields.geometry.make_valid()

    fields["area_m2"] = fields.geometry.area.astype(float)
    fields["area_ha"] = fields["area_m2"] / SQ_M_PER_HA
    fields["perimeter_m"] = fields.geometry.length.astype(float)
    fields["compactness"] = (
        4.0 * math.pi * fields["area_m2"] / fields["perimeter_m"].pow(2)
    )
    fields["vertices"] = fields.geometry.apply(
        lambda geom: sum(len(getattr(part, "exterior").coords) for part in getattr(geom, "geoms", [geom]))
        if geom.geom_type == "MultiPolygon"
        else len(geom.exterior.coords)
    )
    fields["bearing_deg"] = fields.geometry.apply(_bearing_deg)

    source_column = "source" if "source" in fields.columns else None
    if source_column:
        fields["source_key"] = (
            fields[source_column].map(SOURCE_MAP).fillna("other")
        )
    else:
        fields["source_key"] = "other"

    centroids = fields.geometry.centroid
    lonlat = centroids.to_crs("EPSG:4326")
    fields["lon"] = lonlat.x.to_numpy()
    fields["lat"] = lonlat.y.to_numpy()

    keep = [
        "grower", "grower_slug", "farm_slug", "state", "field_id",
        "source_key", "area_m2", "area_ha", "perimeter_m", "compactness",
        "vertices", "bearing_deg", "lon", "lat", "geometry",
    ]
    return fields[[column for column in keep if column in fields.columns]].copy()


# --------------------------------------------------------------------------- #
# Crops
# --------------------------------------------------------------------------- #


def load_cdl(dataset: Dataset) -> pd.DataFrame:
    """Load every CDL composition table into one tidy frame."""

    frames = []
    for grower in dataset.growers:
        for farm in grower.farms:
            frame = pd.read_csv(farm.cdl_path)
            frame["grower_slug"] = grower.slug
            frame["grower"] = grower.label
            frame["farm_slug"] = farm.farm_slug
            frame["field_id"] = frame["field_id"].astype(str)
            frames.append(frame)

    cdl = pd.concat(frames, ignore_index=True)
    for column in ("year", "pixel_count", "pct"):
        cdl[column] = pd.to_numeric(cdl[column], errors="coerce")
    cdl = cdl.dropna(subset=["field_id", "year", "pct"])
    cdl["year"] = cdl["year"].astype(int)
    cdl["crop_name"] = cdl["crop_name"].fillna("Other").astype(str)
    return cdl.sort_values(["grower", "field_id", "year", "crop_name"]).reset_index(drop=True)


def dominant_crops(cdl: pd.DataFrame) -> pd.DataFrame:
    """One row per field-year with the crop carrying the largest share."""

    rows = []
    for (grower, field_id, year), group in cdl.groupby(
        ["grower", "field_id", "year"], sort=True
    ):
        ranked = group.sort_values(["pct", "crop_name"], ascending=[False, True])
        top = ranked.iloc[0]
        rows.append(
            {
                "grower": grower,
                "field_id": field_id,
                "year": int(year),
                "dominant_crop": str(top["crop_name"]),
                "dominant_pct": float(top["pct"]),
                "pixels": float(group["pixel_count"].sum()),
                "classified_pct": float(group["pct"].sum()),
            }
        )
    return pd.DataFrame(rows)


def corn_after_corn(dominant: pd.DataFrame) -> pd.DataFrame:
    """Flag corn field-years whose preceding year in the window is also corn."""

    frame = dominant.sort_values(["grower", "field_id", "year"]).copy()
    frame["previous_crop"] = frame.groupby(["grower", "field_id"])["dominant_crop"].shift(1)
    frame["previous_year"] = frame.groupby(["grower", "field_id"])["year"].shift(1)
    contiguous = frame["previous_year"] == (frame["year"] - 1)
    frame["corn_after_corn"] = (
        (frame["dominant_crop"] == "Corn") & (frame["previous_crop"] == "Corn") & contiguous
    )
    frame["has_previous"] = contiguous
    return frame


def shannon_diversity(crops: Iterable[str]) -> float:
    counts = pd.Series(list(crops)).value_counts(normalize=True)
    return float(-(counts * np.log(counts)).sum())


def field_crop_summary(cdl: pd.DataFrame, dominant: pd.DataFrame) -> pd.DataFrame:
    """Per-field crop history: shares, diversity, corn years, rotation string."""

    years = sorted(dominant["year"].unique())
    rows = []
    for (grower, field_id), group in dominant.groupby(["grower", "field_id"], sort=True):
        sequence = group.sort_values("year")
        shares = (
            cdl[(cdl["grower"] == grower) & (cdl["field_id"] == field_id)]
            .groupby("crop_name")["pct"]
            .mean()
        )
        classified = float(shares.sum()) or 1.0
        rows.append(
            {
                "grower": grower,
                "field_id": field_id,
                "rotation": " -> ".join(sequence["dominant_crop"].tolist()),
                "crop_diversity": shannon_diversity(sequence["dominant_crop"]),
                "corn_years": int((sequence["dominant_crop"] == "Corn").sum()),
                "soybean_years": int((sequence["dominant_crop"] == "Soybeans").sum()),
                "dominant_crop_2023": (
                    sequence[sequence["year"] == max(years)]["dominant_crop"].iloc[0]
                    if not sequence[sequence["year"] == max(years)].empty
                    else ""
                ),
                **{
                    f"share_{name}": float(value) / classified
                    for name, value in shares.items()
                },
            }
        )
    return pd.DataFrame(rows)


def cdl_coverage(cdl: pd.DataFrame, fields: pd.DataFrame) -> pd.DataFrame:
    """Mean classified area over polygon area, per field."""

    pixels = (
        cdl.groupby(["grower", "field_id", "year"])["pixel_count"]
        .sum()
        .groupby(["grower", "field_id"])
        .mean()
        .rename("mean_pixels")
        .reset_index()
    )
    merged = fields[["grower", "field_id", "area_m2", "source_key"]].merge(
        pixels, on=["grower", "field_id"], how="left"
    )
    merged["cdl_ha"] = merged["mean_pixels"] * PIXEL_AREA_M2 / SQ_M_PER_HA
    merged["coverage"] = merged["cdl_ha"] / (merged["area_m2"] / SQ_M_PER_HA)
    return merged


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #


def load_weather(dataset: Dataset) -> pd.DataFrame:
    frames = []
    for grower in dataset.growers:
        for farm in grower.farms:
            frame = pd.read_csv(farm.weather_path)
            frame["grower_slug"] = grower.slug
            frame["grower"] = grower.label
            frame["farm_slug"] = farm.farm_slug
            frame["field_id"] = frame["field_id"].astype(str)
            frames.append(frame)

    weather = pd.concat(frames, ignore_index=True)
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce")
    weather = weather.dropna(subset=["date"])
    for column in ("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "lat", "lon"):
        weather[column] = pd.to_numeric(weather[column], errors="coerce")
    weather["year"] = weather["date"].dt.year
    weather["month"] = weather["date"].dt.month
    weather["gdd"] = (
        (weather["T2M_MAX"] + weather["T2M_MIN"]) / 2.0 - GDD_BASE_C
    ).clip(lower=0.0)
    weather["heat_day"] = (weather["T2M_MAX"] > HEAT_THRESHOLD_C).astype(int)
    return weather.sort_values(["grower", "field_id", "date"]).reset_index(drop=True)


def season_slice(weather: pd.DataFrame, config: RunConfig) -> pd.DataFrame:
    start, end = config.season_start_month, config.season_end_month
    if start <= end:
        mask = weather["month"].between(start, end)
    else:  # a window that crosses the new year
        mask = (weather["month"] >= start) | (weather["month"] <= end)
    return weather[mask].copy()


def field_year_weather(season: pd.DataFrame) -> pd.DataFrame:
    """Per-field, per-year seasonal totals. Always the first aggregation step."""

    return (
        season.groupby(["grower", "grower_slug", "field_id", "year"], sort=True)
        .agg(
            precip_mm=("PRECTOTCORR", "sum"),
            gdd=("gdd", "sum"),
            heat_days=("heat_day", "sum"),
            mean_t=("T2M", "mean"),
            days=("date", "nunique"),
        )
        .reset_index()
    )


def grower_year_weather(field_year: pd.DataFrame) -> pd.DataFrame:
    """Average the per-field totals across fields, per grower-year."""

    return (
        field_year.groupby(["grower", "grower_slug", "year"], sort=True)
        .agg(
            precip_mm=("precip_mm", "mean"),
            gdd=("gdd", "mean"),
            heat_days=("heat_days", "mean"),
            fields=("field_id", "nunique"),
        )
        .reset_index()
    )


def daily_grower_series(season: pd.DataFrame) -> pd.DataFrame:
    """Daily grower-mean GDD accumulation, averaged across fields."""

    daily = (
        season.groupby(["grower", "grower_slug", "date"], sort=True)["gdd"]
        .mean()
        .reset_index()
    )
    daily["year"] = daily["date"].dt.year
    daily = daily.sort_values(["grower", "year", "date"])
    daily["cumulative_gdd"] = daily.groupby(["grower", "year"])["gdd"].cumsum()
    daily["day_of_season"] = daily.groupby(["grower", "year"]).cumcount() + 1
    return daily


def monthly_weather(season: pd.DataFrame) -> pd.DataFrame:
    """Per-field monthly precipitation, then grown to grower-year-month means."""

    per_field = (
        season.groupby(["grower", "field_id", "year", "month"], sort=True)["PRECTOTCORR"]
        .sum()
        .reset_index()
    )
    return (
        per_field.groupby(["grower", "year", "month"], sort=True)["PRECTOTCORR"]
        .mean()
        .reset_index()
        .rename(columns={"PRECTOTCORR": "precip_mm"})
    )


def field_year_precip_map(field_year: pd.DataFrame) -> pd.DataFrame:
    """Mean seasonal precipitation per field across available years."""

    return (
        field_year.groupby(["grower", "field_id"], sort=True)["precip_mm"]
        .mean()
        .reset_index()
    )


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def spearman_with_ci(
    x: Sequence[float], y: Sequence[float], *, seed: int = 20261120, n_boot: int = 2000
) -> dict:
    from scipy.stats import spearmanr

    x_values = np.asarray(list(x), dtype=float)
    y_values = np.asarray(list(y), dtype=float)
    mask = np.isfinite(x_values) & np.isfinite(y_values)
    x_values, y_values = x_values[mask], y_values[mask]
    if len(x_values) < 3:
        return {"rho": float("nan"), "p": float("nan"), "low": float("nan"),
                "high": float("nan"), "n": int(len(x_values))}

    rho, p_value = spearmanr(x_values, y_values)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        index = rng.integers(0, len(x_values), len(x_values))
        if len(set(index.tolist())) < 3:
            continue
        value = spearmanr(x_values[index], y_values[index]).statistic
        if np.isfinite(value):
            draws.append(value)
    low, high = (
        (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
        if draws
        else (float("nan"), float("nan"))
    )
    return {"rho": float(rho), "p": float(p_value), "low": low, "high": high,
            "n": int(len(x_values))}


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> dict:
    from scipy.stats import mannwhitneyu

    left = np.asarray(list(a), dtype=float)
    right = np.asarray(list(b), dtype=float)
    left = left[np.isfinite(left)]
    right = right[np.isfinite(right)]
    if len(left) < 2 or len(right) < 2:
        return {"u": float("nan"), "p": float("nan"), "rank_biserial": float("nan"),
                "n_a": int(len(left)), "n_b": int(len(right))}
    result = mannwhitneyu(left, right, alternative="two-sided")
    rank_biserial = 2.0 * float(result.statistic) / (len(left) * len(right)) - 1.0
    return {
        "u": float(result.statistic),
        "p": float(result.pvalue),
        "rank_biserial": float(rank_biserial),
        "n_a": int(len(left)),
        "n_b": int(len(right)),
    }


def chi_square(table: pd.DataFrame) -> dict:
    from scipy.stats import chi2_contingency

    counts = table.to_numpy(dtype=float)
    counts = counts[counts.sum(axis=1) > 0][:, counts.sum(axis=0) > 0]
    if counts.shape[0] < 2 or counts.shape[1] < 2:
        return {"chi2": float("nan"), "p": float("nan"), "dof": 0,
                "cramers_v": float("nan")}
    result = chi2_contingency(counts, correction=False)
    n = counts.sum()
    v = math.sqrt(result.statistic / (n * (min(counts.shape) - 1)))
    return {
        "chi2": float(result.statistic),
        "p": float(result.pvalue),
        "dof": int(result.dof),
        "cramers_v": float(v),
    }


def variance_shares(
    frame: pd.DataFrame,
    value: str,
    *,
    group: str = "grower",
    year: str = "year",
) -> dict:
    """Sum-of-squares shares: between group, year within group, residual.

    Descriptive only. With a coarse weather grid the residual is expected to be
    zero, which is the null result this function exists to report honestly.
    """

    data = frame[[group, year, value]].dropna()
    if data.empty:
        return {"between": float("nan"), "year_within": float("nan"),
                "residual": float("nan"), "total": float("nan")}

    grand = data[value].mean()
    total_ss = float(((data[value] - grand) ** 2).sum())

    between_ss = 0.0
    year_within_ss = 0.0
    for _, group_frame in data.groupby(group, sort=True):
        group_mean = group_frame[value].mean()
        between_ss += len(group_frame) * (group_mean - grand) ** 2
        for _, year_frame in group_frame.groupby(year, sort=True):
            year_within_ss += len(year_frame) * (year_frame[value].mean() - group_mean) ** 2

    residual_ss = max(total_ss - between_ss - year_within_ss, 0.0)
    scale = total_ss or 1.0
    return {
        "between": 100.0 * between_ss / scale,
        "year_within": 100.0 * year_within_ss / scale,
        "residual": 100.0 * residual_ss / scale,
        "total": total_ss,
    }


def trend_line(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Linear fit used only as a visual guide on log area."""

    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2:
        return np.array([]), np.array([])
    slope, intercept = np.polyfit(x[mask], y[mask], 1)
    grid = np.linspace(x[mask].min(), x[mask].max(), 40)
    return grid, slope * grid + intercept


__all__ = [
    "SOURCE_MAP",
    "cdl_coverage",
    "chi_square",
    "corn_after_corn",
    "daily_grower_series",
    "dominant_crops",
    "field_crop_summary",
    "field_year_precip_map",
    "field_year_weather",
    "grower_year_weather",
    "load_boundaries",
    "load_cdl",
    "load_weather",
    "mann_whitney",
    "monthly_weather",
    "season_slice",
    "shannon_diversity",
    "spearman_with_ci",
    "trend_line",
    "variance_shares",
    "wilson_interval",
]
