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
