import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { operationRegistry, type OperationRegistryEntry } from '../../src/registry/index.js';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const fixturesDir = path.resolve(currentDir, '../fixtures');

export async function readJsonFixture<T>(fileName: string): Promise<T> {
  return JSON.parse(await readFile(path.join(fixturesDir, fileName), 'utf8')) as T;
}

export async function readJsonFile<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, 'utf8')) as T;
}

export async function readJsonLines<T>(filePath: string): Promise<T[]> {
  const raw = await readFile(filePath, 'utf8');
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as T);
}

export function selectRegistryEntries(keys: string[]): OperationRegistryEntry[] {
  const registryMap = new Map(operationRegistry.map((entry) => [`${entry.apiGroup}.${entry.operation}`, entry]));

  return keys.map((key) => {
    const entry = registryMap.get(key);
    if (!entry) {
      throw new Error(`Missing registry entry for ${key}`);
    }

    return entry;
  });
}
