import { createHash } from 'node:crypto';
import path from 'node:path';

import type { DeereClientCallResult, DeereLike, DeereSdkClient } from '../client/deere-client.js';
import {
  JohnDeereCanonicalMapper,
  writeNormalizedFiles,
  type DeereRelationReference,
  type NormalizedFile
} from '../normalize/mapper.js';
import type { OperationRegistryEntry, OperationRegistryStatus } from '../registry/operations.js';
import { operationRegistry } from '../registry/operations.js';
import { advanceCheckpoint, FileCheckpointStore, type CheckpointState } from '../storage/checkpoint.js';
import {
  ManifestWriter,
  type OperationManifestRecord,
  type RequestContext,
  type RunManifestDocument
} from '../storage/manifest.js';
import { RawPayloadWriter } from '../storage/raw.js';

type ExecutableOperationStatus = Exclude<
  OperationRegistryStatus,
  'pending' | 'disabled_by_default' | 'skipped_by_checkpoint'
>;

interface ScopeReference extends DeereRelationReference {
  deereId: string;
}

interface ExecutionScope {
  orgId: string;
  farm?: ScopeReference;
  field?: ScopeReference;
  equipmentId?: string;
  machineId?: string;
}

export interface RegistryExecutorOptions {
  growerSlug: string;
  orgId: string;
  dataRoot: string;
  since?: string;
  mock: boolean;
  force?: boolean;
}

export interface RegistryExecutorMockFixture {
  status?: ExecutableOperationStatus;
  payload?: unknown;
  error?: unknown;
  requestContext?: RequestContext;
}

export interface RegistryExecutorResult {
  growerSlug: string;
  runStatus: string;
  startTime: string;
  endTime: string;
  runManifest: RunManifestDocument;
  checkpoint: CheckpointState;
  operations: OperationManifestRecord[];
  runManifestPaths: string[];
  operationManifestPaths: string[];
  checkpointPaths: string[];
  outputPaths: string[];
}

export interface RegistryExecutorDependencies {
  client?: DeereSdkClient;
  registry?: readonly OperationRegistryEntry[];
  rawPayloadWriter?: RawPayloadWriter;
  manifestWriter?: ManifestWriter;
  checkpointStore?: FileCheckpointStore;
  mockFixtures?: Record<string, RegistryExecutorMockFixture>;
  now?: () => Date;
}

interface OperationExecutionResult {
  status: ExecutableOperationStatus;
  startTime: string;
  endTime: string;
  payload?: unknown;
  error?: unknown;
  requestContext?: RequestContext;
}

const LIST_LIKE_OPERATIONS = new Set(['list', 'listAll', 'listOrganizations', 'listUsers']);

export class RegistryExecutor {
  private readonly client?: DeereSdkClient;
  private readonly registry: readonly OperationRegistryEntry[];
  private readonly rawPayloadWriter: RawPayloadWriter;
  private readonly manifestWriter: ManifestWriter;
  private readonly checkpointStore?: FileCheckpointStore;
  private readonly mockFixtures: Record<string, RegistryExecutorMockFixture>;
  private readonly now: () => Date;

  constructor(dependencies: RegistryExecutorDependencies = {}) {
    this.client = dependencies.client;
    this.registry = dependencies.registry ?? operationRegistry;
    this.rawPayloadWriter = dependencies.rawPayloadWriter ?? new RawPayloadWriter();
    this.manifestWriter = dependencies.manifestWriter ?? new ManifestWriter();
    this.checkpointStore = dependencies.checkpointStore;
    this.mockFixtures = dependencies.mockFixtures ?? {};
    this.now = dependencies.now ?? (() => new Date());
  }

  async execute(options: RegistryExecutorOptions): Promise<RegistryExecutorResult> {
    const startedAt = this.now();
    const checkpointStore = this.checkpointStore ?? new FileCheckpointStore(options);
    let checkpoint = await checkpointStore.load();
    const scope: ExecutionScope = {
      orgId: options.orgId
    };
    const operations: OperationManifestRecord[] = [];

    for (const entry of this.registry) {
      const operationKey = toOperationKey(entry);
      const requestContext = this.buildRequestContext(entry, options, scope, operationKey);

      if (entry.status === 'unsupported_by_sdk') {
        operations.push(
          this.buildSkippedRecord({
            operationKey,
            status: 'unsupported_by_sdk',
            requestContext,
            errorDetails: {
              reason: 'Operation is declared as unsupported by the installed deere-sdk version.',
              sdkPath: entry.sdkPath
            }
          })
        );
        continue;
      }

      if (!entry.defaultEnabled && !options.force) {
        operations.push(
          this.buildSkippedRecord({
            operationKey,
            status: 'disabled_by_default',
            requestContext,
            errorDetails: {
              reason: 'Operation is destructive or opt-in and was not forced.',
              destructive: entry.destructive
            }
          })
        );
        continue;
      }

      if (shouldSkipByCheckpoint(checkpoint, operationKey, options.since)) {
        operations.push(
          this.buildSkippedRecord({
            operationKey,
            status: 'skipped_by_checkpoint',
            requestContext,
            errorDetails: {
              reason: 'Checkpoint indicates the operation was already synced within the requested window.',
              lastUpdatedAt: checkpoint.operationCursors[operationKey]?.updatedAt ?? null,
              since: options.since
            }
          })
        );
        continue;
      }

      const execution = options.mock
        ? this.executeMockOperation(entry, operationKey, scope)
        : await this.executeLiveOperation(entry, requestContext, scope);
      const mapper = new JohnDeereCanonicalMapper({
        dataRoot: options.dataRoot,
        growerSlug: options.growerSlug,
        sourceApi: entry.apiGroup,
        sourceOperation: entry.operation,
        fetchedAt: execution.endTime
      });
      const outputPaths: string[] = [];

      let record: OperationManifestRecord;

      try {
        if (execution.payload !== undefined && (execution.status === 'accessible' || execution.status === 'empty')) {
          const rawWrite = await this.rawPayloadWriter.write({
            dataRoot: options.dataRoot,
            growerSlug: options.growerSlug,
            apiGroup: entry.apiGroup,
            operation: entry.operation,
            fetchedAt: new Date(execution.endTime),
            idOrPage: deriveIdOrPage(execution.payload, operationKey),
            payload: execution.payload
          });
          outputPaths.push(rawWrite.relativePath);

          const normalizedFiles = this.mapNormalizedOutputs(entry, execution.payload, mapper, scope);
          if (normalizedFiles.length > 0) {
            const normalizedWrites = await writeNormalizedFiles(normalizedFiles);
            outputPaths.push(...normalizedWrites.map((filePath) => toDataRelativePath(options.dataRoot, filePath)));
          }

          updateScopeFromPayload(entry, execution.payload, scope);
        }

        record = {
          operation: operationKey,
          status: mapExecutionStatus(execution.status),
          startTime: execution.startTime,
          endTime: execution.endTime,
          outputPaths: uniquePaths(outputPaths),
          errorDetails: serializeErrorDetails(execution.error),
          requestContext: {
            ...requestContext,
            ...(execution.requestContext ?? {})
          }
        };
      } catch (error) {
        record = {
          operation: operationKey,
          status: 'error',
          startTime: execution.startTime,
          endTime: this.now().toISOString(),
          outputPaths: uniquePaths(outputPaths),
          errorDetails: serializeErrorDetails(error),
          requestContext
        };
      }

      operations.push(record);
      checkpoint = advanceCheckpoint(checkpoint, {
        operation: operationKey,
        status: record.status,
        completedAt: record.endTime,
        cursor: deriveCursor(execution.payload, record.endTime),
        fingerprint: deriveFingerprint(execution.payload, record.status),
        requestContext: record.requestContext
      });
    }

    const operationManifest = await this.manifestWriter.writeOperationManifest({
      dataRoot: options.dataRoot,
      growerSlug: options.growerSlug,
      operations,
      generatedAt: this.now()
    });
    const checkpointWrite = await checkpointStore.save(checkpoint);
    const endedAt = this.now();
    const runManifest = await this.manifestWriter.writeRunManifest({
      dataRoot: options.dataRoot,
      growerSlug: options.growerSlug,
      status: deriveRunStatus(operations),
      startTime: startedAt,
      endTime: endedAt,
      requestContext: {
        orgId: options.orgId,
        mock: options.mock,
        force: options.force ?? false,
        since: options.since ?? null
      },
      operations,
      outputPaths: [
        ...operationManifest.outputPaths.map((filePath) => toDataRelativePath(options.dataRoot, filePath)),
        ...checkpointWrite.outputPaths.map((filePath) => toDataRelativePath(options.dataRoot, filePath))
      ],
      nextCheckpoint: {
        lastSuccessfulRun: checkpointWrite.state.lastSuccessfulRun,
        operationCursorCount: Object.keys(checkpointWrite.state.operationCursors).length,
        outputPaths: checkpointWrite.outputPaths.map((filePath) => toDataRelativePath(options.dataRoot, filePath))
      }
    });

    return {
      growerSlug: options.growerSlug,
      runStatus: runManifest.document.status,
      startTime: startedAt.toISOString(),
      endTime: endedAt.toISOString(),
      runManifest: runManifest.document,
      checkpoint: checkpointWrite.state,
      operations,
      runManifestPaths: runManifest.outputPaths,
      operationManifestPaths: operationManifest.outputPaths,
      checkpointPaths: checkpointWrite.outputPaths,
      outputPaths: uniquePaths([
        ...runManifest.outputPaths,
        ...operationManifest.outputPaths,
        ...checkpointWrite.outputPaths,
        ...operations.flatMap((operation) => operation.outputPaths)
      ])
    };
  }

  private buildRequestContext(
    entry: OperationRegistryEntry,
    options: RegistryExecutorOptions,
    scope: ExecutionScope,
    operationKey: string
  ): RequestContext {
    return {
      operationKey,
      apiGroup: entry.apiGroup,
      operation: entry.operation,
      sdkPath: entry.sdkPath,
      authMode: entry.authMode,
      entityScope: entry.entityScope,
      requiredScopes: entry.requiredScopes,
      orgId: options.orgId,
      growerSlug: options.growerSlug,
      mock: options.mock,
      force: options.force ?? false,
      since: options.since ?? null,
      scope: {
        farmId: scope.farm?.deereId ?? null,
        fieldId: scope.field?.deereId ?? null,
        equipmentId: scope.equipmentId ?? null,
        machineId: scope.machineId ?? null
      }
    };
  }

  private buildSkippedRecord(options: {
    operationKey: string;
    status: Extract<OperationRegistryStatus, 'unsupported_by_sdk' | 'disabled_by_default' | 'skipped_by_checkpoint'>;
    requestContext: RequestContext;
    errorDetails: unknown;
  }): OperationManifestRecord {
    const timestamp = this.now().toISOString();

    return {
      operation: options.operationKey,
      status: options.status,
      startTime: timestamp,
      endTime: timestamp,
      outputPaths: [],
      errorDetails: options.errorDetails,
      requestContext: options.requestContext
    };
  }

  private executeMockOperation(
    entry: OperationRegistryEntry,
    operationKey: string,
    scope: ExecutionScope
  ): OperationExecutionResult {
    const startedAt = this.now().toISOString();
    const fixture = this.mockFixtures[operationKey] ?? {};
    const payload =
      fixture.payload ??
      (fixture.status === 'empty'
        ? []
        : fixture.status === 'unauthorized' || fixture.status === 'unsupported_environment' || fixture.status === 'error'
          ? undefined
          : buildDefaultMockPayload(entry, scope));
    const status = fixture.status ?? inferStatusFromPayload(payload);
    const error = fixture.error ?? buildDefaultError(status, operationKey);
    const endedAt = this.now().toISOString();

    return {
      status,
      startTime: startedAt,
      endTime: endedAt,
      payload,
      error,
      requestContext: fixture.requestContext
    };
  }

  private async executeLiveOperation(
    entry: OperationRegistryEntry,
    requestContext: RequestContext,
    scope: ExecutionScope
  ): Promise<OperationExecutionResult> {
    if (!this.client) {
      const timestamp = this.now().toISOString();
      return {
        status: 'error',
        startTime: timestamp,
        endTime: timestamp,
        error: new Error('Registry executor requires a Deere SDK client in non-mock mode.'),
        requestContext
      };
    }

    const args = buildInvocationArgs(entry, scope);

    if (entry.sdkPath === 'deere.safe.fieldOperations.listAllWithMeasurements') {
      const result = await (
        this.client.listFieldOperationsWithMeasurements as (...callArgs: unknown[]) => Promise<DeereClientCallResult<unknown>>
      )(...args);
      return toOperationExecutionResult(result, requestContext);
    }

    const target = resolveSdkTarget(this.client.sdk, entry.sdkPath);

    if (!target) {
      const timestamp = this.now().toISOString();
      return {
        status: 'unsupported_by_sdk',
        startTime: timestamp,
        endTime: timestamp,
        error: {
          reason: 'SDK path could not be resolved at runtime.',
          sdkPath: entry.sdkPath
        },
        requestContext
      };
    }

    const result = await this.client.run(() => target.method(...args));
    return toOperationExecutionResult(result, requestContext);
  }

  private mapNormalizedOutputs(
    entry: OperationRegistryEntry,
    payload: unknown,
    mapper: JohnDeereCanonicalMapper,
    scope: ExecutionScope
  ): NormalizedFile[] {
    const records = toRecordArray(payload);

    switch (entry.apiGroup) {
      case 'organizations':
        return records.map((record) => mapper.mapOrganization(record).file);
      case 'farms':
        return records.map((record) => mapper.mapFarm(record).file);
      case 'fields':
        return records.map((record) => mapper.mapField(record, { farm: scope.farm }).file);
      case 'boundaries':
        return records.map((record) => mapper.mapBoundary(record, { farm: scope.farm, field: scope.field }).file);
      case 'equipment':
        return records.map((record) => mapper.mapEquipment(record).file);
      case 'operators':
        return records.map((record) => mapper.mapOperator(record).file);
      case 'cropTypes':
        return records.map((record) => mapper.mapCropType(record).file);
      case 'products':
        return records.map((record) => mapper.mapProduct(record).file);
      case 'fieldOperations':
        return records.flatMap((record) => mapper.mapFieldOperation(record, { farm: scope.farm, field: scope.field }).files);
      default:
        return [];
    }
  }
}

function resolveSdkTarget(
  root: DeereLike,
  sdkPath: string
): { parent: Record<string, unknown>; method: (...args: unknown[]) => Promise<unknown> } | null {
  const segments = sdkPath.split('.').slice(1);
  let current: unknown = root as unknown;

  for (let index = 0; index < segments.length - 1; index += 1) {
    if (!current || typeof current !== 'object') {
      return null;
    }

    current = (current as Record<string, unknown>)[segments[index]];
  }

  if (!current || typeof current !== 'object') {
    return null;
  }

  const parent = current as Record<string, unknown>;
  const leaf = parent[segments[segments.length - 1]];

  if (typeof leaf !== 'function') {
    return null;
  }

  return {
    parent,
    method: (...args) => (leaf as (...methodArgs: unknown[]) => Promise<unknown>).apply(parent, args)
  };
}

function buildInvocationArgs(entry: OperationRegistryEntry, scope: ExecutionScope): unknown[] {
  const args: unknown[] = [scope.orgId];

  if (!LIST_LIKE_OPERATIONS.has(entry.operation)) {
    switch (entry.entityScope) {
      case 'farm':
        if (scope.farm?.deereId) {
          args.push(scope.farm.deereId);
        }
        break;
      case 'field':
        if (scope.field?.deereId) {
          args.push(scope.field.deereId);
        }
        break;
      case 'farm_or_field':
        if (scope.field?.deereId) {
          args.push(scope.field.deereId);
        } else if (scope.farm?.deereId) {
          args.push(scope.farm.deereId);
        }
        break;
      case 'equipment':
      case 'grower_or_equipment':
        if (scope.equipmentId) {
          args.push(scope.equipmentId);
        }
        break;
      case 'machine':
        if (scope.machineId) {
          args.push(scope.machineId);
        }
        break;
      default:
        break;
    }
  }

  return args;
}

function toOperationExecutionResult(
  result: DeereClientCallResult<unknown>,
  requestContext: RequestContext
): OperationExecutionResult {
  return {
    status:
      result.status === 'unsupported'
        ? 'unsupported_by_sdk'
        : result.status,
    startTime: result.startTime,
    endTime: result.endTime,
    payload: result.data,
    error: result.error,
    requestContext: {
      ...requestContext,
      attempts: result.attempts,
      refreshed: result.refreshed
    }
  };
}

function mapExecutionStatus(status: ExecutableOperationStatus): OperationRegistryStatus {
  return status;
}

function inferStatusFromPayload(payload: unknown): ExecutableOperationStatus {
  if (payload == null) {
    return 'empty';
  }

  if (Array.isArray(payload)) {
    return payload.length === 0 ? 'empty' : 'accessible';
  }

  if (typeof payload === 'object' && payload !== null && 'values' in payload && Array.isArray(payload.values)) {
    return payload.values.length === 0 ? 'empty' : 'accessible';
  }

  return 'accessible';
}

function buildDefaultError(status: ExecutableOperationStatus, operationKey: string): unknown {
  switch (status) {
    case 'unauthorized':
      return { name: 'UnauthorizedError', message: `Mock fixture denied access to ${operationKey}.` };
    case 'unsupported_environment':
      return { name: 'UnsupportedEnvironmentError', message: `Mock fixture rejected ${operationKey} for the active environment.` };
    case 'error':
      return { name: 'MockExecutionError', message: `Mock fixture failed ${operationKey}.` };
    default:
      return undefined;
  }
}

function buildDefaultMockPayload(entry: OperationRegistryEntry, scope: ExecutionScope): unknown {
  const farm = scope.farm ?? { deereId: 'mock-farm-1', displayName: 'Mock Farm 1', slug: 'mock-farm-1' };
  const field = scope.field ?? {
    deereId: 'mock-field-1',
    displayName: 'Mock Field 1',
    slug: 'mock-field-1'
  };

  switch (entry.apiGroup) {
    case 'organizations':
      return [{ id: scope.orgId, name: `Organization ${scope.orgId}` }];
    case 'farms':
      return [{ id: farm.deereId, name: farm.displayName ?? 'Mock Farm 1' }];
    case 'fields':
      return [{ id: field.deereId, name: field.displayName ?? 'Mock Field 1', farmId: farm.deereId, farmName: farm.displayName }];
    case 'boundaries':
      return [
        {
          id: 'mock-boundary-1',
          farmId: farm.deereId,
          farmName: farm.displayName,
          fieldId: field.deereId,
          fieldName: field.displayName,
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [-93.0, 41.0],
                [-92.9, 41.0],
                [-92.9, 41.1],
                [-93.0, 41.1],
                [-93.0, 41.0]
              ]
            ]
          }
        }
      ];
    case 'fieldOperations':
      return [
        {
          id: 'mock-field-op-1',
          operationType: 'Planting',
          operationDate: '2026-04-01T00:00:00.000Z',
          farmId: farm.deereId,
          farmName: farm.displayName,
          fieldId: field.deereId,
          fieldName: field.displayName
        }
      ];
    case 'equipment':
      return [{ id: scope.equipmentId ?? 'mock-equipment-1', name: 'Mock Tractor' }];
    case 'operators':
      return [{ id: 'mock-operator-1', name: 'Mock Operator' }];
    case 'products':
      return [{ id: 'mock-product-1', name: 'Mock Seed', productType: 'seed' }];
    case 'cropTypes':
      return [{ id: 'mock-crop-type-1', name: 'Corn' }];
    case 'machineLocations':
    case 'machineAlerts':
    case 'machineEngineHours':
    case 'machineHoursOfOperation':
    case 'machineDeviceStateReports':
      return [{ id: scope.machineId ?? 'mock-machine-1', machineId: scope.machineId ?? 'mock-machine-1' }];
    default:
      return [{ id: `${entry.apiGroup}-${entry.operation}-1`, name: `Mock ${entry.apiGroup} ${entry.operation}` }];
  }
}

function toRecordArray(payload: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(payload)) {
    return payload.filter((value): value is Record<string, unknown> => isRecord(value));
  }

  if (isRecord(payload) && Array.isArray(payload.values)) {
    return payload.values.filter((value): value is Record<string, unknown> => isRecord(value));
  }

  if (isRecord(payload)) {
    return [payload];
  }

  return [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toOperationKey(entry: Pick<OperationRegistryEntry, 'apiGroup' | 'operation'>): string {
  return `${entry.apiGroup}.${entry.operation}`;
}

function serializeErrorDetails(error: unknown): unknown {
  if (error === undefined) {
    return undefined;
  }

  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      ...(error.stack ? { stack: error.stack } : {})
    };
  }

  return error;
}

function toDataRelativePath(dataRoot: string, filePath: string): string {
  return path.relative(dataRoot, filePath).split(path.sep).join('/');
}

function deriveIdOrPage(payload: unknown, fallback: string): string {
  const firstRecord = toRecordArray(payload)[0];
  const idCandidate =
    readString(firstRecord?.id) ??
    readString(firstRecord?.deereId) ??
    readString(firstRecord?.fieldId) ??
    readString(firstRecord?.farmId) ??
    fallback;

  return idCandidate;
}

function deriveCursor(payload: unknown, fallback: string): string {
  const timestamps = toRecordArray(payload)
    .flatMap((record) => [record.updatedAt, record.updatedTime, record.operationDate, record.lastModifiedTime])
    .map(readString)
    .filter((value): value is string => Boolean(value));

  return timestamps.at(-1) ?? fallback;
}

function deriveFingerprint(payload: unknown, status: OperationRegistryStatus): string {
  return createHash('sha1')
    .update(JSON.stringify({ status, payload: payload ?? null }))
    .digest('hex');
}

function shouldSkipByCheckpoint(checkpoint: CheckpointState, operation: string, since?: string): boolean {
  if (!since) {
    return false;
  }

  const cursor = checkpoint.operationCursors[operation];
  if (!cursor?.updatedAt) {
    return false;
  }

  const sinceTime = Date.parse(since);
  const updatedAtTime = Date.parse(cursor.updatedAt);

  if (Number.isNaN(sinceTime) || Number.isNaN(updatedAtTime)) {
    return false;
  }

  return updatedAtTime >= sinceTime;
}

function deriveRunStatus(operations: readonly OperationManifestRecord[]): string {
  if (operations.some((operation) => operation.status === 'error')) {
    return 'completed_with_errors';
  }

  if (
    operations.some((operation) =>
      ['unauthorized', 'unsupported_by_sdk', 'unsupported_environment', 'disabled_by_default'].includes(operation.status)
    )
  ) {
    return 'completed_with_warnings';
  }

  return 'completed';
}

function uniquePaths(paths: Iterable<string>): string[] {
  return [...new Set(paths)];
}

function readString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function updateScopeFromPayload(entry: OperationRegistryEntry, payload: unknown, scope: ExecutionScope): void {
  const firstRecord = toRecordArray(payload)[0];

  if (!firstRecord) {
    return;
  }

  if (entry.apiGroup === 'farms') {
    const farmId = readString(firstRecord.id) ?? readString(firstRecord.deereId);
    if (farmId) {
      scope.farm = {
        deereId: farmId,
        displayName: readString(firstRecord.name) ?? readString(firstRecord.displayName) ?? farmId,
        slug: scope.farm?.slug
      };
    }
  }

  if (entry.apiGroup === 'fields') {
    const fieldId = readString(firstRecord.id) ?? readString(firstRecord.deereId);
    if (fieldId) {
      scope.field = {
        deereId: fieldId,
        displayName: readString(firstRecord.name) ?? readString(firstRecord.displayName) ?? fieldId,
        slug: scope.field?.slug
      };
    }

    const farmId = readString(firstRecord.farmId);
    if (farmId && !scope.farm) {
      scope.farm = {
        deereId: farmId,
        displayName: readString(firstRecord.farmName) ?? farmId
      };
    }
  }

  if (entry.apiGroup === 'equipment') {
    scope.equipmentId = readString(firstRecord.id) ?? readString(firstRecord.deereId) ?? scope.equipmentId;
  }

  if (entry.apiGroup.startsWith('machine')) {
    scope.machineId =
      readString(firstRecord.machineId) ?? readString(firstRecord.id) ?? readString(firstRecord.deereId) ?? scope.machineId;
  }
}
