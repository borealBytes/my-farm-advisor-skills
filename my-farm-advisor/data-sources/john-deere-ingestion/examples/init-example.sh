#!/usr/bin/env bash

set -euo pipefail

# Example OAuth init workflow.
# - Uses env vars by default.
# - Supports optional CLI overrides for one-off runs.
# - Never hardcode real credentials here.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

# Build once before using the dist CLI.
if [[ ! -f "./dist/src/cli.js" ]]; then
  npm run build
fi

# Required unless you pass CLI_CLIENT_ID / CLI_CLIENT_SECRET below.
export JD_CLIENT_ID="${JD_CLIENT_ID:-}"
export JD_CLIENT_SECRET="${JD_CLIENT_SECRET:-}"

# Optional runtime overrides.
export JD_ENVIRONMENT="${JD_ENVIRONMENT:-sandboxapi}"
export JD_REDIRECT_URI="${JD_REDIRECT_URI:-http://localhost:9090/callback}"
export JD_DATA_ROOT="${JD_DATA_ROOT:-$PROJECT_DIR/.runtime/example-init-data}"

# Optional per-invocation overrides. Leave empty to use env vars.
CLI_CLIENT_ID="${CLI_CLIENT_ID:-}"
CLI_CLIENT_SECRET="${CLI_CLIENT_SECRET:-}"
AUTH_CODE="${AUTH_CODE:-}"

args=(
  ./dist/src/cli.js
  init
  --environment "$JD_ENVIRONMENT"
  --redirect-uri "$JD_REDIRECT_URI"
)

if [[ -n "$CLI_CLIENT_ID" ]]; then
  args+=(--client-id "$CLI_CLIENT_ID")
fi

if [[ -n "$CLI_CLIENT_SECRET" ]]; then
  args+=(--client-secret "$CLI_CLIENT_SECRET")
fi

if [[ -n "$AUTH_CODE" ]]; then
  # Headless fallback when you already captured the callback code.
  args+=(--code "$AUTH_CODE")
fi

if [[ -z "$JD_CLIENT_ID" && -z "$CLI_CLIENT_ID" ]]; then
  printf 'Set JD_CLIENT_ID or CLI_CLIENT_ID before running this example.\n' >&2
  exit 1
fi

if [[ -z "$JD_CLIENT_SECRET" && -z "$CLI_CLIENT_SECRET" ]]; then
  printf 'Set JD_CLIENT_SECRET or CLI_CLIENT_SECRET before running this example.\n' >&2
  exit 1
fi

node "${args[@]}"
