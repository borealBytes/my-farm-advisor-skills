import { createHash } from 'node:crypto'
import { access, readFile, rm, mkdtemp } from 'node:fs/promises'
import path from 'node:path'
import { tmpdir } from 'node:os'

import { describe, expect, it } from 'vitest'

import { buildGrowerPaths } from '../../src/paths.js'
import { FileCheckpointStore } from '../../src/storage/checkpoint.js'
import { startWebhookServer } from '../../src/webhook/server.js'

describe('John Deere webhook server', () => {
  it('serves a health endpoint', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-webhook-health-'))

    const server = await startWebhookServer({
      dataRoot: tempRoot,
      growerSlug: 'grower-a',
      port: 0
    })

    try {
      const response = await fetch(`${server.url}/health`)

      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toEqual({ status: 'ok' })
    } finally {
      await server.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('logs webhook events and marks the sync-needed checkpoint', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-webhook-event-'))

    const server = await startWebhookServer({
      dataRoot: tempRoot,
      growerSlug: 'grower-a',
      port: 0,
      now: () => new Date('2026-04-29T15:16:17.000Z')
    })

    try {
      const payload = {
        eventType: 'field.updated',
        timestamp: '2026-04-29T12:00:00.000Z',
        source: {
          orgId: 'org-1',
          system: 'john-deere'
        },
        resource: {
          id: 'field-123'
        }
      }
      const rawBody = JSON.stringify(payload)
      const response = await fetch(`${server.url}/webhook`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body: rawBody
      })

      expect(response.status).toBe(200)
      await expect(response.json()).resolves.toEqual({
        status: 'accepted',
        growerSlug: 'grower-a',
        eventType: 'field.updated',
        payloadHash: createHash('sha256').update(rawBody).digest('hex')
      })

      const growerPaths = buildGrowerPaths({ dataRoot: tempRoot, growerSlug: 'grower-a' })
      const loggedEventsRaw = await readFile(growerPaths.rawWebhooksEventsFile, 'utf8')
      const loggedEvents = loggedEventsRaw.trim().split('\n').map((line) => JSON.parse(line))

      expect(loggedEvents).toHaveLength(1)
      expect(loggedEvents[0]).toEqual({
        receivedAt: '2026-04-29T15:16:17.000Z',
        growerSlug: 'grower-a',
        eventType: 'field.updated',
        timestamp: '2026-04-29T12:00:00.000Z',
        payloadHash: createHash('sha256').update(rawBody).digest('hex'),
        source: {
          orgId: 'org-1',
          system: 'john-deere'
        },
        payload
      })

      const checkpointStore = new FileCheckpointStore({
        dataRoot: tempRoot,
        growerSlug: 'grower-a'
      })
      const checkpointState = await checkpointStore.load()

      expect(checkpointState).toEqual({
        growerSlug: 'grower-a',
        lastSuccessfulRun: '2026-04-29T15:16:17.000Z',
        operationCursors: {
          'sync-needed': {
            fingerprint: createHash('sha256').update(rawBody).digest('hex'),
            requestContext: {
              reason: 'webhook',
              eventType: 'field.updated',
              timestamp: '2026-04-29T12:00:00.000Z',
              source: {
                orgId: 'org-1',
                system: 'john-deere'
              }
            },
            updatedAt: '2026-04-29T15:16:17.000Z'
          }
        }
      })

      await expect(access(path.join(growerPaths.rawManifestsDir, 'checkpoints.json'))).resolves.toBeUndefined()
      await expect(access(path.join(growerPaths.manifestsDir, 'checkpoints.json'))).resolves.toBeUndefined()
    } finally {
      await server.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })

  it('rejects webhook payloads missing required fields', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-webhook-invalid-'))

    const server = await startWebhookServer({
      dataRoot: tempRoot,
      growerSlug: 'grower-a',
      port: 0
    })

    try {
      const response = await fetch(`${server.url}/webhook`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json'
        },
        body: JSON.stringify({
          eventType: 'field.updated',
          timestamp: '2026-04-29T12:00:00.000Z'
        })
      })

      expect(response.status).toBe(400)
      await expect(response.json()).resolves.toEqual({
        status: 'error',
        message: 'Webhook field `source` must be an object.'
      })
    } finally {
      await server.close()
      await rm(tempRoot, { recursive: true, force: true })
    }
  })
})
