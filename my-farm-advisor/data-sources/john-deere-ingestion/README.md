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
- Rotate `JD_CLIENT_SECRET` on a regular cadence. The skill reads it fresh on every run and does not cache it.
- The default token store persists refresh tokens in a portable file under the resolved data root. This is a dev/portable v1 default and is replaceable behind the `TokenStore` interface.
- Token storage files live under ignored runtime paths and must never be committed.

## Sandbox-first flow

1. Register an application in the John Deere developer portal and obtain a client ID and secret.
2. Set `JD_ENVIRONMENT=sandboxapi`.
3. Run `jd init`. The CLI prints an authorization URL. Open it in a browser or paste the returned code.
4. After token exchange, the CLI lists organizations and checks for required connection grants.
5. Run `jd registry` to see which APIs are accessible in the sandbox.
6. Run `jd ingest` to export raw and normalized data.
7. Only after sandbox validation should you switch to `JD_ENVIRONMENT=production`.

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

The default `FileTokenStore` saves tokens adjacent to the data root. This is suitable for development and portable setups. For production hardening, swap in an encrypted or keychain-backed implementation behind the `TokenStore` interface.

## R2-readiness boundary

- This subskill does not wire directly into the R2 seed pipeline in v1.
- The canonical tree shape and data root resolution are designed to align with R2 conventions, so future integration should require only configuration changes.
- Object-storage sync commands such as `rsync --no-times` belong in the R2 seed pipeline layer, not here.

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
