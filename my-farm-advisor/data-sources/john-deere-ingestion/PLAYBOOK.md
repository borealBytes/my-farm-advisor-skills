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

## Data root resolution

The subskill resolves the writable data root in this order:

1. `JD_DATA_ROOT`
2. `/data/workspace/data/my-farm-advisor`
3. `.runtime/my-farm-advisor/data/`

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

## Output guarantee

- Raw payloads are never overwritten.
- Normalized projections use source-specific naming so they do not collide with other source artifacts.
- Operation registry manifests record the authoritative status for every attempted API call.

## Status enum

The registry uses exactly these statuses:

`pending | accessible | unauthorized | unsupported_by_sdk | unsupported_environment | empty | error | disabled_by_default | skipped_by_checkpoint`

## Notes

- The portable `FileTokenStore` is the dev/portable v1 default. It is replaceable behind the `TokenStore` interface for production hardening.
- HATEOAS mode is supported via the SDK client and can be enabled in config for future compatibility.
- The local webhook receiver logs events to a JSONL file and can queue incremental syncs. Production webhook deployment is out of scope in v1.
