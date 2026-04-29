import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { describe, expect, it } from 'vitest';

import { RawPayloadWriter } from '../../src/storage/raw.js';

describe('RawPayloadWriter', () => {
  it('appends a new file instead of overwriting an existing raw payload', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-raw-store-'));

    try {
      const writer = new RawPayloadWriter();
      const fetchedAt = new Date('2026-04-28T14:05:06.000Z');

      const firstWrite = await writer.write({
        dataRoot: tempRoot,
        growerSlug: 'grower-a',
        apiGroup: 'Field Operations',
        operation: 'List All',
        fetchedAt,
        idOrPage: 'Page 1',
        payload: { records: [1] }
      });

      const secondWrite = await writer.write({
        dataRoot: tempRoot,
        growerSlug: 'grower-a',
        apiGroup: 'Field Operations',
        operation: 'List All',
        fetchedAt,
        idOrPage: 'Page 1',
        payload: { records: [1] }
      });

      expect(firstWrite.path).not.toBe(secondWrite.path);
      expect(firstWrite.path).toMatch(/2026-04-28T14-05-06Z_list-all_page-1\.json$/);
      expect(secondWrite.path).toMatch(/2026-04-28T14-05-06Z_list-all_page-1_001\.json$/);

      const [firstContents, secondContents, firstStats, secondStats] = await Promise.all([
        readFile(firstWrite.path, 'utf-8'),
        readFile(secondWrite.path, 'utf-8'),
        stat(firstWrite.path),
        stat(secondWrite.path)
      ]);

      expect(firstContents).toBe('{\n  "records": [\n    1\n  ]\n}\n');
      expect(secondContents).toBe(firstContents);
      expect(firstStats.isFile()).toBe(true);
      expect(secondStats.isFile()).toBe(true);
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });
});
