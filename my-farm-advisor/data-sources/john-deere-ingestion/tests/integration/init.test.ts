import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Readable } from 'node:stream';

import { describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';
import type { StoredToken } from '../../src/tokens/store.js';

const DISCOVERY_URL =
  'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/.well-known/oauth-authorization-server';
const TOKEN_ENDPOINT = 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token';

describe('init CLI integration', () => {
  it('runs the full mocked init flow, persists tokens, and reports org connection status', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-init-flow-'));

    try {
      const result = await runCli(['init'], {
        cwd: '/workspace/project',
        env: {
          JD_CLIENT_ID: 'client-123',
          JD_CLIENT_SECRET: 'secret-456',
          JD_DATA_ROOT: tempRoot,
          JD_GROWER: 'Iowa Demo Grower'
        },
        stdin: Readable.from(['manual-init-code\n']),
        fetch: async (input: string | URL | Request, init?: RequestInit) => {
          const url = String(input);

          if (url === DISCOVERY_URL) {
            return new Response(
              JSON.stringify({
                issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
                authorization_endpoint:
                  'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize',
                token_endpoint: TOKEN_ENDPOINT,
                revocation_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke'
              }),
              {
                status: 200,
                headers: { 'content-type': 'application/json' }
              }
            );
          }

          if (url === TOKEN_ENDPOINT) {
            const body = init?.body as URLSearchParams;

            expect(body.get('grant_type')).toBe('authorization_code');
            expect(body.get('code')).toBe('manual-init-code');

            return new Response(
              JSON.stringify({
                access_token: 'integration-access-token',
                refresh_token: 'integration-refresh-token',
                expires_in: 7200,
                token_type: 'Bearer',
                scope: 'ag1 eq1 files offline_access org2'
              }),
              {
                status: 200,
                headers: { 'content-type': 'application/json' }
              }
            );
          }

          if (url === 'https://sandboxapi.deere.com/platform/organizations') {
            return new Response(
              JSON.stringify({
                values: [
                  {
                    name: 'Needs Connection Org',
                    _links: {
                      connections: {
                        href: 'https://sandboxapi.deere.com/platform/organizations/1/connections'
                      }
                    }
                  }
                ]
              }),
              {
                status: 200,
                headers: { 'content-type': 'application/json' }
              }
            );
          }

          throw new Error(`Unexpected fetch URL: ${url}`);
        }
      });

      const tokenFilePath = path.join(tempRoot, 'tokens', 'iowa-demo-grower.json');
      const persistedToken = JSON.parse(await readFile(tokenFilePath, 'utf8')) as StoredToken;

      expect(result.exitCode).toBe(0);
      expect(result.output).toContain('authorizationCodeSource: stdin');
      expect(result.output).toContain('tokenSaved: yes (Bearer)');
      expect(result.output).toContain(
        'orgConnection: required - complete an Operations Center org connection for Needs Connection Org'
      );
      expect(result.output).toContain(`tokenStorePath: ${tokenFilePath}`);
      expect(persistedToken).toMatchObject({
        accessToken: 'integration-access-token',
        refreshToken: 'integration-refresh-token',
        tokenType: 'Bearer',
        scope: 'ag1 eq1 files offline_access org2'
      });
      expect(new Date(persistedToken.expiresAt).toString()).not.toBe('Invalid Date');
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });
});
