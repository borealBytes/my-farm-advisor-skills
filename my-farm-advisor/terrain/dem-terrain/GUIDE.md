
## Global 30 m DEMs — implemented downloader (non-US fields)

`download_dem_terrain.py` now live-downloads the global public-COG adapters
(Copernicus GLO-30, NASADEM, ALOS AW3D30) via
`_download_global_cog_tiles`: 1x1 degree tiles are fetched from their
unauthenticated public HTTPS URLs into
`shared/dem/<adapter_id>/<field_slug>/`, sha256-journaled in
`cog_download_manifest.json` (checksum drift fails closed). The resolver
(`--source-policy auto`) tries candidates in rank order and validates each
against field coverage, so a failed candidate (e.g. an authorized-only
NASADEM COG URL) falls through to the next public source.

This unlocks terrain for every non-US field — the pipeline previously only
downloaded USGS TNM/3DEP (US). Verified 2026-11-02 on Ontario fields:
`copernicus_glo30` selected, tile `Copernicus_DSM_COG_10_N43_00_W081_00_DEM.tif`,
field elevations 327–328 m ASL (expected ~330 m for Waterloo County).
For US fields the resolver still prefers USGS TNM at 1 m as before.

Canadian high-resolution upgrade (not wired): Ontario Imagery-Derived DEM
2 m (Hub item `1ce266ee55c44ffca2d457bc5db13b92`) and NRCan CTR —
candidates when sub-30 m Canadian terrain is needed.
