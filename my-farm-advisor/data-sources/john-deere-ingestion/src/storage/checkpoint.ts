import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { buildGrowerPaths } from '../paths.js';
import { type OperationStatus } from './manifest.js';

export interface OperationCursorState {
  cursor?: string;
  fingerprint?: string;
  updatedAt: string;
  requestContext?: Record<string, unknown>;
}

export interface CheckpointState {
  growerSlug: string;
  lastSuccessfulRun: string | null;
  operationCursors: Record<string, OperationCursorState>;
}

export interface CheckpointStoreOptions {
  dataRoot: string;
  growerSlug: string;
}

export interface CheckpointOperationResult {
  operation: string;
  status: OperationStatus;
  completedAt: Date | string;
  cursor?: string | null;
  fingerprint?: string | null;
  requestContext?: Record<string, unknown>;
}

export interface CheckpointWriteResult {
  state: CheckpointState;
  outputPaths: string[];
}

const ADVANCING_STATUSES = new Set<OperationStatus>(['accessible', 'empty']);

function normalizeTimestamp(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : value;
}

function serializeJson(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function buildCheckpointPaths(options: CheckpointStoreOptions): string[] {
  const growerPaths = buildGrowerPaths(options);
  return [
    path.join(growerPaths.rawManifestsDir, 'checkpoints.json'),
    path.join(growerPaths.manifestsDir, 'checkpoints.json')
  ];
}

export function createEmptyCheckpoint(growerSlug: string): CheckpointState {
  return {
    growerSlug,
    lastSuccessfulRun: null,
    operationCursors: {}
  };
}

export function advanceCheckpoint(
  checkpoint: CheckpointState,
  result: CheckpointOperationResult
): CheckpointState {
  if (!ADVANCING_STATUSES.has(result.status)) {
    return checkpoint;
  }

  const completedAt = normalizeTimestamp(result.completedAt);
  const previousCursor = checkpoint.operationCursors[result.operation] ?? { updatedAt: completedAt };

  return {
    growerSlug: checkpoint.growerSlug,
    lastSuccessfulRun: completedAt,
    operationCursors: {
      ...checkpoint.operationCursors,
      [result.operation]: {
        ...previousCursor,
        ...(result.cursor == null ? {} : { cursor: result.cursor }),
        ...(result.fingerprint == null ? {} : { fingerprint: result.fingerprint }),
        ...(result.requestContext == null ? {} : { requestContext: result.requestContext }),
        updatedAt: completedAt
      }
    }
  };
}

export class FileCheckpointStore {
  constructor(private readonly options: CheckpointStoreOptions) {}

  async load(): Promise<CheckpointState> {
    const checkpointPaths = buildCheckpointPaths(this.options);

    for (const checkpointPath of checkpointPaths) {
      if (!(await pathExists(checkpointPath))) {
        continue;
      }

      const raw = await readFile(checkpointPath, 'utf-8');
      const parsed = JSON.parse(raw) as CheckpointState;
      return {
        growerSlug: parsed.growerSlug,
        lastSuccessfulRun: parsed.lastSuccessfulRun ?? null,
        operationCursors: parsed.operationCursors ?? {}
      };
    }

    return createEmptyCheckpoint(this.options.growerSlug);
  }

  async save(state: CheckpointState): Promise<CheckpointWriteResult> {
    const checkpointPaths = buildCheckpointPaths(this.options);
    const payload = serializeJson(state);

    await Promise.all(
      checkpointPaths.map(async (checkpointPath) => {
        await mkdir(path.dirname(checkpointPath), { recursive: true });
        await writeFile(checkpointPath, payload, 'utf-8');
      })
    );

    return {
      state,
      outputPaths: checkpointPaths
    };
  }

  async recordOperationResult(result: CheckpointOperationResult): Promise<CheckpointWriteResult> {
    const current = await this.load();
    const next = advanceCheckpoint(current, result);
    return this.save(next);
  }
}
