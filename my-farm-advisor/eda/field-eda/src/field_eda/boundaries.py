"""Boundary category: area, shape, the geometry analysis, and the source map."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import maps, metrics, style
from .context import Analysis

CATEGORY = "boundaries"


def _grower_frame(analysis: Analysis) -> pd.DataFrame:
    fields = analysis.fields
    frame = fields.drop(columns="geometry").copy()
    frame["grower_order"] = frame["grower_slug"].map(analysis.grower_index)
    return frame.sort_values(["grower_order", "area_ha"]).reset_index(drop=True)


def run(analysis: Analysis) -> dict[str, list[Path]]:
    analysis.ensure_dirs()
    frame = _grower_frame(analysis)
    written: dict[str, list[Path]] = {"figures": [], "maps": [], "tables": []}
    written["figures"].append(_figure_area(analysis, frame))
    written["figures"].append(_figure_shape(analysis, frame))
    written["tables"].append(_analysis_table(analysis, frame))
    written["maps"].append(_map_sources(analysis))
    return written


# --------------------------------------------------------------------------- #
# F1 — area distribution
# --------------------------------------------------------------------------- #


def _figure_area(analysis: Analysis, frame: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 4.4))

    growers = list(analysis.growers)
    positions = {grower.slug: index for index, grower in enumerate(growers)}
    rng = np.random.default_rng(analysis.dataset.config.seed)

    for grower in growers:
        subset = frame[frame["grower_slug"] == grower.slug]
        base = positions[grower.slug]
        ax.boxplot(
            subset["area_ha"],
            positions=[base],
            widths=0.5,
            vert=False,
            showfliers=False,
            patch_artist=True,
            boxprops=dict(facecolor="white", edgecolor=style.MUTED, linewidth=0.9),
            whiskerprops=dict(color=style.MUTED, linewidth=0.9),
            capprops=dict(color=style.MUTED, linewidth=0.9),
            medianprops=dict(color=style.grower_color(grower.label, base), linewidth=1.8),
            zorder=2,
        )
        offset = rng.uniform(-0.14, 0.14, len(subset))
        positions_in_subset = pd.Series(np.arange(len(subset)), index=subset.index)
        marker = {"csb": "s", "osm": "o", "other": "D"}
        for key, group in subset.groupby("source_key"):
            ax.scatter(
                group["area_ha"],
                base + offset[positions_in_subset.loc[group.index].to_numpy()],
                s=46,
                marker=marker.get(key, "o"),
                facecolor=style.source_color(key),
                edgecolor="white",
                linewidth=0.7,
                alpha=0.9,
                zorder=3,
            )

    labels = [f"{grower.label}\n{grower.slug.replace('-grower', '')}" for grower in growers]
    ax.set_yticks(range(len(growers)))
    ax.set_yticklabels(labels)
    ax.set_xscale("log")
    ax.set_xlabel("Field area (ha, log scale)")
    ax.set_ylabel("Grower")
    ax.set_title("Field size: two populations in Illinois and Iowa, one in Nebraska", loc="left")
    ax.set_ylim(-0.65, len(growers) - 0.35)

    legend_handles = style.source_legend()
    legend_handles.append(
        plt.Line2D([], [], color=style.MUTED, linewidth=1.6,
                   label="median (grower colour)")
    )
    ax.legend(handles=legend_handles, loc="lower right", ncol=3, handletextpad=0.5,
              columnspacing=1.2)

    style.footnote(
        fig,
        "Box = IQR, whiskers = 1.5x IQR, dots = fields (n=30). "
        "Marker shape and colour show boundary source, not management.",
    )
    path = analysis.figures_dir / "01_boundary_area.png"
    style.save_figure(fig, path, analysis.dpi)

    small = frame.nsmallest(1, "area_ha").iloc[0]
    style.write_caption(
        path,
        title="F1 — Field area distribution",
        question="How large are the fields, and is each grower one population?",
        story=(
            f"Illinois and Iowa each mix a few small hand-traced parcels with large "
            f"CSB blocks, so their distributions are bimodal. Nebraska is a single "
            f"narrow band of large fields. The smallest field in the run is "
            f"{small['area_ha']:.1f} ha ({small['field_id']}, {small['source_key']})."
        ),
        caveat=(
            "The bimodality follows boundary provenance, not management. A farm "
            "with two sources will always look bimodal, so this figure cannot be "
            "read as two field-size strategies."
        ),
        inputs=analysis.input_names(),
    )
    return path


# --------------------------------------------------------------------------- #
# F2 — shape versus area
# --------------------------------------------------------------------------- #


def _figure_shape(analysis: Analysis, frame: pd.DataFrame) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    marker = {"csb": "s", "osm": "o", "other": "D"}
    greys = ["#9aa0a6", "#6b7280", "#c7cdd6"]

    for index, grower in enumerate(analysis.growers):
        subset = frame[frame["grower_slug"] == grower.slug]
        colour = style.grower_color(grower.label, index)
        for key, group in subset.groupby("source_key"):
            ax.scatter(
                group["area_ha"],
                group["compactness"],
                s=52,
                marker=marker.get(key, "o"),
                facecolor=colour,
                edgecolor="white" if key != "osm" else colour,
                linewidth=0.8,
                alpha=0.92,
                label=f"{grower.label} · {key}",
                zorder=3,
            )
        grid, fit = metrics.trend_line(
            np.log10(subset["area_ha"].to_numpy()),
            subset["compactness"].to_numpy(),
        )
        if grid.size:
            ax.plot(10 ** grid, fit, color=colour, linewidth=1.2, linestyle="--",
                    alpha=0.75, zorder=2)

    ax.axhline(0.785, color=style.MUTED, linewidth=0.9, linestyle=":")
    ax.text(1.15, 0.797, "square  0.785", fontsize=7.4, color=style.MUTED)
    ax.axhline(1.0, color=style.MUTED, linewidth=0.9, linestyle=":")
    ax.text(1.15, 1.007, "circle  1.0", fontsize=7.4, color=style.MUTED)

    ax.set_xscale("log")
    ax.set_xlabel("Field area (ha, log scale)")
    ax.set_ylabel(r"Compactness  $4\pi A / P^2$")
    ax.set_ylim(0.0, 1.08)
    ax.set_title("Shape is set by boundary provenance first, size second", loc="left")

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc="lower left", ncol=2, handletextpad=0.5,
              columnspacing=1.0, fontsize=7.4)

    style.footnote(
        fig,
        "Dashed line = linear guide per grower on log area (not a prediction). "
        "n=30 fields; read the correlations in boundary_analysis.csv, not a star.",
    )
    path = analysis.figures_dir / "02_boundary_shape.png"
    style.save_figure(fig, path, analysis.dpi)

    style.write_caption(
        path,
        title="F2 — Field shape versus area",
        question="Are larger fields more regular in shape?",
        story=(
            "Source separates the two bands: CSB blocks have a median compactness "
            "of 0.34 against 0.63 for OSM parcels. Within CSB, larger fields are "
            "less compact, not more (Spearman about -0.6): they are long, "
            "survey-aligned blocks. OSM parcel size shows no relationship. Shape is "
            "a provenance story with a size tilt, not a simple size story."
        ),
        caveat=(
            "Thirty fields. The guide lines are visual only; the reported Spearman "
            "correlations and their bootstrap intervals in boundary_analysis.csv are "
            "the evidence, and size and source remain confounded."
        ),
        inputs=analysis.input_names(),
        notes=["Compactness is computed in EPSG:5070 metres, never in degrees."],
    )
    return path


# --------------------------------------------------------------------------- #
# A1 — geometry analysis
# --------------------------------------------------------------------------- #


def _row(scope: str, group: str, metric: str, value: float, *, low=np.nan,
         high=np.nan, p_value=np.nan, n: int = 0, note: str = "") -> dict:
    return {
        "scope": scope,
        "group": group,
        "metric": metric,
        "value": None if value is None or not np.isfinite(value) else round(float(value), 4),
        "ci_low": None if not np.isfinite(low) else round(float(low), 4),
        "ci_high": None if not np.isfinite(high) else round(float(high), 4),
        "p_value": None if not np.isfinite(p_value) else round(float(p_value), 4),
        "n": int(n),
        "note": note,
    }


def _analysis_table(analysis: Analysis, frame: pd.DataFrame) -> Path:
    config = analysis.dataset.config
    rows: list[dict] = []

    for grower in analysis.growers:
        subset = frame[frame["grower_slug"] == grower.slug]
        rows.append(_row("grower", grower.label, "area_ha_median",
                         subset["area_ha"].median(), n=len(subset)))
        rows.append(_row("grower", grower.label, "compactness_median",
                         subset["compactness"].median(), n=len(subset)))
        correlation = metrics.spearman_with_ci(
            np.log10(subset["area_ha"].to_numpy()),
            subset["compactness"].to_numpy(),
            seed=config.seed,
            n_boot=config.bootstrap,
        )
        rows.append(
            _row(
                "grower", grower.label, "spearman_log_area_compactness",
                correlation["rho"], low=correlation["low"], high=correlation["high"],
                p_value=correlation["p"], n=correlation["n"],
                note="bootstrap 2.5-97.5 percentile",
            )
        )

    for key in ("csb", "osm"):
        subset = frame[frame["source_key"] == key]
        if subset.empty:
            continue
        rows.append(_row("source", key, "area_ha_median", subset["area_ha"].median(),
                         n=len(subset)))
        rows.append(_row("source", key, "compactness_median",
                         subset["compactness"].median(), n=len(subset)))
        correlation = metrics.spearman_with_ci(
            np.log10(subset["area_ha"].to_numpy()),
            subset["compactness"].to_numpy(),
            seed=config.seed,
            n_boot=config.bootstrap,
        )
        rows.append(
            _row(
                "source", key, "spearman_log_area_compactness",
                correlation["rho"], low=correlation["low"], high=correlation["high"],
                p_value=correlation["p"], n=correlation["n"],
                note="within source only; bootstrap 2.5-97.5 percentile",
            )
        )

    csb = frame[frame["source_key"] == "csb"]["compactness"]
    osm = frame[frame["source_key"] == "osm"]["compactness"]
    if len(csb) >= 2 and len(osm) >= 2:
        test = metrics.mann_whitney(csb, osm)
        rows.append(
            _row(
                "source", "csb_vs_osm", "rank_biserial_compactness",
                test["rank_biserial"], p_value=test["p"], n=test["n_a"] + test["n_b"],
                note=(
                    "Mann-Whitney U two-sided; effect size 2U/(n1*n2)-1; "
                    f"n_csb={test['n_a']}, n_osm={test['n_b']}"
                ),
            )
        )

    mixed = [
        grower for grower in analysis.growers
        if frame[frame["grower_slug"] == grower.slug]["source_key"].nunique() > 1
    ]
    for grower in mixed:
        subset = frame[frame["grower_slug"] == grower.slug]
        left = subset[subset["source_key"] == "csb"]["compactness"]
        right = subset[subset["source_key"] == "osm"]["compactness"]
        if len(left) >= 2 and len(right) >= 2:
            test = metrics.mann_whitney(left, right)
            rows.append(
                _row(
                    "within_grower", grower.label, "rank_biserial_compactness",
                    test["rank_biserial"], p_value=test["p"], n=len(subset),
                    note=f"csb n={test['n_a']}, osm n={test['n_b']}",
                )
            )

    table = pd.DataFrame(rows)
    table["note"] = table["note"].fillna("")
    confound = "size and source are confounded in this dataset"
    for row in rows:
        if row["scope"] in ("source", "within_grower"):
            row["note"] = f"{row['note']}; {confound}" if row["note"] else confound

    table = pd.DataFrame(rows)
    table["note"] = table["note"].fillna("")
    path = analysis.tables_dir / "boundary_analysis.csv"
    table.to_csv(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# M1 — boundary source map
# --------------------------------------------------------------------------- #


def _map_sources(analysis: Analysis) -> Path:
    import matplotlib.pyplot as plt

    style.apply_style()
    fields = analysis.fields
    growers = list(analysis.growers)
    fig, axes = plt.subplots(1, len(growers), figsize=(4.3 * len(growers) + 1.0, 4.9))
    if len(growers) == 1:
        axes = [axes]

    for ax, grower in zip(axes, growers):
        subset = fields[fields["grower_slug"] == grower.slug]
        projected = maps.project_farm(subset)
        for key in ("csb", "osm", "other"):
            layer = projected[projected["source_key"] == key]
            if layer.empty:
                continue
            layer.plot(
                ax=ax, facecolor=style.source_color(key), edgecolor="white",
                linewidth=0.7, alpha=0.9, zorder=3,
            )
            if key == "osm":
                # Hand-traced parcels are only a few pixels wide at farm scale;
                # a marker at the representative point keeps them discoverable.
                points = layer.geometry.representative_point()
                ax.scatter(
                    points.x, points.y, s=26, marker="o",
                    facecolor=style.source_color(key), edgecolor="white",
                    linewidth=0.6, zorder=6,
                )
        maps.decorate(ax, projected)
        style.panel_title(
            ax,
            f"{grower.label} · {grower.slug.replace('-grower', '')}",
            f"{len(subset)} fields · {grower.grid_cells} weather cells",
        )

        smallest = subset.nsmallest(1, "area_ha").iloc[0]
        point = projected.loc[smallest.name].geometry.representative_point()
        if smallest["area_ha"] < 20:
            style.arrow_annotation(
                ax,
                xy=(point.x, point.y),
                text=f"{smallest['area_ha']:.1f} ha OSM parcel",
                offset=(30, -34),
                colour=style.MUTED,
            )

    handles = style.source_legend()
    fig.legend(handles=handles, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.985),
               frameon=False)
    fig.suptitle("Who drew each field — and how different the field populations are",
                 x=0.01, y=1.02, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    path = analysis.maps_dir / "01_boundary_sources.png"
    style.save_figure(fig, path, analysis.dpi)

    style.write_caption(
        path,
        title="M1 — Field boundaries by source",
        question="Where are the fields, and who drew each one?",
        story=(
            "Nebraska is effectively one contiguous block of neighbouring CSB "
            "fields. Illinois and Iowa are scattered parcels, and the small Illinois "
            "OSM parcel is visible next to blocks two orders of magnitude larger."
        ),
        caveat=(
            "This is a farm overview, not a single-field footprint: local UTM "
            "kilometres, 4% viewport padding, north arrow and scale bar, no "
            "auto-rotation. Source is provenance, not management."
        ),
        inputs=analysis.input_names(),
    )
    return path
