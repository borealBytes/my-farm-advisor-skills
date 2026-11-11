# Satellite basemap underlay (contract, 2026-11-09)

Every field map in the pipeline renders over keyless satellite imagery —
the style first shipped in the SSURGO admin map and adopted by the user for
**all** figures: nodata corners read as farm scenery, never as a gray void.

| Item | Value |
|---|---|
| Tiles | Esri World Imagery (`server.arcgisonline.com/.../World_Imagery/MapServer/tile/{z}/{y}/{x}`) — anonymous, no account, no key |
| Fetcher | `lib/basemap.py` → `contextily.tile.bounds2raster` (bbox in WGS84, mosaic in EPSG:3857) |
| Registration | mosaic warped in ONE resample (rotated rasterio `Affine`) into the same field-local frame the data panels use — pixel-registered at any rotation, no ctx axis tricks |
| Zoom | `round(log2(156543.03·cosφ / target_res))`, clamped 3–17; default target 8 m/px |
| Draw order | basemap zorder −10 FIRST, data on top; soil/class fills at `alpha 0.82–0.88` so scenery shows through |
| Extent | the full panel viewport (polygon + 15 % under the 2026-11-09 policy), so the ring between the 10 % raster halo and the viewport edge is imagery, not white |
| Failure mode | any error (offline, tile outage) → no-op, figure renders on plain background; set `AG_BASEMAP_DEBUG=1` to raise |
| Attribution | `Imagery © Esri` bottom-left, 4.6 pt — drawn by `basemap.attribution` wherever draw() succeeded |

Rules for new renderers: call `basemap.draw(ax, frame, ext, ny, nx)` BEFORE
the first data layer of each panel (ext = that panel's final viewport
extent; ny/nx = data array shape so grids share resolution); then plot data
with an alpha < 1 where a data-on-imagery blend is wanted (continuous
rasters: 0.82–0.88; class/derived rasters may stay opaque so imagery shows
only in nodata). `generate_ssurgo_maps.py` predates the module and uses
`ctx.add_basemap` directly on geo axes — equivalent output; new rotated
panels must use `lib/basemap.py`.
