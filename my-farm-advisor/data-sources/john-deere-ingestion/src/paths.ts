import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const JD_WORKSPACE_DATA_ROOT = '/data/workspace/data/my-farm-advisor';

export interface ResolveDataRootOptions {
  env?: NodeJS.ProcessEnv;
  moduleDir?: string;
  pathExists?: (candidatePath: string) => boolean;
}

export interface DeereSlugOptions {
  displayName: string;
  deereId: string;
  existingSlugs?: Iterable<string>;
}

export interface RawPayloadPathOptions {
  dataRoot: string;
  growerSlug: string;
  apiGroup: string;
  operation: string;
  fetchedAt: Date;
  idOrPage: string;
}

export interface GrowerPathOptions {
  dataRoot: string;
  growerSlug: string;
}

export interface FarmPathOptions extends GrowerPathOptions {
  farmSlug: string;
}

export interface FieldPathOptions extends FarmPathOptions {
  fieldSlug: string;
  year: number;
}

export interface MachineYearPathOptions extends GrowerPathOptions {
  machineId: string;
  year: number;
}

export interface NormalizedTreeOptions extends FieldPathOptions {}

export interface GrowerPaths {
  growerDir: string;
  growerFile: string;
  sourceDir: string;
  rawRootDir: string;
  rawManifestsDir: string;
  rawWebhooksDir: string;
  rawWebhooksEventsFile: string;
  manifestsDir: string;
  logsDir: string;
  logsFile: string;
  equipmentDir: string;
  operatorsDir: string;
  usersDir: string;
  clientsDir: string;
  partnershipsDir: string;
  connectionsDir: string;
  productsDir: string;
  cropTypesDir: string;
  assetsDir: string;
  notificationsDir: string;
  filesDir: string;
  webhooksDir: string;
  machineDataDir: string;
  machineLocationsRootDir: string;
  machineAlertsRootDir: string;
  machineEngineHoursRootDir: string;
  machineHoursOfOperationRootDir: string;
  machineDeviceStateReportsRootDir: string;
  aempDir: string;
  farmsDir: string;
}

export interface FarmPaths {
  farmDir: string;
  farmFile: string;
  boundaryDir: string;
  fieldBoundariesFile: string;
  boundariesDir: string;
  mapLayersDir: string;
  workPlansDir: string;
  manifestsDir: string;
  logsDir: string;
  fieldsDir: string;
}

export interface FieldPaths {
  fieldDir: string;
  fieldFile: string;
  boundaryDir: string;
  fieldBoundaryFile: string;
  plantingYearDir: string;
  harvestYearDir: string;
  applicationsYearDir: string;
  sprayingDir: string;
  fertilizerDir: string;
  otherApplicationsDir: string;
  operationsYearDir: string;
  guidanceLinesDir: string;
  flagsDir: string;
  mapLayersDir: string;
  filesDir: string;
  machineLocationsYearDir: string;
  alertsYearDir: string;
  manifestsDir: string;
  derivedDir: string;
  logsDir: string;
}

export interface MachineDataPaths {
  locationsYearDir: string;
  alertsYearDir: string;
  engineHoursDir: string;
  hoursOfOperationYearDir: string;
  deviceStateReportsYearDir: string;
}

export interface NormalizedTreePaths {
  grower: GrowerPaths;
  farm: FarmPaths;
  field: FieldPaths;
}

const CURRENT_MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));

export function resolveDataRoot(options: ResolveDataRootOptions = {}): string {
  const env = options.env ?? process.env;
  const pathExists = options.pathExists ?? existsSync;
  const explicitRoot = env.JD_DATA_ROOT?.trim();

  if (explicitRoot) {
    return path.resolve(explicitRoot);
  }

  if (pathExists(JD_WORKSPACE_DATA_ROOT)) {
    return JD_WORKSPACE_DATA_ROOT;
  }

  const moduleDir = options.moduleDir ?? CURRENT_MODULE_DIR;
  return path.resolve(moduleDir, '../../../..', '.runtime', 'my-farm-advisor', 'data');
}

export function slugifyDeereName(value: string): string {
  const asciiValue = value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

  const slug = asciiValue
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');

  return slug || 'item';
}

export function createDeereSlug(options: DeereSlugOptions): string {
  const baseSlug = slugifyDeereName(options.displayName || options.deereId);
  const existingSlugs = new Set(options.existingSlugs ?? []);

  if (!existingSlugs.has(baseSlug)) {
    return baseSlug;
  }

  const idSuffix = slugifyDeereName(options.deereId);
  return `${baseSlug}-${idSuffix}`;
}

export function toDeerePathSegment(value: string): string {
  return slugifyDeereName(value);
}

export function formatJohnDeereTimestampPrefix(value: Date): string {
  const isoString = value.toISOString();
  return isoString.slice(0, 19).replace(/:/g, '-') + 'Z';
}

function formatDateParts(value: Date): { year: string; month: string; day: string } {
  return {
    year: String(value.getUTCFullYear()),
    month: String(value.getUTCMonth() + 1).padStart(2, '0'),
    day: String(value.getUTCDate()).padStart(2, '0')
  };
}

function joinPath(...segments: string[]): string {
  return path.join(...segments);
}

export function buildRawPayloadRelativePath(options: Omit<RawPayloadPathOptions, 'dataRoot' | 'growerSlug'>): string {
  const apiGroup = toDeerePathSegment(options.apiGroup);
  const operation = toDeerePathSegment(options.operation);
  const idOrPage = toDeerePathSegment(options.idOrPage);
  const { year, month, day } = formatDateParts(options.fetchedAt);
  const timestamp = formatJohnDeereTimestampPrefix(options.fetchedAt);

  return joinPath(
    'source',
    'john-deere',
    'raw',
    apiGroup,
    operation,
    year,
    month,
    day,
    `${timestamp}_${operation}_${idOrPage}.json`
  );
}

export function buildRawPayloadPath(options: RawPayloadPathOptions): string {
  return joinPath(
    options.dataRoot,
    'growers',
    options.growerSlug,
    buildRawPayloadRelativePath(options)
  );
}

export function buildGrowerPaths(options: GrowerPathOptions): GrowerPaths {
  const growerDir = joinPath(options.dataRoot, 'growers', options.growerSlug);
  const sourceDir = joinPath(growerDir, 'source', 'john-deere');
  const machineDataDir = joinPath(growerDir, 'machine-data');

  return {
    growerDir,
    growerFile: joinPath(growerDir, 'grower.john-deere.json'),
    sourceDir,
    rawRootDir: joinPath(sourceDir, 'raw'),
    rawManifestsDir: joinPath(sourceDir, 'manifests'),
    rawWebhooksDir: joinPath(sourceDir, 'webhooks'),
    rawWebhooksEventsFile: joinPath(sourceDir, 'webhooks', 'events.jsonl'),
    manifestsDir: joinPath(growerDir, 'manifests', 'john-deere'),
    logsDir: joinPath(growerDir, 'logs'),
    logsFile: joinPath(growerDir, 'logs', 'john-deere-ingest.jsonl'),
    equipmentDir: joinPath(growerDir, 'equipment', 'john-deere'),
    operatorsDir: joinPath(growerDir, 'operators', 'john-deere'),
    usersDir: joinPath(growerDir, 'users', 'john-deere'),
    clientsDir: joinPath(growerDir, 'clients', 'john-deere'),
    partnershipsDir: joinPath(growerDir, 'partnerships', 'john-deere'),
    connectionsDir: joinPath(growerDir, 'connections', 'john-deere'),
    productsDir: joinPath(growerDir, 'products', 'john-deere'),
    cropTypesDir: joinPath(growerDir, 'crop-types', 'john-deere'),
    assetsDir: joinPath(growerDir, 'assets', 'john-deere'),
    notificationsDir: joinPath(growerDir, 'notifications', 'john-deere'),
    filesDir: joinPath(growerDir, 'files', 'john-deere'),
    webhooksDir: joinPath(growerDir, 'webhooks', 'john-deere'),
    machineDataDir,
    machineLocationsRootDir: joinPath(machineDataDir, 'locations'),
    machineAlertsRootDir: joinPath(machineDataDir, 'alerts'),
    machineEngineHoursRootDir: joinPath(machineDataDir, 'engine-hours'),
    machineHoursOfOperationRootDir: joinPath(machineDataDir, 'hours-of-operation'),
    machineDeviceStateReportsRootDir: joinPath(machineDataDir, 'device-state-reports'),
    aempDir: joinPath(growerDir, 'aemp', 'john-deere'),
    farmsDir: joinPath(growerDir, 'farms')
  };
}

export function buildFarmPaths(options: FarmPathOptions): FarmPaths {
  const farmDir = joinPath(options.dataRoot, 'growers', options.growerSlug, 'farms', options.farmSlug);

  return {
    farmDir,
    farmFile: joinPath(farmDir, 'farm.john-deere.json'),
    boundaryDir: joinPath(farmDir, 'boundary'),
    fieldBoundariesFile: joinPath(farmDir, 'boundary', 'field_boundaries.john-deere.geojson'),
    boundariesDir: joinPath(farmDir, 'boundaries', 'john-deere'),
    mapLayersDir: joinPath(farmDir, 'map-layers', 'john-deere'),
    workPlansDir: joinPath(farmDir, 'work-plans', 'john-deere'),
    manifestsDir: joinPath(farmDir, 'manifests', 'john-deere'),
    logsDir: joinPath(farmDir, 'logs'),
    fieldsDir: joinPath(farmDir, 'fields')
  };
}

export function buildFieldPaths(options: FieldPathOptions): FieldPaths {
  const yearSegment = String(options.year);
  const fieldDir = joinPath(
    options.dataRoot,
    'growers',
    options.growerSlug,
    'farms',
    options.farmSlug,
    'fields',
    options.fieldSlug
  );

  return {
    fieldDir,
    fieldFile: joinPath(fieldDir, 'field.john-deere.json'),
    boundaryDir: joinPath(fieldDir, 'boundary'),
    fieldBoundaryFile: joinPath(fieldDir, 'boundary', 'field_boundary.john-deere.geojson'),
    plantingYearDir: joinPath(fieldDir, 'planting', 'john-deere', yearSegment),
    harvestYearDir: joinPath(fieldDir, 'harvest', 'john-deere', yearSegment),
    applicationsYearDir: joinPath(fieldDir, 'applications', 'john-deere', yearSegment),
    sprayingDir: joinPath(fieldDir, 'applications', 'john-deere', yearSegment, 'spraying'),
    fertilizerDir: joinPath(fieldDir, 'applications', 'john-deere', yearSegment, 'fertilizer'),
    otherApplicationsDir: joinPath(fieldDir, 'applications', 'john-deere', yearSegment, 'other'),
    operationsYearDir: joinPath(fieldDir, 'operations', 'john-deere', yearSegment),
    guidanceLinesDir: joinPath(fieldDir, 'guidance-lines', 'john-deere'),
    flagsDir: joinPath(fieldDir, 'flags', 'john-deere'),
    mapLayersDir: joinPath(fieldDir, 'map-layers', 'john-deere'),
    filesDir: joinPath(fieldDir, 'files', 'john-deere'),
    machineLocationsYearDir: joinPath(fieldDir, 'machine-locations', 'john-deere', yearSegment),
    alertsYearDir: joinPath(fieldDir, 'alerts', 'john-deere', yearSegment),
    manifestsDir: joinPath(fieldDir, 'manifests', 'john-deere'),
    derivedDir: joinPath(fieldDir, 'derived'),
    logsDir: joinPath(fieldDir, 'logs')
  };
}

export function buildMachineDataPaths(options: MachineYearPathOptions): MachineDataPaths {
  const yearSegment = String(options.year);
  const root = buildGrowerPaths(options);

  return {
    locationsYearDir: joinPath(root.machineLocationsRootDir, options.machineId, 'john-deere', yearSegment),
    alertsYearDir: joinPath(root.machineAlertsRootDir, options.machineId, 'john-deere', yearSegment),
    engineHoursDir: joinPath(root.machineEngineHoursRootDir, options.machineId, 'john-deere'),
    hoursOfOperationYearDir: joinPath(
      root.machineHoursOfOperationRootDir,
      options.machineId,
      'john-deere',
      yearSegment
    ),
    deviceStateReportsYearDir: joinPath(
      root.machineDeviceStateReportsRootDir,
      options.machineId,
      'john-deere',
      yearSegment
    )
  };
}

function uniqueDirectories(pathsToCreate: Iterable<string>): string[] {
  return [...new Set(pathsToCreate)];
}

export function buildNormalizedTreePaths(options: NormalizedTreeOptions): NormalizedTreePaths {
  return {
    grower: buildGrowerPaths(options),
    farm: buildFarmPaths(options),
    field: buildFieldPaths(options)
  };
}

export async function createMockNormalizedTree(options: NormalizedTreeOptions): Promise<NormalizedTreePaths> {
  const tree = buildNormalizedTreePaths(options);
  const directories = uniqueDirectories([
    tree.grower.growerDir,
    tree.grower.sourceDir,
    tree.grower.rawRootDir,
    tree.grower.rawManifestsDir,
    tree.grower.rawWebhooksDir,
    tree.grower.manifestsDir,
    tree.grower.logsDir,
    tree.grower.equipmentDir,
    tree.grower.operatorsDir,
    tree.grower.usersDir,
    tree.grower.clientsDir,
    tree.grower.partnershipsDir,
    tree.grower.connectionsDir,
    tree.grower.productsDir,
    tree.grower.cropTypesDir,
    tree.grower.assetsDir,
    tree.grower.notificationsDir,
    tree.grower.filesDir,
    tree.grower.webhooksDir,
    tree.grower.machineDataDir,
    tree.grower.machineLocationsRootDir,
    tree.grower.machineAlertsRootDir,
    tree.grower.machineEngineHoursRootDir,
    tree.grower.machineHoursOfOperationRootDir,
    tree.grower.machineDeviceStateReportsRootDir,
    tree.grower.aempDir,
    tree.grower.farmsDir,
    tree.farm.farmDir,
    tree.farm.boundaryDir,
    tree.farm.boundariesDir,
    tree.farm.mapLayersDir,
    tree.farm.workPlansDir,
    tree.farm.manifestsDir,
    tree.farm.logsDir,
    tree.farm.fieldsDir,
    tree.field.fieldDir,
    tree.field.boundaryDir,
    tree.field.plantingYearDir,
    tree.field.harvestYearDir,
    tree.field.applicationsYearDir,
    tree.field.sprayingDir,
    tree.field.fertilizerDir,
    tree.field.otherApplicationsDir,
    tree.field.operationsYearDir,
    tree.field.guidanceLinesDir,
    tree.field.flagsDir,
    tree.field.mapLayersDir,
    tree.field.filesDir,
    tree.field.machineLocationsYearDir,
    tree.field.alertsYearDir,
    tree.field.manifestsDir,
    tree.field.derivedDir,
    tree.field.logsDir
  ]);

  await Promise.all(directories.map(async (directoryPath) => mkdir(directoryPath, { recursive: true })));
  return tree;
}
