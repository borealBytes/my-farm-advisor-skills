import { mkdtemp, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { RegistryExecutor, type RegistryExecutorMockFixture } from '../../src/executor/registry-executor.js';
import { FileCheckpointStore } from '../../src/storage/checkpoint.js';
import type { OperationRegistryEntry, OperationRegistryStatus } from '../../src/registry/operations.js';

function createEntry(
  apiGroup: string,
  operation: string,
  overrides: Partial<OperationRegistryEntry> = {}
): OperationRegistryEntry {
  const destructive = ['create', 'update', 'delete', 'patch'].some((prefix) => operation.startsWith(prefix));

  return {
    apiGroup,
    operation,
    sdkPath: `deere.${apiGroup}.${operation}`,
    authMode: 'oauth',
    requiredScopes: destructive ? ['ag2'] : ['ag1'],
    entityScope: 'grower',
    defaultEnabled: !destructive,
    destructive,
    rawDestinationTemplate: `source/john-deere/raw/${apiGroup}/${operation}/{yyyy}/{mm}/{dd}/{timestamp}_{id-or-page}.json`,
    normalizedDestinationTemplate: `growers/{grower_slug}/${apiGroup}/${operation}.json`,
    status: destructive ? 'disabled_by_default' : 'pending',
    ...overrides
  };
}

async function readJson(filePath: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(filePath, 'utf8')) as Record<string, unknown>;
}

describe('RegistryExecutor', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('writes manifests for mixed statuses and keeps destructive operations excluded by default', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-registry-executor-'));
    tempRoots.push(tempRoot);

    const registry: OperationRegistryEntry[] = [
      createEntry('organizations', 'list'),
      createEntry('fields', 'list', { entityScope: 'field' }),
      createEntry('users', 'get', { entityScope: 'user' }),
      createEntry('workPlans', 'list', { status: 'unsupported_by_sdk', entityScope: 'farm_or_field' }),
      createEntry('mapLayers', 'list', { entityScope: 'farm_or_field' }),
      createEntry('clients', 'create', {
        authMode: 'oauth',
        entityScope: 'client',
        destructive: true,
        defaultEnabled: false,
        status: 'disabled_by_default'
      }),
      createEntry('products', 'list'),
      createEntry('flags', 'list', { entityScope: 'field' })
    ];
    const fixtures: Record<string, RegistryExecutorMockFixture> = {
      'organizations.list': {
        payload: [{ id: 'org-1', name: 'Acme Growers', updatedAt: '2026-04-29T12:00:00.000Z' }]
      },
      'fields.list': {
        status: 'empty',
        payload: []
      },
      'users.get': {
        status: 'unauthorized'
      },
      'mapLayers.list': {
        status: 'unsupported_environment'
      },
      'products.list': {
        payload: [{ id: 'prod-1', name: 'Starter Fertilizer', productType: 'fertilizer' }]
      },
      'flags.list': {
        status: 'error'
      }
    };
    const checkpointStore = new FileCheckpointStore({
      dataRoot: tempRoot,
      growerSlug: 'demo-grower'
    });

    await checkpointStore.save({
      growerSlug: 'demo-grower',
      lastSuccessfulRun: '2026-04-29T13:00:00.000Z',
      operationCursors: {
        'products.list': {
          updatedAt: '2026-04-29T13:00:00.000Z',
          cursor: 'cursor-products-1',
          fingerprint: 'fingerprint-products-1'
        }
      }
    });

    const executor = new RegistryExecutor({
      registry,
      checkpointStore,
      mockFixtures: fixtures
    });

    const result = await executor.execute({
      growerSlug: 'demo-grower',
      orgId: 'org-1',
      dataRoot: tempRoot,
      since: '2026-04-29T00:00:00.000Z',
      mock: true
    });

    const statuses = Object.fromEntries(result.operations.map((operation) => [operation.operation, operation.status]));

    expect(statuses).toEqual<Record<string, OperationRegistryStatus>>({
      'organizations.list': 'accessible',
      'fields.list': 'empty',
      'users.get': 'unauthorized',
      'workPlans.list': 'unsupported_by_sdk',
      'mapLayers.list': 'unsupported_environment',
      'clients.create': 'disabled_by_default',
      'products.list': 'skipped_by_checkpoint',
      'flags.list': 'error'
    });

    const runManifestPath = result.runManifestPaths.find((filePath) => filePath.endsWith('latest-run.json'));
    const operationManifestPath = result.operationManifestPaths.find((filePath) =>
      filePath.endsWith('operation-statuses.json')
    );
    const checkpointPath = result.checkpointPaths.find((filePath) => filePath.endsWith('checkpoints.json'));

    expect(runManifestPath).toBeDefined();
    expect(operationManifestPath).toBeDefined();
    expect(checkpointPath).toBeDefined();

    const runManifest = await readJson(runManifestPath ?? '');
    const operationManifest = await readJson(operationManifestPath ?? '');
    const checkpoint = await readJson(checkpointPath ?? '');

    expect(runManifest.status).toBe('completed_with_errors');
    expect(runManifest.statusCounts).toMatchObject({
      accessible: 1,
      empty: 1,
      unauthorized: 1,
      unsupported_by_sdk: 1,
      unsupported_environment: 1,
      disabled_by_default: 1,
      skipped_by_checkpoint: 1,
      error: 1
    });
    expect(operationManifest.operations).toHaveLength(8);

    const growerFile = path.join(tempRoot, 'growers', 'demo-grower', 'grower.john-deere.json');
    const growerPayload = await readJson(growerFile);

    expect(growerPayload).toMatchObject({
      growerSlug: 'demo-grower',
      displayName: 'Acme Growers',
      deereId: 'org-1',
      sourceApi: 'organizations',
      sourceOperation: 'list'
    });

    const organizationsRecord = result.operations.find((operation) => operation.operation === 'organizations.list');
    expect(organizationsRecord?.outputPaths.some((outputPath) => outputPath.endsWith('grower.john-deere.json'))).toBe(true);
    expect(organizationsRecord?.outputPaths.some((outputPath) => /source\/john-deere\/raw\/organizations\/list\//.test(outputPath))).toBe(
      true
    );

    const destructiveRecord = result.operations.find((operation) => operation.operation === 'clients.create');
    expect(destructiveRecord?.outputPaths).toEqual([]);
    expect(destructiveRecord?.errorDetails).toMatchObject({
      reason: 'Operation is destructive or opt-in and was not forced.',
      destructive: true
    });

    expect(checkpoint).toMatchObject({
      growerSlug: 'demo-grower',
      lastSuccessfulRun: expect.any(String),
      operationCursors: {
        'organizations.list': {
          updatedAt: expect.any(String),
          fingerprint: expect.any(String)
        },
        'fields.list': {
          updatedAt: expect.any(String),
          fingerprint: expect.any(String)
        },
        'products.list': {
          updatedAt: '2026-04-29T13:00:00.000Z',
          cursor: 'cursor-products-1',
          fingerprint: 'fingerprint-products-1'
        }
      }
    });
    expect(checkpoint.operationCursors).not.toHaveProperty('users.get');
    expect(checkpoint.operationCursors).not.toHaveProperty('flags.list');
  });
});
