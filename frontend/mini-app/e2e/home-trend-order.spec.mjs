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

const trend = {
  id: 'trend_home_order',
  title: 'Тренд под баннером',
  description: 'Проверка порядка блоков',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

async function mockHome(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/referrals/stats') return json({});
    if (path === '/api/v1/referrals/rewards' || path === '/api/v1/referrals/invitations') return json({ items: [] });
    return json({ items: [] });
  });
}

test('home renders the real live trend rail directly below promo', async ({ page }) => {
  await mockHome(page);
  await page.goto('/mini-app/?route=home');

  const home = page.locator('.home-screen');
  const promo = home.locator(':scope > .promo-slider');
  const trendHost = home.locator(':scope > #roxy-home-live-trends');

  await expect(home).toBeVisible();
  await expect(promo).toBeVisible();
  await expect(trendHost).toBeVisible();
  await expect(trendHost.locator('.live-trend-card', { hasText: trend.title })).toBeVisible();

  await expect.poll(() => home.evaluate((node) => {
    const children = Array.from(node.children);
    const promoIndex = children.findIndex((child) => child.classList.contains('promo-slider'));
    const trendIndex = children.findIndex((child) => child.id === 'roxy-home-live-trends');
    return trendIndex === promoIndex + 1;
  })).toBe(true);
});
