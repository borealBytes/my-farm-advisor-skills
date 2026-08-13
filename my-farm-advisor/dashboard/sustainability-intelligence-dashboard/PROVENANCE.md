# Provenance — Sustainability Intelligence Dashboard

## Origin

This skill was created as the final project deliverable for an agricultural data analytics course. It builds on the data pipeline, SSURGO soil workflows, Sentinel-2 NDVI composites, and NASA POWER weather workflows developed in earlier assignments.

## Sources & Dependencies

- **Field boundaries**: OpenStreetMap-derived boundaries processed by the `my-farm-advisor` data pipeline.
- **SSURGO soil data**: USDA NRCS Soil Survey Geographic Database, accessed via the pipeline soil downloader.
- **NDVI composites**: ESA Sentinel-2 L2A imagery processed through the `sentinel2-imagery` skill.
- **Weather data**: NASA POWER daily time series processed by the `nasa-power-weather` skill.
- **CDL crop masks**: USDA NASS Cropland Data Layer used to mask NDVI composites.

## Code & Asset Authorship

- All Python dashboard code in `src/dashboard_builder/app.py` was authored for this project.
- HTML/CSS layout and documentation were authored for this project.
- No third-party skills, proprietary libraries, or copyrighted assets were copied into this folder.
- No large runtime datasets are committed to Git; only skill scripts, documentation, and a `requirements.txt` are tracked.

## External Tools Used

- AI coding assistants were used to draft code, documentation, and layout. See `AI_USAGE.md` for details.

## Date

2025-07-31
