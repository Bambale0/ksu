import { expect, test } from '@playwright/test';

async function setup(page, { granted = false, result = true, supported = true, onboarding = false, auth = true } = {}) {
  await page.addInitScript(({ granted, result, supported, auth }) => {
    window.__writeRequests = 0;
    window.__telegramLinks = [];
    const app = {
      initData: auth ? 'query_id=e2e&start_param=ref_777&hash=test' : '',
      initDataUnsafe: { user: { id: 999, first_name: 'Referral', allows_write_to_pm: granted }, start_param: 'ref_777' },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      openLink(url) { window.__telegramLinks.push(url); },
      openTelegramLink(url) { window.__telegramLinks.push(url); },
      isVersionAtLeast() { return supported; },
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    };
    if (supported) app.requestWriteAccess = (callback) => {
      window.__writeRequests += 1;
      if (result === 'error') throw new Error('WebAppMethodUnsupported');
      if (result === 'pending') { window.__writeCallback = callback; return; }
      callback(result);
    };
    window.Telegram = { WebApp: app };
  }, { granted, result, supported, auth });
  const requests = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ path, method: request.method(), headers: request.headers() });
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (path === '/api/v1/me') return auth ? json({ id: 'user-999', telegram_id: 999, first_name: 'Referral', balance_rox: '100.00', bot_chat_link: 'https://t.me/fixture_bot?start=connect' }) : json({ detail: 'Unauthorized' }, 401);
    if (path === '/api/v1/onboarding') return json({ enabled: onboarding, completed: !onboarding, version: '2' });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/discovery/home') return json({ promos: [], sections: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    return json({ items: [] });
  });
  return requests;
}

test('referral opens Home immediately over legacy catalog URL without completing onboarding', async ({ page }) => {
  const requests = await setup(page, { onboarding: true });
  await page.goto('/mini-app/?route=catalog&startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();
  await expect(page).toHaveURL(/route=home/);
  await expect(page.locator('.roxy-onboarding-v2')).toHaveCount(0);
  await expect.poll(() => requests.find((r) => r.path === '/api/v1/me')?.headers['x-telegram-start-param']).toBe('ref_777');
  expect(requests.some((r) => r.path === '/api/v1/onboarding/complete')).toBe(false);
  expect(await page.evaluate(() => window.__writeRequests)).toBe(0);
});

test('native consent connects without leaving Home and without automatic prompts', async ({ page }) => {
  const requests = await setup(page);
  await page.goto('/mini-app/?startapp=ref_777');
  const connect = page.getByRole('button', { name: 'Подключить чат Telegram', exact: true });
  await expect(connect).toBeVisible();
  expect(requests.some((r) => r.path === '/api/v1/me')).toBe(true);
  expect(await page.evaluate(() => window.__writeRequests)).toBe(0);
  await connect.click();
  await expect(page.getByText('Сообщения в Telegram разрешены', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.__writeRequests)).toBe(1);
  expect(await page.evaluate(() => window.__telegramLinks)).toEqual([]);
  await expect(page.locator('.home-screen')).toBeVisible();
});

test('denied consent keeps browsing and manual configured fallback available', async ({ page }) => {
  await setup(page, { result: false });
  await page.goto('/mini-app/?startapp=ref_777');
  await page.getByRole('button', { name: 'Подключить чат Telegram', exact: true }).click();
  await expect(page.getByText(/Разрешение не получено/)).toBeVisible();
  await expect(page.locator('.home-screen')).toBeVisible();
  await page.getByRole('button', { name: 'Открыть чат вручную', exact: true }).click();
  expect(await page.evaluate(() => window.__telegramLinks)).toEqual(['https://t.me/fixture_bot?start=connect']);
});

for (const options of [{ supported: false }, { result: 'error' }]) {
  test(`unsupported or failing Telegram SDK offers fallback ${JSON.stringify(options)}`, async ({ page }) => {
    await setup(page, options);
    await page.goto('/mini-app/?startapp=ref_777');
    await page.getByRole('button', { name: 'Подключить чат Telegram', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Открыть чат вручную', exact: true })).toBeVisible();
    await expect(page.locator('.home-screen')).toBeVisible();
  });
}

test('already allowed user is not asked again', async ({ page }) => {
  await setup(page, { granted: true });
  await page.goto('/mini-app/?startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Подключить чат Telegram', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.__writeRequests)).toBe(0);
});

test('server-required onboarding still opens for a referral user', async ({ page }) => {
  await setup(page, { onboarding: true });
  await page.goto('/mini-app/?onboarding=1');
  await expect(page.locator('.roxy-onboarding-v2')).toBeVisible();
  await expect(page.locator('.roxy-onboarding-v2')).toContainText('знакомьтесь');
});

test('sticky referral does not hijack deliberate history navigation after reload', async ({ page }) => {
  await setup(page);
  await page.goto('/mini-app/?startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();
  await page.locator('.home-screen [data-catalog-feature="history"]').click();
  await expect(page).toHaveURL(/route=history/);
  await page.reload();
  await expect(page).toHaveURL(/route=history/);
  await expect(page.getByRole('heading', { name: 'Все работы', exact: true })).toBeVisible();
});


test('pending permission is single-flight and late confirmation settles after timeout', async ({ page }) => {
  await setup(page, { result: 'pending' });
  await page.clock.install();
  await page.goto('/mini-app/?startapp=ref_777');
  const connect = page.getByRole('button', { name: 'Подключить чат Telegram', exact: true });
  await connect.click();
  const pending = page.getByRole('button', { name: 'Ожидаю разрешение…', exact: true });
  await expect(pending).toBeDisabled();
  await pending.dispatchEvent('click');
  expect(await page.evaluate(() => window.__writeRequests)).toBe(1);
  await page.clock.fastForward(20001);
  await expect(page.getByRole('button', { name: 'Открыть чат вручную', exact: true })).toBeVisible();
  await expect(page.locator('.home-screen')).toBeVisible();
  await page.evaluate(() => { window.__writeCallback(true); window.__writeCallback(false); });
  await expect(page.getByText('Сообщения в Telegram разрешены', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.__writeRequests)).toBe(1);
});

test('granted permission is not requested again after remount in the same session', async ({ page }) => {
  await setup(page);
  await page.goto('/mini-app/?startapp=ref_777');
  await page.getByRole('button', { name: 'Подключить чат Telegram', exact: true }).click();
  await expect(page.getByText('Сообщения в Telegram разрешены', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator('.home-screen')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Подключить чат Telegram', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.__writeRequests)).toBe(0);
});

test('storage denial does not block native permission or referral browsing', async ({ page }) => {
  await setup(page);
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new DOMException('Blocked', 'SecurityError'); };
    Storage.prototype.setItem = () => { throw new DOMException('Blocked', 'SecurityError'); };
  });
  await page.goto('/mini-app/?startapp=ref_777');
  await page.getByRole('button', { name: 'Подключить чат Telegram', exact: true }).click();
  await expect(page.getByText('Сообщения в Telegram разрешены', { exact: true })).toBeVisible();
  await expect(page.locator('.home-screen')).toBeVisible();
});

test('unauthenticated launch never requests chat permission', async ({ page }) => {
  const requests = await setup(page, { auth: false });
  await page.goto('/mini-app/?startapp=ref_777');
  await expect(page.locator('.roxy-browser-landing')).toBeVisible();
  expect(requests.some((request) => request.path === '/api/v1/onboarding/complete')).toBe(false);
  await expect(page.getByRole('button', { name: 'Подключить чат Telegram', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.__writeRequests)).toBe(0);
});

test('protected action still redirects referral browsing to mandatory onboarding', async ({ page }) => {
  const requests = await setup(page, { onboarding: true });
  await page.route('**/api/v1/generations', (route) => route.request().method() === 'POST'
    ? route.fulfill({ status: 428, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'onboarding_required', version: '2' } }) })
    : route.fallback());
  await page.goto('/mini-app/?startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();
  await page.evaluate(() => { void fetch('/api/v1/generations', { method: 'POST', body: '{}' }); });
  await expect(page).toHaveURL(/onboarding=1/);
  await expect(page.locator('.roxy-onboarding-v2')).toBeVisible();
  expect(requests.some((request) => request.path === '/api/v1/onboarding/complete')).toBe(false);
});

test('referral Home renders actual current trends at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, { onboarding: true });
  await page.route('**/api/v1/trends?*', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{
      id: '12345678-1234-4234-8234-123456789abc', title: 'Плёночный портрет',
      description: 'Тестовый тренд', media_type: 'image', preview_url: null,
      model: { id: 'test-model', title: 'Test' }, cost_rox: '10.00',
    }] }),
  }));
  await page.goto('/mini-app/?route=catalog&startapp=ref_777');
  await expect(page.locator('#roxy-home-live-trends').getByText('Плёночный портрет', { exact: true })).toBeVisible();
  await expect(page.locator('.roxy-onboarding-v2')).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath('referral-home-mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
