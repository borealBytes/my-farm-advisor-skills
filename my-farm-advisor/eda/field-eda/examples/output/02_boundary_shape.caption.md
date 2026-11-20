# F2 — Field shape versus area

**Question:** Are larger fields more regular in shape?

**What this shows:** Source separates the two bands: CSB blocks have a median compactness of 0.34 against 0.63 for OSM parcels. Within CSB, larger fields are less compact, not more (Spearman about -0.6): they are long, survey-aligned blocks. OSM parcel size shows no relationship. Shape is a provenance story with a size tilt, not a simple size story.

**Caveat:** Thirty fields. The guide lines are visual only; the reported Spearman correlations and their bootstrap intervals in boundary_analysis.csv are the evidence, and size and source remain confounded.

**Reading notes:**
- Compactness is computed in EPSG:5070 metres, never in degrees.

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
