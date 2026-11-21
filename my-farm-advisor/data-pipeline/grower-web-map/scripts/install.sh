#!/usr/bin/env bash
# Copy this subskill into an installed My Farm Advisor runtime.
#
#   DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime ./scripts/install.sh
#
# The subskill is installed as a sibling of the runtime ""src"" tree, so a later
# data-pipeline ""install.sh --force-refresh"" cannot delete it.

set -euo pipefail

SKILL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATA_PIPELINE_DATA_ROOT:?set DATA_PIPELINE_DATA_ROOT to the runtime root (for example ~/my-farm-advisor-runtime)}"

RUNTIME_BASE="${DATA_PIPELINE_DATA_ROOT}/data-pipeline"
DEST="${RUNTIME_BASE}/grower-web-map"

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
  "${SKILL_DIR}/" "${DEST}/"

for relative in src/grower_web_map.py scripts/generate_grower_web_map.py SKILL.md; do
  if ! cmp -s "${SKILL_DIR}/${relative}" "${DEST}/${relative}"; then
    printf 'ERROR: installed copy differs from checkout: %s\n' "${relative}" >&2
    exit 1
  fi
done

VENV_PY="${DATA_PIPELINE_VENV_DIR:-${RUNTIME_BASE}/.venv}/bin/python"
if [[ -x "${VENV_PY}" ]]; then
  RUNNER="${VENV_PY}"
else
  RUNNER="python3"
fi

printf 'Installed grower-web-map -> %s\n' "${DEST}"
printf 'Verified byte-identical: src/grower_web_map.py, scripts/generate_grower_web_map.py, SKILL.md\n\n'
printf 'Render every grower:\n'
printf '  DATA_PIPELINE_DATA_ROOT=%q %q %q\n' \
  "${DATA_PIPELINE_DATA_ROOT}" "${RUNNER}" "${DEST}/scripts/generate_grower_web_map.py"
printf 'Render one grower:\n'
printf '  DATA_PIPELINE_DATA_ROOT=%q %q %q --grower-slug <grower-slug>\n' \
  "${DATA_PIPELINE_DATA_ROOT}" "${RUNNER}" "${DEST}/scripts/generate_grower_web_map.py"
