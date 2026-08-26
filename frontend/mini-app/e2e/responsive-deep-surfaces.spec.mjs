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

async function mockApp(page, { onboarding = false, bootDelay = 0 } = {}) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=responsive-deep&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        contentSafeAreaInset: { top: 24, bottom: 20, left: 0, right: 0 },
        viewportStableHeight: window.innerHeight,
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    if (bootDelay) await new Promise((resolve) => setTimeout(resolve, bootDelay));
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: onboarding, completed: !onboarding, title: 'ROXY', body: 'Добро пожаловать' });
    if (path === '/api/v1/onboarding/complete') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [{ id: 'nano_banana', family: 'nano_banana', title: 'Nano Banana', media_types: ['image'], variant_count: 1, price_from_rox: '15.00', variants: [{ id: model.id, title: model.title, version: '2', media_type: 'image', operation: 'auto', price_rox: '15.00' }] }] });
    if (path === '/api/v1/generations/quote') return json({ cost_rox: '15.00', cost_rub: '150.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations') return json(method === 'POST' ? { id: 'gen_new', status: 'queued' } : { items: [generation], has_more: false, next_before: null }, method === 'POST' ? 202 : 200);
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
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/trends/trend_1') return json(trend);
    if (path === '/api/v1/prompt-tools') return json({ items: [{ id: 'prompt_builder', enabled: true, cost_credits: '1.00' }, { id: 'video_prompt', enabled: true, cost_credits: '30.00' }] });
    if (path.startsWith('/api/v1/prompt-tools/')) return json({ id: 'prompt_task', status: 'succeeded', result: { prompt_ru: 'Готово' } });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/references/touch') return json({ touched: 0 });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy?start=ref_777', first_line: 0, second_line: 0, partner_balance_rub: '0' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path === '/api/v1/payments/card/packages') return json({ packages: { starter: { credits: '100', prices: { RUB: '100' } }, plus: { credits: '500', prices: { RUB: '450' } } } });
    if (path === '/api/v1/batch-generations' && method === 'GET') return json({ items: [] });
    if (path === '/api/v1/batch-generations/quote') return json({ input_count: 2, per_item_cost_credits: '15.00', total_cost_credits: '30.00' });
    if (path === '/api/v1/batch-generations' && method === 'POST') return json({ id: 'batch_1', status: 'running', model_id: model.id, prompt: 'x', input_count: 2, succeeded_count: 0, failed_count: 0, active_count: 2, progress_percent: 0, total_charged_credits: '30.00', items: [] }, 202);
    return json({ items: [] });
  });
}

async function noOverflow(page) {
  await expect.poll(() => page.evaluate(() => {
    const viewport = window.innerWidth;
    return document.documentElement.scrollWidth <= viewport + 1 && document.body.scrollWidth <= viewport + 1;
  })).toBe(true);
}

async function insideViewport(locator, viewport) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box.x).toBeGreaterThanOrEqual(-1);
  expect(box.y).toBeGreaterThanOrEqual(-1);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + Math.min(box.height, viewport.height)).toBeLessThanOrEqual(viewport.height + 1);
}

const representativeDevices = [
  { name: 'small iPhone', viewport: { width: 320, height: 568 } },
  { name: 'iPhone landscape', viewport: { width: 852, height: 393 } },
  { name: 'iPad portrait', viewport: { width: 834, height: 1194 } },
  { name: 'iPad landscape', viewport: { width: 1194, height: 834 } },
];

const deepSurfaces = [
  { name: 'generation action', url: '/mini-app/?route=generation-action&generation=gen_1&action=remix', ready: '.generation-action-screen' },
  { name: 'prompt tools', url: '/mini-app/prompt-tools/?mode=image', ready: '.standalone-screen' },
  { name: 'batch', url: '/mini-app/batch/', ready: '.standalone-screen' },
  { name: 'trend', url: '/mini-app/trend/?id=trend_1', ready: '.standalone-screen' },
];

for (const device of representativeDevices) {
  for (const surface of deepSurfaces) {
    test(`${surface.name} fits ${device.name}`, async ({ page }) => {
      await page.setViewportSize(device.viewport);
      await mockApp(page);
      await page.goto(surface.url);
      await expect(page.locator(surface.ready).first()).toBeVisible({ timeout: 10_000 });
      await noOverflow(page);
      const topbar = page.locator('.topbar');
      if (await topbar.count()) await insideViewport(topbar, device.viewport);
    });
  }
}

test('iPad preview is a contained scrollable dialog', async ({ page }) => {
  const viewport = { width: 834, height: 1194 };
  await page.setViewportSize(viewport);
  await mockApp(page);
  await page.goto('/mini-app/?route=history');
  await page.locator('.history-card').first().click();
  const preview = page.locator('.preview-card');
  await expect(preview).toBeVisible();
  await noOverflow(page);
  const box = await preview.boundingBox();
  expect(box).not.toBeNull();
  expect(box.width).toBeLessThanOrEqual(840);
  expect(box.x).toBeGreaterThan(10);
  expect(box.y).toBeGreaterThan(10);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 10);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 10);
});

test('iPad onboarding stays centered and safe-area contained', async ({ page }) => {
  const viewport = { width: 834, height: 1194 };
  await page.setViewportSize(viewport);
  await mockApp(page, { onboarding: true });
  await page.goto('/mini-app/?route=home');
  const card = page.locator('.onboarding-card');
  await expect(card).toBeVisible();
  await noOverflow(page);
  const box = await card.boundingBox();
  expect(box).not.toBeNull();
  expect(box.width).toBeLessThanOrEqual(520);
  expect(box.x).toBeGreaterThan(100);
});

test('iPad splash has no overflow during delayed boot', async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await mockApp(page, { bootDelay: 250 });
  const navigation = page.goto('/mini-app/?route=home');
  await expect(page.locator('.splash')).toBeVisible();
  await noOverflow(page);
  await navigation;
});

test('iPhone preview never hides the close control behind the notch', async ({ page }) => {
  const viewport = { width: 393, height: 852 };
  await page.setViewportSize(viewport);
  await mockApp(page);
  await page.goto('/mini-app/?route=history');
  await page.locator('.history-card').first().click();
  const close = page.locator('.preview-close');
  await expect(close).toBeVisible();
  const box = await close.boundingBox();
  expect(box).not.toBeNull();
  expect(box.y).toBeGreaterThanOrEqual(24);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
});
