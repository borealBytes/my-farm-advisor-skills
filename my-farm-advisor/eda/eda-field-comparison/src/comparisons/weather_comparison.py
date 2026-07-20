"""Category C: Weather comparison analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd


def _load_gdd_for_county(gdd_parquet_dir: Path, county_name: str, state_fips: str, year: int) -> float | None:
    """Load GDD from pipeline's existing county-level parquet files."""
    pq_path = gdd_parquet_dir / f"gdd_by_fips_{year}.parquet"
    if not pq_path.exists():
        return None
    try:
        df = pd.read_parquet(pq_path)
        match = df[(df["county_name"].str.contains(county_name, case=False, na=False)) &
                   (df["state_fips"].astype(str).str.zfill(2) == str(state_fips).zfill(2))]
        if not match.empty:
            return float(match.iloc[0]["gdd_total_c"])
    except Exception:
        pass
    return None


def _compute_gdd_from_daily(daily_df: pd.DataFrame, base_temp: float = 10.0) -> float:
    """Compute cumulative GDD from daily T2M_MIN/T2M_MAX as fallback."""
    if "T2M_MIN" not in daily_df.columns or "T2M_MAX" not in daily_df.columns:
        return np.nan
    avg = (daily_df["T2M_MIN"] + daily_df["T2M_MAX"]) / 2
    gdd = (avg - base_temp).clip(lower=0).sum()
    return gdd


def _load_daily_weather_for_field(field_weather_path: Path) -> pd.DataFrame:
    df = pd.read_csv(field_weather_path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def weather_analysis(growers: dict, output_dir: Path) -> dict:
    """Run Category C: GDD distribution, precip variability, temp-precip correlation.
    
    Returns dict of statistical results for summary.
    """
    print("\n" + "=" * 60)
    print("Category C: Weather Analysis")
    print("=" * 60)

    gdd_parquet_dir = Path(growers[list(growers.keys())[0]]["data_root"]) / "data-pipeline/shared/corn_maturity/tables"

    records = []
    for grower_slug, info in growers.items():
        state = info["state"]
        fields_dir = Path(info["fields_dir"])
        if not fields_dir.exists():
            continue
        for field_dir in fields_dir.iterdir():
            if not field_dir.is_dir():
                continue
            field_id = field_dir.name
            weather_csv = field_dir / "weather" / "daily_weather.csv"
            if not weather_csv.exists():
                continue

            daily = _load_daily_weather_for_field(weather_csv)
            if daily.empty:
                continue

            gdd_val = None
            county_name = info.get("county_name", "")
            state_fips = info.get("state_fips", "")
            if county_name and state_fips:
                for year in range(2021, 2026):
                    gdd_year = _load_gdd_for_county(gdd_parquet_dir, county_name, state_fips, year)
                    if gdd_year is not None:
                        gdd_val = gdd_val or 0
                        gdd_val += gdd_year

            if gdd_val is None:
                gdd_val = _compute_gdd_from_daily(daily)

            precip = daily["PRECTOTCORR"] if "PRECTOTCORR" in daily.columns else pd.Series([])
            precip_cv = (precip.std() / precip.mean() * 100) if precip.mean() and precip.mean() != 0 else np.nan

            records.append({
                "field_id": field_id,
                "State": state,
                "gdd": gdd_val,
                "precip_cv": precip_cv,
            })

    if not records:
        print("  No weather data found.")
        return {}

    df = pd.DataFrame(records)
    stats_result = {}
    order = ["Illinois", "Iowa", "Nebraska"]

    # C1: GDD distribution by State
    plt.figure(figsize=(8, 5))
    subset = df.dropna(subset=["gdd"])
    if not subset.empty:
        sns.violinplot(data=subset, x="State", y="gdd", hue="State", legend=False, palette="Set2", order=order)
        plt.title("Growing Degree Days (GDD) Distribution by State", fontsize=14, fontweight="bold")
        plt.xlabel("State", fontsize=12)
        plt.ylabel("Cumulative GDD (°C)", fontsize=12)
        plt.tight_layout()
        out1 = output_dir / "06_weather_gdd_distribution.png"
        plt.savefig(out1, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()
        print(f"  Saved: {out1.name}")
        
        # ANOVA on GDD across states
        groups = [subset[subset["State"] == s]["gdd"].dropna() for s in order if not subset[subset["State"] == s].empty]
        if len(groups) >= 2:
            f_stat, p_anova = stats.f_oneway(*groups)
            # Eta-squared (effect size)
            ss_between = sum(len(g) * (g.mean() - subset["gdd"].mean())**2 for g in groups)
            ss_total = ((subset["gdd"] - subset["gdd"].mean())**2).sum()
            eta_sq = ss_between / ss_total if ss_total > 0 else 0
            
            stats_result["gdd_anova"] = {
                "category": "C. Weather",
                "test": "One-way ANOVA",
                "variables": "GDD across States",
                "f_statistic": f_stat,
                "p_value": p_anova,
                "eta_squared": eta_sq,
                "n": len(subset),
            }
            print(f"  GDD ANOVA: F={f_stat:.3f}, p={p_anova:.4f}, eta²={eta_sq:.3f}")
            
            # Tukey HSD post-hoc
            try:
                tukey = pairwise_tukeyhsd(subset["gdd"], subset["State"], alpha=0.05)
                print(f"  Tukey HSD post-hoc:")
                for row in tukey.summary().data[1:]:
                    print(f"    {row[0]} vs {row[1]}: p={row[3]:.4f}, reject={row[6]}")
            except Exception as e:
                print(f"  Tukey HSD skipped: {e}")
    else:
        print("  No GDD data available for violin plot.")

    # C2: Precipitation variability (CV) by State
    plt.figure(figsize=(8, 5))
    subset2 = df.dropna(subset=["precip_cv"])
    if not subset2.empty:
        sns.boxplot(data=subset2, x="State", y="precip_cv", hue="State", legend=False, palette="Set2", order=order)
        plt.title("Precipitation Variability by State", fontsize=14, fontweight="bold")
        plt.xlabel("State", fontsize=12)
        plt.ylabel("Precipitation CV (%)", fontsize=12)
        plt.tight_layout()
        out2 = output_dir / "07_weather_precip_variability.png"
        plt.savefig(out2, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()
        print(f"  Saved: {out2.name}")
        
        # Kruskal-Wallis test for precip CV (non-normal)
        groups_cv = [subset2[subset2["State"] == s]["precip_cv"].dropna() for s in order if not subset2[subset2["State"] == s].empty]
        if len(groups_cv) >= 2:
            h_stat, p_kw = stats.kruskal(*groups_cv)
            # Epsilon-squared effect size approximation
            n_total = len(subset2)
            eps_sq = (h_stat / (n_total - 1)) if n_total > 1 else 0
            
            stats_result["precip_kruskal"] = {
                "category": "C. Weather",
                "test": "Kruskal-Wallis H-test",
                "variables": "Precipitation CV across States",
                "h_statistic": h_stat,
                "p_value": p_kw,
                "epsilon_squared": eps_sq,
                "n": n_total,
            }
            print(f"  Precip CV Kruskal-Wallis: H={h_stat:.3f}, p={p_kw:.4f}, epsilon²={eps_sq:.3f}")
    else:
        print("  No precipitation CV data available.")

    # C3: Monthly T2M_MAX vs PRECTOTCORR correlation by State
    corr_records = []
    for grower_slug, info in growers.items():
        state = info["state"]
        weather_csv = Path(info["weather"])
        if not weather_csv.exists():
            continue
        wdf = pd.read_csv(weather_csv)
        if "date" not in wdf.columns:
            continue
        wdf["date"] = pd.to_datetime(wdf["date"])
        wdf["month"] = wdf["date"].dt.month

        if "T2M_MAX" in wdf.columns and "PRECTOTCORR" in wdf.columns:
            monthly = wdf.groupby("month")[["T2M_MAX", "PRECTOTCORR"]].mean()
            corr = monthly["T2M_MAX"].corr(monthly["PRECTOTCORR"])
            corr_records.append({"State": state, "correlation": corr})

    if corr_records:
        corr_df = pd.DataFrame(corr_records)
        plt.figure(figsize=(6, 4))
        colors = ["coral" if c < 0 else "steelblue" for c in corr_df["correlation"]]
        sns.barplot(data=corr_df, x="State", y="correlation", hue="State", legend=False, palette=colors, order=order)
        plt.axhline(0, color="black", linewidth=0.8)
        plt.title("Monthly Temperature vs Precipitation Correlation", fontsize=14, fontweight="bold")
        plt.xlabel("State", fontsize=12)
        plt.ylabel("Pearson r", fontsize=12)
        plt.ylim(-1, 1)
        plt.tight_layout()
        out3 = output_dir / "08_weather_temp_precip_correlation.png"
        plt.savefig(out3, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()
        print(f"  Saved: {out3.name}")
        for _, row in corr_df.iterrows():
            print(f"    {row['State']}: r={row['correlation']:.3f}")
    else:
        print("  No monthly weather correlation data available.")
    
    return stats_result
