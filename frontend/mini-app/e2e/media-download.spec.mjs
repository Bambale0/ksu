import { expect, test as base } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:https';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ASSET_ID = '11111111-1111-4111-8111-111111111111';
const GENERATION_ID = '22222222-2222-4222-8222-222222222222';
const OTHER_ID = '33333333-3333-4333-8333-333333333333';
const FILE_NAME = 'generation-' + GENERATION_ID + '-1.png';
const MEDIA_PATH = '/api/v1/media/' + ASSET_ID + '/signed/4102444800/test-signature';
const CONTENTS = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvLkAAAAASUVORK5CYII=', 'base64');

// WebKit cannot complete routed attachment downloads. Use real HTTPS transport;
// only the owner-authenticated descriptor API is intercepted by Playwright.
const test = base.extend({
  attachment: async ({}, use) => {
    const directory = await mkdtemp(join(tmpdir(), 'ksu-download-e2e-'));
    let server;
    // The retained descriptor starts valid on the controlled server clock.
    // Advancing to wall time makes its actual expires value fall in the past.
    const oldExpires = Math.floor(Date.now() / 1000) - 1;
    const oldPath = '/api/v1/media/' + ASSET_ID + '/signed/' + oldExpires + '/test-signature';
    let clockSeconds = oldExpires - 1;
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
        const record = { url, headers: { ...request.headers }, method: request.method, status: 200 };
        requests.push(record);
        const expires = Number(parsed.pathname.split('/')[6]);
        if (![MEDIA_PATH, oldPath].includes(parsed.pathname) || expires < clockSeconds) {
          record.status = 404;
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
      const origin = 'https://127.0.0.1:' + server.address().port;
      await use({
        url: origin + MEDIA_PATH + '?download=1',
        oldUrl: origin + oldPath + '?download=1',
        requests,
        expireOld() { clockSeconds = Math.floor(Date.now() / 1000); },
      });
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

test.use({ ignoreHTTPSErrors: true, acceptDownloads: true });

function downloadAction(page, name = /^Скачать/) {
  // The old anchor remains selectable for the pre-fix expiry reproduction.
  return page.getByRole('button', { name }).or(page.getByRole('link', { name }));
}

async function setup(page, attachment, {
  native = false, throws = false, accepted = true, stale = false,
  metadataReady, metadataDelayMs = 0, descriptorResponse, extraMedia = false,
} = {}) {
  const nativeCalls = [];
  await page.exposeFunction('__recordNativeDownload', (params) => nativeCalls.push(params));
  await page.addInitScript(({ native, throws, accepted }) => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    window.downloadCalls = [];
    window.descriptorFetches = [];
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      if (/^\/api\/v1\/media\/[^/]+$/.test(url.pathname)) {
        window.descriptorFetches.push({ path: url.pathname, cache: init?.cache });
      }
      return originalFetch(input, init);
    };
    window.Telegram = { WebApp: {
      initData: 'synthetic-download-initdata',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      isVersionAtLeast(version) { return native && version === '8.0'; },
      downloadFile(params, callback) {
        window.downloadCalls.push(params);
        void window.__recordNativeDownload(params);
        if (throws) throw new Error('Native client rejected the request');
        callback?.(accepted);
      },
    } };
  }, { native, throws, accepted });
  const descriptorRequests = [];
  let visible = true;
  let listRequests = 0;
  const descriptor = {
    id: ASSET_ID, generation_id: GENERATION_ID, status: 'ready',
    download_url: attachment.url, download_filename: FILE_NAME,
    content_type: 'image/png', size_bytes: CONTENTS.length, ordinal: 0,
  };
  await page.route('http://127.0.0.1:*/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ telegram_id: 777, first_name: 'QA', balance_rox: '0' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/media/' + ASSET_ID) {
      descriptorRequests.push(request);
      expect(request.method()).toBe('GET');
      expect(request.headers()['x-telegram-init-data']).toBe('synthetic-download-initdata');
      await metadataReady;
      if (metadataDelayMs) await new Promise((resolve) => setTimeout(resolve, metadataDelayMs));
      const reply = descriptorResponse?.(descriptorRequests.length, descriptor) || { body: descriptor };
      return json(reply.body, reply.status || 200);
    }
    if (path === '/api/v1/generations') {
      listRequests++;
      expect(request.headers()['x-telegram-init-data']).toBe('synthetic-download-initdata');
      const selected = {
        id: ASSET_ID, url: attachment.url.replace('?download=1', ''),
        download_url: stale ? attachment.oldUrl : attachment.url, download_filename: FILE_NAME,
        content_type: 'image/png', size_bytes: CONTENTS.length, ordinal: 0,
      };
      return json({ items: visible ? [{
        id: GENERATION_ID, status: 'succeeded', created_at: '2026-11-06T01:00:00Z',
        model: { title: 'Synthetic image' },
        media_delivery: { state: 'ready', ready: extraMedia ? 2 : 1, expected: extraMedia ? 2 : 1 },
        media: extraMedia ? [{ ...selected, id: OTHER_ID, ordinal: 1 }, selected] : [selected],
      }] : [] });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/downloads/');
  await expect(downloadAction(page).first()).toBeVisible();
  if (stale) attachment.expireOld();
  return {
    descriptorRequests, nativeCalls,
    hideItems() { visible = false; },
    listRequests: () => listRequests,
  };
}

async function expectFreshRequest(page, api, count = 1) {
  expect(api.descriptorRequests).toHaveLength(count);
  expect(await page.evaluate(() => window.descriptorFetches)).toEqual(
    Array.from({ length: count }, () => ({ path: '/api/v1/media/' + ASSET_ID, cache: 'no-store' })),
  );
}

async function expectAttachment(page, attachment, action = () => downloadAction(page).click()) {
  const completed = page.waitForEvent('download', { timeout: 15000 });
  // Keep rejection observed if the pre-fix expired URL navigates to a 404.
  void completed.catch(() => {});
  await action();
  const download = await completed;
  expect(await download.failure()).toBeNull();
  expect(download.url()).toBe(attachment.url);
  expect(download.suggestedFilename()).toBe(FILE_NAME);
  expect(await readFile(await download.path())).toEqual(CONTENTS);
  expect(attachment.requests).toHaveLength(1);
  expect(attachment.requests[0].url).toBe(attachment.url);
  expect(attachment.requests[0].status).toBe(200);
  expect(attachment.requests[0].method).toBe('GET');
  expect(attachment.requests[0].headers['x-telegram-init-data']).toBeUndefined();
  await expect(page).toHaveURL(/\/mini-app\/downloads\/$/);
}

test('supported Telegram clients request a native download of the fresh signed attachment', async ({ page, attachment }) => {
  const api = await setup(page, attachment, { native: true });
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls).toEqual([{ url: attachment.url, file_name: FILE_NAME }]);
  await expectFreshRequest(page, api);
  expect(attachment.requests).toEqual([]);
});

for (const scenario of [
  { name: 'older Telegram client', native: false, throws: false },
  { name: 'native API error', native: true, throws: true },
]) {
  test(scenario.name + ' downloads actual bytes after delayed fresh metadata', async ({ page, attachment }) => {
    // Deliberate server latency exceeds the original click's transient activation.
    const api = await setup(page, attachment, { ...scenario, metadataDelayMs: 6000 });
    await expectAttachment(page, attachment);
    await expectFreshRequest(page, api);
    expect(api.nativeCalls).toEqual(scenario.native ? [{ url: attachment.url, file_name: FILE_NAME }] : []);
  });
}

test('declining the native download does not force a browser download', async ({ page, attachment }) => {
  const api = await setup(page, attachment, { native: true, accepted: false });
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls).toEqual([{ url: attachment.url, file_name: FILE_NAME }]);
  await expectFreshRequest(page, api);
  expect(attachment.requests).toEqual([]);
});

test('expired saved descriptor is renewed before the native download', async ({ page, attachment }) => {
  const api = await setup(page, attachment, { native: true, stale: true });
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls).toEqual([{ url: attachment.url, file_name: FILE_NAME }]);
  await expectFreshRequest(page, api);
  expect(attachment.requests).toEqual([]);
});

test('expired saved descriptor is renewed before an actual browser download', async ({ page, attachment }) => {
  const api = await setup(page, attachment, { stale: true });
  try {
    await expectAttachment(page, attachment);
  } finally {
    // Preserve exact old-URL/404 evidence when reproducing the pre-fix failure.
    await test.info().attach('attachment-requests', {
      body: JSON.stringify(attachment.requests.map(({ url, status }) => ({ url, status }))),
      contentType: 'application/json',
    });
  }
  await expectFreshRequest(page, api);
});

for (const status of [403, 404, 503]) {
  test('descriptor HTTP ' + status + ' cannot use the saved download URL', async ({ page, attachment }) => {
    const api = await setup(page, attachment, {
      native: true, stale: true,
      descriptorResponse: () => ({ status, body: { detail: 'Descriptor unavailable' } }),
    });
    await downloadAction(page).click();
    await expect(page.locator('.transaction-list').getByRole('alert')).toContainText('Попробуйте');
    await expect(downloadAction(page)).toBeEnabled();
    await expectFreshRequest(page, api);
    expect(api.nativeCalls).toEqual([]);
    expect(attachment.requests).toEqual([]);
  });
}

for (const scenario of [
  { name: 'missing URL', patch: { download_url: null } },
  { name: 'different asset', patch: { id: OTHER_ID } },
  { name: 'different generation', patch: { generation_id: OTHER_ID } },
  { name: 'unready media', patch: { status: 'pending' } },
  { name: 'javascript URL', patch: { download_url: 'javascript:window.__badDownload=true' } },
  { name: 'data URL', patch: { download_url: 'data:text/html,unsafe-download' } },
]) {
  test('invalid descriptor ' + scenario.name + ' cannot use the saved URL', async ({ page, attachment }) => {
    const api = await setup(page, attachment, {
      native: true, stale: true,
      descriptorResponse: (_count, descriptor) => ({ body: { ...descriptor, ...scenario.patch } }),
    });
    await downloadAction(page).click();
    await expect(page.locator('.transaction-list').getByRole('alert')).toContainText('Попробуйте');
    await expectFreshRequest(page, api);
    expect(api.nativeCalls).toEqual([]);
    expect(attachment.requests).toEqual([]);
    expect(await page.evaluate(() => window.__badDownload)).toBeUndefined();
  });
}

test('descriptor failure preserves a retryable action without reusing the expired URL', async ({ page, attachment }) => {
  const api = await setup(page, attachment, {
    native: true, stale: true,
    descriptorResponse: (count, descriptor) => count === 1
      ? { status: 503, body: { detail: 'Temporary unavailable' } }
      : { body: descriptor },
  });
  await downloadAction(page).click();
  await expect(page.locator('.transaction-list').getByRole('alert')).toContainText('Попробуйте');
  expect(api.nativeCalls).toEqual([]);
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls).toEqual([{ url: attachment.url, file_name: FILE_NAME }]);
  await expect(page.locator('.transaction-list').getByRole('alert')).toHaveCount(0);
  await expectFreshRequest(page, api, 2);
  expect(attachment.requests).toEqual([]);
});

test('every download request refreshes its capability including a second click', async ({ page, attachment }) => {
  const api = await setup(page, attachment, {
    native: true,
    descriptorResponse: (count, descriptor) => ({
      body: { ...descriptor, download_url: attachment.url + '&issued=' + count },
    }),
  });
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls.length).toBe(1);
  await downloadAction(page).click();
  await expect.poll(() => api.nativeCalls).toEqual([
    { url: attachment.url + '&issued=1', file_name: FILE_NAME },
    { url: attachment.url + '&issued=2', file_name: FILE_NAME },
  ]);
  await expectFreshRequest(page, api, 2);
  await expect(page.getByRole('link', { name: /^Скачать/ })).toHaveCount(0);
});

test('the selected asset is refreshed by identity even when it is not first', async ({ page, attachment }) => {
  const api = await setup(page, attachment, { native: true, stale: true, extraMedia: true });
  await downloadAction(page, /^Скачать 2/).click();
  await expect.poll(() => api.nativeCalls).toEqual([{ url: attachment.url, file_name: FILE_NAME }]);
  await expectFreshRequest(page, api);
});

test('rapid duplicate clicks share one in-flight descriptor request', async ({ page, attachment }) => {
  let release;
  const metadataReady = new Promise((resolve) => { release = resolve; });
  const api = await setup(page, attachment, { native: true, stale: true, metadataReady });
  try {
    await downloadAction(page).evaluate((element) => { element.click(); element.click(); });
    await expect.poll(() => api.descriptorRequests.length).toBe(1);
    await expect(downloadAction(page)).toBeDisabled();
    expect(api.nativeCalls).toEqual([]);
  } finally {
    release();
  }
  await expect.poll(() => api.nativeCalls.length).toBe(1);
  await expect(downloadAction(page)).toBeEnabled();
  await expectFreshRequest(page, api);
});

test('removing an asset during descriptor refresh aborts without a late download', async ({ page, attachment }) => {
  let release;
  const metadataReady = new Promise((resolve) => { release = resolve; });
  const api = await setup(page, attachment, { native: true, stale: true, metadataReady });
  try {
    await downloadAction(page).click();
    await expect.poll(() => api.descriptorRequests.length).toBe(1);
    api.hideItems();
    const aborted = page.waitForEvent('requestfailed', {
      predicate: (request) => new URL(request.url()).pathname === '/api/v1/media/' + ASSET_ID,
    });
    await page.getByRole('button', { name: 'Обновить', exact: true }).click();
    await expect(downloadAction(page)).toHaveCount(0);
    await aborted;
  } finally {
    release();
  }
  expect(api.nativeCalls).toEqual([]);
  expect(attachment.requests).toEqual([]);
});
