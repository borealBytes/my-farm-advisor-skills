# Examples

Four reviewed anchor figures, one per workflow family. They are the smallest set
that shows boundary, CDL, and weather output without turning the gallery into the
whole run.

| File | What it shows | Why this one |
| --- | --- | --- |
| [`output/02_boundary_shape.png`](output/02_boundary_shape.png) | Compactness against area, coloured by grower, marker by boundary source | The shape/source confound is the boundary story in one panel |
| [`output/04_cdl_rotation.png`](output/04_cdl_rotation.png) | Field-by-field rotation heatmap, 2019–2023 | The clearest within-field-over-time signal |
| [`output/05_weather_gdd.png`](output/05_weather_gdd.png) | Cumulative GDD per season, faceted by grower | Shows the between-grower heat contrast and small within-grower spread |
| [`output/02_cdl_2023.png`](output/02_cdl_2023.png) | 2023 dominant crop per field, three farm-overview panels | Spatial evidence with one shared categorical legend |

Each PNG has a `.caption.md` sidecar recording its question, story, and caveat.
The remaining figures and every analysis table are runtime-only; regenerate them
with the CLI.

## Regenerate

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/eda/field-eda
./scripts/install.sh
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/scripts/run_field_eda.py"
```

Then copy the four files above from
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-eda/` into `output/`. The
figures are deterministic for unchanged inputs, so a regeneration should produce
the same image.

## Review note

Every committed figure passed the repository five-point vision review in
[`../../../../CONTRIBUTING.md`](../../../../CONTRIBUTING.md) before commit: no empty
panels, legible labels at README size, metre/kilometre axes with north arrow and
scale bar on maps, a categorical palette that matches its legend, and honest
caveats in the caption. The review verdict is recorded in the commit message.
