# Headless cron & plugin-seed runtime contract

Unattended-run facts for the data pipeline (cron, plugin seeding, fresh install).
Verified against the installed scripts' argparse, not against prose.

## Cron-shell environment

- Cron/systemd shells do **not** source `environment.d`: export
  `DATA_PIPELINE_DATA_ROOT` in the cronjob definition itself (the gateway
  process's environ likewise does not carry profile `.env` secrets).
- Non-interactive runs **fail fast** on the missing var rather than falling back
  to a default root — treat this as a feature: a missing export becomes a hard
  error, never a silent wrong-tree write.
- All default-path providers are keyless (CSB GeoParquet, Overpass, NASA POWER
  public Zarr, SSURGO/gNATSGO, Ontario DSS, SoilGrids floor, Copernicus DEM,
  WorldCereal RDM, Planetary Computer anonymous). The only account-gated path is
  the optional CDSE backend for WorldCereal Sentinel-1 — fresh homes need zero
  accounts.
- `install.sh --dry-run` prints planned actions without mutating — use it as the
  dry-run gate for any UI or script that wraps installs (including
  `--non-interactive --force-refresh` for CI/smoke over a divergent runtime).

## Refresh command surface (verified)

- `farm_dashboard.py refresh` accepts **only** `--scope farm|grower|all`,
  `--grower-slug`, `--farm-slug`, `--force`. Any baked flag outside that list
  (e.g. `--allow-live-downloads`) is an argparse exit-2 and kills every nightly
  run.
- Terrain live-fetch is the **orchestrator's** job: `run_farm_pipeline.py` itself
  passes `--allow-live-downloads` to the DEM step. The scheduler must not re-add
  the flag to the refresh line.
- `--force` sets `AG_FORCE=1` and re-runs **all** steps (multi-year CDL, DEM
  tiles, satellite clips all re-download). Daily incremental is plain
  `farm_dashboard.py refresh --scope all` (live-data-wins: fresh artifacts
  skip). Reserve `--force` for a deliberate full-rebuild affordance.
- Keep UI refresh and cron calling the same command so behavior cannot drift —
  only the schedule differs.

## Plugin-seed design rules

- The user-boundary ingest contract is normative in
  `data-pipeline/AGENTS.md` § "Plugin onboarding — user-boundary ingest
  contract" (GeoJSON 4326, hard-required `field_id` + `country`, repo-contract
  write set with `source=user_upload`, checkpoints
  `accepted → counties_matched → legs_running`, sha256 no-op idempotency,
  `--prune-missing` the only deletion path). Endpoints spec against that
  section; do not restate the field lists elsewhere.
- Writer/reader skill split: the vendored payload carries the **full** tree;
  reader profile mirrors are written with `install.sh` + `scripts/ingest/`
  **stripped at seeder copy time** — never a second repo variant (a second
  variant doubles the drift surface for a `cp` filter's worth of benefit).
- Capability detection hashes the mirror's subtree manifest (`install.sh`
  present ⇒ writer). An env var present in a reader's `.env` is a warning, not
  an error — readers need it to read the archive; writes come from scripts,
  not from the variable.
- Daily-engagement cron belongs to the conversation agent (overseer); the
  pipeline profile's cron is pure ingest. A pipeline agent that also chats drags
  UI concerns into the sole writer.

## Trio-repo checkout hygiene

- Before editing/committing to the skills-trio repo, confirm which checkout is
  on `main` (`git worktree list`, `git branch --show-current`): feature-branch
  clones can have a **different tree shape**, so a clean `git status` is no
  proof you are committing where you think you are.
- The deployed profile mirror can be **ahead of repo main** (sections authored
  in-place during sessions). Backport + push before creating any release tag or
  vendor pin, or the vendored tree ships older than the runtime runs — see
  SKILL.md "Verification and sync rules".
