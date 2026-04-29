import { AuthError, DeereError, RateLimitError, type DeereClientConfig } from 'deere-sdk';
import { describe, expect, it, vi } from 'vitest';

import { DeereSdkClient } from '../../src/client/deere-client.js';
import type { RefreshAccessTokenOptions, StoredToken } from '../../src/tokens/store.js';

function createFieldOperationsApi() {
  return {
    listAll: vi.fn()
  };
}

describe('DeereSdkClient', () => {
  it('instantiates Deere with access token, mapped environment, and hateoas flag', async () => {
    const configs: Array<DeereClientConfig & { hateoas?: boolean }> = [];
    const fieldOperations = createFieldOperationsApi();
    fieldOperations.listAll.mockResolvedValue([{ id: 'field-op-1' }]);

    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi',
        hateoas: true
      },
      {
        deereFactory: (config) => {
          configs.push(config);
          return { fieldOperations };
        }
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('accessible');
    expect(result.data).toEqual([{ id: 'field-op-1' }]);
    expect(result.startTime <= result.endTime).toBe(true);
    expect(configs).toEqual([
      expect.objectContaining({
        accessToken: 'access-token-1',
        environment: 'sandbox',
        hateoas: true,
        maxRetries: 0
      })
    ]);
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    const configs: Array<DeereClientConfig & { hateoas?: boolean }> = [];
    const refreshedToken: StoredToken = {
      accessToken: 'access-token-2',
      refreshToken: 'refresh-token-2',
      expiresAt: '2026-04-28T12:00:00.000Z',
      tokenType: 'Bearer',
      scope: 'ag1 offline_access'
    };
    const refreshSpy = vi.fn(async (_options: RefreshAccessTokenOptions): Promise<StoredToken> => refreshedToken);
    let invocation = 0;

    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'production',
        refresh: {
          tokenStore: {} as never,
          tokenStoreKey: { grower: 'demo-grower' },
          clientId: 'client-1',
          clientSecret: 'secret-1'
        }
      },
      {
        refreshAccessToken: refreshSpy,
        deereFactory: (config) => {
          configs.push(config);

          return {
            fieldOperations: {
              listAll: vi.fn(async () => {
                invocation += 1;
                if (invocation === 1) {
                  throw new AuthError('expired token', 401, 'Unauthorized');
                }

                return [{ id: 'field-op-2' }];
              })
            }
          };
        }
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('accessible');
    expect(result.refreshed).toBe(true);
    expect(result.attempts).toBe(2);
    expect(result.data).toEqual([{ id: 'field-op-2' }]);
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(configs).toEqual([
      expect.objectContaining({ accessToken: 'access-token-1', environment: 'production' }),
      expect.objectContaining({ accessToken: 'access-token-2', environment: 'production' })
    ]);
  });

  it('classifies 403 responses as unauthorized', async () => {
    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi'
      },
      {
        deereFactory: () => ({
          fieldOperations: {
            listAll: vi.fn(async () => {
              throw new AuthError('forbidden', 403, 'Forbidden');
            })
          }
        })
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('unauthorized');
    expect(result.error).toBeInstanceOf(AuthError);
  });

  it('retries 429 responses with exponential backoff and jitter', async () => {
    const sleepSpy = vi.fn(async () => undefined);
    let attempts = 0;

    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi'
      },
      {
        sleep: sleepSpy,
        random: () => 0,
        deereFactory: () => ({
          fieldOperations: {
            listAll: vi.fn(async () => {
              attempts += 1;

              if (attempts < 3) {
                throw new RateLimitError('slow down', 429, 'Too Many Requests', 1);
              }

              return [{ id: 'field-op-3' }];
            })
          }
        })
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('accessible');
    expect(result.attempts).toBe(3);
    expect(sleepSpy).toHaveBeenNthCalledWith(1, 1000);
    expect(sleepSpy).toHaveBeenNthCalledWith(2, 2000);
  });

  it('classifies environment mismatch errors as unsupported_environment', async () => {
    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi'
      },
      {
        deereFactory: () => ({
          fieldOperations: {
            listAll: vi.fn(async () => {
              throw new DeereError('Requested resource is not available in this environment.', 400, 'Bad Request');
            })
          }
        })
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('unsupported_environment');
  });

  it('classifies empty responses as empty', async () => {
    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi'
      },
      {
        deereFactory: () => ({
          fieldOperations: {
            listAll: vi.fn(async () => [])
          }
        })
      }
    );

    const result = await client.run((deere) => deere.fieldOperations.listAll('org-1', 'field-1'));

    expect(result.status).toBe('empty');
    expect(result.data).toEqual([]);
  });

  it('uses the safe field operations measurement path when available', async () => {
    const safeListAllWithMeasurements = vi.fn(async () => [{ id: 'field-op-safe' }]);
    const listAll = vi.fn(async () => [{ id: 'field-op-fallback' }]);
    const client = new DeereSdkClient(
      {
        accessToken: 'access-token-1',
        environment: 'sandboxapi'
      },
      {
        deereFactory: () => ({
          safe: {
            fieldOperations: {
              listAllWithMeasurements: safeListAllWithMeasurements
            }
          },
          fieldOperations: {
            listAll
          }
        })
      }
    );

    const result = await client.listFieldOperationsWithMeasurements('org-1', 'field-1');

    expect(result.status).toBe('accessible');
    expect(result.data).toEqual([{ id: 'field-op-safe' }]);
    expect(safeListAllWithMeasurements).toHaveBeenCalledWith('org-1', 'field-1');
    expect(listAll).not.toHaveBeenCalled();
  });
});
