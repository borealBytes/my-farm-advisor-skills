import path from 'node:path';

import { buildTokenFilePath } from './tokens/file-store.js';
import { resolveDataRoot } from './paths.js';
import type { JohnDeereOAuthEnvironment } from './oauth/endpoints.js';

export const DEFAULT_JD_REDIRECT_URI = 'http://localhost:9090/callback';
export const DEFAULT_JD_ENVIRONMENT: JohnDeereOAuthEnvironment = 'sandboxapi';

export interface CliConfig {
  dataRoot: string;
  grower: string;
  profile: string;
  environment: JohnDeereOAuthEnvironment;
  redirectUri: string;
  clientId?: string;
  clientSecret?: string;
  dryRun: boolean;
  mock: boolean;
  orgId?: string;
  since?: string;
  hateoas: boolean;
  force: boolean;
  configDir: string;
  configFile: string;
  tokenStorePath: string;
}

export interface ParseConfigOverrides {
  dataRoot?: string;
  grower?: string;
  profile?: string;
  redirectUri?: string;
  clientId?: string;
  clientSecret?: string;
  environment?: JohnDeereOAuthEnvironment;
  dryRun?: boolean;
  mock?: boolean;
  orgId?: string;
  since?: string;
  hateoas?: boolean;
  force?: boolean;
}

export interface ParseConfigOptions {
  env?: NodeJS.ProcessEnv;
  cwd?: string;
  overrides?: ParseConfigOverrides;
  pathExists?: (candidatePath: string) => boolean;
}

function trimOptional(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function parseConfig(options: ParseConfigOptions = {}): CliConfig {
  const env = options.env ?? process.env;
  const cwd = options.cwd ?? process.cwd();
  const overrides = options.overrides ?? {};
  const overrideDataRoot = trimOptional(overrides.dataRoot);
  const effectiveEnv = {
    ...env,
    ...(overrideDataRoot ? { JD_DATA_ROOT: overrideDataRoot } : {})
  };
  const dataRoot = resolveDataRoot({
    env: effectiveEnv,
    moduleDir: path.join(cwd, 'src'),
    pathExists: options.pathExists
  });
  const grower = trimOptional(overrides.grower) ?? trimOptional(env.JD_GROWER) ?? 'todo-grower';
  const profile = trimOptional(overrides.profile) ?? trimOptional(env.JD_PROFILE) ?? 'default';
  const configDir = path.join(dataRoot, '.john-deere');

  return {
    dataRoot,
    grower,
    profile,
    environment:
      overrides.environment ??
      (trimOptional(env.JD_ENVIRONMENT) as JohnDeereOAuthEnvironment | undefined) ??
      DEFAULT_JD_ENVIRONMENT,
    redirectUri: trimOptional(overrides.redirectUri) ?? trimOptional(env.JD_REDIRECT_URI) ?? DEFAULT_JD_REDIRECT_URI,
    clientId: trimOptional(overrides.clientId) ?? trimOptional(env.JD_CLIENT_ID),
    clientSecret: trimOptional(overrides.clientSecret) ?? trimOptional(env.JD_CLIENT_SECRET),
    dryRun: overrides.dryRun ?? false,
    mock: overrides.mock ?? false,
    orgId: trimOptional(overrides.orgId) ?? trimOptional(env.JD_ORG_ID),
    since: trimOptional(overrides.since) ?? trimOptional(env.JD_SINCE),
    hateoas: overrides.hateoas ?? trimOptional(env.JD_HATEOAS) === 'true',
    force: overrides.force ?? false,
    configDir,
    configFile: path.join(configDir, 'config.json'),
    tokenStorePath: buildTokenFilePath({ dataRoot, grower, profile })
  };
}
