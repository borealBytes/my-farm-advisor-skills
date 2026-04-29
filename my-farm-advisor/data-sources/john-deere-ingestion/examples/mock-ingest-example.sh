#!/usr/bin/env bash

set -euo pipefail

# Example deterministic mock ingest for CI or local testing.
# No credentials are required.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

if [[ ! -f "./dist/src/cli.js" ]]; then
  npm run build
fi

export JD_DATA_ROOT="${JD_DATA_ROOT:-$PROJECT_DIR/.runtime/example-mock-data}"
export JD_GROWER="${JD_GROWER:-iowa-demo-grower}"
export JD_ENVIRONMENT="${JD_ENVIRONMENT:-sandboxapi}"

# Use MOCK_DRY_RUN=1 to preview without writing files.
MOCK_DRY_RUN="${MOCK_DRY_RUN:-0}"

args=(
  ./dist/src/cli.js
  ingest
  --mock
  --environment "$JD_ENVIRONMENT"
  --data-root "$JD_DATA_ROOT"
  --grower "$JD_GROWER"
)

if [[ "$MOCK_DRY_RUN" == "1" ]]; then
  args+=(--dry-run)
fi

node "${args[@]}"
