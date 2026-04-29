import { createHash, randomBytes as defaultRandomBytes } from 'node:crypto';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import readline from 'node:readline/promises';

import type { CliConfig } from '../config.js';
import { resolveOAuthEndpoints, type JohnDeereOAuthEndpoints } from '../oauth/endpoints.js';
import { FileTokenStore } from '../tokens/file-store.js';
import type { StoredToken, TokenStore } from '../tokens/store.js';

export const DEFAULT_JD_OAUTH_SCOPES = ['ag1', 'eq1', 'files', 'offline_access', 'org2'] as const;
export const DEFAULT_CALLBACK_TIMEOUT_MS = 120_000;

const LOCAL_CALLBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1']);

export interface InitFlowOptions {
  config: CliConfig;
  fetch?: typeof fetch;
  tokenStore?: TokenStore;
  stdin?: NodeJS.ReadableStream;
  stdout?: NodeJS.WritableStream;
  authorizationCode?: string;
  callbackTimeoutMs?: number;
  now?: () => Date;
  randomBytes?: (size: number) => Buffer;
  createServer?: typeof createServer;
}

export interface RefreshAccessTokenOptions {
  config: CliConfig;
  fetch?: typeof fetch;
  tokenStore?: TokenStore;
  now?: () => Date;
}

export interface InitFlowResult {
  authorizationUrl: string;
  tokenStorePath: string;
  dryRun: boolean;
  token?: StoredToken;
  authorizationCodeSource?: AuthorizationCodeSource;
  orgConnection: OrgConnectionStatus;
  outputLines: string[];
}

export interface OrgConnectionStatus {
  checked: boolean;
  required: boolean;
  organizationCount: number;
  organizationNamesRequiringConnection: string[];
  message: string;
}

export type AuthorizationCodeSource = 'cli-arg' | 'stdin' | 'local-callback';

interface AuthorizationContext {
  state: string;
  scope: string;
  codeVerifier: string;
  codeChallenge: string;
}

interface AuthorizationCodeResolution {
  code: string;
  source: AuthorizationCodeSource;
}

interface OAuthTokenPayload {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
  scope?: string;
}

interface CallbackListener {
  waitForCode: () => Promise<string>;
  close: () => Promise<void>;
  listenerUrl: string;
}

export async function initJohnDeereAuth(options: InitFlowOptions): Promise<InitFlowResult> {
  const config = options.config;
  const fetchImpl = options.fetch ?? globalThis.fetch;
  const tokenStore = options.tokenStore ?? new FileTokenStore({ dataRoot: config.dataRoot });
  const now = options.now ?? (() => new Date());
  const authorization = createAuthorizationContext(options.randomBytes ?? defaultRandomBytes);
  const endpoints = await resolveOAuthEndpoints({ environment: config.environment, fetch: fetchImpl });
  const authorizationUrl = buildAuthorizationUrl({
    config,
    endpoints,
    state: authorization.state,
    scope: authorization.scope,
    codeChallenge: authorization.codeChallenge
  });

  const outputLines = [
    'John Deere init',
    `environment: ${config.environment}`,
    `authorizationUrl: ${authorizationUrl}`,
    `tokenStorePath: ${config.tokenStorePath}`
  ];

  if (config.dryRun) {
    outputLines.push('dry-run: token exchange skipped; no token files written.');

    return {
      authorizationUrl,
      tokenStorePath: config.tokenStorePath,
      dryRun: true,
      orgConnection: {
        checked: false,
        required: false,
        organizationCount: 0,
        organizationNamesRequiringConnection: [],
        message: 'dry-run: organization connection detection skipped.'
      },
      outputLines
    };
  }

  const codeResolution = await resolveAuthorizationCode({
    ...options,
    endpoints,
    authorization,
    authorizationUrl
  });
  outputLines.push(`authorizationCodeSource: ${codeResolution.source}`);

  const tokenResponse = await exchangeAuthorizationCode({
    config,
    endpoints,
    fetchImpl,
    authorizationCode: codeResolution.code,
    codeVerifier: authorization.codeVerifier
  });

  const storedToken = await tokenStore.save(buildTokenStoreKey(config), createStoredToken({
    tokenResponse,
    fallbackScope: authorization.scope,
    now: now()
  }));

  outputLines.push(`tokenSaved: yes (${storedToken.tokenType})`);
  outputLines.push(`tokenExpiresAt: ${storedToken.expiresAt}`);

  const orgConnection = await detectOrganizationConnections({
    endpoints,
    accessToken: storedToken.accessToken,
    fetchImpl
  });
  outputLines.push(`orgConnection: ${orgConnection.message}`);

  return {
    authorizationUrl,
    tokenStorePath: config.tokenStorePath,
    dryRun: false,
    token: storedToken,
    authorizationCodeSource: codeResolution.source,
    orgConnection,
    outputLines
  };
}

export async function refreshAccessToken(options: RefreshAccessTokenOptions): Promise<StoredToken> {
  const fetchImpl = options.fetch ?? globalThis.fetch;
  const tokenStore = options.tokenStore ?? new FileTokenStore({ dataRoot: options.config.dataRoot });
  const now = options.now ?? (() => new Date());
  const existingToken = await tokenStore.load(buildTokenStoreKey(options.config));

  if (!existingToken) {
    throw new Error(
      `Cannot refresh John Deere access token because no token record exists at ${options.config.tokenStorePath}.`
    );
  }

  const endpoints = await resolveOAuthEndpoints({ environment: options.config.environment, fetch: fetchImpl });
  const tokenResponse = await exchangeRefreshToken({
    config: options.config,
    endpoints,
    fetchImpl,
    refreshToken: existingToken.refreshToken
  });

  return tokenStore.update(buildTokenStoreKey(options.config), {
    accessToken: tokenResponse.access_token,
    refreshToken: tokenResponse.refresh_token ?? existingToken.refreshToken,
    expiresAt: createExpiryIsoString(tokenResponse.expires_in, now()),
    tokenType: tokenResponse.token_type,
    scope: normalizeScope(tokenResponse.scope, existingToken.scope)
  });
}

export function createAuthorizationContext(
  randomBytesImpl: (size: number) => Buffer = defaultRandomBytes
): AuthorizationContext {
  const codeVerifier = toBase64Url(randomBytesImpl(32));

  return {
    state: toBase64Url(randomBytesImpl(16)),
    scope: DEFAULT_JD_OAUTH_SCOPES.join(' '),
    codeVerifier,
    // Deere's shared Okta OAuth tenant supports PKCE with S256. Even when a confidential
    // client secret is present we still send a verifier/challenge pair so pasted codes and
    // local-loopback redirects are protected against interception.
    codeChallenge: toBase64Url(createHash('sha256').update(codeVerifier).digest())
  };
}

export function buildAuthorizationUrl(options: {
  config: CliConfig;
  endpoints: JohnDeereOAuthEndpoints;
  state: string;
  scope: string;
  codeChallenge: string;
}): string {
  const url = new URL(options.endpoints.authorizationEndpoint);

  url.searchParams.set('response_type', 'code');
  url.searchParams.set('client_id', options.config.clientId ?? 'missing-client-id');
  url.searchParams.set('redirect_uri', options.config.redirectUri);
  url.searchParams.set('scope', options.scope);
  url.searchParams.set('state', options.state);
  url.searchParams.set('code_challenge', options.codeChallenge);
  url.searchParams.set('code_challenge_method', 'S256');

  if (options.config.orgId) {
    url.searchParams.set('org_id', options.config.orgId);
  }

  return url.toString();
}

export async function startLocalCallbackListener(options: {
  redirectUri: string;
  expectedState: string;
  callbackTimeoutMs?: number;
  createServerImpl?: typeof createServer;
}): Promise<CallbackListener> {
  const redirectUrl = new URL(options.redirectUri);

  if (redirectUrl.protocol !== 'http:' || !LOCAL_CALLBACK_HOSTNAMES.has(redirectUrl.hostname)) {
    throw new Error(`Local callback requires an http localhost redirect URI. Received ${options.redirectUri}.`);
  }

  const createServerImpl = options.createServerImpl ?? createServer;
  const callbackPath = redirectUrl.pathname || '/callback';
  const callbackTimeoutMs = options.callbackTimeoutMs ?? DEFAULT_CALLBACK_TIMEOUT_MS;
  const server = createServerImpl();
  let resolved = false;

  const codePromise = new Promise<string>((resolve, reject) => {
    const finish = async (result: { code?: string; error?: unknown }) => {
      if (resolved) {
        return;
      }

      resolved = true;
      clearTimeout(timeoutHandle);
      await closeServer(server);
      if (result.error !== undefined) {
        reject(result.error);
      } else if (typeof result.code === 'string') {
        resolve(result.code);
      } else {
        reject(new Error('Authorization callback completed without a code.'));
      }
    };

    const timeoutHandle = setTimeout(() => {
      void finish({ error: new Error(`Timed out waiting for OAuth callback at ${options.redirectUri}.`) });
    }, callbackTimeoutMs);

    server.on('request', (request, response) => {
      void handleCallbackRequest({
        request,
        response,
        callbackPath,
        expectedState: options.expectedState,
        onSuccess: (code) => finish({ code }),
        onError: (error) => finish({ error })
      });
    });
  });

  const port = redirectUrl.port ? Number.parseInt(redirectUrl.port, 10) : 80;
  server.listen(port, redirectUrl.hostname);
  await new Promise<void>((resolve, reject) => {
    const handleListening = () => {
      cleanup();
      resolve();
    };
    const handleError = (error: Error) => {
      cleanup();
      reject(error);
    };
    const cleanup = () => {
      server.off('listening', handleListening);
      server.off('error', handleError);
    };

    server.once('listening', handleListening);
    server.once('error', handleError);
  });

  return {
    waitForCode: () => codePromise,
    close: async () => {
      resolved = true;
      await closeServer(server);
    },
    listenerUrl: options.redirectUri
  };
}

export function parseManualAuthorizationInput(input: string, expectedState?: string): string {
  const trimmed = input.trim();

  if (!trimmed) {
    throw new Error('Authorization code input cannot be empty.');
  }

  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    const url = new URL(trimmed);
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');

    if (!code) {
      throw new Error('The pasted callback URL does not contain an OAuth authorization code.');
    }

    if (expectedState && state && state !== expectedState) {
      throw new Error('The pasted callback URL state does not match the generated OAuth state.');
    }

    return code;
  }

  if (trimmed.includes('code=')) {
    const queryIndex = trimmed.indexOf('?');
    const query = queryIndex >= 0 ? trimmed.slice(queryIndex + 1) : trimmed;
    const params = new URLSearchParams(query.startsWith('&') ? query.slice(1) : query);
    const code = params.get('code');
    const state = params.get('state');

    if (code) {
      if (expectedState && state && state !== expectedState) {
        throw new Error('The pasted callback parameters state does not match the generated OAuth state.');
      }

      return code;
    }
  }

  return trimmed;
}

async function resolveAuthorizationCode(
  options: InitFlowOptions & {
    endpoints: JohnDeereOAuthEndpoints;
    authorization: AuthorizationContext;
    authorizationUrl: string;
  }
): Promise<AuthorizationCodeResolution> {
  if (options.authorizationCode?.trim()) {
    return {
      code: parseManualAuthorizationInput(options.authorizationCode, options.authorization.state),
      source: 'cli-arg'
    };
  }

  const stdin = options.stdin ?? process.stdin;

  if (!('isTTY' in stdin) || !stdin.isTTY) {
    const rawInput = await readAuthorizationCodeFromStream(stdin);
    return {
      code: parseManualAuthorizationInput(rawInput, options.authorization.state),
      source: 'stdin'
    };
  }

  let callbackListener: CallbackListener | undefined;

  try {
    callbackListener = await startLocalCallbackListener({
      redirectUri: options.config.redirectUri,
      expectedState: options.authorization.state,
      callbackTimeoutMs: options.callbackTimeoutMs,
      createServerImpl: options.createServer
    });
  } catch {
    callbackListener = undefined;
  }

  const manualAbortController = new AbortController();

  const manualInputPromise = readInteractiveAuthorizationCode({
    stdin,
    stdout: options.stdout ?? process.stdout,
    signal: manualAbortController.signal,
    prompt: callbackListener
      ? [
          `Open this URL in your browser: ${options.authorizationUrl}`,
          `Waiting for callback on ${callbackListener.listenerUrl}.`,
          'If the browser cannot reach localhost, paste the full callback URL or the authorization code and press Enter: '
        ].join('\n')
      : [
          `Open this URL in your browser: ${options.authorizationUrl}`,
          'Local callback server unavailable; paste the full callback URL or the authorization code and press Enter: '
        ].join('\n')
  })
    .then((value) => ({
      code: parseManualAuthorizationInput(value, options.authorization.state),
      source: 'stdin' as const
    }))
    .catch((error) => {
      if (isAbortError(error)) {
        return new Promise<AuthorizationCodeResolution>(() => undefined);
      }

      throw error;
    });

  if (!callbackListener) {
    return manualInputPromise;
  }

  try {
    const result = await Promise.race([
      callbackListener.waitForCode().then((code) => ({ code, source: 'local-callback' as const })),
      manualInputPromise
    ]);

    manualAbortController.abort();
    return result;
  } finally {
    manualAbortController.abort();
    await callbackListener.close();
  }
}

async function exchangeAuthorizationCode(options: {
  config: CliConfig;
  endpoints: JohnDeereOAuthEndpoints;
  fetchImpl: typeof fetch;
  authorizationCode: string;
  codeVerifier: string;
}): Promise<OAuthTokenPayload> {
  const response = await options.fetchImpl(options.endpoints.tokenEndpoint, {
    method: 'POST',
    headers: {
      accept: 'application/json',
      'content-type': 'application/x-www-form-urlencoded'
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code: options.authorizationCode,
      redirect_uri: options.config.redirectUri,
      client_id: options.config.clientId ?? '',
      client_secret: options.config.clientSecret ?? '',
      code_verifier: options.codeVerifier
    })
  });

  if (!response.ok) {
    throw new Error(`John Deere token exchange failed with HTTP ${response.status}.`);
  }

  const tokenPayload = assertOAuthTokenPayload((await response.json()) as unknown);

  if (!tokenPayload.refresh_token) {
    throw new Error('John Deere token exchange did not return a refresh token. Ensure offline_access is granted.');
  }

  return tokenPayload;
}

async function exchangeRefreshToken(options: {
  config: CliConfig;
  endpoints: JohnDeereOAuthEndpoints;
  fetchImpl: typeof fetch;
  refreshToken: string;
}): Promise<OAuthTokenPayload> {
  const response = await options.fetchImpl(options.endpoints.tokenEndpoint, {
    method: 'POST',
    headers: {
      accept: 'application/json',
      'content-type': 'application/x-www-form-urlencoded'
    },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: options.refreshToken,
      client_id: options.config.clientId ?? '',
      client_secret: options.config.clientSecret ?? ''
    })
  });

  if (!response.ok) {
    throw new Error(`John Deere refresh token exchange failed with HTTP ${response.status}.`);
  }

  return assertOAuthTokenPayload((await response.json()) as unknown);
}

async function detectOrganizationConnections(options: {
  endpoints: JohnDeereOAuthEndpoints;
  accessToken: string;
  fetchImpl: typeof fetch;
}): Promise<OrgConnectionStatus> {
  try {
    const response = await options.fetchImpl(`${options.endpoints.apiBaseUrl}/organizations`, {
      headers: {
        accept: 'application/vnd.deere.axiom.v3+json, application/json',
        authorization: `Bearer ${options.accessToken}`
      }
    });

    if (!response.ok) {
      return {
        checked: false,
        required: false,
        organizationCount: 0,
        organizationNamesRequiringConnection: [],
        message: `skipped - organizations query returned HTTP ${response.status}`
      };
    }

    const payload = (await response.json()) as unknown;
    const organizations = extractOrganizations(payload);
    const organizationNamesRequiringConnection = organizations
      .filter((organization) => hasConnectionsLink(organization))
      .map((organization) => organization.name);

    if (organizationNamesRequiringConnection.length > 0) {
      return {
        checked: true,
        required: true,
        organizationCount: organizations.length,
        organizationNamesRequiringConnection,
        message: `required - complete an Operations Center org connection for ${organizationNamesRequiringConnection.join(', ')}`
      };
    }

    return {
      checked: true,
      required: false,
      organizationCount: organizations.length,
      organizationNamesRequiringConnection: [],
      message: `ok - no org connection links detected across ${organizations.length} organizations`
    };
  } catch (error) {
    return {
      checked: false,
      required: false,
      organizationCount: 0,
      organizationNamesRequiringConnection: [],
      message: `skipped - failed to inspect organizations (${error instanceof Error ? error.message : 'unknown error'})`
    };
  }
}

function assertOAuthTokenPayload(value: unknown): OAuthTokenPayload {
  if (!value || typeof value !== 'object') {
    throw new TypeError('OAuth token response must be an object.');
  }

  const candidate = value as Record<string, unknown>;

  return {
    access_token: readRequiredString(candidate.access_token, 'access_token'),
    refresh_token: readOptionalString(candidate.refresh_token, 'refresh_token'),
    expires_in: readRequiredNumber(candidate.expires_in, 'expires_in'),
    token_type: readRequiredString(candidate.token_type, 'token_type'),
    scope: readOptionalString(candidate.scope, 'scope')
  };
}

function createStoredToken(options: {
  tokenResponse: OAuthTokenPayload;
  fallbackScope: string;
  now: Date;
}): StoredToken {
  return {
    accessToken: options.tokenResponse.access_token,
    refreshToken: options.tokenResponse.refresh_token ?? '',
    expiresAt: createExpiryIsoString(options.tokenResponse.expires_in, options.now),
    tokenType: options.tokenResponse.token_type,
    scope: normalizeScope(options.tokenResponse.scope, options.fallbackScope)
  };
}

function createExpiryIsoString(expiresInSeconds: number, now: Date): string {
  return new Date(now.getTime() + expiresInSeconds * 1000).toISOString();
}

function normalizeScope(scope: string | undefined, fallbackScope: string): string {
  return scope?.trim() ? scope : fallbackScope;
}

function buildTokenStoreKey(config: CliConfig): { grower: string; profile: string } {
  return {
    grower: config.grower,
    profile: config.profile
  };
}

function extractOrganizations(payload: unknown): Array<{ name: string; raw: Record<string, unknown> }> {
  if (Array.isArray(payload)) {
    return payload.flatMap((value) => normalizeOrganization(value));
  }

  if (!payload || typeof payload !== 'object') {
    return [];
  }

  const candidate = payload as Record<string, unknown>;
  const collections = [candidate.values, candidate.organizations];

  for (const collection of collections) {
    if (Array.isArray(collection)) {
      return collection.flatMap((value) => normalizeOrganization(value));
    }
  }

  return [];
}

function normalizeOrganization(value: unknown): Array<{ name: string; raw: Record<string, unknown> }> {
  if (!value || typeof value !== 'object') {
    return [];
  }

  const raw = value as Record<string, unknown>;
  return [
    {
      name:
        readFirstString(raw.name, raw.displayName, raw.id, raw.orgId, raw.identifier) ??
        'unknown-organization',
      raw
    }
  ];
}

function hasConnectionsLink(organization: { raw: Record<string, unknown> }): boolean {
  const linksCandidate = organization.raw.links ?? organization.raw._links;

  if (!linksCandidate) {
    return false;
  }

  if (Array.isArray(linksCandidate)) {
    return linksCandidate.some((entry) => {
      if (!entry || typeof entry !== 'object') {
        return false;
      }

      const link = entry as Record<string, unknown>;
      return readFirstString(link.rel, link.name) === 'connections';
    });
  }

  if (typeof linksCandidate !== 'object') {
    return false;
  }

  const links = linksCandidate as Record<string, unknown>;
  if ('connections' in links) {
    return true;
  }

  return Object.values(links).some((entry) => {
    if (!entry || typeof entry !== 'object') {
      return false;
    }

    const link = entry as Record<string, unknown>;
    return readFirstString(link.rel, link.name) === 'connections';
  });
}

async function handleCallbackRequest(options: {
  request: IncomingMessage;
  response: ServerResponse<IncomingMessage>;
  callbackPath: string;
  expectedState: string;
  onSuccess: (code: string) => void;
  onError: (error: unknown) => void;
}): Promise<void> {
  const requestUrl = new URL(options.request.url ?? '/', 'http://localhost');

  if (requestUrl.pathname !== options.callbackPath) {
    options.response.statusCode = 404;
    options.response.end('Not found');
    return;
  }

  const error = requestUrl.searchParams.get('error');
  if (error) {
    options.response.statusCode = 400;
    options.response.end('John Deere authorization failed. You can close this window and retry.');
    options.onError(new Error(`John Deere authorization failed: ${error}`));
    return;
  }

  const state = requestUrl.searchParams.get('state');
  if (state !== options.expectedState) {
    options.response.statusCode = 400;
    options.response.end('OAuth state mismatch. Close this window and retry from the CLI.');
    options.onError(new Error('OAuth state mismatch on localhost callback.'));
    return;
  }

  const code = requestUrl.searchParams.get('code');
  if (!code) {
    options.response.statusCode = 400;
    options.response.end('Authorization code missing from callback.');
    options.onError(new Error('Authorization code missing from localhost callback.'));
    return;
  }

  options.response.statusCode = 200;
  options.response.setHeader('content-type', 'text/plain; charset=utf-8');
  options.response.end('John Deere authorization received. Return to the CLI.');
  options.onSuccess(code);
}

async function readInteractiveAuthorizationCode(options: {
  stdin: NodeJS.ReadableStream;
  stdout: NodeJS.WritableStream;
  prompt: string;
  signal: AbortSignal;
}): Promise<string> {
  const rl = readline.createInterface({
    input: options.stdin,
    output: options.stdout
  });

  try {
    while (true) {
      const answer = await rl.question(options.prompt, { signal: options.signal });
      if (answer.trim()) {
        return answer;
      }
    }
  } finally {
    rl.close();
  }
}

async function readAuthorizationCodeFromStream(stream: NodeJS.ReadableStream): Promise<string> {
  const chunks: string[] = [];

  for await (const chunk of stream) {
    chunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'));
  }

  const value = chunks.join('').trim();
  if (!value) {
    throw new Error('No authorization code was provided on stdin.');
  }

  return value;
}

async function closeServer(server: Server): Promise<void> {
  if (!server.listening) {
    return;
  }

  await new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
      } else {
        resolve();
      }
    });
  });
}

function toBase64Url(value: Buffer): string {
  return value
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function readRequiredString(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`OAuth field \`${fieldName}\` must be a non-empty string.`);
  }

  return value;
}

function readOptionalString(value: unknown, fieldName: string): string | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined;
  }

  if (typeof value !== 'string') {
    throw new TypeError(`OAuth field \`${fieldName}\` must be a string when present.`);
  }

  return value;
}

function readRequiredNumber(value: unknown, fieldName: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new TypeError(`OAuth field \`${fieldName}\` must be a positive number.`);
  }

  return value;
}

function readFirstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }

  return undefined;
}

function isAbortError(error: unknown): error is Error & { code?: string } {
  return (
    error instanceof Error &&
    (error.name === 'AbortError' || ('code' in error && typeof error.code === 'string' && error.code === 'ABORT_ERR'))
  );
}
