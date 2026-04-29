#!/usr/bin/env bash

set -euo pipefail

# Example incremental sync workflow.
# Requires valid credentials unless you adapt it to mock-mode testing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

if [[ ! -f "./dist/src/cli.js" ]]; then
  npm run build
fi

export JD_CLIENT_ID="${JD_CLIENT_ID:-}"
export JD_CLIENT_SECRET="${JD_CLIENT_SECRET:-}"
export JD_ENVIRONMENT="${JD_ENVIRONMENT:-sandboxapi}"
export JD_DATA_ROOT="${JD_DATA_ROOT:-$PROJECT_DIR/.runtime/example-sync-data}"
export JD_GROWER="${JD_GROWER:-iowa-demo-grower}"

CLI_CLIENT_ID="${CLI_CLIENT_ID:-}"
CLI_CLIENT_SECRET="${CLI_CLIENT_SECRET:-}"
SINCE="${SINCE:-}"
FORCE_SYNC="${FORCE_SYNC:-0}"

args=(
  ./dist/src/cli.js
  sync
  --environment "$JD_ENVIRONMENT"
  --data-root "$JD_DATA_ROOT"
  --grower "$JD_GROWER"
)

if [[ -n "$CLI_CLIENT_ID" ]]; then
  args+=(--client-id "$CLI_CLIENT_ID")
fi

if [[ -n "$CLI_CLIENT_SECRET" ]]; then
  args+=(--client-secret "$CLI_CLIENT_SECRET")
fi

if [[ -n "$SINCE" ]]; then
  args+=(--since "$SINCE")
fi

if [[ "$FORCE_SYNC" == "1" ]]; then
  args+=(--force)
fi

if [[ -z "$JD_CLIENT_ID" && -z "$CLI_CLIENT_ID" ]]; then
  printf 'Set JD_CLIENT_ID or CLI_CLIENT_ID before running sync.\n' >&2
  exit 1
fi

if [[ -z "$JD_CLIENT_SECRET" && -z "$CLI_CLIENT_SECRET" ]]; then
  printf 'Set JD_CLIENT_SECRET or CLI_CLIENT_SECRET before running sync.\n' >&2
  exit 1
fi

node "${args[@]}"
