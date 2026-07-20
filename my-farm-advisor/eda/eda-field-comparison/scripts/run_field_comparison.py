#!/usr/bin/env python3
"""Cross-field, cross-grower comparison of boundaries, CDL, and weather.

Outputs:
- 10+ PNG plots under ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/plots/
- 5+ CSV tables under ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/tables/
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from shapely import length, area as shapely_area

warnings.filterwarnings("ignore", category=FutureWarning)

_DATA_ROOT = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "/tmp")).expanduser() / "data-pipeline"
_GROWERS = ["il-northern-grower", "ia-northern-grower", "nebraska-grower"]
_GS_MONTHS = [5, 6, 7, 8, 9]  # May-Sep growing season
_OUTPUT_PLOTS = _DATA_ROOT / "eda" / "field-comparison" / "plots"
_OUTPUT_TABLES = _DATA_ROOT / "eda" / "field-comparison" / "tables"

# Style setup
sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 100


def _ensure_dirs() -> None:
    _OUTPUT_PLOTS.mkdir(parents=True, exist_ok=True)
    _OUTPUT_TABLES.mkdir(parents=True, exist_ok=True)


def _load_boundaries_gdf() -> gpd.GeoDataFrame:
    """Load all field boundaries as a single GeoDataFrame with grower labels."""
    all_gdfs = []
    for grower in _GROWERS:
        farm = f"{grower}-farm"
        path = _DATA_ROOT / "growers" / grower / "farms" / farm / "boundary" / "field_boundaries.geojson"
        if not path.exists():
            continue
        gdf = gpd.read_file(path).to_crs("EPSG:4326")
        gdf["grower"] = grower
        # Compute metrics in projected CRS (Albers Equal Area for CONUS)
        gdf_proj = gdf.to_crs("EPSG:5070")
        gdf["area_m2"] = gdf_proj.geometry.area
        gdf["area_acres"] = gdf["area_m2"] / 4046.8564224
        perim = gdf_proj.geometry.boundary.length
        gdf["perimeter_m"] = perim
        gdf["circularity"] = (4.0 * np.pi * gdf["area_m2"]) / (perim ** 2)
        gdf["centroid_lat"] = gdf.geometry.centroid.y
        gdf["centroid_lon"] = gdf.geometry.centroid.x
        all_gdfs.append(gdf)
    return pd.concat(all_gdfs, ignore_index=True) if all_gdfs else gpd.GeoDataFrame()


def _load_boundaries_df() -> pd.DataFrame:
    gdf = _load_boundaries_gdf()
    if gdf.empty:
        return pd.DataFrame()
    cols = ["field_id", "grower", "area_m2", "area_acres", "perimeter_m", "circularity", "centroid_lat", "centroid_lon"]
    return gdf[cols].copy()


def _load_cdl() -> pd.DataFrame:
    records = []
    for grower in _GROWERS:
        farm = f"{grower}-farm"
        for year in range(2021, 2026):
            path = (
                _DATA_ROOT
                / "growers"
                / grower
                / "farms"
                / farm
                / "derived"
                / "tables"
                / f"{grower.replace('-', '_')}_{year}_cdl.csv"
            )
            if path.exists():
                df = pd.read_csv(path)
                df["year"] = year
                df["grower"] = grower
                records.append(df)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def _load_weather() -> pd.DataFrame:
    records = []
    for grower in _GROWERS:
        farm = f"{grower}-farm"
        path = (
            _DATA_ROOT
            / "growers"
            / grower
            / "farms"
            / farm
            / "derived"
            / "tables"
            / f"{grower.replace('-', '_')}_weather_2021_2025.csv"
        )
        if path.exists():
            df = pd.read_csv(path, parse_dates=["date"])
            df["grower"] = grower
            records.append(df)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


# ---------------------------------------------------------------------------
# A. BOUNDARIES
# ---------------------------------------------------------------------------

def _plot_A0_geospatial(boundaries_gdf: gpd.GeoDataFrame) -> None:
    """Geospatial map of all fields colored by grower."""
    if boundaries_gdf.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 10))

    # Load US states for context
    states_path = _DATA_ROOT / "shared" / "geoadmin" / "l1_states" / "states_usa.geojson"
    if states_path.exists():
        states = gpd.read_file(states_path).to_crs("EPSG:4326")
        # Filter to relevant states
        target_states = ["Illinois", "Iowa", "Nebraska"]
        states = states[states["state_name"].isin(target_states)]
        states.boundary.plot(ax=ax, color="gray", linewidth=0.8, alpha=0.5)

    # Color map for growers
    grower_colors = {
        "il-northern-grower": "#2ecc71",  # green
        "ia-northern-grower": "#3498db",  # blue
        "nebraska-grower": "#e74c3c",     # red
    }

    for grower, color in grower_colors.items():
        subset = boundaries_gdf[boundaries_gdf["grower"] == grower]
        if not subset.empty:
            subset.plot(
                ax=ax,
                color=color,
                edgecolor="black",
                linewidth=0.5,
                alpha=0.6,
                label=grower.replace("-", " ").title(),
            )

    ax.set_title("FP2 Field Boundaries by Grower", fontsize=16, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.legend(title="Grower", loc="upper right")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "A0_geospatial_map.png", dpi=300, bbox_inches="tight")
    plt.close()


def _plot_A1(boundaries: pd.DataFrame) -> None:
    plt.figure(figsize=(10, 6))
    ax = sns.boxplot(data=boundaries, x="grower", y="area_acres", hue="grower", palette="Set2", legend=False)
    ax.set_title("Field Area Distribution by Grower", fontsize=14, fontweight="bold")
    ax.set_xlabel("Grower")
    ax.set_ylabel("Area (acres)")
    # Add sample size annotation
    for i, grower in enumerate(boundaries["grower"].unique()):
        n = len(boundaries[boundaries["grower"] == grower])
        ax.annotate(f"n={n}", xy=(i, boundaries[boundaries["grower"] == grower]["area_acres"].max()),
                   ha="center", va="bottom", fontsize=9, color="black")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "A1_field_area_by_grower.png", dpi=300, bbox_inches="tight")
    plt.close()


def _plot_A2(boundaries: pd.DataFrame) -> None:
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=boundaries, x="area_acres", y="circularity", hue="grower", s=120, alpha=0.7, palette="Set2")
    plt.axhline(y=0.785, color="red", linestyle="--", alpha=0.5, label="Circle (0.785)")
    plt.title("Field Circularity vs. Area by Grower", fontsize=14, fontweight="bold")
    plt.xlabel("Area (acres)")
    plt.ylabel("Circularity (4πA/P²)")
    plt.legend(title="Grower")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "A2_circularity_vs_area.png", dpi=300, bbox_inches="tight")
    plt.close()


def _test_A3(boundaries: pd.DataFrame) -> pd.DataFrame:
    groups = [g["area_acres"].values for _, g in boundaries.groupby("grower")]
    h_stat, p_val = stats.kruskal(*groups)
    result = [{"test": "Kruskal-Wallis", "H_statistic": h_stat, "p_value": p_val}]
    if p_val < 0.05:
        from itertools import combinations
        for g1, g2 in combinations(boundaries["grower"].unique(), 2):
            a = boundaries[boundaries["grower"] == g1]["area_acres"]
            b = boundaries[boundaries["grower"] == g2]["area_acres"]
            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            result.append(
                {
                    "test": f"Mann-Whitney U ({g1} vs {g2})",
                    "U_statistic": u,
                    "p_value": p,
                }
            )
    return pd.DataFrame(result)


# ---------------------------------------------------------------------------
# B. CDL
# ---------------------------------------------------------------------------

def _plot_B1(cdl: pd.DataFrame) -> None:
    if cdl.empty:
        return
    comp = cdl.groupby(["grower", "year", "crop_name"])["pct"].sum().reset_index()
    comp = comp.pivot_table(
        index=["grower", "year"], columns="crop_name", values="pct", fill_value=0
    )
    comp = comp.reset_index()
    comp_melt = comp.melt(id_vars=["grower", "year"], var_name="crop", value_name="pct")

    g = sns.FacetGrid(comp_melt, col="grower", height=5, aspect=1.2, sharey=True)
    g.map_dataframe(sns.barplot, x="year", y="pct", hue="crop", palette="tab10")
    g.add_legend(title="Crop", bbox_to_anchor=(1.05, 0.5), loc="center left")
    g.set_axis_labels("Year", "Percentage (%)")
    g.set_titles(col_template="{col_name}")
    plt.suptitle("Crop Composition by Grower and Year", y=1.02, fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "B1_crop_composition_by_grower_year.png", dpi=300, bbox_inches="tight")
    plt.close()


def _plot_B2(cdl: pd.DataFrame) -> None:
    if cdl.empty:
        return

    def shannon(group):
        p = group["pct"] / 100.0
        p = p[p > 0]
        return -np.sum(p * np.log(p))

    div = (
        cdl.groupby(["grower", "field_id", "year"])
        .apply(shannon, include_groups=False)
        .reset_index(name="shannon")
    )
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=div, x="grower", y="shannon", hue="grower", palette="Set2", legend=False)
    plt.title("Crop Diversity (Shannon Index) by Grower", fontsize=14, fontweight="bold")
    plt.xlabel("Grower")
    plt.ylabel("Shannon Diversity Index")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "B2_crop_diversity_by_grower.png", dpi=300, bbox_inches="tight")
    plt.close()


def _test_B3(cdl: pd.DataFrame) -> pd.DataFrame:
    if cdl.empty:
        return pd.DataFrame()
    dom = cdl.loc[cdl.groupby(["grower", "field_id", "year"])["pct"].idxmax()][
        ["grower", "field_id", "year", "crop_name"]
    ]
    ct = pd.crosstab(dom["grower"], dom["crop_name"])
    chi2, p, dof, expected = stats.chi2_contingency(ct)
    return pd.DataFrame(
        [
            {
                "test": "Chi-square (crop x grower)",
                "chi2": chi2,
                "p_value": p,
                "dof": dof,
            }
        ]
    )


def _plot_B4(cdl: pd.DataFrame) -> None:
    """Corn vs Soybeans dominance over time by grower."""
    if cdl.empty:
        return
    cs = cdl[cdl["crop_name"].isin(["Corn", "Soybeans"])].copy()
    cs_summary = cs.groupby(["grower", "year", "crop_name"])["pct"].mean().reset_index()
    cs_summary = cs_summary.pivot(index=["grower", "year"], columns="crop_name", values="pct").fillna(0)
    cs_summary = cs_summary.reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    for ax, grower in zip(axes, _GROWERS):
        subset = cs_summary[cs_summary["grower"] == grower]
        if not subset.empty:
            ax.plot(subset["year"], subset["Corn"], marker="o", label="Corn", linewidth=2, color="#f39c12")
            ax.plot(subset["year"], subset["Soybeans"], marker="s", label="Soybeans", linewidth=2, color="#27ae60")
            ax.set_title(grower.replace("-", " ").title(), fontsize=12, fontweight="bold")
            ax.set_xlabel("Year")
            ax.set_ylabel("Mean Coverage (%)")
            ax.legend()
            ax.grid(True, alpha=0.3)
    fig.suptitle("Corn vs. Soybeans Dominance Over Time", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "B4_corn_soy_trends.png", dpi=300, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# C. WEATHER
# ---------------------------------------------------------------------------

def _plot_C1(weather: pd.DataFrame) -> None:
    if weather.empty:
        return
    gs = weather[weather["date"].dt.month.isin(_GS_MONTHS)]
    gs_temp = (
        gs.groupby(["grower", "field_id", gs["date"].dt.year])["T2M"]
        .mean()
        .reset_index(name="mean_temp_c")
    )
    gs_temp = gs_temp.rename(columns={"date": "year"})
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=gs_temp, x="year", y="mean_temp_c", hue="grower", palette="Set2")
    plt.title("Growing-Season Mean Temperature by Grower and Year", fontsize=14, fontweight="bold")
    plt.xlabel("Year")
    plt.ylabel("Mean Temperature (°C)")
    plt.legend(title="Grower")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "C1_growing_season_temperature.png", dpi=300, bbox_inches="tight")
    plt.close()


def _plot_C2(weather: pd.DataFrame) -> None:
    if weather.empty:
        return
    gs = weather[weather["date"].dt.month.isin(_GS_MONTHS)]
    gs_precip = (
        gs.groupby(["grower", "field_id", gs["date"].dt.year])["PRECTOTCORR"]
        .sum()
        .reset_index(name="total_precip_mm")
    )
    gs_precip = gs_precip.rename(columns={"date": "year"})
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=gs_precip, x="year", y="total_precip_mm", hue="grower", palette="Set2")
    plt.title("Growing-Season Total Precipitation by Grower and Year", fontsize=14, fontweight="bold")
    plt.xlabel("Year")
    plt.ylabel("Total Precipitation (mm)")
    plt.legend(title="Grower")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "C2_growing_season_precipitation.png", dpi=300, bbox_inches="tight")
    plt.close()


def _test_C3(weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty:
        return pd.DataFrame()
    gs = weather[weather["date"].dt.month.isin(_GS_MONTHS)]
    summary = (
        gs.groupby(["grower", "field_id", gs["date"].dt.year])
        .agg(mean_temp_c=("T2M", "mean"), total_precip_mm=("PRECTOTCORR", "sum"))
        .reset_index()
    )
    summary = summary.rename(columns={"date": "year"})
    results = []
    plt.figure(figsize=(10, 6))
    for grower, group in summary.groupby("grower"):
        r, p = stats.pearsonr(group["mean_temp_c"], group["total_precip_mm"])
        results.append(
            {
                "grower": grower,
                "pearson_r": r,
                "p_value": p,
                "n": len(group),
            }
        )
        plt.scatter(group["mean_temp_c"], group["total_precip_mm"], label=grower, alpha=0.7, s=80)
        z = np.polyfit(group["mean_temp_c"], group["total_precip_mm"], 1)
        pfit = np.poly1d(z)
        x_line = np.linspace(group["mean_temp_c"].min(), group["mean_temp_c"].max(), 100)
        plt.plot(x_line, pfit(x_line), "--", alpha=0.5)
    plt.title("Growing-Season Temperature vs. Precipitation", fontsize=14, fontweight="bold")
    plt.xlabel("Mean Temperature (°C)")
    plt.ylabel("Total Precipitation (mm)")
    plt.legend(title="Grower")
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "C3_temp_vs_precip_scatter.png", dpi=300, bbox_inches="tight")
    plt.close()
    return pd.DataFrame(results)


def _plot_C4(weather: pd.DataFrame) -> None:
    """Monthly weather pattern comparison across growers (field-year level)."""
    if weather.empty:
        return
    gs = weather[weather["date"].dt.month.isin(_GS_MONTHS)].copy()
    gs["month"] = gs["date"].dt.month
    monthly = gs.groupby(["grower", "field_id", "month"]).agg(
        mean_temp_c=("T2M", "mean"),
        total_precip_mm=("PRECTOTCORR", "sum"),
    ).reset_index()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Temperature
    sns.lineplot(data=monthly, x="month", y="mean_temp_c", hue="grower", palette="Set2", ax=axes[0], errorbar="sd")
    axes[0].set_title("Monthly Growing-Season Temperature", fontsize=14, fontweight="bold")
    axes[0].set_xlabel("Month")
    axes[0].set_ylabel("Mean Temperature (°C)")
    axes[0].set_xticks(range(5, 10))
    axes[0].legend(title="Grower")

    # Precipitation
    sns.lineplot(data=monthly, x="month", y="total_precip_mm", hue="grower", palette="Set2", ax=axes[1], errorbar="sd")
    axes[1].set_title("Monthly Growing-Season Precipitation", fontsize=14, fontweight="bold")
    axes[1].set_xlabel("Month")
    axes[1].set_ylabel("Total Precipitation (mm)")
    axes[1].set_xticks(range(5, 10))
    axes[1].legend(title="Grower")

    plt.suptitle("Field-Level Monthly Weather Patterns (2021-2025)", fontsize=16, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(_OUTPUT_PLOTS / "C4_monthly_weather_patterns.png", dpi=300, bbox_inches="tight")
    plt.close()


def _test_C5(weather: pd.DataFrame) -> pd.DataFrame:
    """ANOVA: compare growing-season precipitation across growers per year."""
    if weather.empty:
        return pd.DataFrame()
    gs = weather[weather["date"].dt.month.isin(_GS_MONTHS)]
    summary = (
        gs.groupby(["grower", "field_id", gs["date"].dt.year])
        .agg(total_precip_mm=("PRECTOTCORR", "sum"))
        .reset_index()
    )
    summary = summary.rename(columns={"date": "year"})

    results = []
    for year, group in summary.groupby("year"):
        groups = [g["total_precip_mm"].values for _, g in group.groupby("grower")]
        if len(groups) >= 2:
            f_stat, p_val = stats.f_oneway(*groups)
            results.append({"year": year, "f_statistic": f_stat, "p_value": p_val})
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# D. SUMMARY TABLE
# ---------------------------------------------------------------------------

def _build_summary_table(boundaries: pd.DataFrame, cdl: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Build a per-grower summary table."""
    rows = []
    for grower in _GROWERS:
        row = {"grower": grower}

        # Boundaries
        b = boundaries[boundaries["grower"] == grower]
        if not b.empty:
            row["field_count"] = len(b)
            row["mean_area_acres"] = round(b["area_acres"].mean(), 2)
            row["mean_circularity"] = round(b["circularity"].mean(), 3)

        # CDL
        c = cdl[cdl["grower"] == grower]
        if not c.empty:
            dom = c.loc[c.groupby(["field_id", "year"])["pct"].idxmax()]
            row["dominant_crop"] = dom["crop_name"].mode().iloc[0] if not dom.empty else "N/A"

        # Weather
        w = weather[weather["grower"] == grower]
        if not w.empty:
            gs = w[w["date"].dt.month.isin(_GS_MONTHS)]
            row["mean_gs_temp_c"] = round(gs["T2M"].mean(), 2)
            row["mean_gs_precip_mm"] = round(gs["PRECTOTCORR"].sum() / len(gs["field_id"].unique()) / 5, 2)

        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    _ensure_dirs()
    print("Loading data...")
    boundaries_gdf = _load_boundaries_gdf()
    boundaries = _load_boundaries_df()
    cdl = _load_cdl()
    weather = _load_weather()

    print(f"Boundaries: {len(boundaries)} fields")
    print(f"CDL records: {len(cdl)} rows")
    print(f"Weather records: {len(weather)} rows")

    print("\nA. Boundary analysis...")
    _plot_A0_geospatial(boundaries_gdf)
    _plot_A1(boundaries)
    _plot_A2(boundaries)
    a3 = _test_A3(boundaries)
    a3.to_csv(_OUTPUT_TABLES / "A3_size_statistical_test.csv", index=False)

    print("B. CDL analysis...")
    _plot_B1(cdl)
    _plot_B2(cdl)
    b3 = _test_B3(cdl)
    b3.to_csv(_OUTPUT_TABLES / "B3_cdl_statistical_tests.csv", index=False)
    _plot_B4(cdl)

    print("C. Weather analysis...")
    _plot_C1(weather)
    _plot_C2(weather)
    c3 = _test_C3(weather)
    c3.to_csv(_OUTPUT_TABLES / "C3_temp_precip_correlation.csv", index=False)
    _plot_C4(weather)
    c5 = _test_C5(weather)
    c5.to_csv(_OUTPUT_TABLES / "C5_precip_anova_by_year.csv", index=False)

    print("D. Summary table...")
    summary = _build_summary_table(boundaries, cdl, weather)
    summary.to_csv(_OUTPUT_TABLES / "D0_grower_summary.csv", index=False)

    print(f"\nDone. Outputs in:")
    print(f"  Plots: {_OUTPUT_PLOTS}")
    print(f"  Tables: {_OUTPUT_TABLES}")
    print(f"\nGenerated {len(list(_OUTPUT_PLOTS.glob('*.png')))} plots and {len(list(_OUTPUT_TABLES.glob('*.csv')))} tables.")


if __name__ == "__main__":
    main()
