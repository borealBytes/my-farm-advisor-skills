#!/usr/bin/env node

import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Command } from 'commander';

import { initJohnDeereAuth } from './auth/init.js';
import { parseConfig } from './config.js';
import { resolveOAuthEndpoints } from './oauth/endpoints.js';
import { buildGrowerPaths } from './paths.js';
import type { TokenStore } from './tokens/store.js';

export interface RunCliResult {
  output: string;
  exitCode: number;
  config?: ReturnType<typeof parseConfig>;
}

export interface RunCliOptions {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  executableName?: string;
  fetch?: typeof fetch;
  tokenStore?: TokenStore;
  stdin?: NodeJS.ReadableStream;
  stdout?: NodeJS.WritableStream;
  callbackTimeoutMs?: number;
}

interface CliGlobalOptions {
  dryRun?: boolean;
  mock?: boolean;
  environment?: 'sandboxapi' | 'sandbox' | 'production';
  dataRoot?: string;
  grower?: string;
  profile?: string;
  redirectUri?: string;
  clientId?: string;
  clientSecret?: string;
  orgId?: string;
  since?: string;
  hateoas?: boolean;
  force?: boolean;
}

interface RegistryOptions extends CliGlobalOptions {
  output?: string;
}

interface InitCommandOptions extends CliGlobalOptions {
  code?: string;
}

interface WebhookOptions extends CliGlobalOptions {
  port?: number;
}

function addSharedCommandOptions(command: Command): Command {
  return command
    .option('--dry-run', 'Print intended actions without writing data or tokens')
    .option('--mock', 'Use mock mode instead of live John Deere API calls')
    .option('--environment <environment>', 'Target John Deere environment (sandboxapi, sandbox, production)')
    .option('--data-root <path>', 'Override the resolved John Deere data root')
    .option('--org-id <id>', 'Target John Deere organization id')
    .option('--since <timestamp>', 'Incremental sync lower bound timestamp')
    .option('--hateoas', 'Enable HATEOAS-ready API traversal mode');
}

function createBaseProgram(capturedOutput: string[], executableName: string): Command {
  const program = new Command();

  program
    .name(executableName)
    .description('John Deere ingestion CLI. Aliases: jd, john-deere, john-deer.')
    .showHelpAfterError()
    .option('--dry-run', 'Print intended actions without writing data or tokens')
    .option('--mock', 'Use mock mode instead of live John Deere API calls')
    .option('--environment <environment>', 'Target John Deere environment (sandboxapi, sandbox, production)')
    .option('--data-root <path>', 'Override the resolved John Deere data root')
    .option('--grower <slug>', 'Override the grower slug used for paths and token storage')
    .option('--profile <name>', 'Override the John Deere profile name')
    .option('--redirect-uri <uri>', 'Override the OAuth redirect URI')
    .option('--client-id <id>', 'Override the John Deere OAuth client id')
    .option('--client-secret <secret>', 'Override the John Deere OAuth client secret')
    .option('--org-id <id>', 'Target John Deere organization id')
    .option('--since <timestamp>', 'Incremental sync lower bound timestamp')
    .option('--hateoas', 'Enable HATEOAS-ready API traversal mode')
    .addHelpText(
      'after',
      '\nAliases:\n  jd\n  john-deere\n  john-deer\n'
    )
    .configureOutput({
      writeOut: (text) => capturedOutput.push(text),
      writeErr: (text) => capturedOutput.push(text)
    });

  return program;
}

function buildCommandConfig(command: Command, options: RunCliOptions): ReturnType<typeof parseConfig> {
  const cliOptions = command.optsWithGlobals<CliGlobalOptions>();

  return parseConfig({
    cwd: options.cwd,
    env: options.env,
    overrides: {
      dataRoot: cliOptions.dataRoot,
      grower: cliOptions.grower,
      profile: cliOptions.profile,
      redirectUri: cliOptions.redirectUri,
      clientId: cliOptions.clientId,
      clientSecret: cliOptions.clientSecret,
      environment: cliOptions.environment,
      dryRun: cliOptions.dryRun,
      mock: cliOptions.mock,
      orgId: cliOptions.orgId,
      since: cliOptions.since,
      hateoas: cliOptions.hateoas,
      force: cliOptions.force
    }
  });
}

function missingCredentials(config: ReturnType<typeof parseConfig>): string[] {
  const missing: string[] = [];

  if (!config.clientId) {
    missing.push('JD_CLIENT_ID');
  }

  if (!config.clientSecret) {
    missing.push('JD_CLIENT_SECRET');
  }

  return missing;
}

function formatMissingCredentials(commandName: string, config: ReturnType<typeof parseConfig>): RunCliResult {
  const missing = missingCredentials(config);
  return {
    output: [
      `Cannot run '${commandName}' because required credentials are missing.`,
      `Missing: ${missing.join(', ')}`,
      'Set the missing environment variables and try again. No stack trace emitted.'
    ].join('\n'),
    exitCode: 1,
    config
  };
}

function buildRegistryManifest(config: ReturnType<typeof parseConfig>) {
  return {
    generatedAt: new Date().toISOString(),
    environment: config.environment,
    hateoas: config.hateoas,
    orgId: config.orgId ?? null,
    mock: config.mock,
    operations: [
      {
        apiGroup: 'organizations',
        operation: 'listOrganizations',
        sdkPath: 'deere.organizations.list',
        status: 'pending'
      },
      {
        apiGroup: 'farms',
        operation: 'listFarms',
        sdkPath: 'deere.farms.list',
        status: config.mock ? 'accessible' : 'pending'
      },
      {
        apiGroup: 'fields',
        operation: 'listFields',
        sdkPath: 'deere.fields.list',
        status: config.mock ? 'accessible' : 'pending'
      }
    ]
  };
}

async function handlePaths(command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);
  const growerPaths = buildGrowerPaths({ dataRoot: config.dataRoot, growerSlug: config.grower });

  return {
    output: [
      'Resolved John Deere paths',
      `dataRoot: ${config.dataRoot}`,
      `configDir: ${config.configDir}`,
      `configFile: ${config.configFile}`,
      `tokenStorePath: ${config.tokenStorePath}`,
      `growerDir: ${growerPaths.growerDir}`,
      `rawRootDir: ${growerPaths.rawRootDir}`,
      `manifestsDir: ${growerPaths.manifestsDir}`,
      `logsFile: ${growerPaths.logsFile}`,
      `dryRun: ${String(config.dryRun)}`
    ].join('\n'),
    exitCode: 0,
    config
  };
}

async function handleInit(command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);
  const initOptions = command.optsWithGlobals<InitCommandOptions>();

  if (missingCredentials(config).length > 0) {
    return formatMissingCredentials('init', config);
  }

  const result = await initJohnDeereAuth({
    config,
    fetch: options.fetch,
    tokenStore: options.tokenStore,
    stdin: options.stdin,
    stdout: options.stdout,
    authorizationCode: initOptions.code,
    callbackTimeoutMs: options.callbackTimeoutMs
  });

  return {
    output: result.outputLines.join('\n'),
    exitCode: 0,
    config
  };
}

async function handleIngestLike(commandName: 'ingest' | 'sync', command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);

  if (!config.mock && missingCredentials(config).length > 0) {
    return formatMissingCredentials(commandName, config);
  }

  return {
    output: [
      `John Deere ${commandName} scaffold`,
      `environment: ${config.environment}`,
      `dataRoot: ${config.dataRoot}`,
      `orgId: ${config.orgId ?? 'not-set'}`,
      `since: ${config.since ?? 'not-set'}`,
      `mock: ${String(config.mock)}`,
      `force: ${String(config.force)}`,
      `hateoas: ${String(config.hateoas)}`,
      config.dryRun
        ? 'dry-run: no manifests, tokens, or export files written.'
        : 'stub: command routing is wired; data export implementation lands in a later task.'
    ].join('\n'),
    exitCode: 0,
    config
  };
}

async function handleRegistry(command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);
  const registryOptions = command.optsWithGlobals<RegistryOptions>();
  const manifest = buildRegistryManifest(config);
  const manifestJson = JSON.stringify(manifest, null, 2);

  if (registryOptions.output && !config.dryRun) {
    await mkdir(path.dirname(registryOptions.output), { recursive: true });
    await writeFile(registryOptions.output, `${manifestJson}\n`, 'utf8');
  }

  return {
    output: registryOptions.output
      ? [
          `Registry manifest ${config.dryRun ? 'would be written' : 'written'} to ${registryOptions.output}`,
          manifestJson
        ].join('\n')
      : manifestJson,
    exitCode: 0,
    config
  };
}

async function handleWebhook(command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);
  const webhookOptions = command.optsWithGlobals<WebhookOptions>();
  const port = webhookOptions.port ?? 9090;

  return {
    output: [
      'John Deere webhook scaffold',
      `port: ${port}`,
      `eventsFile: ${buildGrowerPaths({ dataRoot: config.dataRoot, growerSlug: config.grower }).rawWebhooksEventsFile}`,
      config.dryRun ? 'dry-run: listener not started.' : 'listener startup stubbed; routing is wired.'
    ].join('\n'),
    exitCode: 0,
    config
  };
}

async function handleDoctor(command: Command, options: RunCliOptions): Promise<RunCliResult> {
  const config = buildCommandConfig(command, options);
  const missing = missingCredentials(config);

  let endpointStatus = 'unreachable';
  let authorizationEndpoint = 'unavailable';

  try {
    const endpoints = await resolveOAuthEndpoints({ environment: config.environment, fetch: options.fetch });
    endpointStatus = `ok (${endpoints.source})`;
    authorizationEndpoint = endpoints.authorizationEndpoint;
  } catch (error) {
    endpointStatus = `error (${error instanceof Error ? error.message : 'unknown error'})`;
  }

  return {
    output: [
      'John Deere doctor',
      `environment: ${config.environment}`,
      `dataRoot: ${config.dataRoot}`,
      `credentials: ${missing.length === 0 ? 'configured' : `missing ${missing.join(', ')}`}`,
      `tokenStore: ${existsSync(config.tokenStorePath) ? 'present' : 'missing'} (${config.tokenStorePath})`,
      `endpointReachability: ${endpointStatus}`,
      `authorizationEndpoint: ${authorizationEndpoint}`
    ].join('\n'),
    exitCode: missing.length === 0 ? 0 : 1,
    config
  };
}

export async function runCli(argv: string[], options: RunCliOptions = {}): Promise<RunCliResult> {
  const capturedOutput: string[] = [];
  const executableName = options.executableName ?? 'jd';
  const program = createBaseProgram(capturedOutput, executableName);
  let commandResult: RunCliResult | undefined;

  addSharedCommandOptions(
    program
      .command('init')
    .description('Initialize OAuth flow and print or exchange the authorization code')
    .option('--code <authorizationCode>', 'Paste the callback URL or authorization code instead of using localhost callback')
    .action(async function initAction() {
      commandResult = await handleInit(this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('ingest')
    .description('Run full John Deere export routing')
    .option('--force', 'Bypass incremental safeguards for a full refresh')
    .action(async function ingestAction() {
      commandResult = await handleIngestLike('ingest', this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('sync')
    .description('Run incremental John Deere export routing')
    .option('--force', 'Force a sync even when checkpoints suggest no changes')
    .action(async function syncAction() {
      commandResult = await handleIngestLike('sync', this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('registry')
    .description('Print or write the John Deere registry manifest scaffold')
    .option('--output <path>', 'Write registry JSON to the provided path')
    .action(async function registryAction() {
      commandResult = await handleRegistry(this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('webhook')
    .description('Start or describe the local John Deere webhook receiver')
    .option('--port <port>', 'Port for the local webhook receiver', (value) => Number.parseInt(value, 10), 9090)
    .action(async function webhookAction() {
      commandResult = await handleWebhook(this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('doctor')
    .description('Check configuration, credentials, token store, and endpoint resolution')
    .action(async function doctorAction() {
      commandResult = await handleDoctor(this as Command, options);
    })
  );

  addSharedCommandOptions(
    program
      .command('paths')
    .description('Print resolved John Deere data, config, and token paths')
    .action(async function pathsAction() {
      commandResult = await handlePaths(this as Command, options);
    })
  );

  program.exitOverride();

  try {
    await program.parseAsync(argv, { from: 'user' });
  } catch (error) {
    const message = capturedOutput.join('').trimEnd();

    return {
      output: message || (error instanceof Error ? error.message : 'CLI parsing failed.'),
      exitCode:
        typeof error === 'object' && error !== null && 'exitCode' in error && typeof error.exitCode === 'number'
          ? error.exitCode
          : 1
    };
  }

  if (commandResult) {
    return commandResult;
  }

  const output = capturedOutput.join('').trimEnd() || program.helpInformation().trimEnd();

  return {
    output,
    exitCode: 0
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const result = await runCli(process.argv.slice(2), {
    cwd: process.cwd(),
    env: process.env,
    executableName: 'jd'
  });
  if (result.output) {
    process.stdout.write(`${result.output}\n`);
  }
  process.exitCode = result.exitCode;
}
