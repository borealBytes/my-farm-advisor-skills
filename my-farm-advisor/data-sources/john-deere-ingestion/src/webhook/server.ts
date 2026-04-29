import { createHash } from 'node:crypto'
import { appendFile, mkdir } from 'node:fs/promises'
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import path from 'node:path'

import { buildGrowerPaths } from '../paths.js'
import { FileCheckpointStore } from '../storage/checkpoint.js'

export const DEFAULT_WEBHOOK_PORT = 9090
export const DEFAULT_WEBHOOK_HOST = '127.0.0.1'

export interface JohnDeereWebhookPayload extends Record<string, unknown> {
  eventType: string
  timestamp: string
  source: Record<string, unknown>
}

export interface WebhookEventRecord {
  receivedAt: string
  growerSlug: string
  eventType: string
  timestamp: string
  payloadHash: string
  source: Record<string, unknown>
  payload: JohnDeereWebhookPayload
}

export interface StartWebhookServerOptions {
  dataRoot: string
  growerSlug: string
  port?: number
  host?: string
  now?: () => Date
  createServerImpl?: typeof createServer
}

export interface StartedWebhookServer {
  host: string
  port: number
  url: string
  eventsFile: string
  close: () => Promise<void>
}

interface ParsedWebhookRequest {
  payload: JohnDeereWebhookPayload
  payloadHash: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readNonEmptyString(value: unknown, fieldName: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`Webhook field \`${fieldName}\` must be a non-empty string.`)
  }

  return value
}

function writeJson(response: ServerResponse<IncomingMessage>, statusCode: number, payload: unknown): void {
  response.statusCode = statusCode
  response.setHeader('content-type', 'application/json; charset=utf-8')
  response.end(`${JSON.stringify(payload)}\n`)
}

async function readRequestBody(request: IncomingMessage): Promise<string> {
  const chunks: string[] = []

  for await (const chunk of request) {
    chunks.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'))
  }

  return chunks.join('')
}

function parseWebhookRequest(rawBody: string): ParsedWebhookRequest {
  let parsed: unknown

  try {
    parsed = JSON.parse(rawBody)
  } catch {
    throw new TypeError('Webhook request body must be valid JSON.')
  }

  if (!isRecord(parsed)) {
    throw new TypeError('Webhook request body must be a JSON object.')
  }

  const eventType = readNonEmptyString(parsed.eventType, 'eventType')
  const timestamp = readNonEmptyString(parsed.timestamp, 'timestamp')

  if (!isRecord(parsed.source)) {
    throw new TypeError('Webhook field `source` must be an object.')
  }

  return {
    payload: {
      ...parsed,
      eventType,
      timestamp,
      source: parsed.source
    },
    payloadHash: createHash('sha256').update(rawBody).digest('hex')
  }
}

async function appendWebhookEvent(options: {
  dataRoot: string
  growerSlug: string
  event: WebhookEventRecord
}): Promise<string> {
  const eventsFile = buildGrowerPaths({ dataRoot: options.dataRoot, growerSlug: options.growerSlug }).rawWebhooksEventsFile

  await mkdir(path.dirname(eventsFile), { recursive: true })
  await appendFile(eventsFile, `${JSON.stringify(options.event)}\n`, 'utf8')

  return eventsFile
}

async function markSyncNeededCheckpoint(options: {
  dataRoot: string
  growerSlug: string
  event: WebhookEventRecord
}): Promise<void> {
  const checkpointStore = new FileCheckpointStore({
    dataRoot: options.dataRoot,
    growerSlug: options.growerSlug
  })

  await checkpointStore.recordOperationResult({
    operation: 'sync-needed',
    status: 'accessible',
    completedAt: options.event.receivedAt,
    fingerprint: options.event.payloadHash,
    requestContext: {
      reason: 'webhook',
      eventType: options.event.eventType,
      timestamp: options.event.timestamp,
      source: options.event.source
    }
  })
}

async function closeServer(server: Server): Promise<void> {
  if (!server.listening) {
    return
  }

  await new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error)
      } else {
        resolve()
      }
    })
  })
}

function waitForSigint(signal?: AbortSignal): Promise<'sigint' | 'abort'> {
  return new Promise((resolve) => {
    const onSigint = () => {
      cleanup()
      resolve('sigint')
    }

    const onAbort = () => {
      cleanup()
      resolve('abort')
    }

    const cleanup = () => {
      process.off('SIGINT', onSigint)
      signal?.removeEventListener('abort', onAbort)
    }

    process.once('SIGINT', onSigint)

    if (signal) {
      signal.addEventListener('abort', onAbort, { once: true })
    }
  })
}

export async function startWebhookServer(options: StartWebhookServerOptions): Promise<StartedWebhookServer> {
  const host = options.host ?? DEFAULT_WEBHOOK_HOST
  const port = options.port ?? DEFAULT_WEBHOOK_PORT
  const now = options.now ?? (() => new Date())
  const createServerImpl = options.createServerImpl ?? createServer
  const eventsFile = buildGrowerPaths({ dataRoot: options.dataRoot, growerSlug: options.growerSlug }).rawWebhooksEventsFile

  const server = createServerImpl(async (request, response) => {
    const method = request.method ?? 'GET'
    const requestUrl = new URL(request.url ?? '/', `http://${host}:${port}`)

    if (method === 'GET' && requestUrl.pathname === '/health') {
      writeJson(response, 200, { status: 'ok' })
      return
    }

    if (method === 'POST' && requestUrl.pathname === '/webhook') {
      try {
        const rawBody = await readRequestBody(request)
        const parsedRequest = parseWebhookRequest(rawBody)
        const event: WebhookEventRecord = {
          receivedAt: now().toISOString(),
          growerSlug: options.growerSlug,
          eventType: parsedRequest.payload.eventType,
          timestamp: parsedRequest.payload.timestamp,
          payloadHash: parsedRequest.payloadHash,
          source: parsedRequest.payload.source,
          payload: parsedRequest.payload
        }

        await appendWebhookEvent({
          dataRoot: options.dataRoot,
          growerSlug: options.growerSlug,
          event
        })
        await markSyncNeededCheckpoint({
          dataRoot: options.dataRoot,
          growerSlug: options.growerSlug,
          event
        })

        writeJson(response, 200, {
          status: 'accepted',
          growerSlug: options.growerSlug,
          eventType: event.eventType,
          payloadHash: event.payloadHash
        })
      } catch (error) {
        const statusCode = error instanceof TypeError ? 400 : 500
        writeJson(response, statusCode, {
          status: 'error',
          message: error instanceof Error ? error.message : 'Unknown webhook processing error.'
        })
      }

      return
    }

    writeJson(response, 404, {
      status: 'not-found'
    })
  })

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, host, () => {
      server.off('error', reject)
      resolve()
    })
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    await closeServer(server)
    throw new Error('Webhook server failed to resolve a TCP address.')
  }

  return {
    host,
    port: address.port,
    url: `http://${host}:${address.port}`,
    eventsFile,
    close: () => closeServer(server)
  }
}

export async function runWebhookServer(
  options: StartWebhookServerOptions & {
    shutdownSignal?: AbortSignal
    onStarted?: (server: StartedWebhookServer) => void | Promise<void>
  }
): Promise<StartedWebhookServer> {
  const startedServer = await startWebhookServer(options)

  try {
    await options.onStarted?.(startedServer)
    await waitForSigint(options.shutdownSignal)
    return startedServer
  } finally {
    await startedServer.close()
  }
}
