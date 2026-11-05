# geoadmin-admin

_Repo-native skill scaffold for shared geoadmin assets._

---

## 📋 Purpose

This workflow owns shared geoadmin data handling for the repository, including canonical Level 0, Level 1, and Level 2 admin roots under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/`.

## 📦 Scope

- Shared geoadmin root discovery
- County/state/country admin layout helpers
- Future standardization and source-vintage metadata work

## 🔗 Integration

- Code lives under `my-farm-advisor/admin/geoadmin-admin/src/`
- Shared outputs live under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/`
- Annual maturity scripts consume this skill through repo-native path helpers and bootstrap code

The default shared-data initializer builds L0/L1/L2 geoadmin payloads before county weather and maturity outputs:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

## Water overlay (`lakes` level) — mandatory on administrative maps

Administrative polygons (TIGER counties, GADM census divisions, Natural Earth
countries) are LAND-only. A choropleth built from them alone renders the Great
Lakes, Lake Winnipeg, Great Slave/Bear and every other big lake as blank holes
that read as missing data.

Rule: any map drawn from geoadmin polygons must overlay
`shared/geoadmin/lakes/lakes.parquet` (Natural Earth 10m lakes, open water
>= 150 km2, computed via equal-area EPSG:6933) ON TOP of the polygon fills.
Build with `download_geoadmin.py --levels lakes`. Label at least the five Great
Lakes italic blue. The reference implementation is
`scripts/render_maturity_maps.py` in a reference project (`research/figures/`
outputs).

## Any-country L1/L2 (`--gadm-iso`)

`download_geoadmin.py --gadm-iso AUS [MEX DEU ...]` builds GADM 4.1 admin
levels for **any ISO3 country** into per-country roots (`l1_states_<iso>`,
`l2_counties_<iso>`) with the same standardized schemas as US/Canada — synthetic
`<ISO3><index>` codes in the FIPS slots, raw `GID_1/GID_2` kept per row — and
merges them into the single combined county-role lookup that weather
aggregation and FIPS-context consumers read. Verified live: `--gadm-iso AUS`
→ 11 states/territories, 568 LGA-level units, combined lookup 4,096 rows.
L0 (all countries) comes from Natural Earth already. GADM Terms of Use: free
to use, cite GADM, no redistribution of the boundary files themselves; Canada
keeps its StatCan PRUID enrichment. One archive download per country (cached,
sha256-journalled in `metadata.json`).
