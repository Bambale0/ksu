import { expect, test } from '@playwright/test';

const TREND_ID = '11111111-1111-4111-8111-111111111111';
const TREND_TASK_ID = '22222222-2222-4222-8222-222222222222';
const NORMAL_TASK_ID = '33333333-3333-4333-8333-333333333333';
const IMAGE_URL = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
const model = {
  id: 'nano-banana-pro', title: 'NanoBanana PRO', family: 'nanobanana',
  media_type: 'image', operation: 'generate_or_edit', price_rox: '25.00',
  ui_schema: {
    defaults: {},
    fields: [{ name: 'prompt', label: 'Описание', control: 'textarea', required: true }],
  },
};

const task = (id, status, ready = false) => ({
  id, status, model, created_at: '2026-10-10T08:43:16Z',
  result_url: ready ? IMAGE_URL : null,
  result_urls: ready ? [IMAGE_URL] : [],
  media: ready ? [{ url: IMAGE_URL, content_type: 'image/gif' }] : [],
});

async function telegramWithoutChat(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=delivery-no-chat&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function fakeApi(page, { taskId, details }) {
  let detailRequests = 0;
  let creates = 0;
  let lastTask = task(taskId, 'queued');
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (value, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(value),
    });
    if (path === '/api/v1/me') return json({
      id: 'signed-qa-user', telegram_id: 777, first_name: 'QA',
      balance_rox: '25.00', is_admin: false,
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations/quote') return json({
      model_id: model.id, cost_rox: '25.00',
      effective_cost_rox: '25.00', retail_cost_rox: '25.00',
    });
    if (path === '/api/v1/generations' && method === 'POST') {
      creates++;
      return json({ id: taskId, status: 'queued' }, 202);
    }
    if (path === '/api/v1/generations' && method === 'GET') {
      const succeededOnly = new URL(request.url()).searchParams.get('status') === 'succeeded';
      const include = creates || taskId === TREND_TASK_ID;
      const items = include && (!succeededOnly || lastTask.status === 'succeeded') ? [lastTask] : [];
      return json({ items, has_more: false });
    }
    if (path === '/api/v1/generations/' + taskId) {
      detailRequests++;
      lastTask = details(detailRequests);
      return json(lastTask);
    }
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/me/overview') return json({});
    if (path === '/api/v1/referrals/stats') return json({ first_line: 0, second_line: 0 });
    if (path.startsWith('/api/v1/referrals/')) return json({ items: [] });
    if (path === '/api/v1/promocodes/active') return json({ active: false });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    return json({ items: [] });
  });
  return { detailRequests: () => detailRequests, creates: () => creates };
}

test('pending trend result arrives in Mini App with no Telegram chat, including delayed owned media', async ({ page }) => {
  await telegramWithoutChat(page);
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n === 1 ? task(TREND_TASK_ID, 'queued')
      : n === 2 ? task(TREND_TASK_ID, 'generating')
      : n === 3 ? task(TREND_TASK_ID, 'succeeded', false)
      : task(TREND_TASK_ID, 'succeeded', true),
  });

  // Exactly the real navigation used after POST /trends/:id/run.
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.preview-card')).toBeVisible();
  await expect(page.locator('.preview-media img')).toHaveAttribute('src', IMAGE_URL, { timeout: 20000 });
  await expect(page.locator('.history-card').first()).toContainText('Готово');
  expect(counts.detailRequests()).toBeGreaterThanOrEqual(4);

  // Polling must stop once the owned media is ready, not spin forever.
  const completedCalls = counts.detailRequests();
  await page.waitForTimeout(3100);
  expect(counts.detailRequests()).toBe(completedCalls);
});

test('ordinary generation is recovered after reload without Telegram delivery', async ({ page }) => {
  await telegramWithoutChat(page);
  const counts = await fakeApi(page, {
    taskId: NORMAL_TASK_ID,
    details: (n) => n < 3 ? task(NORMAL_TASK_ID, 'queued') : task(NORMAL_TASK_ID, 'succeeded', true),
  });
  await page.goto('/mini-app/?route=create');
  const prompt = page.locator('textarea').first();
  await prompt.fill('Портрет без Telegram-чата');
  await page.locator('.create-summary button.primary').first().click();
  await expect.poll(() => counts.creates()).toBe(1);
  // Simulate closing/reopening Mini App while the provider is generating.
  await page.reload();
  await page.goto('/mini-app/?route=history');
  await expect(page.locator('.history-card').first()).toContainText('Готово', { timeout: 20000 });
  await page.locator('.history-card').first().click();
  await expect(page.locator('.preview-media img')).toHaveAttribute('src', IMAGE_URL);
  expect(counts.detailRequests()).toBeGreaterThanOrEqual(3);
});

test('completed work refreshes the standalone downloads screen without manual reload', async ({ page }) => {
  await telegramWithoutChat(page);
  await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n < 3 ? task(TREND_TASK_ID, 'generating') : task(TREND_TASK_ID, 'succeeded', true),
  });
  await page.goto('/mini-app/downloads/');
  await expect(page.getByRole('link', { name: /Открыть результат/ })).toHaveAttribute('href', IMAGE_URL, { timeout: 20000 });
});

test('failed generation updates the existing preview, then polling stops', async ({ page }) => {
  await telegramWithoutChat(page);
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n === 1 ? task(TREND_TASK_ID, 'queued')
      : { ...task(TREND_TASK_ID, 'failed'), error: 'provider_generation_failed' },
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.preview-media')).toContainText('Генерация не удалась', { timeout: 12000 });
  await expect(page.locator('.history-card').first()).toContainText('Не получилось');
  // The initial deep-link detail fetch and the shared observer can overlap;
  // allow the observer to see the terminal status, then prove quiescence.
  await page.waitForTimeout(2800);
  const completedCalls = counts.detailRequests();
  await page.waitForTimeout(3100);
  expect(counts.detailRequests()).toBe(completedCalls);
});

test('generation polling pauses when WebView is hidden and resumes on visibility change', async ({ page }) => {
  await telegramWithoutChat(page);
  let finished = false;
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: () => finished ? task(TREND_TASK_ID, 'succeeded', true) : task(TREND_TASK_ID, 'generating'),
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect.poll(() => counts.detailRequests()).toBeGreaterThanOrEqual(2);
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(200);
  const before = counts.detailRequests();
  await page.waitForTimeout(2900);
  expect(counts.detailRequests()).toBe(before);
  finished = true;
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('.preview-media img')).toHaveAttribute('src', IMAGE_URL, { timeout: 10000 });
});
