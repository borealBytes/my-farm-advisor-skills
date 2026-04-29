import { mkdtemp, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { describe, expect, it } from 'vitest';

import {
  buildFieldPaths,
  buildMachineDataPaths,
  buildNormalizedTreePaths,
  buildRawPayloadPath,
  createDeereSlug,
  createMockNormalizedTree,
  formatJohnDeereTimestampPrefix,
  resolveDataRoot,
  slugifyDeereName
} from '../../src/paths.js';

describe('resolveDataRoot', () => {
  it('prefers JD_DATA_ROOT when provided', () => {
    const result = resolveDataRoot({
      env: { JD_DATA_ROOT: '/tmp/jd-root' },
      pathExists: () => true,
      moduleDir: '/repo/my-farm-advisor/data-sources/john-deere-ingestion/src'
    });

    expect(result).toBe('/tmp/jd-root');
  });

  it('falls back to workspace data root when available', () => {
    const result = resolveDataRoot({
      env: {},
      pathExists: (candidatePath) => candidatePath === '/data/workspace/data/my-farm-advisor',
      moduleDir: '/repo/my-farm-advisor/data-sources/john-deere-ingestion/src'
    });

    expect(result).toBe('/data/workspace/data/my-farm-advisor');
  });

  it('falls back to checkout runtime data root when env and workspace are unavailable', () => {
    const result = resolveDataRoot({
      env: {},
      pathExists: () => false,
      moduleDir: '/repo/my-farm-advisor/data-sources/john-deere-ingestion/src'
    });

    expect(result).toBe('/repo/.runtime/my-farm-advisor/data');
  });
});

describe('slug generation', () => {
  it('slugifies Deere display names into kebab case', () => {
    expect(slugifyDeereName('  North 40 / Pivot #7  ')).toBe('north-40-pivot-7');
    expect(slugifyDeereName('São Field ++')).toBe('sao-field');
  });

  it('appends Deere ID only on collision', () => {
    expect(
      createDeereSlug({
        displayName: 'North Field',
        deereId: 'FIELD-123',
        existingSlugs: ['south-field']
      })
    ).toBe('north-field');

    expect(
      createDeereSlug({
        displayName: 'North Field',
        deereId: 'FIELD-123',
        existingSlugs: ['north-field']
      })
    ).toBe('north-field-field-123');
  });
});

describe('raw and normalized path mapping', () => {
  it('formats ISO-safe timestamp prefixes and raw payload paths', () => {
    const fetchedAt = new Date('2026-04-28T14:05:06.000Z');

    expect(formatJohnDeereTimestampPrefix(fetchedAt)).toBe('2026-04-28T14-05-06Z');

    const rawPath = buildRawPayloadPath({
      dataRoot: '/data/root',
      growerSlug: 'iowa-demo-grower',
      apiGroup: 'Field Operations',
      operation: 'List All',
      fetchedAt,
      idOrPage: 'Page 2'
    });

    expect(rawPath).toBe(
      '/data/root/growers/iowa-demo-grower/source/john-deere/raw/field-operations/list-all/2026/04/28/2026-04-28T14-05-06Z_list-all_page-2.json'
    );
  });

  it('builds normalized field and machine year folders with year segments', () => {
    const fieldPaths = buildFieldPaths({
      dataRoot: '/data/root',
      growerSlug: 'grower-a',
      farmSlug: 'farm-a',
      fieldSlug: 'field-a',
      year: 2025
    });

    expect(fieldPaths.plantingYearDir).toBe(
      '/data/root/growers/grower-a/farms/farm-a/fields/field-a/planting/john-deere/2025'
    );
    expect(fieldPaths.sprayingDir).toBe(
      '/data/root/growers/grower-a/farms/farm-a/fields/field-a/applications/john-deere/2025/spraying'
    );

    const machinePaths = buildMachineDataPaths({
      dataRoot: '/data/root',
      growerSlug: 'grower-a',
      machineId: 'machine-77',
      year: 2025
    });

    expect(machinePaths.locationsYearDir).toBe(
      '/data/root/growers/grower-a/machine-data/locations/machine-77/john-deere/2025'
    );
    expect(machinePaths.engineHoursDir).toBe(
      '/data/root/growers/grower-a/machine-data/engine-hours/machine-77/john-deere'
    );
  });
});

describe('mock tree creation', () => {
  it('creates the grower, farm, and field John Deere tree contract', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-paths-'));

    try {
      const tree = await createMockNormalizedTree({
        dataRoot: tempRoot,
        growerSlug: 'grower-a',
        farmSlug: 'farm-a',
        fieldSlug: 'field-a',
        year: 2025
      });

      const normalizedTree = buildNormalizedTreePaths({
        dataRoot: tempRoot,
        growerSlug: 'grower-a',
        farmSlug: 'farm-a',
        fieldSlug: 'field-a',
        year: 2025
      });

      expect(tree).toEqual(normalizedTree);

      const directoriesToCheck = [
        tree.grower.equipmentDir,
        tree.grower.connectionsDir,
        tree.grower.aempDir,
        tree.farm.boundariesDir,
        tree.farm.workPlansDir,
        tree.field.sprayingDir,
        tree.field.fertilizerDir,
        tree.field.otherApplicationsDir,
        tree.field.machineLocationsYearDir,
        tree.field.alertsYearDir
      ];

      await Promise.all(
        directoriesToCheck.map(async (directoryPath) => {
          const details = await stat(directoryPath);
          expect(details.isDirectory()).toBe(true);
        })
      );
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });
});
