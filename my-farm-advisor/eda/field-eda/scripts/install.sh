#!/usr/bin/env bash
# Copy this subskill into an installed My Farm Advisor runtime.
#
#   DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime ./scripts/install.sh
#
# The subskill is installed as a sibling of the runtime "src" tree, so a later
# data-pipeline "install.sh --force-refresh" cannot delete it.

set -euo pipefail

SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATA_PIPELINE_DATA_ROOT:?set DATA_PIPELINE_DATA_ROOT to the runtime root (for example ~/my-farm-advisor-runtime)}"

RUNTIME_BASE="${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
DEST="${RUNTIME_BASE}/eda/field-eda"

if [[ ! -d "${RUNTIME_BASE}/growers" ]]; then
  printf 'ERROR: %s does not look like a data-pipeline runtime (missing growers/)\n' "${RUNTIME_BASE}" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  printf 'ERROR: rsync is required to install this subskill\n' >&2
  exit 1
fi

mkdir -p "${DEST}"
rsync -a --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'examples/output' \
  --exclude 'figures' \
  --exclude 'maps' \
  --exclude 'tables' \
  --exclude 'manifest.json' \
  "${SKILL_DIR}/" "${DEST}/"

for relative in \
  src/field_eda/discover.py \
  src/field_eda/metrics.py \
  src/field_eda/style.py \
  src/field_eda/maps.py \
  src/field_eda/context.py \
  src/field_eda/maturity.py \
  src/field_eda/boundaries.py \
  src/field_eda/cdl.py \
  src/field_eda/weather.py \
  src/field_eda/signals.py \
  scripts/run_field_eda.py; do
  if ! cmp -s "${SKILL_DIR}/${relative}" "${DEST}/${relative}"; then
    printf 'ERROR: installed copy differs from source: %s\n' "${relative}" >&2
    exit 1
  fi
done

printf 'Installed field-eda to %s\n' "${DEST}"
printf 'Run: %s/data-pipeline/.venv/bin/python %s/scripts/run_field_eda.py --check-only\n' \
  "${DATA_PIPELINE_DATA_ROOT}" "${DEST}"
