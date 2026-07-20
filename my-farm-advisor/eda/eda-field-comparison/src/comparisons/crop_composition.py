"""Crop composition analysis: Figures 14, 15, and 16."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def crop_composition_analysis(growers: dict, output_dir: Path) -> None:
    """Generate Figure 14 (crop pct composition by state), Figure 15 (acreage share over time), and Figure 16 (total acreage by crop and state)."""
    print("\n" + "=" * 60)
    print("Crop Composition Analysis")
    print("=" * 60)

    # Load CDL data
    frames = []
    for grower_slug, info in growers.items():
        cdl_path = Path(info["cdl_updated"])
        if cdl_path.exists():
            df = pd.read_csv(cdl_path)
            df["State"] = info["state"]
            frames.append(df)

    if not frames:
        print("  No CDL data found.")
        return

    cdl = pd.concat(frames, ignore_index=True)

    # Define crop colors (consistent with Figure 11B + additions)
    crop_colors = {
        "Corn": "#FFD700",
        "Soybeans": "#228B22",
        "Grass/Pasture": "#8B4513",
        "Alfalfa": "#90EE90",
        "Forest": "#006400",
        "Winter Wheat": "#DAA520",
        "Fallow/Idle": "#A9A9A9",
    }
    default_color = "#808080"

    # ---------------------------
    # Figure 14: Crop composition by state (mean pct)
    # ---------------------------
    # Compute mean pct per (State, crop_name) across all fields and years
    comp = cdl.groupby(["State", "crop_name"])["pct"].mean().reset_index()

    # Pivot for plotting: states as clusters, crops as bars within each cluster
    pivot_pct = comp.pivot(index="crop_name", columns="State", values="pct").fillna(0)
    states_order = ["Illinois", "Iowa", "Nebraska"]

    # Get all crops, sorted by total mean pct descending
    all_crops = pivot_pct.sum(axis=1).sort_values(ascending=False).index.tolist()

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(states_order))
    bar_width = 0.10
    n_crops = len(all_crops)
    offsets = np.linspace(-(n_crops - 1) * bar_width / 2, (n_crops - 1) * bar_width / 2, n_crops)

    for i, crop in enumerate(all_crops):
        vals = [pivot_pct.loc[crop, s] if s in pivot_pct.columns else 0 for s in states_order]
        ax.bar(x + offsets[i], vals, bar_width, label=crop, color=crop_colors.get(crop, default_color), edgecolor="black", linewidth=0.3)

    ax.set_xlabel("State", fontsize=12)
    ax.set_ylabel("Mean Crop Percentage (%)", fontsize=12)
    ax.set_title("Crop Composition by State (2021–2025 Average)", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(states_order)
    ax.legend(title="Crop", loc="upper right", fontsize=8)
    ax.set_ylim(0, 75)
    plt.tight_layout()
    out14 = output_dir / "14_crop_composition_by_state.png"
    plt.savefig(out14, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out14.name}")

    # ---------------------------
    # Figure 15: Crop acreage share over time (2021–2025)
    # ---------------------------
    # Aggregate minor crops into "Other"
    major_crops = {"Corn", "Soybeans", "Grass/Pasture", "Alfalfa"}
    cdl_plot = cdl.copy()
    cdl_plot["crop_plot"] = cdl_plot["crop_name"].apply(
        lambda c: c if c in major_crops else "Other"
    )

    # Sum acreage per (State, year, crop_plot)
    acreage = cdl_plot.groupby(["State", "year", "crop_plot"])["acreage"].sum().reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)

    for i, state in enumerate(states_order):
        ax = axes[i]
        state_data = acreage[acreage["State"] == state]

        # Pivot: year x crop
        pivot_acre = state_data.pivot(index="year", columns="crop_plot", values="acreage").fillna(0)
        pivot_acre = pivot_acre.reindex(columns=[c for c in crop_colors if c in pivot_acre.columns] + (["Other"] if "Other" in pivot_acre.columns else []), fill_value=0)

        # Plot grouped bars
        years = pivot_acre.index
        n_crops_plot = len(pivot_acre.columns)
        bar_width = 0.15
        offsets2 = np.linspace(-(n_crops_plot - 1) * bar_width / 2, (n_crops_plot - 1) * bar_width / 2, n_crops_plot)

        for j, crop in enumerate(pivot_acre.columns):
            vals = pivot_acre[crop].values
            ax.bar(years + offsets2[j], vals, bar_width, label=crop,
                   color=crop_colors.get(crop, default_color), edgecolor="black", linewidth=0.3)

        ax.set_title(f"{state}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Year", fontsize=10)
        if i == 0:
            ax.set_ylabel("Total Acreage", fontsize=12)
        ax.set_xticks(years)
        ax.set_xticklabels(years, rotation=0)
        ax.set_ylim(0, 2500)
        ax.legend(fontsize=7, loc="upper right")

    fig.suptitle("Crop Acreage Share by Year (2021–2025)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out15 = output_dir / "15_crop_acreage_share_trend.png"
    plt.savefig(out15, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out15.name}")

    # ---------------------------
    # Figure 16: Crop total acreage by state (sum acreage)
    # ---------------------------
    # Compute sum acreage per (State, crop_name) across all fields and years
    comp_ac = cdl.groupby(["State", "crop_name"])["acreage"].sum().reset_index()
    pivot_ac = comp_ac.pivot(index="crop_name", columns="State", values="acreage").fillna(0)

    # Get all crops, sorted by total acreage descending
    all_crops_ac = pivot_ac.sum(axis=1).sort_values(ascending=False).index.tolist()

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(states_order))
    bar_width = 0.10
    n_crops = len(all_crops_ac)
    offsets = np.linspace(-(n_crops - 1) * bar_width / 2, (n_crops - 1) * bar_width / 2, n_crops)

    for i, crop in enumerate(all_crops_ac):
        vals = [pivot_ac.loc[crop, s] if s in pivot_ac.columns else 0 for s in states_order]
        ax.bar(x + offsets[i], vals, bar_width, label=crop,
               color=crop_colors.get(crop, default_color), edgecolor="black", linewidth=0.3)

    ax.set_xlabel("State", fontsize=12)
    ax.set_ylabel("Total Acreage", fontsize=12)
    ax.set_title("Crop Acreage by State (2021–2025 Total)", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(states_order)
    ax.legend(title="Crop", loc="upper right", fontsize=8)
    ax.set_ylim(0, 10000)
    plt.tight_layout()
    out16 = output_dir / "16_crop_acreage_by_state.png"
    plt.savefig(out16, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out16.name}")
