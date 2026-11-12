# Grower Web Map Examples

No generated map is checked in. The page is a runtime artifact that depends on live
grower data under `DATA_PIPELINE_DATA_ROOT` and fetches Esri tiles in the browser, so
committing it would bake deployment data into the repository.

## Regenerate against a runtime

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/install.sh"
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/scripts/generate_grower_web_map.py"
```

Then open the generated file in a browser:

```text
$DATA_PIPELINE_DATA_ROOT/data-pipeline/growers/<grower>/derived/maps/<grower>_fields_map.html
```

## Expected result

| Grower | Farms | Fields | Area | HTML |
| --- | --- | --- | --- | --- |
| `il-prairie-grower` | 1 | 4 | 223.3 ha | ~15–25 KB |
| `ia-cedar-grower` | 1 | 4 | 170.3 ha | ~15–25 KB |

Each map shows four polygons over World Imagery, a per-farm legend, and a clickable
field list. Clicking a field reports grower, farm, field name, field ID, and hectares.

Hectares come from the boundary file's `area_acres` with
`1 acre = 4046.8564224 m²`, so the values above match 551.9 ac and 420.9 ac.
