import {
  AuthError,
  Deere,
  DeereError,
  type DeereClientConfig,
  type FieldOperationsApi
} from 'deere-sdk';

import type { JohnDeereOAuthEnvironment } from '../oauth/endpoints.js';
import {
  refreshAccessToken,
  type RefreshAccessTokenOptions,
  type StoredToken,
  type TokenStore,
  type TokenStoreKey
} from '../tokens/store.js';

export type DeereClientCallStatus =
  | 'accessible'
  | 'unauthorized'
  | 'unsupported'
  | 'unsupported_environment'
  | 'empty'
  | 'error';

export interface DeereClientCallResult<T> {
  status: DeereClientCallStatus;
  startTime: string;
  endTime: string;
  data?: T;
  error?: unknown;
  attempts: number;
  refreshed: boolean;
}

export interface DeereClientRefreshConfig {
  tokenStore: TokenStore;
  tokenStoreKey: TokenStoreKey;
  clientId: string;
  clientSecret: string;
  discoveryUrl?: string;
}

export interface DeereSdkClientOptions {
  accessToken: string;
  environment: JohnDeereOAuthEnvironment;
  hateoas?: boolean;
  fetch?: typeof fetch;
  refresh?: DeereClientRefreshConfig;
}

export interface DeereSdkClientDependencies {
  deereFactory?: (config: DeereClientConfig & { hateoas?: boolean }) => DeereLike;
  refreshAccessToken?: (options: RefreshAccessTokenOptions) => Promise<StoredToken>;
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
}

type DeereEnvironment = DeereClientConfig['environment'];

type DeereFieldOperationsListAllArgs = Parameters<FieldOperationsApi['listAll']>;
type DeereFieldOperationsListAllReturn = Awaited<ReturnType<FieldOperationsApi['listAll']>>;

interface DeereSafeLike {
  fieldOperations?: {
    listAllWithMeasurements?: (...args: DeereFieldOperationsListAllArgs) => Promise<DeereFieldOperationsListAllReturn>;
  };
}

export interface DeereLike {
  fieldOperations: {
    listAll: (...args: DeereFieldOperationsListAllArgs) => Promise<DeereFieldOperationsListAllReturn>;
  };
  safe?: DeereSafeLike;
}

const MAX_RATE_LIMIT_RETRIES = 3;

export class DeereSdkClient {
  private readonly options: DeereSdkClientOptions;
  private readonly deereFactory: (config: DeereClientConfig & { hateoas?: boolean }) => DeereLike;
  private readonly refreshTokenFn: (options: RefreshAccessTokenOptions) => Promise<StoredToken>;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly random: () => number;

  private deere: DeereLike;

  constructor(options: DeereSdkClientOptions, dependencies: DeereSdkClientDependencies = {}) {
    this.options = options;
    this.deereFactory = dependencies.deereFactory ?? ((config) => new Deere(config));
    this.refreshTokenFn = dependencies.refreshAccessToken ?? refreshAccessToken;
    this.sleep = dependencies.sleep ?? defaultSleep;
    this.random = dependencies.random ?? Math.random;
    this.deere = this.instantiateDeere(options.accessToken);
  }

  get sdk(): DeereLike {
    return this.deere;
  }

  async run<T>(operation: (deere: DeereLike) => Promise<T>): Promise<DeereClientCallResult<T>> {
    const startTime = new Date();
    let attempts = 0;
    let rateLimitRetries = 0;
    let refreshed = false;

    while (true) {
      attempts += 1;

      try {
        const data = await operation(this.deere);
        const endTime = new Date();

        return {
          status: isEmptyResponse(data) ? 'empty' : 'accessible',
          startTime: startTime.toISOString(),
          endTime: endTime.toISOString(),
          data,
          attempts,
          refreshed
        };
      } catch (error) {
        const statusCode = getErrorStatus(error);

        if (statusCode === 401) {
          if (!refreshed && this.options.refresh) {
            try {
              const token = await this.refreshTokenFn({
                environment: this.options.environment,
                tokenStore: this.options.refresh.tokenStore,
                tokenStoreKey: this.options.refresh.tokenStoreKey,
                clientId: this.options.refresh.clientId,
                clientSecret: this.options.refresh.clientSecret,
                discoveryUrl: this.options.refresh.discoveryUrl,
                fetch: this.options.fetch
              });

              refreshed = true;
              this.deere = this.instantiateDeere(token.accessToken);
              continue;
            } catch (refreshError) {
              return this.buildFailureResult('unauthorized', startTime, attempts, refreshed, refreshError);
            }
          }

          return this.buildFailureResult('unauthorized', startTime, attempts, refreshed, error);
        }

        if (statusCode === 403 || error instanceof AuthError) {
          return this.buildFailureResult('unauthorized', startTime, attempts, refreshed, error);
        }

        if (statusCode === 429 && rateLimitRetries < MAX_RATE_LIMIT_RETRIES) {
          const delayMs = calculateRetryDelayMs(rateLimitRetries, this.random);
          rateLimitRetries += 1;
          await this.sleep(delayMs);
          continue;
        }

        if (isEnvironmentMismatchError(error)) {
          return this.buildFailureResult('unsupported_environment', startTime, attempts, refreshed, error);
        }

        if (statusCode === 404) {
          return this.buildFailureResult('unsupported', startTime, attempts, refreshed, error);
        }

        return this.buildFailureResult('error', startTime, attempts, refreshed, error);
      }
    }
  }

  async listFieldOperationsWithMeasurements(
    ...args: DeereFieldOperationsListAllArgs
  ): Promise<DeereClientCallResult<DeereFieldOperationsListAllReturn>> {
    return this.run((deere) => {
      const safeList = deere.safe?.fieldOperations?.listAllWithMeasurements;

      if (typeof safeList === 'function') {
        return safeList(...args);
      }

      return deere.fieldOperations.listAll(...args);
    });
  }

  private instantiateDeere(accessToken: string): DeereLike {
    const sdkEnvironment = toSdkEnvironment(this.options.environment);

    const config: DeereClientConfig & { hateoas?: boolean } = {
      accessToken,
      environment: sdkEnvironment,
      fetch: this.options.fetch,
      maxRetries: 0,
      ...(this.options.hateoas ? { hateoas: true } : {})
    };

    return this.deereFactory(config);
  }

  private buildFailureResult<T>(
    status: DeereClientCallStatus,
    startTime: Date,
    attempts: number,
    refreshed: boolean,
    error: unknown
  ): DeereClientCallResult<T> {
    return {
      status,
      startTime: startTime.toISOString(),
      endTime: new Date().toISOString(),
      error,
      attempts,
      refreshed
    };
  }
}

export function calculateRetryDelayMs(attempt: number, random: () => number = Math.random): number {
  const baseDelayMs = 1000 * 2 ** attempt;
  const jitterMs = Math.floor(random() * 250);
  return baseDelayMs + jitterMs;
}

function toSdkEnvironment(environment: JohnDeereOAuthEnvironment): DeereEnvironment {
  return environment === 'sandboxapi' ? 'sandbox' : environment;
}

function getErrorStatus(error: unknown): number | undefined {
  if (error instanceof DeereError) {
    return error.status;
  }

  if (typeof error === 'object' && error !== null && 'status' in error && typeof error.status === 'number') {
    return error.status;
  }

  return undefined;
}

function isEnvironmentMismatchError(error: unknown): boolean {
  const haystack = [
    error instanceof Error ? error.message : undefined,
    error instanceof DeereError ? stringifyUnknown(error.body) : undefined,
    stringifyUnknown(error)
  ]
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
    .join(' ')
    .toLowerCase();

  return /environment/.test(haystack);
}

function isEmptyResponse(value: unknown): boolean {
  if (value == null) {
    return true;
  }

  if (Array.isArray(value)) {
    return value.length === 0;
  }

  if (typeof value === 'object' && 'values' in value && Array.isArray(value.values)) {
    return value.values.length === 0;
  }

  return false;
}

function stringifyUnknown(value: unknown): string | undefined {
  if (typeof value === 'string') {
    return value;
  }

  if (value == null) {
    return undefined;
  }

  try {
    return JSON.stringify(value);
  } catch {
    return undefined;
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
