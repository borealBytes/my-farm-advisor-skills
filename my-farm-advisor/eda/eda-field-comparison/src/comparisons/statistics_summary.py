"""Statistics summary: write plain text and markdown summaries of all analyses."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def write_stats_summary(all_stats: list[dict], output_dir: Path) -> None:
    """Write both stats_summary.txt and stats_summary.md."""
    print("\n" + "=" * 60)
    print("Statistics Summary")
    print("=" * 60)

    # Plain text version
    txt_lines = []
    txt_lines.append("=" * 60)
    txt_lines.append("FIELD-LEVEL EDA STATISTICAL SUMMARY")
    txt_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    txt_lines.append("=" * 60)
    txt_lines.append("")

    for stat in all_stats:
        if not stat:
            continue
        txt_lines.append("-" * 60)
        txt_lines.append(f"Category: {stat.get('category', 'Unknown')}")
        txt_lines.append(f"Test: {stat.get('test', 'Unknown')}")
        txt_lines.append(f"Variables: {stat.get('variables', 'Unknown')}")
        txt_lines.append("")
        
        for key, value in stat.items():
            if key in ("category", "test", "variables"):
                continue
            if isinstance(value, float):
                txt_lines.append(f"  {key}: {value:.4f}")
            elif isinstance(value, tuple) and len(value) == 2:
                txt_lines.append(f"  {key}: [{value[0]:.4f}, {value[1]:.4f}]")
            else:
                txt_lines.append(f"  {key}: {value}")
        txt_lines.append("")

    txt_path = output_dir / "stats_summary.txt"
    with open(txt_path, "w") as f:
        f.write("\n".join(txt_lines))
    print(f"  Saved: {txt_path.name}")

    # Markdown version
    md_lines = []
    md_lines.append("# Field-Level EDA Statistical Summary")
    md_lines.append("")
    md_lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append("")
    md_lines.append("## Overview")
    md_lines.append("")
    md_lines.append("This report summarizes the statistical tests performed during the Assignment 2 field-level EDA.")
    md_lines.append("")

    for stat in all_stats:
        if not stat:
            continue
        md_lines.append(f"### {stat.get('category', 'Unknown')}: {stat.get('test', 'Unknown')}")
        md_lines.append("")
        md_lines.append(f"**Variables:** {stat.get('variables', 'Unknown')}")
        md_lines.append("")
        md_lines.append("| Metric | Value |")
        md_lines.append("|--------|-------|")
        
        for key, value in stat.items():
            if key in ("category", "test", "variables"):
                continue
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                md_lines.append(f"| {label} | {value:.4f} |")
            elif isinstance(value, tuple) and len(value) == 2:
                md_lines.append(f"| {label} | [{value[0]:.4f}, {value[1]:.4f}] |")
            else:
                md_lines.append(f"| {label} | {value} |")
        
        md_lines.append("")
        
        # Interpretation
        if "p_value" in stat:
            p = stat["p_value"]
            alpha = 0.05
            sig = "significant" if p < alpha else "not significant"
            md_lines.append(f"> **Interpretation:** The result is statistically {sig} (p = {p:.4f}, α = {alpha}).")
            md_lines.append("")
        
        if "eta_squared" in stat:
            eta = stat["eta_squared"]
            if eta < 0.01:
                size = "negligible"
            elif eta < 0.06:
                size = "small"
            elif eta < 0.14:
                size = "medium"
            else:
                size = "large"
            md_lines.append(f"> **Effect size:** η² = {eta:.3f} ({size} effect).")
            md_lines.append("")
        
        if "r_squared" in stat:
            r2 = stat["r_squared"]
            md_lines.append(f"> **Explained variance:** R² = {r2:.3f} ({r2*100:.1f}% of variance explained).")
            md_lines.append("")

    md_lines.append("---")
    md_lines.append("")
    md_lines.append("*End of summary*")

    md_path = output_dir / "stats_summary.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"  Saved: {md_path.name}")
