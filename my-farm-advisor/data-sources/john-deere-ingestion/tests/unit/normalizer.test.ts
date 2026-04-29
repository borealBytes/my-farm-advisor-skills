import path from 'node:path'
import { tmpdir } from 'node:os'
import { mkdtemp, readFile, rm } from 'node:fs/promises'

import { afterEach, describe, expect, it } from 'vitest'

import { JohnDeereCanonicalMapper, writeNormalizedFiles } from '../../src/normalize/mapper.js'

const fetchedAt = new Date('2026-04-28T14:05:06.000Z')

async function readJsonFile(filePath: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(filePath, 'utf8')) as Record<string, unknown>
}

describe('JohnDeereCanonicalMapper', () => {
  const tempRoots: string[] = []

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })))
    tempRoots.length = 0
  })

  async function createMapper(sourceApi: string, sourceOperation: string): Promise<{
    tempRoot: string
    mapper: JohnDeereCanonicalMapper
  }> {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-normalizer-'))
    tempRoots.push(tempRoot)

    return {
      tempRoot,
      mapper: new JohnDeereCanonicalMapper({
        dataRoot: tempRoot,
        growerSlug: 'test-grower',
        fetchedAt,
        sourceApi,
        sourceOperation
      })
    }
  }

  it('maps organization payloads to grower.john-deere.json with source metadata', async () => {
    const { mapper } = await createMapper('organizations', 'listOrganizations')
    const result = mapper.mapOrganization({
      id: 'org-1',
      name: 'Acme Growers',
      updatedAt: '2026-04-20T12:00:00.000Z'
    })

    await writeNormalizedFiles([result.file])
    const written = await readJsonFile(result.file.path)

    expect(result.file.path).toMatch(/growers\/test-grower\/grower\.john-deere\.json$/)
    expect(written).toMatchObject({
      growerSlug: 'test-grower',
      displayName: 'Acme Growers',
      deereId: 'org-1',
      sourceApi: 'organizations',
      sourceOperation: 'listOrganizations',
      fetchedAt: '2026-04-28T14:05:06.000Z',
      updatedAt: '2026-04-20T12:00:00.000Z',
      sourceSystem: 'john-deere'
    })
  })

  it('maps farms and fields into canonical Deere file names using stable slugs', async () => {
    const { mapper } = await createMapper('fields', 'listFields')
    const farm = mapper.mapFarm({ id: 'farm-1', name: 'North 40' })
    const field = mapper.mapField(
      { id: 'field-1', name: 'Pivot A', updatedTime: '2026-04-22T00:00:00.000Z' },
      { farm: { deereId: 'farm-1', displayName: 'North 40' } }
    )

    await writeNormalizedFiles([farm.file, field.file])
    const writtenField = await readJsonFile(field.file.path)

    expect(farm.farmSlug).toBe('north-40')
    expect(field.fieldSlug).toBe('pivot-a')
    expect(farm.file.path).toMatch(/growers\/test-grower\/farms\/north-40\/farm\.john-deere\.json$/)
    expect(field.file.path).toMatch(
      /growers\/test-grower\/farms\/north-40\/fields\/pivot-a\/field\.john-deere\.json$/
    )
    expect(writtenField).toMatchObject({
      farmSlug: 'north-40',
      fieldSlug: 'pivot-a',
      farmDeereId: 'farm-1',
      deereId: 'field-1',
      sourceApi: 'fields',
      sourceOperation: 'listFields',
      updatedAt: '2026-04-22T00:00:00.000Z'
    })
  })

  it('maps field boundaries to field_boundary.john-deere.geojson without touching neutral boundary names', async () => {
    const { mapper } = await createMapper('boundaries', 'listBoundaries')
    mapper.mapFarm({ id: 'farm-1', name: 'North 40' })
    mapper.mapField({ id: 'field-1', name: 'Pivot A' }, { farm: { deereId: 'farm-1', displayName: 'North 40' } })
    const boundary = mapper.mapBoundary(
      {
        id: 'boundary-1',
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [-93.0, 41.0],
              [-92.0, 41.0],
              [-92.0, 42.0],
              [-93.0, 42.0],
              [-93.0, 41.0]
            ]
          ]
        }
      },
      {
        farm: { deereId: 'farm-1', displayName: 'North 40' },
        field: { deereId: 'field-1', displayName: 'Pivot A' }
      }
    )

    await writeNormalizedFiles([boundary.file])
    const writtenBoundary = await readJsonFile(boundary.file.path)

    expect(boundary.file.path).toMatch(
      /growers\/test-grower\/farms\/north-40\/fields\/pivot-a\/boundary\/field_boundary\.john-deere\.geojson$/
    )
    expect(writtenBoundary.deereId).toBe('boundary-1')
    expect(writtenBoundary.type).toBe('FeatureCollection')
    expect(Array.isArray(writtenBoundary.features)).toBe(true)
  })

  it('maps equipment, operators, products, and crop types to grower-level Deere folders', async () => {
    const { mapper } = await createMapper('equipment', 'listGrowerResources')
    const equipment = mapper.mapEquipment({ id: 'eq-1', name: 'Sprayer 7' })
    const operator = mapper.mapOperator({ id: 'op-1', name: 'Dana Operator' })
    const product = mapper.mapProduct({ id: 'prod-1', name: 'Starter Fertilizer', productType: 'fertilizer' })
    const cropType = mapper.mapCropType({ id: 'crop-1', name: 'Corn' })

    await writeNormalizedFiles([equipment.file, operator.file, product.file, cropType.file])
    const writtenProduct = await readJsonFile(product.file.path)

    expect(equipment.file.path).toMatch(/growers\/test-grower\/equipment\/john-deere\/sprayer-7\.john-deere\.json$/)
    expect(operator.file.path).toMatch(/growers\/test-grower\/operators\/john-deere\/dana-operator\.john-deere\.json$/)
    expect(product.file.path).toMatch(
      /growers\/test-grower\/products\/john-deere\/fertilizer\/starter-fertilizer\.john-deere\.json$/
    )
    expect(cropType.file.path).toMatch(/growers\/test-grower\/crop-types\/john-deere\/corn\.john-deere\.json$/)
    expect(writtenProduct).toMatchObject({
      productCategory: 'fertilizer',
      sourceApi: 'equipment',
      sourceOperation: 'listGrowerResources'
    })
  })

  it('maps planting, harvest, and application operations into year folders plus the general operations folder', async () => {
    const { mapper } = await createMapper('fieldOperations', 'listAllWithMeasurements')
    mapper.mapFarm({ id: 'farm-1', name: 'North 40' })
    mapper.mapField({ id: 'field-1', name: 'Pivot A' }, { farm: { deereId: 'farm-1', displayName: 'North 40' } })

    const planting = mapper.mapFieldOperation(
      {
        id: 'operation-plant',
        operationType: 'Planting',
        operationDate: '2025-04-10T08:00:00.000Z',
        farmId: 'farm-1',
        fieldId: 'field-1'
      },
      {
        farm: { deereId: 'farm-1', displayName: 'North 40' },
        field: { deereId: 'field-1', displayName: 'Pivot A' }
      }
    )
    const harvest = mapper.mapFieldOperation(
      {
        id: 'operation-harvest',
        operationType: 'Harvest',
        operationDate: '2025-10-14T17:30:00.000Z',
        farmId: 'farm-1',
        fieldId: 'field-1'
      },
      {
        farm: { deereId: 'farm-1', displayName: 'North 40' },
        field: { deereId: 'field-1', displayName: 'Pivot A' }
      }
    )
    const application = mapper.mapFieldOperation(
      {
        id: 'operation-fert',
        operationType: 'Fertilizer Application',
        operationDate: '2025-05-01T09:15:00.000Z',
        farmId: 'farm-1',
        fieldId: 'field-1'
      },
      {
        farm: { deereId: 'farm-1', displayName: 'North 40' },
        field: { deereId: 'field-1', displayName: 'Pivot A' }
      }
    )

    await writeNormalizedFiles([...planting.files, ...harvest.files, ...application.files])

    expect(planting.files.some((file) => /planting\/john-deere\/2025\//.test(file.path))).toBe(true)
    expect(planting.files.some((file) => /operations\/john-deere\/2025\//.test(file.path))).toBe(true)
    expect(harvest.files.some((file) => /harvest\/john-deere\/2025\//.test(file.path))).toBe(true)
    expect(application.files.some((file) => /applications\/john-deere\/2025\/fertilizer\//.test(file.path))).toBe(
      true
    )
    expect(application.files.some((file) => /operations\/john-deere\/2025\//.test(file.path))).toBe(true)

    const writtenPlanting = await readJsonFile(
      planting.files.find((file) => /planting\/john-deere\/2025\//.test(file.path))?.path ?? ''
    )

    expect(writtenPlanting).toMatchObject({
      deereId: 'operation-plant',
      operationType: 'Planting',
      occurredAt: '2025-04-10T08:00:00.000Z',
      fieldSlug: 'pivot-a',
      farmSlug: 'north-40'
    })
  })
})
