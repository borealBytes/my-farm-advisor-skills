import path from 'node:path';

import { refreshAccessToken as refreshStoredAuthToken } from '../auth/init.js';
import { DeereSdkClient } from '../client/deere-client.js';
import type { CliConfig } from '../config.js';
import {
  RegistryExecutor,
  type RegistryExecutorMockFixture,
  type RegistryExecutorResult
} from '../executor/registry-executor.js';
import { buildGrowerPaths, formatJohnDeereTimestampPrefix } from '../paths.js';
import type { OperationRegistryEntry } from '../registry/index.js';
import { FileCheckpointStore } from '../storage/checkpoint.js';
import { FileTokenStore } from '../tokens/file-store.js';
import type { StoredToken, TokenStore } from '../tokens/store.js';

export interface CommandExecutionDependencies {
  fetch?: typeof fetch;
  tokenStore?: TokenStore;
  now?: () => Date;
  registry?: readonly OperationRegistryEntry[];
  mockFixtures?: Record<string, RegistryExecutorMockFixture>;
}

export interface CommandExecutionResult {
  mode: 'ingest' | 'sync';
  effectiveSince?: string;
  runManifestPath: string;
  latestRunManifestPath: string;
  checkpointPath: string;
  outputLines: string[];
  executorResult?: RegistryExecutorResult;
}

export interface RunOrchestratedCommandOptions {
  mode: 'ingest' | 'sync';
  config: CliConfig;
  effectiveSince?: string;
  dependencies?: CommandExecutionDependencies;
}

const MOCK_ORG_ID = 'mock-org-1';
const TOKEN_REFRESH_SKEW_MS = 60_000;

export async function runIngestCommand(
  config: CliConfig,
  dependencies: CommandExecutionDependencies = {}
): Promise<CommandExecutionResult> {
  return runOrchestratedCommand({
    mode: 'ingest',
    config,
    effectiveSince: config.force ? undefined : config.since,
    dependencies
  });
}

export async function runOrchestratedCommand(
  options: RunOrchestratedCommandOptions
): Promise<CommandExecutionResult> {
  const now = options.dependencies?.now ?? (() => new Date());
  const growerPaths = buildGrowerPaths({
    dataRoot: options.config.dataRoot,
    growerSlug: options.config.grower
  });
  const plannedRunId = formatJohnDeereTimestampPrefix(now());
  const runManifestPath = path.join(growerPaths.manifestsDir, `run-${plannedRunId}.json`);
  const latestRunManifestPath = path.join(growerPaths.manifestsDir, 'latest-run.json');
  const checkpointPath = path.join(growerPaths.manifestsDir, 'checkpoints.json');
  const orgId = resolveOrgId(options.config);

  if (options.config.dryRun) {
    return {
      mode: options.mode,
      effectiveSince: options.effectiveSince,
      runManifestPath,
      latestRunManifestPath,
      checkpointPath,
      outputLines: buildDryRunSummary({
        mode: options.mode,
        config: options.config,
        orgId,
        effectiveSince: options.effectiveSince,
        runManifestPath,
        checkpointPath
      })
    };
  }

  const checkpointStore = new FileCheckpointStore({
    dataRoot: options.config.dataRoot,
    growerSlug: options.config.grower
  });
  const tokenStore = options.dependencies?.tokenStore ?? new FileTokenStore({ dataRoot: options.config.dataRoot });
  const client = options.config.mock
    ? undefined
    : await createLiveClient({
        config: options.config,
        tokenStore,
        fetch: options.dependencies?.fetch,
        now
      });
  const executor = new RegistryExecutor({
    client,
    checkpointStore,
    registry: options.dependencies?.registry,
    mockFixtures: options.dependencies?.mockFixtures,
    now
  });
  const executorResult = await executor.execute({
    growerSlug: options.config.grower,
    orgId,
    dataRoot: options.config.dataRoot,
    since: options.effectiveSince,
    mock: options.config.mock,
    force: options.config.force
  });
  const actualRunManifestPath = selectGrowerManifestPath(
    executorResult.runManifestPaths,
    growerPaths.manifestsDir,
    /^run-.*\.json$/
  ) ?? runManifestPath;

  return {
    mode: options.mode,
    effectiveSince: options.effectiveSince,
    runManifestPath: actualRunManifestPath,
    latestRunManifestPath,
    checkpointPath,
    executorResult,
    outputLines: buildExecutionSummary({
      mode: options.mode,
      config: options.config,
      orgId,
      effectiveSince: options.effectiveSince,
      runManifestPath: actualRunManifestPath,
      latestRunManifestPath,
      checkpointPath,
      result: executorResult
    })
  };
}

async function createLiveClient(options: {
  config: CliConfig;
  tokenStore: TokenStore;
  fetch?: typeof fetch;
  now: () => Date;
}): Promise<DeereSdkClient> {
  const token = await resolveStoredToken(options);

  return new DeereSdkClient({
    accessToken: token.accessToken,
    environment: options.config.environment,
    hateoas: options.config.hateoas,
    fetch: options.fetch,
    refresh: {
      tokenStore: options.tokenStore,
      tokenStoreKey: {
        grower: options.config.grower,
        profile: options.config.profile
      },
      clientId: requireConfigString(options.config.clientId, 'JD_CLIENT_ID'),
      clientSecret: requireConfigString(options.config.clientSecret, 'JD_CLIENT_SECRET')
    }
  });
}

async function resolveStoredToken(options: {
  config: CliConfig;
  tokenStore: TokenStore;
  fetch?: typeof fetch;
  now: () => Date;
}): Promise<StoredToken> {
  const tokenKey = {
    grower: options.config.grower,
    profile: options.config.profile
  };
  const storedToken = await options.tokenStore.load(tokenKey);

  if (!storedToken) {
    throw new Error(
      `No John Deere token is stored for grower '${options.config.grower}'. Run 'jd init --org-id ${options.config.orgId ?? '<org-id>'}' first.`
    );
  }

  if (!isTokenExpired(storedToken, options.now())) {
    return storedToken;
  }

  return refreshStoredAuthToken({
    config: options.config,
    fetch: options.fetch,
    tokenStore: options.tokenStore,
    now: options.now
  });
}

function isTokenExpired(token: StoredToken, referenceTime: Date): boolean {
  const expiresAtTime = Date.parse(token.expiresAt);

  if (Number.isNaN(expiresAtTime)) {
    return false;
  }

  return expiresAtTime <= referenceTime.getTime() + TOKEN_REFRESH_SKEW_MS;
}

function resolveOrgId(config: CliConfig): string {
  const orgId = config.orgId?.trim();

  if (orgId) {
    return orgId;
  }

  if (config.mock) {
    return MOCK_ORG_ID;
  }

  throw new Error("Missing John Deere organization id. Supply --org-id or set JD_ORG_ID.");
}

function requireConfigString(value: string | undefined, name: string): string {
  if (!value?.trim()) {
    throw new Error(`Missing required John Deere configuration value ${name}.`);
  }

  return value;
}

function selectGrowerManifestPath(paths: readonly string[], manifestsDir: string, pattern: RegExp): string | undefined {
  return paths.find((filePath) => path.dirname(filePath) === manifestsDir && pattern.test(path.basename(filePath)));
}

function buildDryRunSummary(options: {
  mode: 'ingest' | 'sync';
  config: CliConfig;
  orgId: string;
  effectiveSince?: string;
  runManifestPath: string;
  checkpointPath: string;
}): string[] {
  return [
    `John Deere ${options.mode}`,
    `environment: ${options.config.environment}`,
    `grower: ${options.config.grower}`,
    `orgId: ${options.orgId}`,
    `requestedSince: ${options.config.since ?? 'not-set'}`,
    `effectiveSince: ${options.effectiveSince ?? 'not-set'}`,
    `mock: ${String(options.config.mock)}`,
    `force: ${String(options.config.force)}`,
    `hateoas: ${String(options.config.hateoas)}`,
    `plannedRunManifest: ${options.runManifestPath}`,
    `plannedCheckpoint: ${options.checkpointPath}`,
    'dry-run: no manifests, checkpoints, raw payloads, or normalized files written.'
  ];
}

function buildExecutionSummary(options: {
  mode: 'ingest' | 'sync';
  config: CliConfig;
  orgId: string;
  effectiveSince?: string;
  runManifestPath: string;
  latestRunManifestPath: string;
  checkpointPath: string;
  result: RegistryExecutorResult;
}): string[] {
  return [
    `John Deere ${options.mode}`,
    `environment: ${options.config.environment}`,
    `grower: ${options.config.grower}`,
    `orgId: ${options.orgId}`,
    `requestedSince: ${options.config.since ?? 'not-set'}`,
    `effectiveSince: ${options.effectiveSince ?? 'not-set'}`,
    `mock: ${String(options.config.mock)}`,
    `force: ${String(options.config.force)}`,
    `hateoas: ${String(options.config.hateoas)}`,
    `status: ${options.result.runManifest.status}`,
    `totalDurationMs: ${String(options.result.runManifest.totalDurationMs)}`,
    `statusCounts: ${JSON.stringify(options.result.runManifest.statusCounts)}`,
    `runManifest: ${options.runManifestPath}`,
    `latestRunManifest: ${options.latestRunManifestPath}`,
    `checkpoint: ${options.checkpointPath}`,
    `nextCheckpoint: ${options.result.runManifest.nextCheckpoint.lastSuccessfulRun ?? 'not-set'}`,
    `outputPathCount: ${String(options.result.runManifest.outputPaths.length)}`
  ];
}
