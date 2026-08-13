# Sustainability Intelligence Dashboard

## Skill Overview

This skill generates a **standalone HTML dashboard** for grower-level sustainability analysis, combining SSURGO soil health metrics, Sentinel-2 NDVI composites, and NASA POWER weather context into a single interactive visualization.

## Quick Start

### Prerequisites

- Python 3.10+
- Existing `my-farm-advisor` data pipeline runtime with processed fields
- The following Python packages (install via `requirements.txt`):
  - `geopandas`, `rasterio`, `rasterstats`, `pandas`, `numpy`
  - `plotly`, `folium`, `scipy`

### Installation

```bash
cd my-farm-advisor-skills/my-farm-advisor/dashboard/sustainability-intelligence-dashboard
pip install -r requirements.txt
```

### Running the Dashboard

```bash
# Set required environment variables
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
export AG_GROWER_SLUG=iowa-grower
export AG_FARM_SLUG=iowa-grower-iowa
export AG_FARM_NAME="Iowa Farm"
export PYTHONPATH=src

# Run the dashboard builder
python -m dashboard_builder.app
```

### Output

The dashboard is written as a single HTML file:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/dashboards/sustainability_dashboard.html
```

Open this file in any modern web browser (Chrome, Firefox, Edge, Safari). An internet connection is required for the Plotly and Bootstrap CDNs on first load.

## Dashboard Features

### Hero Map (Left Panel)
- **Field Boundaries**: Choropleth colored by Soil Health Index (SHI)
- **Field Drainage Class Layer**: Toggleable polygon layer showing each field's dominant drainage class
- **Esri Satellite Imagery**: Toggleable high-resolution base map
- **NDVI Marker Layer**: Toggleable circle markers sized and colored by average NDVI
- **Field Hover Popups**: Click any field to see SHI, area, dominant soil, drainage class, and latest NDVI

### Right Sidebar
- **KPI Cards**: Total fields, total acreage, average SHI, average NDVI, NDVI field count, average growing-season precipitation
- **Plotly Chart Carousel**: 5 interactive charts with dot navigation and keyboard arrow controls
  - **Scatter Plot**: SHI vs NDVI Coefficient of Variation with OLS trend line and R² annotation
  - **Heatmap**: SHI component breakdown (OM, AWS, CEC, pH, Clay) by field
  - **Boxplot**: Soil property distributions across fields with individual field hover points
  - **Climatology**: Dual-axis weather anomalies (precipitation bars + GDD line + NDVI overlay)
  - **NDVI Time-Series**: Mean NDVI trajectories by field (2021–2025)
- **Correlation Text**: Dynamic interpretation of the soil health-stability relationship
- **Methodology Note**: In-dashboard explanation of how SHI is calculated

### Year Explorer
- Select any year from 2021–2025 to see field-level mean NDVI, peak NDVI, precipitation anomaly, GDD anomaly, and dominant stress classification

### Executive Summary
- Natural-language summary of key findings, weather context, and field-level recommendations

## Data Requirements

The dashboard expects the following pre-computed datasets in the runtime directory:

| Dataset | Source | Location |
|---|---|---|
| Field Inventory | Pipeline manifest | `manifests/field-inventory.csv` |
| Field Boundaries | OSM / bootstrapped | `fields/<id>/boundary/field_boundary.geojson` |
| Integrated Field Analytics | Pipeline summary | `derived/tables/field_master_analytics.csv` |
| SSURGO Soil | NRCS Web Soil Survey | `derived/tables/iowa_grower_iowa_ssurgo_summary.csv` |
| SSURGO GeoJSON (used for field drainage) | NRCS Web Soil Survey | `fields/<id>/soil/ssurgo_soil_types.geojson` |
| NDVI Composites | Sentinel-2 + CDL masks | `fields/<id>/derived/features/ndvi_year_YYYY_composite.tif` |
| Weather Anomalies | NASA POWER | `derived/tables/farm_weather_anomalies.csv` |
| Weather Daily | NASA POWER | `derived/tables/iowa_grower_iowa_weather_2021_2025.csv` |
| CDL / Rotation | USDA NASS | `derived/tables/iowa_grower_iowa_crop_rotation.csv` |

## Workflow

```
1. Data Pipeline generates field data (boundaries, soil, weather, NDVI)
2. Run dashboard skill → reads field inventory + analytics + GeoJSONs + TIFs
3. Dashboard skill builds interactive Plotly charts and Folium map
4. Outputs standalone HTML to derived/dashboards/
```

## Architecture

```
dashboard_builder/
├── app.py              # Main orchestrator: loads data, builds charts, assembles HTML
```

Internal modules within `app.py`:
- `DataLoader`: Reads all runtime CSVs, GeoJSONs, and NDVI TIFs; loads field inventory dynamically
- `ChartBuilder`: Creates interactive Plotly charts
- `MapBuilder`: Creates Folium map with field boundaries, drainage class overlays, NDVI markers, layer control
- `DashboardBuilder`: Assembles all components into final HTML string

## Grower-Level Behavior

The dashboard is **grower-level**: it reads the farm's `manifests/field-inventory.csv` and builds the analysis for every field listed there. It does not hardcode a field list. Fields without NDVI composites are still included in the soil health, weather, and map sections; NDVI-specific charts automatically include only fields with available composites.

## Known Limitations

- **SoilGrids integration**: The ISRIC SoilGrids REST API is currently paused. Direct COG access was attempted but proved too slow for the project timeline (~15+ min for 9 depth/property combinations). The dashboard uses SSURGO-only SHI with a documented fallback plan.
- **NDVI coverage**: Only 5 of 10 fields have Sentinel-2 NDVI composites. The remaining 5 fields are included in soil, weather, and map sections but omitted from NDVI-specific charts.
- **Drainage layer**: The map shows field-level dominant drainage class rather than the full SSURGO map-unit polygons. This keeps the standalone HTML file small and fast-loading while still communicating spatial drainage patterns.
- **Climatology baseline**: Uses 5-year average (2021–2025) as "normal" rather than a 20+ year climatology due to data availability constraints.
- **Offline use**: The dashboard loads Plotly and Bootstrap from CDNs. For fully offline use, download the libraries locally and update the `<script>`/`<link>` tags.

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `DATA_PIPELINE_DATA_ROOT` error | Export the absolute path to your runtime directory |
| Empty dashboard / missing charts | Verify that `derived/tables/field_master_analytics.csv` exists |
| Map shows no fields | Check that `manifests/field-inventory.csv` and field `boundary/field_boundary.geojson` files exist |

## License

Same as parent `my-farm-advisor-skills` repository.
