#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportArgumentType=false, reportCallIssue=false, reportReturnType=false
"""Generate SSURGO soil profile cards for each field and farm-level comparisons."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_REPO = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from reporting_bootstrap import ensure_skill_path  # noqa: E402


ensure_skill_path("farm-intelligence-reporting")

from paths import (
    farm_boundary_path,
    farm_ssurgo_summary_path,
    farm_summary_path,
    field_summary_path,
)
from reporting_bootstrap import field_slug_map_from_inventory

_SCRIPT = Path(__file__)
_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")


def plot_soil_properties_card(
    field_data: pd.DataFrame, field_id: str, output_path: Path
) -> None:
    """Generate soil properties visualization card."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.patch.set_facecolor("#fafaf9")

    if field_data.empty:
        for ax in axes.flat:
            ax.text(
                0.5,
                0.5,
                "No soil data",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        plt.savefig(
            output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        plt.close(fig)
        return

    # Get the first (and should be only) row for this field
    row = field_data.iloc[0]

    # Plot 1: Organic Matter and pH
    ax = axes[0, 0]
    categories = ["OM (%)", "pH", "Clay (%)", "Sand (%)"]
    values = [
        row.get("avg_om_pct", 0) or 0,
        row.get("avg_ph", 7) or 7,  # raw value: a rescaled bar with a raw label once printed pH 1.7 for a 6.7 soil
        row.get("avg_clay_pct", 0) or 0,
        row.get("avg_sand_pct", 0) or 0,
    ]
    colors = ["#8B4513", "#4169E1", "#D2691E", "#F4A460"]
    bars = ax.barh(categories, values, color=colors, alpha=0.7, edgecolor="black")
    ax.set_xlabel("Value")
    ax.set_title("Soil Properties", fontsize=11, fontweight="bold")
    ax.set_xlim(0, max(values) * 1.2)
    # Add value labels
    for bar, val in zip(bars, values):
        ax.text(
            val + 0.1,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}",
            va="center",
            fontsize=9,
        )

    # Plot 2: Water Storage and CEC
    ax = axes[0, 1]
    metrics = ["AWS (in)", "CEC"]
    values2 = [row.get("total_aws_inches", 0) or 0, row.get("avg_cec", 0) or 0]
    colors2 = ["#20B2AA", "#9370DB"]
    bars2 = ax.bar(metrics, values2, color=colors2, alpha=0.7, edgecolor="black")
    ax.set_ylabel("Value")
    ax.set_title("Water & CEC", fontsize=11, fontweight="bold")
    # Add value labels
    for bar, val in zip(bars2, values2):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.5,
            f"{val:.1f}",
            ha="center",
            fontsize=9,
        )

    # Plot 3: Component and Horizon counts
    ax = axes[1, 0]
    counts = ["MUKEYs", "Components", "Horizons"]
    values3 = [
        row.get("n_mukeys", 0) or 0,
        row.get("n_components", 0) or 0,
        row.get("n_horizons", 0) or 0,
    ]
    colors3 = ["#FF6B6B", "#4ECDC4", "#45B7D1"]
    bars3 = ax.bar(counts, values3, color=colors3, alpha=0.7, edgecolor="black")
    ax.set_ylabel("Count")
    ax.set_title("Soil Complexity", fontsize=11, fontweight="bold")
    # Add value labels
    for bar, val in zip(bars3, values3):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.2,
            f"{int(val)}",
            ha="center",
            fontsize=9,
        )

    # Plot 4: Text summary
    ax = axes[1, 1]
    ax.axis("off")

    dominant_soil = row.get("dominant_soil", "Unknown")
    drainage = row.get("drainage_class", "Unknown")
    ph_constraint = row.get("ph_constraint", "Unknown")
    erosion = row.get("erosion_risk", "Unknown")

    summary_text = f"""
    Field: {field_id}
    
    Dominant Soil:
    {dominant_soil}
    
    Drainage Class:
    {drainage}
    
    pH Constraint:
    {ph_constraint}
    
    Erosion Risk:
    {erosion}
    """

    ax.text(
        0.1,
        0.9,
        summary_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.3),
    )
    ax.set_title("Soil Summary", fontsize=11, fontweight="bold")

    fig.suptitle(
        f"Soil Profile: {field_id}", fontsize=14, fontweight="bold", y=0.98
    )
    plt.tight_layout()
    plt.savefig(
        output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)


def plot_texture_triangle_card(
    field_data: pd.DataFrame, field_id: str, output_path: Path
) -> None:
    """Generate texture visualization card."""
    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_facecolor("#fafaf9")

    if field_data.empty:
        ax.text(
            0.5,
            0.5,
            "No soil data available",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        plt.savefig(
            output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        plt.close(fig)
        return

    row = field_data.iloc[0]

    # Get texture values
    clay = row.get("avg_clay_pct", 0) or 0
    sand = row.get("avg_sand_pct", 0) or 0
    silt = 100 - clay - sand  # Calculate silt

    # Create a simple texture visualization
    # Draw a triangle representing soil texture
    from matplotlib.patches import Polygon

    # Triangle vertices (Clay, Sand, Silt)
    triangle = Polygon(
        [[0, 0], [1, 0], [0.5, 0.866]], fill=False, edgecolor="black", linewidth=2
    )
    ax.add_patch(triangle)

    # Calculate position in triangle
    # Normalize to percentages
    total = clay + sand + silt
    if total > 0:
        clay_pct = clay / total
        sand_pct = sand / total
        silt_pct = silt / total

        # Convert to Cartesian coordinates
        x = 0.5 * (2 * sand_pct + silt_pct) / (clay_pct + sand_pct + silt_pct)
        y = 0.866 * silt_pct / (clay_pct + sand_pct + silt_pct)

        # Plot the point
        ax.scatter(
            x,
            y,
            s=500,
            c="#8B4513",
            marker="o",
            edgecolors="black",
            linewidths=2,
            zorder=5,
        )
        ax.annotate(
            f"{field_id}\nC:{clay:.0f}% S:{sand:.0f}% Si:{silt:.0f}%",
            (x, y),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="yellow", alpha=0.7),
        )

    # Add labels
    ax.text(0, -0.05, "Clay", ha="center", fontsize=12, fontweight="bold")
    ax.text(1, -0.05, "Sand", ha="center", fontsize=12, fontweight="bold")
    ax.text(0.5, 0.9, "Silt", ha="center", fontsize=12, fontweight="bold")

    ax.set_xlim(-0.1, 1.1)
    ax.set_ylim(-0.1, 1.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Soil Texture: {field_id}", fontsize=14, fontweight="bold")

    plt.tight_layout()
    plt.savefig(
        output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)


def plot_farm_comparison_card(
    all_fields_data: dict[str, pd.DataFrame], output_path: Path
) -> None:
    """Generate farm-level soil comparison card."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.patch.set_facecolor("#fafaf9")

    if not all_fields_data:
        for ax in axes.flat:
            ax.text(
                0.5,
                0.5,
                "No soil data available",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        plt.savefig(
            output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        plt.close(fig)
        return

    field_ids = []
    om_values = []
    ph_values = []
    aws_values = []
    clay_values = []

    for field_id, field_data in sorted(all_fields_data.items()):
        if field_data.empty:
            continue
        row = field_data.iloc[0]
        field_ids.append(field_id)
        om_values.append(row.get("avg_om_pct", 0) or 0)
        ph_values.append(row.get("avg_ph", 0) or 0)
        aws_values.append(row.get("total_aws_inches", 0) or 0)
        clay_values.append(row.get("avg_clay_pct", 0) or 0)

    if not field_ids:
        for ax in axes.flat:
            ax.text(
                0.5,
                0.5,
                "No valid soil data",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        plt.savefig(
            output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        plt.close(fig)
        return

    x_pos = range(len(field_ids))
    colors = plt.cm.tab10(np.linspace(0, 1, len(field_ids)))

    # Plot 1: Organic Matter
    ax = axes[0, 0]
    bars = ax.bar(x_pos, om_values, color=colors, alpha=0.7, edgecolor="black")
    ax.set_ylabel("Organic Matter (%)")
    ax.set_title("Organic Matter by Field", fontsize=11, fontweight="bold")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(field_ids, rotation=45, ha="right")
    for bar, val in zip(bars, om_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.05,
            f"{val:.1f}",
            ha="center",
            fontsize=8,
        )

    # Plot 2: pH
    ax = axes[0, 1]
    bars = ax.bar(x_pos, ph_values, color=colors, alpha=0.7, edgecolor="black")
    ax.set_ylabel("pH")
    ax.set_title("Soil pH by Field", fontsize=11, fontweight="bold")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(field_ids, rotation=45, ha="right")
    ax.axhline(y=7, color="red", linestyle="--", alpha=0.5, label="Neutral pH")
    for bar, val in zip(bars, ph_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.05,
            f"{val:.1f}",
            ha="center",
            fontsize=8,
        )

    # Plot 3: Available Water Storage
    ax = axes[1, 0]
    bars = ax.bar(x_pos, aws_values, color=colors, alpha=0.7, edgecolor="black")
    ax.set_ylabel("AWS (inches)")
    ax.set_title("Available Water Storage by Field", fontsize=11, fontweight="bold")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(field_ids, rotation=45, ha="right")
    for bar, val in zip(bars, aws_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.5,
            f"{val:.0f}",
            ha="center",
            fontsize=8,
        )

    # Plot 4: Clay Content
    ax = axes[1, 1]
    bars = ax.bar(x_pos, clay_values, color=colors, alpha=0.7, edgecolor="black")
    ax.set_ylabel("Clay (%)")
    ax.set_title("Clay Content by Field", fontsize=11, fontweight="bold")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(field_ids, rotation=45, ha="right")
    for bar, val in zip(bars, clay_values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.5,
            f"{val:.0f}",
            ha="center",
            fontsize=8,
        )

    fig.suptitle("Farm Soil Comparison", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(
        output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    plt.close(fig)


def main() -> None:
    print("=" * 60)
    print("SSURGO Soil Profile Cards")
    print("=" * 60)

    fields_path = farm_boundary_path(_DEFAULT_GROWER, _DEFAULT_FARM)
    if not fields_path.exists():
        print(f"ERROR: Fields file not found: {fields_path}")
        sys.exit(1)

    fields = gpd.read_file(fields_path)
    field_slug_map = field_slug_map_from_inventory()

    # Load SSURGO data
    ssurgo_path = farm_ssurgo_summary_path(_DEFAULT_GROWER, _DEFAULT_FARM)
    if not ssurgo_path.exists():
        print(f"WARNING: SSURGO data not found: {ssurgo_path}")
        print("Skipping soil card generation.")
        sys.exit(0)

    ssurgo_df = pd.read_csv(ssurgo_path)

    all_fields_data = {}

    # Generate per-field cards
    for idx, field_row in fields.iterrows():
        field_id = str(field_row.get("field_id", f"field_{idx}"))
        field_short = field_id

        print(f"\nProcessing field: {field_id}")

        # Get soil data for this field
        field_soil = ssurgo_df[ssurgo_df["field_id"] == field_id]
        all_fields_data[field_id] = field_soil

        # Generate cards
        field_slug = field_slug_map.get(field_id, "")
        if not field_slug:
            continue
        output_path_1 = field_summary_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_properties.png"
        )
        output_path_1.parent.mkdir(parents=True, exist_ok=True)
        plot_soil_properties_card(field_soil, field_short, output_path_1)
        print("  ✓ properties")

        output_path_2 = field_summary_path(
            _DEFAULT_GROWER, _DEFAULT_FARM, field_slug, "soil_texture.png"
        )
        plot_texture_triangle_card(field_soil, field_short, output_path_2)
        print("  ✓ texture")

    # Generate farm-level comparison
    print("\nGenerating farm comparison card...")
    farm_output = farm_summary_path(
        _DEFAULT_GROWER, _DEFAULT_FARM, "soil_cards/farm_comparison.png"
    )
    farm_output.parent.mkdir(parents=True, exist_ok=True)
    plot_farm_comparison_card(all_fields_data, farm_output)
    print("  ✓ farm_comparison")

    print("\n" + "=" * 60)
    print(f"Soil cards complete → {farm_output.parent}")
    print("=" * 60)


if __name__ == "__main__":
    main()
