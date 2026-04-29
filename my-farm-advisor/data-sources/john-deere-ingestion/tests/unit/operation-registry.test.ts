import { mkdtemp, readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { operationRegistry, REQUIRED_API_GROUPS, writeOperationRegistryJson } from '../../src/registry/index.js';

interface SdkOperation {
  apiGroup: string;
  operation: string;
}

const SDK_DEERE_DECLARATION = path.resolve('node_modules/deere-sdk/dist/deere.d.ts');

function readSourceFile(filePath: string): ts.SourceFile {
  const sourceText = ts.sys.readFile(filePath);

  if (!sourceText) {
    throw new Error(`Unable to read TypeScript declaration: ${filePath}`);
  }

  return ts.createSourceFile(filePath, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
}

function extractSdkOperations(): SdkOperation[] {
  const deereSource = readSourceFile(SDK_DEERE_DECLARATION);
  const classToApiFile = new Map<string, string>();
  const apiGroupToClassName = new Map<string, string>();

  for (const statement of deereSource.statements) {
    if (ts.isImportDeclaration(statement) && statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings)) {
      const moduleSpecifier = statement.moduleSpecifier.getText(deereSource).slice(1, -1);

      for (const element of statement.importClause.namedBindings.elements) {
        classToApiFile.set(element.name.text, moduleSpecifier);
      }
    }

    if (ts.isClassDeclaration(statement) && statement.name?.text === 'Deere') {
      for (const member of statement.members) {
        if (
          ts.isPropertyDeclaration(member) &&
          member.name &&
          ts.isIdentifier(member.name) &&
          member.type &&
          ts.isTypeReferenceNode(member.type) &&
          ts.isIdentifier(member.type.typeName)
        ) {
          apiGroupToClassName.set(member.name.text, member.type.typeName.text);
        }
      }
    }
  }

  return [...apiGroupToClassName.entries()].flatMap(([apiGroup, className]) => {
    const relativeModulePath = classToApiFile.get(className);

    if (!relativeModulePath) {
      throw new Error(`Missing import for Deere API class ${className}`);
    }

    if (!relativeModulePath.startsWith('./api/')) {
      return [];
    }

    const apiDeclarationPath = path.resolve(path.dirname(SDK_DEERE_DECLARATION), `${relativeModulePath.replace(/\.js$/, '.d.ts')}`);
    const apiSource = readSourceFile(apiDeclarationPath);

    for (const statement of apiSource.statements) {
      if (ts.isClassDeclaration(statement) && statement.name?.text === className) {
        return statement.members.flatMap((member) => {
          if (!ts.isMethodDeclaration(member) || !member.name || !ts.isIdentifier(member.name)) {
            return [];
          }

          return [{ apiGroup, operation: member.name.text }];
        });
      }
    }

    throw new Error(`Unable to find class ${className} in ${apiDeclarationPath}`);
  });
}

function toOperationKey({ apiGroup, operation }: SdkOperation): string {
  return `${apiGroup}.${operation}`;
}

function isWriteOperation(operation: string): boolean {
  return ['create', 'update', 'delete', 'patch'].some((prefix) => operation.startsWith(prefix));
}

describe('operation registry', () => {
  it('covers every Deere SDK API operation plus required unsupported entries', () => {
    const sdkOperations = extractSdkOperations();
    const registryKeys = new Set(operationRegistry.map(toOperationKey));
    const sdkKeys = sdkOperations.map(toOperationKey);

    for (const sdkKey of sdkKeys) {
      expect(registryKeys.has(sdkKey), `missing registry entry for ${sdkKey}`).toBe(true);
    }

    expect(registryKeys.has('fieldOperations.listAllWithMeasurements')).toBe(true);
    expect(registryKeys.has('workPlans.list')).toBe(true);
    expect(operationRegistry).toHaveLength(sdkOperations.length + 2);
  });

  it('includes every required API group and records unsupported plan-only APIs', () => {
    const registryGroups = new Set(operationRegistry.map((entry) => entry.apiGroup));

    for (const apiGroup of REQUIRED_API_GROUPS) {
      expect(registryGroups.has(apiGroup), `missing required api group ${apiGroup}`).toBe(true);
    }

    expect(operationRegistry).toContainEqual(
      expect.objectContaining({
        apiGroup: 'workPlans',
        operation: 'list',
        sdkPath: 'deere.workPlans.list',
        status: 'unsupported_by_sdk'
      })
    );

    expect(operationRegistry).toContainEqual(
      expect.objectContaining({
        apiGroup: 'fieldOperations',
        operation: 'listAllWithMeasurements',
        sdkPath: 'deere.safe.fieldOperations.listAllWithMeasurements',
        status: 'unsupported_by_sdk'
      })
    );
  });

  it('defaults read operations on and keeps mutating operations disabled by default', () => {
    for (const entry of operationRegistry) {
      const writeOperation = isWriteOperation(entry.operation);

      if (writeOperation) {
        expect(entry.defaultEnabled, `${entry.apiGroup}.${entry.operation} should be disabled by default`).toBe(false);
        expect(entry.destructive, `${entry.apiGroup}.${entry.operation} should be marked destructive`).toBe(true);
        expect(entry.status, `${entry.apiGroup}.${entry.operation} should default to disabled_by_default`).toBe('disabled_by_default');
      } else {
        expect(entry.defaultEnabled, `${entry.apiGroup}.${entry.operation} should be enabled by default`).toBe(true);
        expect(entry.destructive, `${entry.apiGroup}.${entry.operation} should not be marked destructive`).toBe(false);
      }
    }
  });

  it('writes the registry to JSON through the registry index helper', async () => {
    const tempDir = await mkdtemp(path.join(tmpdir(), 'jd-registry-'));

    try {
      const outputPath = path.join(tempDir, 'manifests', 'operation-registry.json');
      const writtenPath = await writeOperationRegistryJson(outputPath);

      expect(writtenPath).toBe(outputPath);

      const json = await readFile(outputPath, 'utf8');
      expect(JSON.parse(json)).toEqual(operationRegistry);
      expect(json.endsWith('\n')).toBe(true);
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });
});
