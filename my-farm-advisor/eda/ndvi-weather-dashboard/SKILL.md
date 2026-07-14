---
name: ndvi-weather-dashboard
description: Generate a self-contained HTML dashboard combining Sentinel NDVI time series, daily weather, and cumulative GDD for a single field-year. Detects notable events (heavy rain, hot days, cool periods, NDVI dips, rapid NDVI increases) and renders them as annotated 4-panel chart with event callout cards.
version: 1.0.0
author: Boreal Bytes
tags: [ndvi, sentinel, weather, gdd, dashboard, visualization, html]
---

# ndvi-weather-dashboard

Generate a self-contained interactive HTML dashboard for any field-year in the data-pipeline runtime. The dashboard combines CDL crop identification, Sentinel-2 NDVI time series, NASA POWER daily weather, and cumulative Growing Degree Days into a single annotated 4-panel figure with event callout cards below.

## Start Here

- [GUIDE.md](GUIDE.md) – usage and command examples
- [AGENTS.md](AGENTS.md) – runtime conventions and local instructions
