# F7 — Maturity fit against county heat

**Question:** Does each season deliver the heat the county's recommended relative maturity assumes?

**What this shows:** IA sits 57 GDD below its county target and the season mean falls short in 4 of 5, by up to 108 GDD (5.4 RM) in 2022; IL sits 25 GDD below its county target and the season mean falls short in 3 of 5, by up to 111 GDD (5.6 RM) in 2023; NE sits 7 GDD above its county target and the season mean falls short in 2 of 5, by up to 67 GDD (3.3 RM) in 2021. The county target is a county-average planning value, so part of a gap is location and part is the season. A farm that sits below the county reference needs an earlier hybrid even in a normal year.

**Caveat:** Two GDD definitions meet here on purpose: this figure uses the whole calendar year, base 10 °C, cap 30 °C, matching maturity-by-fips; F5 and A3 use April-September with no cap. The county reference is built from the county weather table, not from these ten fields, so a level offset is location, not management. Field spread is NASA POWER grid spread, so the verdict is per grower.

**Reading notes:**
- Required GDD is the county RM target times 20 GDD per RM, the same linear rule the maturity product applies.
- Soybean maturity is latitude-regression based and has no comparable heat test, so it is reported as a reference value in A4 only.

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
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2021.parquet`
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2022.parquet`
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2023.parquet`
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2024.parquet`
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2025.parquet`
- `data-pipeline/shared/corn_maturity/tables/rm_by_fips_2021_2025_average.parquet`
- `data-pipeline/shared/soybean_maturity/tables/mg_by_fips_2021_2025_average.parquet`
