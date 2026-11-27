import { expect, test } from '@playwright/test';

async function loginFixture(page) {
  await page.route('**/api/v1/browser-auth/config', route => route.fulfill({ json: { bot_username: 'RoxyTestBot' } }));
  await page.route('https://telegram.org/js/telegram-widget.js?22', route => route.fulfill({
    contentType: 'application/javascript', body: 'window.__roxyWidgetLoaded = true;',
  }));
}

for (const width of [320, 390, 768, 1280, 1648]) {
  test(`anonymous Mini App opens the canonical responsive login at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await loginFixture(page);
    await page.goto('/mini-app/?route=home');
    await expect(page.locator('body')).toHaveAttribute('data-page', 'login');
    await expect(page.locator('.roxy-browser-landing')).toHaveCount(0);
    await expect(page.locator('#login-status')).toContainText('Подтверди вход');
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    expect(new URL(page.url()).pathname).toBe('/login');
  });
}

test('signed exchange resumes the original internal route with referral and without auth or unknown parameters', async ({ page }) => {
  await loginFixture(page);
  await page.route('**/api/v1/browser-auth', route => route.fulfill({ json: {
    ok: true, init_data: 'query_id=browser-test&hash=synthetic', expires_in: 3600,
  } }));
  await page.route('**/api/v1/me', route => route.fulfill({ json: { id: 'synthetic', telegram_id: 42, balance_rox: '0' } }));
  await page.goto('/mini-app/?route=profile&ref=QA&unknown=discard&init_data=discard');
  await expect(page.locator('#login-status')).toContainText('Подтверди вход');
  expect(page.url()).not.toContain('init_data');
  await page.evaluate(() => { void window.onRoxyTelegramAuth({ id: 42, first_name: 'Test', auth_date: 1, hash: 'fixture' }); });
  await page.waitForURL(url => url.pathname === '/mini-app/' && url.searchParams.get('route') === 'profile');
  const url = new URL(page.url());
  expect(url.searchParams.get('ref')).toBe('QA');
  expect(url.searchParams.has('unknown')).toBe(false);
  expect(url.searchParams.has('init_data')).toBe(false);
});

test('direct trend entry preserves the target without copying it into the login URL', async ({ page }) => {
  await loginFixture(page);
  const trend = '11111111-1111-4111-8111-111111111111';
  await page.route('**/api/v1/browser-auth', route => route.fulfill({ json: {
    ok: true, init_data: 'query_id=browser-test&hash=synthetic', expires_in: 3600,
  } }));
  await page.route('**/api/v1/me', route => route.fulfill({ json: { id: 'synthetic', telegram_id: 42 } }));
  await page.goto('/mini-app/trend/?id=' + trend + '&startapp=ref_777');
  await expect(page.locator('#login-status')).toContainText('Подтверди вход');
  expect(page.url()).not.toContain(trend);
  await page.evaluate(() => { void window.onRoxyTelegramAuth({ id: 42, first_name: 'Test', auth_date: 1, hash: 'fixture' }); });
  await page.waitForURL(url => url.pathname === '/mini-app/trend/');
  expect(new URL(page.url()).searchParams.get('id')).toBe(trend);
  expect(new URL(page.url()).searchParams.get('startapp')).toBe('ref_777');
});

test('resume cannot redirect outside the app', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('__roxy_browser_resume_v1', '//example.invalid/mini-app/');
    sessionStorage.setItem('__roxy_browser_init_data_v1', JSON.stringify({ initData: 'query_id=test&hash=fixture', expiresAt: Date.now() + 60000 }));
  });
  await page.route('**/api/v1/me', route => route.fulfill({ json: { id: 'synthetic', telegram_id: 42 } }));
  await page.goto('/login?resume=1');
  await expect(page.locator('#login-continue')).toHaveAttribute('href', '/mini-app/');
});
