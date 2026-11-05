#!/usr/bin/env python3
# Copyright 2026 Clayton Young (borealBytes / Superior Byte Works, LLC)
# Licensed under the Apache License, Version 2.0.

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def main():
    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)

    trials = pd.DataFrame(
        {
            "trial_id": ["BMS-T01", "BMS-T02"],
            "location": ["Site-A", "Site-B"],
            "season": ["2026A", "2026A"],
            "status": ["retrieved_mock", "retrieved_mock"],
        }
    )
    trials.to_csv(out / "bms_trials_read.csv", index=False)

    update = pd.DataFrame(
        {
            "trial_id": ["BMS-T03"],
            "operation": ["create_mock"],
            "result": ["success"],
        }
    )
    update.to_csv(out / "bms_trials_write_result.csv", index=False)

    sites = pd.DataFrame(
        {
            "trial_id": ["BMS-T01", "BMS-T02", "BMS-T03"],
            "lon": [-97.1, -96.4, -95.7],
            "lat": [40.6, 40.8, 41.2],
            "status": ["retrieved", "retrieved", "created"],
        }
    )
    sites.to_csv(out / "bms_trial_sites.csv", index=False)

    colors = np.where(sites["status"] == "created", "#ff7f0e", "#2ca02c")
    fig, ax = plt.subplots(figsize=(6.8, 4.8))
    # Real satellite basemap instead of decorative gridlines + a text label
    # claiming "Regional context": plot in Web Mercator and tile underneath.
    import contextily as ctx
    import geopandas as gpd

    g = gpd.GeoDataFrame(
        sites, geometry=gpd.points_from_xy(sites["lon"], sites["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    x, y = g.geometry.x, g.geometry.y
    ax.scatter(x, y, c=colors, s=130, zorder=3, edgecolors="white", linewidths=0.8)
    for _, r in g.iterrows():
        ax.annotate(
            str(r["trial_id"]),
            (r.geometry.x, r.geometry.y),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
            color="white",
            zorder=4,
            bbox=dict(boxstyle="round,pad=0.18", fc="#1f2937", ec="none", alpha=0.72),
        )
    # Set the view extent BEFORE fetching tiles, otherwise contextily only
    # tiles the old extent and a white strip appears along the edges.
    ax.set_xlim(x.min() - 25000, x.max() + 25000)
    ax.set_ylim(y.min() - 22000, y.max() + 22000)
    ctx.add_basemap(
        ax,
        source=ctx.providers.Esri.WorldImagery,
        crs="EPSG:3857",
    )
    # Geopolitical reference: L0/L1/L2 boundaries and L2 county names from
    # the cached GeoAdmin layers (the data-pipeline lib), so a viewer knows
    # where these sites are without reading coordinates.
    try:
        _lib = Path(__file__).resolve().parents[2].parent / "my-farm-advisor" / \
            "data-pipeline" / "src" / "scripts" / "lib"
        import sys

        if _lib.is_dir() and str(_lib) not in sys.path:
            sys.path.insert(0, str(_lib))
        from geoadmin_context import add_admin_context

        add_admin_context(ax, g, crs="EPSG:3857")
    except Exception as exc:  # noqa: BLE001 — context is additive
        print(f"(admin context skipped: {exc})")
    ax.set_title("BMS Trial Footprint")
    ax.set_xlabel("Web Mercator X (m)")
    ax.set_ylabel("Web Mercator Y (m)")
    ax.grid(alpha=0.18)
    fig.tight_layout()
    fig.savefig(out / "bms_trial_site_map.png", dpi=150)
    plt.close(fig)

    conclusion = (
        "BMS client conclusion\n"
        "=====================\n"
        "Mock BMS trial transactions are paired with site footprints for operational review.\n"
        "This format supports quick checks by breeders, agronomists, and data managers.\n"
    )
    (out / "conclusion.txt").write_text(conclusion, encoding="utf-8")
    print("Saved BMS mock read/write outputs, site map, and conclusion")


if __name__ == "__main__":
    main()
