---
name: john-deere-ingestion
description: Ingest grower data from the John Deere Operations Center using the TypeScript deere-sdk. Exports raw API responses and normalized grower/farm/field projections into the canonical farm data tree.
version: 1.0.0
author: Boreal Bytes
tags: [agriculture, john-deere, ingestion, oauth, operations-center, data-source]
---

# Skill: john-deere-ingestion

## Use this skill when

- You need to connect a grower account to the John Deere Operations Center.
- You want to export field boundaries, operations, equipment, or machine data from Deere into the canonical farm tree.
- You need an operation registry that records which Deere APIs are accessible, unauthorized, or unsupported for a given grower.
- You want a repeatable, incremental sync that preserves raw source payloads and writes normalized projections.

## What this skill does

- Authenticates grower accounts via OAuth Authorization Code flow with a local callback server and a pasted-code fallback.
- Discovers and records the status of every API group exposed by the installed deere-sdk.
- Exports immutable raw JSON responses under source-specific timestamped paths.
- Projects normalized grower, farm, and field assets into the canonical tree using `.john-deere.` filenames and `john-deere/` leaf folders.
- Supports incremental sync with checkpoint-based skipping so repeated runs do not re-fetch unchanged data.

## What this skill does not do

- It does not wire directly into the R2 seed pipeline in v1. R2 integration is a future phase.
- It does not claim production certification or production readiness. This is a dev/portable v1 build.
- It does not perform destructive write, update, or delete operations against Deere APIs in default mode.

## Commands

| Command | Alias | Purpose |
|---|---|---|
| `jd init` | `john-deere init`, `john-deer init` | OAuth setup, token persistence, and org connection check |
| `jd ingest` | `john-deere ingest`, `john-deer ingest` | Full registry export for the connected grower |
| `jd sync` | `john-deere sync`, `john-deer sync` | Incremental sync using last checkpoint |
| `jd registry` | `john-deere registry`, `john-deer registry` | Export the operation registry manifest |
| `jd webhook` | `john-deere webhook`, `john-deer webhook` | Start the local webhook receiver |
| `jd doctor` | `john-deere doctor`, `john-deer doctor` | Verify env vars, token store, and endpoint reachability |
| `jd paths` | `john-deere paths`, `john-deer paths` | Print resolved data root and canonical path mapping |

## Execution examples

### Print paths without credentials

```bash
npx jd paths --dry-run
```

Output includes the resolved data root, token store path, raw export directory, manifest directory, and example canonical paths for the current configuration.

### Verify the environment

```bash
JD_CLIENT_ID=<id> JD_CLIENT_SECRET=<secret> npx jd doctor
```

Reports credential presence, token store state, OAuth endpoint reachability, and data root writability.

### Initialize OAuth in sandbox

```bash
JD_CLIENT_ID=<id> JD_CLIENT_SECRET=<secret> npx jd init --environment sandboxapi
```

Starts a local callback server on `localhost:9090/callback`, prints the authorization URL, exchanges the code for tokens, and checks organization connections.

### Headless init with a pre-obtained code

```bash
JD_CLIENT_ID=<id> JD_CLIENT_SECRET=<secret> npx jd init --code <authorization-code>
```

Useful for non-interactive environments or when the browser flow is not available.

### Export the operation registry

```bash
npx jd registry
```

Prints the full registry JSON. To write it to a file:

```bash
npx jd registry --output registry-manifest.json
```

### Full ingest in sandbox

```bash
JD_CLIENT_ID=<id> JD_CLIENT_SECRET=<secret> npx jd ingest --environment sandboxapi
```

Runs every enabled operation in the registry, writes raw JSON snapshots, normalized projections, operation manifests, and a run summary.

### Incremental sync

```bash
JD_CLIENT_ID=<id> JD_CLIENT_SECRET=<secret> npx jd sync
```

Reads the last checkpoint and skips operations whose data has not changed. Use `--force` to bypass the checkpoint and run a full sync.

### Start the webhook receiver

```bash
npx jd webhook --port 8080
```

Logs incoming John Deere webhook events to a JSONL file under the resolved data root.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JD_CLIENT_ID` | Yes | - | OAuth client ID from John Deere developer portal |
| `JD_CLIENT_SECRET` | Yes | - | OAuth client secret from John Deere developer portal |
| `JD_REDIRECT_URI` | No | `http://localhost:9090/callback` | OAuth redirect URI |
| `JD_ENVIRONMENT` | No | `sandboxapi` | API environment: `sandboxapi` or `production` |
| `JD_DATA_ROOT` | No | See data root resolution below | Writable root for raw and normalized outputs |

## Credential handling

- Credentials are read exclusively from environment variables. No secrets are stored in source files.
- The default token store is a portable file-based store under the resolved data root. It persists refresh tokens so headless sync can run without a browser.
- Token files must never be committed. They live under an ignored runtime path by default.
- Rotate `JD_CLIENT_SECRET` periodically. The skill does not cache the secret; it reads it fresh on every run.

## Sandbox-first flow

1. Set `JD_ENVIRONMENT=sandboxapi`.
2. Run `jd init` and complete OAuth in the sandbox.
3. Verify the organization list and connection grants.
4. Run `jd registry` to record which APIs are accessible in the sandbox.
5. Run `jd ingest` to export raw and normalized data.
6. Only after sandbox validation succeeds should you consider switching to `production`.

## Mock mode

Mock mode runs the full ingest or sync pipeline without calling live John Deere APIs. It uses deterministic fixture payloads so CI pipelines and local testing can exercise manifest writing, checkpoint advancement, and normalized output creation without credentials.

### When to use mock mode

- Local development when credentials are not available.
- CI pipelines that must test CLI behavior without sandbox secrets.
- Regression testing for manifest formats, checkpoint logic, and normalized path contracts.

### Mock mode examples

```bash
# Full ingest with deterministic fixtures
npx jd ingest --mock

# Sync with mock fixtures (exercises checkpoint skipping logic)
npx jd sync --mock

# Mock ingest with a custom data root
npx jd ingest --mock --data-root ./test-output

# Mock ingest with dry-run to inspect intended paths
npx jd ingest --mock --dry-run
```

Mock mode writes real files: raw JSON snapshots, normalized projections, operation manifests, and run summaries. Clean the output directory between runs to avoid accumulating mock artifacts.

## Data root resolution

The subskill resolves the writable data root in this order:

1. `JD_DATA_ROOT`
2. `/data/workspace/data/my-farm-advisor`
3. `.runtime/my-farm-advisor/data/`

## Evidence paths

After a run completes, the following artifacts are available under the resolved data root. These paths are useful for validation, debugging, and CI assertions.

| Artifact | Path pattern | Purpose |
|---|---|---|
| Raw API snapshot | `growers/<slug>/source/john-deere/raw/<api_group>/<operation>/<YYYY>/<MM>/<DD>/<HHmmss>_<operation>_<id>.json` | Immutable JSON response from the API |
| Normalized grower | `growers/<slug>/grower.john-deere.json` | Canonical grower projection |
| Normalized farm | `growers/<slug>/farms/<farm_slug>/farm.john-deere.json` | Canonical farm projection |
| Normalized field | `growers/<slug>/farms/<farm_slug>/fields/<field_slug>/field.john-deere.json` | Canonical field projection |
| Field boundary | `growers/<slug>/farms/<farm_slug>/fields/<field_slug>/boundary/field_boundary.john-deere.geojson` | GeoJSON boundary from Deere |
| Operation statuses | `growers/<slug>/source/john-deere/manifests/operation-statuses.json` | Per-operation status, timing, and output paths |
| Latest run | `growers/<slug>/source/john-deere/manifests/latest-run.json` | Run-level summary with status counts and checkpoint |
| Checkpoint | `growers/<slug>/source/john-deere/checkpoints/latest-checkpoint.json` | Incremental sync cursor state |
| Token store | `<data_root>/tokens/<grower_slug>.json` | Refresh token persistence (dev-only) |
| Webhook log | `<data_root>/webhooks/john-deere-events.jsonl` | Incoming webhook events (one JSON object per line) |

In mock mode, the same paths are populated under the resolved (or overridden) data root so tests can assert on file existence and content.

## Raw + normalized data contract

Every export writes both:

- **Raw**: immutable JSON snapshots under `growers/<grower_slug>/source/john-deere/raw/<api_group>/<operation>/<YYYY>/<MM>/<DD>/<HHmmss>_<operation>_<id>.json`
- **Normalized**: canonical projections under `growers/<grower_slug>/farms/<farm_slug>/fields/<field_slug>/...` using `.john-deere.` filenames or `john-deere/` leaf folders

The highest normalized boundary is always `growers/<grower_slug>/`. No normalized output creates top-level `farms/`, `fields/`, or `equipment/` directories outside a grower path.

## R2-readiness boundary

- The data root resolution order mirrors the R2 seed pipeline convention, but direct R2 wiring is explicitly out of scope in v1.
- The normalized tree follows the same grower/farm/field/asset shape that the R2 seed pipeline expects, so later integration should be a path/config change rather than a restructure.
- Object-storage sync semantics such as `rsync --no-times` are not implemented here; they belong in the R2 seed pipeline layer.

## R2 migration notes

When the R2 seed pipeline is ready to consume John Deere ingest outputs, the integration path should be:

1. **Run JD ingest first** so the canonical tree is populated with Deere artifacts.
2. **Run R2 seed** so shared baselines and non-Deere farm data are present in the same tree.
3. **R2 scripts read JD manifests** from `growers/<slug>/manifests/john-deere/latest-run.json` to understand which operations succeeded, which were unauthorized, and which produced normalized outputs.
4. **R2 scripts read JD normalized data** from `.john-deere.` files and `john-deere/` leaf folders without risk of collision, because JD artifacts are source-scoped.

### Data root alignment

Both pipelines resolve the writable root with the same precedence pattern:

- Explicit env override (`JD_DATA_ROOT` / `R2_SEED_DATA_ROOT`)
- OpenClaw workspace default (`/data/workspace/data/my-farm-advisor`)
- Local checkout fallback (`data/my-farm-advisor` or `.runtime/my-farm-advisor/data/`)

If both pipelines target the same root, the combined tree contains neutral R2 seed files plus source-scoped JD files in the same canonical structure.

### Manifest consumption contract

An R2 pipeline script that wants to consume JD operation results should expect:

- `operation-statuses.json` lists every attempted API call with `operation`, `status`, `startTime`, `endTime`, `outputPaths`, and `errorDetails`.
- `latest-run.json` adds run-level metadata: `runId`, `totalDurationMs`, `statusCounts`, and `nextCheckpoint`.
- Both files are mirrored under `source/john-deere/manifests/` (raw mirror) and `manifests/john-deere/` (normalized mirror).

An R2 adapter can map these JSON payloads into Python dataclasses or pandas DataFrames without restructuring the tree.

### Path mapping checklist

| Canonical R2 path | JD equivalent | Notes |
|---|---|---|
| `growers/<slug>/grower.json` | `growers/<slug>/grower.john-deere.json` | JD writes a parallel source-scoped file, not a replacement. |
| `growers/<slug>/farms/<slug>/farm.json` | `growers/<slug>/farms/<slug>/farm.john-deere.json` | Same pattern: parallel, not overwriting. |
| `growers/<slug>/farms/<slug>/fields/<slug>/boundary/` | `growers/<slug>/farms/<slug>/fields/<slug>/boundary/field_boundary.john-deere.geojson` | JD boundary is source-scoped; neutral boundary can coexist. |
| `growers/<slug>/farms/<slug>/fields/<slug>/manifests/` | `growers/<slug>/farms/<slug>/fields/<slug>/manifests/john-deere/` | JD field manifests live in a source subfolder. |
| `growers/<slug>/farms/<slug>/manifests/` | `growers/<slug>/farms/<slug>/manifests/john-deere/` | Same subfolder convention. |

### What R2 should NOT do

- Do not modify R2 pipeline scripts to invoke `jd ingest` or `jd sync`. Those commands stay in the JD subskill.
- Do not rename JD artifacts to neutral filenames. Source scoping prevents collisions; removing it would create merge conflicts.
- Do not claim production R2 integration is complete until an explicit integration phase is planned and tested.

## Validation commands

Use these commands to verify the subskill state before and after runs.

### Verify environment and connectivity

```bash
npx jd doctor
```

Checks:
- `JD_CLIENT_ID` and `JD_CLIENT_SECRET` are present
- Token store file exists and is readable
- OAuth discovery endpoint is reachable
- Data root is writable

### Inspect the operation registry

```bash
npx jd registry
```

Prints every registered operation with its default enablement, auth mode, scope, and status. Use this to preview which APIs will be called before running `ingest`.

### Verify outputs after a run

```bash
# List raw snapshots for a grower
ls growers/<slug>/source/john-deere/raw/

# Check the latest run manifest
jq . growers/<slug>/source/john-deere/manifests/latest-run.json

# Count operations by status
jq '.operations | group_by(.status) | map({status: .[0].status, count: length})' growers/<slug>/source/john-deere/manifests/operation-statuses.json

# Verify checkpoint exists after sync
ls growers/<slug>/source/john-deere/checkpoints/latest-checkpoint.json
```

### Run the test suite

```bash
cd my-farm-advisor/data-sources/john-deere-ingestion
npm run build
npm test
```

All 70 tests across 22 test files exercise unit and integration behavior including mock-mode ingest, sync, registry export, webhook handling, token storage, and R2 adapter contracts.

## Output guarantee

- Raw payloads are never overwritten.
- Normalized projections use source-specific naming so they do not collide with other source artifacts.
- Operation registry manifests record the authoritative status for every attempted API call.

## Status enum

The registry records every operation with one of these statuses:

| Status | Meaning |
|---|---|
| `pending` | Not yet attempted (initial state before a run) |
| `accessible` | Successful API call with data returned |
| `unauthorized` | 401/403 or missing OAuth scope |
| `unsupported_by_sdk` | The requested API method is not present in the installed `deere-sdk` |
| `unsupported_environment` | SDK/environment mismatch |
| `empty` | Successful API call that returned no records |
| `error` | Unexpected failure (network, parsing, or persistence error) |
| `disabled_by_default` | Write or destructive operation excluded from default export |
| `skipped_by_checkpoint` | Unchanged since last sync; skipped during incremental runs |

After a full ingest, expect a mix of `accessible`, `empty`, `unauthorized`, and `unsupported_by_sdk`. `disabled_by_default` and `skipped_by_checkpoint` appear during sync or when destructive operations are left excluded.

## Notes

- The portable `FileTokenStore` is the dev/portable v1 default. It is replaceable behind the `TokenStore` interface for production hardening.
- HATEOAS mode is supported via the SDK client and can be enabled in config for future compatibility.
- The local webhook receiver logs events to a JSONL file and can queue incremental syncs. Production webhook deployment is out of scope in v1.
