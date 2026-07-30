# Dashboard Info

## 1. Project Overview

### What This Project Does

The field_dashboard.html is a dashboard of a single Illinois field along with key environment indicators which affect crop development, and utimately, yield. The dashboard provides potential sources of reduced yield. The **ndvi-weather-dashboard** skill generates self-contained interactive HTML dashboards
that combine satellite vegetation indices, weather data, and crop modeling metrics for
individual agricultural fields. Two complementary dashboard types are produced:

| Dashboard | Purpose | Format |
|-----------|---------|--------|
| **Yearly dashboard** (`ndvi_weather_dashboard_<year>.html`) | Deep-dive into a single growing season | 4-panel Plotly chart + text summary |
| **Main dashboard** (`field_dashboard.html`) | Multi-year comparison + NDVI timelapse | Table + Leaflet map |

### Study Area

| Property | Value |
|----------|-------|
| **Field** | `osm-1499317763` |
| **Farm** | il-grower-illinois |
| **County** | Iroquois County, Illinois |
| **Coordinates** | 40.508°N, 87.787°W |
| **Size** | 259.5 acres |
| **Dominant soil** | Saybrook silt loam, moderately well drained |
| **Crop rotation** | Corn (2021, 2023, 2025), Soybeans (2022, 2024) |

### Technology Stack

| Component | Technology |
|-----------|-----------|
| **Charts** | Plotly (interactive SVG, CDN-hosted) |
| **Map** | Leaflet + Esri World Imagery satellite tiles |
| **NDVI sources** | Sentinel-2 (10 m), Landsat 8/9 (30 m) |
| **Weather** | NASA POWER (daily, ~1 km grid) |
| **Crop data** | USDA NASS Cropland Data Layer (CDL, 30 m) |
| **Soil data** | USDA NRCS SSURGO |
| **Drought index** | 6-month SPI computed from NASA POWER monthly |
| **Python** | pandas, numpy, plotly, geopandas, rasterio, Pillow |

---

## 2. Dataset Description

### 2.1 NASA POWER (Weather)

**Source**: [NASA POWER](https://power.larc.nasa.gov/) (Prediction Of Worldwide Energy Resources)

**API**: `https://power.larc.nasa.gov/api/temporal/daily/point`

**Variables used**:

| Variable | Description | Unit |
|----------|-------------|------|
| `T2M` | Daily mean temperature at 2 m | °C |
| `T2M_MAX` | Daily maximum temperature at 2 m | °C |
| `T2M_MIN` | Daily minimum temperature at 2 m | °C |
| `PRECTOTCORR` | Daily total precipitation (corrected) | mm |
| `ALLSKY_SFC_SW_DWN` | All-sky surface shortwave downward flux | MJ/m²/day |
| `RH2M` | Relative humidity at 2 m | % |
| `WS10M` | Wind speed at 10 m | m/s |

**Temporal coverage**: 2021-01-01 through 2025-12-31 (daily, 365–366 days per year)

**Spatial resolution**: ~0.5° × 0.625° (~55 km × 55 km at the equator; effectively
a single grid cell for a field this size)

**Update frequency**: Daily, with ~1-week latency

**Long-term data (SPI)**: Monthly PRECTOTCORR from 2000-01 through present, fetched via
`https://power.larc.nasa.gov/api/temporal/monthly/point`

### 2.2 Sentinel-2 (NDVI)

**Source**: [Microsoft Planetary Computer STAC](https://planetarycomputer.microsoft.com/)
(Sentinel-2 Level-2A collection)

**Resolution**: 10 m (red, NIR bands)

**NDVI formula**: `NDVI = (NIR - Red) / (NIR + Red)`

**Scene count**: 43 scenes across 2021–2025 (7–9 per year)

**Seasonal coverage**: March through November

**Cloud filtering**: Scenes with cloud cover > 70% are excluded

### 2.3 Landsat 8/9 (NDVI)

**Source**: Microsoft Planetary Computer STAC (Landsat Collection 2 Level-2)

**Resolution**: 30 m (red, NIR bands)

**NDVI formula**: Same as Sentinel-2

**Scene count**: 44 scenes across 2021–2025 (7–9 per year)

**Combined observations**: 87 total NDVI scenes when Sentinel + Landsat are merged,
providing roughly biweekly coverage during the growing season

### 2.4 Cropland Data Layer (CDL)

**Source**: [USDA NASS Cropland Data Layer](https://www.nass.usda.gov/Research_and_Science/Cropland/Release/)

**Resolution**: 30 m

**Coverage**: 2021–2025, annual

**Purpose**: Identifies planted crop (corn, soybeans) per year per field

**Data access**: GeoTIFF rasters from USDA NASS, clipped to farm boundaries

### 2.5 SSURGO (Soil)

**Source**: [USDA NRCS Soil Survey Geographic Database](https://www.nrcs.usda.gov/resources/data-and-reports/soil-survey-geographic-database-ssurgo)

**Access**: Via USDA SDA (Soil Data Access) API

**Key properties for this field**:

| Property | Value |
|----------|-------|
| Water holding capacity (WHC) | 44.7 mm (1.76 in) |
| Organic matter (topsoil) | 3.63% |
| pH | 6.54 (slightly acidic) |
| CEC | 26.24 meq/100g |
| Clay content | 32.65% |
| Sand content | 12.1% |
| Dominant soil series | Saybrook (fine-silty, mixed, superactive, mesic Aquic Argiudoll) |
| Drainage class | Moderately well drained |
| Erosion risk | Moderate |

### 2.6 Drought Index (SPI)

**Source**: Computed locally from NASA POWER monthly precipitation

**Method**: Standardized Precipitation Index (6-month, April–September window)

**Baseline**: 2000 through year prior to target year

**Category thresholds** (per drought.gov conventions):

| SPI range | Category |
|-----------|----------|
| ≥ 2.0 | W4 - Exceptionally Wet |
| 1.6 to 1.9 | W3 - Extremely Wet |
| 1.3 to 1.5 | W2 - Severely Wet |
| 0.8 to 1.2 | W1 - Moderately Wet |
| 0.5 to 0.7 | W0 - Abnormally Wet |
| –0.5 to 0.5 | Normal |
| –0.7 to –0.5 | D0 - Abnormally Dry |
| –1.2 to –0.8 | D1 - Moderate Drought |
| –1.5 to –1.3 | D2 - Severe Drought |
| –1.9 to –1.6 | D3 - Extreme Drought |
| ≤ –2.0 | D4 - Exceptional Drought |

---

## 3. Dashboard Explanation

### 3.1 Yearly Dashboard (`ndvi_weather_dashboard_<year>.html`)

Opens as a single self-contained HTML file. Layout top to bottom:

```
╔══════════════════════════════════════════════════╗
║  2023 Corn - osm-1499317763                     ║
║  Iroquois, IL · 259.5 ac                        ║
║  [📈 16 satellite scenes] [🌦 NASA POWER] [🌽 CDL] ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  ┌── Panel 1: NDVI ──────────────────────────┐  ║
║  │  Sentinel-2 (green circles + line)         │  ║
║  │  Landsat 8/9 (orange triangles + line)     │  ║
║  │  ⚠️ Key event hover markers on dip/surge   │  ║
║  └────────────────────────────────────────────┘  ║
║                                                  ║
║  ┌── Panel 2: Precipitation ─────────────────┐  ║
║  │  Daily bars (blue), heavy rain (dark blue) │  ║
║  │  Mean line (dashed), ⚠️ hover on events    │  ║
║  └────────────────────────────────────────────┘  ║
║                                                  ║
║  ┌── Panel 3: Temperature ─────────────────┐   ║
║  │  T2M_MAX (red), T2M (dotted),            │  ║
║  │  T2M_MIN (blue with fill)                │  ║
║  │  ⚠️ hover on hot days                     │  ║
║  └────────────────────────────────────────────┘  ║
║                                                  ║
║  ┌── Panel 4: Cumulative GDD ───────────────┐  ║
║  │  Orange curve with daily increment hover   │  ║
║  │  Crop-stage reference lines (VE, V6, etc.) │  ║
║  └────────────────────────────────────────────┘  ║
╠══════════════════════════════════════════════════╣
║  Year Overview                                   ║
║  ┌────────────────────────────────────────────┐  ║
║  │ In 2023, Corn was grown on this field...   │  ║
║  │ Growing season: 662 mm precipitation       │  ║
║  │ Total GDD: 1984 (base 10°C, cap 30°C)     │  ║
║  │ Drought: D4 - Exceptional Drought (-2.31) │  ║
║  └────────────────────────────────────────────┘  ║
║                                                  ║
║  ⚠️ Potential Yield Constraints:                 ║
║  • Low GDD (1984 < 2000)                         ║
║  • Heat stress: 54 days above 30°C              ║
║  • Severe drought (D4) — high water stress risk  ║
║                                                  ║
║  Key Events:                                     ║
║  • Mar 27: Cool period lasting 4 days           ║
║  • Jul 27: Hot day with a high of 37°C          ║
║  • Aug 5: Heavy rainfall of 51 mm               ║
╚══════════════════════════════════════════════════╝
```

#### Chart Interaction

- **Hover** on any panel to see values at that date (all panels sync via shared x-axis)
- **Hover** on event markers to see amber ⚠️ "Key event!" popup
- **Hover** on GDD line to see cumulative total and daily increment
- **Legend** items: click to toggle traces; double-click to isolate
- **Pan/Zoom**: plotly built-in toolbar (zoom, pan, reset axes)

### 3.2 Main Dashboard (`field_dashboard.html`)

```
╔══════════════════════════════════════════════════╗
║  osm-1499317763 · Main Dashboard                 ║
║  Iroquois, 259.5 ac                              ║
║  📅 2021–2025  🔄 Corn→Soybeans→Corn→Soybeans→Corn ║
╠══════════════════════════════════════════════════╣
║  Soil Summary                                    ║
║  ┌──────┬──────┬──────┬──────────┬──────────┐   ║
║  │44.7mm│3.63% │ 6.54 │ Saybrook │Mod. well │   ║
║  │ WHC  │  OM  │  pH  │Dominant  │ drained  │   ║
║  └──────┴──────┴──────┴──────────┴──────────┘   ║
╠══════════════════════════════════════════════════╣
║  Key Environmental Indicators per Year           ║
║  ┌──────────┬──────┬──────┬──────┬──────┬──────┐║
║  │ Metric   │ 2021 │ 2022 │ 2023 │ 2024 │ 2025 │║
║  ├──────────┼──────┼──────┼──────┼──────┼──────┤║
║  │ Crop     │🌽C   │🫘S  │🌽C   │🫘S  │🌽C   │║
║  │ Cum. GDD │ 2013 │ 1985 │ 1984 │ 2153 │ 2115 │║
║  │ >30°C    │  35  │  55  │  54  │  46  │  58  │║
║  │ <10°C    │ 105  │ 119  │ 103  │  94  │ 102  │║
║  │ >44.7mm  │   8  │   2  │   3  │   6  │   3  │║
║  │ Drought  │•0.05 │-1.90 │-2.31 │+0.33 │-0.55 │║
║  │ Peak NDVI│0.846 │0.660 │0.566 │0.624 │0.620 │║
║  └──────────┴──────┴──────┴──────┴──────┴──────┘║
║  Click a year to view detailed dashboard         ║
╠══════════════════════════════════════════════════╣
║  NDVI Timelapse 2021–2025                        ║
║  ┌────────────────────────────────────────────┐  ║
║  │                                            │  ║
║  │  Esri satellite basemap + NDVI overlay     │  ║
║  │  Field boundary outline                    │  ║
║  │  80+ scenes cycling through time           │  ║
║  │                                            │  ║
║  └────────────────────────────────────────────┘  ║
║  [▶ Play] ═══════●═══════════════════ 45 of 80  ║
║  Legend: -0.2 ━━━━━━━━━━━━━━━━━━━ 1.0           ║
║                                                  ║
║  ▸ 2021 (36 events)                              ║
║  ▸ 2022 (55 events)                              ║
║  ▸ 2023 (55 events)                              ║
║  ▸ 2024 (47 events)                              ║
║  ▸ 2025 (59 events)                              ║
╚══════════════════════════════════════════════════╝
```

#### Map Interaction

- **Time slider**: drag to scrub through 87 NDVI scenes (2021–2025)
- **Play button**: auto-advance at 1.2 s per scene
- **Event list**: click any weather event to jump to the nearest NDVI scene
- **Satellite view**: Esri World Imagery basemap with NDVI color overlay
- **NDVI coloring**: RdYlGn colormap (red → yellow → green, range –0.2 to 1.0)

---

## 4. Analytical Interpretation

### 4.1 Growing Degree Days (GDD)

GDD measures thermal time available for crop development. The calculation uses
the Baskerville-Emin method: daily average temperature minus a 10°C base, capped
at 30°C, accumulated from March 1.

| GDD range | Agronomic meaning |
|-----------|-------------------|
| < 2000 | Insufficient for full-season corn maturity (needs ~2500 to R6) |
| 2000–2200 | Marginal for full-season; adequate for shorter-season hybrids |
| 2200–2500 | Adequate for most corn hybrids in central IL |
| > 2500 | Sufficient for full maturity; excess may indicate abnormally warm season |

**Field observations**: 2024 reached 2153 GDD (highest), 2023 reached 1984 GDD
(lowest). The 2022–2023 values fall below 2000, triggering the "Low GDD" yield
constraint. This is significant for corn years (2021, 2023, 2025) where full
maturity requires more thermal time than soybeans.

### 4.2 Heat Stress (Days > 30°C)

Daily maximum temperatures above 30°C during the growing season can cause:

- **Corn**: Reduced pollination success (silks desiccate, pollen viability drops)
  when temps exceed 35°C during the R1 (silking) stage (~1100 GDD, typically July)
- **Soybeans**: Flower abortion and reduced pod set above 35°C during R1–R5

**Threshold**: >40 days above 30°C triggers the "Heat stress" yield constraint.
This is a conservative threshold — even 30–40 hot days can reduce yield potential,
but >40 indicates meaningful stress.

**Field observations**: All years 2022–2025 exceeded 40 hot days. 2025 had the
most (58 days). 2021 was borderline at 35 days. Combined with drought in 2022–2023,
heat stress likely caused significant yield reduction in those corn years.

### 4.3 Cold Stress (Days < 10°C)

Daily maximum temperatures below 10°C mean essentially zero GDD accumulation for
that day. Extended periods of sub-10°C highs in spring delay emergence and early
growth; in autumn they truncate grain fill.

**Threshold**: >110 days triggers the "Not enough heat" constraint. This is typical
for central IL winters (November–March), so the constraint is primarily informative
for comparing year-to-year variation in shoulder-season temperatures.

**Field observations**: Only 2022 exceeded 110 cold days (119). This aligns with
that year's cool spring (late April warm-up).

### 4.4 Drought (6-Month SPI)

The Standardized Precipitation Index measures how observed precipitation deviates
from the long-term average for the April–September growing season window.

| SPI category | Agronomic interpretation |
|--------------|-------------------------|
| Normal (+0.5 to –0.5) | Typical moisture; no drought stress expected |
| D0 (Abnormally Dry) | Minor moisture deficit; watch for developing stress |
| D1 (Moderate Drought) | Some yield loss likely without irrigation |
| D2 (Severe Drought) | Significant yield loss; crop water stress evident |
| D3 (Extreme Drought) | Severe yield loss; crop failure risk high |
| D4 (Exceptional Drought) | Widespread crop failure likely |

**Field observations**: This field experienced D3 (2022) and D4 (2023) drought
conditions — two consecutive years of severe precipitation deficit in the April–
September window. 2024 recovered to near-normal (+0.33). The 2022–2023 drought
period likely had substantial yield impacts on both corn (2023) and soybeans
(2022). The drought SPI explains the lower peak NDVI values in 2022–2023 (0.660,
0.566) compared to 2021 (0.846) and 2024 (0.624).

### 4.5 Early Crop Flooding (April Heavy Rain)

Waterlogged soils in April delay planting, cause seed rot, and can force replanting.
The threshold of 44.7 mm/day equals the field's soil water holding capacity —
precipitation exceeding this in a single day (or two consecutive days) saturates
the root zone.

**Field observations**: No April heavy rain events exceeded the threshold in the
2021–2025 record. This is typical for central Illinois, where spring rains are
frequent but extreme single-day events are rare.

### 4.6 NDVI Trajectory

The NDVI curve over the growing season tells a story of crop establishment,
growth, peak biomass, and senescence:

| Phase | NDVI range | Interpretation |
|-------|-----------|----------------|
| Emergence | < 0.3 | Bare soil or recently emerged crop |
| Vegetative growth | 0.3 → 0.7 | Canopy closure, leaf area expansion |
| Peak biomass | > 0.6 | Full canopy, maximum photosynthetic capacity |
| Senescence | 0.7 → 0.2 | Grain fill complete, leaves senesce |

**Key observation**: 2023 (corn) had an unusually low peak NDVI of 0.566 —
well below the expected 0.8+ for corn at peak biomass. This is consistent with
the D4 exceptional drought limiting canopy development. In contrast, 2021 (also
corn) reached 0.846 with normal moisture.

### 4.7 Combined Interpretation (2021–2025)

| Year | Crop | GDD | Hot days | Drought | Peak NDVI | Overall assessment |
|------|------|-----|----------|---------|-----------|-------------------|
| 2021 | Corn | 2013 | 35 | Normal | 0.846 | Favorable season, adequate moisture |
| 2022 | Soybeans | 1985 | 55 | D3 Extreme | 0.660 | Drought-stressed, reduced canopy |
| 2023 | Corn | 1984 | 54 | D4 Exceptional | 0.566 | Severe drought, major yield reduction |
| 2024 | Soybeans | 2153 | 46 | Normal | 0.624 | Recovery year, adequate GDD |
| 2025 | Corn | 2115 | 58 | D0 | 0.620 | Marginal moisture, high heat stress |

The 2022–2023 drought period is the dominant feature of this 5-year record.
Crop yields were likely significantly below trend in those years. The rotation
pattern (corn → beans → corn → beans → corn) shows that corn in drought years
(2023) suffered more severely than soybeans (2022), as reflected in peak NDVI
values (0.566 vs 0.660).

---

## 5. AI Usage Documentation

### 5.1 Assistive AI Tools Used

This project was developed with assistance from **Opencode** (Anthropic Claude /
DeepSeek models), an interactive CLI coding agent that collaborates on software
engineering tasks.

### 5.2 Scope of AI Assistance

The AI contributed to the following aspects of the project:

| Area | Specific contributions |
|------|----------------------|
| **Code generation** | Writing Plotly chart code, Leaflet map integration, HTML/CSS for dashboard layout |
| **Data processing** | NDVI raster reading (rasterio), zonal statistics, PNG generation from GeoTIFFs |
| **Refactoring** | Migration from matplotlib to Plotly (interactive charts), adding Landsat data alongside Sentinel |
| **Event detection** | Algorithm for heavy rain, heat stress, cool period, NDVI dip/surge detection |
| **Statistical computation** | GDD calculation, 6-month SPI computation from NASA POWER API |
| **Yield constraints** | Logic for threshold-based constraint checking and natural-language summary generation |
| **Documentation** | README.md, this document, code comments, SKILL.md/GUIDE.md updates |
| **Debugging** | Fixing Plotly API issues (opacity property placement, dash syntax, shape options) |
| **Testing** | Output verification, data validation scripts |

### 5.3 Human Decisions

All design decisions and analytical interpretations were made by the human developer:

- **Threshold selection**: 30°C for hot days, 10°C for GDD base, 44.7 mm for
  flood definition, 35°C for heat stress events, 2000 GDD for low-GDD constraint
- **Visual design**: Color schemes, chart layout, legend order, dashboard structure
- **Analytical interpretation**: The narrative in Section 4 of this document,
  connecting SPI values to yield outcomes, comparing NDVI across years
- **Crop-specific logic**: Corn vs. soybean GDD stage references, rotation pattern
  analysis
- **Constraint severity levels**: Which thresholds constitute a "warning" vs.
  "normal" condition
- **Data source selection**: Which satellite sources to include, which weather
  variables to plot, which soil properties to display

### 5.4 Workflow

1. **Human**: Specifies the task (e.g., "add Landsat data to the NDVI plot")
2. **AI**: Writes implementation code, suggests approach
3. **Human**: Reviews output, requests modifications, makes design decisions
4. **AI**: Iterates on feedback, fixes issues
5. **Human**: Final approval and commit

All code was reviewed and tested before being incorporated into the project.
The AI did not autonomously make design decisions, set analytical thresholds,
or interpret results.

### 5.5 Limitations

- AI-generated code was verified by running the dashboard generation and
  inspecting the output HTML in a browser
- AI suggestions for analytical thresholds were compared against published
  agronomic guidelines (University of Illinois Extension, USDA, drought.gov)
- The AI does not have access to real-time data or APIs beyond what the
  developer configured
