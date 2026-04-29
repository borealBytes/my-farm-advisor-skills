#!/usr/bin/env bash

set -euo pipefail

# Example local webhook receiver usage.
# Default mode is dry-run so the example is safe in CI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

if [[ ! -f "./dist/src/cli.js" ]]; then
  npm run build
fi

export JD_DATA_ROOT="${JD_DATA_ROOT:-$PROJECT_DIR/.runtime/example-webhook-data}"
export JD_GROWER="${JD_GROWER:-iowa-demo-grower}"
WEBHOOK_PORT="${WEBHOOK_PORT:-9091}"
WEBHOOK_DRY_RUN="${WEBHOOK_DRY_RUN:-1}"

args=(
  ./dist/src/cli.js
  webhook
  --data-root "$JD_DATA_ROOT"
  --grower "$JD_GROWER"
  --port "$WEBHOOK_PORT"
)

if [[ "$WEBHOOK_DRY_RUN" == "1" ]]; then
  args+=(--dry-run)
fi

node "${args[@]}"
