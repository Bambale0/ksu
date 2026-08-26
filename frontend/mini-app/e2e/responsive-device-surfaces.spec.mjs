import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: {
    groups: [{ id: 'prompt', title: 'Описание' }],
    fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true }],
    defaults: {},
  },
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

const generation = {
  id: 'gen_1',
  status: 'succeeded',
  model,
  prompt: 'Неоновый портрет',
  result_url: null,
  result_urls: [],
  media: [],
  prompt_actions_allowed: true,
  publication_scope: 'private',
  is_profile_visible: false,
  is_public_feed: false,
  created_at: '2026-08-22T10:00:00Z',
};

const feedCard = {
  ...generation,
  id: 'feed_1',
  model: model.title,
  likes_count: 12,
  shares_count: 2,
  comments_count: 1,
  liked_by_me: false,
  is_mine: true,
  publication_scope: 'feed',
  is_profile_visible: true,
  is_public_feed: true,
  surface: 'feed',
  feed_published_at: generation.created_at,
};

const trend = {
  id: 'trend_1',
  title: 'Неоновый портрет',
  description: 'Быстрый старт',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

async function mockRoxy(page, { safeArea = { top: 0, bottom: 0, left: 0, right: 0 } } = {}) {
  await page.addInitScript((insets) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=responsive&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        contentSafeAreaInset: insets,
        viewportStableHeight: window.innerHeight,
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, safeArea);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [family] });
    if (path === '/api/v1/generations/quote') return json({ cost_rox: '15.00', cost_rub: '150.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') return json({ id: 'gen_new', status: 'queued', cost_rox: '15.00' }, 202);
    if (path === '/api/v1/generations') return json({ items: [generation], has_more: false, next_before: null });
    if (path === '/api/v1/generations/gen_1/action-context') return json({
      generation: { id: generation.id, status: generation.status, media_type: 'image', model_id: model.id, model_title: model.title, prompt: generation.prompt },
      action: { id: 'remix', label: 'Повторить', derivative: true },
      candidate_models: [model],
      defaults: { model_id: model.id, prompt: generation.prompt, parameters: {}, billing_seconds: null },
      source_url: null,
      source_references: { images: [] },
      edit_presets: [],
    });
    if (path.startsWith('/api/v1/generations/')) return json(generation);
    if (path === '/api/v1/feed') return json({ items: [feedCard] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [feedCard] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/trends/trend_1') return json(trend);
    if (path.startsWith('/api/v1/prompt-tools')) return json(path === '/api/v1/prompt-tools' ? { items: [] } : { id: 'prompt_task', status: 'succeeded', result: {} });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/references/touch') return json({ touched: 0 });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy?start=ref_777', first_line: 2, second_line: 1, partner_balance_rub: '1200' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path === '/api/v1/payments/card/packages') return json({ packages: { starter: { credits: '100', prices: { RUB: '100' } } } });
    if (path === '/api/v1/batch-generations') return json({ items: [] });
    if (path === '/api/v1/batch-generations/quote') return json({ input_count: 1, per_item_cost_credits: '15.00', total_cost_credits: '15.00' });
    return json({ items: [] });
  });
}

async function expectNoHorizontalOverflow(page) {
  await expect.poll(() => page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    viewport: window.innerWidth,
  }))).toMatchObject({
    doc: await page.evaluate(() => window.innerWidth),
    body: await page.evaluate(() => window.innerWidth),
  });
}

const devices = [
  { name: 'iPhone SE', viewport: { width: 320, height: 568 } },
  { name: 'iPhone 15', viewport: { width: 393, height: 852 } },
  { name: 'iPhone 15 Pro Max', viewport: { width: 430, height: 932 } },
  { name: 'iPhone landscape', viewport: { width: 852, height: 393 } },
  { name: 'iPad mini', viewport: { width: 768, height: 1024 } },
  { name: 'iPad Air', viewport: { width: 820, height: 1180 } },
  { name: 'iPad Pro 11', viewport: { width: 834, height: 1194 } },
  { name: 'iPad Pro landscape', viewport: { width: 1194, height: 834 } },
];

const rootRoutes = ['home', 'feed', 'catalog', 'create', 'history', 'profile', 'partners'];

for (const device of devices) {
  for (const route of rootRoutes) {
    test(`${route} fits ${device.name}`, async ({ page }) => {
      await page.setViewportSize(device.viewport);
      await mockRoxy(page);
      await page.goto(`/mini-app/?route=${route}`);
      await expect(page.locator('.roxy-app')).toBeVisible();
      await expect(page.locator('main')).not.toBeEmpty();
      await expectNoHorizontalOverflow(page);

      const nav = page.locator('.bottom-nav');
      await expect(nav).toBeVisible();
      const navBox = await nav.boundingBox();
      expect(navBox).not.toBeNull();
      expect(navBox.x).toBeGreaterThanOrEqual(0);
      expect(navBox.x + navBox.width).toBeLessThanOrEqual(device.viewport.width + 1);

      const topbar = page.locator('.topbar');
      const topbarBox = await topbar.boundingBox();
      expect(topbarBox).not.toBeNull();
      expect(topbarBox.x).toBeGreaterThanOrEqual(0);
      expect(topbarBox.x + topbarBox.width).toBeLessThanOrEqual(device.viewport.width + 1);
    });
  }
}

test('Telegram safe area keeps native iPhone env fallback', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await mockRoxy(page, { safeArea: { top: 24, bottom: 34, left: 0, right: 0 } });
  await page.goto('/mini-app/?route=home');
  const vars = await page.evaluate(() => ({
    top: document.documentElement.style.getPropertyValue('--tg-safe-top'),
    bottom: document.documentElement.style.getPropertyValue('--tg-safe-bottom'),
  }));
  expect(vars.top).toContain('env(safe-area-inset-top');
  expect(vars.bottom).toContain('env(safe-area-inset-bottom');
});

test('tablet home uses tablet grid instead of phone carousel', async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=home');
  await expect(page.locator('.home-screen')).toBeVisible();
  expect(await page.locator('.format-grid').evaluate((node) => getComputedStyle(node).display)).toBe('grid');
  const shellWidth = await page.locator('.main-shell').evaluate((node) => node.getBoundingClientRect().width);
  expect(shellWidth).toBeGreaterThan(780);
});

test('landscape iPhone keeps navigation compact', async ({ page }) => {
  await page.setViewportSize({ width: 852, height: 393 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=home');
  const navBox = await page.locator('.bottom-nav').boundingBox();
  expect(navBox).not.toBeNull();
  expect(navBox.height).toBeLessThanOrEqual(68);
});

test('tablet wallet becomes a contained modal and stays inside viewport', async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=home');
  await page.locator('.balance-button').click();
  const sheet = page.locator('.sheet');
  await expect(sheet).toBeVisible();
  const box = await sheet.boundingBox();
  expect(box).not.toBeNull();
  expect(box.width).toBeLessThanOrEqual(780);
  expect(box.x).toBeGreaterThan(20);
  expect(box.y).toBeGreaterThan(20);
  expect(box.x + box.width).toBeLessThanOrEqual(814);
  expect(box.y + box.height).toBeLessThanOrEqual(1174);
  expect(await sheet.evaluate((node) => getComputedStyle(node).borderBottomWidth)).not.toBe('0px');
});
