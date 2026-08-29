import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: { groups: [], fields: [], defaults: {} },
};

const family = {
  id: 'nano_banana',
  family: 'nano_banana',
  title: 'Nano Banana',
  media_types: ['image'],
  variant_count: 1,
  price_from_rox: '15.00',
  variants: [{ id: model.id, title: model.title, version: '2', media_type: 'image', operation: 'auto', price_rox: '15.00' }],
};

async function mockWebView(page) {
  await page.addInitScript(() => {
    window.__telegramBackVisible = false;
    window.__telegramBackHandler = null;
    window.__telegramClosed = false;
    window.__pressTelegramBack = () => window.__telegramBackHandler?.();
    window.Telegram = {
      WebApp: {
        initData: 'query_id=back-navigation&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        contentSafeAreaInset: { top: 24, bottom: 34, left: 0, right: 0 },
        viewportStableHeight: window.innerHeight,
        ready() {},
        expand() {},
        close() { window.__telegramClosed = true; },
        onEvent() {},
        offEvent() {},
        openLink() {},
        BackButton: {
          show() { window.__telegramBackVisible = true; },
          hide() { window.__telegramBackVisible = false; },
          onClick(callback) { window.__telegramBackHandler = callback; },
          offClick(callback) {
            if (window.__telegramBackHandler === callback) window.__telegramBackHandler = null;
          },
        },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({
      id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00',
      profile_link: 'https://t.me/roxy?start=profile_777',
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [family] });
    if (path === '/api/v1/generations' && method === 'GET') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [] });
    if (path === '/api/v1/referrals/stats') return json({
      referral_link: 'https://t.me/roxy?start=ref_777', profile_link: 'https://t.me/roxy?start=profile_777',
      first_line: 0, second_line: 0, partner_balance_rub: '0',
    });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path.endsWith('/packages')) return json({ configured: false, packages: {} });
    return json({ items: [] });
  });
}

async function pressTelegramBack(page) {
  await expect.poll(() => page.evaluate(() => typeof window.__telegramBackHandler === 'function')).toBe(true);
  await page.evaluate(() => window.__pressTelegramBack());
}

test('Catalog leaves Telegram Close chrome visible while other main surfaces use Back', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await mockWebView(page);
  await page.goto('/mini-app/?route=catalog');
  await expect(page.locator('.bottom-nav')).toBeVisible();
  await expect(page.locator('button[data-roxy-customer-route="catalog"]')).toHaveAttribute('aria-current', 'page');
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(false);

  await page.locator('button[data-roxy-customer-route="feed"]').click();
  await expect(page).toHaveURL(/\/mini-app\/?\?route=feed/);
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(true);

  await page.locator('button[data-roxy-customer-route="catalog"]').click();
  await expect(page).toHaveURL(/\/mini-app\/?\?route=catalog/);
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(false);
});

test('Profile -> Wallet -> native Back returns to Profile, then Home, then closes WebView', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await mockWebView(page);
  await page.goto('/mini-app/?route=home');
  await expect(page.locator('.bottom-nav')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(true);

  await page.locator('button[data-roxy-customer-route="profile"]').click();
  await expect(page).toHaveURL(/\/mini-app\/?\?route=profile/);
  await expect(page.locator('.profile-screen')).toBeVisible();

  await page.locator('.profile-screen button[aria-label="Баланс"]').click();
  await expect(page).toHaveURL(/\/mini-app\/payments\//);
  await expect(page.locator('.standalone-app')).toBeVisible();

  await pressTelegramBack(page);
  await expect(page).toHaveURL(/\/mini-app\/?\?route=profile/);
  await expect(page.locator('.profile-screen')).toBeVisible();

  await pressTelegramBack(page);
  await expect(page).toHaveURL(/\/mini-app\/?\?route=home/);

  await pressTelegramBack(page);
  await expect.poll(() => page.evaluate(() => window.__telegramClosed)).toBe(true);
});

test('direct Profile launch backs to Home without escaping app history', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await mockWebView(page);
  await page.goto('/mini-app/?route=profile');
  await expect(page.locator('.profile-screen')).toBeVisible();

  await pressTelegramBack(page);
  await expect(page).toHaveURL(/\/mini-app\/?\?route=home/);
  await expect(page.locator('.bottom-nav')).toBeVisible();

  await pressTelegramBack(page);
  await expect.poll(() => page.evaluate(() => window.__telegramClosed)).toBe(true);
});