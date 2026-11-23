import { expect, test } from '@playwright/test';

const WEB_ME = {
  id: '11111111-1111-4111-8111-111111111111',
  telegram_id: null,
  first_name: 'Web Creator',
  balance_rox: '123.00',
  profile_link: null,
  preferences: { ui_language: 'ru', notifications_enabled: true },
};

async function openProfile(page, { telegram = false, failLogout = false } = {}) {
  await page.addInitScript(({ native }) => {
    window.Telegram = {
      WebApp: {
        initData: native ? 'query_id=native&hash=fixture' : '',
        initDataUnsafe: native ? { user: { id: 777, first_name: 'Telegram QA' } } : {},
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { native: telegram });

  const seen = [];
  let sessionActive = true;

  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    const request = route.request();
    const json = (body, status = 200, headers = {}) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body), headers });

    if (path === '/api/v1/web-auth/me')
      return json({ authenticated: sessionActive, user_id: WEB_ME.id });
    if (path === '/api/v1/web-auth/logout') {
      seen.push({ method: request.method(), path, headers: request.headers() });
      if (failLogout) return json({ detail: 'Session service temporarily unavailable' }, 503);
      sessionActive = false;
      return json({ ok: true }, 200, { 'set-cookie': 'roxy_web_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax' });
    }
    if (path === '/api/v1/me')
      return json(telegram ? { ...WEB_ME, telegram_id: 777 } : WEB_ME);
    if (path === '/api/v1/onboarding')
      return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models')
      return json({ models: [], families: [] });
    if (path === '/api/v1/generations')
      return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed')
      return json({ items: [] });
    if (path === '/api/v1/referrals/stats')
      return json({ referral_link: null, profile_link: null, promo_codes: [] });
    if (path === '/api/v1/promocodes/active')
      return json({ active: false });
    if (path === '/api/v1/trends')
      return json({ items: [] });
    return json({ items: [] });
  });
  await page.route('**/login', (route) =>
    route.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>ROXY AI STUDIO — вход</title><p>Войти в аккаунт</p>' }));

  await page.goto('/mini-app/?route=profile');
  await expect(page.locator('.profile-screen')).toBeVisible();
  return seen;
}

test('web-only profile revokes server session once, then returns to /login', async ({ page, context }) => {
  await context.addCookies([{
    name: 'roxy_web_session',
    value: 'fictional-test-cookie',
    domain: '127.0.0.1',
    path: '/',
    httpOnly: true,
    sameSite: 'Lax',
  }]);
  const seen = await openProfile(page);

  const button = page.getByRole('button', { name: 'Выйти из аккаунта' });
  await expect(button).toBeVisible();
  await button.click();
  await expect(page).toHaveURL(/\/login$/);
  expect(seen).toHaveLength(1);
  expect(seen[0].method).toBe('POST');
  expect(seen[0].headers.cookie).toContain('roxy_web_session=');
  expect((await context.cookies()).some((cookie) => cookie.name === 'roxy_web_session')).toBe(false);
});

test('failed session revoke keeps web visitor signed in and displays a useful error', async ({ page }) => {
  const seen = await openProfile(page, { failLogout: true });
  const button = page.getByRole('button', { name: 'Выйти из аккаунта' });
  await button.click();
  await expect(page.locator('.web-profile-logout-error')).toBeVisible();
  await expect(button).toBeEnabled();
  await expect(page).toHaveURL(/\/mini-app\//);
  expect(seen).toHaveLength(1);
});

test('native Telegram Mini App profile never shows browser logout', async ({ page }) => {
  const seen = await openProfile(page, { telegram: true });
  await expect(page.getByRole('button', { name: 'Выйти из аккаунта' })).toHaveCount(0);
  expect(seen).toHaveLength(0);
});
