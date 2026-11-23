import { expect, test } from '@playwright/test';

const STORAGE_KEY = '__roxy_browser_init_data_v1';
const BROWSER_TOKEN = 'query_id=browser-signout&hash=fixture';
const NATIVE_TOKEN = 'query_id=native-telegram&hash=fixture';

async function openWebProfile(page, { native = false, account = false } = {}) {
  await page.addInitScript(({ browserToken, nativeToken, storageKey, nativeLaunch }) => {
    // The login fixture must not re-authenticate after the logout navigation.
    if (!sessionStorage.getItem('__roxy_logout_fixture_installed')) {
      sessionStorage.setItem('__roxy_logout_fixture_installed', '1');
      sessionStorage.setItem(storageKey, JSON.stringify({
        initData: browserToken,
        expiresAt: Date.now() + 60_000,
      }));
    }
    window.Telegram = { WebApp: {
      initData: nativeLaunch ? nativeToken : '',
      initDataUnsafe: nativeLaunch
        ? { user: { id: 777, first_name: 'Telegram QA' } }
        : {},
      ready() {}, expand() {}, onEvent() {}, offEvent() {}, close() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  }, { browserToken: BROWSER_TOKEN, nativeToken: NATIVE_TOKEN, storageKey: STORAGE_KEY, nativeLaunch: native });

  await page.route('**/api/v1/**', (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const auth = route.request().headers()['x-telegram-init-data'];
    if (pathname === '/api/v1/me') {
      if (auth !== (native ? NATIVE_TOKEN : BROWSER_TOKEN)) {
        return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}' });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: '11111111-1111-4111-8111-111111111111',
        telegram_id: 777,
        first_name: 'QA',
        username: 'qa',
        balance_rox: '100',
      }) });
    }
    if (pathname === '/api/v1/generations/models') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"models":[],"families":[]}' });
    }
    if (pathname === '/api/v1/browser-auth/config') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"bot_username":"RoxyTestBot"}' });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[],"active":false}' });
  });

  await page.goto(account ? '/mini-app/account/' : '/mini-app/?route=profile', { waitUntil: 'domcontentloaded' });
}

test('signed-in website profile offers logout and clears browser credentials', async ({ page }) => {
  await openWebProfile(page);
  const logout = page.getByRole('button', { name: 'Выйти из аккаунта' });
  await expect(logout).toBeVisible();
  await logout.click();
  await expect(page).toHaveURL(/\/mini-app\/$/);
  await expect(page.getByRole('heading', { name: 'Создавай фото и видео с AI' })).toBeVisible();
  expect(await page.evaluate((key) => sessionStorage.getItem(key), STORAGE_KEY)).toBeNull();
});

test('standalone web account also exposes logout', async ({ page }) => {
  await openWebProfile(page, { account: true });
  await expect(page.getByRole('button', { name: 'Выйти из аккаунта' })).toBeVisible();
});

test('native Telegram profile never offers website logout even with leftover browser credential', async ({ page }) => {
  await openWebProfile(page, { native: true });
  await expect(page.locator('.profile-screen')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Выйти из аккаунта' })).toHaveCount(0);
});
