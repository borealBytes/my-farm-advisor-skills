import { type StoredToken, type TokenStore, type TokenStoreKey } from './store.js';

export class KeychainTokenStoreNotImplementedError extends Error {
  constructor() {
    super('KeychainTokenStore is not implemented in v1. Use FileTokenStore for portable local development.');
    this.name = 'KeychainTokenStoreNotImplementedError';
  }
}

export class KeychainTokenStore implements TokenStore {
  async save(_key: TokenStoreKey, _token: StoredToken): Promise<StoredToken> {
    throw new KeychainTokenStoreNotImplementedError();
  }

  async load(_key: TokenStoreKey): Promise<StoredToken | null> {
    throw new KeychainTokenStoreNotImplementedError();
  }

  async update(_key: TokenStoreKey, _updates: Partial<StoredToken>): Promise<StoredToken> {
    throw new KeychainTokenStoreNotImplementedError();
  }

  async delete(_key: TokenStoreKey): Promise<boolean> {
    throw new KeychainTokenStoreNotImplementedError();
  }
}
