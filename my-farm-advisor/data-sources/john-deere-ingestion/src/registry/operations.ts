import path from 'node:path';

import {
  buildFarmPaths,
  buildFieldPaths,
  buildGrowerPaths,
  buildMachineDataPaths,
  buildRawPayloadRelativePath,
  formatJohnDeereTimestampPrefix,
  slugifyDeereName
} from '../paths.js';

export const OPERATION_REGISTRY_STATUSES = [
  'pending',
  'accessible',
  'unauthorized',
  'unsupported_by_sdk',
  'unsupported_environment',
  'empty',
  'error',
  'disabled_by_default',
  'skipped_by_checkpoint'
] as const;

export type OperationRegistryStatus = (typeof OPERATION_REGISTRY_STATUSES)[number];

export type OperationRegistryAuthMode = 'oauth' | 'client_credentials' | 'oauth_or_client_app' | 'special';

export type OperationRegistryEntityScope =
  | 'grower'
  | 'user'
  | 'client'
  | 'farm'
  | 'field'
  | 'farm_or_field'
  | 'grower_or_farm_or_field'
  | 'equipment'
  | 'grower_or_equipment'
  | 'asset'
  | 'operator'
  | 'machine'
  | 'partnership'
  | 'connection'
  | 'webhook';

export interface OperationRegistryEntry {
  apiGroup: string;
  operation: string;
  sdkPath: string;
  authMode: OperationRegistryAuthMode;
  requiredScopes: string[];
  entityScope: OperationRegistryEntityScope;
  defaultEnabled: boolean;
  destructive: boolean;
  rawDestinationTemplate: string;
  normalizedDestinationTemplate: string;
  status: OperationRegistryStatus;
}

interface SupportedGroupDefinition {
  apiGroup: string;
  rawGroupSlug: string;
  authMode: OperationRegistryAuthMode;
  entityScope: OperationRegistryEntityScope;
  normalizedDestinationTemplate: string;
  operations: readonly string[];
  readScopes?: readonly string[];
  writeScopes?: readonly string[];
}

interface UnsupportedEntryDefinition {
  apiGroup: string;
  operation: string;
  sdkPath: string;
  authMode: OperationRegistryAuthMode;
  requiredScopes: readonly string[];
  entityScope: OperationRegistryEntityScope;
  defaultEnabled: boolean;
  destructive: boolean;
  rawGroupSlug: string;
  normalizedDestinationTemplate: string;
}

export const REQUIRED_API_GROUPS = [
  'organizations',
  'users',
  'clients',
  'farms',
  'fields',
  'boundaries',
  'fieldOperations',
  'guidanceLines',
  'flags',
  'mapLayers',
  'cropTypes',
  'products',
  'equipment',
  'equipmentMeasurement',
  'assets',
  'operators',
  'partnerships',
  'connectionManagement',
  'webhook',
  'notifications',
  'files',
  'machineLocations',
  'machineAlerts',
  'machineEngineHours',
  'machineHoursOfOperation',
  'machineDeviceStateReports',
  'harvestId',
  'aemp',
  'workPlans'
] as const;

export const READ_SCOPES = ['ag1'] as const;
export const WRITE_SCOPES = ['ag2'] as const;

const TEMPLATE_DATA_ROOT = '{dataRoot}';
const TEMPLATE_GROWER_SLUG = '{grower_slug}';
const TEMPLATE_FARM_SLUG = '{farm_slug}';
const TEMPLATE_FIELD_SLUG = '{field_slug}';
const TEMPLATE_MACHINE_ID = '{machine_id}';
const TEMPLATE_YEAR_VALUE = 2099;
const RAW_TEMPLATE_DATE = new Date('2099-01-02T03:04:05.000Z');
const RAW_TEMPLATE_TIMESTAMP = formatJohnDeereTimestampPrefix(RAW_TEMPLATE_DATE);
const RAW_TEMPLATE_ID = 'template-id-or-page';
const TEMPLATE_GROWER_ROOT = path.join(TEMPLATE_DATA_ROOT, 'growers', TEMPLATE_GROWER_SLUG);

const growerTemplatePaths = buildGrowerPaths({
  dataRoot: TEMPLATE_DATA_ROOT,
  growerSlug: TEMPLATE_GROWER_SLUG
});
const farmTemplatePaths = buildFarmPaths({
  dataRoot: TEMPLATE_DATA_ROOT,
  growerSlug: TEMPLATE_GROWER_SLUG,
  farmSlug: TEMPLATE_FARM_SLUG
});
const fieldTemplatePaths = buildFieldPaths({
  dataRoot: TEMPLATE_DATA_ROOT,
  growerSlug: TEMPLATE_GROWER_SLUG,
  farmSlug: TEMPLATE_FARM_SLUG,
  fieldSlug: TEMPLATE_FIELD_SLUG,
  year: TEMPLATE_YEAR_VALUE
});
const machineTemplatePaths = buildMachineDataPaths({
  dataRoot: TEMPLATE_DATA_ROOT,
  growerSlug: TEMPLATE_GROWER_SLUG,
  machineId: TEMPLATE_MACHINE_ID,
  year: TEMPLATE_YEAR_VALUE
});

function toTemplatePath(absolutePath: string): string {
  return path
    .relative(TEMPLATE_GROWER_ROOT, absolutePath)
    .split(path.sep)
    .join('/')
    .replaceAll(String(TEMPLATE_YEAR_VALUE), '{yyyy}');
}

function appendTemplate(basePath: string, leafPath: string): string {
  return `${basePath}/${leafPath}`;
}

function buildRawTemplate(rawGroupSlug: string, operation: string): string {
  return buildRawPayloadRelativePath({
    apiGroup: rawGroupSlug,
    operation,
    fetchedAt: RAW_TEMPLATE_DATE,
    idOrPage: RAW_TEMPLATE_ID
  })
    .replace(`/${RAW_TEMPLATE_DATE.getUTCFullYear()}/01/02/`, '/{yyyy}/{mm}/{dd}/')
    .replace(RAW_TEMPLATE_TIMESTAMP, '{timestamp}')
    .replace(slugifyDeereName(RAW_TEMPLATE_ID), '{id-or-page}');
}

function isWriteOperation(operation: string): boolean {
  return ['create', 'update', 'delete', 'patch'].some((prefix) => operation.startsWith(prefix));
}

function buildSupportedEntries(definition: SupportedGroupDefinition): OperationRegistryEntry[] {
  return definition.operations.map((operation) => {
    const destructive = isWriteOperation(operation);

    return {
      apiGroup: definition.apiGroup,
      operation,
      sdkPath: `deere.${definition.apiGroup}.${operation}`,
      authMode: definition.authMode,
      requiredScopes: destructive
        ? [...(definition.writeScopes ?? WRITE_SCOPES)]
        : [...(definition.readScopes ?? READ_SCOPES)],
      entityScope: definition.entityScope,
      defaultEnabled: !destructive,
      destructive,
      rawDestinationTemplate: buildRawTemplate(definition.rawGroupSlug, operation),
      normalizedDestinationTemplate: definition.normalizedDestinationTemplate,
      status: destructive ? 'disabled_by_default' : 'pending'
    };
  });
}

function buildUnsupportedEntry(definition: UnsupportedEntryDefinition): OperationRegistryEntry {
  return {
    apiGroup: definition.apiGroup,
    operation: definition.operation,
    sdkPath: definition.sdkPath,
    authMode: definition.authMode,
    requiredScopes: [...definition.requiredScopes],
    entityScope: definition.entityScope,
    defaultEnabled: definition.defaultEnabled,
    destructive: definition.destructive,
    rawDestinationTemplate: buildRawTemplate(definition.rawGroupSlug, definition.operation),
    normalizedDestinationTemplate: definition.normalizedDestinationTemplate,
    status: 'unsupported_by_sdk'
  };
}

const supportedGroupDefinitions: readonly SupportedGroupDefinition[] = [
  {
    apiGroup: 'organizations',
    rawGroupSlug: 'organizations',
    authMode: 'oauth',
    entityScope: 'grower',
    normalizedDestinationTemplate: `${toTemplatePath(growerTemplatePaths.growerFile)} | ${appendTemplate(toTemplatePath(growerTemplatePaths.connectionsDir), 'organizations.john-deere.json')}`,
    operations: ['list', 'listAll', 'get', 'listOrganizations', 'listUsers']
  },
  {
    apiGroup: 'users',
    rawGroupSlug: 'users',
    authMode: 'oauth',
    entityScope: 'user',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.usersDir), 'current-user.john-deere.json'),
    operations: ['get']
  },
  {
    apiGroup: 'clients',
    rawGroupSlug: 'clients',
    authMode: 'oauth',
    entityScope: 'client',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(growerTemplatePaths.clientsDir), '{client_slug}.john-deere.json')} | ${appendTemplate(toTemplatePath(farmTemplatePaths.farmDir), 'clients.john-deere.json')}`,
    operations: ['list', 'listAll', 'create', 'get', 'update', 'delete', 'listFarms', 'listFields']
  },
  {
    apiGroup: 'farms',
    rawGroupSlug: 'farms',
    authMode: 'oauth',
    entityScope: 'farm',
    normalizedDestinationTemplate: `${toTemplatePath(farmTemplatePaths.farmFile)} | ${appendTemplate(toTemplatePath(farmTemplatePaths.fieldsDir), '{field_slug}/field.john-deere.json')}`,
    operations: ['list', 'listAll', 'create', 'get', 'update', 'delete', 'listClients', 'listFields']
  },
  {
    apiGroup: 'fields',
    rawGroupSlug: 'fields',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: `${toTemplatePath(fieldTemplatePaths.fieldFile)} | ${appendTemplate(toTemplatePath(farmTemplatePaths.farmDir), 'fields.john-deere.json')}`,
    operations: ['list', 'listAll', 'create', 'get', 'update', 'delete', 'listFarms', 'listClients']
  },
  {
    apiGroup: 'boundaries',
    rawGroupSlug: 'boundaries',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(farmTemplatePaths.boundariesDir), '{boundary_id}.john-deere.json')} | ${toTemplatePath(fieldTemplatePaths.fieldBoundaryFile)}`,
    operations: ['list', 'listAll', 'listBoundaries', 'create', 'get', 'getBoundaries', 'update', 'delete']
  },
  {
    apiGroup: 'fieldOperations',
    rawGroupSlug: 'field-operations',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: [
      appendTemplate(toTemplatePath(fieldTemplatePaths.plantingYearDir), '{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.harvestYearDir), '{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.sprayingDir), '{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.fertilizerDir), '{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.otherApplicationsDir), '{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.operationsYearDir), '{operation}.john-deere.json')
    ].join(' | '),
    operations: ['list', 'listAll', 'get', 'getFieldops']
  },
  {
    apiGroup: 'guidanceLines',
    rawGroupSlug: 'guidance-lines',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(fieldTemplatePaths.guidanceLinesDir), '{guidance_line_id}.john-deere.json')} | ${appendTemplate(toTemplatePath(farmTemplatePaths.mapLayersDir), 'guidance-lines-{guidance_line_id}.john-deere.json')}`,
    operations: ['list', 'listAll', 'create', 'get', 'update']
  },
  {
    apiGroup: 'flags',
    rawGroupSlug: 'flags',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(fieldTemplatePaths.flagsDir), '{flag_id}.john-deere.json'),
    operations: ['get', 'update', 'delete', 'getFlags', 'create', 'list', 'listAll']
  },
  {
    apiGroup: 'mapLayers',
    rawGroupSlug: 'map-layers',
    authMode: 'oauth',
    entityScope: 'farm_or_field',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(farmTemplatePaths.mapLayersDir), '{map_layer_id}.john-deere.json')} | ${appendTemplate(toTemplatePath(fieldTemplatePaths.mapLayersDir), '{map_layer_id}.john-deere.json')}`,
    operations: ['list', 'listAll', 'create', 'get', 'delete']
  },
  {
    apiGroup: 'cropTypes',
    rawGroupSlug: 'crop-types',
    authMode: 'oauth',
    entityScope: 'grower',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(growerTemplatePaths.cropTypesDir), '{crop_type_id}.john-deere.json')} | ../../shared/john-deere/reference/crop-types.json`,
    operations: ['list', 'listAll', 'get', 'getCroptypes', 'listCroptypes']
  },
  {
    apiGroup: 'products',
    rawGroupSlug: 'products',
    authMode: 'oauth',
    entityScope: 'grower',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.productsDir), '{category}/{product_id}.john-deere.json'),
    operations: [
      'list',
      'listAll',
      'create',
      'get',
      'update',
      'createAssociatetoorg',
      'listVarieties',
      'getVarieties',
      'listDocuments',
      'patch'
    ]
  },
  {
    apiGroup: 'equipment',
    rawGroupSlug: 'equipment',
    authMode: 'oauth',
    entityScope: 'equipment',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(growerTemplatePaths.equipmentDir), '{equipment_id}.john-deere.json')} | ${appendTemplate(toTemplatePath(growerTemplatePaths.equipmentDir), 'reference/{operation}.john-deere.json')}`,
    operations: [
      'get',
      'create',
      'getEquipment',
      'update',
      'delete',
      'list',
      'listAll',
      'getEquipmentmakes',
      'getEquipmenttypes',
      'listEquipmenttypes',
      'listEquipmentmodels',
      'listEquipmentisgtypes',
      'getEquipmentisgtypes',
      'getEquipmentisgtypes2',
      'getEquipmentmodels',
      'getEquipmentmodels2'
    ]
  },
  {
    apiGroup: 'equipmentMeasurement',
    rawGroupSlug: 'equipment-measurement',
    authMode: 'oauth',
    entityScope: 'equipment',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.equipmentDir), '{equipment_id}/measurements/{timestamp}.john-deere.json'),
    operations: ['create']
  },
  {
    apiGroup: 'assets',
    rawGroupSlug: 'assets',
    authMode: 'oauth',
    entityScope: 'asset',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.assetsDir), '{asset_id}.john-deere.json'),
    operations: ['list', 'listAll', 'create', 'get', 'update', 'delete', 'listLocations', 'createLocations', 'getAssetcatalog']
  },
  {
    apiGroup: 'operators',
    rawGroupSlug: 'operators',
    authMode: 'oauth',
    entityScope: 'operator',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.operatorsDir), '{operator_slug}.john-deere.json'),
    operations: ['list', 'listAll', 'create', 'delete', 'get', 'update', 'deleteOperators']
  },
  {
    apiGroup: 'partnerships',
    rawGroupSlug: 'partnerships',
    authMode: 'oauth',
    entityScope: 'partnership',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.partnershipsDir), '{partnership_id}.john-deere.json'),
    operations: ['list', 'listAll', 'create', 'get', 'delete', 'listPermissions', 'createPermissions']
  },
  {
    apiGroup: 'connectionManagement',
    rawGroupSlug: 'connection-management',
    authMode: 'client_credentials',
    entityScope: 'connection',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.connectionsDir), 'management/{connection_id}.john-deere.json'),
    readScopes: [],
    writeScopes: [],
    operations: ['list', 'listAll', 'delete', 'deleteConnections']
  },
  {
    apiGroup: 'webhook',
    rawGroupSlug: 'webhook',
    authMode: 'oauth_or_client_app',
    entityScope: 'webhook',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(growerTemplatePaths.webhooksDir), 'subscriptions.john-deere.json')} | ${toTemplatePath(growerTemplatePaths.rawWebhooksEventsFile)}`,
    operations: ['list', 'listAll', 'create', 'get', 'update']
  },
  {
    apiGroup: 'notifications',
    rawGroupSlug: 'notifications',
    authMode: 'oauth',
    entityScope: 'grower',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(growerTemplatePaths.notificationsDir), '{yyyy}/{notification_id}.john-deere.json'),
    operations: ['get', 'create', 'delete', 'list', 'listAll']
  },
  {
    apiGroup: 'files',
    rawGroupSlug: 'files',
    authMode: 'oauth',
    entityScope: 'grower_or_farm_or_field',
    normalizedDestinationTemplate: [
      appendTemplate(toTemplatePath(growerTemplatePaths.filesDir), '{file_id}.john-deere.json'),
      appendTemplate(toTemplatePath(farmTemplatePaths.farmDir), 'files/john-deere/{file_id}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.filesDir), '{file_id}.john-deere.json')
    ].join(' | '),
    operations: ['list', 'listAll', 'get', 'update', 'listFiles', 'create']
  },
  {
    apiGroup: 'machineLocations',
    rawGroupSlug: 'machine-locations',
    authMode: 'oauth',
    entityScope: 'machine',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(machineTemplatePaths.locationsYearDir), '{timestamp}.john-deere.json')} | ${appendTemplate(toTemplatePath(fieldTemplatePaths.machineLocationsYearDir), '{timestamp}.john-deere.json')}`,
    operations: ['get']
  },
  {
    apiGroup: 'machineAlerts',
    rawGroupSlug: 'machine-alerts',
    authMode: 'oauth',
    entityScope: 'machine',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(machineTemplatePaths.alertsYearDir), '{timestamp}.john-deere.json')} | ${appendTemplate(toTemplatePath(fieldTemplatePaths.alertsYearDir), '{timestamp}.john-deere.json')}`,
    operations: ['list', 'listAll']
  },
  {
    apiGroup: 'machineEngineHours',
    rawGroupSlug: 'machine-engine-hours',
    authMode: 'oauth',
    entityScope: 'machine',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(machineTemplatePaths.engineHoursDir), '{timestamp}.john-deere.json'),
    operations: ['list', 'listAll']
  },
  {
    apiGroup: 'machineHoursOfOperation',
    rawGroupSlug: 'machine-hours-of-operation',
    authMode: 'oauth',
    entityScope: 'machine',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(machineTemplatePaths.hoursOfOperationYearDir), '{timestamp}.john-deere.json'),
    operations: ['list', 'listAll']
  },
  {
    apiGroup: 'machineDeviceStateReports',
    rawGroupSlug: 'machine-device-state-reports',
    authMode: 'oauth',
    entityScope: 'machine',
    normalizedDestinationTemplate: appendTemplate(toTemplatePath(machineTemplatePaths.deviceStateReportsYearDir), '{timestamp}.john-deere.json'),
    operations: ['get']
  },
  {
    apiGroup: 'harvestId',
    rawGroupSlug: 'harvest-id',
    authMode: 'oauth',
    entityScope: 'field',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(fieldTemplatePaths.harvestYearDir), 'cotton/{serial_number}.john-deere.json')} | ${appendTemplate(toTemplatePath(growerTemplatePaths.assetsDir), 'harvest-id-cotton/{serial_number}.john-deere.json')}`,
    operations: ['list', 'listAll', 'get']
  },
  {
    apiGroup: 'aemp',
    rawGroupSlug: 'aemp',
    authMode: 'special',
    entityScope: 'grower_or_equipment',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(growerTemplatePaths.aempDir), '{page_or_id}.john-deere.json')} | ${appendTemplate(toTemplatePath(growerTemplatePaths.equipmentDir), '{equipment_id}/aemp/{timestamp}.john-deere.json')}`,
    readScopes: [],
    writeScopes: [],
    operations: ['get']
  }
] as const;

const unsupportedEntries: readonly UnsupportedEntryDefinition[] = [
  {
    apiGroup: 'fieldOperations',
    operation: 'listAllWithMeasurements',
    sdkPath: 'deere.safe.fieldOperations.listAllWithMeasurements',
    authMode: 'oauth',
    requiredScopes: READ_SCOPES,
    entityScope: 'field',
    defaultEnabled: true,
    destructive: false,
    rawGroupSlug: 'field-operations',
    normalizedDestinationTemplate: [
      appendTemplate(toTemplatePath(fieldTemplatePaths.plantingYearDir), 'measurements/{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.harvestYearDir), 'measurements/{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.sprayingDir), 'measurements/{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.fertilizerDir), 'measurements/{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.otherApplicationsDir), 'measurements/{operation}.john-deere.json'),
      appendTemplate(toTemplatePath(fieldTemplatePaths.operationsYearDir), 'measurements/{operation}.john-deere.json')
    ].join(' | ')
  },
  {
    apiGroup: 'workPlans',
    operation: 'list',
    sdkPath: 'deere.workPlans.list',
    authMode: 'oauth',
    requiredScopes: READ_SCOPES,
    entityScope: 'farm_or_field',
    defaultEnabled: true,
    destructive: false,
    rawGroupSlug: 'work-plans',
    normalizedDestinationTemplate: `${appendTemplate(toTemplatePath(farmTemplatePaths.workPlansDir), '{work_plan_id}.john-deere.json')} | ${appendTemplate(toTemplatePath(fieldTemplatePaths.operationsYearDir), 'work-plans/{work_plan_id}.john-deere.json')}`
  }
] as const;

export const operationRegistry: OperationRegistryEntry[] = [
  ...supportedGroupDefinitions.flatMap((definition) => buildSupportedEntries(definition)),
  ...unsupportedEntries.map((definition) => buildUnsupportedEntry(definition))
];
