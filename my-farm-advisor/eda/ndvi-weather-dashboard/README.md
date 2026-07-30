# ndvi-weather-dashboard

Generate interactive HTML dashboards combining satellite NDVI time series, NASA POWER daily
weather, cumulative GDD, and drought SPI for a single field-year. Two dashboard types are
produced:

- **Yearly dashboard** — 4-panel Plotly chart (NDVI, precipitation, temperature, GDD) with
  event hover markers, year overview text, and yield constraint warnings.
- **Main dashboard** — year-over-year comparison table (environmental indicators, drought SPI,
  soil summary) plus an NDVI timelapse map with Leaflet satellite imagery.

---

## How to Run

### Prerequisites

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
```

All commands use the data-pipeline virtual environment for geospatial dependencies.

### Yearly Dashboard (single year)

```bash
cd my-farm-advisor-skills/my-farm-advisor/eda/ndvi-weather-dashboard/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  ndvi_weather_dashboard.py osm-1499317763 --year 2023
```

Or from Python:

```python
from ndvi_weather_dashboard import generate_dashboard

path = generate_dashboard(
    field_slug="osm-1499317763",
    year=2023,
    grower_slug="il-grower",
    farm_slug="il-grower-illinois",
)
print(f"Dashboard: {path}")
```

### Main Dashboard (all years)

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  my-farm-advisor-skills/my-farm-advisor/eda/ndvi-weather-dashboard/src/generate_main_dashboard.py
```

### Batch Generate All Years

```python
from ndvi_weather_dashboard import generate_dashboard

for year in [2021, 2022, 2023, 2024, 2025]:
    path = generate_dashboard(field_slug="osm-1499317763", year=year)
    print(f"{year}: {path}")
```

---

## Output Location

Dashboards are written to the field's `derived/dashboards/` directory:

| Dashboard | Filename |
|-----------|----------|
| Yearly | `ndvi_weather_dashboard_<year>.html` |
| Main | `field_dashboard.html` |

Full path:

```
growers/<grower>/farms/<farm>/fields/<field>/derived/dashboards/
```

Example for the reference field:

```
growers/il-grower/farms/il-grower-illinois/fields/osm-1499317763/derived/dashboards/
├── field_dashboard.html                        # main dashboard
├── ndvi_weather_dashboard_2021.html
├── ndvi_weather_dashboard_2022.html
├── ndvi_weather_dashboard_2023.html
├── ndvi_weather_dashboard_2024.html
└── ndvi_weather_dashboard_2025.html
```

Both are self-contained HTML files — open directly in any browser.

---

## Dependencies

### Python Runtime

The data-pipeline virtual environment (`data-pipeline/.venv`) provides all dependencies:

| Package | Required for |
|---------|-------------|
| `pandas` | Weather data loading, metric computation |
| `numpy` | GDD calculation, SPI computation |
| `plotly` | Interactive 4-panel chart (yearly dashboard) |
| `geopandas` | Field boundary reading |
| `rasterio` | NDVI GeoTIFF reading for zonal statistics |
| `Pillow` | NDVI raster → PNG conversion (main dashboard map) |
| `urllib3` | NASA POWER API call for SPI data |

### Browser

Any modern browser (Chrome, Firefox, Edge, Safari).

### Internet Access

| Feature | Requires internet? | Notes |
|---------|-------------------|-------|
| Plotly chart interactivity | Yes | plotly.js loaded from CDN (`cdn.plot.ly`) |
| Leaflet map basemap | Yes | Esri World Imagery tiles from `arcgisonline.com` |
| Static content (text, tables) | No | HTML with inline CSS renders offline |
| Hover tooltips on chart | Yes | Requires plotly.js CDN |

Without internet, dashboards display all text, tables, and static chart images but
interactive features (zoom, pan, hover tooltips, map tiles) will not function.

### Data Pipeline

The target field must have been processed through the data pipeline steps:

1. Field boundary ingested (`boundary/field_boundary.geojson`)
2. Satellite imagery downloaded (Sentinel-2 + Landsat manifests, NDVI GeoTIFFs)
3. Weather downloaded (NASA POWER, `weather/daily_weather.csv`)
4. CDL crop classification (`derived/tables/ndvi_year_crop_join.csv`)
5. SSURGO soil data (for main dashboard soil summary)

---

## Dashboard Layout

### Yearly Dashboard

```
ndvi_weather_dashboard_2023.html
├── Header (field, crop, year, scene count badges)
├── Warning banners (missing data, sparse coverage)
├── 4-panel interactive chart
│   ├── Panel 1: NDVI — Sentinel-2 (green) + Landsat (orange) trend lines
│   ├── Panel 2: Precipitation — bars with heavy rain in dark blue
│   ├── Panel 3: Temperature — T2M_MAX, T2M, T2M_MIN lines
│   └── Panel 4: Cumulative GDD — curve with crop-stage reference lines
├── Year Overview (crop summary, precipitation, GDD, SPI)
├── ⚠️ Potential Yield Constraints (threshold-based warnings)
└── Key events (chronological list of weather/NDVI events)
```

### Main Dashboard (field_dashboard.html)

```
field_dashboard.html
├── Header (field, county, acres, crop rotation)
├── Soil Summary card (WHC, OM%, pH, dominant soil, drainage)
├── Key Environmental Indicators per Year table
│   ├── Crop (with emoji), Cumulative GDD
│   ├── Days > 30°C (Heat Stress Warning)
│   ├── Days < 10°C (Not Enough Heat)
│   ├── Days Precip > 44.7 mm (Flood Warning)
│   ├── Drought (6-mo SPI)
│   └── Peak NDVI (max value per row highlighted red)
├── NDVI Timelapse 2021–2025 (Esri satellite map)
│   ├── 80+ NDVI overlays from Sentinel-2 + Landsat
│   ├── Time slider + play button
│   └── Key event list (click to jump to nearest scene)
└── Footer
```

---

## Input Data

All paths relative to the field root (`growers/<g>/farms/<f>/fields/<field>/`):

| Asset | Path |
|-------|------|
| CDL crop join | `derived/tables/ndvi_year_crop_join.csv` |
| Sentinel manifest | `satellite/sentinel/manifest.json` |
| Landsat manifest | `satellite/landsat/manifest.json` |
| Sentinel NDVI rasters | `satellite/sentinel/{year}/sentinel_{date}/*_ndvi.tif` |
| Landsat NDVI rasters | `satellite/landsat/{year}/landsat_{date}/*_ndvi.tif` |
| Field boundary | `boundary/field_boundary.geojson` |
| Daily weather | `weather/daily_weather.csv` |
| SSURGO summary | `soil/ssurgo_summary.csv` |
| Field metadata | `field.json` |

---

## Key Metrics

### GDD Calculation

```
Daily GDD = max(0, (T2M_MAX + T2M_MIN) / 2 - 10°C), capped at 30°C
```

Accumulation starts March 1 (DOY 60). Crop-stage reference lines:

| Stage | Corn (GDD) | Soybeans (GDD) |
|-------|-----------|----------------|
| VE | 120 | 130 |
| V6 | 250 | 350 |
| V12 / R1 | 550 / 1100 | 750 |
| R3 / R5 | 1700 | 1400 |
| R6 / R8 | 2500 | 2100 |

### Drought (6-mo SPI)

Standardized Precipitation Index computed from NASA POWER monthly
precipitation (2000–present baseline, April–September 6-month window).
Thresholds follow drought.gov conventions:

| SPI Range | Category |
|-----------|----------|
| ≥ 2.0 | W4 - Exceptionally Wet |
| 1.6 to 1.9 | W3 - Extremely Wet |
| 1.3 to 1.5 | W2 - Severely Wet |
| 0.8 to 1.2 | W1 - Moderately Wet |
| 0.5 to 0.7 | W0 - Abnormally Wet |
| –0.5 to 0.5 | Normal |
| –0.7 to –0.5 | D0 - Abnormally Dry |
| –1.2 to –0.8 | D1 - Moderate Drought |
| –1.5 to –1.3 | D2 - Severe Drought |
| –1.9 to –1.6 | D3 - Extreme Drought |
| ≤ –2.0 | D4 - Exceptional Drought |

### Yield Constraint Thresholds

| Constraint | Threshold |
|------------|-----------|
| Low GDD | Cumulative GDD < 2000 |
| Early crop flooding | Heavy rain (>44.7 mm) in April |
| Severe drought | SPI category D2, D3, or D4 |
| Heat stress | >40 days with T2M_MAX > 30°C |
| Not enough heat | >110 days with T2M_MAX < 10°C |

---

## Known Data Limitations

- **CDL coverage**: only years present in `ndvi_year_crop_join.csv` are available
- **Cloud cover**: scenes with cloud cover > 70% are excluded
- **Weather gaps**: missing weather days > 10% in Mar–Nov trigger a warning
- **GDD parameters**: base/cap fixed at 10/30°C (corn defaults); soybean stages use
  different thresholds
- **SPI baseline**: 2000–present (NASA POWER era); shorter baselines increase variance
- **NDVI emergence**: estimated from first scene with NDVI ≥ 0.3 (DOY ≥ 60); may not
  reflect true planting date
- **Field boundary**: must be present for NDVI zonal statistics
