import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { resolveDataRoot, toDeerePathSegment, type ResolveDataRootOptions } from '../paths.js';
import {
  assertStoredToken,
  normalizeTokenStoreKey,
  TokenStoreRecordNotFoundError,
  type StoredToken,
  type TokenStore,
  type TokenStoreKey
} from './store.js';

export interface FileTokenStoreOptions extends ResolveDataRootOptions {
  dataRoot?: string;
}

export interface TokenFilePathOptions {
  dataRoot: string;
  grower: string;
  profile?: string;
}

export class FileTokenStore implements TokenStore {
  readonly dataRoot: string;
  readonly tokensDir: string;

  constructor(options: FileTokenStoreOptions = {}) {
    this.dataRoot = options.dataRoot ?? resolveDataRoot(options);
    this.tokensDir = path.join(this.dataRoot, 'tokens');
  }

  getTokenFilePath(key: TokenStoreKey): string {
    return buildTokenFilePath({ dataRoot: this.dataRoot, ...key });
  }

  async save(key: TokenStoreKey, token: StoredToken): Promise<StoredToken> {
    const normalizedToken = assertStoredToken(token);
    const tokenFilePath = this.getTokenFilePath(key);

    await mkdir(path.dirname(tokenFilePath), { recursive: true });
    await writeFile(tokenFilePath, `${JSON.stringify(normalizedToken, null, 2)}\n`, 'utf8');

    return normalizedToken;
  }

  async load(key: TokenStoreKey): Promise<StoredToken | null> {
    try {
      const rawDocument = await readFile(this.getTokenFilePath(key), 'utf8');
      return assertStoredToken(JSON.parse(rawDocument) as unknown);
    } catch (error) {
      if (isMissingFileError(error)) {
        return null;
      }

      throw error;
    }
  }

  async update(key: TokenStoreKey, updates: Partial<StoredToken>): Promise<StoredToken> {
    const existingToken = await this.load(key);

    if (!existingToken) {
      const normalizedKey = normalizeTokenStoreKey(key);
      throw new TokenStoreRecordNotFoundError(
        `No token record exists for grower \`${normalizedKey.grower}\` and profile \`${normalizedKey.profile}\`.`
      );
    }

    const mergedToken = assertStoredToken({
      ...existingToken,
      ...updates
    });

    return this.save(key, mergedToken);
  }

  async delete(key: TokenStoreKey): Promise<boolean> {
    try {
      await rm(this.getTokenFilePath(key));
      return true;
    } catch (error) {
      if (isMissingFileError(error)) {
        return false;
      }

      throw error;
    }
  }
}

export function buildTokenFilePath(options: TokenFilePathOptions): string {
  const normalizedKey = normalizeTokenStoreKey(options);
  const growerSegment = toDeerePathSegment(normalizedKey.grower);
  const profileSegment = toDeerePathSegment(normalizedKey.profile);
  const filename = profileSegment === 'default' ? `${growerSegment}.json` : `${growerSegment}.${profileSegment}.json`;

  return path.join(options.dataRoot, 'tokens', filename);
}

function isMissingFileError(error: unknown): error is NodeJS.ErrnoException {
  return typeof error === 'object' && error !== null && 'code' in error && error.code === 'ENOENT';
}
