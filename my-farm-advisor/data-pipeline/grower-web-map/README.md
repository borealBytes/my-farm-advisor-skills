# Grower Web Map

Lightweight interactive HTML map, one file per grower, built from the real field
polygons the data pipeline already downloaded.

- **Input:** installed runtime tree — `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
- **Output:** `growers/<grower>/derived/maps/<grower>_fields_map.html` plus a small manifest
- **Basemap:** Esri World Imagery tiles (online), optional place labels and OpenStreetMap streets
- **Areas:** hectares, converted from the boundary file's `area_acres`

## Why it exists

The pipeline writes farm reports, posters, and cards, but there is no grower-level
view that a grower can open in a browser and click through. This subskill closes that
gap without shipping imagery: it embeds a few kilobytes of GeoJSON and lets Leaflet
fetch the satellite tiles.

## Run it

From an installed runtime (the normal path):

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/install.sh"
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/generate_grower_web_map.py"
```

Render one grower or choose an output directory:

```bash
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/generate_grower_web_map.py" \
  --grower-slug il-prairie-grower

"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/generate_grower_web_map.py" \
  --grower-slug ia-cedar-grower \
  --output-dir "$DATA_PIPELINE_DATA_ROOT/data-pipeline/exports/grower-maps"
```

The CLI accepts `--data-root` instead of the environment variable, `--title` for a
custom page title, `--area-decimals` for the console summary, and `--quiet`.

## Output contract

| Artifact | Where | Notes |
| --- | --- | --- |
| HTML map | `growers/<grower>/derived/maps/<grower>_fields_map.html` | Self-contained page, external tiles only |
| Manifest | `growers/<grower>/derived/maps/<grower>_fields_map.manifest.json` | Counts, hectares, sources, skipped features |

Expected size is roughly 15–25 KB for a four-field grower. The payload grows with
coordinate count and field attributes, not with imagery: a few hundred fields stays in
the low megabytes, and no raster is ever embedded.

## Map behavior

- Satellite imagery is the default base layer; place labels are on, streets are a
  toggle. Zoom, pan, scale bar, and layer control are standard Leaflet.
- Every field for the grower is drawn, colored per farm, with a legend in the sidebar.
- Constant-size locator dots mark each field centroid, so a grower with dispersed fields
  still sees every field in the fit-all view. Dots are toggleable in the layer control.
- Clicking a field opens a popup with **grower, farm, field name, field ID, area (ha),
  crop tag, county, and boundary source**.
- The sidebar lists fields by farm. Clicking a row zooms to that field and opens its
  popup; hovering syncs the highlight; the search box filters by name, ID, or farm.
- "Fit all fields" returns to the grower extent. The layout collapses to a drawer on
  narrow screens.

## Hectares, not relabelled acres

Source boundaries store `area_acres`. The generator converts every value with the
exact international acre:

```text
1 acre       = 4046.8564224 m²
1 hectare    = 10 000 m²
hectares     = acres × 0.40468564224
```

Field values are converted before rounding. Farm and grower totals are summed from
unrounded field hectares and then rounded, so a total can differ from the sum of
rounded field values by up to 0.05 ha. The HTML displays one decimal; the manifest
stores two. `area_acres` is never written into the HTML or the manifest.

If a boundary feature has no `area_acres`, the generator computes the polygon area
spherically and converts m² to hectares, recording nothing extra.

## Determinism

- Growers, farms, and fields are sorted by slug, and JSON keys are sorted, so the same
  runtime tree produces the same HTML bytes.
- No timestamps are written into the HTML or manifest.
- Colors are assigned per farm in slug order from a fixed palette.

## Requirements

- Python 3.11+ standard library only; no new dependencies and no changes to the
  runtime virtualenv.
- Internet access in the browser for Esri tiles. Without it the polygons and sidebar
  still render, but the basemap is blank.
- Read access to the runtime tree under `DATA_PIPELINE_DATA_ROOT`.

## Limits

- This is a viewer, not a GIS editor. It does not create or modify boundaries.
- Public Esri World Imagery tiles are used with attribution for demo and operational
  review. A production deployment that needs guaranteed tile availability or
  contractual terms should supply its own licensed tile service.
- Field boundaries retain their source license (OpenStreetMap/Overpass is ODbL and
  needs attribution; the map footer and README record it).
- Acres from the source file are the pipeline's figure of record; this skill does not
  re-survey geometry, it converts the reported area.

## Verification

Run from the repository root after changes:

```bash
bash scripts/validate.sh
```

For a runtime check, render both growers and confirm the manifest counts, hectares,
and HTML size:

```bash
python3 - <<'PY'
import json, pathlib
for slug in ("il-prairie-grower", "ia-cedar-grower"):
    p = pathlib.Path.home()/"my-farm-advisor-runtime/data-pipeline/growers"/slug/"derived/maps"/f"{slug}_fields_map.manifest.json"
    data = json.loads(p.read_text())
    print(slug, data["field_count"], "fields", data["area_ha"], "ha", data["html_bytes"], "bytes")
PY
```
