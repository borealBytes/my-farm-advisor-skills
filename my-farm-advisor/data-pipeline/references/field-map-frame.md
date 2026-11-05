# Field-local map frame (UTM origin-at-SW, north arrow, viewport rotation)

Any figure that draws a field polygon for a human — horizon tables, property
maps, trial-placement plans, NDVI/terrain field maps — uses this frame. Never
plot a single field on geodetic degree axes; at field scale degrees are
uninterpretable ticks with no meaning.

## The standard (implemented in `generate_soil_texture_triangles.py`)

1. **Project to the local UTM zone**: `zone = floor((lon + 180) / 6) + 1`,
   EPSG `32600 + zone` (north) / `32700 + zone` (south). Metres are the only
   honest unit for a field.
2. **Pin the origin**: translate the whole layer by the SW corner of the
   field bounding box so the field starts at `(0, 0)`. Axis labels:
   `"m E from SW corner (UTM {zone})"` and `"m N"`. Every coordinate the
   reader sees is "how far into my field".
3. **North arrow, boxed, top-right**: bold `N` in a white rounded box with a
   heavy upward shaft, placed in axes-fraction coords so it never moves with
   data zoom. Non-negotiable — a metre-axis field map without a north arrow
   forces the reader to guess orientation.

## Rotating the field to fit the viewport

Long fields drawn into square (or wrong-aspect) panels waste half the figure.
Rotate the field geometry so its long axis spans the panel's long axis:

```python
import math
import shapely.affinity as aff

def orient_field(gdf, long_axis: str = "horizontal") -> tuple:
    """Rotate field geometry about the origin so the longest boundary edge
    runs along the panel's long axis. Returns (rotated_gdf, rot_deg)."""
    g = gdf.dissolve().geometry.iloc[0]
    mrr = g.minimum_rotated_rectangle
    pts = list(mrr.exterior.coords)
    edges = list(zip(pts, pts[1:]))[:4]
    (x1, y1), (x2, y2) = max(edges,
                             key=lambda e: (e[1][0]-e[0][0])**2 + (e[1][1]-e[0][1])**2)
    theta = math.degrees(math.atan2(y2 - y1, x2 - x1))   # bearing of long edge
    rot = theta if long_axis == "horizontal" else theta - 90.0
    return gdf.assign(geometry=gdf.geometry.map(
        lambda geom: aff.rotate(geom, -rot, origin=(0, 0)))), rot % 360.0
```

**Pitfalls, in order of how they will bite:**

- **Translate → rotate → re-translate.** Pin SW at (0,0), rotate the geometry
  about that origin, then re-pin (0,0) at the SW corner of the **rotated**
  bounding box — that is the corner the reader's ruler starts from. Rotating
  about the geographic origin flings the field off-canvas.
- **Pick the orientation from the panel's actual aspect at draw time**
  (`fig.canvas.draw()` → `ax.get_position()` × figsize): field long edge along
  the panel's long edge, always. Never hardcode "horizontal".
- **The north arrow rotates opposite to the data.** The data frame no longer
  points up after rotation. If the geometry was rotated clockwise by `rot`,
  the arrow tip must point `(cx + r·sin rot, cy + r·cos rot)` in
  axes-fraction coords (straight up is `(0, 1)`), with the boxed `N` label
  beyond the tip. Rotating the geometry and keeping a straight-up arrow is a
  lie, not a simplification.
- **Keep the metre grid axis-aligned to the frame, not the field**: gridlines
  read as distances; the field rotates inside them.
- When `rot != 0`, label the axes `"field-local m (rotated {rot:.0f}° from E)"`
  — "from SW corner" alone implies unrotated easting. Normalize |rot| < 0.25°
  to exactly 0 so near-vertical fields keep the plain "m E from SW corner"
  label and a straight arrow instead of a noisy "360°".
- Rotation is presentational: never store rotated geometries as the field
  boundary of record; re-apply at render time from the EPSG:4326 boundary.

## References in this repo

- Live implementation: `src/scripts/reporting/generate_soil_texture_triangles.py`
  (`render_horizon_table` map panel: UTM pin + boxed N arrow; rotation helper
  above is the extension contract).

## Ship checklist (vision-QC enforced, 2026-11-05)

- Rotation canonicalized to (-90, +90] with a **0.5° dead-zone** — a −0° field
  is an unrotated field; it gets the plain `m E from SW corner` label, a
  straight arrow, and NO callout.
- When rotated: italic callout inside the panel, top-left,
  `field rotated ±NN° to fit — N shown by arrow`; axis states the same angle.
- **500 m scale bar** always (blended data-x/axes-y transform so the length is
  honest after aspect equal + datalim).
- Arrow: r=0.135 axes-fraction, lw 3.0, boxed N at fontsize 16, tip at
  (cx + r·sin rot, cy + r·cos rot).
- Table: `auto_set_column_width(all)` then **×1.35 width on every numeric
  column via `cell.set_width`** (mpl ≥ 3.11 moved widths onto cells;
  `Table.alter`/`_argW` are gone). Without the slack, adjacent values read as
  merged columns ("6.50.18").
- Depth axis lives on the FIRST profile panel only (ticks 20/60, no bottom
  100 label — it collides with xtick labels); texture strip carries a real
  3-swatch sand/silt/clay legend below the panel; the method footnote is
  LEFT-aligned at x=0.40 so it never runs under that legend.

## Raster-buffer and legend conventions (2026-11, global-data-parity)

- **Every raster clip** must extend beyond the true field boundary by at least
  one source cell, so boundary pixels are complete and edge-effect statistics
  (coverage %, filter neighborhoods) are computable. The single source of
  truth is `src/scripts/lib/raster_rules.py`:
  `buffer_meters(source_crs, cell_m, cells=EDGE_BUFFER_CELLS)` with
  `EDGE_BUFFER_CELLS = 1` (absolute floor) and
  `EDGE_BUFFER_CELLS_FILTER = 3` for clips feeding terrain filters
  (slope/TWI kernels read up to 3 cells in). Ingest sites record
  `coverage_pct` (field area inside valid pixels) in their provenance
  manifests at download time — a boundary with >0 % no-data in the clip is
  a visible, actionable flag, not a silent hole.
- **Grid-map panels share one identical frame rect** across every band:
  rasters are square-padded bottom-anchored (extra space east+north of the
  NW-pinned data), and a post-layout pass repositions all used axes onto one
  common square before `savefig` — otherwise colorbar widths silently differ
  the datalim padding and the panels cannot be compared side by side.
- **Soil-property colorbars are discrete ISRIC legends, never continuous
  gradients**: `BoundaryNorm` on the vendored ISRIC `soil.legends` TSV
  boundaries (crop to data range ±3 bands, ≤9 ticks). SoilGrids pH legends
  are ×10-encoded — divide PHIHOX MIN/MAX by 10 before use.
- On dense multi-panel grids (7-up+) the north arrow moves to the **SE
  corner** (`arrow_xy=(0.04, 0.86)`) at r=0.11 / boxed-N fontsize 11, and
  scale-bar text always carries a white halo bbox so it survives any tile.
- Restriction callouts on horizon tables live in a matplotlib **legend box**
  (hatched Patch handles, one entry per band) right of the texture stack —
  hand-placed gutter text provably collides when depth windows nest.

## Continuous vs categorical — the scale standard for every map we publish

Each figure declares its feature type and gets the scale class the literature
uses for it (no rainbow on continuous fields, no continuous gradient on
banded soil classes):

| Feature | Type | Scale (standard adopted) |
| --- | --- | --- |
| Soil clay/silt/sand %, pH, CEC, OC (gridded) | banded soil classes | **ISRIC SoilGrids `soil.legends` discrete steps** (`BoundaryNorm`, vendored TSVs) — the same breaks ISRIC maps itself |
| Soil texture class (triangle panel) | categorical (12 classes) | USDA texture-triangle fills, categorical |
| Crop type / land class | categorical | WorldCereal official palette codes; unknown = white swatch with grey edge |
| Elevation (DEM) | continuous | `terrain` (green→brown→white→blue) — relief convention, perceptually ordered |
| Hillshade | continuous | grayscale |
| Slope, TWI | continuous, positive-skew | sequential (`YlOrBr`, `YlGnBu`) |
| Flow accumulation, LS | continuous, power-law | sequential on **log10** — axis says so (`log₁₀ upstream cells`) |
| TPI, relative elevation | continuous, signed about 0 | diverging `RdBu_r`, midpoint at 0 |
| Aspect | **cyclic** | HSV hue wheel, vmin/vmax fixed 0–360 (a sequential map on a cyclic quantity fakes a seam at N) |
| NDVI | continuous −1…1 | diverging green↔tan (RdYlGn family), zero at the neutral break |

Rule of thumb encoded in the renderers: if the value can be averaged
meaningfully and orders spatially → sequential/diverging continuous; if it
names something → categorical palette from the governing standard; if it is
already published with official breaks (SoilGrids) → reuse the breaks,
verbatim. Colorbars then carry units and (for log scales) the transform.
