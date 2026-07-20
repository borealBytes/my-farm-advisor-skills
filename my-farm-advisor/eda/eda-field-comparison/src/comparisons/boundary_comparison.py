"""Category A: Field boundary comparison analysis."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import pearsonr, spearmanr


def _load_boundary_features(boundary_path: Path) -> list[dict]:
    with open(boundary_path) as f:
        geojson = json.load(f)
    return geojson.get("features", [])


def _calculate_area_acres(coords: list) -> float:
    """Shoelace formula for polygon area, rough degree-to-acre conversion."""
    n = len(coords) - 1
    if n < 3:
        return 0.0
    area_sq_deg = 0.0
    for i in range(n):
        j = (i + 1) % n
        area_sq_deg += coords[i][0] * coords[j][1]
        area_sq_deg -= coords[j][0] * coords[i][1]
    area_sq_deg = abs(area_sq_deg) / 2.0
    return area_sq_deg * 2264000


def _build_boundary_df(growers: dict[str, dict]) -> pd.DataFrame:
    records = []
    for grower_slug, info in growers.items():
        boundary_path = Path(info["boundary"])
        features = _load_boundary_features(boundary_path)
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [[]])[0]
            area = _calculate_area_acres(coords)
            records.append({
                "grower": grower_slug,
                "State": info["state"],
                "field_id": props.get("field_id", "unknown"),
                "area_acres": area,
            })
    return pd.DataFrame(records)


def boundary_analysis(growers: dict, rotation_df: pd.DataFrame, output_dir: Path) -> dict:
    """Run Category A: boundary size distribution, count vs acreage, area vs diversity correlation.
    
    Returns dict of statistical results for summary.
    """
    print("\n" + "=" * 60)
    print("Category A: Field Boundary Analysis")
    print("=" * 60)

    df = _build_boundary_df(growers)
    if df.empty:
        print("  No boundary data found.")
        return {}

    # A1: Field size distribution by State
    plt.figure(figsize=(12, 5))
    states_order = ["Illinois", "Iowa", "Nebraska"]
    for i, state in enumerate(states_order, 1):
        subset = df[df["State"] == state]["area_acres"]
        if subset.empty:
            continue
        plt.subplot(1, 3, i)
        sns.histplot(subset, kde=True, bins=8, color="steelblue")
        plt.title(f"{state}\n(n={len(subset)})")
        plt.xlabel("Field Area (acres)")
        plt.ylabel("Count")
    plt.suptitle("Field Size Distribution by State", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out1 = output_dir / "01_boundary_size_distribution.png"
    plt.savefig(out1, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out1.name}")

    # A2: Field count vs total acreage by State
    summary = df.groupby("State").agg(
        field_count=("area_acres", "count"),
        total_acres=("area_acres", "sum"),
        mean_acres=("area_acres", "mean"),
    ).reindex(states_order)

    x = np.arange(len(summary))
    width = 0.35
    fig, ax1 = plt.subplots(figsize=(9, 6))
    bars1 = ax1.bar(x - width / 2, summary["field_count"], width, label="Field Count", color="steelblue")
    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width / 2, summary["total_acres"], width, label="Total Acres", color="coral")
    ax1.set_xlabel("State", fontsize=12)
    ax1.set_ylabel("Field Count", color="steelblue", fontsize=12)
    ax2.set_ylabel("Total Acres", color="coral", fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(summary.index)
    ax1.set_title("Field Count vs Total Acreage by State", fontsize=14, fontweight="bold")
    ax1.set_ylim(0, 12)
    ax2.set_ylim(0, 4500)
    
    # Annotate bars cleanly
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.2,
                f'{int(height)}', ha='center', va='bottom', fontsize=9, color='steelblue')
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 80,
                f'{int(height)}', ha='center', va='bottom', fontsize=9, color='coral')
    
    # Both legends to top right
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
    plt.tight_layout()
    out2 = output_dir / "02_boundary_count_vs_acreage.png"
    plt.savefig(out2, dpi=300, bbox_inches="tight", pad_inches=0.3)
    plt.close()
    print(f"  Saved: {out2.name}")

    # A3: Correlation: boundary area vs crop diversity
    stats_result = {}
    diversity = rotation_df.groupby("field_id")["crop_diversity"].first().reset_index()
    merged = df.merge(diversity, on="field_id", how="inner")
    if len(merged) >= 3:
        r, p = pearsonr(merged["area_acres"], merged["crop_diversity"])
        rho, p_spear = spearmanr(merged["area_acres"], merged["crop_diversity"])
        ci_low = r - 1.96 * np.sqrt((1 - r**2) / (len(merged) - 2))
        ci_high = r + 1.96 * np.sqrt((1 - r**2) / (len(merged) - 2))
        stats_result = {
            "category": "A. Boundaries",
            "test": "Pearson + Spearman correlation",
            "variables": "Field area vs crop diversity",
            "pearson_r": r,
            "pearson_p": p,
            "spearman_rho": rho,
            "spearman_p": p_spear,
            "ci_95": (ci_low, ci_high),
            "n": len(merged),
            "r_squared": r**2,
        }
        print(f"  Correlation (area vs crop diversity):")
        print(f"    Pearson r={r:.3f}, p={p:.4f}, R²={r**2:.3f}")
        print(f"    Spearman rho={rho:.3f}, p={p_spear:.4f}")
        print(f"    95% CI: [{ci_low:.3f}, {ci_high:.3f}]")
        if p < 0.05:
            print(f"    → Significant {'positive' if r > 0 else 'negative'} relationship")
        else:
            print(f"    → Not significant (p >= 0.05)")
    else:
        print("  Insufficient data for area vs diversity correlation.")
    
    return stats_result
