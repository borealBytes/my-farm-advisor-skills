import { access, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { buildRawPayloadPath, buildRawPayloadRelativePath, type RawPayloadPathOptions } from '../paths.js';

export interface WriteRawPayloadOptions extends RawPayloadPathOptions {
  payload: unknown;
}

export interface RawPayloadWriteResult {
  path: string;
  relativePath: string;
}

function serializePayload(payload: unknown): string {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

function addImmutableSuffix(filePath: string, sequence: number): string {
  const extension = path.extname(filePath);
  const basename = extension ? filePath.slice(0, -extension.length) : filePath;
  return `${basename}_${String(sequence).padStart(3, '0')}${extension}`;
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function ensureImmutablePath(filePath: string): Promise<string> {
  if (!(await pathExists(filePath))) {
    return filePath;
  }

  let sequence = 1;
  while (true) {
    const candidate = addImmutableSuffix(filePath, sequence);
    if (!(await pathExists(candidate))) {
      return candidate;
    }
    sequence += 1;
  }
}

export class RawPayloadWriter {
  async write(options: WriteRawPayloadOptions): Promise<RawPayloadWriteResult> {
    const basePath = buildRawPayloadPath(options);
    const outputPath = await ensureImmutablePath(basePath);

    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, serializePayload(options.payload), 'utf-8');

    return {
      path: outputPath,
      relativePath: path.join(
        'growers',
        options.growerSlug,
        buildRawPayloadRelativePath(options).replace(path.basename(basePath), path.basename(outputPath))
      )
    };
  }
}
