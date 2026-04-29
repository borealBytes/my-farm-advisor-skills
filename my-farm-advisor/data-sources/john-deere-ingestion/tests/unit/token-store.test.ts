import { mkdtemp, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { describe, expect, it } from 'vitest';

import { buildTokenFilePath, FileTokenStore } from '../../src/tokens/file-store.js';
import { TokenStoreRecordNotFoundError, type StoredToken } from '../../src/tokens/store.js';

const SAMPLE_TOKEN: StoredToken = {
  accessToken: 'access-token-1',
  refreshToken: 'refresh-token-1',
  expiresAt: '2026-04-28T12:00:00.000Z',
  tokenType: 'Bearer',
  scope: 'org2 files offline_access ag1'
};

describe('FileTokenStore', () => {
  it('round-trips save/load/update/delete using a portable tokens directory', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-token-store-'));

    try {
      const store = new FileTokenStore({ dataRoot: tempRoot });
      const key = { grower: 'North 40 Demo' };

      await expect(store.load(key)).resolves.toBeNull();

      const savedToken = await store.save(key, SAMPLE_TOKEN);
      expect(savedToken).toEqual(SAMPLE_TOKEN);

      const tokenFilePath = store.getTokenFilePath(key);
      expect(tokenFilePath).toBe(path.join(tempRoot, 'tokens', 'north-40-demo.json'));

      const tokenFileContents = JSON.parse(await readFile(tokenFilePath, 'utf8')) as StoredToken;
      expect(tokenFileContents).toEqual(SAMPLE_TOKEN);

      await expect(store.load(key)).resolves.toEqual(SAMPLE_TOKEN);

      const updatedToken = await store.update(key, {
        accessToken: 'access-token-2',
        expiresAt: '2026-04-28T13:00:00.000Z'
      });

      expect(updatedToken).toEqual({
        ...SAMPLE_TOKEN,
        accessToken: 'access-token-2',
        expiresAt: '2026-04-28T13:00:00.000Z'
      });
      await expect(store.load(key)).resolves.toEqual(updatedToken);

      await expect(store.delete(key)).resolves.toBe(true);
      await expect(store.load(key)).resolves.toBeNull();
      await expect(store.delete(key)).resolves.toBe(false);
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('defaults token files under the resolved runtime data root, not src', () => {
    const store = new FileTokenStore({
      env: {},
      moduleDir: '/repo/my-farm-advisor/data-sources/john-deere-ingestion/src',
      pathExists: () => false
    });

    const tokenFilePath = store.getTokenFilePath({ grower: 'Grower Alpha' });

    expect(store.dataRoot).toBe('/repo/.runtime/my-farm-advisor/data');
    expect(tokenFilePath).toBe('/repo/.runtime/my-farm-advisor/data/tokens/grower-alpha.json');
    expect(tokenFilePath.includes('/src/')).toBe(false);
  });

  it('adds a profile suffix for non-default profiles', () => {
    const tokenFilePath = buildTokenFilePath({
      dataRoot: '/data/root',
      grower: 'Grower Alpha',
      profile: 'Sandbox Team'
    });

    expect(tokenFilePath).toBe('/data/root/tokens/grower-alpha.sandbox-team.json');
  });

  it('throws a typed error when updating a missing token record', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-token-store-missing-'));

    try {
      const store = new FileTokenStore({ dataRoot: tempRoot });

      await expect(store.update({ grower: 'missing-grower' }, { accessToken: 'new-access-token' })).rejects.toBeInstanceOf(
        TokenStoreRecordNotFoundError
      );
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });
});
