# EDA Field Comparison

Cross-field, cross-grower comparison of boundaries, CDL crop history, and NASA POWER weather.

## Prototype Field-Year Selection

For FP3 dashboard prototyping, the following field-year was selected based on data completeness and CDL purity:

| Property | Value |
|----------|-------|
| **Field ID** | `osm-1157043055` |
| **Grower** | `ia-northern-grower` (Iowa) |
| **Year** | `2023` |
| **CDL Crop** | **Soybeans** (100% purity) |
| **Field Size** | ~55 acres |
| **Sentinel Scenes** | 18 (highest coverage among FP1 fields) |
| **Weather** | Complete daily records |
| **NDVI Composite** | Available |

**Rationale:** This field-year offers the cleanest data coverage of all FP1 fields — 100% pure soybean classification, 18 Sentinel scenes for dense NDVI time-series, and complete NASA POWER weather. It is representative of a typical Iowa row-crop field without edge-case complications.

## Multi-Year Path

After the 2023 prototype is validated, the skill will generate plots for all years (2021–2025):

| Year | Crop |
|------|------|
| 2021 | Soybeans |
| 2022 | Corn |
| 2023 | Soybeans (prototype) |
| 2024 | Corn |
| 2025 | Soybeans |

## Outputs

Static PNG plots and CSV tables are written to:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-comparison/
├── plots/
└── tables/
```

## Entrypoint

```bash
python scripts/run_field_comparison.py
```

See [GUIDE.md](GUIDE.md) for full workflow documentation.
