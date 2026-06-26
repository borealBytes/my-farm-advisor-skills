# Assignment 2: Field-Level EDA (Illinois, Iowa, Nebraska)

Compare field boundaries, CDL cropland history, and weather across 3 growers
(~10 fields each) in Illinois (Iroquois), Iowa (Kossuth), and Nebraska (Hall).

## Input Data

| Source | Format | Location per farm |
|---|---|---|
| Field boundaries | GeoJSON (`field_boundaries.geojson`) | `boundary/` |
| Weather (NASA POWER) | CSV (`{prefix}_weather_{start}_{end}.csv`) | `derived/tables/` |
| CDL annual | CSV (`{prefix}_{year}_cdl.csv`) | `derived/tables/` |
| CDL composition | CSV (`{prefix}_cdl_{start}_{end}_full_composition.csv`) | `derived/tables/` |
| Crop rotation | CSV (`{prefix}_crop_rotation.csv`) | `derived/tables/` |

## Output

`shared/assignment2-eda/derived/` under the runtime root:

```
reports/
  boundaries_area_histogram.png     — stat vis 1: field size distribution
  boundaries_area_stats.png         — stat vis 2: mean/median area per grower
  boundaries_area_boxplot.png       — comparison: area across growers
  boundaries_field_map.png          — map: all fields colored by grower
  cdl_composition_by_grower.png     — stat vis 1: crop mix by grower
  cdl_crop_trend.png                — stat vis 2: corn/soy trend 2021–2025
  cdl_rotation_diversity.png        — comparison: rotation diversity across growers
  cdl_dominant_crop_map.png         — map: dominant 2025 crop per field
  weather_annual_precip.png         — stat vis 1: annual precip by grower
  weather_monthly_temps.png         — stat vis 2: monthly temperature profiles
  weather_temp_precip_scatter.png   — comparison: temp vs precip correlation
  weather_avg_temp_map.png          — map: field-level mean temperature
tables/
  field_boundary_summary.csv
  cdl_summary.csv
  weather_summary.csv
  combined_field_summary.csv
```

## Run

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_assignment2.py
```
