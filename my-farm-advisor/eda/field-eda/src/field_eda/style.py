"""Shared palettes, matplotlib defaults, captions, and map furniture.

Colours are fixed by meaning, never by plot order: a grower keeps its state
colour and a crop keeps its class colour in every figure, so the map and the bar
chart agree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch

# --------------------------------------------------------------------------- #
# Palettes
# --------------------------------------------------------------------------- #

#: Grower colour keyed by state code. Falls back to a stable hash-free order for
#: unknown states so the palette never depends on discovery order.
GROWER_COLORS = {
    "IL": "#1f6feb",
    "IA": "#2e8b57",
    "NE": "#d97706",
}
GROWER_FALLBACK = ("#7b3fa0", "#0f766e", "#b91c1c", "#4b5563")

CROP_COLORS = {
    "Corn": "#f2c230",
    "Soybeans": "#4f9d3a",
    "Winter Wheat": "#c98b3a",
    "Alfalfa": "#8e6cc9",
    "Grass/Pasture": "#a8c66c",
    "Fallow/Idle": "#c9b79c",
    "Forest": "#2f5d3a",
    "Open Water": "#3f7fbf",
    "Developed": "#9aa0a6",
    "Wetlands": "#5f9ea0",
    "Other": "#b0b7bf",
}

SOURCE_COLORS = {
    "csb": "#2b6cb0",
    "osm": "#dd6b20",
    "other": "#6b7280",
}
SOURCE_LABELS = {
    "csb": "USDA CSB field",
    "osm": "OpenStreetMap parcel",
    "other": "Other source",
}

INK = "#1f2933"
MUTED = "#6b7280"
GRID = "#d9dee5"


def grower_color(state: str, index: int = 0) -> str:
    return GROWER_COLORS.get(state.upper(), GROWER_FALLBACK[index % len(GROWER_FALLBACK)])


def crop_color(name: str) -> str:
    return CROP_COLORS.get(name, CROP_COLORS["Other"])


def source_color(key: str) -> str:
    return SOURCE_COLORS.get(key, SOURCE_COLORS["other"])


def ordered_crops(names: Iterable[str]) -> list[str]:
    """Crops in a stable legend order: known classes first, then alphabetical."""
    known = [name for name in CROP_COLORS if name in set(names)]
    extra = sorted(set(names) - set(known))
    return known + extra


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 110,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#c7cdd6",
            "axes.labelcolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "grid.alpha": 0.9,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "font.size": 9,
            "font.family": "DejaVu Sans",
            "text.color": INK,
        }
    )


# --------------------------------------------------------------------------- #
# Captions and manifest
# --------------------------------------------------------------------------- #


def write_caption(
    png_path: Path,
    *,
    title: str,
    question: str,
    story: str,
    caveat: str,
    inputs: Sequence[str],
    notes: Sequence[str] = (),
) -> Path:
    """Write the ``*.caption.md`` sidecar that a later report consumes."""

    lines = [
        f"# {title}",
        "",
        f"**Question:** {question}",
        "",
        f"**What this shows:** {story}",
        "",
        f"**Caveat:** {caveat}",
    ]
    if notes:
        lines += ["", "**Reading notes:**"]
        lines += [f"- {note}" for note in notes]
    lines += ["", "**Inputs:**"]
    lines += [f"- `{name}`" for name in inputs]
    lines.append("")
    path = png_path.with_suffix(".caption.md")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def save_figure(fig: plt.Figure, path: Path, dpi: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# Legends
# --------------------------------------------------------------------------- #


def grower_handles(growers: Sequence[object], index: dict[str, int]) -> list[Line2D]:
    handles = []
    for grower in growers:
        label = getattr(grower, "label", str(grower))
        key = getattr(grower, "slug", label)
        handles.append(
            Line2D(
                [], [], marker="o", linestyle="none", markersize=7,
                markerfacecolor=grower_color(label, index.get(key, 0)),
                markeredgecolor="white", markeredgewidth=0.8,
                label=f"{label} · {key}",
            )
        )
    return handles


def crop_legend(names: Sequence[str], **kwargs) -> list[Patch]:
    return [Patch(facecolor=crop_color(name), edgecolor="white", label=name) for name in names]


def source_legend() -> list[Patch]:
    return [
        Patch(facecolor=source_color(key), edgecolor="white", label=SOURCE_LABELS[key])
        for key in ("csb", "osm")
    ]


# --------------------------------------------------------------------------- #
# Map furniture
# --------------------------------------------------------------------------- #


def draw_north_arrow(ax, x: float = 0.94, y: float = 0.93, size: float = 0.055) -> None:
    """Boxed north arrow in axes coordinates, matching the frame contract."""
    ax.annotate(
        "",
        xy=(x, y + size),
        xytext=(x, y - size),
        xycoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color=INK, linewidth=1.4),
        zorder=20,
    )
    ax.text(
        x, y + size + 0.025, "N", transform=ax.transAxes,
        ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK,
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white",
                  edgecolor="#c7cdd6", linewidth=0.7),
        zorder=21,
    )


def draw_scale_bar(
    ax,
    x_km: float,
    y_km: float,
    length_km: float,
    *,
    colour: str = INK,
) -> None:
    """Alternating scale bar in data coordinates (kilometres)."""
    n = 4
    step = length_km / n
    for i in range(n):
        ax.add_patch(
            plt.Rectangle(
                (x_km + i * step, y_km), step, max(length_km * 0.035, 0.04),
                facecolor=colour if i % 2 == 0 else "white",
                edgecolor=colour, linewidth=0.7, zorder=20,
            )
        )
    ax.text(
        x_km + length_km * 0.5, y_km + length_km * 0.075,
        f"{length_km:g} km", ha="center", va="bottom", fontsize=8, color=colour,
        zorder=20,
    )


def nice_scale_km(span_km: float) -> float:
    for candidate in (1, 2, 5, 10, 20, 25, 50, 100):
        if candidate >= span_km * 0.18:
            return float(candidate)
    return 100.0


def panel_title(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", pad=20)
    if subtitle:
        ax.text(
            0.0, 1.006, subtitle, transform=ax.transAxes,
            ha="left", va="bottom", fontsize=7.8, color=MUTED,
        )


def footnote(fig: plt.Figure, text: str) -> None:
    fig.text(0.01, -0.035, text, ha="left", va="top", fontsize=7.2, color=MUTED)


def arrow_annotation(ax, xy, text: str, *, offset=(28, -30),
                     colour: str = INK) -> None:
    ax.annotate(
        text, xy=xy, xytext=offset, textcoords="offset points", fontsize=7.6,
        color=colour,
        arrowprops=dict(arrowstyle="-", color=colour, linewidth=0.8,
                        shrinkA=2, shrinkB=3),
        bbox=dict(boxstyle="round,pad=0.22", facecolor="white",
                  edgecolor="#d9dee5", linewidth=0.6, alpha=0.95),
        zorder=30,
    )


__all__ = [
    "GROWER_COLORS",
    "CROP_COLORS",
    "SOURCE_COLORS",
    "SOURCE_LABELS",
    "INK",
    "MUTED",
    "apply_style",
    "arrow_annotation",
    "crop_color",
    "crop_legend",
    "draw_north_arrow",
    "draw_scale_bar",
    "footnote",
    "grower_color",
    "grower_handles",
    "nice_scale_km",
    "ordered_crops",
    "panel_title",
    "save_figure",
    "source_color",
    "source_legend",
    "write_caption",
    "write_json",
]
