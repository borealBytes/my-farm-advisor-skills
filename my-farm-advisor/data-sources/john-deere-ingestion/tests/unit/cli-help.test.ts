import { describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

describe('CLI help', () => {
  it('prints usage text for --help', async () => {
    const result = await runCli(['--help']);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('Usage:');
    expect(result.output).toContain('john-deere');
  });
});
