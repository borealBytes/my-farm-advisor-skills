# Figure Catalog

Every output answers one question, carries one story, and states one caveat. The
later report is assembled from these, so the caption text lives here as the
authoritative wording.

## Boundaries

### F1 — `figures/01_boundary_area.png`

- **Question:** How large are the fields, and is each grower one population?
- **Story:** Illinois and Iowa are bimodal — a handful of small hand-traced OSM
  parcels next to large CSB blocks. Nebraska is a single narrow band of large
  fields. Which grower you are talking about changes what "a field" means.
- **Caveat:** The split follows boundary provenance, not management. A farm with
  two sources will always look bimodal.
- **Inputs:** boundary files for every included farm.

### F2 — `figures/02_boundary_shape.png`

- **Question:** Are larger fields more regular in shape?
- **Story:** Boundary source separates the bands — CSB fields have a median
  compactness near 0.34 against 0.63 for OSM parcels. Within CSB, larger fields
  are *less* compact (Spearman about −0.6), because they are long survey-aligned
  blocks; OSM size shows no relationship. Source first, size second.
- **Caveat:** n = 30 fields. Read the correlation and its interval, not a
  significance star; size and source are confounded.
- **Inputs:** boundary files.

### A1 — `tables/boundary_analysis.csv`

- **Content:** per grower, Spearman correlation of log area with compactness plus
  a bootstrap interval; per source, the same correlation within that source and a
  Mann–Whitney U with rank-biserial effect size, plus the same test restricted to
  growers that contain both sources.
- **Story:** the source effect is large; within CSB, area is negatively related to
  compactness; OSM parcels show no size effect.
- **Caveat:** size and source are confounded; the file carries this as a note.

### M1 — `maps/01_boundary_sources.png`

- **Question:** Where are the fields, and who drew each one?
- **Story:** Nebraska is effectively one contiguous block of neighbouring CSB
  fields. Illinois and Iowa are scattered parcels, and the Illinois outlier at
  about 1 ha is visible next to blocks two orders of magnitude larger.
- **Caveat:** farm overview, not a single-field footprint. Local UTM kilometres,
  north arrow, scale bar; no auto-rotation.
- **Inputs:** boundary files.

## CDL

### F3 — `figures/03_cdl_composition.png`

- **Question:** What does each field grow across 2019–2023?
- **Story:** Nebraska is corn-dominated (about four field-years in five).
  Illinois is corn-leaning with a grass meadow outlier. Iowa leans soybean. The
  three growers are running recognisably different cropping systems.
- **Caveat:** five-year mean shares; the sequence is in F4.
- **Inputs:** CDL composition tables.

### F4 — `figures/04_cdl_rotation.png`

- **Question:** How does each field rotate, year by year?
- **Story:** Illinois and Iowa alternate corn and soybean. Nebraska holds corn
  for multi-year runs, which is what the corn-after-corn rate in A2 quantifies.
- **Caveat:** five years only. No 2024 or 2025, so no completed rotation cycle is
  guaranteed and prediction accuracy cannot be tested here.
- **Inputs:** CDL composition tables.

### A2 — `tables/cdl_analysis.csv`

- **Content:** per grower — corn and soybean share of field-years, corn-after-corn
  rate with a Wilson interval, mean Shannon diversity, most common rotation
  pattern; plus a chi-square test of crop class against grower with Cramér's V.
- **Story:** continuous corn is a Nebraska property, not a dataset artefact.
- **Caveat:** field-years within a field are not independent. The interval is
  descriptive.

### M2 — `maps/02_cdl_2023.png`

- **Question:** What was on each field in 2023?
- **Story:** corn and soybean blocks separate spatially, and the Illinois grass
  outlier is obvious. One shared legend across all growers.
- **Caveat:** 30 m CDL pixels; small parcels are represented by very few pixels.
- **Inputs:** CDL composition tables, boundary files.

## Weather

### F5 — `figures/05_weather_gdd.png`

- **Question:** How does each season accumulate heat?
- **Story:** Nebraska reaches roughly 2,000 GDD against about 1,840 in Illinois
  and 1,720 in Iowa, and separates early in the season. Year-to-year spread
  within a grower is small next to the between-grower gap.
- **Caveat:** five seasons; GDD base 10 °C with no upper cap.
- **Inputs:** weather tables.

### F6 — `figures/06_weather_precip.png`

- **Question:** When does the water arrive, and how variable is it?
- **Story:** Nebraska is drier in every month. Illinois and Iowa carry more
  summer rain, and 2024 stands out as the wet season. Monthly shape is otherwise
  similar across growers.
- **Caveat:** daily sums from a coarse grid, not gauge data.
- **Inputs:** weather tables.

### A3 — `tables/weather_analysis.csv`

- **Content:** variance shares for seasonal precipitation and GDD (between
  growers, between years within growers, within grower-years), per-grower means,
  within-grower field standard deviation, and the Spearman coupling between
  seasonal GDD and precipitation across grower-years.
- **Story:** growing-season heat is mostly a grower property (about three
  quarters of the GDD variance sits between growers), while precipitation is
  mostly year-to-year (about four fifths) with a smaller, consistent grower
  offset. In both cases the within-grower-year share is only 2–3%, so weather
  cannot rank fields inside a grower. The honest conclusion is the null result.
- **Caveat:** three growers and fifteen grower-years. Descriptive decomposition,
  no field-level inference.

### M3 — `maps/03_weather_precip.png`

- **Question:** Does within-grower weather actually vary in space?
- **Story:** visibly not. Fields inside a grower share one colour band; the
  contrast is between growers. This is the spatial evidence for A3's null result.
- **Caveat:** shared colour scale across growers; the map would look dramatic on
  a per-grower scale, which is exactly why the scale is shared.
- **Inputs:** weather tables, boundary files.
