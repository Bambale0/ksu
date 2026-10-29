import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

const mediaOrigin = 'https://trend-preview.example.invalid';
const uploadedUrl = `${mediaOrigin}/uploaded-preview.png`;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64');
const previewFile = { name: 'trend-preview.png', mimeType: 'image/png', buffer: png };
// Bundled Chromium uses VP8; WebKit exercises the same portrait clip as H.264.
const videoFixtures = {
  chromium: {
    extension: 'webm', contentType: 'video/webm',
    body: readFileSync(new URL('../../../tests/fixtures/trend-preview-portrait.webm', import.meta.url)),
  },
  webkit: {
    extension: 'mp4', contentType: 'video/mp4',
    body: readFileSync(new URL('../../../tests/fixtures/trend-preview-portrait.mp4', import.meta.url)),
  },
};

function fulfillVideo(route, { body, contentType }) {
  const headers = { 'accept-ranges': 'bytes' };
  const range = route.request().headers().range;
  if (!range) return route.fulfill({ status: 200, contentType, headers, body });
  const match = /^bytes=(\d*)-(\d*)$/.exec(range);
  const from = match?.[1] ? Number(match[1]) : Math.max(0, body.length - Number(match?.[2]));
  const to = match?.[1] && match[2] ? Math.min(Number(match[2]), body.length - 1) : body.length - 1;
  if (!match || (!match[1] && !match[2]) || !Number.isSafeInteger(from) || !Number.isSafeInteger(to)
    || from >= body.length || to < from) {
    return route.fulfill({ status: 416, headers: { ...headers, 'content-range': `bytes */${body.length}` }, body: '' });
  }
  return route.fulfill({
    status: 206, contentType,
    headers: { ...headers, 'content-range': `bytes ${from}-${to}/${body.length}` },
    body: body.subarray(from, to + 1),
  });
}

const model = {
  id: 'video-catalog-model', title: 'Видео из каталога', family: 'video',
  media_type: 'video', operation: 'text_to_video', price_rox: '10.00',
  known_fields: ['prompt', 'duration'], required_fields: ['prompt', 'duration'],
  ui_schema: { groups: [], fields: [], defaults: { duration: 5 } },
};

function videoTrends(count, previewUrl) {
  return Array.from({ length: count }, (_, index) => ({
    id: `mobile-trend-${index}`,
    title: `Мобильный тренд ${index + 1}`,
    is_active: true,
    payload: {
      media_type: 'video', model_id: model.id, preview_url: previewUrl(index),
      prompt: `Сценарий ${index + 1}`, description: `Описание ${index + 1}`,
      input_mode: 'none', min_references: 0, max_references: 0,
      parameters: { duration: 5 }, tags: ['trend'], sort_order: index,
    },
  }));
}

async function setup(page, browserName, { count = 3, listMode = 'success' } = {}) {
  const videoFixture = videoFixtures[browserName];
  if (!videoFixture) throw new Error(`No portrait media fixture for ${browserName}`);
  const previewUrl = (index) => `${mediaOrigin}/admin-preview-${index}.${videoFixture.extension}`;
  const state = {
    items: videoTrends(count, previewUrl), previewUrl, listMode, listRequests: 0, pendingLists: [],
    mediaRequests: new Set(), uploads: 0, uploadStatus: 201,
    unexpectedWrites: [], errors: [],
  };
  page.on('pageerror', (error) => state.errors.push(error.message));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=mobile-trend-admin&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'Admin' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });

  // Every API and external resource is intercepted. In particular the real SDK
  // must not overwrite the synthetic Telegram session on a production build.
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.hostname === 'telegram.org' && path === '/js/telegram-web-app.js') {
      return route.fulfill({ contentType: 'application/javascript', body: '' });
    }
    if (url.origin === mediaOrigin) {
      const video = /^\/admin-preview-(\d+)\.(mp4|webm)$/.exec(path);
      if (video) {
        state.mediaRequests.add(Number(video[1]));
        // A real tiny video exercises metadata/layout and Safari byte ranges.
        // Resource activation is the oracle, not a simulated iPhone crash.
        return fulfillVideo(route, videoFixture);
      }
      return route.fulfill({ status: 200, contentType: 'image/png', body: png });
    }
    if (path.startsWith('/api/v1/')) {
      if (path === '/api/v1/me') return json({
        id: 'mobile-admin', telegram_id: 777, first_name: 'Admin',
        is_admin: true, balance_rox: '1000.00',
      });
      if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
      if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
      if (path === '/api/v1/trends/manage' && request.method() === 'GET') {
        state.listRequests += 1;
        if (state.listMode === 'pending') {
          state.pendingLists.push(route);
          return;
        }
        if (state.listMode === 'failure') return json({ detail: 'Не удалось получить список трендов' }, 503);
        return json({ items: state.items, models: [model] });
      }
      if (path === '/api/v1/uploads/kie') {
        state.uploads += 1;
        expect(request.method()).toBe('POST');
        expect(request.postDataBuffer().toString()).toContain('filename="trend-preview.png"');
        if (state.uploadStatus !== 201) return json({ detail: 'Не удалось загрузить превью' }, state.uploadStatus);
        return json({ url: uploadedUrl, mime_type: 'image/png', reference: { id: 'preview-1', kind: 'image' } }, 201);
      }
      if (request.method() !== 'GET') {
        state.unexpectedWrites.push(`${request.method()} ${path}`);
        return json({ detail: 'Unexpected mutation in touch-only regression' }, 400);
      }
      return json({ items: [], has_more: false, next_before: null });
    }
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort();
    return route.continue();
  });
  await page.goto('/mini-app/?route=home');
  await expect(page.getByRole('button', { name: 'Управлять трендами', exact: true })).toBeVisible();
  return state;
}

async function openManager(page) {
  await page.getByRole('button', { name: 'Управлять трендами', exact: true }).tap();
  const manager = page.getByRole('dialog', { name: 'Управление трендами', exact: true });
  await expect(manager).toBeVisible();
  return manager;
}

async function openCreate(page, manager) {
  await manager.getByRole('button', { name: '＋ Новый тренд', exact: true }).tap();
  const form = page.getByRole('dialog', { name: 'Добавить тренд', exact: true });
  await expect(form).toBeVisible();
  return form;
}

async function choosePreview(page, form) {
  const chooser = page.waitForEvent('filechooser');
  await form.getByLabel('Загрузить превью', { exact: true }).tap();
  await (await chooser).setFiles(previewFile);
}

function expectClean(state) {
  expect(state.errors).toEqual([]);
  expect(state.unexpectedWrites).toEqual([]);
}

async function reportMediaState(video, phase) {
  const state = await video.evaluate((element) => ({
    src: element.getAttribute('src'), currentSrc: element.currentSrc, paused: element.paused,
    readyState: element.readyState, networkState: element.networkState,
    bufferedLength: element.buffered.length, videoWidth: element.videoWidth, videoHeight: element.videoHeight,
    isConnected: element.isConnected,
    error: element.error ? { code: element.error.code, message: element.error.message } : null,
    canPlayType: {
      h264: element.canPlayType('video/mp4; codecs="avc1.42E01E"'),
      vp8: element.canPlayType('video/webm; codecs="vp8"'),
    },
  })).catch((error) => ({ diagnosticError: String(error) }));
  console.error(`[trend-admin-media:${phase}] ${JSON.stringify(state)}`);
}

async function expectVideoMetadata(video) {
  try {
    await expect.poll(() => video.evaluate((element) => element.videoWidth)).toBeGreaterThan(0);
    const metadata = await video.evaluate((element) => ({
      width: element.videoWidth, height: element.videoHeight, error: element.error?.code ?? null,
    }));
    // Portrait dimensions expose layout shifts concealed by a square fixture.
    expect(metadata.height).toBeGreaterThan(metadata.width);
    expect(metadata.error).toBeNull();
  } catch (error) {
    await reportMediaState(video, 'metadata');
    throw error;
  }
}

test('a large video list stays usable by touch without activating far-offscreen media', async ({ page, browserName }) => {
  const state = await setup(page, browserName, { count: 300 });
  state.items = state.items.map((item) => ({ ...item, payload: { ...item.payload, description: '' } }));
  const manager = await openManager(page);
  const cards = manager.locator('.inline-trend-admin-card');
  await expect(cards).toHaveCount(300);
  await expect.poll(() => state.mediaRequests.has(0)).toBe(true);
  const firstCard = cards.first();
  const firstVideo = firstCard.locator('video');
  await expectVideoMetadata(firstVideo);
  const firstCardHeight = await firstCard.evaluate((element) => element.getBoundingClientRect().height);
  const panel = manager.locator('.inline-trend-admin-panel');
  const scrollHeight = await panel.evaluate((element) => element.scrollHeight);

  // Baseline assigns src to all 300 auto-playing videos. Check both browser
  // requests and the dormant far-offscreen sources, without timing a freeze.
  await expect(cards.last().locator('video')).not.toHaveAttribute('src', /.+/);
  const activatedTail = await cards.evaluateAll((elements) => elements.slice(-25)
    .filter((element) => Boolean(element.querySelector('video')?.getAttribute('src'))).length);
  expect(activatedTail).toBe(0);
  expect([...state.mediaRequests].filter((index) => index >= 275)).toEqual([]);

  const lastCard = cards.last();
  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).scrollIntoViewIfNeeded();
  const lastVideo = lastCard.locator('video');
  await expect(lastVideo).toHaveAttribute('src', state.previewUrl(299));
  await expect.poll(() => state.mediaRequests.has(299)).toBe(true);
  await expectVideoMetadata(lastVideo);
  // Removing the attribute alone does not unload an already selected resource.
  try {
    await expect.poll(() => firstVideo.evaluate((element) => ({
      currentSrc: element.currentSrc, paused: element.paused,
    }))).toEqual({ currentSrc: '', paused: true });
  } catch (error) {
    await reportMediaState(firstVideo, 'offscreen-cleanup');
    throw error;
  }
  await expect.poll(async () => Math.abs((await firstCard.evaluate((element) => element.getBoundingClientRect().height)) - firstCardHeight)).toBeLessThan(1);
  await expect.poll(() => panel.evaluate((element) => element.scrollHeight)).toBe(scrollHeight);
  const preview = lastCard.locator('.inline-trend-admin-preview');
  const previewHeight = await preview.evaluate((element) => element.getBoundingClientRect().height);
  expect(previewHeight).toBeGreaterThan(0);
  const scrollTop = await panel.evaluate((element) => element.scrollTop);
  expect(scrollTop).toBeGreaterThan(0);

  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).tap();
  const form = page.getByRole('dialog', { name: 'Редактировать тренд', exact: true });
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('Мобильный тренд 300');
  await expect(manager.locator('video[src]')).toHaveCount(0);
  // The covered list must keep its geometry while its media is absent, not
  // merely recover its dimensions after the editor is dismissed.
  await expect.poll(async () => Math.abs((await preview.evaluate((element) => element.getBoundingClientRect().height)) - previewHeight)).toBeLessThan(1);
  await expect.poll(() => panel.evaluate((element) => element.scrollHeight)).toBe(scrollHeight);
  await expect.poll(async () => Math.abs((await panel.evaluate((element) => element.scrollTop)) - scrollTop)).toBeLessThan(2);
  await form.getByLabel('Название', { exact: true }).fill('Проверка последней карточки');
  await form.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(form).toHaveCount(0);
  await expect(lastVideo).toHaveAttribute('src', state.previewUrl(299));
  await expectVideoMetadata(lastVideo);
  await expect.poll(async () => Math.abs((await preview.evaluate((element) => element.getBoundingClientRect().height)) - previewHeight)).toBeLessThan(1);
  await expect.poll(() => panel.evaluate((element) => element.scrollHeight)).toBe(scrollHeight);
  await expect.poll(async () => Math.abs((await panel.evaluate((element) => element.scrollTop)) - scrollTop)).toBeLessThan(2);
  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).tap();
  await expect(page.getByRole('dialog', { name: 'Редактировать тренд', exact: true })
    .getByLabel('Название', { exact: true })).toHaveValue('Мобильный тренд 300');
  expectClean(state);
});

test('refreshing one card loads the changed video and closing releases its media', async ({ page, browserName }) => {
  const state = await setup(page, browserName);
  const manager = await openManager(page);
  const video = manager.locator('.inline-trend-admin-card').first().locator('video');
  await expect(video).toHaveAttribute('src', state.previewUrl(0));
  await expectVideoMetadata(video);
  const replacementUrl = state.previewUrl(300);
  state.items = state.items.map((item, index) => index === 0
    ? { ...item, payload: { ...item.payload, preview_url: replacementUrl } }
    : item);
  await manager.getByRole('button', { name: 'Обновить', exact: true }).tap();
  await expect(video).toHaveAttribute('src', replacementUrl);
  await expect.poll(() => state.mediaRequests.has(300)).toBe(true);
  await expect.poll(() => video.evaluate((element) => ({
    currentSrc: element.currentSrc,
    hasMetadata: element.readyState >= HTMLMediaElement.HAVE_METADATA,
  }))).toEqual({ currentSrc: replacementUrl, hasMetadata: true });
  await expectVideoMetadata(video);

  // Retain the node handle so disappearance from the DOM cannot masquerade as
  // releasing the selected media resource. No media method is mocked or forced.
  const retiredVideo = await video.elementHandle();
  expect(retiredVideo).not.toBeNull();
  try {
    await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
    await expect(manager).toHaveCount(0);
    try {
      await expect.poll(() => retiredVideo.evaluate((element) => ({
        connected: element.isConnected, currentSrc: element.currentSrc, paused: element.paused,
      }))).toEqual({ connected: false, currentSrc: '', paused: true });
    } catch (error) {
      await reportMediaState(retiredVideo, 'unmount-cleanup');
      throw error;
    }
  } finally {
    await retiredVideo.dispose();
  }
  expect(state.listRequests).toBe(2);
  expectClean(state);
});

test('touch opens a usable create form and releases management media until it closes', async ({ page, browserName }) => {
  const state = await setup(page, browserName);
  const manager = await openManager(page);
  await expect.poll(() => state.mediaRequests.has(0)).toBe(true);
  const form = await openCreate(page, manager);
  await expect(manager.locator('video[src]')).toHaveCount(0);
  await form.getByLabel('Название', { exact: true }).fill('Новый тренд с телефона');
  await choosePreview(page, form);
  await expect(form.getByLabel('URL превью', { exact: true })).toHaveValue(uploadedUrl);
  const uploadedPreview = form.getByAltText('Превью тренда', { exact: true });
  await expect(uploadedPreview).toBeVisible();
  await expect.poll(() => uploadedPreview.evaluate((element) => element.naturalWidth)).toBeGreaterThan(0);
  await form.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(form).toHaveCount(0);
  await expect(manager.locator('.inline-trend-admin-card').first().locator('video')).toHaveAttribute('src', state.previewUrl(0));
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  const reopened = await openManager(page);
  const freshForm = await openCreate(page, reopened);
  await expect(freshForm.getByLabel('Название', { exact: true })).toHaveValue('');
  await expect(freshForm.getByLabel('URL превью', { exact: true })).toHaveValue('');
  expect(state.uploads).toBe(1);
  expectClean(state);
});

test('pending and failed list requests leave touch close and reopen available', async ({ page, browserName }) => {
  const state = await setup(page, browserName, { listMode: 'pending' });
  let manager = await openManager(page);
  await expect.poll(() => state.pendingLists.length).toBe(1);
  await expect(manager.getByText('Загружаю тренды…', { exact: true })).toBeVisible();
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  const settled = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/trends/manage');
  await state.pendingLists.shift().fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: state.items, models: [model] }),
  });
  await (await settled).finished();

  state.listMode = 'failure';
  manager = await openManager(page);
  await expect(manager.getByRole('alert')).toHaveText('Не удалось получить список трендов');
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  state.listMode = 'success';
  const restored = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/trends/manage');
  manager = await openManager(page);
  await (await restored).finished();
  await expect(manager.getByRole('button', { name: 'Обновить', exact: true })).toBeEnabled();
  await expect(manager.getByRole('alert')).toHaveCount(0);
  await expect(manager.locator('.inline-trend-admin-card')).toHaveCount(3);
  const form = await openCreate(page, manager);
  await form.getByLabel('Название', { exact: true }).fill('После восстановления сети');
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('После восстановления сети');
  expect(state.listRequests).toBe(3);
  expectClean(state);
});

test('failed preview upload keeps the form interactive and accepts the same file on retry', async ({ page, browserName }) => {
  const state = await setup(page, browserName);
  state.uploadStatus = 503;
  const manager = await openManager(page);
  const form = await openCreate(page, manager);
  await form.getByLabel('Название', { exact: true }).fill('Черновик после ошибки');
  await choosePreview(page, form);
  await expect(form.getByRole('alert')).toHaveText('Сервис временно недоступен. Попробуйте ещё раз.');
  await expect(form.getByLabel('Загрузить превью', { exact: true })).toBeEnabled();
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('Черновик после ошибки');
  state.uploadStatus = 201;
  await choosePreview(page, form);
  await expect(form.getByLabel('URL превью', { exact: true })).toHaveValue(uploadedUrl);
  await expect(form.getByRole('alert')).toHaveCount(0);
  await form.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(form).toHaveCount(0);
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  await openManager(page);
  expect(state.uploads).toBe(2);
  expectClean(state);
});
