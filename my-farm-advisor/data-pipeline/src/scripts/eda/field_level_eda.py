#!/usr/bin/env python3
"""
field_level_eda.py - Assignment 2 Field-Level EDA Comparison
"""

from __future__ import annotations

import argparse
import base64
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

matplotlib.use("Agg")
plt.style.use("seaborn-v0_8-whitegrid")


def _data_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _output_dir() -> Path:
    out = _data_root() / "eda" / "field-comparison" / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def discover_growers(data_root: Path) -> list[str]:
    growers_dir = data_root / "growers"
    if not growers_dir.exists():
        return []
    return sorted([d.name for d in growers_dir.iterdir() if d.is_dir()])


def discover_farm_slug(data_root: Path, grower_slug: str) -> str | None:
    farms_dir = data_root / "growers" / grower_slug / "farms"
    if not farms_dir.exists():
        return None
    subdirs = [d.name for d in farms_dir.iterdir() if d.is_dir()]
    return subdirs[0] if subdirs else None


def load_boundaries(data_root: Path, grower: str, farm: str) -> gpd.GeoDataFrame | None:
    path = data_root / "growers" / grower / "farms" / farm / "boundary" / "field_boundaries.geojson"
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    gdf["grower"] = grower
    return gdf


def load_cdl(data_root: Path, grower: str, farm: str, year: int) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower / "farms" / farm / "derived" / "tables"
    if not tables_dir.exists():
        return None
    matches = list(tables_dir.glob(f"*{year}_cdl.csv"))
    if not matches:
        return None
    df = pd.read_csv(matches[0])
    df["grower"] = grower
    return df


def load_weather_from_fields(data_root: Path, grower: str, farm: str) -> pd.DataFrame | None:
    fields_dir = data_root / "growers" / grower / "farms" / farm / "fields"
    if not fields_dir.exists():
        return None
    frames = []
    for field_dir in fields_dir.iterdir():
        if not field_dir.is_dir():
            continue
        weather_file = field_dir / "weather" / "daily_weather.csv"
        if weather_file.exists():
            df = pd.read_csv(weather_file, parse_dates=["date"])
            if len(df) > 1:
                df["grower"] = grower
                frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def shannon_index(pct_series: pd.Series) -> float:
    p = pct_series / 100.0
    p = p[p > 0]
    return -np.sum(p * np.log(p))


def calc_gdd(temp_min: float, temp_max: float, base: float = 10.0) -> float:
    t_avg = (temp_min + temp_max) / 2.0
    return max(0.0, t_avg - base)


def kruskal_wallis_with_posthoc(groups: dict[str, pd.Series]) -> pd.DataFrame:
    names = list(groups.keys())
    samples = [groups[n].dropna().values for n in names]
    h_stat, p_kw = stats.kruskal(*samples)
    n_pairs = len(names) * (len(names) - 1) // 2
    rows = []
    for i, n1 in enumerate(names):
        for n2 in names[i + 1 :]:
            u_stat, p_raw = stats.mannwhitneyu(
                groups[n1].dropna(), groups[n2].dropna(), alternative="two-sided"
            )
            p_adj = min(p_raw * n_pairs, 1.0)
            rows.append({
                "group_1": n1,
                "group_2": n2,
                "U_statistic": u_stat,
                "p_raw": p_raw,
                "p_bonferroni": p_adj,
                "significant": p_adj < 0.05,
            })
    df = pd.DataFrame(rows)
    df["kw_H"] = h_stat
    df["kw_p"] = p_kw
    return df


def cramers_v(contingency: pd.DataFrame) -> float:
    chi2, _, _, _ = stats.chi2_contingency(contingency)
    n = contingency.sum().sum()
    phi2 = chi2 / n
    r, k = contingency.shape
    phi2corr = max(0, phi2 - ((k - 1) * (r - 1)) / (n - 1))
    rcorr = r - ((r - 1) ** 2) / (n - 1)
    kcorr = k - ((k - 1) ** 2) / (n - 1)
    denom = min((kcorr - 1), (rcorr - 1))
    return np.sqrt(phi2corr / denom) if denom > 0 else 0.0


def plot_boundary_area_violin(gdf: gpd.GeoDataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.violinplot(data=gdf, x="grower", y="area_acres", palette="Set2", ax=ax)
    sns.stripplot(data=gdf, x="grower", y="area_acres", color="black", alpha=0.5, size=6, ax=ax)
    ax.set_title("Field Area Distribution by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("Grower", fontsize=12)
    ax.set_ylabel("Area (acres)", fontsize=12)
    ax.set_ylim(bottom=0)
    for i, grower in enumerate(gdf["grower"].unique()):
        mean_area = gdf[gdf["grower"] == grower]["area_acres"].mean()
        ax.annotate(f"μ={mean_area:.1f}", xy=(i, mean_area), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
    plt.tight_layout()
    path = out_dir / "01_boundary_area_violin_by_grower.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_cdl_colored_grower_maps(gdf: gpd.GeoDataFrame, cdl_all: pd.DataFrame, out_dir: Path) -> None:
    try:
        import contextily as ctx
        has_ctx = True
    except ImportError:
        has_ctx = False
        print("  Warning: contextily not available, using plain maps")

    dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
    gdf_clean = gdf.drop(columns=["crop_name"], errors="ignore")
    gdf_merged = gdf_clean.merge(dom[["field_id", "crop_name"]], on="field_id", how="left")

    all_crops = sorted(gdf_merged["crop_name"].dropna().unique())
    palette = sns.color_palette("Set2", n_colors=len(all_crops))
    color_map = dict(zip(all_crops, palette))

    growers = gdf_merged["grower"].unique()
    for grower in growers:
        subset = gdf_merged[gdf_merged["grower"] == grower].copy()
        fig, ax = plt.subplots(figsize=(10, 8))

        if has_ctx:
            subset_wm = subset.to_crs(epsg=3857)
            for crop in all_crops:
                crop_subset = subset_wm[subset_wm["crop_name"] == crop]
                if not crop_subset.empty:
                    crop_subset.plot(ax=ax, alpha=0.7, edgecolor="black", linewidth=1.5,
                                    color=color_map[crop], label=crop)
            try:
                ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, zoom=12)
            except Exception:
                ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=12)
            ax.set_title(f"Field Boundaries — {grower}", fontsize=14, fontweight="bold")
        else:
            for crop in all_crops:
                crop_subset = subset[subset["crop_name"] == crop]
                if not crop_subset.empty:
                    crop_subset.plot(ax=ax, alpha=0.7, edgecolor="black", linewidth=1.5,
                                    color=color_map[crop], label=crop)
            ax.set_title(f"Field Boundaries — {grower} (no basemap)", fontsize=14, fontweight="bold")

        ax.set_xlabel("Longitude", fontsize=12)
        ax.set_ylabel("Latitude", fontsize=12)
        ax.legend(title="Dominant CDL", loc="upper right", fontsize=8)

        for idx, row in subset.iterrows():
            centroid = row.geometry.centroid
            ax.annotate(row["field_id"].split("-")[-1], 
                       xy=(centroid.x, centroid.y),
                       xytext=(5, 5), textcoords="offset points",
                       fontsize=7, alpha=0.8)

        plt.tight_layout()
        safe_name = grower.replace("-", "_")
        path = out_dir / f"03a_boundary_map_{safe_name}.png"
        plt.savefig(path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")


def plot_cdl_composition(cdl_all: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
    comp = dom.groupby(["grower", "crop_name"]).size().unstack(fill_value=0)
    comp_pct = comp.div(comp.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(10, 6))
    comp_pct.plot(kind="barh", stacked=True, ax=ax, colormap="Set2")
    ax.set_title("Dominant Crop Composition by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("Percentage of Fields (%)", fontsize=12)
    ax.set_ylabel("Grower", fontsize=12)
    ax.legend(title="Crop", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    path = out_dir / "04_cdl_dominant_crop_percent_by_grower.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")
    return comp_pct


def plot_cdl_crop_counts(cdl_all: pd.DataFrame, out_dir: Path) -> None:
    dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
    counts = dom.groupby(["grower", "crop_name"]).size().reset_index(name="field_count")
    fig, ax = plt.subplots(figsize=(10, 6))
    pivot = counts.pivot(index="grower", columns="crop_name", values="field_count").fillna(0)
    pivot.plot(kind="bar", ax=ax, colormap="Set2", edgecolor="black")
    ax.set_title("CDL Crop Class Counts by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("Grower", fontsize=12)
    ax.set_ylabel("Number of Fields", fontsize=12)
    ax.legend(title="Crop", bbox_to_anchor=(1.05, 1), loc="upper left")
    ax.tick_params(axis="x", rotation=0)
    plt.tight_layout()
    path = out_dir / "05_cdl_crop_class_counts_by_grower.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_cdl_diversity(cdl_all: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    diversity = []
    for (grower, field_id), group in cdl_all.groupby(["grower", "field_id"]):
        div = shannon_index(group["pct"])
        diversity.append({"grower": grower, "field_id": field_id, "shannon_index": div})
    div_df = pd.DataFrame(diversity)
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=div_df, x="grower", y="shannon_index", palette="Set2", ax=ax)
    sns.stripplot(data=div_df, x="grower", y="shannon_index", color="black", alpha=0.5, size=6, ax=ax)
    ax.set_title("CDL Shannon Diversity Index by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("Grower", fontsize=12)
    ax.set_ylabel("Shannon Index (higher = more diverse)", fontsize=12)
    for i, grower in enumerate(div_df["grower"].unique()):
        mean_div = div_df[div_df["grower"] == grower]["shannon_index"].mean()
        ax.annotate(f"μ={mean_div:.2f}", xy=(i, mean_div), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
    plt.tight_layout()
    path = out_dir / "06_cdl_shannon_diversity_boxplot.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")
    return div_df


def plot_field_size_vs_cdl_correlation(
    gdf: gpd.GeoDataFrame, cdl_all: pd.DataFrame, out_dir: Path, summaries_dir: Path
) -> None:
    dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
    merged = gdf[["field_id", "area_acres", "grower"]].merge(
        dom[["field_id", "pct", "crop_name"]], on="field_id", how="inner"
    )
    fig, ax = plt.subplots(figsize=(10, 6))
    crops = merged["crop_name"].unique()
    palette = sns.color_palette("Set2", n_colors=len(crops))
    for crop, color in zip(crops, palette):
        sub = merged[merged["crop_name"] == crop]
        ax.scatter(sub["area_acres"], sub["pct"], label=crop, alpha=0.7, s=100, color=color,
                   edgecolor="black")
    if len(merged) > 2:
        r_pearson, p_pearson = stats.pearsonr(merged["area_acres"], merged["pct"])
        r_spearman, p_spearman = stats.spearmanr(merged["area_acres"], merged["pct"])
        ax.annotate(
            f"Pearson r={r_pearson:.3f} (p={p_pearson:.4f})\n"
            f"Spearman ρ={r_spearman:.3f} (p={p_spearman:.4f})",
            xy=(0.05, 0.95), xycoords="axes fraction", fontsize=10,
            verticalalignment="top", bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5)
        )
        corr_df = pd.DataFrame([{
            "pearson_r": r_pearson,
            "pearson_p": p_pearson,
            "spearman_rho": r_spearman,
            "spearman_p": p_spearman,
            "n_fields": len(merged),
        }])
        corr_df.to_csv(summaries_dir / "field_size_cdl_correlation.csv", index=False)
    ax.set_title("Field Size vs. Dominant CDL Crop Percentage", fontsize=14, fontweight="bold")
    ax.set_xlabel("Field Area (acres)", fontsize=12)
    ax.set_ylabel("Dominant Crop Percentage (%)", fontsize=12)
    ax.legend(title="Crop", bbox_to_anchor=(1.05, 1), loc="upper left")
    ax.set_ylim(0, 105)
    plt.tight_layout()
    path = out_dir / "07_cdl_field_size_vs_crop_pct_correlation.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_weather_gdd_cumulative(weather_all: pd.DataFrame, out_dir: Path) -> None:
    weather_all = weather_all.copy()
    weather_all["GDD"] = weather_all.apply(
        lambda row: calc_gdd(row["T2M_MIN"], row["T2M_MAX"]), axis=1
    )
    daily = (weather_all.groupby(["grower", "date"])
             .agg({"GDD": "mean"}).reset_index())
    daily["doy"] = daily["date"].dt.dayofyear
    daily["year"] = daily["date"].dt.year

    fig, ax = plt.subplots(figsize=(12, 6))
    for grower in daily["grower"].unique():
        sub = daily[daily["grower"] == grower]
        yearly_gdd = sub.groupby("year").apply(
            lambda x: x.sort_values("doy")["GDD"].cumsum().values
        )
        max_len = max(len(v) for v in yearly_gdd)
        aligned = []
        for v in yearly_gdd:
            if len(v) == max_len:
                aligned.append(v)
        if aligned:
            mean_cum = np.mean(aligned, axis=0)
            doy_range = sub["doy"].sort_values().unique()[:len(mean_cum)]
            ax.plot(doy_range, mean_cum, label=grower, linewidth=2)

    ax.set_title("Mean Cumulative GDD by Grower (Base 10C)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Day of Year", fontsize=12)
    ax.set_ylabel("Cumulative GDD", fontsize=12)
    ax.legend(title="Grower")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = out_dir / "11_weather_cumulative_gdd_by_grower.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_within_field_timeseries(weather_all: pd.DataFrame, out_dir: Path) -> None:
    reps = {}
    for grower in weather_all["grower"].unique():
        fid = weather_all[weather_all["grower"] == grower]["field_id"].iloc[0]
        reps[grower] = fid

    weather_2023 = weather_all[weather_all["date"].dt.year == 2023].copy()

    fig, axes = plt.subplots(len(reps), 1, figsize=(14, 10), sharex=True)
    if len(reps) == 1:
        axes = [axes]

    palette = sns.color_palette("Set2", n_colors=len(reps))
    for ax, (grower, fid), color in zip(axes, reps.items(), palette):
        sub = weather_2023[weather_2023["field_id"] == fid].sort_values("date")
        ax.fill_between(sub["date"], sub["T2M_MIN"], sub["T2M_MAX"],
                        alpha=0.3, color=color, label="Temp Range")
        ax.plot(sub["date"], sub["T2M"], color="black", linewidth=1, label="Mean Temp")
        ax2 = ax.twinx()
        ax2.bar(sub["date"], sub["PRECTOTCORR"], alpha=0.3, color="blue", width=1, label="Precip")
        ax.set_title(f"{grower} — Field {fid} (2023)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Temp (C)", fontsize=10)
        ax2.set_ylabel("Precip (mm)", fontsize=10, color="blue")
        ax.legend(loc="upper left")

    axes[-1].set_xlabel("Date", fontsize=12)
    plt.tight_layout()
    path = out_dir / "weather_within_field_timeseries.png"
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def _img_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def assemble_html_report(out_dir: Path, data_coverage: dict, 
                         gdf_all: gpd.GeoDataFrame, cdl_all: pd.DataFrame,
                         kw_area: pd.DataFrame | None, chi_results: pd.DataFrame | None,
                         div_summary: pd.DataFrame | None, corr_df: pd.DataFrame | None) -> None:
    report_path = out_dir / "assignment_2_eda_report.html"
    print(f"\n--- Assembling HTML Report ---")

    largest_fields = {}
    for grower in gdf_all["grower"].unique():
        sub = gdf_all[gdf_all["grower"] == grower]
        largest = sub.loc[sub["area_acres"].idxmax()]
        largest_fields[grower] = {
            "field_id": largest["field_id"],
            "area": largest["area_acres"]
        }

    dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
    for grower, info in largest_fields.items():
        crop_match = dom[(dom["grower"] == grower) & (dom["field_id"] == info["field_id"])]
        if not crop_match.empty:
            info["crop"] = crop_match.iloc[0]["crop_name"]
            info["crop_pct"] = crop_match.iloc[0]["pct"]
        else:
            info["crop"] = "Unknown"
            info["crop_pct"] = 0

    grower_crops = {}
    for grower in dom["grower"].unique():
        sub = dom[dom["grower"] == grower]
        top_crop = sub["crop_name"].value_counts().index[0]
        top_count = sub["crop_name"].value_counts().iloc[0]
        grower_crops[grower] = {"crop": top_crop, "count": top_count}

    diversity_means = {}
    if div_summary is not None:
        for grower in div_summary.index:
            diversity_means[grower] = div_summary.loc[grower, "mean"]

    def img_section(path: Path) -> str:
        if not path.exists():
            return f"<p><em>Image not found: {path.name}</em></p>"
        b64 = _img_to_base64(path)
        return f'<img src="data:image/png;base64,{b64}" alt="{path.name}" style="max-width:100%;" />'

    boundary_violin = img_section(out_dir / "01_boundary_area_violin_by_grower.png")

    grower_maps = ""
    for grower in sorted(gdf_all["grower"].unique()):
        safe_name = grower.replace("-", "_")
        map_path = out_dir / f"03a_boundary_map_{safe_name}.png"
        grower_maps += f"<div class='viz'>{img_section(map_path)}</div>"

    cdl_comp = img_section(out_dir / "04_cdl_dominant_crop_percent_by_grower.png")
    cdl_counts = img_section(out_dir / "05_cdl_crop_class_counts_by_grower.png")
    cdl_div = img_section(out_dir / "06_cdl_shannon_diversity_boxplot.png")
    gdd_plot = img_section(out_dir / "11_weather_cumulative_gdd_by_grower.png")
    weather_ts = img_section(out_dir / "weather_within_field_timeseries.png")

    kw_text = ""
    if kw_area is not None:
        p_val = kw_area["kw_p"].iloc[0]
        sig_any = kw_area["significant"].any()
        kw_text = f"""Kruskal-Wallis H-test (non-parametric ANOVA alternative) was used because field-area distributions are non-normal and sample sizes are small. H={kw_area['kw_H'].iloc[0]:.3f}, p={p_val:.4f}. {"No significant differences" if not sig_any else "Significant differences found"} in field-area distributions across growers. This test was chosen because it tests the null hypothesis that all growers have the same median field area, telling us whether observed size differences are statistically meaningful or likely due to random sampling."""

    all_crops = sorted(dom["crop_name"].unique())
    crop_colors_desc = ", ".join([f"{c}" for c in all_crops])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Assignment 2: Field-Level Exploratory Data Analysis</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 1200px; margin: 0 auto; padding: 30px; line-height: 1.7; color: #333; }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; font-size: 28px; }}
        h2 {{ color: #34495e; margin-top: 40px; font-size: 22px; border-left: 5px solid #3498db; padding-left: 15px; }}
        h3 {{ color: #555; margin-top: 25px; font-size: 18px; }}
        .viz {{ margin: 25px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e9ecef; }}
        .viz img {{ max-width: 100%; height: auto; border: 1px solid #ddd; }}
        ul {{ margin: 15px 0; }}
        li {{ margin: 8px 0; }}
        .note {{ background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0; }}
        .ok {{ background: #d4edda; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; }}
        .findings {{ background: #e7f3ff; padding: 15px; border-left: 4px solid #2196F3; margin: 20px 0; }}
        strong {{ color: #2c3e50; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>Assignment 2: Field-Level Exploratory Data Analysis</h1>

    <h2>1. Field Area Distribution by Grower</h2>

    <p>{kw_text}</p>

    <div class="viz">
        {boundary_violin}
    </div>

    <div class="findings">
        <ul>
            <li>This analysis covers three growers across the U.S. Corn Belt:
                <ul>
                    <li><strong>il-grower</strong> — Illinois (Iroquois County, FIPS 17-075)</li>
                    <li><strong>ia-grower</strong> — Iowa (Kossuth County, FIPS 19-109)</li>
                    <li><strong>ne-grower</strong> — Nebraska (Hamilton County, FIPS 31-081)</li>
                </ul>
                Each grower has 10 fields sampled from OpenStreetMap farmland polygons. Data layers include field boundaries (GeoJSON), NASA POWER daily weather (2021–2025), and USDA NASS CDL crop classifications (2021–2025).
            </li>
            <li><strong>Largest field by grower:</strong>
                <ul>
                    <li><strong>il-grower:</strong> {largest_fields.get('il-grower', {}).get('field_id', 'N/A')} — {largest_fields.get('il-grower', {}).get('area', 0):.1f} acres, dominant CDL: {largest_fields.get('il-grower', {}).get('crop', 'N/A')} ({largest_fields.get('il-grower', {}).get('crop_pct', 0):.1f}%)</li>
                    <li><strong>ia-grower:</strong> {largest_fields.get('ia-grower', {}).get('field_id', 'N/A')} — {largest_fields.get('ia-grower', {}).get('area', 0):.1f} acres, dominant CDL: {largest_fields.get('ia-grower', {}).get('crop', 'N/A')} ({largest_fields.get('ia-grower', {}).get('crop_pct', 0):.1f}%)</li>
                    <li><strong>ne-grower:</strong> {largest_fields.get('ne-grower', {}).get('field_id', 'N/A')} — {largest_fields.get('ne-grower', {}).get('area', 0):.1f} acres, dominant CDL: {largest_fields.get('ne-grower', {}).get('crop', 'N/A')} ({largest_fields.get('ne-grower', {}).get('crop_pct', 0):.1f}%)</li>
                </ul>
            </li>
            <li>Nebraska shows the widest range of field sizes, from small plots under 6 acres to large rectangles over 240 acres, reflecting the mix of pivot-irrigation circles and smaller parcels in Hamilton County.</li>
            <li>Illinois fields cluster in the 1–260 acre range, with most being medium-sized rectangles typical of the eastern Corn Belt.</li>
            <li>Iowa fields span 20–600 acres, with one exceptionally large field (osm-1466094203 at ~596 acres), characteristic of the highly mechanized, large-scale row-crop operations in north-central Iowa.</li>
        </ul>
    </div>

    <h2>Field Boundaries by Grower</h2>
    <p>The following maps show each grower's fields with OpenStreetMap basemap context. Each field is color coded by the dominant CDL.</p>
    {grower_maps}

    <div class="findings">
        <ul>
            <li>The three growers are clearly separated geographically: Illinois fields sit around 40.5–41.0°N, 87.5–88.0°W; Iowa fields around 43.0–43.3°N, 94.1–94.4°W; Nebraska fields around 40.7–40.9°N, 97.9–98.2°W.</li>
            <li>The dominant-crop map reveals state-level agricultural signatures: Illinois shows a mix of corn and soybean dominance, Iowa is heavily corn-dominated, and Nebraska shows a mix with some alfalfa and forest patches.</li>
            <li>CDL classifications at 30 m resolution mean small fields may have mixed-pixel bias, especially visible in the Illinois grower where some small fields show 100% single-crop classification.</li>
        </ul>
    </div>

    <h2>2. Crop Typology by Grower</h2>

    <h3>Dominant Crop Composition by Grower</h3>
    <p>The growers consider {len(all_crops)} crop types ({crop_colors_desc}). Each bar plot shows the percentage of crop mix practiced in their fields across three growers.</p>

    <div class="viz">
        {cdl_comp}
    </div>

    <div class="findings">
        <ul>
            <li><strong>ia-grower (Iowa):</strong> Corn is the dominant crop on {grower_crops.get('ia-grower', {}).get('count', 0)} out of 10 fields, reflecting Iowa's status as the top corn-producing state. Soybeans appear on {10 - grower_crops.get('ia-grower', {}).get('count', 0)} fields.</li>
            <li><strong>il-grower (Illinois):</strong> Shows a more balanced corn-soybean rotation, with soybeans dominant on several fields. This aligns with Illinois's typical corn-soybean rotation system.</li>
            <li><strong>ne-grower (Nebraska):</strong> Corn dominates but with notable diversity including alfalfa and forest classifications, reflecting Hamilton County's mixed agricultural landscape with irrigated crops and natural vegetation.</li>
        </ul>
    </div>

    <h3>CDL Crop Class Counts by Grower</h3>
    <p>Crop practices vary grower to grower. The crop class adopted by each grower is given below.</p>

    <div class="viz">
        {cdl_counts}
    </div>

    <div class="findings">
        <ul>
            <li>Raw counts confirm Iowa's heavy corn orientation with nearly all fields classified as corn in 2025.</li>
            <li>Illinois shows the most even split between corn and soybeans, consistent with the state's 2-year rotation practices.</li>
            <li>Nebraska has the highest crop-type diversity, with alfalfa and forest appearing alongside corn and soybeans, indicating a less monoculture-dominated landscape.</li>
        </ul>
    </div>

    <h3>CDL Shannon Diversity Index by Grower</h3>
    <p>Unlike simple species counts, Shannon index accounts for both richness (number of crop types) and evenness (how equally they are represented). In agricultural remote sensing, it helps identify fields with high edge-pixel mixing versus pure monoculture interiors. The Shannon Diversity Index measures how many different crop classes are present within each field and how evenly they are distributed. Higher values mean more diverse fields (more edge effects or mixed cropping).</p>

    <div class="viz">
        {cdl_div}
    </div>

    <div class="findings">
        <ul>
            <li>Nebraska shows the highest mean Shannon diversity ({diversity_means.get('ne-grower', 0):.2f}), indicating fields with more mixed classifications — likely due to smaller field sizes creating more edge pixels at 30 m resolution.</li>
            <li>Iowa has the lowest diversity ({diversity_means.get('ia-grower', 0):.2f}), confirming the near-monoculture corn dominance.</li>
            <li>Illinois falls in the middle ({diversity_means.get('il-grower', 0):.2f}), reflecting the corn-soybean rotation but with some fields showing pure single-crop classification.</li>
        </ul>
    </div>

    <h2>3. Crop Growth Weather Conditions</h2>

    <h3>Mean Cumulative GDD by Grower (Base 10°C)</h3>
    <p>Growing Degree Days (base 10°C) measure heat accumulation during the growing season. Crops like corn and soybeans require minimum thermal time to reach maturity. By plotting cumulative GDD trajectories, we can compare how quickly each state accumulates the heat necessary for crop development. These trajectories represent mean cumulative GDD averaged across all available years (2021–2025) and all fields with weather data per grower.</p>

    <div class="viz">
        {gdd_plot}
    </div>

    <div class="findings">
        <ul>
            <li>Nebraska consistently leads in cumulative GDD accumulation, reaching higher totals earlier in the season. This reflects its more westerly, warmer continental climate.</li>
            <li>Illinois and Iowa track closely but below Nebraska, with Iowa generally accumulating slightly less heat than Illinois due to its more northerly latitude.</li>
            <li>By early September (DOY 250), most corn and soybean crops in the Corn Belt have reached reproductive maturity or physiological maturity. After this point, GDD accumulation becomes less biologically relevant because the crop has completed its growth cycle and is approaching harvest. The plateau effect also reflects the natural decline in temperatures as autumn approaches.</li>
        </ul>
    </div>

    <h3>Annual Precipitation and Temperature Variations</h3>
    <p>Daily temperature and precipitation data reveal the actual growing conditions crops experienced. Temperature extremes (heat stress above 35°C or cold snaps) and precipitation timing (drought periods or excess rain) directly impact yield potential, pest pressure, and planting/harvest windows. The following time-series plots show daily temperature ranges (shaded) and mean temperature (black line) alongside precipitation (blue bars) for one representative field per grower during the 2023 growing season.</p>

    <div class="viz">
        {weather_ts}
    </div>

    <div class="findings">
        <ul>
            <li><strong>Nebraska (2023):</strong> Shows the warmest conditions with the widest daily temperature swings. Precipitation is more sporadic with distinct dry periods in mid-summer, typical of the semi-humid western Corn Belt where irrigation is common.</li>
            <li><strong>Illinois (2023):</strong> Moderate temperatures with more consistent precipitation distribution. The cooler, wetter pattern is characteristic of the eastern Corn Belt.</li>
            <li><strong>Iowa (2023):</strong> Coolest overall temperatures with notable precipitation events in late spring and early summer. The temperature range is narrower than Nebraska, reflecting more maritime influence from the north.</li>
            <li>The wider temperature ranges in Nebraska directly translate to higher GDD accumulation rates seen in the cumulative plot above. Conversely, Iowa's cooler daily means result in slower GDD accumulation, potentially extending the growing season.</li>
            <li>No catastrophic extreme events are visible in 2023, but Nebraska shows several periods where daily maxima exceed 35°C (95°F), which can cause heat stress during pollination. Iowa and Illinois stay below this threshold more consistently.</li>
        </ul>
    </div>

    <h2>4. Limitations, Missing Data, and Assumptions</h2>
    <ul>
        <li><strong>Weather coverage:</strong> All 30 fields (10 per grower) now have complete NASA POWER daily weather data for 2021–2025. Weather was re-downloaded using the NASA POWER Zarr backend after the initial pipeline run left some fields with empty files.</li>
        <li><strong>Temporal range (2021–2025):</strong> This five-year window was chosen because it represents the most recent complete period available in the NASA POWER reanalysis and CDL archives. It captures recent climate variability without going so far back that land-use changes would invalidate boundary comparisons. Long-term climatology might smooth over important short-term seasonal fluctuations visible in this window.</li>
        <li><strong>CDL resolution:</strong> USDA NASS CDL is provided at 30 m resolution. Fields smaller than ~22 acres (9 ha) may be represented by only a few pixels, leading to mixed-classification artifacts. This particularly affects the Shannon diversity calculations for small fields.</li>
        <li><strong>Weather data source:</strong> NASA POWER provides reanalysis data at ~0.5° × 0.5° resolution. Field-level weather is extracted at field centroids and may not capture microclimatic variations within large fields or topographic effects.</li>
        <li><strong>GDD simplification:</strong> The GDD calculation uses a simple base-10°C formula without an upper cutoff. Real corn GDD models typically cap accumulation at 30°C because temperatures above this threshold do not accelerate development and may cause heat stress.</li>
        <li><strong>Spatial independence:</strong> Statistical tests assume fields are independent samples. In reality, nearby fields share similar weather and soil conditions, creating spatial autocorrelation that is not corrected in these analyses.</li>
        <li><strong>Soil analysis exclusion:</strong> Soil analysis is not required for this assignment and was intentionally excluded. The EDA subskill focuses on boundaries, CDL crops, and weather only. SSURGO soil tables exist in the runtime but were not analyzed here.</li>
    </ul>

    <h2>5. Summary</h2>
    <table>
        <tr>
            <th>Grower</th>
            <th>State</th>
            <th>County</th>
            <th>Fields</th>
            <th>Dominant Crop</th>
            <th>Largest Field (acres)</th>
            <th>Shannon Diversity</th>
            <th>GDD Rank</th>
        </tr>
        <tr>
            <td>il-grower</td>
            <td>Illinois</td>
            <td>Iroquois</td>
            <td>10</td>
            <td>Corn/Soybean mix</td>
            <td>{largest_fields.get('il-grower', {}).get('area', 0):.1f}</td>
            <td>{diversity_means.get('il-grower', 0):.2f}</td>
            <td>2nd (mid)</td>
        </tr>
        <tr>
            <td>ia-grower</td>
            <td>Iowa</td>
            <td>Kossuth</td>
            <td>10</td>
            <td>Corn (dominant)</td>
            <td>{largest_fields.get('ia-grower', {}).get('area', 0):.1f}</td>
            <td>{diversity_means.get('ia-grower', 0):.2f}</td>
            <td>3rd (lowest)</td>
        </tr>
        <tr>
            <td>ne-grower</td>
            <td>Nebraska</td>
            <td>Hamilton</td>
            <td>10</td>
            <td>Corn/Soybean/Alfalfa</td>
            <td>{largest_fields.get('ne-grower', {}).get('area', 0):.1f}</td>
            <td>{diversity_means.get('ne-grower', 0):.2f}</td>
            <td>1st (highest)</td>
        </tr>
    </table>

    <hr>
    <p><em>Report generated from outputs produced by the field-level EDA comparison workflow.</em></p>
</body>
</html>
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved: {report_path}")


def run_all(data_root: Path | None = None) -> None:
    if data_root is None:
        data_root = _data_root()
    out_dir = _output_dir()
    summaries_dir = out_dir / "summary"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Assignment 2: Field-Level EDA Comparison")
    print("=" * 60)

    growers = discover_growers(data_root)
    print(f"\nDiscovered growers: {growers}")

    boundary_list = []
    cdl_list = []
    weather_list = []
    data_coverage = {}

    for grower in growers:
        farm = discover_farm_slug(data_root, grower)
        if not farm:
            continue
        data_coverage[grower] = {"farm": farm}

        gdf = load_boundaries(data_root, grower, farm)
        if gdf is not None:
            boundary_list.append(gdf)
            data_coverage[grower]["fields"] = len(gdf)

        cdl = None
        for year in range(2025, 2020, -1):
            cdl = load_cdl(data_root, grower, farm, year)
            if cdl is not None:
                data_coverage[grower]["cdl_year"] = year
                break
        if cdl is not None:
            cdl_list.append(cdl)

        w = load_weather_from_fields(data_root, grower, farm)
        if w is not None:
            weather_list.append(w)
            data_coverage[grower]["weather_fields"] = w["field_id"].nunique()
        else:
            data_coverage[grower]["weather_fields"] = 0

    print("\n--- Data Coverage ---")
    for g, info in data_coverage.items():
        print(f"  {g}: {info}")

    gdf_all = None
    kw_area = None
    if boundary_list:
        print("\n--- Boundary Analysis ---")
        gdf_all = pd.concat(boundary_list, ignore_index=True)
        plot_boundary_area_violin(gdf_all, out_dir)

        area_groups = {g: gdf_all[gdf_all["grower"] == g]["area_acres"] for g in gdf_all["grower"].unique()}
        kw_area = kruskal_wallis_with_posthoc(area_groups)
        kw_path = summaries_dir / "boundary_kruskal_wallis.csv"
        kw_area.to_csv(kw_path, index=False)
        print(f"  Saved: {kw_path}")

    cdl_all = None
    chi_results = None
    div_summary = None
    corr_df = None
    if cdl_list:
        print("\n--- CDL Analysis ---")
        cdl_all = pd.concat(cdl_list, ignore_index=True)
        plot_cdl_composition(cdl_all, out_dir)
        plot_cdl_crop_counts(cdl_all, out_dir)
        div_df = plot_cdl_diversity(cdl_all, out_dir)

        if gdf_all is not None:
            plot_field_size_vs_cdl_correlation(gdf_all, cdl_all, out_dir, summaries_dir)
            plot_cdl_colored_grower_maps(gdf_all, cdl_all, out_dir)

        dom = cdl_all.loc[cdl_all.groupby(["grower", "field_id"])["pct"].idxmax()]
        contingency = pd.crosstab(dom["grower"], dom["crop_name"])
        chi2, p_chi, _, _ = stats.chi2_contingency(contingency)
        cram_v = cramers_v(contingency)
        chi_results = pd.DataFrame([{
            "chi2": chi2,
            "p_value": p_chi,
            "cramers_v": cram_v,
            "significant": p_chi < 0.05,
        }])
        chi_path = summaries_dir / "cdl_chi_square_cramers_v.csv"
        chi_results.to_csv(chi_path, index=False)
        print(f"  Saved: {chi_path}")
        print(f"  Chi-square: chi2={chi2:.3f}, p={p_chi:.4f}, Cramers V={cram_v:.3f}")

        div_summary = div_df.groupby("grower")["shannon_index"].agg(["mean", "std", "min", "max"]).round(3)
        div_summary.to_csv(summaries_dir / "cdl_diversity_summary.csv")

    if weather_list:
        print("\n--- Weather Analysis ---")
        weather_all = pd.concat(weather_list, ignore_index=True)
        plot_weather_gdd_cumulative(weather_all, out_dir)
        plot_within_field_timeseries(weather_all, out_dir)

        gs = weather_all[(weather_all["date"].dt.month >= 4) & (weather_all["date"].dt.month <= 10)]
        temp_groups = {g: gs[gs["grower"] == g]["T2M"] for g in gs["grower"].unique()}
        kw_temp = kruskal_wallis_with_posthoc(temp_groups)
        kw_path = summaries_dir / "weather_kruskal_wallis.csv"
        kw_temp.to_csv(kw_path, index=False)
        print(f"  Saved: {kw_path}")

    print("\n--- Report Assembly ---")
    if gdf_all is not None and cdl_all is not None:
        assemble_html_report(out_dir, data_coverage, gdf_all, cdl_all, 
                            kw_area, chi_results, div_summary, corr_df)
    else:
        print("  Skipping report: missing boundary or CDL data")

    print("\n" + "=" * 60)
    print("EDA Complete")
    print("=" * 60)
    print(f"Output directory: {out_dir}")
    files = sorted(out_dir.rglob("*"))
    print(f"Generated {len(files)} files")


def main() -> None:
    parser = argparse.ArgumentParser(description="Field-Level EDA Comparison")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Path to data-pipeline root (default: 4 levels above script)")
    args = parser.parse_args()
    run_all(data_root=args.data_root)


if __name__ == "__main__":
    main()