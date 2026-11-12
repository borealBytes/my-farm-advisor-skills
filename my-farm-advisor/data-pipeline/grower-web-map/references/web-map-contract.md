# Grower Web Map Contract

This file is the contract between the generator and anyone changing the page. It
describes the embedded data shape, the required UI behavior, the basemap policy, and
the size budget.

## Embedded data

The HTML carries one JSON block:

```html
<script id="grower-map-data" type="application/json">{...}</script>
```

Top-level shape:

```json
{
  "generator": "grower-web-map",
  "version": "0.1.0",
  "area_unit": "hectares",
  "grower": {"slug": "", "name": "", "farm_count": 0, "field_count": 0, "area_ha": 0.0},
  "farms": [
    {"slug": "", "name": "", "state": "", "color": "#hex", "area_ha": 0.0,
     "fields": [{"field_id": "", "field_slug": "", "field_name": "", "area_ha": 0.0}]}
  ],
  "geojson": {"type": "FeatureCollection", "features": []}
}
```

Each feature property set is exactly:

| Property | Required | Notes |
| --- | --- | --- |
| `field_id` | yes | Pipeline field identifier |
| `field_slug` | yes | Runtime directory name |
| `field_name` | yes | `field.json` display name, falling back to slug |
| `farm_slug`, `farm_name` | yes | Farm identity for the popup |
| `grower_slug`, `grower_name` | yes | Grower identity for the popup |
| `area_ha` | yes | Hectares, rounded to 3 decimals |
| `crop_name` | no | OSM `landuse` tag from the boundary |
| `county_name` | no | County from the boundary |
| `state_fips` | no | Two-digit state FIPS |
| `source` | no | Boundary provider string |

`area_acres` must not appear in the embedded payload or the manifest.

## Required UI behavior

1. All fields for the grower render at once, colored per farm, with a legend.
2. A constant-size locator marker sits at each field centroid so dispersed fields stay
   visible when the grower extent is zoomed out; clicking it focuses the field.
3. Zoom and pan work; "Fit all fields" restores the grower extent.
4. Clicking a field opens a popup containing grower, farm, field name, field ID, and
   area in hectares.
5. A sidebar lists fields by farm; clicking a row zooms to the field and opens its popup.
6. A search box filters the sidebar by field name, ID, or farm name.
7. The page stays usable at 320 px viewport width; the sidebar becomes a drawer.

## Basemap policy

- Default base layer: Esri World Imagery
  (`.../World_Imagery/MapServer/tile/{z}/{y}/{x}`), `maxZoom: 19`.
- Overlay: Esri World Boundaries and Places labels, on by default.
- Secondary base: OpenStreetMap standard tiles, off by default.
- Attribution is mandatory and rendered by Leaflet; do not remove it.
- Tiles are fetched at view time. Never inline tile images or raster products.

## Size budget

| Condition | Expectation |
| --- | --- |
| Four fields | ~15–25 KB total HTML |
| 100 fields | under ~400 KB |
| Any grower | No embedded imagery, no base64, no data bundle |

If a page approaches the megabyte range, investigate repeated attributes or
unnecessary coordinate precision before adding a simplification step.

## Failure behavior

- A grower with no usable field polygons fails with a non-zero exit and an explicit
  error; it does not write an empty map.
- Unusable features (non-areal geometry, missing `field_id`, coordinates outside
  EPSG:4326 ranges) are skipped, counted, and recorded in the manifest under
  `skipped_features`.
- Missing optional metadata (crop, county, source, display name) falls back to a
  placeholder rather than failing the render.
