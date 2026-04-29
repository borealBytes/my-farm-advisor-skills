export type JohnDeereOAuthEnvironment = 'sandboxapi' | 'sandbox' | 'production';

export interface OAuthDiscoveryDocument {
  issuer?: string;
  authorization_endpoint?: string;
  token_endpoint?: string;
  revocation_endpoint?: string;
  [key: string]: unknown;
}

export interface JohnDeereOAuthEndpoints {
  environment: JohnDeereOAuthEnvironment;
  discoveryUrl: string;
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  revocationEndpoint: string;
  apiBaseUrl: string;
  source: 'discovery' | 'fallback';
}

export interface ResolveOAuthEndpointsOptions {
  environment: JohnDeereOAuthEnvironment;
  discoveryUrl?: string;
  fetch?: typeof fetch;
}

export class OAuthEndpointResolutionError extends Error {
  readonly discoveryUrl: string;
  override readonly cause?: unknown;

  constructor(message: string, options: { discoveryUrl: string; cause?: unknown }) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = 'OAuthEndpointResolutionError';
    this.discoveryUrl = options.discoveryUrl;
    this.cause = options.cause;
  }
}

const DEFAULT_DISCOVERY_URL =
  'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7/.well-known/oauth-authorization-server';

const DEFAULT_ISSUER = 'https://signin.johndeere.com/oauth2/aus78tnlaysMraFhC1t7';

const DEFAULT_AUTHORIZATION_ENDPOINT = `${DEFAULT_ISSUER}/v1/authorize`;
const DEFAULT_TOKEN_ENDPOINT = `${DEFAULT_ISSUER}/v1/token`;
const DEFAULT_REVOCATION_ENDPOINT = `${DEFAULT_ISSUER}/v1/revoke`;

const API_BASE_URLS: Record<JohnDeereOAuthEnvironment, string> = {
  production: 'https://api.deere.com/platform',
  sandbox: 'https://sandboxapi.deere.com/platform',
  sandboxapi: 'https://sandboxapi.deere.com/platform'
};

export function getDefaultOAuthDiscoveryUrl(): string {
  return DEFAULT_DISCOVERY_URL;
}

export function getFallbackOAuthEndpoints(
  environment: JohnDeereOAuthEnvironment,
  discoveryUrl = DEFAULT_DISCOVERY_URL
): JohnDeereOAuthEndpoints {
  return {
    environment,
    discoveryUrl,
    issuer: DEFAULT_ISSUER,
    authorizationEndpoint: DEFAULT_AUTHORIZATION_ENDPOINT,
    tokenEndpoint: DEFAULT_TOKEN_ENDPOINT,
    revocationEndpoint: DEFAULT_REVOCATION_ENDPOINT,
    apiBaseUrl: API_BASE_URLS[environment],
    source: 'fallback'
  };
}

export async function resolveOAuthEndpoints(
  options: ResolveOAuthEndpointsOptions
): Promise<JohnDeereOAuthEndpoints> {
  const discoveryUrl = options.discoveryUrl ?? DEFAULT_DISCOVERY_URL;
  const fetchImpl = options.fetch ?? globalThis.fetch;

  if (typeof fetchImpl !== 'function') {
    throw new OAuthEndpointResolutionError('OAuth endpoint discovery requires a fetch implementation.', {
      discoveryUrl
    });
  }

  try {
    const response = await fetchImpl(discoveryUrl, {
      headers: {
        accept: 'application/json'
      }
    });

    if (!response.ok) {
      throw new Error(`Discovery request failed with HTTP ${response.status}`);
    }

    const document = (await response.json()) as OAuthDiscoveryDocument;

    if (
      typeof document.issuer !== 'string' ||
      typeof document.authorization_endpoint !== 'string' ||
      typeof document.token_endpoint !== 'string' ||
      typeof document.revocation_endpoint !== 'string'
    ) {
      throw new Error('Discovery document is missing one or more required OAuth metadata fields.');
    }

    return {
      environment: options.environment,
      discoveryUrl,
      issuer: document.issuer,
      authorizationEndpoint: document.authorization_endpoint,
      tokenEndpoint: document.token_endpoint,
      revocationEndpoint: document.revocation_endpoint,
      apiBaseUrl: API_BASE_URLS[options.environment],
      source: 'discovery'
    };
  } catch (error) {
    if (discoveryUrl === DEFAULT_DISCOVERY_URL) {
      return getFallbackOAuthEndpoints(options.environment, discoveryUrl);
    }

    throw new OAuthEndpointResolutionError('Failed to resolve John Deere OAuth endpoints from discovery.', {
      discoveryUrl,
      cause: error
    });
  }
}

// Deere's public docs and official OAuth samples all point to one Okta discovery URL for both
// sandbox and production OAuth flows. Environment-specific behavior lives at the API base URL layer
// (`sandboxapi.deere.com/platform` vs `api.deere.com/platform`), matching deere-sdk's environment map.
