import path from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'

import {
  buildFieldPaths,
  buildFarmPaths,
  buildGrowerPaths,
  createDeereSlug,
  formatJohnDeereTimestampPrefix,
  slugifyDeereName
} from '../paths.js'

type DeereEntity = Record<string, unknown>

const DEFAULT_NAME_CANDIDATES = ['displayName', 'name', 'title', 'label']
const DEFAULT_UPDATED_AT_CANDIDATES = [
  'updatedAt',
  'updatedTime',
  'lastModifiedTime',
  'lastModifiedDate',
  'modifiedAt',
  'modifiedTime'
]
const FARM_ID_CANDIDATES = ['id', 'deereId', 'farmId']
const FIELD_ID_CANDIDATES = ['id', 'deereId', 'fieldId']
const BOUNDARY_ID_CANDIDATES = ['id', 'deereId', 'boundaryId']
const EQUIPMENT_ID_CANDIDATES = ['id', 'deereId', 'equipmentId', 'assetId']
const OPERATOR_ID_CANDIDATES = ['id', 'deereId', 'operatorId', 'userId']
const PRODUCT_ID_CANDIDATES = ['id', 'deereId', 'productId']
const CROP_TYPE_ID_CANDIDATES = ['id', 'deereId', 'cropTypeId']
const OPERATION_ID_CANDIDATES = ['id', 'deereId', 'fieldOperationId', 'operationId']
const RELATION_FARM_ID_CANDIDATES = ['farmId', 'farm.id', 'farm.deereId', 'relationships.farm.id']
const RELATION_FARM_NAME_CANDIDATES = ['farmName', 'farm.name', 'farm.displayName', 'relationships.farm.name']
const RELATION_FIELD_ID_CANDIDATES = ['fieldId', 'field.id', 'field.deereId', 'relationships.field.id']
const RELATION_FIELD_NAME_CANDIDATES = ['fieldName', 'field.name', 'field.displayName', 'relationships.field.name']

export interface DeereMappingContext {
  dataRoot: string
  growerSlug: string
  sourceApi: string
  sourceOperation: string
  fetchedAt: Date | string
}

export interface DeereRelationReference {
  deereId?: string
  displayName?: string
  slug?: string
}

export interface NormalizedFile<TContent = unknown> {
  path: string
  format: 'json' | 'geojson'
  content: TContent
}

export interface MappedOrganizationResult {
  file: NormalizedFile<Record<string, unknown>>
}

export interface MappedFarmResult {
  farmSlug: string
  file: NormalizedFile<Record<string, unknown>>
}

export interface MappedFieldResult {
  farmSlug: string
  fieldSlug: string
  file: NormalizedFile<Record<string, unknown>>
}

export interface MappedBoundaryResult {
  farmSlug: string
  fieldSlug: string
  file: NormalizedFile<Record<string, unknown>>
}

export interface MappedGrowerEntityResult {
  slug: string
  file: NormalizedFile<Record<string, unknown>>
}

export interface MappedFieldOperationResult {
  farmSlug: string
  fieldSlug: string
  year: number
  category: 'planting' | 'harvest' | 'applications' | 'operations'
  applicationCategory?: 'spraying' | 'fertilizer' | 'other'
  files: NormalizedFile<Record<string, unknown>>[]
}

interface DeereSourceMetadata {
  deereId: string
  sourceApi: string
  sourceOperation: string
  fetchedAt: string
  updatedAt?: string
  sourceSystem: 'john-deere'
}

interface DeereGeoJsonFeature {
  type: 'Feature'
  id?: string
  geometry: GeoJsonGeometry | null
  properties: Record<string, unknown>
}

interface DeereGeoJsonFeatureCollection extends Record<string, unknown> {
  type: 'FeatureCollection'
  features: DeereGeoJsonFeature[]
}

type GeoJsonGeometry = Record<string, unknown>

interface RelationResolution {
  deereId: string
  displayName: string
  slug: string
}

interface ClassifiedFieldOperation {
  category: 'planting' | 'harvest' | 'applications' | 'operations'
  applicationCategory?: 'spraying' | 'fertilizer' | 'other'
  operationType: string
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }

  return value as Record<string, unknown>
}

function getValueAtPath(source: Record<string, unknown>, candidatePath: string): unknown {
  let current: unknown = source

  for (const segment of candidatePath.split('.')) {
    const currentRecord = asRecord(current)

    if (!currentRecord || !(segment in currentRecord)) {
      return undefined
    }

    current = currentRecord[segment]
  }

  return current
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed ? trimmed : undefined
  }

  if (typeof value === 'number' || typeof value === 'bigint') {
    return String(value)
  }

  return undefined
}

function pickFirstString(source: DeereEntity, candidates: string[]): string | undefined {
  for (const candidate of candidates) {
    const value = toStringValue(getValueAtPath(source, candidate))

    if (value) {
      return value
    }
  }

  return undefined
}

function parseDateValue(value: unknown): Date | undefined {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value
  }

  if (typeof value !== 'string' && typeof value !== 'number') {
    return undefined
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? undefined : parsed
}

function pickFirstDate(source: DeereEntity, candidates: string[]): Date | undefined {
  for (const candidate of candidates) {
    const parsed = parseDateValue(getValueAtPath(source, candidate))

    if (parsed) {
      return parsed
    }
  }

  return undefined
}

function toIsoString(value: Date | string): string {
  const parsed = parseDateValue(value)

  if (!parsed) {
    throw new Error(`Invalid date value: ${String(value)}`)
  }

  return parsed.toISOString()
}

function requireDeereId(source: DeereEntity, candidates: string[], entityLabel: string): string {
  const deereId = pickFirstString(source, candidates)

  if (!deereId) {
    throw new Error(`Missing Deere ID for ${entityLabel}`)
  }

  return deereId
}

function inferDisplayName(source: DeereEntity, fallback: string, candidates: string[] = DEFAULT_NAME_CANDIDATES): string {
  return pickFirstString(source, candidates) ?? fallback
}

function buildSourceMetadata(
  source: DeereEntity,
  context: DeereMappingContext,
  idCandidates: string[]
): DeereSourceMetadata {
  const deereId = requireDeereId(source, idCandidates, context.sourceApi)
  const updatedAt = pickFirstDate(source, DEFAULT_UPDATED_AT_CANDIDATES)

  return {
    deereId,
    sourceApi: context.sourceApi,
    sourceOperation: context.sourceOperation,
    fetchedAt: toIsoString(context.fetchedAt),
    ...(updatedAt ? { updatedAt: updatedAt.toISOString() } : {}),
    sourceSystem: 'john-deere'
  }
}

function toJsonFile<TContent extends Record<string, unknown>>(filePath: string, content: TContent): NormalizedFile<TContent> {
  return {
    path: filePath,
    format: filePath.endsWith('.geojson') ? 'geojson' : 'json',
    content
  }
}

function toEntityFileName(source: DeereEntity, idCandidates: string[], displayName: string): string {
  const deereId = requireDeereId(source, idCandidates, displayName)
  return `${createDeereSlug({ displayName, deereId })}.john-deere.json`
}

function toFeatureCollection(
  source: DeereEntity,
  sharedProperties: Record<string, unknown>
): DeereGeoJsonFeatureCollection {
  const maybeCollection = pickFirstString(source, ['type']) === 'FeatureCollection'
  const maybeFeature = pickFirstString(source, ['type']) === 'Feature'
  const featuresValue = maybeCollection ? getValueAtPath(source, 'features') : undefined

  if (Array.isArray(featuresValue)) {
    const features = featuresValue.map((featureValue, index) => {
      const feature = asRecord(featureValue) ?? {}

      return {
        type: 'Feature' as const,
        id: toStringValue(feature.id) ?? toStringValue(feature.properties && asRecord(feature.properties)?.id) ?? String(index + 1),
        geometry: (asRecord(feature.geometry) ?? null) as GeoJsonGeometry | null,
        properties: {
          ...sharedProperties,
          ...(asRecord(feature.properties) ?? {})
        }
      }
    })

    return {
      type: 'FeatureCollection',
      features
    }
  }

  if (maybeFeature) {
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          id: toStringValue(source.id),
          geometry: (asRecord(getValueAtPath(source, 'geometry')) ?? null) as GeoJsonGeometry | null,
          properties: sharedProperties
        }
      ]
    }
  }

  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: toStringValue(source.id),
        geometry: (asRecord(getValueAtPath(source, 'geometry')) ?? null) as GeoJsonGeometry | null,
        properties: sharedProperties
      }
    ]
  }
}

function classifyProduct(source: DeereEntity): 'seed' | 'chemical' | 'fertilizer' | 'other' {
  const haystack = [
    pickFirstString(source, ['productType', 'type', 'category', 'kind']),
    pickFirstString(source, DEFAULT_NAME_CANDIDATES)
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  if (/seed|hybrid|variet/.test(haystack)) {
    return 'seed'
  }

  if (/fert|nutrient/.test(haystack)) {
    return 'fertilizer'
  }

  if (/chem|herb|fung|pestic|insect|spray/.test(haystack)) {
    return 'chemical'
  }

  return 'other'
}

function classifyFieldOperation(source: DeereEntity): ClassifiedFieldOperation {
  const operationType =
    pickFirstString(source, ['operationType', 'type', 'workType', 'category', 'name']) ?? 'operation'
  const haystack = operationType.toLowerCase()

  if (/plant|seed|sow/.test(haystack)) {
    return { category: 'planting', operationType }
  }

  if (/harvest|yield/.test(haystack)) {
    return { category: 'harvest', operationType }
  }

  if (/appl|spray|fert|chemical|herb|fung|pestic|insect|nutrient/.test(haystack)) {
    if (/fert|nutrient/.test(haystack)) {
      return { category: 'applications', applicationCategory: 'fertilizer', operationType }
    }

    if (/spray|chemical|herb|fung|pestic|insect/.test(haystack)) {
      return { category: 'applications', applicationCategory: 'spraying', operationType }
    }

    return { category: 'applications', applicationCategory: 'other', operationType }
  }

  return { category: 'operations', operationType }
}

function resolveOperationDate(source: DeereEntity, fallback: Date | string): Date {
  return (
    pickFirstDate(source, [
      'operationDate',
      'startDate',
      'startTime',
      'effectiveAt',
      'occurredAt',
      ...DEFAULT_UPDATED_AT_CANDIDATES
    ]) ?? parseDateValue(fallback) ?? new Date(toIsoString(fallback))
  )
}

function normalizeRelationReference(
  source: DeereRelationReference | DeereEntity | undefined,
  idCandidates: string[],
  nameCandidates: string[],
  slugCandidates: string[]
): DeereRelationReference | undefined {
  if (!source) {
    return undefined
  }

  const record = source as DeereEntity

  return {
    deereId: 'deereId' in record ? toStringValue(record.deereId) ?? pickFirstString(record, idCandidates) : pickFirstString(record, idCandidates),
    displayName:
      'displayName' in record
        ? toStringValue(record.displayName) ?? pickFirstString(record, nameCandidates)
        : pickFirstString(record, nameCandidates),
    slug:
      'slug' in record
        ? toStringValue(record.slug) ?? pickFirstString(record, slugCandidates)
        : pickFirstString(record, slugCandidates)
  }
}

export class JohnDeereCanonicalMapper {
  private readonly farmSlugsById = new Map<string, string>()
  private readonly farmSlugSet = new Set<string>()
  private readonly fieldSlugsByFarmId = new Map<string, Map<string, string>>()
  private readonly fieldSlugSetsByFarmId = new Map<string, Set<string>>()

  constructor(private readonly context: DeereMappingContext) {}

  mapOrganization(organization: DeereEntity): MappedOrganizationResult {
    const metadata = buildSourceMetadata(organization, this.context, ['id', 'deereId', 'organizationId'])
    const displayName = inferDisplayName(organization, this.context.growerSlug)
    const growerPaths = buildGrowerPaths(this.context)

    return {
      file: toJsonFile(growerPaths.growerFile, {
        growerSlug: this.context.growerSlug,
        displayName,
        organizationType: pickFirstString(organization, ['type', 'organizationType']),
        ...metadata
      })
    }
  }

  mapFarm(farm: DeereEntity): MappedFarmResult {
    const metadata = buildSourceMetadata(farm, this.context, FARM_ID_CANDIDATES)
    const displayName = inferDisplayName(farm, metadata.deereId)
    const farmSlug = this.ensureFarmSlug({ deereId: metadata.deereId, displayName })
    const farmPaths = buildFarmPaths({
      dataRoot: this.context.dataRoot,
      growerSlug: this.context.growerSlug,
      farmSlug
    })

    return {
      farmSlug,
      file: toJsonFile(farmPaths.farmFile, {
        growerSlug: this.context.growerSlug,
        farmSlug,
        displayName,
        archived: getValueAtPath(farm, 'archived') ?? false,
        ...metadata
      })
    }
  }

  mapField(field: DeereEntity, options: { farm?: DeereRelationReference | DeereEntity } = {}): MappedFieldResult {
    const metadata = buildSourceMetadata(field, this.context, FIELD_ID_CANDIDATES)
    const displayName = inferDisplayName(field, metadata.deereId)
    const farm = this.resolveFarmRelation(options.farm, field)
    const fieldSlug = this.ensureFieldSlug(farm.deereId, {
      deereId: metadata.deereId,
      displayName
    })
    const fieldPaths = buildFieldPaths({
      dataRoot: this.context.dataRoot,
      growerSlug: this.context.growerSlug,
      farmSlug: farm.slug,
      fieldSlug,
      year: new Date(toIsoString(this.context.fetchedAt)).getUTCFullYear()
    })

    return {
      farmSlug: farm.slug,
      fieldSlug,
      file: toJsonFile(fieldPaths.fieldFile, {
        growerSlug: this.context.growerSlug,
        farmSlug: farm.slug,
        fieldSlug,
        displayName,
        farmDeereId: farm.deereId,
        ...metadata
      })
    }
  }

  mapBoundary(
    boundary: DeereEntity,
    options: {
      farm?: DeereRelationReference | DeereEntity
      field?: DeereRelationReference | DeereEntity
    } = {}
  ): MappedBoundaryResult {
    const metadata = buildSourceMetadata(boundary, this.context, BOUNDARY_ID_CANDIDATES)
    const farm = this.resolveFarmRelation(options.farm, boundary)
    const field = this.resolveFieldRelation(farm.deereId, options.field, boundary)
    const fieldPaths = buildFieldPaths({
      dataRoot: this.context.dataRoot,
      growerSlug: this.context.growerSlug,
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      year: new Date(toIsoString(this.context.fetchedAt)).getUTCFullYear()
    })

    const geoJson = toFeatureCollection(boundary, {
      growerSlug: this.context.growerSlug,
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      boundaryType: pickFirstString(boundary, ['boundaryType', 'typeName']) ?? 'field-boundary',
      ...metadata
    })

    return {
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      file: toJsonFile(fieldPaths.fieldBoundaryFile, {
        ...geoJson,
        ...metadata
      })
    }
  }

  mapEquipment(equipment: DeereEntity): MappedGrowerEntityResult {
    return this.mapGrowerEntity(equipment, {
      idCandidates: EQUIPMENT_ID_CANDIDATES,
      directoryPath: buildGrowerPaths(this.context).equipmentDir,
      displayNameFallback: 'equipment'
    })
  }

  mapOperator(operator: DeereEntity): MappedGrowerEntityResult {
    return this.mapGrowerEntity(operator, {
      idCandidates: OPERATOR_ID_CANDIDATES,
      directoryPath: buildGrowerPaths(this.context).operatorsDir,
      displayNameFallback: 'operator'
    })
  }

  mapCropType(cropType: DeereEntity): MappedGrowerEntityResult {
    return this.mapGrowerEntity(cropType, {
      idCandidates: CROP_TYPE_ID_CANDIDATES,
      directoryPath: buildGrowerPaths(this.context).cropTypesDir,
      displayNameFallback: 'crop-type'
    })
  }

  mapProduct(product: DeereEntity): MappedGrowerEntityResult {
    const productCategory = classifyProduct(product)

    return this.mapGrowerEntity(product, {
      idCandidates: PRODUCT_ID_CANDIDATES,
      directoryPath: path.join(buildGrowerPaths(this.context).productsDir, productCategory),
      displayNameFallback: 'product',
      extraContent: {
        productCategory
      }
    })
  }

  mapFieldOperation(
    fieldOperation: DeereEntity,
    options: {
      farm?: DeereRelationReference | DeereEntity
      field?: DeereRelationReference | DeereEntity
    } = {}
  ): MappedFieldOperationResult {
    const metadata = buildSourceMetadata(fieldOperation, this.context, OPERATION_ID_CANDIDATES)
    const farm = this.resolveFarmRelation(options.farm, fieldOperation)
    const field = this.resolveFieldRelation(farm.deereId, options.field, fieldOperation)
    const occurredAt = resolveOperationDate(fieldOperation, this.context.fetchedAt)
    const year = occurredAt.getUTCFullYear()
    const timestampPrefix = formatJohnDeereTimestampPrefix(occurredAt)
    const classified = classifyFieldOperation(fieldOperation)
    const fieldPaths = buildFieldPaths({
      dataRoot: this.context.dataRoot,
      growerSlug: this.context.growerSlug,
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      year
    })
    const operationTypeSlug = slugifyDeereName(classified.operationType)
    const fileStem = `${timestampPrefix}_${operationTypeSlug}_${slugifyDeereName(metadata.deereId)}`
    const content = {
      growerSlug: this.context.growerSlug,
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      farmDeereId: farm.deereId,
      fieldDeereId: field.deereId,
      operationType: classified.operationType,
      occurredAt: occurredAt.toISOString(),
      ...metadata
    }

    const files = [
      toJsonFile(path.join(fieldPaths.operationsYearDir, `${fileStem}.john-deere.json`), {
        category: 'operations',
        ...content
      })
    ]

    if (classified.category === 'planting') {
      files.push(
        toJsonFile(path.join(fieldPaths.plantingYearDir, `${fileStem}.john-deere.json`), {
          category: 'planting',
          ...content
        })
      )
    }

    if (classified.category === 'harvest') {
      files.push(
        toJsonFile(path.join(fieldPaths.harvestYearDir, `${fileStem}.john-deere.json`), {
          category: 'harvest',
          ...content
        })
      )
    }

    if (classified.category === 'applications') {
      const applicationDirectory =
        classified.applicationCategory === 'spraying'
          ? fieldPaths.sprayingDir
          : classified.applicationCategory === 'fertilizer'
            ? fieldPaths.fertilizerDir
            : fieldPaths.otherApplicationsDir

      files.push(
        toJsonFile(path.join(applicationDirectory, `${fileStem}.john-deere.json`), {
          category: 'applications',
          applicationCategory: classified.applicationCategory,
          ...content
        })
      )
    }

    return {
      farmSlug: farm.slug,
      fieldSlug: field.slug,
      year,
      category: classified.category,
      applicationCategory: classified.applicationCategory,
      files
    }
  }

  private mapGrowerEntity(
    source: DeereEntity,
    options: {
      idCandidates: string[]
      directoryPath: string
      displayNameFallback: string
      extraContent?: Record<string, unknown>
    }
  ): MappedGrowerEntityResult {
    const metadata = buildSourceMetadata(source, this.context, options.idCandidates)
    const displayName = inferDisplayName(source, metadata.deereId)
    const slug = createDeereSlug({
      displayName,
      deereId: metadata.deereId
    })
    const filePath = path.join(options.directoryPath, toEntityFileName(source, options.idCandidates, displayName))

    return {
      slug,
      file: toJsonFile(filePath, {
        growerSlug: this.context.growerSlug,
        displayName,
        ...options.extraContent,
        ...metadata
      })
    }
  }

  private ensureFarmSlug(reference: DeereRelationReference): string {
    if (!reference.deereId) {
      throw new Error('Missing Deere ID for farm relation')
    }

    const existing = this.farmSlugsById.get(reference.deereId)

    if (existing) {
      return existing
    }

    const slug =
      reference.slug ??
      createDeereSlug({
        displayName: reference.displayName ?? reference.deereId,
        deereId: reference.deereId,
        existingSlugs: this.farmSlugSet
      })

    this.farmSlugsById.set(reference.deereId, slug)
    this.farmSlugSet.add(slug)
    return slug
  }

  private ensureFieldSlug(farmDeereId: string, reference: DeereRelationReference): string {
    if (!reference.deereId) {
      throw new Error('Missing Deere ID for field relation')
    }

    const existingByFarm = this.fieldSlugsByFarmId.get(farmDeereId)
    const existing = existingByFarm?.get(reference.deereId)

    if (existing) {
      return existing
    }

    const existingSlugs = this.fieldSlugSetsByFarmId.get(farmDeereId) ?? new Set<string>()
    const slug =
      reference.slug ??
      createDeereSlug({
        displayName: reference.displayName ?? reference.deereId,
        deereId: reference.deereId,
        existingSlugs
      })
    const slugsById = existingByFarm ?? new Map<string, string>()

    slugsById.set(reference.deereId, slug)
    existingSlugs.add(slug)
    this.fieldSlugsByFarmId.set(farmDeereId, slugsById)
    this.fieldSlugSetsByFarmId.set(farmDeereId, existingSlugs)
    return slug
  }

  private resolveFarmRelation(
    provided: DeereRelationReference | DeereEntity | undefined,
    fallbackSource: DeereEntity
  ): RelationResolution {
    const explicit = normalizeRelationReference(
      provided,
      FARM_ID_CANDIDATES,
      DEFAULT_NAME_CANDIDATES,
      ['slug', 'farmSlug']
    )
    const fallback = normalizeRelationReference(
      {
        deereId: pickFirstString(fallbackSource, RELATION_FARM_ID_CANDIDATES),
        displayName: pickFirstString(fallbackSource, RELATION_FARM_NAME_CANDIDATES)
      },
      FARM_ID_CANDIDATES,
      DEFAULT_NAME_CANDIDATES,
      ['slug', 'farmSlug']
    )
    const reference = {
      deereId: explicit?.deereId ?? fallback?.deereId,
      displayName: explicit?.displayName ?? fallback?.displayName,
      slug: explicit?.slug ?? fallback?.slug
    }

    if (!reference.deereId) {
      throw new Error('Unable to resolve farm relation for Deere entity')
    }

    const slug = this.ensureFarmSlug(reference)
    return {
      deereId: reference.deereId,
      displayName: reference.displayName ?? reference.deereId,
      slug
    }
  }

  private resolveFieldRelation(
    farmDeereId: string,
    provided: DeereRelationReference | DeereEntity | undefined,
    fallbackSource: DeereEntity
  ): RelationResolution {
    const explicit = normalizeRelationReference(
      provided,
      FIELD_ID_CANDIDATES,
      DEFAULT_NAME_CANDIDATES,
      ['slug', 'fieldSlug']
    )
    const fallback = normalizeRelationReference(
      {
        deereId: pickFirstString(fallbackSource, RELATION_FIELD_ID_CANDIDATES),
        displayName: pickFirstString(fallbackSource, RELATION_FIELD_NAME_CANDIDATES)
      },
      FIELD_ID_CANDIDATES,
      DEFAULT_NAME_CANDIDATES,
      ['slug', 'fieldSlug']
    )
    const reference = {
      deereId: explicit?.deereId ?? fallback?.deereId,
      displayName: explicit?.displayName ?? fallback?.displayName,
      slug: explicit?.slug ?? fallback?.slug
    }

    if (!reference.deereId) {
      throw new Error('Unable to resolve field relation for Deere entity')
    }

    const slug = this.ensureFieldSlug(farmDeereId, reference)
    return {
      deereId: reference.deereId,
      displayName: reference.displayName ?? reference.deereId,
      slug
    }
  }
}

export async function writeNormalizedFiles(files: Iterable<NormalizedFile>): Promise<string[]> {
  const writtenFiles: string[] = []

  for (const file of files) {
    await mkdir(path.dirname(file.path), { recursive: true })
    await writeFile(file.path, `${JSON.stringify(file.content, null, 2)}\n`, 'utf8')
    writtenFiles.push(file.path)
  }

  return writtenFiles
}
