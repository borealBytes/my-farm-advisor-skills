import { describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

describe('CLI help', () => {
  it('prints usage text for --help', async () => {
    const result = await runCli(['--help'], { executableName: 'john-deere' });

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('Usage:');
    expect(result.output).toContain('john-deere');
    expect(result.output).toContain('init');
    expect(result.output).toContain('ingest');
    expect(result.output).toContain('sync');
    expect(result.output).toContain('registry');
    expect(result.output).toContain('webhook');
    expect(result.output).toContain('doctor');
    expect(result.output).toContain('paths');
    expect(result.output).toContain('john-deer');
  });
});
