import { expect, test } from '@playwright/test';

const STORAGE_KEY = '__roxy_browser_init_data_v1';
const BROWSER_TOKEN = 'query_id=browser-signout&hash=fixture';
const NATIVE_TOKEN = 'query_id=native-telegram&hash=fixture';

// Reuse the complete live /me/overview contract from customer-backend-parity.
const WEB_OVERVIEW = {
  account: { username: 'qa_user', first_name: 'QA', last_name: null, created_at: '2026-08-20T00:00:00Z' },
  balance: { bonus_rox: '150.00', withdrawable_rox: '100.00', rub_accounting_equivalent: '150.00' },
  generations: { total: 3, statuses: { succeeded: 2, generating: 1 } },
  payments: { total: 1, currencies: { RUB: { count: 1, successful_count: 1, successful_amount: '100.00', credited_rox: '110.00' } } },
  support: { total: 1, statuses: { open: 1 } },
  partner: { first_line: 2, second_line: 1, available_rub: '1200.00', pending_rub: '300.00', withdrawable_rox: '1200.00', withdrawals: {} },
  social: { following: 2, followers: 4 },
  notifications: { unread: 1 },
  preferences: { ui_language: 'auto', notifications_enabled: true, marketing_notifications: false, profile_discoverable: false },
};

async function openWebProfile(page, { native = false, account = false, malformedOverview = false } = {}) {
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
      ...(nativeLaunch ? {openLink(url) { window.__qaOpenedWebUrl = url; }} : {}),
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
    if (pathname === '/api/v1/me/overview') {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(malformedOverview ? { items: [] } : WEB_OVERVIEW) });
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
  await expect(page.getByRole('link', {name:'Вход в веб-версию'})).toHaveAttribute('href','/login?section=profile');
  await logout.click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('body')).toHaveAttribute('data-page','login');
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


test('malformed account overview preserves web logout and shows a retryable error instead of crashing', async ({ page }) => {
  await openWebProfile(page, { account: true, malformedOverview: true });
  await expect(page.getByRole('button', { name: 'Выйти из аккаунта' })).toBeVisible();
  await expect(page.locator('.action-error')).toContainText('Не удалось загрузить профиль');
  await expect(page.getByText('Не удалось открыть приложение. Ошибка уже отправлена в диагностику.')).toHaveCount(0);
});

test('native profile heading opens the real website externally without exposing launch credentials', async ({page})=>{
  await openWebProfile(page,{native:true});
  const link=page.getByRole('link',{name:'Вход в веб-версию'});
  await expect(link).toHaveAttribute('href','/login?section=profile');
  await link.click();
  expect(await page.evaluate(()=>window.__qaOpenedWebUrl)).toBe(new URL('/login?section=profile',page.url()).href);
  expect(new URL(page.url()).pathname).toBe('/mini-app/');
  expect(await page.evaluate(key=>sessionStorage.getItem(key),STORAGE_KEY)).not.toBeNull();
});

test('browser heading reaches public login and keeps the profile session', async ({page})=>{
  await openWebProfile(page);
  await page.getByRole('link',{name:'Вход в веб-версию'}).click();
  await expect(page).toHaveURL(/login\?section=profile$/);
  await expect(page.locator('#login-continue')).toHaveAttribute('href','/mini-app/?route=profile');
  expect(await page.evaluate(key=>JSON.parse(sessionStorage.getItem(key)).initData,STORAGE_KEY)).toBe(BROWSER_TOKEN);
});


test('native balance opens website login for topup, not embedded checkout',async({page})=>{
  await openWebProfile(page,{native:true});
  await page.locator('.balance-button').first().click();
  expect(await page.evaluate(()=>window.__qaOpenedWebUrl)).toBe(new URL('/login?section=payments',page.url()).href);
  await expect(page).toHaveURL(/\/mini-app\/\?route=profile/);
});
