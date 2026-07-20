"""Time-series comparisons: crop rotation timeline, trends, and stability."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def timeseries_analysis(growers: dict, output_dir: Path) -> None:
    """Generate 11A, 11B, 12, 13: time-series visualizations."""
    print("\n" + "=" * 60)
    print("Time-Series Analysis")
    print("=" * 60)

    # Load all CDL data
    cdl_frames = []
    for grower_slug, info in growers.items():
        cdl_path = Path(info["cdl_updated"])
        if cdl_path.exists():
            df = pd.read_csv(cdl_path)
            df["State"] = info["state"]
            cdl_frames.append(df)
    
    if not cdl_frames:
        print("  No CDL data for time-series.")
        return
    
    cdl = pd.concat(cdl_frames, ignore_index=True)
    
    # 11A: Crop rotation heatmap (field_id x year, color = crop)
    # Get dominant crop per field per year
    dominant = cdl.loc[cdl.groupby(["field_id", "year"])["pct"].idxmax()].copy()
    
    # Create pivot table
    pivot = dominant.pivot(index="field_id", columns="year", values="crop_name")
    
    # Map crops to numeric codes for colormap
    all_crops = sorted(dominant["crop_name"].unique())
    crop_map = {crop: i for i, crop in enumerate(all_crops)}
    pivot_numeric = pivot.map(lambda x: crop_map.get(x, -1) if pd.notna(x) else -1)
    
    # Add State info for sorting
    field_states = dominant[["field_id", "State"]].drop_duplicates().set_index("field_id")
    pivot_numeric = pivot_numeric.join(field_states)
    pivot_numeric = pivot_numeric.sort_values(["State", "field_id"])
    state_labels = pivot_numeric["State"]
    pivot_numeric = pivot_numeric.drop(columns=["State"])
    
    plt.figure(figsize=(10, 14))
    cmap = plt.colormaps.get_cmap("tab20").resampled(len(all_crops))
    im = plt.imshow(pivot_numeric.values, aspect="auto", cmap=cmap, vmin=-0.5, vmax=len(all_crops)-0.5)
    
    plt.yticks(range(len(pivot_numeric)), pivot_numeric.index, fontsize=8)
    plt.xticks(range(len(pivot_numeric.columns)), pivot_numeric.columns)
    plt.xlabel("Year", fontsize=12)
    plt.ylabel("Field ID", fontsize=12)
    plt.title("Crop Rotation Timeline by Field", fontsize=14, fontweight="bold")
    
    # Add state separators
    state_changes = state_labels.ne(state_labels.shift()).cumsum()
    for i in range(1, state_changes.max() + 1):
        idx = state_changes[state_changes == i].index
        if len(idx) > 0:
            y_pos = list(pivot_numeric.index).index(idx[-1]) + 0.5
            plt.axhline(y=y_pos, color="black", linewidth=1)
    
    # Colorbar with crop labels
    cbar = plt.colorbar(im, shrink=0.6)
    cbar.set_ticks(range(len(all_crops)))
    cbar.set_ticklabels(all_crops)
    cbar.set_label("Crop Type", fontsize=10)
    
    plt.tight_layout()
    out1 = output_dir / "11A_crop_rotation_heatmap.png"
    plt.savefig(out1, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out1.name}")

    # 11B: Stacked area chart (total acreage by crop over years)
    yearly_crop = cdl.groupby(["State", "year", "crop_name"])["acreage"].sum().reset_index()
    
    fig, axes = plt.subplots(3, 1, figsize=(10, 12))
    states_order = ["Illinois", "Iowa", "Nebraska"]
    colors = {"Corn": "#FFD700", "Soybeans": "#228B22", "Grass/Pasture": "#8B4513", 
              "Forest": "#006400", "Alfalfa": "#90EE90"}
    
    for i, state in enumerate(states_order):
        ax = axes[i]
        state_data = yearly_crop[yearly_crop["State"] == state]
        pivot_state = state_data.pivot(index="year", columns="crop_name", values="acreage").fillna(0)
        
        # Ensure all years present
        for year in range(2021, 2026):
            if year not in pivot_state.index:
                pivot_state.loc[year] = 0
        pivot_state = pivot_state.sort_index()
        
        ax.stackplot(pivot_state.index, *[pivot_state[col] for col in pivot_state.columns],
                     labels=pivot_state.columns, colors=[colors.get(c, "gray") for c in pivot_state.columns],
                     alpha=0.8)
        ax.set_title(f"{state}: Crop Acreage Over Time", fontsize=12, fontweight="bold")
        ax.set_xlabel("Year", fontsize=10)
        ax.set_ylabel("Acreage", fontsize=10)
        ax.legend(loc="upper left", fontsize=8)
        ax.set_xticks(range(2021, 2026))
    
    plt.tight_layout()
    out2 = output_dir / "11B_crop_rotation_stacked.png"
    plt.savefig(out2, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out2.name}")

    # 12: Dominant crop share trend over years
    dominant_trend = dominant.groupby(["State", "year"])["pct"].mean().reset_index()
    
    plt.figure(figsize=(10, 5))
    for state in states_order:
        subset = dominant_trend[dominant_trend["State"] == state]
        plt.plot(subset["year"], subset["pct"], marker="o", label=state, linewidth=2)
    
    plt.title("Dominant Crop Share Trend (2021–2025)", fontsize=14, fontweight="bold")
    plt.xlabel("Year", fontsize=12)
    plt.ylabel("Mean Dominant Crop Percentage (%)", fontsize=12)
    plt.ylim(0, 105)
    plt.xticks(range(2021, 2026))
    plt.legend(title="State", fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    out3 = output_dir / "12_dominant_crop_share_trend.png"
    plt.savefig(out3, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out3.name}")

    # 13: Field size stability (total acreage per field vs year)
    field_year = cdl.groupby(["State", "field_id", "year"])["acreage"].sum().reset_index()
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for i, state in enumerate(states_order):
        ax = axes[i]
        state_data = field_year[field_year["State"] == state]
        for field_id in state_data["field_id"].unique():
            field_data = state_data[state_data["field_id"] == field_id]
            ax.plot(field_data["year"], field_data["acreage"], alpha=0.5, linewidth=1)
        
        # Mean line
        mean_acreage = state_data.groupby("year")["acreage"].mean()
        ax.plot(mean_acreage.index, mean_acreage.values, "k--", linewidth=2, label="Mean")
        
        ax.set_title(f"{state}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Year", fontsize=10)
        ax.set_ylabel("Total Acreage", fontsize=10)
        ax.set_xticks(range(2021, 2026))
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    
    fig.suptitle("Field Size Stability Over Time", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out4 = output_dir / "13_field_size_stability.png"
    plt.savefig(out4, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out4.name}")
