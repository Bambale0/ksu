import { expect, test } from '@playwright/test';

test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

const mediaOrigin = 'https://trend-preview.example.invalid';
const previewUrl = (index) => `${mediaOrigin}/admin-preview-${index}.mp4`;
const uploadedUrl = `${mediaOrigin}/uploaded-preview.png`;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF9sAAAAASUVORK5CYII=', 'base64');
const previewFile = { name: 'trend-preview.png', mimeType: 'image/png', buffer: png };

const model = {
  id: 'video-catalog-model', title: 'Видео из каталога', family: 'video',
  media_type: 'video', operation: 'text_to_video', price_rox: '10.00',
  known_fields: ['prompt', 'duration'], required_fields: ['prompt', 'duration'],
  ui_schema: { groups: [], fields: [], defaults: { duration: 5 } },
};

function videoTrends(count) {
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

async function setup(page, { count = 3, listMode = 'success' } = {}) {
  const state = {
    items: videoTrends(count), listMode, listRequests: 0, pendingLists: [],
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
      const video = /^\/admin-preview-(\d+)\.mp4$/.exec(path);
      if (video) {
        state.mediaRequests.add(Number(video[1]));
        // The oracle is resource activation, not codec performance or an
        // artificial simulation of an actual iPhone process crash.
        return route.fulfill({ status: 200, contentType: 'video/mp4', body: '' });
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

test('a large video list stays usable by touch without activating far-offscreen media', async ({ page }) => {
  const state = await setup(page, { count: 300 });
  const manager = await openManager(page);
  const cards = manager.locator('.inline-trend-admin-card');
  await expect(cards).toHaveCount(300);
  await expect.poll(() => state.mediaRequests.has(0)).toBe(true);

  // Baseline assigns src to all 300 auto-playing videos. Check both browser
  // requests and the dormant far-offscreen sources, without timing a freeze.
  await expect(cards.last().locator('video')).not.toHaveAttribute('src', /.+/);
  const activatedTail = await cards.evaluateAll((elements) => elements.slice(-25)
    .filter((element) => Boolean(element.querySelector('video')?.getAttribute('src'))).length);
  expect(activatedTail).toBe(0);
  expect([...state.mediaRequests].filter((index) => index >= 275)).toEqual([]);

  const lastCard = cards.last();
  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).scrollIntoViewIfNeeded();
  await expect(lastCard.locator('video')).toHaveAttribute('src', previewUrl(299));
  await expect.poll(() => state.mediaRequests.has(299)).toBe(true);
  const panel = manager.locator('.inline-trend-admin-panel');
  const scrollTop = await panel.evaluate((element) => element.scrollTop);
  expect(scrollTop).toBeGreaterThan(0);

  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).tap();
  const form = page.getByRole('dialog', { name: 'Редактировать тренд', exact: true });
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('Мобильный тренд 300');
  await expect(manager.locator('video[src]')).toHaveCount(0);
  await form.getByLabel('Название', { exact: true }).fill('Проверка последней карточки');
  await form.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(form).toHaveCount(0);
  await expect.poll(async () => Math.abs((await panel.evaluate((element) => element.scrollTop)) - scrollTop)).toBeLessThan(2);
  await expect(lastCard.locator('video')).toHaveAttribute('src', previewUrl(299));
  await lastCard.getByRole('button', { name: 'Редактировать', exact: true }).tap();
  await expect(page.getByRole('dialog', { name: 'Редактировать тренд', exact: true })
    .getByLabel('Название', { exact: true })).toHaveValue('Мобильный тренд 300');
  expectClean(state);
});

test('touch opens a usable create form and releases management media until it closes', async ({ page }) => {
  const state = await setup(page);
  const manager = await openManager(page);
  await expect.poll(() => state.mediaRequests.has(0)).toBe(true);
  const form = await openCreate(page, manager);
  await expect(manager.locator('video[src]')).toHaveCount(0);
  await form.getByLabel('Название', { exact: true }).fill('Новый тренд с телефона');
  await choosePreview(page, form);
  await expect(form.getByLabel('URL превью', { exact: true })).toHaveValue(uploadedUrl);
  await expect(form.getByAltText('Превью тренда', { exact: true })).toBeVisible();
  await form.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(form).toHaveCount(0);
  await expect(manager.locator('.inline-trend-admin-card').first().locator('video')).toHaveAttribute('src', previewUrl(0));
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  const reopened = await openManager(page);
  const freshForm = await openCreate(page, reopened);
  await expect(freshForm.getByLabel('Название', { exact: true })).toHaveValue('');
  await expect(freshForm.getByLabel('URL превью', { exact: true })).toHaveValue('');
  expect(state.uploads).toBe(1);
  expectClean(state);
});

test('pending and failed list requests leave touch close and reopen available', async ({ page }) => {
  const state = await setup(page, { listMode: 'pending' });
  let manager = await openManager(page);
  await expect.poll(() => state.pendingLists.length).toBe(1);
  await expect(manager.getByText('Загружаю тренды…', { exact: true })).toBeVisible();
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  const settled = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/trends/manage');
  await state.pendingLists.shift().fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: state.items, models: [model] }),
  });
  await settled;

  state.listMode = 'failure';
  manager = await openManager(page);
  await expect(manager.getByRole('alert')).toHaveText('Не удалось получить список трендов');
  await manager.getByRole('button', { name: 'Закрыть', exact: true }).tap();
  await expect(manager).toHaveCount(0);
  state.listMode = 'success';
  manager = await openManager(page);
  await expect(manager.getByRole('alert')).toHaveCount(0);
  await expect(manager.locator('.inline-trend-admin-card')).toHaveCount(3);
  const form = await openCreate(page, manager);
  await form.getByLabel('Название', { exact: true }).fill('После восстановления сети');
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('После восстановления сети');
  expect(state.listRequests).toBe(3);
  expectClean(state);
});

test('failed preview upload keeps the form interactive and accepts the same file on retry', async ({ page }) => {
  const state = await setup(page);
  state.uploadStatus = 503;
  const manager = await openManager(page);
  const form = await openCreate(page, manager);
  await form.getByLabel('Название', { exact: true }).fill('Черновик после ошибки');
  await choosePreview(page, form);
  await expect(form.getByRole('alert')).toHaveText('Не удалось загрузить превью');
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
