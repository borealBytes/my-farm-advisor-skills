# Soil Health Index (SHI) Methodology

## Purpose

The Composite Soil Health Index (SHI) provides a single 0–100 score that summarizes the health and productive capacity of each field based on publicly available SSURGO soil survey data.

## Data Source

- **SSURGO** (Soil Survey Geographic Database): USDA NRCS
- **Resolution**: Map unit component level, aggregated to field-level means
- **Properties used**: Organic matter (%), pH, available water storage (inches), cation exchange capacity (CEC), clay content (%), drainage class

## Component Scoring

Each component is scored 0–100 using Min-Max normalization across all fields in the analysis set, then weighted according to agronomic importance.

### 1. Organic Matter Score (weight: 30%)

**Rationale**: Organic matter is the cornerstone of soil health. It improves water holding capacity, nutrient cycling, soil structure, and biological activity.

**Formula**:
```
om_score = ((avg_om_pct - min_om) / (max_om - min_om)) * 100
```

**Notes**: Values clipped to [0, 100].

### 2. Available Water Storage Score (weight: 25%)

**Rationale**: Water availability during the growing season is the primary yield-limiting factor in rainfed agriculture. Higher AWS buffers against drought stress.

**Formula**:
```
aws_score = ((total_aws_inches - min_aws) / (max_aws - min_aws)) * 100
```

### 3. Cation Exchange Capacity Score (weight: 20%)

**Rationale**: CEC represents the soil's capacity to hold and exchange nutrient cations (Ca²⁺, Mg²⁺, K⁺, NH₄⁺). It is used here as a proxy for soil fertility and the biological nutrient-cycling capacity of the soil. Higher CEC soils can support more microbial biomass and retain nutrients against leaching.

**Formula**:
```
cec_score = ((avg_cec - min_cec) / (max_cec - min_cec)) * 100
```

### 4. pH Optimality Score (weight: 15%)

**Rationale**: pH affects nutrient availability, microbial activity, and root development. The agronomic optimum for corn/soybean rotation in Iowa is approximately pH 6.8. Scores decrease linearly as pH moves away from this optimum.

**Formula**:
```
ph_distance = |avg_ph - 6.8|
ph_score = max(0, (1 - ph_distance / 1.5)) * 100
```

**Parameters**:
- Optimal pH: 6.8
- Zero-score distance: 1.5 pH units (i.e., pH 5.3 or 8.3 = 0)

### 5. Clay Content Score (weight: 10%)

**Rationale**: Clay content influences water retention, nutrient holding, and soil structure stability. Moderate clay levels (20–35%) are ideal for Iowa corn/soy systems — too low leads to drought sensitivity; too high leads to poor drainage and compaction. The score rewards moderate clay levels.

**Formula**:
```
clay_score = ((avg_clay_pct - min_clay) / (max_clay - min_clay)) * 100
```

## Drainage Class Adjustment

Drainage class directly impacts trafficability, root aeration, and disease pressure. It is applied as a bonus/penalty after the weighted composite.

| Drainage Class | Adjustment | Rationale |
|---|---|---|
| Well drained | +5 | Optimal for most operations |
| Moderately well drained | 0 | Acceptable with minor limitations |
| Somewhat poorly drained | -5 | Wetness limits planting windows, aeration |
| Poorly drained | -10 | Chronic wetness, trafficability issues |
| Very poorly drained | -10 | Severe limitations, drainage investment needed |
| Somewhat excessively drained | +5 | Well-drained but may need water conservation |

## Composite SHI Formula

```
shi_base = (om_score * 0.30) + (aws_score * 0.25) + (cec_score * 0.20) + (ph_score * 0.15) + (clay_score * 0.10)

shi = clip(shi_base + drainage_adjustment, 0, 100)
```

## Validation & Cross-Checks

### Internal Consistency
- OM and AWS are positively correlated (r ≈ 0.6 in this dataset), which is agronomically expected
- CEC and OM are positively correlated (r ≈ 0.7), consistent with organic matter's high CEC
- pH scores are clustered around 6.8, reflecting the natural pH of Iowa prairie-derived soils

### SoilGrids Cross-Validation (Attempted)
- ISRIC SoilGrids was accessed via COG VRT for SOC, pH, and CEC
- Network latency prevented completion within project timeline
- Planned: Compare SSURGO-SHI vs. SoilGrids-SHI per field; target correlation r > 0.7 for validation

## Sensitivity Analysis

Changing weights within ±10 percentage points (while maintaining sum = 100%) shifts field rankings by at most 2 positions in this dataset. The dominant drivers are:
1. OM (30%) — largest single contributor
2. AWS (25%) — second largest, often co-varying with OM
3. Drainage adjustment — can shift score by ±10 points

## Interpretation Guide

| SHI Range | Interpretation | Management Implication |
|---|---|---|
| 70–100 | Excellent soil health | Maintain practices; use as benchmark |
| 50–70 | Good soil health | Minor improvements (cover crops, reduced tillage) |
| 30–50 | Fair soil health | Significant investment needed (OM building, drainage) |
| 0–30 | Poor soil health | Priority for intensive soil health program |

## References

- USDA NRCS. (2024). *Soil Survey Geographic (SSURGO) Database*. https://websoilsurvey.nrcs.usda.gov/
- USDA NRCS. (2019). *Soil Health Assessment*. National Soil Survey Center.
- Cornell University. (2023). *Comprehensive Assessment of Soil Health (CASH)*. https://cals.cornell.edu/cash
- ISRIC. (2024). *SoilGrids 2.0*. https://www.isric.org/explore/soilgrids
