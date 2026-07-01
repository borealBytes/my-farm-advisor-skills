import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

DATA_ROOT = Path(os.environ.get(
    "DATA_PIPELINE_DATA_ROOT",
    os.path.expanduser("~/my-farm-advisor-runtime/data-pipeline"),
))
GROWERS = DATA_ROOT / "growers"
OUTPUT = DATA_ROOT.parent / "eda-outputs" / "weather"

GROWERS_CONFIG = [
    ("illinois-grower", "illinois-farm", "Illinois"),
    ("iowa-grower", "iowa-farm", "Iowa"),
    ("nebraska-grower", "nebraska-farm", "Nebraska"),
]

sns.set_theme(style="whitegrid")
COLORS = {"Illinois": "#66c2a5", "Iowa": "#fc8d62", "Nebraska": "#8da0cb"}


def load_weather() -> pd.DataFrame:
    records = []
    for grower_slug, farm_slug, label in GROWERS_CONFIG:
        path = GROWERS / grower_slug / "farms" / farm_slug / "derived" / "tables" / f"{label.lower()}_weather_2021_2025.csv"
        df = pd.read_csv(path, parse_dates=["date"])
        df["grower"] = label
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month
        records.append(df)
    return pd.concat(records, ignore_index=True)


def plot_seasonal_temperature(df: pd.DataFrame, output: Path):
    monthly = df.groupby(["grower", "month"])["T2M"].agg(["mean", "std"]).reset_index()
    monthly["month"] = monthly["month"].astype(int)

    fig, ax = plt.subplots(figsize=(9, 5))
    for grower in ["Illinois", "Iowa", "Nebraska"]:
        subset = monthly[monthly["grower"] == grower]
        ax.plot(subset["month"], subset["mean"], "-o", color=COLORS[grower], label=grower, linewidth=2)
        ax.fill_between(
            subset["month"],
            subset["mean"] - subset["std"],
            subset["mean"] + subset["std"],
            color=COLORS[grower],
            alpha=0.15,
        )
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean temperature (°C)")
    ax.set_title("Seasonal temperature cycle by grower (5-yr avg ±1σ)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "seasonal_temperature.png", dpi=150)
    plt.close(fig)


def plot_annual_precipitation(df: pd.DataFrame, output: Path):
    annual = df.groupby(["grower", "year"])["PRECTOTCORR"].sum().reset_index()
    annual["year"] = annual["year"].astype(int)

    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.25
    years = sorted(annual["year"].unique())
    x = np.arange(len(years))
    for i, grower in enumerate(["Illinois", "Iowa", "Nebraska"]):
        subset = annual[annual["grower"] == grower].set_index("year").reindex(years)
        ax.bar(x + i * width, subset["PRECTOTCORR"], width, label=grower, color=COLORS[grower])
    ax.set_xticks(x + width)
    ax.set_xticklabels(years)
    ax.set_xlabel("Year")
    ax.set_ylabel("Total precipitation (mm)")
    ax.set_title("Annual precipitation by grower")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "annual_precipitation.png", dpi=150)
    plt.close(fig)


def plot_growing_season_climate(df: pd.DataFrame, output: Path):
    gs = df[df["month"].between(4, 9)]
    field_year = gs.groupby(["grower", "field_id", "year"]).agg(
        mean_temp=("T2M", "mean"),
        total_precip=("PRECTOTCORR", "sum"),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(8, 6))
    for grower in ["Illinois", "Iowa", "Nebraska"]:
        subset = field_year[field_year["grower"] == grower]
        ax.scatter(
            subset["mean_temp"], subset["total_precip"],
            c=COLORS[grower], label=grower, alpha=0.7, s=40,
            edgecolors="black", linewidths=0.3,
        )
    ax.set_xlabel("Mean growing-season temperature (°C)")
    ax.set_ylabel("Total growing-season precipitation (mm)")
    ax.set_title("Growing-season climate space (Apr–Sep, field-year points)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "growing_season_climate.png", dpi=150)
    plt.close(fig)


def plot_within_grower_multi_var(df: pd.DataFrame, output: Path):
    monthly = df.groupby(["grower", "month"]).agg(
        T2M=("T2M", "mean"),
        precip=("PRECTOTCORR", "mean"),
        solar=("ALLSKY_SFC_SW_DWN", "mean"),
    ).reset_index()
    monthly["month"] = monthly["month"].astype(int)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=False)
    for ax, grower in zip(axes, ["Illinois", "Iowa", "Nebraska"]):
        subset = monthly[monthly["grower"] == grower]
        ax2 = ax.twinx()

        l1 = ax.plot(subset["month"], subset["T2M"], "-o", color=COLORS[grower], linewidth=2, label="T2M")
        l2 = ax.plot(subset["month"], subset["solar"], "--s", color="darkorange", linewidth=1.5, label="Solar")
        l3 = ax2.bar(subset["month"], subset["precip"], alpha=0.25, color="steelblue", width=0.6, label="Precip")

        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"], fontsize=7)
        ax.set_xlabel("")
        ax.set_ylabel("Temperature (°C) / Solar (kWh/m²/d)", fontsize=8)
        ax2.set_ylabel("Mean daily precip (mm)", fontsize=8)
        ax.set_title(grower, fontsize=10)

        all_lines = l1 + l2
        labels = [l.get_label() for l in all_lines]
        ax.legend(all_lines + [l3], labels + ["Precip"], loc="upper left", fontsize=6)

    fig.suptitle("Within-grower multi-variable weather cycle (5-yr monthly means)", fontsize=11)
    fig.tight_layout()
    fig.savefig(output / "within_grower_weather_cycle.png", dpi=150)
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Loading weather data for all growers...")
    df = load_weather()
    print(f"  {len(df)} daily records loaded ({df['field_id'].nunique()} fields)")

    print("Plotting seasonal temperature...")
    plot_seasonal_temperature(df, OUTPUT)

    print("Plotting annual precipitation...")
    plot_annual_precipitation(df, OUTPUT)

    print("Plotting growing-season climate space...")
    plot_growing_season_climate(df, OUTPUT)

    print("Plotting within-grower multi-variable weather cycle...")
    plot_within_grower_multi_var(df, OUTPUT)

    print(f"Done. Outputs in {OUTPUT}")


if __name__ == "__main__":
    main()
