import { describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

describe('CLI integration routing', () => {
  it('prints resolved paths without requiring credentials', async () => {
    const result = await runCli(['paths', '--dry-run'], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: '/tmp/jd-data',
        JD_GROWER: 'iowa-demo-grower'
      }
    });

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('Resolved John Deere paths');
    expect(result.output).toContain('dataRoot: /tmp/jd-data');
    expect(result.output).toContain('tokenStorePath: /tmp/jd-data/tokens/iowa-demo-grower.json');
  });

  it('prints an auth URL for init --dry-run with supplied credentials', async () => {
    const result = await runCli(['init', '--dry-run', '--environment', 'sandboxapi'], {
      cwd: '/workspace/project',
      env: {
        JD_CLIENT_ID: 'client-123',
        JD_CLIENT_SECRET: 'secret-456',
        JD_DATA_ROOT: '/tmp/jd-data'
      },
      fetch: async () =>
        new Response(
          JSON.stringify({
            issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
            authorization_endpoint:
              'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize',
            token_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token',
            revocation_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke'
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' }
          }
        )
    });

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('authorizationUrl: https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize?');
    expect(result.output).toContain('client_id=client-123');
    expect(result.output).toContain('dry-run: token exchange skipped; no token files written.');
  });

  it('fails gracefully when live ingest credentials are missing', async () => {
    const result = await runCli(['ingest'], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: '/tmp/jd-data'
      }
    });

    expect(result.exitCode).toBe(1);
    expect(result.output).toContain("Cannot run 'ingest' because required credentials are missing.");
    expect(result.output).toContain('Missing: JD_CLIENT_ID, JD_CLIENT_SECRET');
    expect(result.output).not.toContain('Error:');
    expect(result.output).not.toContain('at ');
  });
});
