import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: {
    groups: [{ id: 'prompt', title: 'Описание' }, { id: 'references', title: 'Референсы' }],
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true },
      { name: 'video_list', label: 'Видео-референс', control: 'json', group: 'references', required: false },
    ],
    defaults: {
      video_list: [
        { url: 'https://media.example/first.mp4' },
        { url: 'https://media.example/second.mp4' },
      ],
    },
  },
};

async function mockHomeCatalog(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=home-catalog&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', is_admin: false });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/promocodes/active') return json({ active: false, code: null });
    if (path === '/api/v1/me/overview') return json({ notifications: {}, support: {}, social: {}, partner: {}, payments: {} });
    return json({ items: [] });
  });
}

async function expectCanonicalCatalog(page) {
  const oldHome = page.locator('.bottom-nav button[data-roxy-customer-route="home"]');
  const catalog = page.locator('.bottom-nav button[data-roxy-customer-route="catalog"]');

  await expect(oldHome).toHaveCount(0);
  await expect(catalog).toBeVisible();
  await expect(catalog.locator('small')).toHaveText('Каталог');
  await expect(catalog).toHaveAttribute('aria-current', 'page');
  await expect(catalog).toHaveClass(/active/);
  await expect(page.locator('#roxy-catalog-feature-hub')).toBeVisible();
  await expect(page.locator('#roxy-home-live-trends')).toBeVisible();
  await expect(page.locator('#roxy-home-trend-folders')).toBeVisible();
  await expect(page.locator('#roxy-backend-parity-features')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Что создаём?' })).toHaveCount(0);
  await expect(page.locator('#roxy-catalog-trend-folders')).toHaveCount(0);
}

test('bot startup opens the visible Catalog root', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=home');

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});

test('visible Catalog always routes to canonical home', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=home');

  await page.locator('.bottom-nav button[data-roxy-customer-route="create"]').click();
  await expect(page).toHaveURL(/[?&]route=create(?:&|$)/);

  const catalog = page.locator('.bottom-nav button[data-roxy-customer-route="catalog"]');
  await catalog.click();

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});

test('legacy route=catalog normalizes to canonical home', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});

test('unknown routes fall back to the canonical Home feature group', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=unknown');

  await expect(page.locator('#roxy-catalog-feature-hub')).toBeVisible();
});

test('canonical Home fetches its trend list once', async ({ page }) => {
  let trendRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/trends') trendRequests += 1;
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=home');
  await expect(page.locator('#roxy-catalog-feature-hub')).toBeVisible();
  await expect(page.locator('#roxy-home-trend-folders')).toBeVisible();
  await page.waitForLoadState('networkidle');

  expect(trendRequests).toBe(1);
});

test('structured video uploads lock edits and report upload errors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);

  let uploadCount = 0;
  let signalFirstUpload;
  let releaseFirstUpload;
  const firstUploadStarted = new Promise((resolve) => { signalFirstUpload = resolve; });
  const firstUploadGate = new Promise((resolve) => { releaseFirstUpload = resolve; });
  await page.route('**/api/v1/uploads/kie', async (route) => {
    uploadCount += 1;
    if (uploadCount === 1) {
      signalFirstUpload();
      await firstUploadGate;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ url: '/uploads/feed/faststart-video.mp4' }),
      });
    }
    return route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Temporary upload failure' }),
    });
  });

  await page.goto('/mini-app/?route=create');

  const editor = page.locator('[data-structured-kind="video_list"]');
  await expect(editor).toBeVisible();
  const rows = editor.locator('.structured-row');
  await expect(rows).toHaveCount(2);
  const secondRow = rows.nth(1);
  await secondRow.locator('input[type="file"]').setInputFiles({
    name: 'replacement.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('replacement-video'),
  });
  await firstUploadStarted;
  try {
    await expect(secondRow.locator('input[placeholder="https://..."]')).toBeDisabled();
    await expect(rows.first().getByRole('button', { name: 'Удалить видео' })).toBeDisabled();
    await expect(rows.first().locator('input[placeholder="Начало, сек"]')).toBeDisabled();
  } finally {
    releaseFirstUpload();
  }

  await expect(secondRow.locator('input[placeholder="https://..."]')).toHaveValue('/uploads/feed/faststart-video.mp4');
  await rows.first().locator('input[type="file"]').setInputFiles({
    name: 'failed.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('failed-video'),
  });
  await expect(editor.getByRole('alert')).toHaveText('Не удалось загрузить файл. Попробуйте ещё раз.');
});
