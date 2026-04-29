import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { formatJohnDeereTimestampPrefix, buildGrowerPaths } from '../paths.js';

export const OPERATION_STATUSES = [
  'pending',
  'accessible',
  'unauthorized',
  'unsupported_by_sdk',
  'unsupported_environment',
  'empty',
  'error',
  'disabled_by_default',
  'skipped_by_checkpoint'
] as const;

export type OperationStatus = (typeof OPERATION_STATUSES)[number];

export interface RequestContext {
  [key: string]: unknown;
}

export interface OperationManifestRecord {
  operation: string;
  status: OperationStatus;
  startTime: string;
  endTime: string;
  outputPaths: string[];
  errorDetails?: unknown;
  requestContext: RequestContext;
}

export interface OperationManifestDocument {
  growerSlug: string;
  generatedAt: string;
  operations: OperationManifestRecord[];
}

export interface RunManifestDocument {
  growerSlug: string;
  runId: string;
  status: string;
  startTime: string;
  endTime: string;
  totalDurationMs: number;
  outputPaths: string[];
  requestContext: RequestContext;
  operations: OperationManifestRecord[];
  statusCounts: Partial<Record<OperationStatus, number>>;
  nextCheckpoint: {
    lastSuccessfulRun: string | null;
    operationCursorCount: number;
    outputPaths: string[];
  };
}

export interface ManifestWriteOptions {
  dataRoot: string;
  growerSlug: string;
  fileName?: string;
}

export interface WriteOperationManifestOptions extends ManifestWriteOptions {
  operations: OperationManifestRecord[];
  generatedAt?: Date | string;
}

export interface WriteRunManifestOptions extends ManifestWriteOptions {
  status: string;
  startTime: Date | string;
  endTime: Date | string;
  requestContext?: RequestContext;
  operations: OperationManifestRecord[];
  outputPaths?: string[];
  runId?: string;
  nextCheckpoint?: {
    lastSuccessfulRun: string | null;
    operationCursorCount: number;
    outputPaths: string[];
  };
}

export interface ManifestWriteResult<TDocument> {
  document: TDocument;
  outputPaths: string[];
}

function normalizeTimestamp(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : value;
}

function serializeJson(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function uniquePaths(paths: Iterable<string>): string[] {
  return [...new Set(paths)];
}

function buildManifestDestinations(dataRoot: string, growerSlug: string, fileName: string): string[] {
  const growerPaths = buildGrowerPaths({ dataRoot, growerSlug });
  return [
    path.join(growerPaths.rawManifestsDir, fileName),
    path.join(growerPaths.manifestsDir, fileName)
  ];
}

async function writeDocument<TDocument>(
  options: ManifestWriteOptions,
  defaultFileName: string,
  document: TDocument
): Promise<ManifestWriteResult<TDocument>> {
  const fileName = options.fileName ?? defaultFileName;
  const outputPaths = buildManifestDestinations(options.dataRoot, options.growerSlug, fileName);
  const payload = serializeJson(document);

  await Promise.all(
    outputPaths.map(async (outputPath) => {
      await mkdir(path.dirname(outputPath), { recursive: true });
      await writeFile(outputPath, payload, 'utf-8');
    })
  );

  return { document, outputPaths };
}

function countStatuses(operations: OperationManifestRecord[]): Partial<Record<OperationStatus, number>> {
  return operations.reduce<Partial<Record<OperationStatus, number>>>((counts, operation) => {
    counts[operation.status] = (counts[operation.status] ?? 0) + 1;
    return counts;
  }, {});
}

export class ManifestWriter {
  async writeOperationManifest(
    options: WriteOperationManifestOptions
  ): Promise<ManifestWriteResult<OperationManifestDocument>> {
    const document: OperationManifestDocument = {
      growerSlug: options.growerSlug,
      generatedAt: normalizeTimestamp(options.generatedAt ?? new Date()),
      operations: options.operations
    };

    return writeDocument(options, 'operation-statuses.json', document);
  }

  async writeRunManifest(options: WriteRunManifestOptions): Promise<ManifestWriteResult<RunManifestDocument>> {
    const startTime = normalizeTimestamp(options.startTime);
    const endTime = normalizeTimestamp(options.endTime);
    const outputPaths = uniquePaths([
      ...(options.outputPaths ?? []),
      ...options.operations.flatMap((operation) => operation.outputPaths)
    ]);
    const runId = options.runId ?? formatJohnDeereTimestampPrefix(new Date(startTime));

    const document: RunManifestDocument = {
      growerSlug: options.growerSlug,
      runId,
      status: options.status,
      startTime,
      endTime,
      totalDurationMs: Math.max(0, Date.parse(endTime) - Date.parse(startTime)),
      outputPaths,
      requestContext: options.requestContext ?? {},
      operations: options.operations,
      statusCounts: countStatuses(options.operations),
      nextCheckpoint: options.nextCheckpoint ?? {
        lastSuccessfulRun: null,
        operationCursorCount: 0,
        outputPaths: []
      }
    };

    const latestRun = await writeDocument(options, 'latest-run.json', document);
    const timestampedRun = await writeDocument(
      {
        ...options,
        fileName: `run-${runId}.json`
      },
      `run-${runId}.json`,
      document
    );

    return {
      document,
      outputPaths: uniquePaths([...latestRun.outputPaths, ...timestampedRun.outputPaths])
    };
  }
}
