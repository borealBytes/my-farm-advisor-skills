import { Readable } from 'node:stream';

import { describe, expect, it, vi } from 'vitest';

import { initJohnDeereAuth, refreshAccessToken } from '../../src/auth/init.js';
import { parseConfig, type ParseConfigOverrides } from '../../src/config.js';
import type { StoredToken, TokenStore } from '../../src/tokens/store.js';

const DISCOVERY_URL =
  'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/.well-known/oauth-authorization-server';
const AUTHORIZATION_ENDPOINT = 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize';
const TOKEN_ENDPOINT = 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token';
const REVOCATION_ENDPOINT = 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke';
const FIXED_NOW = new Date('2026-04-29T12:00:00.000Z');

function createConfig(overrides: ParseConfigOverrides = {}) {
  return parseConfig({
    cwd: '/workspace/project',
    env: {
      JD_CLIENT_ID: 'client-123',
      JD_CLIENT_SECRET: 'secret-456',
      JD_DATA_ROOT: '/tmp/jd-data',
      JD_GROWER: 'Iowa Demo Grower',
      JD_PROFILE: 'sandbox-profile'
    },
    overrides
  });
}

function discoveryResponse(): Response {
  return new Response(
    JSON.stringify({
      issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
      authorization_endpoint: AUTHORIZATION_ENDPOINT,
      token_endpoint: TOKEN_ENDPOINT,
      revocation_endpoint: REVOCATION_ENDPOINT
    }),
    {
      status: 200,
      headers: { 'content-type': 'application/json' }
    }
  );
}

function createTokenStoreMock(): TokenStore {
  return {
    save: vi.fn(async (_key, token) => token),
    load: vi.fn(async () => null),
    update: vi.fn(async (_key, updates) => ({
      accessToken: typeof updates.accessToken === 'string' ? updates.accessToken : 'updated-access-token',
      refreshToken: typeof updates.refreshToken === 'string' ? updates.refreshToken : 'updated-refresh-token',
      expiresAt: typeof updates.expiresAt === 'string' ? updates.expiresAt : FIXED_NOW.toISOString(),
      tokenType: typeof updates.tokenType === 'string' ? updates.tokenType : 'Bearer',
      scope: typeof updates.scope === 'string' ? updates.scope : 'ag1 eq1 files offline_access org2'
    })),
    delete: vi.fn(async () => true)
  };
}

describe('John Deere auth init flow', () => {
  it('prints the full authorization URL during dry-run and never writes tokens', async () => {
    const tokenStore = createTokenStoreMock();
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      expect(String(input)).toBe(DISCOVERY_URL);
      return discoveryResponse();
    });

    const result = await initJohnDeereAuth({
      config: createConfig({ dryRun: true }),
      fetch: fetchMock,
      tokenStore,
      randomBytes: (size) => Buffer.alloc(size, 9)
    });

    const authorizationUrl = new URL(result.authorizationUrl);

    expect(result.dryRun).toBe(true);
    expect(authorizationUrl.origin + authorizationUrl.pathname).toBe(AUTHORIZATION_ENDPOINT);
    expect(authorizationUrl.searchParams.get('client_id')).toBe('client-123');
    expect(authorizationUrl.searchParams.get('redirect_uri')).toBe('http://localhost:9090/callback');
    expect(authorizationUrl.searchParams.get('scope')).toBe('ag1 eq1 files offline_access org2');
    expect(authorizationUrl.searchParams.get('state')).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(authorizationUrl.searchParams.get('code_challenge_method')).toBe('S256');
    expect(result.outputLines).toContain('dry-run: token exchange skipped; no token files written.');
    expect(tokenStore.save).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('uses pasted stdin code when browser callback is unavailable and persists tokens', async () => {
    const tokenStore = createTokenStoreMock();
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url === DISCOVERY_URL) {
        return discoveryResponse();
      }

      if (url === TOKEN_ENDPOINT) {
        const body = init?.body as URLSearchParams;
        expect(body.get('grant_type')).toBe('authorization_code');
        expect(body.get('code')).toBe('manual-auth-code');
        expect(body.get('code_verifier')).toMatch(/^[A-Za-z0-9_-]+$/);

        return new Response(
          JSON.stringify({
            access_token: 'access-token-1',
            refresh_token: 'refresh-token-1',
            expires_in: 3600,
            token_type: 'Bearer',
            scope: 'ag1 eq1 files offline_access org2'
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        );
      }

      if (url === 'https://sandboxapi.deere.com/platform/organizations') {
        return new Response(JSON.stringify({ values: [{ name: 'Alpha Org', links: {} }] }), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        });
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    const result = await initJohnDeereAuth({
      config: createConfig(),
      fetch: fetchMock,
      tokenStore,
      stdin: Readable.from(['manual-auth-code\n']),
      now: () => FIXED_NOW,
      randomBytes: (size) => Buffer.alloc(size, 7)
    });

    expect(result.authorizationCodeSource).toBe('stdin');
    expect(tokenStore.save).toHaveBeenCalledWith(
      { grower: 'Iowa Demo Grower', profile: 'sandbox-profile' },
      {
        accessToken: 'access-token-1',
        refreshToken: 'refresh-token-1',
        expiresAt: '2026-04-29T13:00:00.000Z',
        tokenType: 'Bearer',
        scope: 'ag1 eq1 files offline_access org2'
      }
    );
    expect(result.outputLines).toContain('authorizationCodeSource: stdin');
  });

  it('reports when organizations still require an Operations Center connection', async () => {
    const tokenStore = createTokenStoreMock();
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);

      if (url === DISCOVERY_URL) {
        return discoveryResponse();
      }

      if (url === TOKEN_ENDPOINT) {
        return new Response(
          JSON.stringify({
            access_token: 'access-token-2',
            refresh_token: 'refresh-token-2',
            expires_in: 1800,
            token_type: 'Bearer',
            scope: 'ag1 eq1 files offline_access org2'
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        );
      }

      if (url === 'https://sandboxapi.deere.com/platform/organizations') {
        return new Response(
          JSON.stringify({
            values: [
              {
                name: 'Connected Later Org',
                links: {
                  connections: {
                    href: 'https://sandboxapi.deere.com/platform/organizations/123/connections'
                  }
                }
              }
            ]
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        );
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    const result = await initJohnDeereAuth({
      config: createConfig(),
      fetch: fetchMock,
      tokenStore,
      authorizationCode: 'manual-code-from-cli',
      now: () => FIXED_NOW
    });

    expect(result.orgConnection.required).toBe(true);
    expect(result.orgConnection.organizationNamesRequiringConnection).toEqual(['Connected Later Org']);
    expect(result.outputLines).toContain(
      'orgConnection: required - complete an Operations Center org connection for Connected Later Org'
    );
  });

  it('refreshes the access token and updates the token store in place', async () => {
    const existingToken: StoredToken = {
      accessToken: 'stale-access-token',
      refreshToken: 'refresh-token-9',
      expiresAt: '2026-04-29T11:00:00.000Z',
      tokenType: 'Bearer',
      scope: 'ag1 eq1 files offline_access org2'
    };
    const tokenStore = createTokenStoreMock();
    vi.mocked(tokenStore.load).mockResolvedValue(existingToken);
    vi.mocked(tokenStore.update).mockImplementation(async (_key, updates) => ({
      ...existingToken,
      ...updates
    }));

    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url === DISCOVERY_URL) {
        return discoveryResponse();
      }

      if (url === TOKEN_ENDPOINT) {
        const body = init?.body as URLSearchParams;
        expect(body.get('grant_type')).toBe('refresh_token');
        expect(body.get('refresh_token')).toBe('refresh-token-9');

        return new Response(
          JSON.stringify({
            access_token: 'fresh-access-token',
            expires_in: 900,
            token_type: 'Bearer'
          }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        );
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    const refreshedToken = await refreshAccessToken({
      config: createConfig(),
      fetch: fetchMock,
      tokenStore,
      now: () => FIXED_NOW
    });

    expect(tokenStore.update).toHaveBeenCalledWith(
      { grower: 'Iowa Demo Grower', profile: 'sandbox-profile' },
      {
        accessToken: 'fresh-access-token',
        refreshToken: 'refresh-token-9',
        expiresAt: '2026-04-29T12:15:00.000Z',
        tokenType: 'Bearer',
        scope: 'ag1 eq1 files offline_access org2'
      }
    );
    expect(refreshedToken.accessToken).toBe('fresh-access-token');
    expect(refreshedToken.refreshToken).toBe('refresh-token-9');
  });
});
