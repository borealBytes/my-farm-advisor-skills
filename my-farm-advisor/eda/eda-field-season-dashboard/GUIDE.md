---
name: eda-field-season-dashboard
description: Generate a single aligned field-season dashboard combining Sentinel NDVI, daily weather, and CDL crop-year data for one field and one growing season. Outputs a 4-panel PNG with shared date axis.
version: 1.0.0
author: Boreal Bytes
tags: [eda, dashboard, ndvi, weather, gdd, sentinel, cdl]
---

# Workflow: eda-field-season-dashboard

## Description

Produces a single aligned dashboard image for one field and one growing season. Four panels share a common date axis:

1. **NDVI** — mean Sentinel NDVI per scene date
2. **Precipitation** — daily rainfall with heavy-event highlighting
3. **Temperature / Extremes** — daily min, mean, max with hot/cold annotations
4. **Cumulative GDD** — growing degree days from April 1 with soybean stage reference lines

Notable events (rapid greening, heat spikes, heavy rain, NDVI peak, senescence) are detected automatically and annotated directly on the panels.

## When to Use This Workflow

- **Field-season review**: Inspect one field's growing season at a glance
- **Crop year comparison**: Run multiple times on different years to compare
- **NDVI validation**: Confirm NDVI timing aligns with weather events and crop stage expectations
- **Report inclusion**: Single-figure summary for presentations or dashboards

## Usage

```bash
python src/field_season_dashboard.py \
  --grower-slug ia-grower \
  --farm-slug ia-grower-iowa \
  --field-id osm-1360316062 \
  --year 2023 \
  --output-dir /path/to/output
```

### Prototype

The prototype field-year is:

| Property | Value |
|----------|-------|
| Grower | `ia-grower` (Iowa, Kossuth County) |
| Farm | `ia-grower-iowa` |
| Field | `osm-1360316062` |
| Year | 2023 |
| CDL crop | Soybeans (95.5% of field) |
| Sentinel scenes | 9 (Mar 20 – Nov 30, avg 1.6% cloud) |

```bash
python src/field_season_dashboard.py --grower-slug ia-grower --farm-slug ia-grower-iowa --field-id osm-1360316062 --year 2023
```

Without `--output-dir`, the script writes to the runtime EDA output directory.

## Output

A single PNG file named `{field_id}_{year}_season_dashboard.png` with four aligned panels and embedded annotations.

## Data Sources

- **Field boundary**: `growers/{grower}/farms/{farm}/fields/{field}/boundary/field_boundary.geojson`
- **Sentinel NDVI**: `growers/{grower}/farms/{farm}/fields/{field}/satellite/sentinel/manifest.json` + per-scene NDVI TIFs
- **Weather**: `growers/{grower}/farms/{farm}/fields/{field}/weather/daily_weather.csv`
- **CDL**: `growers/{grower}/farms/{farm}/derived/tables/{prefix}_cdl_2021_2025_full_composition.csv`

## Event Detection

| Event | Method | Panel annotated |
|-------|--------|-----------------|
| Rapid greening | NDVI increase >0.15 between scenes | NDVI |
| Peak NDVI | Maximum scene NDVI value | NDVI |
| Senescence | NDVI decline >0.1 after peak | NDVI |
| Heavy rain | PRECTOTCORR > 95th percentile | Precipitation |
| Hot day | T2M_MAX > 32°C | Temperature |
| Cool spell | T2M_MAX < 20°C (May–Sep) | Temperature |
| GDD milestone | Cumulative GDA crosses soybean stage threshold | Cumulative GDD |

## Stage Thresholds (Soybeans, from strategy guides)

| Stage | Code | Cumulative GDD (base 10°C) |
|-------|------|---------------------------|
| Emergence | VE | ~125 |
| Beginning flower | R1 | ~700–900 |
| Beginning seed | R5 | ~1300–1500 |
| Beginning maturity | R7 | ~2100–2300 |

## Prerequisites

```bash
pip install pandas numpy matplotlib seaborn geopandas rasterio
```

## Resources

- [Matplotlib Documentation](https://matplotlib.org/stable/contents.html)
- [USDA Modified GDD Formula](https://www.nass.usda.gov/Education_and_Outreach/Understanding_Statistics/Definitions/Growing_Degree_Days.pdf)
- [NASA POWER](https://power.larc.nasa.gov/)
- [Sentinel-2](https://sentinel.esa.int/web/sentinel/missions/sentinel-2)
