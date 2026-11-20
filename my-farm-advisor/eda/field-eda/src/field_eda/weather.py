"""Weather category: seasonal heat, monthly water, variance analysis, precip map."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import maps, metrics, style
from .context import Analysis

CATEGORY = "weather"
SEASON_TICKS = [(1, "Apr"), (31, "May"), (61, "Jun"), (91, "Jul"), (122, "Aug"), (153, "Sep")]


def run(analysis: Analysis) -> dict[str, list[Path]]:
    analysis.ensure_dirs()
    written: dict[str, list[Path]] = {"figures": [], "maps": [], "tables": []}
    written["figures"].append(_figure_gdd(analysis))
    written["figures"].append(_figure_precip(analysis))
    written["tables"].append(_analysis_table(analysis))
    written["maps"].append(_map_precip(analysis))
    return written


# --------------------------------------------------------------------------- #
# F5 — cumulative GDD
# --------------------------------------------------------------------------- #


def _figure_gdd(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    daily = metrics.daily_grower_series(analysis.season)
    years = sorted(daily["year"].unique())
    colours = plt.cm.viridis(np.linspace(0.12, 0.86, len(years)))

    growers = list(analysis.growers)
    fig, axes = plt.subplots(1, len(growers), figsize=(4.0 * len(growers) + 1.4, 4.5),
                             sharey=True)
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        for colour, year in zip(colours, years):
            subset = daily[(daily["grower"] == grower.label) & (daily["year"] == year)]
            if subset.empty:
                continue
            ax.plot(subset["day_of_season"], subset["cumulative_gdd"],
                    color=colour, linewidth=1.3, alpha=0.9, zorder=3)
        mean_curve = (
            daily[daily["grower"] == grower.label]
            .groupby("day_of_season")["cumulative_gdd"].mean()
        )
        ax.plot(mean_curve.index, mean_curve.to_numpy(), color=style.grower_color(grower.label),
                linewidth=2.6, alpha=0.35, zorder=2)
        ax.set_xticks([tick for tick, _ in SEASON_TICKS])
        ax.set_xticklabels([label for _, label in SEASON_TICKS])
        ax.set_xlabel("growing season")
        ax.grid(axis="x", visible=False)
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"mean season total {mean_curve.iloc[-1]:,.0f} GDD",
        )

    axes[0].set_ylabel("cumulative GDD (\u00b0C-days, base 10)")
    handles = [
        plt.Line2D([], [], color=colour, linewidth=1.6, label=str(year))
        for colour, year in zip(colours, years)
    ]
    fig.legend(handles=handles, loc="lower center", ncol=len(years),
               bbox_to_anchor=(0.5, -0.01), frameon=False)
    fig.suptitle("Heat accumulation through the season, April-September",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))

    path = analysis.figures_dir / "05_weather_gdd.png"
    style.save_figure(fig, path, analysis.dpi)

    by_grower = analysis.field_year_weather.groupby("grower")["gdd"].mean()
    spread = (
        analysis.field_year_weather.groupby(["grower", "year"])["gdd"].std().groupby("grower").mean()
    )
    style.write_caption(
        path,
        title="F5 — Cumulative growing degree days",
        question="How does each season accumulate heat, and how much does that differ?",
        story=(
            "Nebraska accumulates about "
            f"{by_grower.get('NE', float('nan')):,.0f} GDD against "
            f"{by_grower.get('IL', float('nan')):,.0f} in Illinois and "
            f"{by_grower.get('IA', float('nan')):,.0f} in Iowa, and separates early in "
            "the season. Year-to-year spread inside a grower is small next to the "
            "between-grower gap."
        ),
        caveat=(
            "Five seasons, GDD base 10 \u00b0C with no upper cap, April-September. "
            f"Weather comes from {max(grower.grid_cells for grower in analysis.growers)} "
            "grid cells at most per grower, so this is a regional curve rather than an "
            "on-farm measurement."
        ),
        inputs=analysis.input_names(),
        notes=[f"Within-grower field spread of seasonal GDD is {spread.min():,.0f}-{spread.max():,.0f} GDD."],
    )
    return path


# --------------------------------------------------------------------------- #
# F6 — monthly precipitation
# --------------------------------------------------------------------------- #


def _figure_precip(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    monthly = metrics.monthly_weather(analysis.season)
    config = analysis.dataset.config
    months = list(range(config.season_start_month, config.season_end_month + 1))
    names = [metrics.SEASON_MONTHS[month - 1] for month in months]
    years = sorted(monthly["year"].unique())
    rng = np.random.default_rng(config.seed)

    growers = list(analysis.growers)
    fig, axes = plt.subplots(1, len(growers), figsize=(4.0 * len(growers) + 1.4, 4.5),
                             sharey=True)
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        subset = monthly[monthly["grower"] == grower.label]
        climatology = subset.groupby("month")["precip_mm"].mean().reindex(months)
        ax.bar(np.arange(len(months)), climatology.to_numpy(), width=0.66,
               color=style.grower_color(grower.label), alpha=0.78,
               edgecolor="white", linewidth=0.6, zorder=2)

        for index, month in enumerate(months):
            values = subset[subset["month"] == month]["precip_mm"].to_numpy()
            jitter = rng.uniform(-0.16, 0.16, len(values))
            ax.scatter(index + jitter, values, s=14, color=style.INK, alpha=0.55,
                       linewidth=0, zorder=4)

        wettest = climatology.idxmax()
        ax.annotate(
            f"wettest month\n{climatology.max():.0f} mm",
            xy=(months.index(wettest), climatology.max()),
            xytext=(10, 6), textcoords="offset points",
            ha="left", fontsize=7.0, color=style.MUTED,
            arrowprops=dict(arrowstyle="-", color=style.MUTED, linewidth=0.7),
        )
        ax.set_xticks(np.arange(len(months)))
        ax.set_xticklabels(names)
        ax.set_xlabel("month")
        ax.grid(axis="x", visible=False)
        total = float(subset.groupby("year")["precip_mm"].sum().mean())
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"mean season total {total:,.0f} mm",
        )

    axes[0].set_ylabel("monthly precipitation (mm)")
    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=style.MUTED, alpha=0.7,
                      label="monthly mean, 5 years"),
        plt.Line2D([], [], marker="o", linestyle="none", color=style.INK,
                   alpha=0.6, markersize=4, label="individual season"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.01),
               frameon=False)
    fig.suptitle("When the water arrives, April-September",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))

    path = analysis.figures_dir / "06_weather_precip.png"
    style.save_figure(fig, path, analysis.dpi)

    totals = analysis.field_year_weather.groupby("grower")["precip_mm"].mean()
    style.write_caption(
        path,
        title="F6 — Monthly precipitation",
        question="When does the water arrive, and how variable is it?",
        story=(
            "Nebraska is drier in every month "
            f"({totals.get('NE', float('nan')):,.0f} mm seasonal mean) than Illinois "
            f"({totals.get('IL', float('nan')):,.0f} mm) and Iowa "
            f"({totals.get('IA', float('nan')):,.0f} mm). Monthly shape is broadly "
            "similar, and the individual dots show how much one season can move the "
            "monthly total."
        ),
        caveat=(
            "Daily sums from a coarse NASA POWER grid, not gauge data. "
            f"Grid cells per grower: "
            + ", ".join(f"{grower.label} {grower.grid_cells}" for grower in analysis.growers)
            + ". Within-grower field differences are grid artefacts."
        ),
        inputs=analysis.input_names(),
    )
    return path


# --------------------------------------------------------------------------- #
# A3 — variance attribution
# --------------------------------------------------------------------------- #


def _analysis_table(analysis: Analysis) -> Path:
    field_year = analysis.field_year_weather
    config = analysis.dataset.config
    rows: list[dict] = []

    def add(scope: str, group: str, metric: str, value: float, *, n: int = 0,
            low=np.nan, high=np.nan, p_value=np.nan, note: str = "") -> None:
        rows.append(
            {
                "scope": scope,
                "group": group,
                "metric": metric,
                "value": None if not np.isfinite(value) else round(float(value), 4),
                "ci_low": None if not np.isfinite(low) else round(float(low), 4),
                "ci_high": None if not np.isfinite(high) else round(float(high), 4),
                "p_value": None if not np.isfinite(p_value) else round(float(p_value), 4),
                "n": int(n),
                "note": note,
            }
        )

    for measure in ("precip_mm", "gdd", "heat_days"):
        shares = metrics.variance_shares(field_year, measure)
        for component, key in (
            ("between_growers", "between"),
            ("between_years_within_grower", "year_within"),
            ("within_grower_year", "residual"),
        ):
            add("variance", measure, component, shares[key], n=len(field_year),
                note="percent of total sum of squares")

    for grower in analysis.growers:
        subset = field_year[field_year["grower"] == grower.label]
        add("grower", grower.label, "seasonal_precip_mm_mean",
            subset["precip_mm"].mean(), n=int(subset["field_id"].nunique()))
        add("grower", grower.label, "seasonal_gdd_mean",
            subset["gdd"].mean(), n=int(subset["field_id"].nunique()))
        add("grower", grower.label, "heat_days_mean",
            subset["heat_days"].mean(), n=int(subset["field_id"].nunique()))

        per_field = subset.groupby("field_id")[["precip_mm", "gdd"]].mean()
        add("within_grower", grower.label, "field_precip_mm_sd",
            float(per_field["precip_mm"].std(ddof=1)),
            n=int(per_field["precip_mm"].notna().sum()),
            note=f"{grower.grid_cells} NASA POWER grid cell(s) in this grower")
        add("within_grower", grower.label, "field_gdd_sd",
            float(per_field["gdd"].std(ddof=1)),
            n=int(per_field["gdd"].notna().sum()))

    grower_year = metrics.grower_year_weather(field_year)
    coupling = metrics.spearman_with_ci(
        grower_year["precip_mm"], grower_year["gdd"],
        seed=config.seed, n_boot=config.bootstrap,
    )
    add("coupling", "grower_years", "spearman_precip_gdd", coupling["rho"],
        low=coupling["low"], high=coupling["high"], p_value=coupling["p"],
        n=coupling["n"], note="across grower-years; bootstrap 2.5-97.5")

    frame = pd.DataFrame(rows)
    frame.to_csv(analysis.tables_dir / "weather_analysis.csv", index=False)
    return analysis.tables_dir / "weather_analysis.csv"


# --------------------------------------------------------------------------- #
# M3 — seasonal precipitation map
# --------------------------------------------------------------------------- #


def _map_precip(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    per_field = metrics.field_year_precip_map(analysis.field_year_weather)
    fields = analysis.fields.merge(per_field, on=["grower", "field_id"], how="left",
                                   validate="one_to_one")
    values = fields["precip_mm"].dropna()
    vmin = float(np.floor(values.min() / 10.0) * 10.0)
    vmax = float(np.ceil(values.max() / 10.0) * 10.0)
    if vmax <= vmin:
        vmax = vmin + 10.0

    growers = list(analysis.growers)
    fig, axes = plt.subplots(1, len(growers),
                             figsize=(4.3 * len(growers) + 1.0, 4.9))
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        subset = fields[fields["grower_slug"] == grower.slug].copy()
        projected = maps.project_farm(subset)
        layer = projected.dropna(subset=["precip_mm"])
        layer.plot(
            ax=ax, column="precip_mm", cmap="YlGnBu", vmin=vmin, vmax=vmax,
            edgecolor="white", linewidth=0.7, legend=False, zorder=3,
        )
        maps.decorate(ax, projected)
        value = subset["precip_mm"].mean()
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"{value:,.0f} mm mean · {grower.grid_cells} grid cell(s)",
        )

    import matplotlib.cm as cm
    import matplotlib.colors as mcolors

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    scalar = cm.ScalarMappable(norm=norm, cmap="YlGnBu")
    scalar.set_array(np.array([vmin, vmax]))
    fig.subplots_adjust(bottom=0.24, top=0.84, wspace=0.24)
    cax = fig.add_axes([0.33, 0.09, 0.34, 0.020])
    bar = fig.colorbar(scalar, cax=cax, orientation="horizontal")
    bar.set_label("mean Apr-Sep precipitation, 2021-2025 (mm)", fontsize=8, labelpad=4)
    bar.ax.tick_params(labelsize=7.5)

    fig.suptitle("Within a grower the colour barely changes; between growers it does",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")

    path = analysis.maps_dir / "03_weather_precip.png"
    style.save_figure(fig, path, analysis.dpi)

    spread = (
        analysis.field_year_weather.groupby(["grower", "year"])["precip_mm"].std().groupby("grower").mean()
    )
    style.write_caption(
        path,
        title="M3 — Seasonal precipitation by field",
        question="Does within-grower weather actually vary in space?",
        story=(
            "Visibly barely. Fields inside a grower sit in the same narrow colour "
            "band; the contrast is between Nebraska and the two eastern growers. "
            "This is the spatial evidence for the null result in "
            "weather_analysis.csv, not an assertion of it."
        ),
        caveat=(
            "The colour scale is shared across all three panels on purpose. On a "
            "per-grower scale the within-grower differences would look dramatic and "
            "would be an artefact of the stretch. "
            f"Mean within-grower field SD: "
            + ", ".join(f"{grower.label} {spread[grower.label]:.1f} mm"
                        for grower in analysis.growers)
            + "."
        ),
        inputs=analysis.input_names(),
        notes=["Colour is the five-season mean per field; the grid cell, not the field, is the unit of variation."],
    )
    return path
