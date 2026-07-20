# Grower Web Map — Verification & Test Results

## Test Environment

| Property | Value |
|----------|-------|
| Branch | `FP1` |
| Runtime root | `~/my-farm-advisor-runtime` |
| Growers tested | `il-northern-grower` (Illinois), `ia-northern-grower` (Iowa) |
| Script | `src/scripts/reporting/generate_grower_web_map.py` |
| Date | 2026-07-17 |

## Commands Executed

### 1. Sync runtime source

```bash
cd my-farm-advisor/data-pipeline
./scripts/install.sh --force-refresh --no-install-deps
```

### 2. Generate Illinois grower map

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug il-northern-grower
```

### 3. Generate Iowa grower map

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug ia-northern-grower
```

## Output Verification

| Grower | Output Path | File Size | Status |
|--------|-------------|-----------|--------|
| `il-northern-grower` | `growers/il-northern-grower/maps/grower_web_map.html` | **26.2 KB** | ✅ Generated |
| `ia-northern-grower` | `growers/ia-northern-grower/maps/grower_web_map.html` | **232.3 KB** | ✅ Generated |

> **Note:** The Iowa map is larger because its fields are significantly larger (155, 271, and 16 acres) compared to Illinois (2.2, 3.9, and 0.8 acres), resulting in more coordinate vertices in the GeoJSON.

## Requirements Checklist

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Use actual downloaded field polygon boundaries | Reads `boundary/field_boundaries.geojson` per farm | ✅ |
| Show field polygons on a generic basemap | Esri Satellite + OpenStreetMap via CDN | ✅ |
| Show all fields for each grower | Iterates all farms and fields under `growers/<slug>/farms/` | ✅ |
| User can zoom in and out | Leaflet.js default zoom and pan controls enabled | ✅ |
| Click a field to see basic metadata | Popup shows: Grower, Farm, Field name, ID, Area (acres), County, soil data | ✅ |
| Simple field list / control to zoom to fields | Sidebar field list; click zooms to field and opens popup | ✅ |
| HTML output reasonably small | GeoJSON + summary values only; no rasters or imagery embedded | ✅ |

## Data Flow

The following diagram illustrates how pipeline output assets are consumed to produce the self-contained HTML map:

```mermaid
flowchart LR
    A["Farm Boundary<br/>field_boundaries.geojson"] --> E["generate_grower_web_map.py"]
    B["Soil Summary<br/>ssurgo_summary.csv"] --> E
    C["Soil Polygons<br/>ssurgo_soil_types.geojson"] --> E
    D["NDVI Summary<br/>ndvi_yearly_summary.json"] --> E
    E --> F["Self-contained HTML<br/>grower_web_map.html"]

    style E fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style F fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
```

## Runtime Architecture

The following diagram shows the relationship between the skill source, the runtime copy, and the generated output:

```mermaid
flowchart LR
    A["Skill Source<br/>my-farm-advisor/data-pipeline/src/"] -->|"install.sh<br/>--force-refresh"| B["Runtime Source Copy<br/>~/my-farm-advisor-runtime/.../src/"]
    B -->|"python<br/>generate_grower_web_map.py"| C["Generated HTML Maps"]

    C --> D["growers/il-northern-grower/<br/>maps/grower_web_map.html"]
    C --> E["growers/ia-northern-grower/<br/>maps/grower_web_map.html"]

    style A fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style B fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style C fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
```

## Observations

- Both growers have **empty NDVI yearly summaries** (`"years": []`), so the NDVI layer correctly shows “no data” and is disabled in the UI.
- SSURGO soil summaries are present for both growers, so **Soil OM%**, **Soil pH**, and **Soil Polygons** layers are functional.
- The generated HTML files are pure static assets with no server dependency; they can be opened directly in any modern browser.
- Per the repository asset policy, generated HTML maps live under the runtime directory and are **not committed to Git**.
