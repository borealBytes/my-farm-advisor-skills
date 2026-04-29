import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';
import type { RegistryExecutorMockFixture } from '../../src/executor/registry-executor.js';
import type { OperationManifestDocument, RunManifestDocument } from '../../src/storage/manifest.js';

import { readJsonFile, readJsonFixture, selectRegistryEntries } from './helpers.js';

describe('ingest --mock integration', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('runs mock ingest with realistic fixtures and writes the tree plus manifests', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-ingest-mock-'));
    tempRoots.push(tempRoot);

    const [
      organizations,
      farms,
      fields,
      boundaries,
      fieldOperations,
      equipment,
      products,
      machineLocations,
      emptyResponse,
      unauthorizedResponse
    ] = await Promise.all([
      readJsonFixture<Record<string, unknown>>('orgs.json'),
      readJsonFixture<Record<string, unknown>>('farms.json'),
      readJsonFixture<Record<string, unknown>>('fields.json'),
      readJsonFixture<Record<string, unknown>>('boundaries.json'),
      readJsonFixture<Record<string, unknown>>('field-operations.json'),
      readJsonFixture<Record<string, unknown>>('equipment.json'),
      readJsonFixture<Record<string, unknown>>('products.json'),
      readJsonFixture<Record<string, unknown>>('machine-data.json'),
      readJsonFixture<Record<string, unknown>>('empty-response.json'),
      readJsonFixture<Record<string, unknown>>('unauthorized-response.json')
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
      'files.list',
      'notifications.list'
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
      'files.list': { status: 'empty', payload: emptyResponse },
      'notifications.list': { status: 'unauthorized', error: unauthorizedResponse }
    };

    const result = await runCli(['ingest', '--mock', '--org-id', 'org-12345'], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: tempRoot,
        JD_GROWER: 'iowa-demo-grower'
      },
      registry,
      mockFixtures: fixtures,
      now: () => new Date('2026-05-02T10:00:00.000Z')
    });

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('John Deere ingest');
    expect(result.output).toContain('mock: true');
    expect(result.output).toContain('status: completed_with_warnings');

    const growerRoot = path.join(tempRoot, 'growers', 'iowa-demo-grower');
    const growerFile = path.join(growerRoot, 'grower.john-deere.json');
    const farmFile = path.join(growerRoot, 'farms', 'north-farm', 'farm.john-deere.json');
    const fieldFile = path.join(growerRoot, 'farms', 'north-farm', 'fields', 'north-80', 'field.john-deere.json');
    const boundaryFile = path.join(
      growerRoot,
      'farms',
      'north-farm',
      'fields',
      'north-80',
      'boundary',
      'field_boundary.john-deere.geojson'
    );
    const plantingFile = path.join(
      growerRoot,
      'farms',
      'north-farm',
      'fields',
      'north-80',
      'planting',
      'john-deere',
      '2026',
      '2026-03-15T14-30-00Z_planting_plant-2026-north-80.john-deere.json'
    );
    const operationsFile = path.join(
      growerRoot,
      'farms',
      'north-farm',
      'fields',
      'north-80',
      'operations',
      'john-deere',
      '2026',
      '2026-03-15T14-30-00Z_planting_plant-2026-north-80.john-deere.json'
    );
    const equipmentFile = path.join(growerRoot, 'equipment', 'john-deere', 's780-combine.john-deere.json');
    const productFile = path.join(
      growerRoot,
      'products',
      'john-deere',
      'fertilizer',
      'starter-fertilizer-28-0-0.john-deere.json'
    );
    const runManifestPath = path.join(growerRoot, 'manifests', 'john-deere', 'latest-run.json');
    const operationManifestPath = path.join(growerRoot, 'manifests', 'john-deere', 'operation-statuses.json');

    const [
      growerPayload,
      farmPayload,
      fieldPayload,
      boundaryPayload,
      plantingPayload,
      equipmentPayload,
      productPayload,
      runManifest,
      operationManifest,
      operationsPayload
    ] = await Promise.all([
      readJsonFile<Record<string, unknown>>(growerFile),
      readJsonFile<Record<string, unknown>>(farmFile),
      readJsonFile<Record<string, unknown>>(fieldFile),
      readJsonFile<Record<string, unknown>>(boundaryFile),
      readJsonFile<Record<string, unknown>>(plantingFile),
      readJsonFile<Record<string, unknown>>(equipmentFile),
      readJsonFile<Record<string, unknown>>(productFile),
      readJsonFile<RunManifestDocument>(runManifestPath),
      readJsonFile<OperationManifestDocument>(operationManifestPath),
      readJsonFile<Record<string, unknown>>(operationsFile)
    ]);

    const rawMachineRelativePath =
      operationManifest.operations.find((operation) => operation.operation === 'machineLocations.get')?.outputPaths[0] ?? '';
    const rawMachinePayload = await readJsonFile<Record<string, unknown>>(path.join(tempRoot, rawMachineRelativePath));

    expect(growerPayload).toMatchObject({
      deereId: 'org-12345',
      displayName: 'Prairie View Farms Cooperative',
      sourceApi: 'organizations'
    });
    expect(farmPayload).toMatchObject({ deereId: 'farm-9001', farmSlug: 'north-farm' });
    expect(fieldPayload).toMatchObject({ deereId: 'field-101', fieldSlug: 'north-80', farmSlug: 'north-farm' });
    expect(boundaryPayload).toMatchObject({ deereId: 'boundary-101', type: 'FeatureCollection' });
    expect(plantingPayload).toMatchObject({
      deereId: 'plant-2026-north-80',
      category: 'planting',
      fieldSlug: 'north-80',
      farmSlug: 'north-farm'
    });
    expect(operationsPayload).toMatchObject({
      deereId: 'plant-2026-north-80',
      category: 'operations'
    });
    expect(equipmentPayload).toMatchObject({ deereId: 'equipment-7810', displayName: 'S780 Combine' });
    expect(productPayload).toMatchObject({
      deereId: 'product-28-0-0',
      displayName: 'Starter Fertilizer 28-0-0',
      productCategory: 'fertilizer'
    });
    expect(rawMachinePayload).toMatchObject({
      values: [
        expect.objectContaining({
          machineId: 'machine-s780'
        })
      ]
    });

    expect(runManifest.status).toBe('completed_with_warnings');
    expect(runManifest.statusCounts).toMatchObject({
      accessible: 8,
      empty: 1,
      unauthorized: 1
    });
    expect(operationManifest.operations).toHaveLength(registry.length);
    expect(operationManifest.operations.find((operation) => operation.operation === 'files.list')?.status).toBe('empty');
    expect(operationManifest.operations.find((operation) => operation.operation === 'notifications.list')?.status).toBe(
      'unauthorized'
    );
    expect(rawMachineRelativePath).toMatch(
      /^growers\/iowa-demo-grower\/source\/john-deere\/raw\/machinelocations\/get\/2026\/05\/02\/2026-05-02T10-00-00Z_get_.+\.json$/
    );
  });
});
