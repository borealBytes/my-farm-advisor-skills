import { resolveOAuthEndpoints, type JohnDeereOAuthEnvironment } from '../oauth/endpoints.js';

export interface TokenStoreKey {
  grower: string;
  profile?: string;
}

export interface StoredToken {
  accessToken: string;
  refreshToken: string;
  expiresAt: string;
  tokenType: string;
  scope: string;
}

export interface TokenStore {
  save(key: TokenStoreKey, token: StoredToken): Promise<StoredToken>;
  load(key: TokenStoreKey): Promise<StoredToken | null>;
  update(key: TokenStoreKey, updates: Partial<StoredToken>): Promise<StoredToken>;
  delete(key: TokenStoreKey): Promise<boolean>;
}

export interface RefreshAccessTokenOptions {
  environment: JohnDeereOAuthEnvironment;
  tokenStore: TokenStore;
  tokenStoreKey: TokenStoreKey;
  clientId: string;
  clientSecret: string;
  discoveryUrl?: string;
  fetch?: typeof fetch;
  now?: () => Date;
}

interface RefreshAccessTokenResponse {
  access_token?: unknown;
  refresh_token?: unknown;
  expires_in?: unknown;
  token_type?: unknown;
  scope?: unknown;
}

export class TokenStoreRecordNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TokenStoreRecordNotFoundError';
  }
}

export class TokenRefreshError extends Error {
  override readonly cause?: unknown;

  constructor(message: string, options: { cause?: unknown } = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = 'TokenRefreshError';
    this.cause = options.cause;
  }
}

export function normalizeTokenStoreKey(key: TokenStoreKey): Required<TokenStoreKey> {
  return {
    grower: key.grower,
    profile: key.profile ?? 'default'
  };
}

export function assertStoredToken(value: unknown): StoredToken {
  if (!value || typeof value !== 'object') {
    throw new TypeError('Stored token must be an object.');
  }

  const candidate = value as Record<string, unknown>;

  return {
    accessToken: readRequiredString(candidate.accessToken, 'accessToken'),
    refreshToken: readRequiredString(candidate.refreshToken, 'refreshToken'),
    expiresAt: readRequiredString(candidate.expiresAt, 'expiresAt'),
    tokenType: readRequiredString(candidate.tokenType, 'tokenType'),
    scope: readRequiredString(candidate.scope, 'scope')
  };
}

function readRequiredString(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`Stored token field \`${fieldName}\` must be a non-empty string.`);
  }

  return value;
}

export async function refreshAccessToken(options: RefreshAccessTokenOptions): Promise<StoredToken> {
  const fetchImpl = options.fetch ?? globalThis.fetch;

  if (typeof fetchImpl !== 'function') {
    throw new TokenRefreshError('Token refresh requires a fetch implementation.');
  }

  const existingToken = await options.tokenStore.load(options.tokenStoreKey);

  if (!existingToken) {
    const normalizedKey = normalizeTokenStoreKey(options.tokenStoreKey);
    throw new TokenRefreshError(
      `No stored token exists for grower \`${normalizedKey.grower}\` and profile \`${normalizedKey.profile}\`.`
    );
  }

  try {
    const endpoints = await resolveOAuthEndpoints({
      environment: options.environment,
      discoveryUrl: options.discoveryUrl,
      fetch: fetchImpl
    });

    const response = await fetchImpl(endpoints.tokenEndpoint, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/x-www-form-urlencoded'
      },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: existingToken.refreshToken,
        client_id: options.clientId,
        client_secret: options.clientSecret
      })
    });

    if (!response.ok) {
      throw new TokenRefreshError(`Token refresh failed with HTTP ${response.status}.`, {
        cause: await readRefreshError(response)
      });
    }

    const payload = (await response.json()) as RefreshAccessTokenResponse;

    if (typeof payload.access_token !== 'string' || payload.access_token.trim() === '') {
      throw new TokenRefreshError('Token refresh response did not include a usable access token.');
    }

    const now = options.now?.() ?? new Date();
    const expiresInSeconds =
      typeof payload.expires_in === 'number' && Number.isFinite(payload.expires_in) ? payload.expires_in : undefined;

    const refreshedToken = assertStoredToken({
      accessToken: payload.access_token,
      refreshToken: typeof payload.refresh_token === 'string' && payload.refresh_token.trim() !== '' ? payload.refresh_token : existingToken.refreshToken,
      expiresAt:
        expiresInSeconds === undefined
          ? existingToken.expiresAt
          : new Date(now.getTime() + expiresInSeconds * 1000).toISOString(),
      tokenType: typeof payload.token_type === 'string' && payload.token_type.trim() !== '' ? payload.token_type : existingToken.tokenType,
      scope: typeof payload.scope === 'string' && payload.scope.trim() !== '' ? payload.scope : existingToken.scope
    });

    return options.tokenStore.save(options.tokenStoreKey, refreshedToken);
  } catch (error) {
    if (error instanceof TokenRefreshError) {
      throw error;
    }

    throw new TokenRefreshError('Token refresh failed.', { cause: error });
  }
}

async function readRefreshError(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type');

  if (contentType?.includes('application/json')) {
    return response.json();
  }

  return response.text().catch(() => undefined);
}
