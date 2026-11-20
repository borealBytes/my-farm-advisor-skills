"""CDL category: crop composition, rotation timeline, rotation analysis, crop map."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import maps, metrics, style
from .context import Analysis

CATEGORY = "cdl"


def run(analysis: Analysis) -> dict[str, list[Path]]:
    analysis.ensure_dirs()
    written: dict[str, list[Path]] = {"figures": [], "maps": [], "tables": []}
    written["figures"].append(_figure_composition(analysis))
    written["figures"].append(_figure_rotation(analysis))
    written["tables"].append(_analysis_table(analysis))
    written["maps"].append(_map_2023(analysis))
    return written


def _share_matrix(cdl: pd.DataFrame) -> pd.DataFrame:
    """Mean percentage per field and crop, renormalised to 100% per field."""

    matrix = (
        cdl.groupby(["grower", "field_id", "crop_name"])["pct"]
        .mean()
        .unstack(fill_value=0.0)
    )
    totals = matrix.sum(axis=1).replace(0, np.nan)
    return matrix.div(totals, axis=0).fillna(0.0)


# --------------------------------------------------------------------------- #
# F3 — composition
# --------------------------------------------------------------------------- #


def _figure_composition(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    shares = _share_matrix(analysis.cdl)
    crops = style.ordered_crops(shares.columns)
    shares = shares.reindex(columns=crops, fill_value=0.0)

    growers = list(analysis.growers)
    fig, axes = plt.subplots(
        1, len(growers), figsize=(4.4 * len(growers) + 1.1, 5.0), sharex=True
    )
    if len(growers) == 1:
        axes = [axes]

    y_max = 0
    for ax, grower in zip(axes, growers):
        subset = shares.loc[shares.index.get_level_values("grower") == grower.label]
        subset = subset.reindex(
            subset.get("Corn", pd.Series(0.0, index=subset.index)).sort_values(ascending=True).index
        )
        y_max = max(y_max, len(subset))
        left = np.zeros(len(subset))
        for crop in crops:
            values = subset[crop].to_numpy() * 100.0
            ax.barh(
                np.arange(len(subset)), values, left=left,
                color=style.crop_color(crop), edgecolor="white", linewidth=0.5,
                height=0.78, zorder=3,
            )
            left += values
        ax.set_yticks(np.arange(len(subset)))
        ax.set_yticklabels(subset.index.get_level_values("field_id"), fontsize=7.2)
        ax.set_xlim(0, 100)
        ax.set_xlabel("share of classified area (%)")
        ax.grid(axis="x", color=style.GRID, linewidth=0.6)
        ax.grid(axis="y", visible=False)
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"{len(subset)} fields",
        )

    for ax in axes:
        ax.set_ylim(-0.6, y_max - 0.4)

    handles = style.crop_legend(crops)
    fig.legend(handles=handles, loc="lower center", ncol=min(len(crops), 5),
               bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=7.6)
    fig.suptitle("What each field grows, 2019-2023 mean share",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))

    path = analysis.figures_dir / "03_cdl_composition.png"
    style.save_figure(fig, path, analysis.dpi)

    corn = shares.get("Corn", pd.Series(dtype=float))
    style.write_caption(
        path,
        title="F3 — Crop composition by field",
        question="What does each field grow across 2019-2023?",
        story=(
            "Nebraska is corn-dominated, Iowa leans soybean, and Illinois is "
            "corn-leaning with a grass meadow outlier. The three growers are running "
            "recognisably different cropping systems, not just different fields."
        ),
        caveat=(
            "Five-year mean shares. A field that alternates corn and soybean still "
            "reads as roughly 50/50 here; the year-by-year sequence is F4. Bars are "
            "renormalised to the classified total, so partial CDL coverage can lift "
            "the apparent share of a class."
        ),
        inputs=analysis.input_names(),
        notes=[
            f"CDL is 30 m raster: the smallest field-year in this run has "
            f"{int(analysis.cdl.groupby(['field_id', 'year'])['pixel_count'].sum().min())} pixels.",
        ],
    )
    return path


# --------------------------------------------------------------------------- #
# F4 — rotation timeline
# --------------------------------------------------------------------------- #


def _figure_rotation(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    style.apply_style()
    dominant = analysis.dominant
    crops = style.ordered_crops(dominant["dominant_crop"].unique())
    lookup = {crop: index for index, crop in enumerate(crops)}
    cmap = ListedColormap([style.crop_color(crop) for crop in crops])
    norm = BoundaryNorm(np.arange(-0.5, len(crops) + 0.5), cmap.N)
    years = sorted(dominant["year"].unique())

    growers = list(analysis.growers)
    fig, axes = plt.subplots(
        1, len(growers), figsize=(4.0 * len(growers) + 1.4, 5.0), sharey=False
    )
    if len(growers) == 1:
        axes = [axes]

    y_max = 0
    for ax, grower in zip(axes, growers):
        subset = dominant[dominant["grower"] == grower.label].copy()
        grid = subset.pivot(index="field_id", columns="year", values="dominant_crop")
        grid = grid.reindex(columns=years)
        field_order = sorted(
            grid.index,
            key=lambda field: (
                -int((grid.loc[field] == "Corn").sum()),
                field,
            ),
        )
        grid = grid.loc[field_order]
        y_max = max(y_max, len(grid))
        codes = grid.map(lambda value: lookup.get(value, np.nan)).to_numpy(dtype=float)
        masked = np.ma.masked_invalid(codes)

        ax.imshow(
            masked, cmap=cmap, norm=norm, aspect="auto",
            interpolation="nearest", zorder=3,
        )
        for row in range(codes.shape[0]):
            for column in range(codes.shape[1]):
                if np.isfinite(codes[row, column]):
                    ax.text(column, row, years[column], ha="center", va="center",
                            fontsize=6.4, color="white", fontweight="bold", zorder=4)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([str(year) for year in years], fontsize=8)
        ax.set_yticks(range(len(grid)))
        ax.set_yticklabels(grid.index, fontsize=7.2)
        ax.set_xticks(np.arange(-0.5, len(years), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(grid), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.4)
        ax.grid(which="major", visible=False)
        ax.tick_params(which="minor", length=0)
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"{len(grid)} fields",
        )

    for ax in axes:
        ax.set_ylim(y_max - 0.5, -0.5)

    handles = style.crop_legend(crops)
    fig.legend(handles=handles, loc="lower center", ncol=min(len(crops), 5),
               bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=7.6)
    fig.suptitle("Five-year rotation sequence, field by field",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))

    path = analysis.figures_dir / "04_cdl_rotation.png"
    style.save_figure(fig, path, analysis.dpi)

    style.write_caption(
        path,
        title="F4 — Crop rotation timeline",
        question="How does each field rotate, year by year?",
        story=(
            "Illinois and Iowa alternate corn and soybean almost everywhere. "
            "Nebraska holds corn for multi-year runs, which is what the "
            "corn-after-corn rate in cdl_analysis.csv quantifies. Rotation is a "
            "field-level property, and it is the clearest within-field signal in "
            "this dataset."
        ),
        caveat=(
            "Five years only, 2019-2023. No 2024 or 2025, so no completed rotation "
            "cycle is guaranteed and the pipeline's predicted next crop cannot be "
            "tested here."
        ),
        inputs=analysis.input_names(),
        notes=[
            "Cell label is the year; colour is the dominant crop by CDL percentage.",
            "Dominant crop can hide a split field: check the shares in F3.",
            f"CDL is 30 m raster: the smallest field-year in this run has "
            f"{int(analysis.cdl.groupby(['field_id', 'year'])['pixel_count'].sum().min())} pixels.",
        ],
    )
    return path


# --------------------------------------------------------------------------- #
# A2 — rotation analysis
# --------------------------------------------------------------------------- #


def _analysis_table(analysis: Analysis) -> Path:
    dominant = analysis.dominant
    years = sorted(dominant["year"].unique())
    rows: list[dict] = []

    def add(group: str, metric: str, value: float, *, low=np.nan, high=np.nan,
            p_value=np.nan, n: int = 0, note: str = "") -> None:
        rows.append(
            {
                "scope": "grower",
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

    for grower in analysis.growers:
        subset = dominant[dominant["grower"] == grower.label]
        field_years = len(subset)
        corn_years = int((subset["dominant_crop"] == "Corn").sum())
        soy_years = int((subset["dominant_crop"] == "Soybeans").sum())
        # Denominator: corn field-years that also have a preceding year in the
        # window. Including 2019 (no previous year) would understate the rate.
        eligible = int(
            ((subset["dominant_crop"] == "Corn") & subset["has_previous"]).sum()
        )
        consecutive = int(subset["corn_after_corn"].sum())
        low, high = metrics.wilson_interval(consecutive, eligible)

        add(grower.label, "fields", subset["field_id"].nunique(),
            n=subset["field_id"].nunique())
        add(grower.label, "corn_share_field_years", corn_years / field_years,
            n=field_years)
        add(grower.label, "soybean_share_field_years", soy_years / field_years,
            n=field_years)
        add(grower.label, "corn_after_corn_rate", consecutive / eligible if eligible else np.nan,
            low=low, high=high, n=eligible,
            note=f"{consecutive}/{eligible} corn field-years with a preceding year; Wilson 95%")
        add(grower.label, "mean_shannon_diversity",
            float(_mean_diversity(subset)), n=subset["field_id"].nunique())

        patterns = (
            subset.sort_values(["field_id", "year"])
            .groupby("field_id")["dominant_crop"]
            .apply(lambda values: " -> ".join(values))
        )
        top = patterns.value_counts()
        add(grower.label, "top_rotation_pattern_share", float(top.iloc[0] / len(patterns)),
            n=len(patterns), note=str(top.index[0]))

    # Crop mix by grower: chi-square with Cramer's V.
    table = (
        dominant.assign(count=1)
        .pivot_table(index="dominant_crop", columns="grower", values="count",
                     aggfunc="sum", fill_value=0)
    )
    test = metrics.chi_square(table)
    rows.append(
        {
            "scope": "all",
            "group": "crop_mix_by_grower",
            "metric": "cramers_v",
            "value": round(test["cramers_v"], 4) if np.isfinite(test["cramers_v"]) else None,
            "ci_low": None,
            "ci_high": None,
            "p_value": round(test["p"], 4) if np.isfinite(test["p"]) else None,
            "n": int(len(dominant)),
            "note": (
                f"chi-square={test['chi2']:.2f}, dof={test['dof']}; "
                f"window {min(years)}-{max(years)}"
            ),
        }
    )

    frame = pd.DataFrame(rows)
    frame.to_csv(analysis.tables_dir / "cdl_analysis.csv", index=False)
    return analysis.tables_dir / "cdl_analysis.csv"


def _mean_diversity(subset: pd.DataFrame) -> pd.Series:
    return (
        subset.sort_values(["field_id", "year"])
        .groupby("field_id")["dominant_crop"]
        .apply(metrics.shannon_diversity)
    ).mean()


# --------------------------------------------------------------------------- #
# M2 — 2023 crop map
# --------------------------------------------------------------------------- #


def _map_2023(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    style.apply_style()
    dominant = analysis.dominant
    latest = int(dominant["year"].max())
    snapshot = dominant[dominant["year"] == latest][["grower", "field_id", "dominant_crop"]]
    fields = analysis.fields.merge(
        snapshot, on=["grower", "field_id"], how="left", validate="one_to_one"
    )
    crops = style.ordered_crops(snapshot["dominant_crop"].dropna().unique())
    lookup = {crop: index for index, crop in enumerate(crops)}
    cmap = ListedColormap([style.crop_color(crop) for crop in crops])
    norm = BoundaryNorm(np.arange(-0.5, len(crops) + 0.5), cmap.N)

    growers = list(analysis.growers)
    fig, axes = plt.subplots(1, len(growers), figsize=(4.3 * len(growers) + 1.0, 4.9))
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        subset = fields[fields["grower_slug"] == grower.slug].copy()
        projected = maps.project_farm(subset)
        projected["crop_code"] = projected["dominant_crop"].map(lookup).astype(float)
        missing = projected["crop_code"].isna()
        if missing.any():
            projected[missing].plot(ax=ax, facecolor="#e5e7eb", edgecolor="white",
                                    linewidth=0.7, zorder=2)
        layer = projected[~missing]
        layer.plot(
            ax=ax, column="crop_code", cmap=cmap, norm=norm,
            edgecolor="white", linewidth=0.7, zorder=3,
        )
        maps.decorate(ax, projected)
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"{latest} · {len(subset)} fields",
        )

    handles = style.crop_legend(crops)
    fig.legend(handles=handles, loc="lower center", ncol=min(len(crops), 5),
               bbox_to_anchor=(0.5, -0.02), frameon=False, fontsize=7.6)
    fig.suptitle(f"What was planted in {latest}",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))

    path = analysis.maps_dir / "02_cdl_2023.png"
    style.save_figure(fig, path, analysis.dpi)

    style.write_caption(
        path,
        title=f"M2 — {latest} crop map",
        question="What was planted where in the most recent CDL year?",
        story=(
            "Corn and soybean blocks separate spatially, Nebraska is almost solid "
            "corn, and the Illinois grass outlier stands out immediately. One shared "
            "legend is used for every grower so the colours mean the same crop "
            "across panels."
        ),
        caveat=(
            f"30 m CDL pixels. The smallest field-year in this run has "
            f"{int(analysis.cdl.groupby(['field_id', 'year'])['pixel_count'].sum().min())} "
            "pixels, so a small parcel's class is a handful of pixels rather than a "
            "clean field average."
        ),
        inputs=analysis.input_names(),
        notes=["Farm overview in local UTM kilometres; no auto-rotation."],
    )
    return path
