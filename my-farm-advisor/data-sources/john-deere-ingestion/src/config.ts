export interface CliConfig {
  dataRoot: string;
  grower: string;
  profile: string;
}

export interface ParseConfigOptions {
  env?: NodeJS.ProcessEnv;
  cwd?: string;
}

import { resolveDataRoot } from './paths.js';

export function parseConfig(options: ParseConfigOptions = {}): CliConfig {
  const env = options.env ?? process.env;
  const cwd = options.cwd ?? process.cwd();

  return {
    dataRoot: resolveDataRoot({ env, moduleDir: cwd }),
    grower: env.JD_GROWER ?? 'todo-grower',
    profile: env.JD_PROFILE ?? 'default'
  };
}
