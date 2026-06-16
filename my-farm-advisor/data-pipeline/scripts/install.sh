#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_PIPELINE_DATA_ROOT:-}"
PERSIST_MODE="user"
NON_INTERACTIVE=0
FORCE_REFRESH=0
DRY_RUN=0
INSTALL_DEPS=1
PREPARE_SHARED_DATA=0
PREPARE_SHARED_MATURITY=0
MATURITY_START_YEAR=2021
MATURITY_END_YEAR=2025
MATURITY_COVERAGE="lower48"
MATURITY_WEATHER_BACKEND="zarr"
MATURITY_WEATHER_TIME_STANDARD="lst"
FORCE_SHARED_MATURITY=0
CDL_SCOPE="conus"
CDL_STATE_FIPS=""
CDL_LATEST_YEAR=2025
CDL_WINDOW_YEARS=5
SEED_GROWER_SLUG=""
SEED_FARM_SLUG=""
SEED_FARM_NAME=""
SEED_STATE=""
SEED_FIELD_COUNT=""
SEED_CROP="corn"
SEED_RANDOM_SEED=42
SEED_FORCE=0
SEED_FARM=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Prepare the My Farm Advisor data-pipeline runtime tree.

Options:
  --data-root <abs-path>     Runtime data root. Overrides DATA_PIPELINE_DATA_ROOT.
                             The value must be an absolute path; paths with spaces
                             are supported when shell-quoted by the caller.
  --persist user|none        Persistence mode. Defaults to user.
                             user writes or updates:
                               ${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf
                             none skips persistence.
  --non-interactive          Never prompt. Non-interactive mode is also selected
                             when stdin is not a TTY or CI is set.
  --force-refresh            Permit non-interactive replacement of a divergent
                             runtime source tree.
  --dry-run                  Print planned actions without mutating files.
  --no-install-deps          Skip virtualenv/dependency installation.
  --prepare-shared-data      Build shared geoadmin L0/L1/L2, lower48 county
                             weather, corn RM, soybean MG, and last-five-year
                             CDL rasters after runtime install.
  --prepare-shared-maturity  Build shared lower48 county weather, corn RM, and
                             soybean MG outputs after runtime install.
  --maturity-start-year <y>  First shared maturity year. Defaults to 2021.
  --maturity-end-year <y>    Last shared maturity year. Defaults to 2025.
  --maturity-coverage <mode> Shared maturity coverage: lower48 or
                             traditional-corn-belt. Defaults to lower48.
  --maturity-weather-backend <mode>
                             Shared maturity weather backend: zarr or api.
                             Defaults to zarr.
  --maturity-weather-time-standard <mode>
                             Shared maturity weather time standard: lst or utc.
                             Defaults to lst.
  --force-shared-maturity    Rebuild maturity outputs even if files exist.
                             Also applies to --prepare-shared-data.
  --cdl-scope <mode>         Shared CDL raster scope for --prepare-shared-data:
                             conus or state. Defaults to conus.
  --cdl-state-fips <codes>   Comma-separated state FIPS when --cdl-scope state.
  --cdl-latest-year <y>      Latest CDL candidate year. Defaults to 2025.
  --cdl-window-years <n>     Number of available CDL years. Defaults to 5.
  --seed-grower-slug <slug>  Seed a grower/farm after install.
  --seed-farm-slug <slug>    Optional seeded farm slug. Defaults from grower/state.
  --seed-farm-name <name>    Optional seeded farm display name.
  --seed-state <state>       Seed state name, abbreviation, or FIPS.
  --seed-field-count <n>     Number of OSM fields to seed.
  --seed-crop <crop>         Top-crop county selector crop. Defaults to corn.
  --seed-random-seed <n>     Deterministic field sampling seed. Defaults to 42.
  --seed-force               Force the seeded farm pipeline rerun.
  -h, --help                 Show this help and exit.

Environment:
  DATA_PIPELINE_DATA_ROOT    Alternative source for --data-root. If neither
                             --data-root nor this variable is set, the installer
                             exits nonzero before mutation, especially in
                             --non-interactive or CI contexts. No implicit data
                             root is chosen.
  XDG_CONFIG_HOME, HOME      Determine the user-level persistence location when
                             --persist user is active:
                               ${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf
  DATA_PIPELINE_VENV_DIR     Optional virtualenv override. When set, it must be
                             an absolute path. Existing non-directory paths fail
                             before dependency installation. Defaults to:
                               ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv
  CI                         When set, disables interactive prompts unless the
                             caller explicitly runs in an interactive terminal
                             without --non-interactive.

Runtime data-root validation contract:
  - The data root must be absolute.
  - If the root does not exist, the installer creates it only when its parent is
    writable.
  - An existing file path fails.
  - An unwritable root fails before any copy or dependency installation.
  - Symlink roots are resolved consistently with realpath, or pwd -P where
    realpath is unavailable.

Interactivity contract:
  - Interactive mode means stdin is a TTY, CI is unset, and --non-interactive was
    not passed.
  - Missing --data-root/DATA_PIPELINE_DATA_ROOT in non-interactive mode exits
    nonzero before mutation.

Runtime source refresh contract:
  - Identical runtime source: no-op.
  - Divergent runtime source in interactive mode: prompt exactly refresh/skip/abort.
  - Divergent runtime source in non-interactive mode: fail unless --force-refresh
    is passed.

Persistence and current-shell contract:
  - --persist user writes or updates only the user-level environment.d file shown
    above; system-wide persistence is not supported by this installer.
  - Persistence does not mutate the already-running parent shell.
  - After resolving the data root, the installer prints this exact current-shell
    command for the caller to run if needed:
      export DATA_PIPELINE_DATA_ROOT=<resolved-data-root>
EOF
}

die() {
  echo "[install] $*" >&2
  exit 2
}

log() {
  echo "[install] $*" >&2
}

shell_quote() {
  printf '%q' "$1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --data-root)
      [[ $# -ge 2 ]] || die "--data-root requires an absolute path argument"
      DATA_ROOT="$2"
      shift 2
      ;;
    --persist)
      [[ $# -ge 2 ]] || die "--persist requires user or none"
      case "$2" in
        user|none) PERSIST_MODE="$2" ;;
        *) die "--persist must be user or none" ;;
      esac
      shift 2
      ;;
    --non-interactive)
      NON_INTERACTIVE=1
      shift
      ;;
    --force-refresh)
      FORCE_REFRESH=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-install-deps)
      INSTALL_DEPS=0
      shift
      ;;
    --prepare-shared-data)
      PREPARE_SHARED_DATA=1
      shift
      ;;
    --prepare-shared-maturity)
      PREPARE_SHARED_MATURITY=1
      shift
      ;;
    --maturity-start-year)
      [[ $# -ge 2 ]] || die "--maturity-start-year requires a year"
      MATURITY_START_YEAR="$2"
      shift 2
      ;;
    --maturity-end-year)
      [[ $# -ge 2 ]] || die "--maturity-end-year requires a year"
      MATURITY_END_YEAR="$2"
      shift 2
      ;;
    --maturity-coverage)
      [[ $# -ge 2 ]] || die "--maturity-coverage requires lower48 or traditional-corn-belt"
      case "$2" in
        lower48|traditional-corn-belt) MATURITY_COVERAGE="$2" ;;
        *) die "--maturity-coverage must be lower48 or traditional-corn-belt" ;;
      esac
      shift 2
      ;;
    --maturity-weather-backend)
      [[ $# -ge 2 ]] || die "--maturity-weather-backend requires zarr or api"
      case "$2" in
        zarr|api) MATURITY_WEATHER_BACKEND="$2" ;;
        *) die "--maturity-weather-backend must be zarr or api" ;;
      esac
      shift 2
      ;;
    --maturity-weather-time-standard)
      [[ $# -ge 2 ]] || die "--maturity-weather-time-standard requires lst or utc"
      case "$2" in
        lst|utc) MATURITY_WEATHER_TIME_STANDARD="$2" ;;
        *) die "--maturity-weather-time-standard must be lst or utc" ;;
      esac
      shift 2
      ;;
    --force-shared-maturity)
      FORCE_SHARED_MATURITY=1
      shift
      ;;
    --cdl-scope)
      [[ $# -ge 2 ]] || die "--cdl-scope requires conus or state"
      case "$2" in
        conus|state) CDL_SCOPE="$2" ;;
        *) die "--cdl-scope must be conus or state" ;;
      esac
      shift 2
      ;;
    --cdl-state-fips)
      [[ $# -ge 2 ]] || die "--cdl-state-fips requires comma-separated state FIPS values"
      CDL_STATE_FIPS="$2"
      shift 2
      ;;
    --cdl-latest-year)
      [[ $# -ge 2 ]] || die "--cdl-latest-year requires a year"
      CDL_LATEST_YEAR="$2"
      shift 2
      ;;
    --cdl-window-years)
      [[ $# -ge 2 ]] || die "--cdl-window-years requires a positive integer"
      CDL_WINDOW_YEARS="$2"
      shift 2
      ;;
    --seed-grower-slug)
      [[ $# -ge 2 ]] || die "--seed-grower-slug requires a slug"
      SEED_GROWER_SLUG="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-farm-slug)
      [[ $# -ge 2 ]] || die "--seed-farm-slug requires a slug"
      SEED_FARM_SLUG="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-farm-name)
      [[ $# -ge 2 ]] || die "--seed-farm-name requires a name"
      SEED_FARM_NAME="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-state)
      [[ $# -ge 2 ]] || die "--seed-state requires a state name, abbreviation, or FIPS"
      SEED_STATE="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-field-count)
      [[ $# -ge 2 ]] || die "--seed-field-count requires a positive integer"
      SEED_FIELD_COUNT="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-crop)
      [[ $# -ge 2 ]] || die "--seed-crop requires corn, soybeans, wheat, or cotton"
      case "$2" in
        corn|soybeans|wheat|cotton) SEED_CROP="$2" ;;
        *) die "--seed-crop must be corn, soybeans, wheat, or cotton" ;;
      esac
      SEED_FARM=1
      shift 2
      ;;
    --seed-random-seed)
      [[ $# -ge 2 ]] || die "--seed-random-seed requires an integer"
      SEED_RANDOM_SEED="$2"
      SEED_FARM=1
      shift 2
      ;;
    --seed-force)
      SEED_FORCE=1
      SEED_FARM=1
      shift
      ;;
    *)
      die "unknown option: $1 (run with --help)"
      ;;
  esac
done

[[ "${MATURITY_START_YEAR}" =~ ^[0-9]{4}$ ]] || die "--maturity-start-year must be a four-digit year"
[[ "${MATURITY_END_YEAR}" =~ ^[0-9]{4}$ ]] || die "--maturity-end-year must be a four-digit year"
[[ "${CDL_LATEST_YEAR}" =~ ^[0-9]{4}$ ]] || die "--cdl-latest-year must be a four-digit year"
[[ "${CDL_WINDOW_YEARS}" =~ ^[0-9]+$ ]] || die "--cdl-window-years must be a positive integer"
(( CDL_WINDOW_YEARS > 0 )) || die "--cdl-window-years must be positive"
if (( MATURITY_START_YEAR > MATURITY_END_YEAR )); then
  die "--maturity-start-year must be <= --maturity-end-year"
fi
if [[ "${SEED_FARM}" -eq 1 ]]; then
  [[ -n "${SEED_GROWER_SLUG}" ]] || die "--seed-grower-slug is required when seeding a farm"
  [[ -n "${SEED_STATE}" ]] || die "--seed-state is required when seeding a farm"
  [[ -n "${SEED_FIELD_COUNT}" ]] || die "--seed-field-count is required when seeding a farm"
  [[ "${SEED_FIELD_COUNT}" =~ ^[0-9]+$ ]] || die "--seed-field-count must be a positive integer"
  (( SEED_FIELD_COUNT > 0 )) || die "--seed-field-count must be positive"
  [[ "${SEED_RANDOM_SEED}" =~ ^[0-9]+$ ]] || die "--seed-random-seed must be a non-negative integer"
  PREPARE_SHARED_DATA=1
fi

if [[ "${NON_INTERACTIVE}" -eq 0 && -t 0 && -z "${CI:-}" ]]; then
  INTERACTIVE_MODE=1
else
  INTERACTIVE_MODE=0
fi

if [[ -z "${DATA_ROOT}" ]]; then
  if [[ "${INTERACTIVE_MODE}" -eq 1 ]]; then
    read -r -p "DATA_PIPELINE_DATA_ROOT absolute path: " DATA_ROOT
    [[ -n "${DATA_ROOT}" ]] || die "missing --data-root or DATA_PIPELINE_DATA_ROOT; refusing to mutate runtime state"
  else
    die "missing --data-root or DATA_PIPELINE_DATA_ROOT; refusing to mutate runtime state"
  fi
fi

[[ "${DATA_ROOT}" = /* ]] || die "data root must be an absolute path: ${DATA_ROOT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd -P)"
MY_FARM_ADVISOR_SKILL_ROOT="$(cd "${SKILL_DIR}/.." && pwd -P)"
AUTHORITATIVE_SRC="${SKILL_DIR}/src"
REQUIREMENTS_FILE="${SKILL_DIR}/requirements.txt"
MANIFEST_NAME=".my-farm-advisor-source-manifest.sha256"
SOURCE_LOCATOR_NAME=".my-farm-advisor-source.json"

[[ -d "${AUTHORITATIVE_SRC}" ]] || die "authoritative source directory missing: ${AUTHORITATIVE_SRC}"
[[ -f "${AUTHORITATIVE_SRC}/scripts/run_farm_pipeline.py" ]] || die "authoritative source is missing scripts/run_farm_pipeline.py"

canonicalize_root() {
  local raw="$1"
  if [[ -e "${raw}" ]]; then
    if [[ -d "${raw}" ]]; then
      (cd "${raw}" && pwd -P)
    else
      return 1
    fi
    return 0
  fi

  local parent
  parent="$(dirname "${raw}")"
  local leaf
  leaf="$(basename "${raw}")"
  [[ -d "${parent}" ]] || die "data root parent does not exist: ${parent}"
  local parent_real
  parent_real="$(cd "${parent}" && pwd -P)"
  printf '%s/%s\n' "${parent_real}" "${leaf}"
}

if [[ -e "${DATA_ROOT}" && ! -d "${DATA_ROOT}" ]]; then
  die "data root exists but is not a directory: ${DATA_ROOT}"
fi

RESOLVED_ROOT="$(canonicalize_root "${DATA_ROOT}")" || die "data root exists but is not a directory: ${DATA_ROOT}"
RUNTIME_BASE="${RESOLVED_ROOT}/data-pipeline"
RUNTIME_SRC="${RUNTIME_BASE}/src"
if [[ -n "${DATA_PIPELINE_VENV_DIR:-}" ]]; then
  [[ "${DATA_PIPELINE_VENV_DIR}" = /* ]] || die "DATA_PIPELINE_VENV_DIR must be an absolute path: ${DATA_PIPELINE_VENV_DIR}"
  if [[ -e "${DATA_PIPELINE_VENV_DIR}" && ! -d "${DATA_PIPELINE_VENV_DIR}" ]]; then
    die "DATA_PIPELINE_VENV_DIR exists but is not a directory: ${DATA_PIPELINE_VENV_DIR}"
  fi
  if [[ -d "${DATA_PIPELINE_VENV_DIR}" ]]; then
    [[ -w "${DATA_PIPELINE_VENV_DIR}" ]] || die "DATA_PIPELINE_VENV_DIR is not writable: ${DATA_PIPELINE_VENV_DIR}"
  else
    VENV_PARENT="$(dirname "${DATA_PIPELINE_VENV_DIR}")"
    [[ -d "${VENV_PARENT}" ]] || die "DATA_PIPELINE_VENV_DIR parent does not exist: ${VENV_PARENT}"
    [[ -w "${VENV_PARENT}" ]] || die "DATA_PIPELINE_VENV_DIR parent is not writable: ${VENV_PARENT}"
  fi
  RUNTIME_VENV="${DATA_PIPELINE_VENV_DIR}"
else
  RUNTIME_VENV="${RUNTIME_BASE}/.venv"
fi
LOCK_FILE="${RUNTIME_BASE}/.install.lock"

log "Resolved data root: ${RESOLVED_ROOT}"
log "Resolved runtime virtualenv: ${RUNTIME_VENV}"
log "For the current shell, run: export DATA_PIPELINE_DATA_ROOT=$(shell_quote "${RESOLVED_ROOT}")"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "Dry run: would ensure data root ${RESOLVED_ROOT}"
else
  if [[ ! -d "${RESOLVED_ROOT}" ]]; then
    parent_dir="$(dirname "${RESOLVED_ROOT}")"
    [[ -w "${parent_dir}" ]] || die "data root parent is not writable: ${parent_dir}"
    mkdir -p "${RESOLVED_ROOT}"
  fi
  [[ -d "${RESOLVED_ROOT}" ]] || die "data root is not a directory after creation: ${RESOLVED_ROOT}"
  [[ -w "${RESOLVED_ROOT}" ]] || die "data root is not writable: ${RESOLVED_ROOT}"
fi

persist_user_env() {
  local env_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/environment.d"
  local env_file="${env_dir}/60-my-farm-advisor.conf"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would write ${env_file} with DATA_PIPELINE_DATA_ROOT=${RESOLVED_ROOT}"
    return 0
  fi
  mkdir -p "${env_dir}"
  local tmp_file="${env_file}.tmp.$$"
  if [[ -f "${env_file}" ]]; then
    grep -v '^DATA_PIPELINE_DATA_ROOT=' "${env_file}" > "${tmp_file}" || true
  else
    : > "${tmp_file}"
  fi
  printf 'DATA_PIPELINE_DATA_ROOT=%s\n' "${RESOLVED_ROOT}" >> "${tmp_file}"
  mv "${tmp_file}" "${env_file}"
  log "Persisted DATA_PIPELINE_DATA_ROOT to ${env_file}"
}

write_manifest() {
  local src_dir="$1"
  python3 - "${src_dir}" "${MANIFEST_NAME}" <<'PYMANIFEST'
import hashlib
import sys
from pathlib import Path

src = Path(sys.argv[1])
manifest_name = sys.argv[2]
rows = []
for path in sorted(p for p in src.rglob("*") if p.is_file()):
    rel = path.relative_to(src).as_posix()
    if rel == manifest_name:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f"{digest}  {rel}\n")
(src / manifest_name).write_text("".join(rows), encoding="utf-8")
PYMANIFEST
}

stage_source() {
  local staging_src="$1"
  mkdir -p "${staging_src}"
  (
    cd "${AUTHORITATIVE_SRC}"
    tar \
      --exclude='.git' --exclude='*/.git' \
      --exclude='__pycache__' --exclude='*/__pycache__' \
      --exclude='.pytest_cache' --exclude='*/.pytest_cache' \
      --exclude='.venv' --exclude='*/.venv' \
      --exclude='.cache' --exclude='*/.cache' \
      --exclude='output' --exclude='*/output' \
      --exclude='data' --exclude='*/data' \
      -cf - .
  ) | (
    cd "${staging_src}"
    tar -xf -
  )
  write_manifest "${staging_src}"
  [[ -f "${staging_src}/scripts/run_farm_pipeline.py" ]] || die "staged source is missing scripts/run_farm_pipeline.py"
}

dirs_identical() {
  [[ -d "$1" && -d "$2" ]] || return 1
  diff -qr "$1" "$2" >/dev/null
}

replace_runtime_src() {
  local staging_src="$1"
  if [[ ! -d "${RUNTIME_SRC}" ]]; then
    mv "${staging_src}" "${RUNTIME_SRC}"
    return 0
  fi

  local backup_src="${RUNTIME_BASE}/.src.backup.$$"
  rm -rf "${backup_src}"
  mv "${RUNTIME_SRC}" "${backup_src}"
  if mv "${staging_src}" "${RUNTIME_SRC}"; then
    rm -rf "${backup_src}"
  else
    rm -rf "${RUNTIME_SRC}"
    mv "${backup_src}" "${RUNTIME_SRC}"
    die "failed to refresh runtime source; restored previous source tree"
  fi
}

prompt_for_drift() {
  local answer
  while true; do
    read -r -p "Runtime source differs from checkout. Choose refresh/skip/abort: " answer
    case "${answer}" in
      refresh|skip|abort) printf '%s\n' "${answer}"; return 0 ;;
      *) log "Please type exactly refresh, skip, or abort." ;;
    esac
  done
}

sync_runtime_source() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would refresh ${RUNTIME_SRC} from ${AUTHORITATIVE_SRC}"
    return 0
  fi

  mkdir -p "${RUNTIME_BASE}"
  local stage_dir="${RUNTIME_BASE}/.install-src-stage.$$"
  rm -rf "${stage_dir}"
  mkdir -p "${stage_dir}"
  local staging_src="${stage_dir}/src"
  stage_source "${staging_src}"

  if [[ -d "${RUNTIME_SRC}" ]] && dirs_identical "${RUNTIME_SRC}" "${staging_src}"; then
    log "Runtime source already matches checkout; leaving ${RUNTIME_SRC} unchanged"
    rm -rf "${stage_dir}"
    return 0
  fi

  if [[ -d "${RUNTIME_SRC}" ]]; then
    if [[ "${FORCE_REFRESH}" -eq 1 ]]; then
      log "Runtime source differs; --force-refresh permits replacement"
    elif [[ "${INTERACTIVE_MODE}" -eq 1 ]]; then
      case "$(prompt_for_drift)" in
        refresh) log "Refreshing divergent runtime source after interactive confirmation" ;;
        skip) log "Skipping divergent runtime source refresh"; rm -rf "${stage_dir}"; return 0 ;;
        abort) rm -rf "${stage_dir}"; die "aborted divergent runtime source refresh" ;;
      esac
    else
      rm -rf "${stage_dir}"
      die "runtime source differs from checkout; rerun with --force-refresh to replace non-interactively"
    fi
  else
    log "Installing runtime source into ${RUNTIME_SRC}"
  fi

  replace_runtime_src "${staging_src}"
  rm -rf "${stage_dir}"
  log "Runtime source ready at ${RUNTIME_SRC}"
}

with_runtime_lock() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    sync_runtime_source
    return 0
  fi

  mkdir -p "${RUNTIME_BASE}"
  if command -v flock >/dev/null 2>&1; then
    exec 9>"${LOCK_FILE}"
    flock 9
    sync_runtime_source
    flock -u 9
  else
    local lock_dir="${RUNTIME_BASE}/.install.lock.d"
    local waited=0
    until mkdir "${lock_dir}" 2>/dev/null; do
      waited=$((waited + 1))
      [[ "${waited}" -lt 120 ]] || die "timed out waiting for runtime source lock: ${lock_dir}"
      sleep 1
    done
    trap 'rm -rf "${lock_dir}"' EXIT
    sync_runtime_source
    rm -rf "${lock_dir}"
    trap - EXIT
  fi
}

stage_grower_web_map() {
  local gwm_src="${SKILL_DIR}/grower-web-map/src"
  if [[ ! -d "${gwm_src}" ]]; then
    log "No grower-web-map source found at ${gwm_src}; skipping"
    return 0
  fi
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would copy grower-web-map scripts to ${RUNTIME_SRC}/scripts/"
    return 0
  fi
  mkdir -p "${RUNTIME_SRC}/scripts"
  cp "${gwm_src}/generate_grower_map.py" "${RUNTIME_SRC}/scripts/generate_grower_map.py"
  log "Staged grower-web-map script to ${RUNTIME_SRC}/scripts/generate_grower_map.py"
}

write_source_locator() {
  local locator_path="${RUNTIME_BASE}/${SOURCE_LOCATOR_NAME}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would write source locator ${locator_path} with my_farm_advisor_skill_root=${MY_FARM_ADVISOR_SKILL_ROOT}"
    return 0
  fi
  mkdir -p "${RUNTIME_BASE}"
  python3 - "${locator_path}" "${MY_FARM_ADVISOR_SKILL_ROOT}" <<'PYSOURCELOCATOR'
import json
import sys
from pathlib import Path

locator_path = Path(sys.argv[1])
skill_root = Path(sys.argv[2]).resolve(strict=False)
payload = {
    "my_farm_advisor_skill_root": str(skill_root),
    "purpose": "Import-only checkout locator for runtime scripts; generated outputs stay under DATA_PIPELINE_DATA_ROOT/data-pipeline.",
}
locator_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PYSOURCELOCATOR
  log "Wrote source locator to ${locator_path}"
}

install_dependencies() {
  if [[ "${INSTALL_DEPS}" -eq 0 ]]; then
    log "Skipping virtualenv/dependency installation because --no-install-deps was passed"
    return 0
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would create/update venv at ${RUNTIME_VENV} and install ${REQUIREMENTS_FILE}"
    return 0
  fi

  command -v python3 >/dev/null 2>&1 || die "python3 is required to create the runtime virtualenv"
  if [[ ! -x "${RUNTIME_VENV}/bin/python" ]]; then
    log "Creating runtime virtualenv at ${RUNTIME_VENV}"
    python3 -m venv "${RUNTIME_VENV}"
  else
    log "Updating runtime virtualenv at ${RUNTIME_VENV}"
  fi

  if [[ -f "${REQUIREMENTS_FILE}" ]]; then
    "${RUNTIME_VENV}/bin/python" -m pip install --upgrade pip
    "${RUNTIME_VENV}/bin/python" -m pip install -r "${REQUIREMENTS_FILE}"
  else
    log "No requirements.txt found; leaving virtualenv without dependency install"
  fi
}

prepare_shared_data() {
  if [[ "${PREPARE_SHARED_DATA}" -eq 0 ]]; then
    return 0
  fi

  local shared_script="${RUNTIME_SRC}/scripts/init_shared_data.py"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would prepare shared data with ${shared_script} for ${MATURITY_START_YEAR}-${MATURITY_END_YEAR}, CDL ${CDL_SCOPE} last ${CDL_WINDOW_YEARS} years"
    return 0
  fi

  [[ -x "${RUNTIME_VENV}/bin/python" ]] || die "runtime Python is required for --prepare-shared-data: ${RUNTIME_VENV}/bin/python"
  [[ -f "${shared_script}" ]] || die "shared data script missing: ${shared_script}"

  local command=(
    "${RUNTIME_VENV}/bin/python"
    "${shared_script}"
    --start-year "${MATURITY_START_YEAR}"
    --end-year "${MATURITY_END_YEAR}"
    --coverage "${MATURITY_COVERAGE}"
    --weather-backend "${MATURITY_WEATHER_BACKEND}"
    --weather-time-standard "${MATURITY_WEATHER_TIME_STANDARD}"
    --cdl-scope "${CDL_SCOPE}"
    --cdl-latest-year "${CDL_LATEST_YEAR}"
    --cdl-window-years "${CDL_WINDOW_YEARS}"
  )
  if [[ -n "${CDL_STATE_FIPS}" ]]; then
    command+=(--cdl-state-fips "${CDL_STATE_FIPS}")
  fi
  if [[ "${FORCE_SHARED_MATURITY}" -eq 1 ]]; then
    command+=(--force)
  fi

  log "Preparing shared data for ${MATURITY_START_YEAR}-${MATURITY_END_YEAR} (${MATURITY_COVERAGE}, ${MATURITY_WEATHER_BACKEND}, CDL ${CDL_SCOPE})"
  DATA_PIPELINE_DATA_ROOT="${RESOLVED_ROOT}" DATA_PIPELINE_VENV_DIR="${RUNTIME_VENV}" "${command[@]}"
}

prepare_shared_maturity() {
  if [[ "${PREPARE_SHARED_MATURITY}" -eq 0 ]]; then
    return 0
  fi
  if [[ "${PREPARE_SHARED_DATA}" -eq 1 ]]; then
    return 0
  fi

  local maturity_script="${RUNTIME_SRC}/scripts/run_maturity_years_by_fips.py"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would prepare shared maturity outputs with ${maturity_script} for ${MATURITY_START_YEAR}-${MATURITY_END_YEAR} (${MATURITY_COVERAGE})"
    return 0
  fi

  [[ -x "${RUNTIME_VENV}/bin/python" ]] || die "runtime Python is required for --prepare-shared-maturity: ${RUNTIME_VENV}/bin/python"
  [[ -f "${maturity_script}" ]] || die "shared maturity script missing: ${maturity_script}"

  local command=(
    "${RUNTIME_VENV}/bin/python"
    "${maturity_script}"
    --start-year "${MATURITY_START_YEAR}"
    --end-year "${MATURITY_END_YEAR}"
    --coverage "${MATURITY_COVERAGE}"
    --weather-backend "${MATURITY_WEATHER_BACKEND}"
    --weather-time-standard "${MATURITY_WEATHER_TIME_STANDARD}"
  )
  if [[ "${FORCE_SHARED_MATURITY}" -eq 1 ]]; then
    command+=(--force)
  fi

  log "Preparing shared maturity outputs for ${MATURITY_START_YEAR}-${MATURITY_END_YEAR} (${MATURITY_COVERAGE}, ${MATURITY_WEATHER_BACKEND})"
  DATA_PIPELINE_DATA_ROOT="${RESOLVED_ROOT}" DATA_PIPELINE_VENV_DIR="${RUNTIME_VENV}" "${command[@]}"
}

seed_farm_dashboard() {
  if [[ "${SEED_FARM}" -eq 0 ]]; then
    return 0
  fi

  local dashboard_script="${RUNTIME_SRC}/scripts/farm_dashboard.py"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would seed ${SEED_FIELD_COUNT} fields for ${SEED_GROWER_SLUG} in ${SEED_STATE} with ${dashboard_script}"
    return 0
  fi

  [[ -x "${RUNTIME_VENV}/bin/python" ]] || die "runtime Python is required for farm seeding: ${RUNTIME_VENV}/bin/python"
  [[ -f "${dashboard_script}" ]] || die "farm dashboard script missing: ${dashboard_script}"

  local command=(
    "${RUNTIME_VENV}/bin/python"
    "${dashboard_script}"
    create
    --state "${SEED_STATE}"
    --field-count "${SEED_FIELD_COUNT}"
    --seed "${SEED_RANDOM_SEED}"
    --grower-slug "${SEED_GROWER_SLUG}"
    --crop "${SEED_CROP}"
    --cdl-year "${CDL_LATEST_YEAR}"
  )
  if [[ -n "${SEED_FARM_SLUG}" ]]; then
    command+=(--farm-slug "${SEED_FARM_SLUG}")
  fi
  if [[ -n "${SEED_FARM_NAME}" ]]; then
    command+=(--farm-name "${SEED_FARM_NAME}")
  fi
  if [[ "${SEED_FORCE}" -eq 1 ]]; then
    command+=(--force)
  fi

  log "Seeding ${SEED_FIELD_COUNT} fields for ${SEED_GROWER_SLUG} in ${SEED_STATE}"
  DATA_PIPELINE_DATA_ROOT="${RESOLVED_ROOT}" DATA_PIPELINE_VENV_DIR="${RUNTIME_VENV}" "${command[@]}"
}

case "${PERSIST_MODE}" in
  user) persist_user_env ;;
  none) log "Skipping user-level persistence because --persist none was passed" ;;
  *) die "unsupported persistence mode: ${PERSIST_MODE}" ;;
esac

with_runtime_lock
stage_grower_web_map
write_source_locator
install_dependencies
prepare_shared_data
prepare_shared_maturity
seed_farm_dashboard

log "Install complete. Runtime base: ${RUNTIME_BASE}"
