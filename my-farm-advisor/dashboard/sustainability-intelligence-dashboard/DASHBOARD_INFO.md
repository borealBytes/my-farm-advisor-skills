# Sustainability Intelligence Dashboard — Project Information

## Project Overview

This dashboard analyzes the relationship between **soil health** and **long-term yield stability** across a 10-field Iowa row-crop farming operation. Using publicly available datasets, it demonstrates that fields with stronger soil health characteristics exhibit higher mean NDVI — a remote-sensing proxy for productivity — while also revealing how weather stress can override the soil buffer in individual years.

### Analytical Narrative

**"Soil Health as a Foundation for Productivity, with Weather as a Modulator"**

Healthy soils provide the foundation for consistent crop productivity. Fields with higher organic matter, better water storage capacity, and balanced fertility generally support stronger vegetation vigor (NDVI) because healthy soil improves nutrient availability, water holding capacity, and root development.

This dashboard tests that relationship using 5 years (2021–2025) of Sentinel-2 NDVI composites, SSURGO soil profiles, and NASA POWER weather data. All 10 farm fields are included in the soil health, weather, and geospatial analysis; 5 of the 10 fields have sufficient cloud-free Sentinel-2 coverage to produce NDVI composites and are included in the vegetation stability charts.

---

## Dataset Descriptions

### 1. SSURGO Soil Data (NRCS Web Soil Survey)
- **Source**: USDA NRCS Soil Survey Geographic Database
- **Resolution**: Field-level aggregated by map unit component
- **Properties used**: Organic matter (%), pH, available water storage (inches), cation exchange capacity (CEC), clay content (%), drainage class
- **Coverage**: All 10 fields

### 2. Sentinel-2 NDVI Composites
- **Source**: ESA Sentinel-2 L2A (via Microsoft Planetary Computer)
- **Processing**: Cloud-masked, crop-conditioned using CDL masks, mean-composited per growing season
- **Resolution**: 10m (Sentinel-2 native)
- **Coverage**: 5 of 10 fields (2021–2025)
- **Missing**: 5 fields lacked sufficient cloud-free satellite scene coverage for composite generation

### 3. NASA POWER Weather Data
- **Source**: NASA Prediction of Worldwide Energy Resources (POWER)
- **Variables**: Daily temperature (T2M, T2M_MAX, T2M_MIN), precipitation (PRECTOTCORR), solar radiation, humidity, wind
- **Coverage**: 10 fields × 2021–2025 (daily)
- **Derived metrics**: Growing Degree Days (base 10°C), growing-season precipitation totals

### 4. Cropland Data Layer (CDL)
- **Source**: USDA NASS
- **Use**: Crop masking for NDVI composites (corn vs. soybeans)
- **Coverage**: 2021–2025 field-level crop history

### 5. SoilGrids (Attempted)
- **Source**: ISRIC World Soil Information
- **Status**: Integration attempted via COG VRT access; API service currently paused and direct COG download exceeded project time constraints
- **Plan**: Future integration for global validation layer

---

## Dashboard Explanation

### Layout
- **Header**: Farm name, analysis period, total field count, and KPI cards
- **Hero Map (left panel)**: Interactive Folium map with layer control, field boundaries colored by SHI, NDVI markers, and a field-level drainage class layer
- **Year Explorer**: Interactive year selector showing field-level NDVI and weather anomalies
- **Right Sidebar**: Plotly chart carousel, KPI summary, and methodology note
- **Executive Summary**: Natural-language interpretation of the findings

### How to Read Each Section

#### Map
- **Green boundaries**: High SHI (≥70) — healthiest soils
- **Yellow boundaries**: Moderate SHI (50–70)
- **Orange boundaries**: Low SHI (30–50)
- **Red boundaries**: Very low SHI (<30) — priority for management
- Toggle the drainage class layer to see why a field scores low
- Toggle NDVI markers to see average NDVI by field (larger/greener circles = higher NDVI)

#### Scatter Plot: SHI vs NDVI-CV
- **X-axis**: Soil Health Index (0–100)
- **Y-axis**: NDVI Coefficient of Variation (lower = more stable)
- **Trend line**: Red dashed OLS regression
- **Interpretation**: Only the 5 fields with NDVI are shown. Points in the upper-right are healthy but more variable; points in the lower-right are healthy and stable.

#### SHI Component Heatmap
- Rows = fields (all 10)
- Columns = OM, AWS, CEC, pH, Clay scores
- Color scale = red (low) → yellow → green (high)
- Use this to identify which specific soil properties drive a field's SHI score

#### Soil Property Boxplot
- Distributions of key soil properties across all 10 fields
- Hover points to see individual field values
- Useful for comparing soil variability across the farm

#### Climatology Strip
- **Bars**: Growing-season precipitation anomaly vs. 5-year average
- **Line**: Growing Degree Day anomaly
- **Context**: 2022–2023 were severe drought years; 2024 was excess moisture. This helps explain NDVI dips.

#### NDVI Trajectories
- Line chart showing mean NDVI per field across 2021–2025 (5 fields only)
- Identifies which fields maintained consistent productivity vs. those with high inter-annual volatility

---

## Analytical Interpretation

### Key Findings

1. **SHI Range**: The 10 fields span a wide soil health gradient (SHI 7.7 to 68.4). The lowest-scoring field (Field 9, SHI 7.7) is characterized by low OM (3.1%), low AWS (2.3 in), and somewhat poorly drained Spillville soil. The highest (Field 10, SHI 68.4) has high OM (5.3%), moderate AWS, and poorly drained Webster soil.

2. **Drainage Pattern**: Most fields (9 of 10) are poorly drained Webster soils, receiving a -10 drainage penalty. Field 9 is the only somewhat poorly drained Spillville unit (-5 penalty), which partially offsets its very low OM and AWS scores. Drainage is therefore not a major differentiator across the farm, but it is a consistent wetness constraint.

3. **NDVI Coverage and Productivity**: Among the 5 fields with NDVI composites, the highest-SHI field (Field 10, SHI 68.4) also has the highest mean NDVI (0.397), while the lowest-SHI field with NDVI (Field 9, SHI 7.7) has the lowest mean NDVI (0.348). This supports the expected pattern that healthier soils underpin stronger vegetation signals.

4. **NDVI Stability**: Field 9 (CV = 0.135, PSI = 88.1) is the most stable NDVI field despite having the lowest SHI. This counterintuitive result may reflect the field's small size (25 acres), uniform management, and a stable baseline that does not vary much year-to-year. Field 10 (CV = 0.229) shows the greatest inter-annual variability, possibly because its larger area (197 acres) and stronger soil response amplify the effects of favorable and stressful years.

5. **Correlation**: The Spearman correlation between SHI and NDVI-CV among the 5 NDVI fields is strongly positive (r ≈ 0.90, p ≈ 0.04), indicating that higher-SHI fields are associated with greater NDVI variability in this dataset. The dominant effect of the 2022–2023 drought years likely overwhelmed the soil buffer, causing even high-SHI fields to drop sharply while low-SHI fields stabilized near a lower baseline.

6. **Weather Context**: 2022 and 2023 were severe drought years (-23.7% and -24.9% precipitation anomaly). 2024 was an excess-moisture year (+36.9% anomaly). This wide weather swing provides a strong test of soil buffering and explains much of the year-to-year NDVI variation.

### Decisions Informed

- **Field 10** (highest SHI, 197 acres): Maintain current soil health practices; use as a benchmark for the rest of the farm.
- **Field 9** (lowest SHI, 25 acres): Priority for cover crop adoption, organic matter building, and drainage tile investment.
- **Field 8** (SHI 24.5, 40 acres): Second-lowest SHI; candidate for reduced tillage and organic matter management.
- **Fields without NDVI** (5 fields): Consider installing yield monitors or prioritizing cloud-free Sentinel-2 composite generation for future analysis so they can be included in productivity comparisons.
- **Whole-farm**: Drought resilience planning should focus on water storage improvements (cover crops, reduced tillage, residue management) given the 2022–2023 experience. Drainage investment should be targeted at the most poorly drained fields to improve trafficability and planting windows.

### Variables Appearing Most Important

1. **Organic Matter (OM)**: The largest single driver of SHI variance; strongly correlated with CEC and AWS in this dataset.
2. **Available Water Storage (AWS)**: A key differentiator between high-SHI and low-SHI fields; critical for drought resilience.
3. **Drainage Class**: Uniformly poor across most fields, so it does not differentiate SHI scores but remains critical for operational planning.
4. **NDVI-CV**: Only available for 5 fields; weather stress in 2022–2023 appears to have overwhelmed the soil buffering effect, producing a positive SHI-CV relationship rather than the expected negative one.

### Limitations

- Partial NDVI coverage (5 of 10 fields)
- Small sample size for NDVI-based correlations (n=5)
- Short time series (5 years, 2 of which were severe drought)
- NDVI is a proxy, not direct yield measurement
- SoilGrids validation layer unavailable
- No ground-truth soil sampling to validate SSURGO
- Weather data is field-level but derived from the same NASA POWER grid point for some nearby fields

---

## Future Enhancements

- Integrate SoilGrids COG data when API performance improves
- Extend time series to 2017+ to capture more weather variability
- Generate NDVI composites for the remaining 5 fields
- Add MODIS NPP as alternative productivity proxy
- Include economic metrics (cost/acre, revenue stability)
- Deploy dashboard to a public URL for stakeholder access
