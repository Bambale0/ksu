import { expect, test } from '@playwright/test';

const TREND_ID = '12345678-1234-4234-8234-123456789abc';
const START_PARAM = `trend_${TREND_ID}`;

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

async function mockStickyTrendWebView(page) {
  await page.addInitScript((startParam) => {
    window.__telegramBackVisible = false;
    window.__telegramBackHandler = null;
    window.__pressTelegramBack = () => window.__telegramBackHandler?.();
    const recordBack = (value) => {
      const key = '__trend_back_events';
      const previous = window.sessionStorage.getItem(key) || '';
      window.sessionStorage.setItem(key, `${previous}${value}`);
    };
    window.Telegram = {
      WebApp: {
        initData: 'query_id=trend-back&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' }, start_param: startParam },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: {
          show() { window.__telegramBackVisible = true; recordBack('S'); },
          hide() { window.__telegramBackVisible = false; recordBack('H'); },
          onClick(callback) { window.__telegramBackHandler = callback; },
          offClick(callback) { if (window.__telegramBackHandler === callback) window.__telegramBackHandler = null; },
        },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, START_PARAM);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === `/api/v1/trends/${TREND_ID}` && method === 'GET') return json({
      id: TREND_ID, title: 'Плёночный портрет', description: 'Мягкий плёночный портрет',
      media_type: 'image', preview_url: null, model: { id: model.id, title: model.title },
      cost_rox: '15.00', admin_free: false, reference_requirements: { min: 0, max: 0 },
    });
    if (path === '/api/v1/me') return json({
      id: 'user_1', telegram_id: 777, first_name: 'QA', balance_rox: '150.00',
      profile_link: 'https://t.me/roxy?start=profile_777', is_admin: false,
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [family] });
    if (path === '/api/v1/generations' && method === 'GET') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: '', profile_link: '', first_line: 0, second_line: 0, partner_balance_rub: '0' });
    if (path === '/api/v1/referrals/rewards' || path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path.endsWith('/packages')) return json({ configured: false, packages: {} });
    return json({ items: [] });
  });
}

async function pressTelegramBack(page) {
  await expect.poll(() => page.evaluate(() => typeof window.__telegramBackHandler === 'function')).toBe(true);
  await page.evaluate(() => window.__pressTelegramBack());
}

test('shared trend keeps Back through the gate and native Back returns once to Home catalog', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await mockStickyTrendWebView(page);

  await page.goto(`/mini-app/?startapp=${START_PARAM}`);
  await expect(page).toHaveURL(new RegExp(`/mini-app/trend/\\?id=${TREND_ID}$`));
  await expect(page.getByRole('heading', { name: 'Плёночный портрет' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(true);
  await expect.poll(() => page.evaluate(() => window.sessionStorage.getItem('__trend_back_events') || '')).toMatch(/^S/);

  await pressTelegramBack(page);
  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  const home = page.locator('.bottom-nav button[data-roxy-customer-route="home"]');
  await expect(home).toHaveAttribute('aria-current', 'page');
  await expect(home.locator('small')).toHaveText('Каталог');
  await page.waitForTimeout(500);
  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expect(page.getByText('Открываю тренд…')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.__telegramBackVisible)).toBe(false);
});
