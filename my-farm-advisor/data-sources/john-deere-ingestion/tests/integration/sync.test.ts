import { access, mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

async function readJson(filePath: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(filePath, 'utf8')) as Record<string, unknown>;
}

describe('jd sync --mock', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('reuses the last checkpoint and skips unchanged mock data on the next run', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-sync-integration-'));
    tempRoots.push(tempRoot);

    const args = ['sync', '--mock', '--data-root', tempRoot, '--grower', 'demo-grower', '--org-id', 'org-123'];

    const firstRun = await runCli(args, {
      cwd: '/workspace/project',
      now: () => new Date('2026-05-01T00:00:00.000Z')
    });
    const secondRun = await runCli(args, {
      cwd: '/workspace/project',
      now: () => new Date('2026-05-02T00:00:00.000Z')
    });

    const secondRunManifestPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'manifests',
      'john-deere',
      'run-2026-05-02T00-00-00Z.json'
    );
    const checkpointPath = path.join(
      tempRoot,
      'growers',
      'demo-grower',
      'manifests',
      'john-deere',
      'checkpoints.json'
    );
    const rawOrganizationsDir = path.join(
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
      '01'
    );
    const skippedRawOrganizationPath = path.join(
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
      '02',
      '2026-05-02T00-00-00Z_list_org-123.json'
    );

    expect(firstRun.exitCode).toBe(0);
    expect(secondRun.exitCode).toBe(0);
    expect(secondRun.output).toContain('effectiveSince: 2026-05-01T00:00:00.000Z');

    await Promise.all([access(secondRunManifestPath), access(checkpointPath)]);

    const [secondRunManifest, checkpoint, rawOrganizationFiles] = await Promise.all([
      readJson(secondRunManifestPath),
      readJson(checkpointPath),
      readdir(rawOrganizationsDir)
    ]);

    expect(secondRunManifest).toMatchObject({
      growerSlug: 'demo-grower',
      nextCheckpoint: {
        lastSuccessfulRun: '2026-05-01T00:00:00.000Z'
      }
    });
    expect(secondRunManifest.statusCounts).toMatchObject({
      skipped_by_checkpoint: expect.any(Number),
      disabled_by_default: expect.any(Number),
      unsupported_by_sdk: expect.any(Number)
    });
    const skippedByCheckpoint = (secondRunManifest.statusCounts as Record<string, unknown>).skipped_by_checkpoint;
    expect(typeof skippedByCheckpoint).toBe('number');
    expect((skippedByCheckpoint as number) > 0).toBe(true);

    expect(checkpoint).toMatchObject({
      growerSlug: 'demo-grower',
      lastSuccessfulRun: '2026-05-01T00:00:00.000Z'
    });
    expect(rawOrganizationFiles).toEqual(['2026-05-01T00-00-00Z_list_org-123.json']);
    await expect(access(skippedRawOrganizationPath)).rejects.toBeDefined();
  });
});
