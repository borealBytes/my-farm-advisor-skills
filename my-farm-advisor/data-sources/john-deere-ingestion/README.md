# john-deere-ingestion

Standalone John Deere Operations Center ingestion subskill for My Farm Advisor.

## What it does

This subskill connects to the John Deere Operations Center on behalf of a grower, enumerates every supported API operation through the TypeScript `deere-sdk`, and exports both raw API responses and normalized grower/farm/field projections into the canonical farm data tree.

It is designed to be:

- **Standalone first**: isolated TypeScript tooling under this directory only.
- **Sandbox-first**: default environment is `sandboxapi`.
- **R2-ready later**: follows the same canonical tree shape as the R2 seed pipeline, but does not wire into R2 in v1.

## Commands

Run via `npx` inside this directory, or install the CLI globally:

```bash
npx jd <command>
npx john-deere <command>
npx john-deer <command>
```

| Command | Purpose |
|---|---|
| `init` | OAuth Authorization Code flow with local callback at `localhost:9090/callback`, plus pasted-code fallback. Exchanges code for tokens, persists refresh token, and verifies organization connections. |
| `ingest` | Full export: runs the entire operation registry against the connected grower and writes raw + normalized data. |
| `sync` | Incremental export: reads the last checkpoint and skips operations that have not changed. |
| `registry` | Export the operation registry manifest without calling APIs. Useful for reviewing coverage. |
| `webhook` | Start a local HTTP receiver that logs incoming John Deere webhook events to JSONL. |
| `doctor` | Check environment variables, token store state, endpoint reachability, and data root resolution. |
| `paths` | Print the resolved data root and example canonical paths for the current configuration. |

### Command examples

These invocations have been tested against the CLI build:

```bash
# Print resolved data root and canonical paths without credentials
npx jd paths --dry-run

# Verify environment, token store, and OAuth endpoint reachability
npx jd doctor

# Start OAuth flow in sandbox (opens browser or prints auth URL)
JD_CLIENT_ID=<your-id> JD_CLIENT_SECRET=<your-secret> npx jd init --environment sandboxapi

# Headless init with a pre-obtained authorization code
JD_CLIENT_ID=<your-id> JD_CLIENT_SECRET=<your-secret> npx jd init --code <authorization-code>

# Export the operation registry manifest to stdout
npx jd registry

# Export the registry to a file
npx jd registry --output registry-manifest.json

# Full ingest in sandbox
JD_CLIENT_ID=<your-id> JD_CLIENT_SECRET=<your-secret> npx jd ingest --environment sandboxapi

# Full ingest in mock mode (no credentials needed, deterministic fixtures)
npx jd ingest --mock

# Incremental sync using the last checkpoint
JD_CLIENT_ID=<your-id> JD_CLIENT_SECRET=<your-secret> npx jd sync

# Force a full sync even if a checkpoint exists
npx jd sync --force

# Start the local webhook receiver on the default port
npx jd webhook

# Start the webhook receiver on a custom port
npx jd webhook --port 8080
```

## Environment variables

All secrets are read from environment variables. No secrets are stored in source files.

| Variable | Required | Default | Description |
|---|---|---|---|
| `JD_CLIENT_ID` | Yes | - | OAuth client ID from the John Deere developer portal. |
| `JD_CLIENT_SECRET` | Yes | - | OAuth client secret from the John Deere developer portal. |
| `JD_REDIRECT_URI` | No | `http://localhost:9090/callback` | OAuth redirect URI. Must match the app registration. |
| `JD_ENVIRONMENT` | No | `sandboxapi` | Target API environment. Use `sandboxapi` for sandbox or `production` for live data. |
| `JD_DATA_ROOT` | No | See resolution below | Writable directory for raw exports, normalized projections, manifests, and token storage. |

### Data root resolution

The subskill picks the first available root in this order:

1. `JD_DATA_ROOT`
2. `/data/workspace/data/my-farm-advisor`
3. `.runtime/my-farm-advisor/data/` (relative to the repository root)

This mirrors the R2 seed pipeline precedence, but R2 direct wiring is explicitly out of scope in v1.

## Credential handling

- Never commit credentials. `JD_CLIENT_ID` and `JD_CLIENT_SECRET` must be supplied as environment variables.
- The skill reads the client secret fresh on every run and does not cache it.
- Token storage files live under ignored runtime paths and must never be committed.

### Secret rotation

Rotate `JD_CLIENT_SECRET` on a regular cadence:

1. Generate a new secret in the John Deere developer portal.
2. Update the environment variable to the new value.
3. Verify connectivity with `jd doctor`.
4. Revoke the old secret in the developer portal after confirming the new one works.

Because the skill reads the secret fresh on every invocation, there is no restart or redeploy step. The old secret becomes invalid as soon as it is revoked.

## Sandbox-first flow

1. Register an application in the John Deere developer portal and obtain a client ID and secret.
2. Set `JD_ENVIRONMENT=sandboxapi`.
3. Run `jd init`. The CLI prints an authorization URL. Open it in a browser or paste the returned code.
4. After token exchange, the CLI lists organizations and checks for required connection grants.
5. Run `jd registry` to see which APIs are accessible in the sandbox.
6. Run `jd ingest` to export raw and normalized data.
7. Only after sandbox validation should you switch to `JD_ENVIRONMENT=production`.

## Known limitations

- **Live sandbox tests blocked**: T19 and T20 live sandbox integration tests are blocked pending valid John Deere developer credentials. Mock-mode tests provide deterministic coverage instead.
- **Work Plans API unsupported by SDK**: The `workPlans.list` operation is recorded as `unsupported_by_sdk` because the installed `deere-sdk@0.2.0` does not expose it.
- **Field operations with measurements unsupported by SDK**: `fieldOperations.listAllWithMeasurements` is recorded as `unsupported_by_sdk` in the current SDK version.
- **Organization connection grants required**: Some APIs return 403 until the grower explicitly connects the registered application to their organization in the John Deere developer portal.
- **HATEOAS traversal is partial**: HATEOAS mode is supported via the SDK client but full link-following automation is not yet implemented.
- **Production webhook deployment out of scope**: The local webhook receiver is suitable for development only. Production webhook deployment is not included in v1.
- **R2 direct wiring out of scope**: The subskill aligns with R2 conventions but does not invoke R2 seed pipeline scripts or implement object-storage sync.

## OAuth endpoint resolution

- The resolver uses Deere's official OAuth discovery document first: `https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/.well-known/oauth-authorization-server`.
- Official Deere developer docs and Deere's sample OAuth apps all point to that same Okta tenant for both sandbox and production OAuth.
- Resolved endpoints are therefore shared across sandbox and production:
  - authorize: `https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize`
  - token: `https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token`
  - revoke: `https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke`
- Environment-specific behavior lives at the API base URL layer, not the OAuth server layer:
  - sandbox API base: `https://sandboxapi.deere.com/platform`
  - production API base: `https://api.deere.com/platform`
- If the official discovery URL fails, the resolver falls back to those authoritative endpoint values. If a custom discovery URL fails, it throws `OAuthEndpointResolutionError` so callers can surface the bad configuration instead of silently using stale metadata.

## Raw + normalized data contract

Every export writes two views of the same source data:

### Raw view (immutable)

Raw JSON snapshots are preserved with timestamped filenames under:

```text
growers/<grower_slug>/source/john-deere/raw/<api_group>/<operation>/<YYYY>/<MM>/<DD>/<HHmmss>_<operation>_<id>.json
```

Raw payloads are append-only and never overwritten.

### Normalized view (canonical tree)

Normalized projections follow the My Farm Advisor canonical shape:

```text
growers/<grower_slug>/
  grower.john-deere.json
  farms/<farm_slug>/
    farm.john-deere.json
    boundaries/john-deere/
    fields/<field_slug>/
      field.john-deere.json
      boundary/field_boundary.john-deere.geojson
      planting/john-deere/<YYYY>/
      harvest/john-deere/<YYYY>/
      applications/john-deere/<YYYY>/
      operations/john-deere/<YYYY>/
      guidance-lines/john-deere/
      flags/john-deere/
      map-layers/john-deere/
  equipment/john-deere/
  operators/john-deere/
  products/john-deere/
  crop-types/john-deere/
  machine-data/locations/<machine_id>/john-deere/<YYYY>/
  ...
```

John Deere artifacts use `.john-deere.` filenames or `john-deere/` leaf folders so they do not collide with other source artifacts. The highest normalized boundary is always `growers/<grower_slug>/`.

## Token storage

**Warning: the default token store is development-only.**

The default `FileTokenStore` saves refresh tokens as plain JSON files under the resolved data root. This is a portable v1 default for development and local testing only. It is not encrypted, not certified for production use, and must never be committed to version control.

For production hardening, replace `FileTokenStore` with an encrypted or keychain-backed implementation behind the `TokenStore` interface. The keychain stub at `src/tokens/keychain-store.ts` exists as a placeholder for this future work.

## R2 Integration

This section describes how the John Deere ingestion subskill aligns with the R2 seed pipeline conventions, and what a future R2 integration would look like.

### Canonical tree alignment

The R2 seed pipeline expects a deterministic on-disk tree under `data/my-farm-advisor/`:

```text
growers/<grower_slug>/
  grower.json
  farms/<farm_slug>/
    farm.json
    boundary/
    manifests/
    logs/
    derived/
    fields/<field_slug>/
      boundary/
      soil/
      weather/
      satellite/
      manifests/
      derived/
      logs/
```

John Deere normalized outputs follow the same hierarchy, but scope every artifact to its source so it never collides with other ingest pipelines:

```text
growers/<grower_slug>/
  grower.john-deere.json
  farms/<farm_slug>/
    farm.john-deere.json
    boundaries/john-deere/
    fields/<field_slug>/
      field.john-deere.json
      boundary/field_boundary.john-deere.geojson
      planting/john-deere/<YYYY>/
      harvest/john-deere/<YYYY>/
      applications/john-deere/<YYYY>/
      operations/john-deere/<YYYY>/
      guidance-lines/john-deere/
      flags/john-deere/
      map-layers/john-deere/
  equipment/john-deere/
  operators/john-deere/
  products/john-deere/
  crop-types/john-deere/
```

Because both pipelines use `growers/<slug>/farms/<slug>/fields/<slug>/` as the canonical anchor, an R2 consumer can walk the same tree and read `.john-deere.` files alongside neutral or other-source artifacts without path conflicts.

### Data root resolution precedence

The subskill resolves the writable data root in the same order as the R2 seed pipeline:

1. `JD_DATA_ROOT` (explicit override)
2. `/data/workspace/data/my-farm-advisor` (OpenClaw default)
3. `.runtime/my-farm-advisor/data/` (checkout-relative fallback)

This mirrors the R2 precedence: `R2_SEED_DATA_ROOT` → `/data/workspace/data/my-farm-advisor` → local `data/my-farm-advisor`. When both pipelines target the same root, their outputs live in the same canonical tree.

### Path mapping

| R2 canonical concept | John Deere normalized path |
|---|---|
| Grower metadata | `growers/<slug>/grower.john-deere.json` |
| Farm metadata | `growers/<slug>/farms/<slug>/farm.john-deere.json` |
| Farm boundaries | `growers/<slug>/farms/<slug>/boundaries/john-deere/` |
| Field metadata | `growers/<slug>/farms/<slug>/fields/<slug>/field.john-deere.json` |
| Field boundary | `growers/<slug>/farms/<slug>/fields/<slug>/boundary/field_boundary.john-deere.geojson` |
| Field manifests | `growers/<slug>/farms/<slug>/fields/<slug>/manifests/john-deere/` |
| Planting records | `growers/<slug>/farms/<slug>/fields/<slug>/planting/john-deere/<YYYY>/` |
| Harvest records | `growers/<slug>/farms/<slug>/fields/<slug>/harvest/john-deere/<YYYY>/` |
| Application records | `growers/<slug>/farms/<slug>/fields/<slug>/applications/john-deere/<YYYY>/` |
| Machine locations | `growers/<slug>/machine-data/locations/<machine_id>/john-deere/<YYYY>/` |

Raw API snapshots are kept under `growers/<slug>/source/john-deere/raw/...` and are invisible to R2 reporting unless an R2 script explicitly opts into source replay.

### Manifest output format

The subskill writes two manifest documents that an R2 pipeline could consume directly:

**Operation manifest** (`operation-statuses.json`):

```json
{
  "growerSlug": "iowa-demo-grower",
  "generatedAt": "2026-04-29T12:00:00Z",
  "operations": [
    {
      "operation": "organizations.list",
      "status": "accessible",
      "startTime": "2026-04-29T12:00:00Z",
      "endTime": "2026-04-29T12:00:01Z",
      "outputPaths": [
        "growers/iowa-demo-grower/source/john-deere/raw/organizations/list/2026/04/29/2026-04-29T12-00-00Z_list-all_page-1.json"
      ],
      "errorDetails": null,
      "requestContext": {}
    }
  ]
}
```

**Run manifest** (`latest-run.json` and `run-<timestamp>.json`):

```json
{
  "growerSlug": "iowa-demo-grower",
  "runId": "2026-04-29T12-00-00Z",
  "status": "completed",
  "startTime": "2026-04-29T12:00:00Z",
  "endTime": "2026-04-29T12:05:00Z",
  "totalDurationMs": 300000,
  "outputPaths": [...],
  "requestContext": {},
  "operations": [...],
  "statusCounts": {
    "accessible": 42,
    "unauthorized": 3,
    "empty": 1
  },
  "nextCheckpoint": {
    "lastSuccessfulRun": "2026-04-29T12-00-00Z",
    "operationCursorCount": 46,
    "outputPaths": [...]
  }
}
```

An R2 seed script could read `latest-run.json` from either:
- `growers/<slug>/source/john-deere/manifests/latest-run.json` (raw mirror)
- `growers/<slug>/manifests/john-deere/latest-run.json` (normalized mirror)

Both files contain the same payload.

### Out-of-scope statement

**R2 direct wiring is out of scope in v1.**

This subskill does not:
- Invoke R2 seed pipeline scripts.
- Implement `rsync --no-times` or object-storage sync semantics.
- Write neutral (non-source-scoped) filenames that would overwrite R2 seed data.
- Claim production R2 integration is complete.

Future R2 integration should require only configuration and path mapping changes, because the canonical tree shape, data root resolution, and manifest formats already align with R2 conventions.

## Operation registry statuses

Each API operation is recorded with one of the following statuses:

- `pending` - not yet attempted
- `accessible` - successful call with data returned
- `unauthorized` - 401/403 or missing scope
- `unsupported_by_sdk` - requested API not present in installed `deere-sdk`
- `unsupported_environment` - SDK/environment mismatch
- `empty` - successful call with no records
- `error` - unexpected failure
- `disabled_by_default` - write/destructive operation excluded from default export
- `skipped_by_checkpoint` - unchanged since last sync

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Missing JD_CLIENT_ID or JD_CLIENT_SECRET` | Environment variables are not set. | Export `JD_CLIENT_ID` and `JD_CLIENT_SECRET` before running the CLI, or pass `--client-id` and `--client-secret`. |
| `401 Unauthorized` during ingest or sync | Access token expired or refresh token invalid. | Run `jd init` again to refresh the token. If the issue persists, revoke the old token in the developer portal and re-authorize. |
| `403 Forbidden` on organization endpoints | The grower has not connected the application to their organization. | Ask the grower to approve the connection in the John Deere Operations Center or developer portal. |
| `unsupported_by_sdk` for field operations or work plans | The installed `deere-sdk` version does not expose those methods. | This is a known limitation. The operation is recorded in the manifest and the run continues. |
| Empty lists after successful API calls | The sandbox or production account has no data for that operation. | Verify the grower has data in the target environment. Check the operation status: `empty` means the call succeeded but returned no records. |
| `jd init` hangs waiting for callback | The browser did not redirect to `localhost:9090/callback`, or the port is in use. | Copy the authorization code from the browser URL and paste it into the CLI, or run `jd init --code <code>`. |
| Token file not found during sync | `jd init` was never run, or the token store path changed. | Run `jd doctor` to verify the token store path, then run `jd init` to create a new token. |
| Manifest shows many `unauthorized` statuses | The OAuth scopes granted during init do not cover all requested APIs. | Re-run `jd init` and ensure the application registration includes scopes such as `ag1`, `eq1`, `files`, `org2`, and `offline_access`. |

## Development

```bash
cd my-farm-advisor/data-sources/john-deere-ingestion
npm install
npm run build
npm test
```

All TypeScript tooling is isolated to this directory. There is no root-level `package.json` or `tsconfig.json`.

## Important notes

- This is a dev/portable v1 build. It is not production certified.
- Default ingest mode is read-only. Write, update, and delete operations are either excluded or marked `disabled_by_default`.
- If an endpoint is unauthorized or unsupported, the ingest continues and records the status in the manifest. It does not fail the full run.
