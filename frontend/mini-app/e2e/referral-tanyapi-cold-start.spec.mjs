import { expect, test } from '@playwright/test';

async function installTelegram(page, { initData = 'query_id=e2e&hash=test', startParam = '' } = {}) {
  await page.addInitScript(({ init, start }) => {
    window.Telegram = {
      WebApp: {
        initData: init,
        initDataUnsafe: { user: { id: 999, first_name: 'Cold Start' }, start_param: start },
        ready() {},
        expand() {},
        close() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { init: initData, start: startParam });
}

async function mockCoreApi(page) {
  const requests = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const headers = request.headers();
    requests.push({ path, headers });
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me') return json({
      id: 'cold_user',
      telegram_id: 999,
      first_name: 'Cold Start',
      balance_rox: '100.00',
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ promos: [], sections: [] });
    if (path === '/api/v1/notifications') return json({ items: [], unread_count: 0 });
    return json({ items: [] });
  });
  return requests;
}

async function firstRequest(requests, path) {
  await expect.poll(() => requests.find((item) => item.path === path) || null).not.toBeNull();
  return requests.find((item) => item.path === path);
}

test('startapp query is forwarded on the first core API request when SDK start_param is missing', async ({ page }) => {
  await installTelegram(page, { startParam: '' });
  const requests = await mockCoreApi(page);

  await page.goto('/mini-app/?route=home&startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/me');
  expect(request.headers['x-telegram-init-data']).toBe('query_id=e2e&hash=test');
  expect(request.headers['x-telegram-start-param']).toBe('ref_777');
});

test('early tgWebAppData and tgWebAppStartParam authenticate before SDK initData is ready', async ({ page }) => {
  await installTelegram(page, { initData: '', startParam: '' });
  const requests = await mockCoreApi(page);
  const initData = 'query_id=early&auth_date=1787760000&hash=from_hash';

  await page.goto(`/mini-app/?route=home#tgWebAppData=${encodeURIComponent(initData)}&tgWebAppStartParam=ref_888`);
  await expect(page.locator('.home-screen')).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/me');
  expect(request.headers['x-telegram-init-data']).toBe(initData);
  expect(request.headers['x-telegram-start-param']).toBe('ref_888');
});

test('SDK parsed start_param wins over conflicting URL fallbacks', async ({ page }) => {
  await installTelegram(page, { startParam: 'ref_111' });
  const requests = await mockCoreApi(page);

  await page.goto('/mini-app/?route=home&start_payload=ref_222&startapp=ref_333');
  await expect(page.locator('.home-screen')).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/me');
  expect(request.headers['x-telegram-start-param']).toBe('ref_111');
});

test('signed initData start_param wins while initDataUnsafe is still incomplete', async ({ page }) => {
  await installTelegram(page, {
    initData: 'query_id=e2e&start_param=ref_444&hash=test',
    startParam: '',
  });
  const requests = await mockCoreApi(page);

  await page.goto('/mini-app/?route=home&start_payload=ref_222&startapp=ref_333');
  await expect(page.locator('.home-screen')).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/me');
  expect(request.headers['x-telegram-start-param']).toBe('ref_444');
});

test('product start_payload wins over generic startapp when Telegram has no signed start_param', async ({ page }) => {
  await installTelegram(page, { startParam: '' });
  const requests = await mockCoreApi(page);

  await page.goto('/mini-app/?route=home&start_payload=ref_222&startapp=ref_333');
  await expect(page.locator('.home-screen')).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/me');
  expect(request.headers['x-telegram-start-param']).toBe('ref_222');
});

test('standalone customer API requests carry the same recovered referral headers', async ({ page }) => {
  await installTelegram(page, { startParam: '' });
  const requests = await mockCoreApi(page);

  await page.goto('/mini-app/notifications/?startapp=ref_555');
  await expect(page.getByRole('heading', { name: /Уведомления/i })).toBeVisible();

  const request = await firstRequest(requests, '/api/v1/notifications');
  expect(request.headers['x-telegram-init-data']).toBe('query_id=e2e&hash=test');
  expect(request.headers['x-telegram-start-param']).toBe('ref_555');
});
