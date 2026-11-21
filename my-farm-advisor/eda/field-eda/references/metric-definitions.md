# Metric Definitions

Authoritative definitions for every derived value the subskill reports. If code
and this file disagree, the file wins and the code is wrong.

## Geometry

All geometry measures are computed on the boundary reprojected to
**EPSG:5070** (CONUS Albers, equal-area, metres). Degrees are never used for
length, area, or compactness.

| Metric | Definition | Reading |
| --- | --- | --- |
| `area_ha` | `geometry.area / 10_000` | hectares |
| `perimeter_m` | `geometry.length` | metres |
| `compactness` | `4πA / P²` | 1.00 circle, 0.785 square, → 0 for elongated shapes |
| `vertices` | exterior coordinate count, summed over parts | tracing complexity proxy |
| `bearing_deg` | bearing of the minimum rotated rectangle's long edge, unwrapped to (−90°, 90°] | 0 = north–south long axis, ±45 = diagonal |
| `source_key` | `csb` for `usda_csb_fiboa`, `osm` for `OpenStreetMap/Overpass`, else `other` | groups provenance |

`area_acres` from the boundary file is retained only for a cross-check against
`area_ha`; it is not used in any analysis.

## Crops (CDL)

Input: `<prefix>_cdl_<start>_<end>_full_composition.csv` with
`field_id, year, crop_code, crop_name, pixel_count, pct, crop_source`.

| Metric | Definition |
| --- | --- |
| `dominant_crop` | crop with the largest `pct` for a field-year |
| `crop_share` | mean `pct` for a crop across years, divided by the field's mean classified total, so displayed shares sum to 100% |
| `corn_after_corn` | count of field-years where `dominant_crop = Corn` and the previous year in the window is also Corn |
| `cac_rate` | `corn_after_corn / corn_field_years_with_previous_year` |
| `shannon_diversity` | `−Σ pᵢ ln pᵢ` over the field's five-year dominant-crop counts |
| `cdl_coverage` | `Σ pixel_count × 900 m² / polygon area` for a field's mean year; 1.0 means the polygon is fully classified |
| `min_pixels` | smallest field-year pixel count in the input, quoted in captions |
| `longest_corn_run` | longest sequence of adjacent field-years with `dominant_crop = Corn`; a missing CDL year breaks the run |
| `current_corn_run` | length of the corn run ending at the field's last CDL year |

Pixel area is 900 m² (30 m CDL). Percentages are quantised: a single pixel in a
14-pixel field is 7 percentage points.

## Weather (NASA POWER)

Input: `<prefix>_weather_<start>_<end>.csv` with daily
`field_id, lat, lon, date, T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, …`.

| Metric | Definition |
| --- | --- |
| `gdd` | `max((T2M_MAX + T2M_MIN) / 2 − 10, 0)`, summed daily; base 10 °C, no upper cap |
| `precip_mm` | `Σ PRECTOTCORR` over the window |
| `heat_days` | count of days with `T2M_MAX > 35 °C` |
| `season` | April 1 – September 30 by default (`--season-start-month`, `--season-end-month`) |
| `grid_cells` | distinct `(round(lat / 0.5), round(lon / 0.625))` pairs per grower |

Aggregation order is mandatory: **per field, per year first, then across
fields.** Summing a per-field table grouped only by grower multiplies
precipitation by the number of fields.

NASA POWER is gridded. Fields in the same cell receive identical values, so a
within-grower field comparison measures the grid, not the farm.

## Maturity fit (county maturity product)

Input: `shared/corn_maturity/tables/rm_by_fips_<year>.parquet`,
`shared/corn_maturity/tables/rm_by_fips_<start>_<end>_average.parquet`, and
`shared/soybean_maturity/tables/mg_by_fips_<start>_<end>_average.parquet`.

The county FIPS comes from the field boundary's own `state_fips` and
`county_fips` attributes; a farm that spans counties is rejected.

| Metric | Definition |
| --- | --- |
| `gdd_maturity` | full calendar year `max((min(T2M_MAX, 30) + max(T2M_MIN, 10)) / 2 − 10, 0)`, summed daily |
| `rm_target` | county five-year-average `rm_relative_maturity` for the weather window |
| `gdd_required_c` | `rm_target × 20`, the maturity product's own GDD-per-RM rule |
| `shortfall_c` | `max(gdd_required_c − gdd_maturity, 0)` |
| `rm_shortfall` | `shortfall_c / 20` |
| `season_below_target` | a grower-year whose mean `gdd_maturity` across the grower's fields is below `gdd_required_c` |
| `mean_gdd_gap_c` | mean of `gdd_maturity − gdd_required_c`; negative means cooler than the county reference |
| `soybean_mg` | county `mg_optimal`, a latitude regression; reference only, no heat test |

`gdd_maturity` is **not** the weather category's `gdd`. The weather category uses
April–September with no cap; maturity fit uses the whole calendar year with a
30 °C cap, matching `maturity_by_fips.compute_county_gdd`. Subtracting one from
the other would produce a shortfall that is really a window and cap difference.

The county target is a county-average planning value built from the county
weather table, not from the fields in this run. A level offset is therefore
location, and the result is reported per grower, never as a field ranking.

## Weather risk windows

Within the configured season window, per field-year:

| Metric | Definition |
| --- | --- |
| `dry_spell_days` | longest run of adjacent days with `PRECTOTCORR < 1.0 mm` |
| `july_heat_days` | July days with `T2M_MAX > 35 °C` |
| `jul_aug_precip_mm` | `Σ PRECTOTCORR` over July and August |

## Statistics

| Measure | Definition |
| --- | --- |
| Spearman ρ | rank correlation; two-sided p from `scipy.stats.spearmanr` |
| Spearman interval | 2.5–97.5 percentile of 2,000 seeded bootstrap resamples |
| Mann–Whitney | `scipy.stats.mannwhitneyu`, two-sided; effect size = rank-biserial `2U/(n₁n₂) − 1` |
| Wilson interval | 95% score interval for a proportion, used for corn-after-corn rates |
| Chi-square | `scipy.stats.chi2_contingency` on crop class × grower counts |
| Cramér's V | `sqrt(χ² / (n · (min(r, c) − 1)))` |
| Variance shares | sum-of-squares decomposition of a field-year value: between grower, between year within grower, within grower-year; reported as percentages of total SS |

Sample sizes are always reported: 30 fields across three growers, 15 grower-years
for weather, 150 field-years for crops, and 150 field-years for maturity fit.
These support effect sizes, not population inference.
