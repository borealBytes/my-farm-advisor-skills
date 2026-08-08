#!/usr/bin/env python3
"""
metrics.py — Compute field-level agricultural intelligence scores.

Metrics:
  - Soil Health Score (SHS)      → 0–100
  - Sustainability Index (SI)     → 0–100
  - Conservation Priority Score   → 0–100 (inverse of SI)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Soil Health Score (SHS)
# ---------------------------------------------------------------------------

def _score_ph(ph: float) -> float:
    """Score pH: optimal 6.0–7.0 = 25 pts; linear penalties outside."""
    if pd.isna(ph):
        return 0.0
    if 6.0 <= ph <= 7.0:
        return 25.0
    elif ph < 6.0:
        return max(0.0, 25.0 - (6.0 - ph) * 8.0)
    else:
        return max(0.0, 25.0 - (ph - 7.0) * 8.0)


def _score_om(om: float) -> float:
    """Score organic matter %: ≥ 4% = 25 pts; linear down to 0."""
    if pd.isna(om):
        return 0.0
    return min(25.0, om / 4.0 * 25.0)


def _score_drainage(drainage: str) -> float:
    """Score drainage class."""
    if pd.isna(drainage):
        return 10.0
    d = str(drainage).lower()
    if "well drained" in d and "moderately" not in d:
        return 20.0
    if "moderately well drained" in d:
        return 18.0
    if "somewhat poorly" in d:
        return 12.0
    if "poorly drained" in d:
        return 8.0
    if "very poorly" in d:
        return 4.0
    return 10.0


def _score_awc(awc: float) -> float:
    """Score available water capacity: ≥ 0.2 = 20 pts; linear down."""
    if pd.isna(awc):
        return 0.0
    return min(20.0, awc / 0.2 * 20.0)


def _score_texture(clay: float, sand: float, silt: float) -> float:
    """Score texture balance: loamy ideal = 10 pts."""
    if pd.isna(clay) or pd.isna(sand) or pd.isna(silt):
        return 5.0
    # Loamy roughly: clay 15-35%, sand 25-55%, silt 25-55%
    score = 10.0
    if clay > 45:
        score -= 5.0
    elif clay < 10:
        score -= 3.0
    if sand > 75:
        score -= 5.0
    elif sand < 15:
        score -= 2.0
    return max(0.0, score)


def compute_soil_health_score(soil_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-field Soil Health Score from horizon-level SSURGO data.

    Aggregates by field_id (weighted mean across horizons/components).
    Returns DataFrame with columns: field_id, shs, plus component scores.
    """
    if soil_df is None or soil_df.empty:
        return pd.DataFrame()

    df = soil_df.copy()
    # Ensure required columns exist
    for col in ["ph1to1h2o_r", "om_r", "drainagecl", "awc_r", "claytotal_r", "sandtotal_r", "silttotal_r"]:
        if col not in df.columns:
            df[col] = np.nan

    # Compute per-row scores
    df["ph_score"] = df["ph1to1h2o_r"].apply(_score_ph)
    df["om_score"] = df["om_r"].apply(_score_om)
    df["drainage_score"] = df["drainagecl"].apply(_score_drainage)
    df["awc_score"] = df["awc_r"].apply(_score_awc)
    df["texture_score"] = df.apply(
        lambda r: _score_texture(r.get("claytotal_r"), r.get("sandtotal_r"), r.get("silttotal_r")), axis=1
    )

    df["shs"] = df["ph_score"] + df["om_score"] + df["drainage_score"] + df["awc_score"] + df["texture_score"]

    # Aggregate to field level (simple mean across horizons; could weight by hz thickness)
    field_scores = df.groupby("field_id").agg(
        shs=("shs", "mean"),
        ph_score=("ph_score", "mean"),
        om_score=("om_score", "mean"),
        drainage_score=("drainage_score", "mean"),
        awc_score=("awc_score", "mean"),
        texture_score=("texture_score", "mean"),
        ph_mean=("ph1to1h2o_r", "mean"),
        om_mean=("om_r", "mean"),
        awc_mean=("awc_r", "mean"),
        clay_mean=("claytotal_r", "mean"),
        sand_mean=("sandtotal_r", "mean"),
        silt_mean=("silttotal_r", "mean"),
    ).reset_index()

    # Round
    for col in ["shs", "ph_score", "om_score", "drainage_score", "awc_score", "texture_score",
                "ph_mean", "om_mean", "awc_mean", "clay_mean", "sand_mean", "silt_mean"]:
        field_scores[col] = field_scores[col].round(2)

    return field_scores


# ---------------------------------------------------------------------------
# Rotation Diversity (Shannon Index)
# ---------------------------------------------------------------------------

def _shannon_index(pct_series: pd.Series) -> float:
    p = pct_series / 100.0
    p = p[p > 0]
    if len(p) == 0:
        return 0.0
    return -np.sum(p * np.log(p))


def compute_rotation_diversity(cdl_years: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Compute per-field crop-diversity Shannon index across all available CDL years."""
    if not cdl_years:
        return pd.DataFrame()

    frames = []
    for year, df in cdl_years.items():
        if df is None or df.empty:
            continue
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    all_cdl = pd.concat(frames, ignore_index=True)
    if "field_id" not in all_cdl.columns:
        return pd.DataFrame()

    # For each field, count how many times each crop appears
    crop_counts = all_cdl.groupby(["field_id", "crop_name"]).size().reset_index(name="count")
    field_totals = crop_counts.groupby("field_id")["count"].sum().reset_index(name="total")
    crop_counts = crop_counts.merge(field_totals, on="field_id")
    crop_counts["pct"] = crop_counts["count"] / crop_counts["total"] * 100.0

    diversity = crop_counts.groupby("field_id").apply(
        lambda g: _shannon_index(g["pct"]), include_groups=False
    ).reset_index(name="shannon_diversity")

    return diversity


# ---------------------------------------------------------------------------
# Weather Stress Resilience
# ---------------------------------------------------------------------------

def compute_weather_stress(weather_df: pd.DataFrame, growing_months: tuple[int, ...] = (5, 6, 7, 8, 9)) -> pd.DataFrame:
    """Compute per-field weather stress metrics for the growing season.

    Stress indicators:
      - Drought days: PRECTOTCORR < 1 mm
      - Heat stress days: T2M_MAX > 32°C
    """
    if weather_df is None or weather_df.empty:
        return pd.DataFrame()

    if "field_id" not in weather_df.columns:
        return pd.DataFrame()

    # Filter to growing season
    grow = weather_df[weather_df["month"].isin(growing_months)].copy()
    if grow.empty:
        return pd.DataFrame()

    # Per-field growing-season summaries
    summaries = grow.groupby("field_id").agg(
        total_precip=("PRECTOTCORR", "sum"),
        avg_temp=("T2M", "mean"),
        max_temp=("T2M_MAX", "max"),
        drought_days=("PRECTOTCORR", lambda s: (s < 1.0).sum()),
        heat_stress_days=("T2M_MAX", lambda s: (s > 32.0).sum()),
    ).reset_index()

    # Score: fewer stress days = higher resilience (0–25 scale, then scaled to 0–20)
    max_drought = summaries["drought_days"].max() if len(summaries) > 0 else 1
    max_heat = summaries["heat_stress_days"].max() if len(summaries) > 0 else 1

    summaries["drought_score"] = (1 - summaries["drought_days"] / max(max_drought, 1)) * 10
    summaries["heat_score"] = (1 - summaries["heat_stress_days"] / max(max_heat, 1)) * 10
    summaries["weather_resilience"] = (summaries["drought_score"] + summaries["heat_score"]).round(2)

    return summaries


# ---------------------------------------------------------------------------
# Growing Degree Days (GDD)
# ---------------------------------------------------------------------------

def compute_gdd_summary(weather_df: pd.DataFrame, base_temp: float = 10.0) -> pd.DataFrame:
    """Compute cumulative GDD per field per year."""
    if weather_df is None or weather_df.empty or "field_id" not in weather_df.columns:
        return pd.DataFrame()

    df = weather_df.copy()
    df["gdd_daily"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2.0 - base_temp).clip(lower=0)
    df["year"] = df["date"].dt.year

    gdd = df.groupby(["field_id", "year"])["gdd_daily"].sum().reset_index(name="annual_gdd")
    gdd_mean = gdd.groupby("field_id")["annual_gdd"].mean().reset_index(name="avg_annual_gdd")
    return gdd_mean


# ---------------------------------------------------------------------------
# Sustainability Index (SI)
# ---------------------------------------------------------------------------

def compute_sustainability_index(
    soil_scores: pd.DataFrame,
    rotation_diversity: pd.DataFrame,
    weather_stress: pd.DataFrame,
    ndvi_stability: pd.DataFrame,
) -> pd.DataFrame:
    """Compute Sustainability Index per field.

    Weights:
      - Soil Health Score: 40%
      - Rotation Diversity: 20%
      - Weather Stress Resilience: 20%
      - NDVI Stability: 20%
    """
    # Start with soil scores (guaranteed to have field_id)
    df = soil_scores[["field_id", "shs"]].copy()

    # Merge rotation diversity (scale 0–20)
    if rotation_diversity is not None and not rotation_diversity.empty:
        df = df.merge(rotation_diversity, on="field_id", how="left")
        df["shannon_diversity"] = df["shannon_diversity"].fillna(0)
        # Shannon index typically 0–2 for simple rotations; scale to 0–20
        df["rotation_score"] = (df["shannon_diversity"] / 2.0 * 20.0).clip(upper=20.0)
    else:
        df["rotation_score"] = 10.0  # Neutral default

    # Merge weather stress (0–20)
    if weather_stress is not None and not weather_stress.empty:
        df = df.merge(weather_stress[["field_id", "weather_resilience"]], on="field_id", how="left")
        df["weather_resilience"] = df["weather_resilience"].fillna(10.0)
    else:
        df["weather_resilience"] = 10.0

    # Merge NDVI stability (0–20)
    if ndvi_stability is not None and not ndvi_stability.empty:
        df = df.merge(ndvi_stability[["field_id", "ndvi_stability_score"]], on="field_id", how="left")
        df["ndvi_stability_score"] = df["ndvi_stability_score"].fillna(10.0)
    else:
        df["ndvi_stability_score"] = 10.0

    # Compute SI
    df["si"] = (
        df["shs"] * 0.40
        + df["rotation_score"]
        + df["weather_resilience"]
        + df["ndvi_stability_score"]
    ).round(2)

    # Conservation Priority = inverse
    df["conservation_priority"] = (100.0 - df["si"]).round(2)

    return df
