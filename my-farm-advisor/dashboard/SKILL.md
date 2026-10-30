---
name: my-farm-advisor-dashboard
description: >
  Generates an interactive Row Crop Intelligence Dashboard using Plotly Dash.
  Combines soil, weather, NDVI, and crop rotation data into a single analytical
  experience for any grower in the My Farm Advisor runtime tree.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# Row Crop Intelligence Dashboard

**Domain:** Agricultural Data Visualization & Analytics  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

## Purpose

Generate a Plotly Dash dashboard that communicates meaningful agricultural insights through data storytelling, geospatial analysis, and environmental interpretation for any grower's farm in the My Farm Advisor runtime.

## Start Here

Open [README.md](README.md) for setup instructions, then run:

```bash
python src/row_crop_dashboard.py
```

## Routing Guidance

- Use this skill when the request is to create or view an integrated farm dashboard combining soil, weather, NDVI, and crop data.
- Route to [src/row_crop_dashboard.py](src/row_crop_dashboard.py) for the main dashboard application.
- Route to [src/dashboard_utils.py](src/dashboard_utils.py) for data loading and metric computation utilities.
