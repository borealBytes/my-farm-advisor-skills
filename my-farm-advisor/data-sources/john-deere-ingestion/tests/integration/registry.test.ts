import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';
import type { OperationRegistryEntry } from '../../src/registry/index.js';

describe('registry CLI integration', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('prints and writes the full operation registry without credentials', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-registry-cli-'));
    tempRoots.push(tempRoot);
    const outputPath = path.join(tempRoot, 'registry', 'operations.json');

    const printed = await runCli(['registry'], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: tempRoot
      }
    });

    expect(printed.exitCode).toBe(0);

    const printedRegistry = JSON.parse(printed.output) as OperationRegistryEntry[];
    expect(printedRegistry.length).toBeGreaterThan(100);
    expect(printedRegistry.find((entry) => entry.apiGroup === 'organizations' && entry.operation === 'list')).toMatchObject({
      authMode: 'oauth',
      defaultEnabled: true,
      destructive: false,
      status: 'pending'
    });
    expect(
      printedRegistry.find(
        (entry) => entry.apiGroup === 'fieldOperations' && entry.operation === 'listAllWithMeasurements'
      )
    ).toMatchObject({
      sdkPath: 'deere.safe.fieldOperations.listAllWithMeasurements',
      status: 'unsupported_by_sdk'
    });
    expect(printedRegistry.find((entry) => entry.apiGroup === 'clients' && entry.operation === 'create')).toMatchObject({
      defaultEnabled: false,
      destructive: true,
      status: 'disabled_by_default'
    });
    expect(printedRegistry.find((entry) => entry.apiGroup === 'webhook' && entry.operation === 'list')).toBeDefined();

    const written = await runCli(['registry', '--output', outputPath], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: tempRoot
      }
    });

    expect(written.exitCode).toBe(0);
    expect(written.output).toContain(`Registry manifest written to ${outputPath}`);

    const writtenRegistry = JSON.parse(await readFile(outputPath, 'utf8')) as OperationRegistryEntry[];
    expect(writtenRegistry).toEqual(printedRegistry);
  });
});
