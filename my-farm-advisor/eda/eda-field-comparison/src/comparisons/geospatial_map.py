"""Geospatial maps: field boundaries with optional continental US inset."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def _load_boundary_features(boundary_path: Path) -> list[dict]:
    with open(boundary_path) as f:
        geojson = json.load(f)
    return geojson.get("features", [])


def _plot_polygon(ax, coords: list, color: str, alpha: float = 0.5) -> None:
    """Plot a single polygon on the given axes."""
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    ax.fill(lons, lats, color=color, alpha=alpha, edgecolor=color, linewidth=2)


def _load_us_states(data_root: Path) -> list[dict]:
    """Load US states geojson for inset map."""
    states_path = data_root / "data-pipeline/shared/geoadmin/l1_states/states_usa.geojson"
    if not states_path.exists():
        return []
    with open(states_path) as f:
        geojson = json.load(f)
    return geojson.get("features", [])


def geospatial_maps(growers: dict, output_dir: Path) -> None:
    """Generate 10A (fields only) and 10B (with inset) geospatial maps."""
    print("\n" + "=" * 60)
    print("Geospatial Maps")
    print("=" * 60)

    colors = {"Illinois": "#1E90FF", "Iowa": "#9ACD32", "Nebraska": "#FFB90F"}
    states_order = ["Illinois", "Iowa", "Nebraska"]
    
    # Collect all field polygons with state colors
    all_features = []
    all_lons = []
    all_lats = []
    
    for grower_slug, info in growers.items():
        state = info["state"]
        boundary_path = Path(info["boundary"])
        features = _load_boundary_features(boundary_path)
        for feat in features:
            coords = feat.get("geometry", {}).get("coordinates", [[]])[0]
            all_features.append({"coords": coords, "state": state})
            all_lons.extend([c[0] for c in coords])
            all_lats.extend([c[1] for c in coords])
    
    if not all_features:
        print("  No boundary data for maps.")
        return

    # Calculate bounding box with padding
    lon_min, lon_max = min(all_lons), max(all_lons)
    lat_min, lat_max = min(all_lats), max(all_lats)
    lon_pad = (lon_max - lon_min) * 0.1
    lat_pad = (lat_max - lat_min) * 0.1

    # 10A: Fields only
    fig, ax = plt.subplots(figsize=(10, 8))
    for feat in all_features:
        _plot_polygon(ax, feat["coords"], colors[feat["state"]], alpha=0.3)
    
    ax.set_xlim(lon_min - lon_pad, lon_max + lon_pad)
    ax.set_ylim(lat_min - lat_pad, lat_max + lat_pad)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)
    ax.set_title("Field Boundaries by State", fontsize=14, fontweight="bold")
    
    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=colors[s], edgecolor=colors[s], label=s, alpha=0.5) for s in states_order]
    ax.legend(handles=legend_elements, loc="upper left", title="State", fontsize=10)
    
    plt.tight_layout()
    out1 = output_dir / "10A_geospatial_fields_only.png"
    plt.savefig(out1, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out1.name}")

    # 10B: Fields with continental US inset
    fig, ax_main = plt.subplots(figsize=(10, 8))
    for feat in all_features:
        _plot_polygon(ax_main, feat["coords"], colors[feat["state"]], alpha=0.3)
    
    ax_main.set_xlim(lon_min - lon_pad, lon_max + lon_pad)
    ax_main.set_ylim(lat_min - lat_pad, lat_max + lat_pad)
    ax_main.set_aspect("equal")
    ax_main.set_xlabel("Longitude", fontsize=12)
    ax_main.set_ylabel("Latitude", fontsize=12)
    ax_main.set_title("Field Boundaries by State", fontsize=14, fontweight="bold")
    
    # Legend
    ax_main.legend(handles=legend_elements, loc="upper left", title="State", fontsize=10)
    
    # Inset: continental US with highlighted states
    us_states = _load_us_states(Path(growers[list(growers.keys())[0]]["data_root"]))
    if us_states:
        ax_inset = fig.add_axes([0.62, 0.12, 0.30, 0.30])
        state_names = {s.lower(): colors[s] for s in states_order}
        
        for state_feat in us_states:
            props = state_feat.get("properties", {})
            name = props.get("name", "").lower()
            geom = state_feat.get("geometry", {})
            geom_type = geom.get("type", "")
            
            color = state_names.get(name, "lightgray")
            
            if geom_type == "Polygon":
                coords = geom.get("coordinates", [[]])[0]
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
                ax_inset.fill(lons, lats, color=color, alpha=0.8, edgecolor="black", linewidth=0.8)
            elif geom_type == "MultiPolygon":
                for poly in geom.get("coordinates", []):
                    coords = poly[0]
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    ax_inset.fill(lons, lats, color=color, alpha=0.8, edgecolor="black", linewidth=0.8)
        
        ax_inset.set_xlim(-125, -66)
        ax_inset.set_ylim(24, 50)
        ax_inset.set_aspect("equal")
        ax_inset.set_xticks([])
        ax_inset.set_yticks([])
        ax_inset.set_title("US Context", fontsize=9, fontweight="bold")
        # Add border around inset
        for spine in ax_inset.spines.values():
            spine.set_edgecolor("black")
            spine.set_linewidth(1.5)
    
    plt.tight_layout()
    out2 = output_dir / "10B_geospatial_with_inset.png"
    plt.savefig(out2, dpi=300, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"  Saved: {out2.name}")
