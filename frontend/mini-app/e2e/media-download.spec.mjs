import { expect, test as base } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:https';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ASSET_ID = '11111111-1111-4111-8111-111111111111';
const GENERATION_ID = '22222222-2222-4222-8222-222222222222';
const FILE_NAME = 'generation-' + GENERATION_ID + '-1.png';
const MEDIA_PATH = '/api/v1/media/' + ASSET_ID + '/signed/4102444800/test-signature';
const CONTENTS = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvLkAAAAASUVORK5CYII=', 'base64');

// WebKit cannot complete routed attachment downloads. A real HTTPS transport
// also exercises the native helper's HTTPS gate before its error fallback.
const test = base.extend({
  attachment: async ({}, use) => {
    const directory = await mkdtemp(join(tmpdir(), 'ksu-download-e2e-'));
    let server;
    try {
      const key = join(directory, 'key.pem');
      const cert = join(directory, 'cert.pem');
      execFileSync('openssl', [
        'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-keyout', key, '-out', cert, '-subj', '/CN=localhost',
        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
      ], { stdio: 'ignore' });
      const requests = [];
      server = createServer({ key: await readFile(key), cert: await readFile(cert) }, (request, response) => {
        const url = 'https://' + request.headers.host + request.url;
        const parsed = new URL(url);
        requests.push({ url, headers: { ...request.headers }, method: request.method });
        if (parsed.pathname !== MEDIA_PATH) {
          response.writeHead(404);
          response.end();
          return;
        }
        const download = parsed.searchParams.get('download') === '1';
        response.writeHead(200, {
          'content-type': download ? 'application/octet-stream' : 'image/png',
          'content-length': CONTENTS.length,
          ...(download ? {
            'content-disposition': 'attachment; filename="' + FILE_NAME + '"',
            'access-control-allow-origin': 'https://web.telegram.org',
          } : {}),
        });
        response.end(CONTENTS);
      });
      await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(0, '127.0.0.1', resolve);
      });
      const url = 'https://127.0.0.1:' + server.address().port + MEDIA_PATH + '?download=1';
      await use({ url, requests });
    } finally {
      if (server?.listening) {
        const closed = new Promise((resolve) => server.close(resolve));
        server.closeAllConnections();
        await closed;
      }
      await rm(directory, { recursive: true, force: true });
    }
  },
});

// The certificate is generated only for this isolated loopback test server.
test.use({ ignoreHTTPSErrors: true, acceptDownloads: true });

async function setup(page, attachment, { native = false, throws = false, accepted = true } = {}) {
  await page.addInitScript(({ native, throws, accepted }) => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    window.downloadCalls = [];
    window.Telegram = { WebApp: {
      initData: 'synthetic-download-initdata',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      isVersionAtLeast(version) { return native && version === '8.0'; },
      downloadFile(params, callback) {
        window.downloadCalls.push(params);
        if (throws) throw new Error('Native client rejected the request');
        callback?.(accepted);
      },
    } };
  }, { native, throws, accepted });
  await page.route('http://127.0.0.1:*/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ telegram_id: 777, first_name: 'QA', balance_rox: '0' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') {
      expect(route.request().headers()['x-telegram-init-data']).toBe('synthetic-download-initdata');
      return json({ items: [{
        id: GENERATION_ID, status: 'succeeded', created_at: '2026-11-06T01:00:00Z',
        model: { title: 'Synthetic image' },
        media_delivery: { state: 'ready', ready: 1, expected: 1 },
        media: [{
          id: ASSET_ID, url: attachment.url.replace('?download=1', ''),
          download_url: attachment.url, download_filename: FILE_NAME,
          content_type: 'image/png', size_bytes: CONTENTS.length, ordinal: 0,
        }],
      }] });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/downloads/');
  await expect(page.getByRole('link', { name: /Скачать/ })).toBeVisible();
}

test('supported Telegram clients request a native download of the signed attachment', async ({ page, attachment }) => {
  await setup(page, attachment, { native: true });
  await page.getByRole('link', { name: /Скачать/ }).click();
  await expect.poll(() => page.evaluate(() => window.downloadCalls)).toEqual([{
    url: attachment.url, file_name: FILE_NAME,
  }]);
  expect(attachment.requests).toEqual([]);
});

for (const scenario of [
  { name: 'older Telegram client', native: false, throws: false },
  { name: 'native API error', native: true, throws: true },
]) {
  test(scenario.name + ' falls back to a completed browser attachment download', async ({ page, attachment }) => {
    await setup(page, attachment, scenario);
    const completed = page.waitForEvent('download');
    await page.getByRole('link', { name: /Скачать/ }).click();
    const download = await completed;
    expect(await download.failure()).toBeNull();
    expect(download.url()).toBe(attachment.url);
    expect(download.suggestedFilename()).toBe(FILE_NAME);
    expect(await readFile(await download.path())).toEqual(CONTENTS);
    expect(attachment.requests).toHaveLength(1);
    expect(attachment.requests[0].url).toBe(attachment.url);
    expect(attachment.requests[0].method).toBe('GET');
    expect(attachment.requests[0].headers['x-telegram-init-data']).toBeUndefined();
    expect(await page.evaluate(() => window.downloadCalls)).toEqual(scenario.native ? [{
      url: attachment.url, file_name: FILE_NAME,
    }] : []);
  });
}

test('declining the native download does not force a browser download', async ({ page, attachment }) => {
  await setup(page, attachment, { native: true, accepted: false });
  await page.getByRole('link', { name: /Скачать/ }).click();
  await expect.poll(() => page.evaluate(() => window.downloadCalls)).toEqual([{
    url: attachment.url, file_name: FILE_NAME,
  }]);
  expect(attachment.requests).toEqual([]);
});
