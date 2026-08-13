# Sustainability Intelligence Dashboard — Project Information

## Project Overview

This dashboard analyzes the relationship between **soil health** and **long-term yield stability** across a 5-field Iowa row-crop farming operation. All five fields have cloud-free Sentinel-2 NDVI composites, so every field is included in every visualization.

### Analytical Narrative

**"Soil Health as a Foundation for Productivity, with Weather as a Modulator"**

Healthy soils provide the foundation for consistent crop productivity. Fields with higher organic matter, better water storage capacity, and balanced fertility generally support stronger vegetation vigor (NDVI) because healthy soil improves nutrient availability, water holding capacity, and root development.

This dashboard tests that relationship using 5 years (2021–2025) of Sentinel-2 NDVI composites, SSURGO soil profiles, and NASA POWER weather data. Fields without NDVI composites were excluded from this analysis so that every chart and map layer is consistent across the same set of fields.

---

## Dataset Descriptions

### 1. SSURGO Soil Data (NRCS Web Soil Survey)
- **Source**: USDA NRCS Soil Survey Geographic Database
- **Resolution**: Field-level aggregated by map unit component
- **Properties used**: Organic matter (%), pH, available water storage (inches), cation exchange capacity (CEC), clay content (%), drainage class
- **Coverage**: 5 fields (all fields in the dashboard)

### 2. Sentinel-2 NDVI Composites
- **Source**: ESA Sentinel-2 L2A (via Microsoft Planetary Computer)
- **Processing**: Cloud-masked, crop-conditioned using CDL masks, mean-composited per growing season
- **Resolution**: 10m (Sentinel-2 native)
- **Coverage**: 5 of 5 fields (2021–2025)

### 3. NASA POWER Weather Data
- **Source**: NASA Prediction of Worldwide Energy Resources (POWER)
- **Variables**: Daily temperature (T2M, T2M_MAX, T2M_MIN), precipitation (PRECTOTCORR), solar radiation, humidity, wind
- **Coverage**: 5 fields × 2021–2025 (daily)
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
- **Hero Map**: Interactive Folium map with layer control, field boundaries colored by SHI, NDVI markers, and a field-level drainage class layer
- **Year Explorer**: Interactive year selector showing field-level NDVI and weather anomalies
- **Right Sidebar**: Combined Plotly chart, KPI summary, and methodology note
- **Executive Summary**: Natural-language interpretation of the findings

### How to Read Each Section

#### Map
- **Green boundaries**: High SHI (≥70) — healthiest soils
- **Yellow boundaries**: Moderate SHI (50–70)
- **Orange boundaries**: Low SHI (30–50)
- **Red boundaries**: Very low SHI (<30) — priority for management
- Toggle the drainage class layer to see why a field scores low
- Toggle NDVI markers to see average NDVI by field (larger/greener circles = higher NDVI)
- Click **Expand** in the map header to view the map full-screen

#### Combined Chart: Climate, NDVI, and Soil Health Index (2021–2025)
- **Top panel**: Growing-season precipitation anomaly (bars) and GDD anomaly (line), with dominant stress annotations. Drought years appear red/orange; wet years appear green/blue.
- **Bottom panel**: Mean NDVI trajectory for each field (one line per field) and the average SHI reference line (dashed black) scaled to the NDVI axis.
- **Interpretation**: Compare NDVI dips with weather anomalies to see which fields are resilient; compare NDVI levels against the average SHI to see whether soil health translates into greenness.

---

## Analytical Interpretation

### Key Findings

1. **SHI Range**: The 5 fields span a wide soil health gradient (SHI 7.7 to 68.4). The lowest-scoring field (Field 4, SHI 7.7) is characterized by low OM (3.1%), low AWS (2.3 in), and somewhat poorly drained Spillville soil. The highest (Field 5, SHI 68.4) has high OM (5.3%), moderate AWS, and poorly drained Webster soil.

2. **Drainage Pattern**: Four of the five fields are poorly drained Webster soils, receiving a -10 drainage penalty. Field 4 is the only somewhat poorly drained Spillville unit (-5 penalty), which partially offsets its very low OM and AWS scores. Drainage is therefore not a major differentiator across most of the farm, but it is a consistent wetness constraint.

3. **NDVI Coverage and Productivity**: The highest-SHI field (Field 5, SHI 68.4) also has the highest mean NDVI (0.397), while the lowest-SHI field (Field 4, SHI 7.7) has the lowest mean NDVI (0.348). This supports the expected pattern that healthier soils underpin stronger vegetation signals.

4. **NDVI Stability**: Field 4 (CV = 0.135, PSI = 88.1) is the most stable NDVI field despite having the lowest SHI. This counterintuitive result may reflect the field's small size (25 acres), uniform management, and a stable baseline that does not vary much year-to-year. Field 5 (CV = 0.229) shows the greatest inter-annual variability, possibly because its larger area (197 acres) and stronger soil response amplify the effects of favorable and stressful years.

5. **Correlation**: The Spearman correlation between SHI and NDVI-CV is strongly positive (r ≈ 0.90, p ≈ 0.04), indicating that higher-SHI fields are associated with greater NDVI variability in this dataset. The dominant effect of the 2022–2023 drought years likely overwhelmed the soil buffer, causing even high-SHI fields to drop sharply while low-SHI fields stabilized near a lower baseline.

6. **Weather Context**: 2022 and 2023 were severe drought years (-23.7% and -24.9% precipitation anomaly). 2024 was an excess-moisture year (+36.9% anomaly). This wide weather swing provides a strong test of soil buffering and explains much of the year-to-year NDVI variation.

### Decisions Informed

- **Field 5** (highest SHI, 197 acres): Maintain current soil health practices; use as a benchmark for the rest of the farm.
- **Field 4** (lowest SHI, 25 acres): Priority for cover crop adoption, organic matter building, and drainage tile investment.
- **Whole-farm**: Drought resilience planning should focus on water storage improvements (cover crops, reduced tillage, residue management) given the 2022–2023 experience. Drainage investment should be targeted at the most poorly drained fields to improve trafficability and planting windows.

### Variables Appearing Most Important

1. **Organic Matter (OM)**: The largest single driver of SHI variance; strongly correlated with CEC and AWS in this dataset.
2. **Available Water Storage (AWS)**: A key differentiator between high-SHI and low-SHI fields; critical for drought resilience.
3. **Drainage Class**: Poorly drained across most fields, so it does not differentiate SHI scores but remains critical for operational planning.
4. **NDVI-CV**: Weather stress in 2022–2023 appears to have overwhelmed the soil buffering effect, producing a positive SHI-CV relationship rather than the expected negative one.

### Limitations

- Small sample size (n=5)
- Short time series (5 years, 2 of which were severe drought)
- NDVI is a proxy, not direct yield measurement
- SoilGrids validation layer unavailable
- No ground-truth soil sampling to validate SSURGO
- Weather data is field-level but derived from the same NASA POWER grid point for nearby fields

---

## Future Enhancements

- Integrate SoilGrids COG data when API performance improves
- Extend time series to 2017+ to capture more weather variability
- Include economic metrics (cost/acre, revenue stability)
- Deploy dashboard to a public URL for stakeholder access
