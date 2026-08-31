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
    const request = route.request();
    const path = new URL(request.url()).pathname;
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

test('home puts trends directly below promo before creation formats', async ({ page }) => {
  await mockHome(page);
  await page.goto('/mini-app/?route=home');
  await expect(page.locator('.home-screen')).toBeVisible();
  await expect(page.locator('.home-screen .model-card', { hasText: trend.title })).toBeVisible();

  await expect.poll(() => page.locator('.home-screen').evaluate((home) => {
    const children = Array.from(home.children);
    const promo = children.findIndex((node) => node.classList.contains('promo-slider'));
    const section = (kicker) => children.findIndex((node) => node.querySelector('.kicker')?.textContent?.trim() === kicker);
    const trends = section('Тренды');
    const studio = section('Студия');
    return {
      trendsDirectlyAfterPromo: trends === promo + 1,
      studioAfterTrendRail: studio > trends + 1,
    };
  })).toEqual({ trendsDirectlyAfterPromo: true, studioAfterTrendRail: true });
});

test('catalog puts live trends directly below promo before feature catalog', async ({ page }) => {
  await mockHome(page);
  await page.goto('/mini-app/?route=catalog');

  const catalog = page.locator('.roxy-catalog-feature-mode');
  await expect(catalog).toBeVisible();
  await expect(page.locator('#roxy-live-trends .live-trend-card', { hasText: trend.title })).toBeVisible();

  await expect.poll(() => catalog.evaluate((screen) => {
    const children = Array.from(screen.children);
    const promo = screen.querySelector(':scope > .promo-carousel');
    const trends = screen.querySelector(':scope > #roxy-live-trends');
    const featureHub = screen.querySelector(':scope > #roxy-catalog-feature-hub');
    const trendsIndex = trends ? children.indexOf(trends) : -1;
    const featureHubIndex = featureHub ? children.indexOf(featureHub) : -1;
    return {
      trendsDirectlyAfterPromo: Boolean(promo && trends && promo.nextElementSibling === trends),
      featureCatalogAfterTrends: trendsIndex >= 0 && featureHubIndex > trendsIndex,
    };
  })).toEqual({ trendsDirectlyAfterPromo: true, featureCatalogAfterTrends: true });
});
