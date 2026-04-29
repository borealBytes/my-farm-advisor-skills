import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

export {
  OPERATION_REGISTRY_STATUSES,
  READ_SCOPES,
  REQUIRED_API_GROUPS,
  WRITE_SCOPES,
  operationRegistry
} from './operations.js';
export type {
  OperationRegistryAuthMode,
  OperationRegistryEntityScope,
  OperationRegistryEntry,
  OperationRegistryStatus
} from './operations.js';

import { operationRegistry } from './operations.js';
import type { OperationRegistryEntry } from './operations.js';

export function serializeOperationRegistry(registry: readonly OperationRegistryEntry[] = operationRegistry): string {
  return JSON.stringify(registry, null, 2) + '\n';
}

export async function writeOperationRegistryJson(
  filePath: string,
  registry: readonly OperationRegistryEntry[] = operationRegistry
): Promise<string> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, serializeOperationRegistry(registry), 'utf8');
  return filePath;
}
