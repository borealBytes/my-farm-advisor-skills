"""Cross-grower synthesis: multi-panel summary figure."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _calculate_area_acres(coords: list) -> float:
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


def _load_boundary_features(boundary_path: Path) -> list[dict]:
    with open(boundary_path) as f:
        geojson = json.load(f)
    return geojson.get("features", [])


def synthesis_panel(growers: dict, output_dir: Path) -> None:
    """Generate a 2x3 multi-panel summary comparing IL, IA, NE."""
    print("\n" + "=" * 60)
    print("Synthesis: Three Farms Side-by-Side")
    print("=" * 60)

    states_order = ["Illinois", "Iowa", "Nebraska"]
    metrics = {s: {} for s in states_order}

    for grower_slug, info in growers.items():
        state = info["state"]

        # 1. Mean field size
        features = _load_boundary_features(Path(info["boundary"]))
        areas = [_calculate_area_acres(f.get("geometry", {}).get("coordinates", [[]])[0]) for f in features]
        metrics[state]["mean_field_size"] = np.mean(areas) if areas else np.nan

        # 2. Dominant crop pct (2025)
        cdl_path = Path(info["cdl_updated"])
        if cdl_path.exists():
            cdl = pd.read_csv(cdl_path)
            cdl_2025 = cdl[cdl["year"] == 2025]
            dominant = cdl_2025.loc[cdl_2025.groupby("field_id")["pct"].idxmax()]
            metrics[state]["dominant_pct"] = dominant["pct"].mean()
        else:
            metrics[state]["dominant_pct"] = np.nan

        # 3. Crop diversity
        rot_path = Path(info["rotation"])
        if rot_path.exists():
            rot = pd.read_csv(rot_path)
            metrics[state]["crop_diversity"] = rot["crop_diversity"].mean()
        else:
            metrics[state]["crop_diversity"] = np.nan

        # 4. Mean GDD
        fields_dir = Path(info["fields_dir"])
        gdds = []
        if fields_dir.exists():
            for field_dir in fields_dir.iterdir():
                if not field_dir.is_dir():
                    continue
                weather_csv = field_dir / "weather" / "daily_weather.csv"
                if weather_csv.exists():
                    wdf = pd.read_csv(weather_csv)
                    if "T2M_MIN" in wdf.columns and "T2M_MAX" in wdf.columns:
                        avg = (wdf["T2M_MIN"] + wdf["T2M_MAX"]) / 2
                        gdd = (avg - 10.0).clip(lower=0).sum()
                        gdds.append(gdd)
        metrics[state]["mean_gdd"] = np.mean(gdds) if gdds else np.nan

        # 5. Precip CV
        cvs = []
        if fields_dir.exists():
            for field_dir in fields_dir.iterdir():
                if not field_dir.is_dir():
                    continue
                weather_csv = field_dir / "weather" / "daily_weather.csv"
                if weather_csv.exists():
                    wdf = pd.read_csv(weather_csv)
                    if "PRECTOTCORR" in wdf.columns:
                        p = wdf["PRECTOTCORR"]
                        if p.mean() and p.mean() != 0:
                            cvs.append(p.std() / p.mean() * 100)
        metrics[state]["precip_cv"] = np.mean(cvs) if cvs else np.nan

        # 6. Corn/Soy ratio (2025)
        if cdl_path.exists():
            cdl = pd.read_csv(cdl_path)
            cdl_2025 = cdl[cdl["year"] == 2025]
            corn = cdl_2025[cdl_2025["crop_name"] == "Corn"]["acreage"].sum()
            soy = cdl_2025[cdl_2025["crop_name"] == "Soybeans"]["acreage"].sum()
            metrics[state]["corn_soy_ratio"] = corn / soy if soy > 0 else np.nan
        else:
            metrics[state]["corn_soy_ratio"] = np.nan

    # Build the 2x3 grid with larger figure and better spacing
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle("Three Farms: Side-by-Side Summary (2021–2025)", fontsize=16, fontweight="bold")

    plot_data = [
        ("Mean Field Size\n(acres)", [metrics[s].get("mean_field_size", np.nan) for s in states_order]),
        ("Dominant Crop\nShare (%)", [metrics[s].get("dominant_pct", np.nan) for s in states_order]),
        ("Crop Diversity\n(unique crops)", [metrics[s].get("crop_diversity", np.nan) for s in states_order]),
        ("Mean GDD\n(°C, cumulative)", [metrics[s].get("mean_gdd", np.nan) for s in states_order]),
        ("Precip Variability\n(CV %)", [metrics[s].get("precip_cv", np.nan) for s in states_order]),
        ("Corn/Soy\nRatio", [metrics[s].get("corn_soy_ratio", np.nan) for s in states_order]),
    ]

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    for ax, (title, values) in zip(axes.flat, plot_data):
        bars = ax.bar(states_order, values, color=colors)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel("")
        # Annotate bars with smaller font and offset
        for bar, val in zip(bars, values):
            if not np.isnan(val):
                offset = max(values) * 0.02 if max(values) > 0 else 0.1
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + offset,
                        f"{val:.1f}", ha="center", va="bottom", fontsize=8)

        # Add 20% headroom so annotations never overlap chart boundary
        vals_clean = [v for v in values if not np.isnan(v)]
        if vals_clean:
            ax.set_ylim(0, max(vals_clean) * 1.2)

    plt.subplots_adjust(top=0.92, hspace=0.35, wspace=0.3)
    out = output_dir / "09_synthesis_three_farms.png"
    plt.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.3)
    plt.close()
    print(f"  Saved: {out.name}")

    # Print summary table
    print("\n  Summary Metrics:")
    print(f"  {'Metric':<25} {'IL':>10} {'IA':>10} {'NE':>10}")
    print("  " + "-" * 60)
    for title, values in plot_data:
        label = title.replace("\n", " ")
        print(f"  {label:<25} {values[0]:>10.1f} {values[1]:>10.1f} {values[2]:>10.1f}")
