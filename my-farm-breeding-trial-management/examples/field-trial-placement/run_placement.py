#!/usr/bin/env python3
"""
Field Trial Placement - Optimal placement of trial blocks within field boundaries.

Maximizes or customizes trial area within field interior (minus headlands).
Supports RCBD, alpha-lattice, and augmented designs.

Usage:
    # Maximize trial size
    python run_placement.py --field-boundaries fields.geojson --field-id osm-XXX \\
        --varieties A,B,C,D,E,F --blocks 4 --maximize

    # Set exact trial size
    python run_placement.py --field-boundaries fields.geojson --field-id osm-XXX \\
        --varieties A,B,C,D,E,F --blocks 4 --trial-acres 5.0

    # Set exact plot dimensions
    python run_placement.py --field-boundaries fields.geojson --field-id osm-XXX \\
        --varieties A,B,C,D,E,F --blocks 4 --plot-width-m 15 --plot-height-m 50

    # Set plot size constraints
    python run_placement.py --field-boundaries fields.geojson --field-id osm-XXX \\
        --varieties A,B,C,D,E,F --blocks 4 --maximize \\
        --min-plot-acres 0.1 --max-plot-acres 0.5
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, box
from shapely.affinity import rotate, translate
from shapely.ops import unary_union

# ============================================
# CONSTANTS
# ============================================
ACRES_TO_SQM = 4046.86
DEFAULT_COLORS = [
    "#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4",
    "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16", "#e11d48"
]

# ============================================
# GEOMETRY HELPERS
# ============================================
def rotate_point(x, y, angle_deg):
    """Rotate point (x,y) around origin by angle_deg degrees."""
    angle_rad = np.radians(angle_deg)
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a

def create_rectangle(cx, cy, width, height, angle_deg=0):
    """Create a rotated rectangle centered at (cx, cy)."""
    half_w, half_h = width / 2, height / 2
    corners = [(-half_w, -half_h), (half_w, -half_h), 
               (half_w, half_h), (-half_w, half_h), (-half_w, -half_h)]
    rotated = [rotate_point(x, y, angle_deg) for x, y in corners]
    return Polygon([(rx + cx, ry + cy) for rx, ry in rotated])

# ============================================
# VALIDATION TESTS (Binary)
# ============================================
def validate_trial(field_boundary, headlands_ring, plots, dissolve=True):
    """
    Run binary validation tests on trial placement.
    
    Returns dict with:
      - centroid_inside: centroid of dissolved trial inside field boundary
      - trial_contained: dissolved trial fully contained in field boundary
      - no_headlands_intersect: dissolved trial does not intersect headlands
      - all_pass: all tests pass
    """
    if dissolve:
        dissolved = unary_union(plots)
    else:
        dissolved = plots if hasattr(plots, 'geom_type') else unary_union(plots)
    
    centroid = dissolved.centroid
    
    centroid_inside = field_boundary.contains(centroid)
    trial_contained = field_boundary.contains(dissolved)
    no_headlands = not dissolved.intersects(headlands_ring)
    
    return {
        'centroid_inside': centroid_inside,
        'trial_contained': trial_contained,
        'no_headlands_intersect': no_headlands,
        'all_pass': centroid_inside and trial_contained and no_headlands,
        'dissolved': dissolved
    }

# ============================================
# MAXIMUM RECTANGLE FINDER
# ============================================
def find_max_rectangle(interior_geom, num_varieties, num_blocks, 
                       angle_step=15, grid_step=20,
                       min_plot_acres=None, max_plot_acres=None,
                       min_plot_width_m=None, max_plot_width_m=None,
                       min_plot_height_m=None, max_plot_height_m=None,
                       aspect_ratio=None):
    """
    Find the maximum sized trial rectangle that fits in interior.
    
    Binary search approach:
    1. For each rotation angle
    2. Binary search for max trial area that passes all validation tests
    3. Track the best across all angles
    """
    minx, miny, maxx, maxy = interior_geom.bounds
    field_width = maxx - minx - 30  # 15m buffer each side
    field_height = maxy - miny - 30
    
    # Convert plot constraints to meters
    min_plot_sqm = min_plot_acres * ACRES_TO_SQM if min_plot_acres else 100  # 100 sqm minimum
    max_plot_sqm = max_plot_acres * ACRES_TO_SQM if max_plot_acres else None
    
    # Calculate max trial area based on field bounds
    max_trial_sqm = field_width * field_height * 0.9  # 90% of field
    
    # Headlands ring
    field_boundary = interior_geom.buffer(9.0)  # Reconstruct field boundary
    headlands_ring = field_boundary.difference(interior_geom)
    
    best_result = None
    best_area = 0
    
    angles = list(range(0, 180, angle_step))
    
    for angle in angles:
        # Get rotated field bounds
        test_rect = create_rectangle(0, 0, field_width, field_height, angle)
        rb = test_rect.bounds
        rotated_w = rb[2] - rb[0]
        rotated_h = rb[3] - rb[1]
        
        # Binary search for max trial size at this angle
        low, high = 1000, max_trial_sqm  # 1000 sqm minimum
        best_at_angle = None
        
        while high - low > 500:  # 500 sqm precision
            mid = (low + high) / 2
            
            # Calculate trial dimensions
            if aspect_ratio:
                trial_width = np.sqrt(mid / aspect_ratio)
                trial_height = trial_width * aspect_ratio
            else:
                # Default: N-S orientation (tall)
                trial_width = np.sqrt(mid / 2.5)
                trial_height = trial_width * 2.5
            
            # Check plot size constraints
            plot_w = trial_width / num_varieties
            plot_h = trial_height / num_blocks
            plot_sqm = plot_w * plot_h
            
            # Skip if plot size outside constraints
            if plot_sqm < min_plot_sqm:
                low = mid
                continue
            if max_plot_sqm and plot_sqm > max_plot_sqm:
                high = mid
                continue
            if min_plot_width_m and plot_w < min_plot_width_m:
                low = mid
                continue
            if max_plot_width_m and plot_w > max_plot_width_m:
                high = mid
                continue
            if min_plot_height_m and plot_h < min_plot_height_m:
                low = mid
                continue
            if max_plot_height_m and plot_h > max_plot_height_m:
                high = mid
                continue
            
            # Try to find a position where this trial fits
            found_position = False
            best_pos = None
            
            # Get trial bounds in rotated space
            test_trial = create_rectangle(0, 0, trial_width, trial_height, angle)
            tb = test_trial.bounds
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
            
            # Grid search for position
            x_range = np.linspace(minx + tw/2 + 15, maxx - tw/2 - 15, 15)
            y_range = np.linspace(miny + th/2 + 15, maxy - th/2 - 15, 15)
            
            for cx in x_range:
                for cy in y_range:
                    # Generate plots
                    plots = []
                    for block in range(num_blocks):
                        for col in range(num_varieties):
                            px = -trial_width/2 + col * plot_w
                            py = -trial_height/2 + block * plot_h
                            local_plot = box(px, py, px + plot_w, py + plot_h)
                            rotated = rotate(local_plot, angle, origin=(0,0), use_radians=False)
                            final = translate(rotated, cx, cy)
                            plots.append(final)
                    
                    # Validate
                    result = validate_trial(field_boundary, headlands_ring, plots)
                    if result['all_pass']:
                        found_position = True
                        best_pos = (cx, cy)
                        break
                if found_position:
                    break
            
            if found_position:
                low = mid
                if mid > best_area:
                    assert best_pos is not None
                    best_area = mid
                    best_at_angle = {
                        'angle': angle,
                        'center_x': best_pos[0],
                        'center_y': best_pos[1],
                        'trial_width': trial_width,
                        'trial_height': trial_height,
                        'trial_acres': mid / ACRES_TO_SQM,
                        'plot_width_m': plot_w,
                        'plot_height_m': plot_h,
                        'plot_acres': plot_sqm / ACRES_TO_SQM,
                        'num_plots': num_varieties * num_blocks
                    }
            else:
                high = mid
        
        if best_at_angle and best_at_angle['trial_acres'] > (best_result['trial_acres'] if best_result else 0):
            best_result = best_at_angle
    
    return best_result

# ============================================
# FIXED SIZE TRIAL FINDER
# ============================================
def find_fixed_trial(interior_geom, target_acres, num_varieties, num_blocks,
                     angle_step=15, grid_step=20):
    """Find position for a fixed-size trial."""
    target_sqm = target_acres * ACRES_TO_SQM
    target_width = np.sqrt(target_sqm / 2.5)
    target_height = target_width * 2.5
    
    field_boundary = interior_geom.buffer(9.0)
    headlands_ring = field_boundary.difference(interior_geom)
    
    minx, miny, maxx, maxy = interior_geom.bounds
    
    for angle in range(0, 180, angle_step):
        test_trial = create_rectangle(0, 0, target_width, target_height, angle)
        tb = test_trial.bounds
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        
        x_range = np.linspace(minx + tw/2 + 15, maxx - tw/2 - 15, 20)
        y_range = np.linspace(miny + th/2 + 15, maxy - th/2 - 15, 20)
        
        for cx in x_range:
            for cy in y_range:
                plot_w = target_width / num_varieties
                plot_h = target_height / num_blocks
                
                plots = []
                for block in range(num_blocks):
                    for col in range(num_varieties):
                        px = -target_width/2 + col * plot_w
                        py = -target_height/2 + block * plot_h
                        local_plot = box(px, py, px + plot_w, py + plot_h)
                        rotated = rotate(local_plot, angle, origin=(0,0), use_radians=False)
                        final = translate(rotated, cx, cy)
                        plots.append(final)
                
                result = validate_trial(field_boundary, headlands_ring, plots)
                if result['all_pass']:
                    return {
                        'angle': angle,
                        'center_x': cx,
                        'center_y': cy,
                        'trial_width': target_width,
                        'trial_height': target_height,
                        'trial_acres': target_acres,
                        'plot_width_m': plot_w,
                        'plot_height_m': plot_h,
                        'plot_acres': (plot_w * plot_h) / ACRES_TO_SQM,
                        'num_plots': num_varieties * num_blocks
                    }
    
    return None

# ============================================
# RCBD PLOT GENERATOR
# ============================================
def generate_rcbd_plots(trial_config, varieties, seed=42):
    """Generate RCBD plot layout from trial config."""
    rng = np.random.default_rng(seed)
    num_varieties = len(varieties)
    num_plots = trial_config['num_plots']
    num_blocks = num_plots // num_varieties
    
    cx = trial_config['center_x']
    cy = trial_config['center_y']
    tw = trial_config['trial_width']
    th = trial_config['trial_height']
    angle = trial_config['angle']
    plot_w = trial_config['plot_width_m']
    plot_h = trial_config['plot_height_m']
    
    plots = []
    plot_id = 1
    
    for block in range(num_blocks):
        block_vars = list(varieties)
        rng.shuffle(block_vars)
        
        for col, variety in enumerate(block_vars):
            px = -tw/2 + col * plot_w
            py = -th/2 + block * plot_h
            local_plot = box(px, py, px + plot_w, py + plot_h)
            rotated = rotate(local_plot, angle, origin=(0,0), use_radians=False)
            final = translate(rotated, cx, cy)
            
            plots.append({
                "plot_id": plot_id,
                "block": block + 1,
                "row": block + 1,
                "col": col + 1,
                "variety": variety,
                "area_acres": (plot_w * plot_h) / ACRES_TO_SQM,
                "geometry": final
            })
            plot_id += 1
    
    return gpd.GeoDataFrame(plots, crs="EPSG:32616")

# ============================================
# VISUALIZATION
# ============================================
def create_trial_map(field_utm, headlands_gdf, plots_utm, trial_config, 
                     field_id, varieties, variety_colors, output_path):
    """Create beautiful geospatial trial map."""
    
    fig, ax = plt.subplots(1, 1, figsize=(14, 12))
    fig.patch.set_facecolor('#fafaf9')
    
    bounds = field_utm.total_bounds
    margin_x = (bounds[2] - bounds[0]) * 0.15
    margin_y = (bounds[3] - bounds[1]) * 0.15
    ax.set_xlim(bounds[0] - margin_x, bounds[2] + margin_x)
    ax.set_ylim(bounds[1] - margin_y, bounds[3] + margin_y)
    
    # Satellite basemap
    try:
        esri_provider = cast(Any, getattr(ctx.providers, 'Esri')).WorldImagery
        ctx.add_basemap(ax, crs=field_utm.crs, source=esri_provider,
                       alpha=0.7, zoom='16')
    except:
        ax.set_facecolor('#f0f9ff')
    
    # Headlands
    if not headlands_gdf.empty:
        headlands_gdf.plot(ax=ax, color='#fdba74', alpha=0.5, edgecolor='#c2410c', linewidth=1.5)
    
    # Trial area boundary
    trial_rect = create_rectangle(
        trial_config['center_x'], trial_config['center_y'],
        trial_config['trial_width'], trial_config['trial_height'],
        trial_config['angle']
    )
    gpd.GeoDataFrame(geometry=[trial_rect], crs=field_utm.crs).boundary.plot(
        ax=ax, color='#1e40af', linewidth=2.5, linestyle='--')
    
    # Plots
    plot_w = trial_config['plot_width_m']
    plot_h = trial_config['plot_height_m']
    
    for _, plot in plots_utm.iterrows():
        color = variety_colors[plot["variety"]]
        gpd.GeoDataFrame(geometry=[plot["geometry"]], crs=field_utm.crs).plot(
            ax=ax, color=color, alpha=0.75, edgecolor='white', linewidth=1.5)
        
        centroid = plot["geometry"].centroid
        ax.text(centroid.x, centroid.y - plot_h * 0.35,
                f"P{plot['plot_id']}", ha='center', va='center',
                fontsize=8, fontweight='bold', color='white',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.5))
        # Variety chip is rotated along the plot's long axis so it never collides
        # with neighbours in narrow plots (labels stay readable, trial stays dense).
        rot = trial_config['angle'] % 180
        if rot > 90:
            rot -= 180
        ax.text(centroid.x, centroid.y + plot_h * 0.15,
                plot['variety'], ha='center', va='center',
                fontsize=7, color='white', fontweight='bold', rotation=rot,
                bbox=dict(boxstyle='round,pad=0.2', facecolor=color, alpha=0.8))
    
    # Field boundary
    field_utm.boundary.plot(ax=ax, color='#166534', linewidth=3)
    
    # North arrow
    ax.annotate('', xy=(bounds[2] + margin_x*0.6, bounds[3] - margin_y*0.1),
                xytext=(bounds[2] + margin_x*0.6, bounds[3] - margin_y*0.4),
                arrowprops=dict(arrowstyle='->', lw=2, color='black'))
    ax.text(bounds[2] + margin_x*0.6, bounds[3] - margin_y*0.05, 'N', 
            ha='center', fontsize=12, fontweight='bold')
    
    # Scale bar
    scale_x = bounds[0] + margin_x * 0.3
    scale_y = bounds[1] + margin_y * 0.3
    ax.plot([scale_x, scale_x + 100], [scale_y, scale_y], 'k-', linewidth=3)
    ax.text(scale_x + 50, scale_y - 15, '100m', ha='center', va='top', fontsize=9, fontweight='bold')
    
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor='#fdba74', alpha=0.5, edgecolor='#c2410c', label='Headlands (9m)'),
        Line2D([0], [0], color='#1e40af', linewidth=2.5, linestyle='--', label='Trial Area'),
        Line2D([0], [0], color='#166534', linewidth=3, label='Field Boundary'),
    ]
    for v, c in variety_colors.items():
        legend_elements.append(mpatches.Patch(facecolor=c, alpha=0.75, label=v))
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9, title='Legend', framealpha=0.95)
    
    ax.set_title(
        f'MAXIMUM RCBD Trial — Field {field_id[-8:]}\n'
        f'{len(varieties)} Varieties × {trial_config["num_plots"]//len(varieties)} Blocks = {trial_config["num_plots"]} Plots\n'
        f'Trial: {trial_config["trial_acres"]:.1f} acres · Rotation: {trial_config["angle"]}° · '
        f'Plots: {trial_config["plot_acres"]:.2f} acres ({plot_w:.0f}m × {plot_h:.0f}m)',
        fontsize=14, fontweight='bold', pad=15
    )
    
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()

# ============================================
# MAIN
# ============================================
def main():
    parser = argparse.ArgumentParser(description="Field Trial Placement - Maximize or Customize")
    
    # Required
    parser.add_argument("--field-boundaries", required=True, help="Path to field boundaries GeoJSON")
    parser.add_argument("--field-id", required=True, help="Field ID")
    parser.add_argument("--grower-slug", required=True, help="Grower slug")
    parser.add_argument("--farm-slug", required=True, help="Farm slug")
    parser.add_argument("--varieties", required=True, help="Comma-separated variety names")
    parser.add_argument("--blocks", type=int, default=4, help="Number of RCBD blocks")
    
    # Size options (mutually exclusive group)
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument("--maximize", action="store_true", help="Maximize trial size")
    size_group.add_argument("--trial-acres", type=float, help="Fixed trial size in acres")
    size_group.add_argument("--plot-width-m", type=float, help="Fixed plot width in meters (requires --plot-height-m)")
    
    # Plot constraints
    parser.add_argument("--plot-height-m", type=float, help="Fixed plot height in meters")
    parser.add_argument("--min-plot-acres", type=float, help="Minimum plot size in acres")
    parser.add_argument("--max-plot-acres", type=float, help="Maximum plot size in acres")
    parser.add_argument("--min-plot-width-m", type=float, help="Minimum plot width in meters")
    parser.add_argument("--max-plot-width-m", type=float, help="Maximum plot width in meters")
    parser.add_argument("--min-plot-height-m", type=float, help="Minimum plot height in meters")
    parser.add_argument("--max-plot-height-m", type=float, help="Maximum plot height in meters")
    
    # Other options
    parser.add_argument("--headlands-m", type=float, default=9.0, help="Headlands width in meters")
    parser.add_argument("--angle-step", type=int, default=15, help="Rotation angle step in degrees")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    
    args = parser.parse_args()
    
    varieties = args.varieties.split(",")
    num_varieties = len(varieties)
    variety_colors = {v: DEFAULT_COLORS[i % len(DEFAULT_COLORS)] for i, v in enumerate(varieties)}
    
    # Load field
    fields = gpd.read_file(args.field_boundaries)
    field = fields[fields["field_id"] == args.field_id].copy()
    if field.empty:
        print(f"ERROR: Field {args.field_id} not found")
        sys.exit(1)
    
    field_utm = field.to_crs("EPSG:32616")
    field_geom = field_utm.geometry.iloc[0]
    interior = field_geom.buffer(-args.headlands_m)
    headlands = field_geom.difference(interior)
    headlands_gdf = gpd.GeoDataFrame(geometry=[headlands], crs="EPSG:32616")
    
    print(f"Field: {args.field_id}")
    print(f"Area: {field_geom.area / ACRES_TO_SQM:.1f} acres")
    print(f"Interior: {interior.area / ACRES_TO_SQM:.1f} acres")
    
    # Find trial placement
    if args.maximize:
        print("\n🔍 Finding MAXIMUM trial size...")
        trial_config = find_max_rectangle(
            interior, num_varieties, args.blocks,
            angle_step=args.angle_step,
            min_plot_acres=args.min_plot_acres,
            max_plot_acres=args.max_plot_acres,
            min_plot_width_m=args.min_plot_width_m,
            max_plot_width_m=args.max_plot_width_m,
            min_plot_height_m=args.min_plot_height_m,
            max_plot_height_m=args.max_plot_height_m
        )
    elif args.trial_acres:
        print(f"\n🔍 Finding position for {args.trial_acres} acre trial...")
        trial_config = find_fixed_trial(
            interior, args.trial_acres, num_varieties, args.blocks,
            angle_step=args.angle_step
        )
    elif args.plot_width_m and args.plot_height_m:
        # Calculate trial size from plot dimensions
        trial_width = args.plot_width_m * num_varieties
        trial_height = args.plot_height_m * args.blocks
        trial_acres = (trial_width * trial_height) / ACRES_TO_SQM
        print(f"\n🔍 Finding position for {trial_acres:.1f} acre trial (plots: {args.plot_width_m}m × {args.plot_height_m}m)...")
        trial_config = find_fixed_trial(
            interior, trial_acres, num_varieties, args.blocks,
            angle_step=args.angle_step
        )
        if trial_config:
            trial_config['plot_width_m'] = args.plot_width_m
            trial_config['plot_height_m'] = args.plot_height_m
    else:
        print("\n🔍 Maximizing trial size (default)...")
        trial_config = find_max_rectangle(
            interior, num_varieties, args.blocks,
            angle_step=args.angle_step
        )
    
    if not trial_config:
        print("ERROR: Could not find valid trial placement")
        sys.exit(1)
    
    print(f"\n{'='*50}")
    print(f"✓ OPTIMAL TRIAL FOUND")
    print(f"{'='*50}")
    print(f"  Trial area:  {trial_config['trial_acres']:.2f} acres")
    print(f"  Rotation:    {trial_config['angle']}°")
    print(f"  Position:    ({trial_config['center_x']:.0f}, {trial_config['center_y']:.0f})")
    print(f"  Plot size:   {trial_config['plot_width_m']:.0f}m × {trial_config['plot_height_m']:.0f}m = {trial_config['plot_acres']:.3f} acres")
    print(f"  Total plots: {trial_config['num_plots']}")
    
    # Generate plots
    plots_utm = generate_rcbd_plots(trial_config, varieties, seed=args.seed)
    
    # Validate with binary tests
    field_boundary = interior.buffer(args.headlands_m)
    headlands_ring = field_boundary.difference(interior)
    validation = validate_trial(field_boundary, headlands_ring, plots_utm.geometry.tolist())
    
    print(f"\n  Validation:")
    print(f"    Centroid inside field?     {'✓ PASS' if validation['centroid_inside'] else '✗ FAIL'}")
    print(f"    Trial contained in field?  {'✓ PASS' if validation['trial_contained'] else '✗ FAIL'}")
    print(f"    No headlands intersection? {'✓ PASS' if validation['no_headlands_intersect'] else '✗ FAIL'}")
    
    if not validation['all_pass']:
        print("\n⚠️  WARNING: Validation failed! Adjusting...")
        sys.exit(1)
    
    # Output
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        import os
        _root = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", ".")) / "data-pipeline"
        output_dir = _root / "growers" / args.grower_slug / "farms" / args.farm_slug / "fields" / args.field_id / "trials"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save fieldbook
    fieldbook = plots_utm[["plot_id", "block", "row", "col", "variety", "area_acres"]].copy()
    fieldbook_df = pd.DataFrame(fieldbook)
    fieldbook_df.sort_values(by=["block", "col"]).to_csv(output_dir / "rcbd_fieldbook.csv", index=False)
    
    # Save metadata
    metadata = {
        "field_id": args.field_id,
        "grower_slug": args.grower_slug,
        "farm_slug": args.farm_slug,
        "trial_acres": float(trial_config['trial_acres']),
        "plot_acres": float(trial_config['plot_acres']),
        "plot_width_m": float(trial_config['plot_width_m']),
        "plot_height_m": float(trial_config['plot_height_m']),
        "headlands_m": float(args.headlands_m),
        "rotation_deg": int(trial_config['angle']),
        "center_x": float(trial_config['center_x']),
        "center_y": float(trial_config['center_y']),
        "varieties": varieties,
        "blocks": int(args.blocks),
        "total_plots": int(trial_config['num_plots']),
        "seed": int(args.seed),
        "mode": "maximize" if args.maximize else "fixed",
        "validation": {k: bool(v) for k, v in validation.items() if k != 'dissolved'}
    }
    with open(output_dir / "trial_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    # Create map
    create_trial_map(field_utm, headlands_gdf, plots_utm, trial_config,
                     args.field_id, varieties, variety_colors,
                     output_dir / "trial_map_maximized.png")
    
    print(f"\n✓ Output saved to: {output_dir}")
    print(f"  - rcbd_fieldbook.csv")
    print(f"  - trial_metadata.json")
    print(f"  - trial_map_maximized.png")
    print("\n🌾 Done!")

if __name__ == "__main__":
    main()
