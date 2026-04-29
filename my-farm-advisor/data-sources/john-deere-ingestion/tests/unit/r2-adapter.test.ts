import { describe, expect, it } from 'vitest';

import {
  adaptOperationRecord,
  adaptRunManifest,
  R2_PATH_MAPPING,
  defaultR2ManifestAdapter
} from '../../src/adapters/r2-manifest.js';

import type { OperationManifestRecord, RunManifestDocument } from '../../src/storage/manifest.js';

describe('adaptOperationRecord', () => {
  it('maps JD operation record fields to R2 conventions', () => {
    const record: OperationManifestRecord = {
      operation: 'organizations.list',
      status: 'accessible',
      startTime: '2026-04-29T10:00:00Z',
      endTime: '2026-04-29T10:00:01Z',
      outputPaths: ['growers/g1/source/john-deere/raw/organizations/list/2026/04/29/file.json'],
      errorDetails: undefined,
      requestContext: {}
    };

    const adapted = adaptOperationRecord(record);

    expect(adapted.operation).toBe('organizations.list');
    expect(adapted.status).toBe('accessible');
    expect(adapted.startedAt).toBe('2026-04-29T10:00:00Z');
    expect(adapted.completedAt).toBe('2026-04-29T10:00:01Z');
    expect(adapted.outputPaths).toEqual(record.outputPaths);
    expect(adapted.errorMessage).toBeUndefined();
  });

  it('stringifies error details when present', () => {
    const record: OperationManifestRecord = {
      operation: 'fields.list',
      status: 'error',
      startTime: '2026-04-29T11:00:00Z',
      endTime: '2026-04-29T11:00:02Z',
      outputPaths: [],
      errorDetails: { code: 500, message: 'Internal error' },
      requestContext: {}
    };

    const adapted = adaptOperationRecord(record);

    expect(adapted.errorMessage).toBe('[object Object]');
  });

  it('preserves error details string when already a string', () => {
    const record: OperationManifestRecord = {
      operation: 'farms.list',
      status: 'error',
      startTime: '2026-04-29T11:00:00Z',
      endTime: '2026-04-29T11:00:02Z',
      outputPaths: [],
      errorDetails: 'Network timeout',
      requestContext: {}
    };

    const adapted = adaptOperationRecord(record);

    expect(adapted.errorMessage).toBe('Network timeout');
  });
});

describe('adaptRunManifest', () => {
  it('maps JD run manifest to R2 run summary', () => {
    const manifest: RunManifestDocument = {
      growerSlug: 'iowa-demo-grower',
      runId: '2026-04-29T12-00-00Z',
      status: 'completed',
      startTime: '2026-04-29T12:00:00Z',
      endTime: '2026-04-29T12:05:00Z',
      totalDurationMs: 300000,
      outputPaths: ['path/one.json', 'path/two.json'],
      requestContext: { env: 'sandboxapi' },
      operations: [
        {
          operation: 'organizations.list',
          status: 'accessible',
          startTime: '2026-04-29T12:00:00Z',
          endTime: '2026-04-29T12:00:01Z',
          outputPaths: [],
          requestContext: {}
        },
        {
          operation: 'fields.list',
          status: 'unauthorized',
          startTime: '2026-04-29T12:00:02Z',
          endTime: '2026-04-29T12:00:02Z',
          outputPaths: [],
          requestContext: {}
        }
      ],
      statusCounts: {
        accessible: 1,
        unauthorized: 1
      },
      nextCheckpoint: {
        lastSuccessfulRun: '2026-04-29T12-00-00Z',
        operationCursorCount: 2,
        outputPaths: ['path/one.json']
      }
    };

    const summary = adaptRunManifest(manifest);

    expect(summary.growerSlug).toBe('iowa-demo-grower');
    expect(summary.runId).toBe('2026-04-29T12-00-00Z');
    expect(summary.status).toBe('completed');
    expect(summary.startedAt).toBe('2026-04-29T12:00:00Z');
    expect(summary.completedAt).toBe('2026-04-29T12:05:00Z');
    expect(summary.durationMs).toBe(300000);
    expect(summary.totalOperations).toBe(2);
    expect(summary.statusBreakdown).toEqual({ accessible: 1, unauthorized: 1 });
    expect(summary.checkpoint).toEqual({
      lastSuccessfulRun: '2026-04-29T12-00-00Z',
      operationCursorCount: 2,
      outputPaths: ['path/one.json']
    });
  });

  it('computes totalOperations from the operations array length', () => {
    const manifest: RunManifestDocument = {
      growerSlug: 'g1',
      runId: 'run-1',
      status: 'completed',
      startTime: '2026-04-29T12:00:00Z',
      endTime: '2026-04-29T12:00:00Z',
      totalDurationMs: 0,
      outputPaths: [],
      requestContext: {},
      operations: [],
      statusCounts: {},
      nextCheckpoint: {
        lastSuccessfulRun: null,
        operationCursorCount: 0,
        outputPaths: []
      }
    };

    const summary = adaptRunManifest(manifest);
    expect(summary.totalOperations).toBe(0);
  });
});

describe('R2_PATH_MAPPING', () => {
  it('produces canonical grower manifest path', () => {
    expect(R2_PATH_MAPPING.growerManifests('iowa-demo-grower')).toBe(
      'growers/iowa-demo-grower/manifests/john-deere/'
    );
  });

  it('produces canonical farm manifest path', () => {
    expect(R2_PATH_MAPPING.farmManifests('iowa-demo-grower', 'demo-farm')).toBe(
      'growers/iowa-demo-grower/farms/demo-farm/manifests/john-deere/'
    );
  });

  it('produces canonical field manifest path', () => {
    expect(R2_PATH_MAPPING.fieldManifests('iowa-demo-grower', 'demo-farm', 'north-40')).toBe(
      'growers/iowa-demo-grower/farms/demo-farm/fields/north-40/manifests/john-deere/'
    );
  });

  it('produces raw manifest path', () => {
    expect(R2_PATH_MAPPING.rawManifests('iowa-demo-grower')).toBe(
      'growers/iowa-demo-grower/source/john-deere/manifests/'
    );
  });

  it('produces grower file path', () => {
    expect(R2_PATH_MAPPING.growerFile('iowa-demo-grower')).toBe(
      'growers/iowa-demo-grower/grower.john-deere.json'
    );
  });

  it('produces farm file path', () => {
    expect(R2_PATH_MAPPING.farmFile('iowa-demo-grower', 'demo-farm')).toBe(
      'growers/iowa-demo-grower/farms/demo-farm/farm.john-deere.json'
    );
  });

  it('produces field file path', () => {
    expect(R2_PATH_MAPPING.fieldFile('iowa-demo-grower', 'demo-farm', 'north-40')).toBe(
      'growers/iowa-demo-grower/farms/demo-farm/fields/north-40/field.john-deere.json'
    );
  });

  it('produces field boundary file path', () => {
    expect(R2_PATH_MAPPING.fieldBoundaryFile('iowa-demo-grower', 'demo-farm', 'north-40')).toBe(
      'growers/iowa-demo-grower/farms/demo-farm/fields/north-40/boundary/field_boundary.john-deere.geojson'
    );
  });
});

describe('defaultR2ManifestAdapter', () => {
  it('exposes the same functions as the standalone exports', () => {
    const record: OperationManifestRecord = {
      operation: 'organizations.list',
      status: 'accessible',
      startTime: '2026-04-29T10:00:00Z',
      endTime: '2026-04-29T10:00:01Z',
      outputPaths: [],
      requestContext: {}
    };

    expect(defaultR2ManifestAdapter.adaptOperationRecord(record)).toEqual(
      adaptOperationRecord(record)
    );

    const manifest: RunManifestDocument = {
      growerSlug: 'g1',
      runId: 'run-1',
      status: 'completed',
      startTime: '2026-04-29T10:00:00Z',
      endTime: '2026-04-29T10:00:01Z',
      totalDurationMs: 1000,
      outputPaths: [],
      requestContext: {},
      operations: [record],
      statusCounts: { accessible: 1 },
      nextCheckpoint: {
        lastSuccessfulRun: '2026-04-29T10-00-00Z',
        operationCursorCount: 1,
        outputPaths: []
      }
    };

    expect(defaultR2ManifestAdapter.adaptRunManifest(manifest)).toEqual(
      adaptRunManifest(manifest)
    );
  });
});
