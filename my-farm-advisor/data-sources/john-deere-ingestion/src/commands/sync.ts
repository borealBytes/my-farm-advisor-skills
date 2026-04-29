import type { CliConfig } from '../config.js';
import { FileCheckpointStore } from '../storage/checkpoint.js';

import {
  runOrchestratedCommand,
  type CommandExecutionDependencies,
  type CommandExecutionResult
} from './ingest.js';

export async function runSyncCommand(
  config: CliConfig,
  dependencies: CommandExecutionDependencies = {}
): Promise<CommandExecutionResult> {
  const checkpointStore = new FileCheckpointStore({
    dataRoot: config.dataRoot,
    growerSlug: config.grower
  });
  const checkpoint = await checkpointStore.load();
  const effectiveSince = config.force ? undefined : config.since ?? checkpoint.lastSuccessfulRun ?? undefined;

  return runOrchestratedCommand({
    mode: 'sync',
    config,
    effectiveSince,
    dependencies
  });
}
