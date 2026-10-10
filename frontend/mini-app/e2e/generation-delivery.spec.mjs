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

async function fakeApi(page, { taskId, details, failListTimes = 0 }) {
  let detailRequests = 0;
  let creates = 0;
  let listRequests = 0;
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
      listRequests++;
      if (listRequests <= failListTimes) return json({ detail: 'temporary server issue' }, 503);
      const succeededOnly = new URL(request.url()).searchParams.get('status') === 'succeeded';
      const include = (creates || taskId === TREND_TASK_ID) && !lastTask.hidden_from_history;
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
  return { detailRequests: () => detailRequests, creates: () => creates, listRequests: () => listRequests };
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

test('multi-result generation stays pending until every owned asset is ready', async ({ page }) => {
  await telegramWithoutChat(page);
  const first = { ...task(TREND_TASK_ID, 'succeeded', true), media_delivery: {
    expected: 2, ready: 1, failed: 0, state: 'pending',
  } };
  const second = { ...first, media_delivery: { expected: 2, ready: 2, failed: 0, state: 'ready' },
    media: [...first.media, { url: IMAGE_URL + '#second', ordinal: 1 }] };
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n === 1 ? task(TREND_TASK_ID, 'queued') : n < 4 ? first : second,
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.history-card').first()).toContainText('Сохраняем файл', { timeout: 12000 });
  await expect(page.locator('.history-card').first()).toContainText('Готово', { timeout: 20000 });
  expect(counts.detailRequests()).toBeGreaterThanOrEqual(4);
  await page.waitForTimeout(300);
  const complete = counts.detailRequests();
  await page.waitForTimeout(3500);
  expect(counts.detailRequests()).toBe(complete);
});

test('terminal failed media ingest informs the user without polling forever', async ({ page }) => {
  await telegramWithoutChat(page);
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n < 2 ? task(TREND_TASK_ID, 'queued') :
      { ...task(TREND_TASK_ID, 'succeeded'), media_delivery: {
        expected: 1, ready: 0, failed: 1, state: 'failed',
      } },
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.history-card').first()).toContainText('Не все файлы сохранены', { timeout: 12000 });
  // Deep-link and shared observer may both fetch the terminal result once.
  await page.waitForTimeout(2800);
  const last = counts.detailRequests();
  await page.waitForTimeout(3200);
  expect(counts.detailRequests()).toBe(last);
});

test('hidden completed generation remains accessible by owner but never reappears in history', async ({ page }) => {
  await telegramWithoutChat(page);
  const hidden = (status, ready = false) => ({
    ...task(TREND_TASK_ID, status, ready), hidden_from_history: true,
  });
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n < 2 ? hidden('queued') : hidden('succeeded', true),
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.preview-media img')).toHaveAttribute('src', IMAGE_URL, { timeout: 15000 });
  await expect(page.locator('.history-card')).toHaveCount(0);
  expect(counts.detailRequests()).toBeGreaterThanOrEqual(2);
});

test('recent-history discovery retries even without a pending local UUID', async ({ page }) => {
  await telegramWithoutChat(page);
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID, failListTimes: 1,
    details: (n) => n < 2 ? task(TREND_TASK_ID, 'queued') : task(TREND_TASK_ID, 'succeeded', true),
  });
  await page.goto('/mini-app/?route=home');
  await expect.poll(() => counts.listRequests(), { timeout: 14000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => counts.detailRequests(), { timeout: 16000 }).toBeGreaterThanOrEqual(2);
  // Route via the real popstate handler without reloading the WebView.
  await page.evaluate(() => {
    const target = new URL(location.href);
    target.searchParams.set('route', 'history');
    window.history.pushState({}, '', target);
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.locator('.history-card').first()).toContainText('Готово', { timeout: 10000 });
});

test('batch start registers each generated image and updates its thumbnails automatically', async ({ page }) => {
  await telegramWithoutChat(page);
  const ids = [NORMAL_TASK_ID, '44444444-4444-4444-8444-444444444444'];
  const detailCalls = [0, 0];
  let launched = false;
  const job = {
    id: '55555555-5555-4555-8555-555555555555', status: 'running',
    model_id: model.id, prompt: 'Пакетное тестирование', input_count: 2,
    succeeded_count: 0, failed_count: 0, active_count: 2, progress_percent: 0,
    total_charged_credits: '50.00',
    items: ids.map((id, ordinal) => ({ ordinal, generation: { id, status: 'queued', result_url: null } })),
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (path === '/api/v1/me') return json({ id: 'signed-user', telegram_id: 777, first_name: 'QA' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [{ ...model, known_fields: ['image_url'] }], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false });
    if (path === '/api/v1/uploads/kie') return json({ url: 'https://cdn.example.invalid/mock-image.png' });
    if (path === '/api/v1/batch-generations' && method === 'POST') {
      launched = true;
      return json(job, 202);
    }
    if (path === '/api/v1/batch-generations') return json({ items: launched ? [job] : [] });
    for (let index = 0; index < ids.length; index++) {
      if (path === '/api/v1/generations/' + ids[index]) {
        detailCalls[index]++;
        const ready = detailCalls[index] >= 2;
        return json(task(ids[index], ready ? 'succeeded' : 'queued', ready));
      }
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/batch/');
  await page.locator('textarea.control').first().fill('Пакетное тестирование');
  await page.locator('.upload-control input[type="file"]').setInputFiles([
    { name: 'one.png', mimeType: 'image/png', buffer: Buffer.from('one') },
    { name: 'two.png', mimeType: 'image/png', buffer: Buffer.from('two') },
  ]);
  await page.getByRole('button', { name: 'Запустить пакет' }).click();
  await expect.poll(() => launched).toBe(true);
  await expect(page.locator('.tool-result-card .media-tile img')).toHaveCount(2, { timeout: 22000 });
  expect(detailCalls[0]).toBeGreaterThanOrEqual(2);
  expect(detailCalls[1]).toBeGreaterThanOrEqual(2);
});

test('retrying failed batch items registers the new generation and delivers its media', async ({ page }) => {
  await telegramWithoutChat(page);
  const batchId = '66666666-6666-4666-8666-666666666666';
  let retried = false;
  let detailRequests = 0;
  const failed = {
    id: batchId, model_id: model.id, prompt: 'Retry', status: 'failed',
    input_count: 1, succeeded_count: 0, failed_count: 1, active_count: 0,
    progress_percent: 100, total_charged_credits: '25.00',
    items: [{ ordinal: 0, generation: { id: TREND_TASK_ID, status: 'failed', result_url: null } }],
  };
  await page.route('**/api/v1/**', (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (path === '/api/v1/me') return json({ telegram_id: 777, first_name: 'QA' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [{ ...model, known_fields: ['image_url'] }], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false });
    if (path.endsWith('/retry-quote')) return json({ failed_count: 1, total_cost_credits: '25.00' });
    if (path.endsWith('/retry') && req.method() === 'POST') {
      retried = true;
      return json({
        ...failed, status: 'running', failed_count: 0, active_count: 1,
        items: [{ ordinal: 0, generation: { id: NORMAL_TASK_ID, status: 'queued', result_url: null } }],
      }, 202);
    }
    if (path === '/api/v1/batch-generations') return json({ items: [retried ? {
      ...failed, status: 'running', failed_count: 0, active_count: 1,
      items: [{ ordinal: 0, generation: { id: NORMAL_TASK_ID, status: 'queued', result_url: null } }],
    } : failed] });
    if (path === '/api/v1/generations/' + NORMAL_TASK_ID) {
      detailRequests++;
      return json(task(NORMAL_TASK_ID, detailRequests >= 2 ? 'succeeded' : 'queued', detailRequests >= 2));
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/batch/');
  await page.getByRole('button', { name: 'Повторить ошибки' }).click();
  await expect.poll(() => retried).toBe(true);
  await expect(page.locator('.tool-result-card .media-tile img')).toHaveCount(1, { timeout: 14000 });
  expect(detailRequests).toBeGreaterThanOrEqual(2);
});

test('failed first asset does not block subsequent ready files', async ({ page }) => {
  await telegramWithoutChat(page);
  const partial = { ...task(TREND_TASK_ID, 'succeeded'), media_delivery: {
    expected: 2, ready: 0, failed: 1, state: 'pending',
  } };
  const final = { ...task(TREND_TASK_ID, 'succeeded', true), media_delivery: {
    expected: 2, ready: 1, failed: 1, state: 'failed',
  } };
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n === 1 ? task(TREND_TASK_ID, 'queued') : n < 4 ? partial : final,
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect(page.locator('.history-card').first()).toContainText('Сохраняем файл', { timeout: 12000 });
  await expect(page.locator('.history-card').first()).toContainText('Не все файлы сохранены', { timeout: 20000 });
  await expect(page.locator('.preview-media img')).toHaveAttribute('src', IMAGE_URL);
  expect(counts.detailRequests()).toBeGreaterThanOrEqual(4);
});

test('reopening a completed batch reconciles expired provider thumbnails to owned media', async ({ page }) => {
  await telegramWithoutChat(page);
  let reads = 0;
  const expired = 'https://provider.example.invalid/expired-original.png';
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (payload) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
    if (path === '/api/v1/me') return json({ telegram_id: 777, first_name: 'QA' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [{ ...model, known_fields: ['image_url'] }], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false });
    if (path === '/api/v1/batch-generations') return json({ items: [{
      id: '66666666-6666-4666-8666-666666666666', status: 'succeeded', input_count: 1,
      succeeded_count: 1, failed_count: 0, active_count: 0, progress_percent: 100,
      model_id: model.id, total_charged_credits: '25.00',
      items: [{ ordinal: 0, generation: { id: NORMAL_TASK_ID, status: 'succeeded', result_url: expired } }],
    }] });
    if (path === '/api/v1/generations/' + NORMAL_TASK_ID) {
      reads++;
      return json({ ...task(NORMAL_TASK_ID, 'succeeded', true), media_delivery: {
        expected: 1, ready: 1, failed: 0, state: 'ready',
      } });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/batch/');
  await expect(page.locator('.tool-result-card .media-tile img')).toHaveAttribute('src', IMAGE_URL, { timeout: 18000 });
  expect(reads).toBeGreaterThan(0);
});

test('more than 32 pending generations are observed without silently losing overflow', async ({ page }) => {
  await telegramWithoutChat(page);
  const ids = Array.from({ length: 42 }, (_, index) =>
    '00000000-0000-4000-8000-' + String(index + 1).padStart(12, '0'));
  const observed = new Set();
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (payload) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify(payload),
    });
    if (path === '/api/v1/me') return json({ telegram_id: 777, first_name: 'QA' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false });
    const id = path.replace('/api/v1/generations/', '');
    if (ids.includes(id) && path.startsWith('/api/v1/generations/')) {
      observed.add(id);
      return json({ ...task(id, 'succeeded', true), media_delivery: {
        expected: 1, ready: 1, failed: 0, state: 'ready',
      } });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/?route=home');
  await page.evaluate((taskIds) => window.dispatchEvent(new CustomEvent('roxy:generation-track', {
    detail: { ids: taskIds, telegramId: 777 },
  })), ids);
  await expect.poll(() => observed.size, { timeout: 18000 }).toBe(ids.length);
});

test('downloads never regresses when an older list response resolves after fresh media', async ({ page }) => {
  await telegramWithoutChat(page);
  let requests = 0;
  const old = { ...task(TREND_TASK_ID, 'succeeded'), media_delivery: {
    expected: 1, ready: 0, failed: 0, state: 'pending',
  } };
  const fresh = { ...task(TREND_TASK_ID, 'succeeded', true), media_delivery: {
    expected: 1, ready: 1, failed: 0, state: 'ready',
  }, media: [{ id: 'owned1', url: IMAGE_URL, download_url: '/api/v1/media/owned1/download' }] };
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (payload) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
    if (path === '/api/v1/me') return json({ telegram_id: 777 });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') {
      requests++;
      const snapshot = requests === 1 ? old : fresh;
      if (requests === 1) await new Promise((resolve) => setTimeout(resolve, 1800));
      return json({ items: [snapshot], has_more: false });
    }
    return json({ items: [] });
  });
  await page.goto('/mini-app/downloads/');
  await expect.poll(() => requests).toBeGreaterThanOrEqual(1);
  await page.evaluate((generation) => window.dispatchEvent(new CustomEvent('roxy:generation-update', {
    detail: { generation, terminal: true, ready: true },
  })), fresh);
  const link = page.getByRole('link', { name: /Скачать/ }).first();
  await expect(link).toHaveAttribute('href', '/api/v1/media/owned1/download', { timeout: 12000 });
  await page.waitForTimeout(2000);
  await expect(link).toHaveAttribute('href', '/api/v1/media/owned1/download');
});

test('rotating signed media URLs do not generate duplicate delivery events', async ({ page }) => {
  await telegramWithoutChat(page);
  await page.addInitScript(() => {
    window.__deliveryEvents = [];
    window.addEventListener('roxy:generation-update', (event) => {
      window.__deliveryEvents.push(event.detail.generation);
    });
  });
  const counts = await fakeApi(page, {
    taskId: TREND_TASK_ID,
    details: (n) => n === 1 ? task(TREND_TASK_ID, 'queued') : {
      ...task(TREND_TASK_ID, 'succeeded'),
      result_url: 'https://provider.example.invalid/video.png',
      media: [{ id: 'stable-owned-asset', ordinal: 0, url: IMAGE_URL + '?token=' + n }],
      media_delivery: { expected: 2, ready: 1, failed: 0, state: 'pending' },
    },
  });
  await page.goto('/mini-app/?route=history&generation=' + TREND_TASK_ID);
  await expect.poll(() => counts.detailRequests(), { timeout: 25000 }).toBeGreaterThanOrEqual(5);
  await page.waitForTimeout(150);
  const partialEvents = await page.evaluate(() =>
    window.__deliveryEvents.filter((item) => item.media_delivery?.ready === 1).length);
  expect(partialEvents).toBe(1);
});
