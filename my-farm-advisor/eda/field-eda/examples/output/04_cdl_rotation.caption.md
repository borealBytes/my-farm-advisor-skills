# F4 — Crop rotation timeline

**Question:** How does each field rotate, year by year?

**What this shows:** Illinois and Iowa alternate corn and soybean almost everywhere. Nebraska holds corn for multi-year runs, which is what the corn-after-corn rate in cdl_analysis.csv quantifies. Rotation is a field-level property, and it is the clearest within-field signal in this dataset.

**Caveat:** Five years only, 2019-2023. No 2024 or 2025, so no completed rotation cycle is guaranteed and the pipeline's predicted next crop cannot be tested here.

**Reading notes:**
- Cell label is the year; colour is the dominant crop by CDL percentage.
- Dominant crop can hide a split field: check the shares in F3.
- CDL is 30 m raster: the smallest field-year in this run has 4 pixels.

**Inputs:**
- `data-pipeline/growers/ia-cedar-grower/farms/cedar-farm/boundary/field_boundaries.geojson`
- `data-pipeline/growers/ia-cedar-grower/farms/cedar-farm/derived/tables/cedar_weather_2021_2025.csv`
- `data-pipeline/growers/ia-cedar-grower/farms/cedar-farm/derived/tables/cedar_cdl_2019_2023_full_composition.csv`
- `data-pipeline/growers/il-prairie-grower/farms/prairie-farm/boundary/field_boundaries.geojson`
- `data-pipeline/growers/il-prairie-grower/farms/prairie-farm/derived/tables/prairie_weather_2021_2025.csv`
- `data-pipeline/growers/il-prairie-grower/farms/prairie-farm/derived/tables/prairie_cdl_2019_2023_full_composition.csv`
- `data-pipeline/growers/ne-york-grower/farms/york-farm/boundary/field_boundaries.geojson`
- `data-pipeline/growers/ne-york-grower/farms/york-farm/derived/tables/york_weather_2021_2025.csv`
- `data-pipeline/growers/ne-york-grower/farms/york-farm/derived/tables/york_cdl_2019_2023_full_composition.csv`
