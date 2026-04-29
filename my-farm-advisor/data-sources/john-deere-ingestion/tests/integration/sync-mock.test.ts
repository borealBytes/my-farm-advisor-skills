import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';
import type { RegistryExecutorMockFixture } from '../../src/executor/registry-executor.js';
import type { OperationManifestDocument, RunManifestDocument } from '../../src/storage/manifest.js';

import { readJsonFile, readJsonFixture, selectRegistryEntries } from './helpers.js';

async function countRawFiles(rawRoot: string): Promise<number> {
  const entries = await readdir(rawRoot, { recursive: true, withFileTypes: true });
  return entries.filter((entry) => entry.isFile()).length;
}

describe('sync --mock integration', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('reads the checkpoint and skips unchanged operations in mock mode', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-sync-mock-'));
    tempRoots.push(tempRoot);

    const [organizations, farms, fields, boundaries, fieldOperations, equipment, products, machineLocations, emptyResponse] =
      await Promise.all([
        readJsonFixture<Record<string, unknown>>('orgs.json'),
        readJsonFixture<Record<string, unknown>>('farms.json'),
        readJsonFixture<Record<string, unknown>>('fields.json'),
        readJsonFixture<Record<string, unknown>>('boundaries.json'),
        readJsonFixture<Record<string, unknown>>('field-operations.json'),
        readJsonFixture<Record<string, unknown>>('equipment.json'),
        readJsonFixture<Record<string, unknown>>('products.json'),
        readJsonFixture<Record<string, unknown>>('machine-data.json'),
        readJsonFixture<Record<string, unknown>>('empty-response.json')
      ]);

    const registry = selectRegistryEntries([
      'organizations.list',
      'farms.list',
      'fields.list',
      'boundaries.list',
      'fieldOperations.list',
      'equipment.list',
      'products.list',
      'machineLocations.get',
      'files.list'
    ]);
    const fixtures: Record<string, RegistryExecutorMockFixture> = {
      'organizations.list': { payload: organizations },
      'farms.list': { payload: farms },
      'fields.list': { payload: fields },
      'boundaries.list': { payload: boundaries },
      'fieldOperations.list': { payload: fieldOperations },
      'equipment.list': { payload: equipment },
      'products.list': { payload: products },
      'machineLocations.get': { payload: machineLocations },
      'files.list': { status: 'empty', payload: emptyResponse }
    };

    const baseOptions = {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: tempRoot,
        JD_GROWER: 'iowa-demo-grower'
      },
      registry,
      mockFixtures: fixtures
    } as const;

    const initial = await runCli(['ingest', '--mock', '--org-id', 'org-12345'], {
      ...baseOptions,
      now: () => new Date('2026-05-02T10:00:00.000Z')
    });
    expect(initial.exitCode).toBe(0);

    const rawRoot = path.join(tempRoot, 'growers', 'iowa-demo-grower', 'source', 'john-deere', 'raw');
    const rawFilesBeforeSync = await countRawFiles(rawRoot);

    const sync = await runCli(['sync', '--mock', '--org-id', 'org-12345', '--since', '2026-05-01T00:00:00.000Z'], {
      ...baseOptions,
      now: () => new Date('2026-05-03T08:00:00.000Z')
    });

    expect(sync.exitCode).toBe(0);
    expect(sync.output).toContain('John Deere sync');
    expect(sync.output).toContain('status: completed');
    expect(sync.output).toContain('"skipped_by_checkpoint":9');

    const rawFilesAfterSync = await countRawFiles(rawRoot);
    expect(rawFilesAfterSync).toBe(rawFilesBeforeSync);

    const growerRoot = path.join(tempRoot, 'growers', 'iowa-demo-grower');
    const runManifest = await readJsonFile<RunManifestDocument>(path.join(growerRoot, 'manifests', 'john-deere', 'latest-run.json'));
    const operationManifest = await readJsonFile<OperationManifestDocument>(
      path.join(growerRoot, 'manifests', 'john-deere', 'operation-statuses.json')
    );

    expect(runManifest.status).toBe('completed');
    expect(runManifest.statusCounts).toMatchObject({
      skipped_by_checkpoint: registry.length
    });
    expect(operationManifest.operations.every((operation) => operation.status === 'skipped_by_checkpoint')).toBe(true);
  });
});
