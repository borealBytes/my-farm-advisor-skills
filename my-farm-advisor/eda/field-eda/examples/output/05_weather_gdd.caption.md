# F5 — Cumulative growing degree days

**Question:** How does each season accumulate heat, and how much does that differ?

**What this shows:** Nebraska accumulates about 2,076 GDD against 1,841 in Illinois and 1,719 in Iowa, and separates early in the season. Year-to-year spread inside a grower is small next to the between-grower gap.

**Caveat:** Five seasons, GDD base 10 °C with no upper cap, April-September. Weather comes from 4 grid cells at most per grower, so this is a regional curve rather than an on-farm measurement.

**Reading notes:**
- Within-grower field spread of seasonal GDD is 22-34 GDD.

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
