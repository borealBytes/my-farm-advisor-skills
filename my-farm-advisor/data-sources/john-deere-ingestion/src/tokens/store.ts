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

export class TokenStoreRecordNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TokenStoreRecordNotFoundError';
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
