import { mkdtemp, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import { describe, expect, it } from 'vitest';

import { FileCheckpointStore } from '../../src/storage/checkpoint.js';

describe('FileCheckpointStore', () => {
  it('does not advance the checkpoint when an operation fails', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-checkpoints-'));

    try {
      const store = new FileCheckpointStore({
        dataRoot: tempRoot,
        growerSlug: 'grower-a'
      });

      await store.recordOperationResult({
        operation: 'fieldOperations.listAll',
        status: 'accessible',
        completedAt: '2026-04-28T09:00:00.000Z',
        cursor: 'cursor-1',
        requestContext: { orgId: 'org-1' }
      });

      await store.recordOperationResult({
        operation: 'fieldOperations.listAll',
        status: 'error',
        completedAt: '2026-04-28T10:00:00.000Z',
        cursor: 'cursor-2',
        requestContext: { orgId: 'org-1' }
      });

      const checkpoint = await store.load();

      expect(checkpoint).toEqual({
        growerSlug: 'grower-a',
        lastSuccessfulRun: '2026-04-28T09:00:00.000Z',
        operationCursors: {
          'fieldOperations.listAll': {
            cursor: 'cursor-1',
            requestContext: { orgId: 'org-1' },
            updatedAt: '2026-04-28T09:00:00.000Z'
          }
        }
      });
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  });
});
