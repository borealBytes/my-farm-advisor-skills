# Grower Web Map Examples

Generate interactive HTML maps from data-pipeline field boundaries.

## Illinois Grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python ../scripts/generate_map.py --grower-slug il-grower
```

Output: `growers/il-grower/farms/il-grower-illinois/derived/reports/il-grower_illinois_web_map.html`

## Iowa Grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python ../scripts/generate_map.py --grower-slug ia-grower
```

Output: `growers/ia-grower/farms/ia-grower-iowa/derived/reports/ia-grower_iowa_web_map.html`

## Explicit Farm Slug

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python ../scripts/generate_map.py --grower-slug il-grower --farm-slug il-grower-illinois
```
