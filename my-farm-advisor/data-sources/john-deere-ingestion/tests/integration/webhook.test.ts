import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Writable } from 'node:stream';

import { afterEach, describe, expect, it } from 'vitest';

import { runCli } from '../../src/cli.js';

import { readJsonFixture, readJsonLines } from './helpers.js';

describe('webhook CLI integration', () => {
  const tempRoots: string[] = [];

  afterEach(async () => {
    await Promise.all(tempRoots.map(async (tempRoot) => rm(tempRoot, { recursive: true, force: true })));
    tempRoots.length = 0;
  });

  it('starts a local webhook receiver and appends received events to JSONL', async () => {
    const tempRoot = await mkdtemp(path.join(tmpdir(), 'jd-webhook-cli-'));
    tempRoots.push(tempRoot);

    const webhookEvent = await readJsonFixture<Record<string, unknown>>('webhook-events.json');
    const controller = new AbortController();

    let resolveReady: (() => void) | undefined;
    const ready = new Promise<void>((resolve) => {
      resolveReady = resolve;
    });
    const outputChunks: string[] = [];
    const stdout = new Writable({
      write(chunk, _encoding, callback) {
        const text = chunk.toString();
        outputChunks.push(text);

        if (text.includes('Listening for John Deere webhook events.')) {
          resolveReady?.();
        }

        callback();
      }
    });

    const runPromise = runCli(['webhook', '--port', '0'], {
      cwd: '/workspace/project',
      env: {
        JD_DATA_ROOT: tempRoot,
        JD_GROWER: 'iowa-demo-grower'
      },
      stdout,
      shutdownSignal: controller.signal,
      now: () => new Date('2026-05-02T12:00:00.000Z')
    });

    await ready;

    const startupOutput = outputChunks.join('');
    const urlMatch = startupOutput.match(/url: (http:\/\/127\.0\.0\.1:\d+)/);
    const eventsFileMatch = startupOutput.match(/eventsFile: (.+)/);

    expect(urlMatch).not.toBeNull();
    expect(eventsFileMatch).not.toBeNull();

    const response = await fetch(`${urlMatch?.[1]}/webhook`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      body: JSON.stringify(webhookEvent)
    });

    expect(response.status).toBe(200);
    controller.abort();

    const result = await runPromise;
    expect(result.exitCode).toBe(0);
    expect(result.output).toBe('');

    const finalOutput = outputChunks.join('');
    expect(finalOutput).toContain('Webhook server stopped gracefully.');

    const eventsFilePath = eventsFileMatch?.[1].trim() ?? '';
    const loggedEvents = await readJsonLines<Record<string, unknown>>(eventsFilePath);
    expect(loggedEvents).toHaveLength(1);
    expect(loggedEvents[0]).toMatchObject({
      growerSlug: 'iowa-demo-grower',
      eventType: 'field.updated',
      timestamp: '2026-05-01T10:30:00.000Z',
      source: expect.objectContaining({
        resourceId: 'field-101'
      }),
      payload: webhookEvent
    });
  });
});
