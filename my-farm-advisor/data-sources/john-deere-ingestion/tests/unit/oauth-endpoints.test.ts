import { describe, expect, it, vi } from 'vitest';

import {
  OAuthEndpointResolutionError,
  getDefaultOAuthDiscoveryUrl,
  getFallbackOAuthEndpoints,
  resolveOAuthEndpoints
} from '../../src/oauth/endpoints.js';

describe('OAuth endpoint resolution', () => {
  it('resolves sandbox endpoints from discovery metadata', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
      ok: true,
      json: async () => ({
        issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
        authorization_endpoint:
          'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize',
        token_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token',
        revocation_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke'
      })
    } as Response);

    const endpoints = await resolveOAuthEndpoints({
      environment: 'sandboxapi',
      fetch: fetchMock
    });

    expect(fetchMock).toHaveBeenCalledWith(getDefaultOAuthDiscoveryUrl(), {
      headers: { accept: 'application/json' }
    });
    expect(endpoints).toEqual({
      environment: 'sandboxapi',
      discoveryUrl: getDefaultOAuthDiscoveryUrl(),
      issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
      authorizationEndpoint:
        'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize',
      tokenEndpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token',
      revocationEndpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke',
      apiBaseUrl: 'https://sandboxapi.deere.com/platform',
      source: 'discovery'
    });
  });

  it('resolves production endpoints from discovery metadata', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue({
      ok: true,
      json: async () => ({
        issuer: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7',
        authorization_endpoint:
          'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/authorize',
        token_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/token',
        revocation_endpoint: 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/v1/revoke'
      })
    } as Response);

    const endpoints = await resolveOAuthEndpoints({
      environment: 'production',
      fetch: fetchMock
    });

    expect(endpoints.apiBaseUrl).toBe('https://api.deere.com/platform');
    expect(endpoints.source).toBe('discovery');
    expect(endpoints.authorizationEndpoint).toContain('/v1/authorize');
    expect(endpoints.tokenEndpoint).toContain('/v1/token');
    expect(endpoints.revocationEndpoint).toContain('/v1/revoke');
  });

  it('falls back to authoritative defaults when the official discovery URL fails', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new Error('network unavailable'));

    const endpoints = await resolveOAuthEndpoints({
      environment: 'sandboxapi',
      fetch: fetchMock
    });

    expect(endpoints).toEqual(getFallbackOAuthEndpoints('sandboxapi'));
  });

  it('throws a typed error when a custom discovery URL fails', async () => {
    const discoveryUrl = 'https://example.invalid/.well-known/oauth-authorization-server';
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(new Error('getaddrinfo ENOTFOUND'));

    await expect(
      resolveOAuthEndpoints({
        environment: 'production',
        discoveryUrl,
        fetch: fetchMock
      })
    ).rejects.toMatchObject({
      name: 'OAuthEndpointResolutionError',
      message: 'Failed to resolve John Deere OAuth endpoints from discovery.',
      discoveryUrl
    });
  });
});
