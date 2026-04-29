#!/usr/bin/env node

import { Command } from 'commander';
import { parseConfig } from './config.js';

export interface RunCliResult {
  output: string;
  exitCode: number;
  config?: ReturnType<typeof parseConfig>;
}

export async function runCli(argv: string[]): Promise<RunCliResult> {
  const program = new Command();

  program
    .name('jd')
    .description('John Deere ingestion CLI scaffold')
    .option('--config', 'Print parsed configuration');

  program.exitOverride();

  try {
    program.parse(argv, { from: 'user' });
  } catch {
    return {
      output: 'TODO: CLI help output not implemented yet',
      exitCode: 1
    };
  }

  if (program.opts<{ config?: boolean }>().config) {
    return {
      output: 'TODO: config command output not implemented yet',
      exitCode: 0,
      config: parseConfig()
    };
  }

  return {
    output: 'TODO: CLI command handling not implemented yet',
    exitCode: 0
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const result = await runCli(process.argv.slice(2));
  if (result.output) {
    process.stdout.write(`${result.output}\n`);
  }
  process.exitCode = result.exitCode;
}
