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
