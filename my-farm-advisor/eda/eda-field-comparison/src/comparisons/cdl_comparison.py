"""Category B: CDL / cropland data comparison analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


def cdl_analysis(growers: dict, output_dir: Path) -> dict:
    """Run Category B: dominant crop share, crop diversity, corn vs soy correlation.
    
    Returns dict of statistical results for summary.
    """
    print("\n" + "=" * 60)
    print("Category B: CDL / Cropland Data Analysis")
    print("=" * 60)

    # Load updated CDL composition files
    cdl_frames = []
    rotation_frames = []
    for grower_slug, info in growers.items():
        cdl_path = Path(info["cdl_updated"])
        rot_path = Path(info["rotation"])
        if cdl_path.exists():
            df = pd.read_csv(cdl_path)
            df["State"] = info["state"]
            cdl_frames.append(df)
        if rot_path.exists():
            df = pd.read_csv(rot_path)
            df["State"] = info["state"]
            rotation_frames.append(df)

    if not cdl_frames:
        print("  No CDL data found.")
        return {}

    cdl = pd.concat(cdl_frames, ignore_index=True)
    rotation = pd.concat(rotation_frames, ignore_index=True) if rotation_frames else pd.DataFrame()

    stats_result = {}

    # B1: Dominant crop share (pct) by State
    dominant = cdl.loc[cdl.groupby(["field_id", "year"])["pct"].idxmax()].copy()

    plt.figure(figsize=(8, 5))
    order = ["Illinois", "Iowa", "Nebraska"]
    sns.boxplot(data=dominant, x="State", y="pct", hue="State", legend=False, palette="Set2", order=order)
    plt.title("Dominant Crop Share by State", fontsize=14, fontweight="bold")
    plt.xlabel("State", fontsize=12)
    plt.ylabel("Dominant Crop Percentage (%)", fontsize=12)
    plt.ylim(0, 105)
    plt.tight_layout()
    out1 = output_dir / "03_cdl_dominant_crop_share.png"
    plt.savefig(out1, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out1.name}")

    # B2: Crop diversity index by field, grouped by State
    if not rotation.empty and "crop_diversity" in rotation.columns:
        div_by_field = rotation.groupby(["State", "field_id"])["crop_diversity"].first().reset_index()
        plt.figure(figsize=(12, 6))
        # Vertical bars with rotated x labels
        sns.barplot(data=div_by_field, x="field_id", y="crop_diversity", hue="State", palette="Set2", dodge=False)
        plt.title("Crop Diversity Index by Field", fontsize=14, fontweight="bold")
        plt.xlabel("Field ID", fontsize=12)
        plt.ylabel("Unique Crops (5-year history)", fontsize=12)
        plt.xticks(rotation=45, ha="right", fontsize=8)
        plt.tight_layout()
        out2 = output_dir / "04_cdl_crop_diversity.png"
        plt.savefig(out2, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()
        print(f"  Saved: {out2.name}")
    else:
        print("  Rotation data unavailable for diversity plot.")

    # B3: Corn acreage vs Soybean acreage (2025)
    cdl_2025 = cdl[cdl["year"] == 2025].copy()
    corn = cdl_2025[cdl_2025["crop_name"] == "Corn"][["field_id", "State", "acreage"]].rename(columns={"acreage": "corn_acres"})
    soy = cdl_2025[cdl_2025["crop_name"] == "Soybeans"][["field_id", "acreage"]].rename(columns={"acreage": "soy_acres"})
    merged = corn.merge(soy, on="field_id", how="outer").fillna(0)

    if len(merged) >= 3:
        plt.figure(figsize=(8, 6))
        colors = {"Illinois": "#1f77b4", "Iowa": "#ff7f0e", "Nebraska": "#2ca02c"}
        for state in merged["State"].unique():
            subset = merged[merged["State"] == state]
            plt.scatter(subset["corn_acres"], subset["soy_acres"], label=state, color=colors.get(state, "gray"), alpha=0.7, s=80)

        # Regression line for all points
        if len(merged) >= 2:
            z = np.polyfit(merged["corn_acres"], merged["soy_acres"], 1)
            p = np.poly1d(z)
            x_line = np.linspace(merged["corn_acres"].min(), merged["corn_acres"].max(), 100)
            plt.plot(x_line, p(x_line), "r--", alpha=0.5, label="Trend")

        r, pval = stats.pearsonr(merged["corn_acres"], merged["soy_acres"])
        
        # Linear regression for full stats
        slope, intercept, r_value, p_value_reg, std_err = stats.linregress(merged["corn_acres"], merged["soy_acres"])
        slope_ci = 1.96 * std_err
        
        stats_result = {
            "category": "B. CDL",
            "test": "Linear regression",
            "variables": "Corn acreage vs Soybean acreage (2025)",
            "pearson_r": r,
            "pearson_p": pval,
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_value**2,
            "slope_ci_95": (slope - slope_ci, slope + slope_ci),
            "p_value": p_value_reg,
            "n": len(merged),
        }
        
        # Annotate plot with equation
        equation_text = f"y = {slope:.2f}x + {intercept:.2f}\nR² = {r_value**2:.3f}, p = {p_value_reg:.4f}"
        plt.annotate(equation_text, xy=(0.05, 0.95), xycoords="axes fraction",
                    fontsize=10, verticalalignment="top",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
        
        plt.title("Corn vs Soybean Acreage (2025)", fontsize=14, fontweight="bold")
        plt.xlabel("Corn Acreage", fontsize=12)
        plt.ylabel("Soybean Acreage", fontsize=12)
        plt.legend()
        plt.tight_layout()
        out3 = output_dir / "05_cdl_corn_vs_soy.png"
        plt.savefig(out3, dpi=300, bbox_inches="tight", pad_inches=0.2)
        plt.close()
        print(f"  Saved: {out3.name}")
        print(f"  Correlation (corn vs soy acreage): r={r:.3f}, p={pval:.4f}")
        print(f"    Regression: y = {slope:.2f}x + {intercept:.2f}, R² = {r_value**2:.3f}")
        print(f"    Slope 95% CI: [{slope - slope_ci:.2f}, {slope + slope_ci:.2f}]")
        if pval < 0.05:
            print(f"    → Significant {'negative' if r < 0 else 'positive'} relationship")
        else:
            print(f"    → Not significant (p >= 0.05)")
    else:
        print("  Insufficient data for corn vs soy correlation.")
    
    return stats_result
