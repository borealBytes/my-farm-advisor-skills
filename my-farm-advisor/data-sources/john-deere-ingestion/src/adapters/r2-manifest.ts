import type {
  OperationManifestRecord,
  RunManifestDocument,
  OperationStatus
} from '../storage/manifest.js';

/**
 * R2-compatible view of a single operation result.
 * Field names use R2 conventions (startedAt/completedAt) while preserving
 * the original JD status enum so an R2 consumer can reason about auth,
  * empty, and error states without learning JD-specific terminology.
 */
export interface R2OperationRecord {
  operation: string;
  status: OperationStatus;
  startedAt: string;
  completedAt: string;
  outputPaths: string[];
  errorMessage?: string;
}

/**
 * R2-compatible run summary.
 * Mirrors the JD run manifest but flattens counts and exposes a
 * convenience totalOperations field.
 */
export interface R2RunSummary {
  growerSlug: string;
  runId: string;
  status: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  totalOperations: number;
  statusBreakdown: Partial<Record<OperationStatus, number>>;
  checkpoint: {
    lastSuccessfulRun: string | null;
    operationCursorCount: number;
    outputPaths: string[];
  };
}

/**
 * Static path mapping helpers showing where an R2 consumer should look
 * for John Deere artifacts inside the canonical tree.
 */
export const R2_PATH_MAPPING = {
  growerManifests: (growerSlug: string): string =>
    `growers/${growerSlug}/manifests/john-deere/`,

  farmManifests: (growerSlug: string, farmSlug: string): string =>
    `growers/${growerSlug}/farms/${farmSlug}/manifests/john-deere/`,

  fieldManifests: (growerSlug: string, farmSlug: string, fieldSlug: string): string =>
    `growers/${growerSlug}/farms/${farmSlug}/fields/${fieldSlug}/manifests/john-deere/`,

  rawManifests: (growerSlug: string): string =>
    `growers/${growerSlug}/source/john-deere/manifests/`,

  growerFile: (growerSlug: string): string =>
    `growers/${growerSlug}/grower.john-deere.json`,

  farmFile: (growerSlug: string, farmSlug: string): string =>
    `growers/${growerSlug}/farms/${farmSlug}/farm.john-deere.json`,

  fieldFile: (growerSlug: string, farmSlug: string, fieldSlug: string): string =>
    `growers/${growerSlug}/farms/${farmSlug}/fields/${fieldSlug}/field.john-deere.json`,

  fieldBoundaryFile: (growerSlug: string, farmSlug: string, fieldSlug: string): string =>
    `growers/${growerSlug}/farms/${farmSlug}/fields/${fieldSlug}/boundary/field_boundary.john-deere.geojson`
} as const;

/**
 * Adapt a JD operation manifest record into an R2-compatible shape.
 */
export function adaptOperationRecord(record: OperationManifestRecord): R2OperationRecord {
  return {
    operation: record.operation,
    status: record.status,
    startedAt: record.startTime,
    completedAt: record.endTime,
    outputPaths: record.outputPaths,
    errorMessage: record.errorDetails ? String(record.errorDetails) : undefined
  };
}

/**
 * Adapt a JD run manifest document into an R2-compatible summary.
 */
export function adaptRunManifest(manifest: RunManifestDocument): R2RunSummary {
  return {
    growerSlug: manifest.growerSlug,
    runId: manifest.runId,
    status: manifest.status,
    startedAt: manifest.startTime,
    completedAt: manifest.endTime,
    durationMs: manifest.totalDurationMs,
    totalOperations: manifest.operations.length,
    statusBreakdown: manifest.statusCounts,
    checkpoint: manifest.nextCheckpoint
  };
}

/**
 * Adapter interface for future dependency injection.
 * An R2 bridge can implement this contract to transform JD manifests
 * into whatever Python-friendly or pipeline-friendly shape it needs.
 */
export interface R2ManifestAdapter {
  adaptOperationRecord(record: OperationManifestRecord): R2OperationRecord;
  adaptRunManifest(manifest: RunManifestDocument): R2RunSummary;
}

/**
 * Default adapter implementation.
 */
export const defaultR2ManifestAdapter: R2ManifestAdapter = {
  adaptOperationRecord,
  adaptRunManifest
};
