import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt', 'image_input', 'aspect_ratio', 'resolution', 'output_format'],
  price_rox: '15.00',
  ui_schema: {
    groups: [
      { id: 'prompt', title: 'Описание' },
      { id: 'references', title: 'Референсы' },
      { id: 'output', title: 'Результат' },
    ],
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true },
      { name: 'image_input', label: 'Изображения', control: 'files', group: 'references', accept: 'image/*', required: false, max_items: 14 },
      { name: 'aspect_ratio', label: 'Соотношение сторон', control: 'combobox', group: 'output', suggestions: ['auto', '1:1'], required: false },
      { name: 'resolution', label: 'Разрешение', control: 'combobox', group: 'output', suggestions: ['1K', '2K'], required: false },
      { name: 'output_format', label: 'Формат', control: 'combobox', group: 'output', suggestions: ['png', 'jpg'], required: false },
    ],
    defaults: { aspect_ratio: 'auto', resolution: '1K', output_format: 'png' },
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
  preview_url: null,
  likes_count: 12,
  shares_count: 2,
  comments_count: 1,
  liked_by_me: false,
  is_mine: true,
  publication_scope: 'feed',
  is_profile_visible: true,
  is_public_feed: true,
  surface: 'feed',
  feed_published_at: '2026-08-22T10:05:00Z',
};

const referenceTrend = {
  id: 'trend_ref',
  title: 'Два кадра',
  description: 'Сценарий с двумя референсами',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'image', min: 2, max: 2 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

const simpleTrend = {
  id: 'trend_simple',
  title: 'Неоновый портрет',
  description: 'Быстрый старт',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

const viewports = [
  { width: 320, height: 568 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
];

async function mockApi(page, { onboarding = false, bootDelay = 0 } = {}) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {},
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
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [family] });
    if (path === '/api/v1/generations/quote') return json({ cost_rox: '15.00', cost_rub: '150.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') return json({ id: 'gen_new', status: 'queued', cost_rox: '15.00' }, 202);
    if (path === '/api/v1/generations') return json({ items: [generation], has_more: false, next_before: null });
    if (path === '/api/v1/generations/gen_1/action-context') return json({
      generation: { id: 'gen_1', status: 'succeeded', media_type: 'image', model_id: model.id, model_title: model.title, prompt: generation.prompt },
      action: { id: 'remix', label: 'Повторить', derivative: true },
      candidate_models: [model],
      defaults: { model_id: model.id, prompt: 'Сделай вечерний свет', parameters: { aspect_ratio: '1:1', resolution: '1K', output_format: 'png' }, billing_seconds: null },
      source_url: 'https://cdn.roxy.test/source.jpg',
      source_references: { images: [] },
      edit_presets: [],
    });
    if (path === '/api/v1/generations/gen_1/actions/remix') return json({ id: 'gen_new', status: 'queued' }, 202);
    if (path.startsWith('/api/v1/generations/')) return json(generation);

    if (path === '/api/v1/feed') return json({ items: [feedCard] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [feedCard] });
    if (path.includes('/comments')) return json({ items: [] });
    if (path.includes('/publish')) return json({ item: feedCard, publication_scope: 'feed' });

    if (path === '/api/v1/trends') return json({ items: [simpleTrend, referenceTrend] });
    if (path === '/api/v1/trends/trend_ref') return json(referenceTrend);
    if (path === '/api/v1/trends/trend_simple') return json(simpleTrend);
    if (path.startsWith('/api/v1/trends/') && path.endsWith('/run')) return json({ id: 'trend_generation', status: 'queued', cost_rox: '15.00' }, 202);

    if (path === '/api/v1/prompt-tools') return json({ items: [
      { id: 'prompt_builder', enabled: true, cost_credits: '1.00' },
      { id: 'video_prompt', enabled: true, cost_credits: '30.00' },
    ] });
    if (path.startsWith('/api/v1/prompt-tools/')) return json({ id: 'prompt_task', status: 'succeeded', result: { prompt_ru: 'Готово' } });

    if (path === '/api/v1/uploads/kie') return json({ url: `https://cdn.roxy.test/ref-${Date.now()}.jpg` }, 201);
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/references/touch') return json({ touched: 0 });

    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy?start=ref_777', first_line: 2, second_line: 1, partner_balance_rub: '1200' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });

    if (path === '/api/v1/me/transactions') return json([]);
    if (path === '/api/v1/payments/card/packages') return json({ packages: { starter: { credits: '100', prices: { RUB: '100' } } } });
    if (path === '/api/v1/payments/card/checkout') return json({ payment_url: 'https://pay.test' });

    if (path === '/api/v1/batch-generations' && method === 'GET') return json({ items: [] });
    if (path === '/api/v1/batch-generations/quote') return json({ input_count: 2, per_item_cost_credits: '15.00', total_cost_credits: '30.00' });
    if (path === '/api/v1/batch-generations' && method === 'POST') return json({ id: 'batch_1', status: 'running', model_id: model.id, prompt: 'x', input_count: 2, succeeded_count: 0, failed_count: 0, active_count: 2, progress_percent: 0, total_charged_credits: '30.00', items: [] }, 202);

    return json({ items: [] });
  });

  await page.route('https://cdn.roxy.test/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64') }));
}

async function assertViewport(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await expect(page.locator('[data-roxy-back-button]')).toHaveCount(0);
}

const surfaces = [
  { id: 'home', url: '/mini-app/?route=home', ready: '.home-screen' },
  { id: 'feed', url: '/mini-app/?route=feed', ready: '.screen-head >> text=Работы сообщества' },
  { id: 'catalog', url: '/mini-app/?route=catalog', ready: '.screen-head >> text=Тренды и модели' },
  { id: 'create', url: '/mini-app/?route=create', ready: '.create-screen' },
  { id: 'history', url: '/mini-app/?route=history', ready: '.screen-head >> text=Все работы' },
  { id: 'profile', url: '/mini-app/?route=profile', ready: '.profile-screen' },
  { id: 'partners', url: '/mini-app/?route=partners', ready: '.screen-head >> text=Кабинет автора' },
  { id: 'generation-action', url: '/mini-app/?route=generation-action&generation=gen_1&action=remix', ready: '.generation-action-screen' },
  { id: 'prompt-tools', url: '/mini-app/prompt-tools/?mode=image', ready: 'text=Промпт по фото / видео' },
  { id: 'batch', url: '/mini-app/batch/', ready: 'text=Пакетная обработка' },
];

for (const viewport of viewports) {
  for (const surface of surfaces) {
    test(`${surface.id} is usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await mockApi(page);
      await page.goto(surface.url);
      await expect(page.locator(surface.ready).first()).toBeVisible();
      await assertViewport(page);
    });
  }

  test(`splash is stable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page, { bootDelay: 350 });
    const navigation = page.goto('/mini-app/?route=home');
    await expect(page.locator('.splash')).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await navigation;
  });

  test(`onboarding is usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page, { onboarding: true });
    await page.goto('/mini-app/?route=home');
    await expect(page.locator('.onboarding-card')).toBeVisible();
    await assertViewport(page);
  });

  test(`preview is usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await page.goto('/mini-app/?route=history');
    await page.locator('.history-card').first().click();
    await expect(page.locator('.preview-card')).toBeVisible();
    await assertViewport(page);
  });

  test(`wallet is usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await page.goto('/mini-app/?route=home');
    await page.locator('.balance-button').click();
    await expect(page.locator('.sheet')).toBeVisible();
    await assertViewport(page);
  });
}

test('Home and Catalog trend cards open the trend launcher', async ({ page }) => {
  await mockApi(page);
  await page.goto('/mini-app/?route=home');
  const homeTrend = page.locator(".home-screen [data-trend-launch='true']", { hasText: simpleTrend.title });
  await expect(homeTrend).toBeVisible();
  await homeTrend.click();
  await expect(page).toHaveURL(/\/mini-app\/trend\/\?id=trend_simple/);

  await page.goto('/mini-app/?route=catalog');
  const catalogTrend = page.locator("[data-trend-launch='true']", { hasText: referenceTrend.title });
  await expect(catalogTrend).toBeVisible();
});

test('reference trend waits for all files and sends them only on explicit Generate', async ({ page }) => {
  await mockApi(page);
  let runBody = null;
  await page.route('**/api/v1/trends/trend_ref/run', async (route) => {
    runBody = route.request().postDataJSON();
    await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ id: 'trend_generation', status: 'queued' }) });
  });
  await page.goto('/mini-app/trend/?id=trend_ref');
  const generate = page.getByRole('button', { name: /Сгенерировать/ });
  await expect(generate).toBeDisabled();

  const picker = page.locator("input[type='file']");
  await picker.setInputFiles([
    { name: 'one.png', mimeType: 'image/png', buffer: Buffer.from('one') },
    { name: 'two.png', mimeType: 'image/png', buffer: Buffer.from('two') },
  ]);
  await expect(page.locator('.tool-file-chip')).toHaveCount(2);
  await expect(generate).toBeEnabled();
  expect(runBody).toBeNull();
  await generate.click();
  await expect.poll(() => runBody?.reference_urls?.length || 0).toBe(2);
});
