# WorldCereal Reference Data Module (RDM) — the best-available-data ladder

The pipeline classifies crops per field per year with the **default WorldCereal
models** (keyless Planetary Computer — see
[`crop-rotation-sources.md`](crop-rotation-sources.md)). That model is the
*always-available floor*: it runs everywhere, needs no account, and never
fails you. But a global default model is a compromise — its class vocabulary
has no sugarcane, and its optical band is blind where clouds are. Where a
**regional reference** exists, it beats the model. This is the ladder the
pipeline walks, best first:

| Rung | Source | What it gives | Where it wins |
| --- | --- | --- | --- |
| 1 | National official layer (USDA CDL, AAFC ACI, …) | every-field, per-year, authoritative | US + Canada (see routing table) |
| 2 | **WorldCereal RDM** (`ewoc-rdm-api.iiasa.ac.at`) | contributor reference samples/parcels, harmonized to the EWOC legend, per-collection validity years | anywhere a contributor collected — Brazil, Kenya, EU LCU …; names classes the default model lacks (sugarcane, cassava) |
| 3 | **Default model** (`apply_worldcereal.py`) | per-pixel, per-year, every country | the floor — always runs |

**Rung 2 is keyless too.** The RDM API accepts anonymous requests; no CDSE
account, no token. (The *fine-tuned* regional models — also attractive — live
behind the CDSE training hub and an account; the pipeline deliberately does
not depend on them.)

## The API in five calls

```text
Base:   https://ewoc-rdm-api.iiasa.ac.at     (Swagger: /swagger/v1/swagger.json)
Docs:   https://rdm.esa-worldcereal.org      (portal UI + notebooks)

GET /collections                      → all public collections (269 as of 2026-11, anonymous)
GET /collections/{id}/items           → features; filters:
        Bbox=west,south,east,north  (EPSG:4326, array form)
        ValidityTime.Start / ValidityTime.End  (ISO dates)
        EwocCodes=8,16              (comma-separated EWOC class codes)
        SkipCount / MaxResultCount  (paging, page size ≤ 1e6)
Legend: https://auxdata.terrascope.be/worldcereal/legend/WorldCereal_LC_CT_legend_latest.csv
        (EWOC code → human class name; vendored at src/scripts/data/ewoc_legend.csv)
```

Collection IDs encode provenance: `2017_bra_jecamcirad_poly_111` = 2017 ·
Brazil · JECAM-CIRAD contributor · polygon geometry · EWOC level-111
(cropland). Geometry is EPSG:32723-style local UTM per country — reproject
before comparing areas.

## Script: `scripts/ingest/download_rdm_reference.py`

```bash
python scripts/ingest/download_rdm_reference.py \
    --farm demo-br --field br-r2 --start 2016-01-01 --end 2018-12-31
# or against a raw bbox (no registered field):
python scripts/ingest/download_rdm_reference.py --bbox -49.5 -23.5 -46.5 -20.0 --start 2016-01-01
```

Writes, per field: `fields/<slug>/worldcereal_rdm/rdm_<collection>.geojson`
(only features whose `crop_label` names a real crop) plus
`rdm_provenance.json` (collection metadata, counts, legend version). Exit 0
even when no collection covers the field — the ladder just drops to rung 3.

## Verified queries (2026-11-05)

| Region | Collection | What came back |
| --- | --- | --- |
| São Paulo cane belt, BR | `2017_bra_jecamcirad_poly_111` | 1 154 parcels, 184 labeled **sugar_cane** — the class the default model cannot name. `br-r2`'s boundary *is* one of these parcels. |
| Southwestern Ontario, CA | `2017_can_aafccropinventory_point_110` | 14 AAFC ground points (7 soybean, 4 winter wheat, red clover, pasture, fallow) |
| Kenya (ICRISAT) | `2017_ken_icrisat_point_110` | small-holder points (maize-dominant) — demo of data-sparse countries |

## Demo figures (gallery)

* `examples/worldcereal/output/wc_ladder_on.png` — on-r1: the optical model is
  cloud-gapped in-field (2022 tc-s2 **and** tc-s1 radar re-run both ≈0 %
  labeled); the AAFC RDM points name soybean/wheat in the same bbox. Rung 2
  carries what rung 3 cannot see.
* `examples/worldcereal/output/wc_ladder_br.png` — br-r2: the parcel boundary
  itself was harvested from the RDM collection; the default model sees only
  ~30 % labeled pixels and *no cane class at all*, while the reference panel
  labels it red-sugarcane outright.

## Caveats (stated, not hidden)

* **Reference ≠ current.** Most RDM collections are 2017-vintage snapshots;
  they validate *class vocabulary and region*, not the current rotation.
* **Coverage is contributor-shaped.** Brazil/EU dense, Africa sparse, US/CA
  redundant with rungs 1. A field can legitimately get zero hits.
* **Validity years filter by collection**, not per feature — filter on
  `ValidityTime` at request time.
* Cloud-gapped optical years are the *model's* limitation (254 no-data);
  radar (tc-s1) does not fix gaps from persistent cloud fields over Ontario
  (tested 2026-11-05, on-r1 2021/2022 both 0 % labeled). For ON, ACI
  (rung 1) is the answer, not a better sensor pass.
