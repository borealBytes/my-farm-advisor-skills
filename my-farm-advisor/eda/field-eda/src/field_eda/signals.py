"""Signals category: maturity fit, rotation continuity, and weather risk windows.

These are the decision-facing readings that combine the three data layers. They
stay descriptive: no yield or cost is claimed, because the runtime carries none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import metrics, style
from .context import Analysis

CATEGORY = "signals"
TARGET_LINE = "#8c2f39"


def run(analysis: Analysis) -> dict[str, list[Path]]:
    analysis.ensure_dirs()
    written: dict[str, list[Path]] = {"figures": [], "maps": [], "tables": []}
    written["figures"].append(_figure_maturity(analysis))
    written["tables"].append(_analysis_table(analysis))
    return written


# --------------------------------------------------------------------------- #
# F7 — maturity fit
# --------------------------------------------------------------------------- #


def _season_gap(frame: pd.DataFrame) -> pd.Series:
    """Grower-year mean full-year GDD minus the county requirement.

    Negative means the season as a whole came in under the county target. This
    is deliberately a grower-year comparison: a field-year can dip below target
    while the season is normal, and calling that a failed season would overstate
    the signal.
    """
    if frame.empty:
        return pd.Series(dtype=float)
    required = float(frame["gdd_required_c"].mean())
    return frame.groupby("year")["gdd_maturity"].mean() - required


def _figure_maturity(analysis: Analysis) -> Path:
    import matplotlib.patheffects as path_effects
    import matplotlib.pyplot as plt

    style.apply_style()
    fit = analysis.field_maturity
    years = sorted(fit["year"].unique())
    rng = np.random.default_rng(analysis.dataset.config.seed)
    growers = list(analysis.growers)

    fig, axes = plt.subplots(
        1, len(growers), figsize=(3.7 * len(growers) + 1.1, 4.7), sharey=True
    )
    if len(growers) == 1:
        axes = [axes]

    values = fit["gdd_maturity"].dropna()
    targets = fit["gdd_required_c"].dropna()
    y_low = float(min(values.min(), targets.min())) - 45.0
    y_high = float(max(values.max(), targets.max())) + 95.0

    for ax, grower in zip(axes, growers):
        subset = fit[fit["grower"] == grower.label]
        county = analysis.maturity_targets[subset["county_fips"].iloc[0]]
        target = county.gdd_required_c

        ax.axhline(
            target, color=TARGET_LINE, linewidth=1.4, linestyle=(0, (5, 3)), zorder=2
        )

        by_year = _season_gap(subset)
        for index, year in enumerate(years):
            field_values = subset[subset["year"] == year]["gdd_maturity"].to_numpy()
            jitter = rng.uniform(-0.16, 0.16, len(field_values))
            ax.scatter(
                index + jitter, field_values, s=16,
                color=style.grower_color(grower.label), alpha=0.55,
                edgecolors="white", linewidths=0.4, zorder=4,
            )
            mean = float(np.mean(field_values))
            (line,) = ax.plot(
                [index - 0.22, index + 0.22], [mean, mean],
                color=style.INK, linewidth=2.2, solid_capstyle="butt", zorder=5,
            )
            line.set_path_effects(
                [path_effects.withStroke(linewidth=4.0, foreground="white")]
            )

        short = int((by_year < 0).sum())
        gap = float((subset["gdd_maturity"] - subset["gdd_required_c"]).mean())
        direction = "above" if gap >= 0 else "below"
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"mean {abs(gap):,.0f} GDD {direction} RM {county.rm_target:.1f}"
            f" · {short} of {len(by_year)} seasons short",
        )
        ax.set_xticks(np.arange(len(years)))
        ax.set_xticklabels([str(year) for year in years])
        ax.set_xlim(-0.5, len(years) - 0.5)
        ax.set_xlabel("Year")
        ax.grid(axis="x", visible=False)

    axes[0].set_ylim(y_low, y_high)
    axes[0].set_ylabel(
        "Full-year GDD\n(\u00b0C-days, base 10, cap 30)", fontsize=10.5
    )

    handles = [
        plt.Line2D([], [], marker="o", linestyle="none", color=style.MUTED,
                   markersize=5, label="field"),
        plt.Line2D([], [], color=style.INK, linewidth=2.2, label="grower mean"),
        plt.Line2D([], [], color=TARGET_LINE, linewidth=1.4, linestyle=(0, (5, 3)),
                   label="county RM target"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.01),
               frameon=False)
    fig.suptitle("Heat received against the maturity the county recommends",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 0.995, 0.95))

    path = analysis.figures_dir / "07_signals_maturity.png"
    style.save_figure(fig, path, analysis.dpi)

    parts = []
    for grower in growers:
        subset = fit[fit["grower"] == grower.label]
        by_year = _season_gap(subset)
        gap = float(
            (subset["gdd_maturity"] - subset["gdd_required_c"]).mean()
        )
        worst_year = int(by_year.idxmin())
        worst = float(-by_year.min())
        short = int((by_year < 0).sum())
        where = "below" if gap < 0 else "above"
        if short:
            parts.append(
                f"{grower.label} sits {abs(gap):,.0f} GDD {where} its county "
                f"target and the season mean falls short in {short} of "
                f"{len(by_year)}, by up to {worst:,.0f} GDD "
                f"({worst / metrics.CORN_GDD_PER_RM:.1f} RM) in {worst_year}"
            )
        else:
            parts.append(
                f"{grower.label} sits {abs(gap):,.0f} GDD {where} its county "
                "target and every season mean clears it"
            )

    style.write_caption(
        path,
        title="F7 — Maturity fit against county heat",
        question=(
            "Does each season deliver the heat the county's recommended relative "
            "maturity assumes?"
        ),
        story=(
            "; ".join(parts) + ". The county target is a county-average planning "
            "value, so part of a gap is location and part is the season. A farm "
            "that sits below the county reference needs an earlier hybrid even in "
            "a normal year."
        ),
        caveat=(
            "Two GDD definitions meet here on purpose: this figure uses the whole "
            "calendar year, base 10 \u00b0C, cap 30 \u00b0C, matching "
            "maturity-by-fips; F5 and A3 use April-September with no cap. The "
            "county reference is built from the county weather table, not from "
            "these ten fields, so a level offset is location, not management. "
            "Field spread is NASA POWER grid spread, so the verdict is per grower."
        ),
        inputs=analysis.input_names(maturity=True),
        notes=[
            "Required GDD is the county RM target times 20 GDD per RM, the same "
            "linear rule the maturity product applies.",
            "Soybean maturity is latitude-regression based and has no comparable "
            "heat test, so it is reported as a reference value in A4 only.",
        ],
    )
    return path


# --------------------------------------------------------------------------- #
# A4 — field risk signals
# --------------------------------------------------------------------------- #


def _analysis_table(analysis: Analysis) -> Path:
    fit = analysis.field_maturity
    runs = metrics.corn_run_lengths(analysis.dominant)
    risk = analysis.risk
    cdl_years = sorted(analysis.dominant["year"].unique())
    rows: list[dict] = []

    def add(
        scope: str,
        group: str,
        metric: str,
        value: float,
        *,
        low=np.nan,
        high=np.nan,
        n: int = 0,
        note: str = "",
    ) -> None:
        rows.append(
            {
                "scope": scope,
                "group": group,
                "metric": metric,
                "value": None if not np.isfinite(value) else round(float(value), 4),
                "ci_low": None if not np.isfinite(low) else round(float(low), 4),
                "ci_high": None if not np.isfinite(high) else round(float(high), 4),
                "p_value": None,
                "n": int(n),
                "note": note,
            }
        )

    for grower in analysis.growers:
        label = grower.label

        # Rotation continuity: how long has corn stayed on the same field?
        grower_runs = runs[runs["grower"] == label]
        field_count = len(grower_runs)
        long_run = int((grower_runs["longest_corn_run"] >= 3).sum())
        all_years = int(
            (grower_runs["longest_corn_run"] >= len(cdl_years)).sum()
        )
        low, high = metrics.wilson_interval(long_run, field_count)
        add(
            "grower", label, "field_share_corn_run_3plus",
            long_run / field_count if field_count else np.nan,
            low=low, high=high, n=field_count,
            note=(
                f"{long_run}/{field_count} fields with a corn run of 3+ years "
                f"in {len(cdl_years)} CDL years; Wilson 95%"
            ),
        )
        add(
            "grower", label, "field_share_corn_all_years",
            all_years / field_count if field_count else np.nan,
            n=field_count,
            note=f"{all_years}/{field_count} fields never left corn",
        )
        add(
            "grower", label, "max_corn_run_years",
            float(grower_runs["longest_corn_run"].max()), n=field_count,
            note=f"longest run in the {len(cdl_years)}-year CDL window",
        )

        # Maturity fit: seasons and field-years below the county requirement.
        grower_fit = fit[fit["grower"] == label]
        if not grower_fit.empty:
            county = analysis.maturity_targets[grower_fit["county_fips"].iloc[0]]
            by_year = _season_gap(grower_fit)
            short = int((by_year < 0).sum())
            low, high = metrics.wilson_interval(short, len(by_year))
            worst_year = int(by_year.idxmin())
            worst = float(-by_year.min())
            below_field_years = int((grower_fit["shortfall_c"] > 0).sum())
        else:  # pragma: no cover - discovery already rejects this
            county, by_year = None, pd.Series(dtype=float)
            short = 0
            low = high = np.nan
            worst = 0.0
            worst_year = 0
            below_field_years = 0

        add(
            "grower", label, "county_rm_target",
            county.rm_target if county else np.nan,
            n=len(by_year),
            note=(
                f"{county.county_name} County ({county.fips})"
                if county else "county unknown"
            ),
        )
        add(
            "grower", label, "gdd_required_c",
            county.gdd_required_c if county else np.nan,
            n=len(by_year), note="RM target x 20 GDD per RM",
        )
        add(
            "grower", label, "season_share_below_target",
            short / len(by_year) if len(by_year) else np.nan,
            low=low, high=high, n=len(by_year),
            note=f"{short}/{len(by_year)} season means; Wilson 95%",
        )
        add(
            "grower", label, "max_season_shortfall_c", worst,
            n=len(by_year),
            note=(
                f"{worst_year} · equal to "
                f"{worst / metrics.CORN_GDD_PER_RM:.1f} RM"
            ),
        )
        add(
            "grower", label, "field_year_share_below_target",
            below_field_years / len(grower_fit) if len(grower_fit) else np.nan,
            n=len(grower_fit),
            note=f"{below_field_years}/{len(grower_fit)} field-years",
        )
        mean_gap = (
            float(
                (grower_fit["gdd_maturity"] - grower_fit["gdd_required_c"]).mean()
            )
            if len(grower_fit)
            else np.nan
        )
        add(
            "grower", label, "mean_gdd_gap_c", mean_gap,
            n=len(grower_fit),
            note=(
                "received minus required; negative means cooler than the county "
                "reference"
            ),
        )
        add(
            "grower", label, "soybean_mg_reference",
            county.soybean_mg if county and county.soybean_mg is not None else np.nan,
            n=1, note="county reference, latitude regression; no heat test",
        )

        # Weather risk windows inside the growing season.
        grower_risk = risk[risk["grower"] == label]
        dry_peak = grower_risk.loc[grower_risk["dry_spell_days"].idxmax()]
        heat_peak = grower_risk.loc[grower_risk["july_heat_days"].idxmax()]
        add(
            "grower", label, "mean_dry_spell_days",
            float(grower_risk["dry_spell_days"].mean()), n=len(grower_risk),
            note=(
                f"longest run below {metrics.DRY_SPELL_MM:g} mm/day; "
                f"max {int(dry_peak['dry_spell_days'])} days in {int(dry_peak['year'])}"
            ),
        )
        add(
            "grower", label, "mean_july_heat_days",
            float(grower_risk["july_heat_days"].mean()), n=len(grower_risk),
            note=(
                f"July days above {metrics.HEAT_THRESHOLD_C:g} \u00b0C; "
                f"max {int(heat_peak['july_heat_days'])} in {int(heat_peak['year'])}"
            ),
        )
        add(
            "grower", label, "mean_jul_aug_precip_mm",
            float(grower_risk["jul_aug_precip_mm"].mean()), n=len(grower_risk),
            note="pollination-window water",
        )

    frame = pd.DataFrame(rows)
    frame.to_csv(analysis.tables_dir / "field_signals.csv", index=False)
    return analysis.tables_dir / "field_signals.csv"
