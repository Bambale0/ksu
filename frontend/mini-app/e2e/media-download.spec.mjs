import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const ASSET_ID = '11111111-1111-4111-8111-111111111111';
const GENERATION_ID = '22222222-2222-4222-8222-222222222222';
const FILE_NAME = `generation-${GENERATION_ID}-1.png`;
const DOWNLOAD_URL = `https://roxy.test/api/v1/media/${ASSET_ID}/signed/4102444800/test-signature?download=1`;
const CONTENTS = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jvLkAAAAASUVORK5CYII=', 'base64');

async function setup(page, { native = false, throws = false, accepted = true } = {}) {
  const requests = [];
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
  await page.context().route('https://roxy.test/api/v1/media/**', async (route) => {
    requests.push(route.request());
    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      headers: {
        'content-disposition': `attachment; filename="${FILE_NAME}"`,
        'access-control-allow-origin': 'https://web.telegram.org',
      },
      body: CONTENTS,
    });
  });
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
          id: ASSET_ID, url: DOWNLOAD_URL.replace('?download=1', ''),
          download_url: DOWNLOAD_URL, download_filename: FILE_NAME,
          content_type: 'image/png', size_bytes: CONTENTS.length, ordinal: 0,
        }],
      }] });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/downloads/');
  await expect(page.getByRole('link', { name: /Скачать/ })).toBeVisible();
  return requests;
}

test('supported Telegram clients request a native download of the signed attachment', async ({ page }) => {
  const requests = await setup(page, { native: true });
  await page.getByRole('link', { name: /Скачать/ }).click();
  await expect.poll(() => page.evaluate(() => window.downloadCalls)).toEqual([{
    url: DOWNLOAD_URL, file_name: FILE_NAME,
  }]);
  expect(requests).toEqual([]);
});

for (const scenario of [
  { name: 'older Telegram client', native: false, throws: false },
  { name: 'native API error', native: true, throws: true },
]) {
  test(`${scenario.name} falls back to a completed browser attachment download`, async ({ page }) => {
    const requests = await setup(page, scenario);
    const completed = page.waitForEvent('download');
    await page.getByRole('link', { name: /Скачать/ }).click();
    const download = await completed;
    expect(await download.failure()).toBeNull();
    expect(download.suggestedFilename()).toBe(FILE_NAME);
    expect(await readFile(await download.path())).toEqual(CONTENTS);
    expect(requests).toHaveLength(1);
    expect(requests[0].url()).toBe(DOWNLOAD_URL);
    expect(requests[0].headers()['x-telegram-init-data']).toBeUndefined();
  });
}

test('declining the native download does not force a browser download', async ({ page }) => {
  const requests = await setup(page, { native: true, accepted: false });
  await page.getByRole('link', { name: /Скачать/ }).click();
  await expect.poll(() => page.evaluate(() => window.downloadCalls.length)).toBe(1);
  expect(requests).toEqual([]);
});
