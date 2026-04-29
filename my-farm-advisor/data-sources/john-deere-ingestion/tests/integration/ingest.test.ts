import { access, mkdtemp, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

async function readJson(filePath: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(filePath, 'utf8')) as Record<string, unknown>;
}

describe('jd ingest --mock', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('writes deterministic raw, normalized, manifest, and checkpoint outputs', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-ingest-integration-'));
    tempRoots.push(tempRoot);

    const result = await runCli(
      ['ingest', '--mock', '--data-root', tempRoot, '--grower', 'demo-grower', '--org-id', 'org-123'],
      {
        cwd: '/workspace/project',
        now: () => new Date('2026-05-01T00:00:00.000Z')
      }
    );

    const runManifestPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'manifests',
      'john-deere',
      'run-2026-05-01T00-00-00Z.json'
    );
    const checkpointPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'manifests',
      'john-deere',
      'checkpoints.json'
    );
    const rawOrganizationPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'source',
      'john-deere',
      'raw',
      'organizations',
      'list',
      '2026',
      '05',
      '01',
      '2026-05-01T00-00-00Z_list_org-123.json'
    );
    const growerFilePath = path.join(tempRoot, 'growers', 'demo-grower', 'grower.john-deere.json');
    const plantingOperationPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'farms',
      'mock-farm-1',
      'fields',
      'mock-field-1',
      'planting',
      'john-deere',
      '2026',
      '2026-04-01T00-00-00Z_planting_mock-field-op-1.john-deere.json'
    );

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain(`runManifest: ${runManifestPath}`);
    expect(result.output).toContain(`checkpoint: ${checkpointPath}`);

    await Promise.all([
      access(runManifestPath),
      access(checkpointPath),
      access(rawOrganizationPath),
      access(growerFilePath),
      access(plantingOperationPath)
    ]);

    const [runManifest, growerFile, plantingOperation] = await Promise.all([
      readJson(runManifestPath),
      readJson(growerFilePath),
      readJson(plantingOperationPath)
    ]);

    expect(runManifest).toMatchObject({
      growerSlug: 'demo-grower',
      status: expect.any(String),
      totalDurationMs: expect.any(Number),
      nextCheckpoint: {
        lastSuccessfulRun: '2026-05-01T00:00:00.000Z',
        outputPaths: ['growers/demo-grower/source/john-deere/manifests/checkpoints.json', 'growers/demo-grower/manifests/john-deere/checkpoints.json']
      }
    });
    expect(runManifest.statusCounts).toMatchObject({
      accessible: expect.any(Number),
      disabled_by_default: expect.any(Number),
      unsupported_by_sdk: expect.any(Number)
    });
    expect(Array.isArray(runManifest.outputPaths)).toBe(true);
    expect((runManifest.outputPaths as unknown[]).length).toBeGreaterThan(0);

    expect(growerFile).toMatchObject({
      growerSlug: 'demo-grower',
      displayName: 'Organization org-123',
      deereId: 'org-123'
    });
    expect(plantingOperation).toMatchObject({
      farmSlug: 'mock-farm-1',
      fieldSlug: 'mock-field-1',
      deereId: 'mock-field-op-1',
      operationType: 'Planting',
      occurredAt: '2026-04-01T00:00:00.000Z'
    });
  });
});
