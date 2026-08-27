import { expect, test } from '@playwright/test';

const resultImage = 'https://cdn.roxy.local/result.png';
const savedImage = 'https://cdn.roxy.local/saved.png';

const models = [
  {
    id: 'nano-banana-2', title: 'Nano Banana 2', family: 'nano-banana', operation: 'auto', media_type: 'image', price_rox: '25.00',
    known_fields: ['prompt', 'reference_images', 'resolution'], required_fields: ['prompt'], duration_field: null,
    ui_schema: {
      defaults: { prompt: '', resolution: '1K' },
      fields: [
        { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
        { name: 'reference_images', label: 'Референсы', control: 'files', accept: 'image/*', max_items: 4 },
        { name: 'resolution', label: 'Качество', control: 'select', suggestions: ['1K', '2K'] },
      ],
      groups: [{ id: 'main', title: 'Настройки' }],
    },
  },
  {
    id: 'seedance-2.5', title: 'Seedance 2.5', family: 'seedance', operation: 'auto', media_type: 'video', price_rox: '60.00',
    known_fields: ['prompt', 'image_url', 'duration'], required_fields: ['prompt'], duration_field: 'duration',
    ui_schema: {
      defaults: { prompt: '' },
      fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
      groups: [{ id: 'main', title: 'Настройки' }],
      billing_seconds: { label: 'Длительность', min: 1, max: 10, required: true },
    },
  },
  {
    id: 'roxy-music', title: 'ROXY Music', family: 'music', operation: 'text_to_audio', media_type: 'audio', price_rox: '100.00',
    known_fields: ['prompt'], required_fields: ['prompt'], duration_field: null,
    ui_schema: {
      defaults: { prompt: '' },
      fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
      groups: [{ id: 'main', title: 'Настройки' }],
    },
  },
];

const families = [
  { id: 'nano-banana', title: 'Nano Banana', media_types: ['image'], variant_count: 1, price_from_rox: '25.00', variants: [{ id: 'nano-banana-2', title: 'Nano Banana 2', version: '2', media_type: 'image', operation: 'auto', price_rox: '25.00' }] },
  { id: 'seedance', title: 'Seedance', media_types: ['video'], variant_count: 1, price_from_rox: '60.00', variants: [{ id: 'seedance-2.5', title: 'Seedance 2.5', version: '2.5', media_type: 'video', operation: 'auto', price_rox: '60.00' }] },
  { id: 'music', title: 'Музыка', media_types: ['audio'], variant_count: 1, price_from_rox: '100.00', variants: [{ id: 'roxy-music', title: 'ROXY Music', version: 'Music', media_type: 'audio', operation: 'text_to_audio', price_rox: '100.00' }] },
];

const generation = {
  id: 'gen_1', status: 'succeeded', model: models[0], result_url: resultImage, result_urls: [resultImage],
  media: [{ url: resultImage, kind: 'image' }], prompt: 'Портрет в неоне', prompt_actions_allowed: true,
  created_at: '2026-08-27T08:30:00Z', is_profile_visible: false, publication_scope: 'private',
};

const otherFeedCard = {
  ...generation,
  id: 'feed_other_1', preview_url: resultImage, model: 'Nano Banana 2', prompt: '', prompt_actions_allowed: true,
  likes_count: 12, shares_count: 3, comments_count: 2, liked_by_me: false, is_mine: false,
  publication_scope: 'feed', is_profile_visible: true, is_public_feed: true, surface: 'feed',
  feed_published_at: '2026-08-27T08:40:00Z',
  author: { id: 'author_2', display_name: 'Другой автор', username: 'creator' },
};

const publicTrends = [
  { id: 'trend_portrait', title: 'Неоновый портрет', description: 'Готовая идея для яркого аватара', media_type: 'image', preview_url: resultImage, cost_rox: '25.00', model: { title: 'Nano Banana 2' } },
  { id: 'trend_video', title: 'Короткий клип', description: 'Видео для Reels и Shorts', media_type: 'video', preview_url: resultImage, cost_rox: '60.00', model: { title: 'Seedance 2.5' } },
];

const promptTools = [
  { id: 'image_analysis', title: 'Описание по фото', model: 'gemini-2.5-pro', enabled: true, cost_credits: '1.00', retail_cost_credits: '1.00', cost_rub: '1.00' },
  { id: 'prompt_builder', title: 'Описание по идее', model: 'gpt-5-5', enabled: true, cost_credits: '1.00', retail_cost_credits: '1.00', cost_rub: '1.00' },
  { id: 'video_prompt', title: 'Описание по видео', model: 'gemini-2.5-pro', enabled: true, cost_credits: '30.00', retail_cost_credits: '30.00', cost_rub: '30.00' },
];

const savedReference = {
  id: 'ref_saved_1', kind: 'image', label: 'Сохранённый портрет', url: savedImage, filename: 'saved.png',
  content_type: 'image/png', source: 'mini_app_upload', created_at: '2026-08-27T08:10:00Z', updated_at: '2026-08-27T08:10:00Z', last_used_at: '2026-08-27T08:10:00Z',
};

const managedTrend = {
  id: 'trend_manage_1', title: 'Неоновый портрет', is_active: true, created_at: '2026-08-27T08:00:00Z',
  payload: {
    schema_version: 1, description: 'Готовый портрет', media_type: 'image', preview_url: resultImage,
    model_id: 'nano-banana-2', prompt: 'Скрытая инструкция', parameters: {}, input_mode: 'image',
    min_references: 1, max_references: 4, tags: ['trend', 'portrait'], sort_order: 10, usage_count: 4,
  },
};

const viewports = [
  { width: 320, height: 568 },
  { width: 360, height: 740 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
];

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockSystem(page, { admin = false } = {}) {
  const state = { managed: [{ ...managedTrend, payload: { ...managedTrend.payload } }] };

  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=system_audit&user=%7B%22id%22%3A777%7D&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink(url) { window.__lastOpenedLink = url; },
        openTelegramLink(url) { window.__lastOpenedLink = url; },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', is_admin: admin });
    if (path === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/onboarding/complete') return json(route, { enabled: false, completed: true });

    if (path === '/api/v1/generations/models') return json(route, { models, families });
    if (path === '/api/v1/generations/quote') return json(route, { cost_rox: '25.00', cost_rub: '25.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') return json(route, { id: 'gen_new', status: 'queued', cost_rox: '25.00' });
    if (path === '/api/v1/generations') return json(route, { items: [generation], has_more: false, next_before: null });
    if (path.endsWith('/recreate')) return json(route, { model_id: 'nano-banana-2', prompt: 'Портрет в неоне', input_url: null, billing_seconds: null, parameters: { resolution: '1K', reference_images: [savedImage] } });
    if (path.includes('/remix')) return json(route, { id: 'gen_remix', status: 'queued' });
    if (path.startsWith('/api/v1/generations/')) return json(route, generation);

    if (path === '/api/v1/feed') return json(route, { items: [otherFeedCard], has_more: false, next_before: null });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json(route, { author: { display_name: 'QA' }, items: [{ ...generation, id: 'feed_own_1', preview_url: resultImage, model: 'Nano Banana 2', likes_count: 5, shares_count: 1, comments_count: 0, liked_by_me: false, is_mine: true, publication_scope: 'feed', is_profile_visible: true, is_public_feed: true, surface: 'feed' }] });
    if (path.includes('/publish')) return json(route, { publication_scope: 'feed', downgraded_to_profile: false, item: { ...otherFeedCard, id: 'feed_own_1', is_mine: true, prompt: generation.prompt } });
    if (path.includes('/remove')) return json(route, { id: 'feed_own_1', publication_scope: 'private', is_public_feed: false, is_profile_visible: false });
    if (path.includes('/like')) return json(route, { id: 'feed_other_1', surface: 'feed', liked_by_me: method !== 'DELETE', likes_count: method === 'DELETE' ? 12 : 13 });
    if (path.includes('/share')) return json(route, { id: 'feed_other_1', shares_count: 4, link: 'https://t.me/roxy_aicreativebot?start=feed_feed_other_1' });
    if (path.includes('/comments') && method === 'POST') return json(route, { id: 'comment_new', generation_id: 'feed_other_1', surface: 'feed', text: 'Круто', created_at: '2026-08-27T09:00:00Z', author: { display_name: 'QA' } });
    if (path.includes('/comments')) return json(route, { items: [{ id: 'comment_1', generation_id: 'feed_other_1', surface: 'feed', text: 'Отличная работа', created_at: '2026-08-27T08:50:00Z', author: { display_name: 'User' } }] });

    if (path === '/api/v1/trends/manage' && method === 'GET') return json(route, { items: state.managed, models, limits: { max_references: 8, max_tags: 20 } });
    if (path === '/api/v1/trends/manage' && method === 'POST') {
      const body = request.postDataJSON();
      const created = { id: 'trend_created', title: body.title, payload: body.payload, is_active: body.is_active !== false };
      state.managed.unshift(created);
      return json(route, created, 201);
    }
    if (/^\/api\/v1\/trends\/manage\/[^/]+\/activate$/.test(path) && method === 'POST') {
      const id = path.split('/').at(-2);
      const item = state.managed.find((entry) => entry.id === id);
      if (item) item.is_active = true;
      return json(route, item || state.managed[0]);
    }
    if (/^\/api\/v1\/trends\/manage\/[^/]+$/.test(path) && method === 'DELETE') {
      const id = path.split('/').at(-1);
      const item = state.managed.find((entry) => entry.id === id);
      if (item) item.is_active = false;
      return json(route, item || state.managed[0]);
    }
    if (/^\/api\/v1\/trends\/manage\/[^/]+$/.test(path) && method === 'PATCH') {
      const id = path.split('/').at(-1);
      const body = request.postDataJSON();
      const item = state.managed.find((entry) => entry.id === id);
      if (item) Object.assign(item, { title: body.title, payload: body.payload, is_active: body.is_active !== false });
      return json(route, item || state.managed[0]);
    }
    if (path === '/api/v1/trends') return json(route, { items: publicTrends });
    if (path.includes('/api/v1/trends/') && path.endsWith('/run')) return json(route, { id: 'trend_run', status: 'queued', cost_rox: '25.00' });

    if (path === '/api/v1/prompt-tools') return json(route, { admin_free: admin, items: promptTools });
    if (path === '/api/v1/references') return json(route, { items: [savedReference] });
    if (path === '/api/v1/references/touch') return json(route, { touched: 1 });
    if (path.startsWith('/api/v1/references/') && method === 'DELETE') return route.fulfill({ status: 204, body: '' });
    if (path === '/api/v1/uploads/kie') return json(route, { url: savedImage, name: 'preview.png', mime_type: 'image/png', size: 68, replayed: false, reference: savedReference }, 201);

    if (path === '/api/v1/referrals/stats') return json(route, {
      referral_link: 'https://t.me/roxy_aicreativebot?start=ref_777',
      profile_link: 'https://t.me/roxy_aicreativebot?start=profile_777_ref_777',
      first_line: 2, second_line: 1, partner_balance_rub: '1200.00', available: '1200.00',
    });
    if (path === '/api/v1/referrals/invitations') return json(route, { items: [{ user_id: 'invite_1', first_name: 'Анна', username: 'anna', line: 1, joined_at: '2026-08-27T10:00:00Z' }] });
    if (path === '/api/v1/referrals/rewards') return json(route, { items: [{ id: 'reward_1', line: 1, status: 'completed', amount: '75.00', amount_rox: '75.00', net_amount_rox: '75.00', created_at: '2026-08-27T11:00:00Z', source_user: { first_name: 'Анна', username: 'anna' } }] });

    if (path === '/api/v1/me/transactions') return json(route, []);
    if (path === '/api/v1/payments/card/packages') return json(route, { provider: 'card', label: 'Оплата картой', currencies: ['RUB'], packages: { starter: { credits: '100', prices: { RUB: '100' } } } });
    if (path === '/api/v1/payments/card/checkout') return json(route, { id: 'pay_1', status: 'pending', payment_url: 'https://pay.roxy.local/checkout' });
    if (path === '/api/v1/payments') return json(route, { items: [] });

    return json(route, { items: [] });
  });
}

function bottomButton(page, label) {
  return page.locator('.bottom-nav button:visible').filter({ hasText: label }).first();
}

async function boot(page, scenario, viewport) {
  await page.setViewportSize(viewport);
  await mockSystem(page, { admin: Boolean(scenario.admin) });
  await page.goto(`/mini-app/?route=${scenario.route}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('ROXY').first()).toBeVisible({ timeout: 6_000 });
}

async function openTrendAdmin(page) {
  await expect(page.getByRole('button', { name: 'Управлять трендами' })).toBeVisible();
  await page.getByRole('button', { name: 'Управлять трендами' }).click();
  const dialog = page.getByRole('dialog', { name: 'Управление трендами' });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function chooseFamily(page, name) {
  await page.locator('.family-card').filter({ hasText: name }).first().click();
  await expect(page.locator('.bottom-sheet')).toBeVisible();
}

const cases = [
  // Feed / privacy / cross-user actions.
  { name: 'feed-other-hidden-prompt-repeat', route: 'feed', run: async (page) => {
    const surface = page.locator('.tiktok-feed-surface');
    await expect(surface).toBeVisible();
    await expect(surface.getByRole('button', { name: 'Повторить' })).toBeVisible();
    await surface.getByRole('button', { name: 'Повторить' }).click();
    await expect(page.getByText(/Повтор запущен/)).toBeVisible();
  } },
  { name: 'feed-share-fallback-request', route: 'feed', run: async (page) => {
    const request = page.waitForRequest((entry) => entry.url().includes('/share'));
    await page.locator('.tiktok-feed-surface').getByRole('button', { name: 'Поделиться' }).click();
    await request;
    await expect(page.locator('.tiktok-feed-surface').getByRole('button', { name: 'Поделиться' }).locator('small')).toHaveText('4');
  } },
  { name: 'feed-like-unlike-cycle', route: 'feed', run: async (page) => {
    const like = page.locator('.tiktok-feed-surface').getByRole('button', { name: 'Лайк' });
    await like.click();
    await expect(like).toHaveClass(/liked/);
    await like.click();
    await expect(like).not.toHaveClass(/liked/);
  } },
  { name: 'feed-subscriptions-tab', route: 'feed', run: async (page) => {
    const tab = page.locator('.tiktok-feed-surface').getByRole('tab', { name: 'Подписки' });
    await tab.click();
    await expect(tab).toHaveAttribute('aria-selected', 'true');
  } },
  { name: 'feed-hidden-prompt-details', route: 'feed', run: async (page) => {
    const surface = page.locator('.tiktok-feed-surface');
    await surface.getByRole('button', { name: 'Ещё', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Действия с работой' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Открыть результат' })).toBeVisible();
    await expect(dialog.getByText('Скрытая инструкция')).toHaveCount(0);
  } },
  { name: 'feed-comments-load', route: 'feed', run: async (page) => {
    await page.locator('.tiktok-feed-surface').getByRole('button', { name: 'Комментарии' }).click();
    const dialog = page.getByRole('dialog', { name: 'Комментарии' });
    await expect(dialog.getByText('Отличная работа')).toBeVisible();
  } },

  // Inline trend admin parity with tanyapi, protected by real admin surface state.
  { name: 'trend-admin-button-visible', route: 'catalog', admin: true, run: async (page) => {
    await expect(page.getByRole('button', { name: 'Управлять трендами' })).toBeVisible();
  } },
  { name: 'trend-admin-hidden-for-user', route: 'catalog', admin: false, run: async (page) => {
    await expect(page.getByRole('button', { name: 'Управлять трендами' })).toHaveCount(0);
  } },
  { name: 'trend-admin-manager-list', route: 'catalog', admin: true, run: async (page) => {
    const dialog = await openTrendAdmin(page);
    await expect(dialog.getByText('Неоновый портрет')).toBeVisible();
    await expect(dialog.getByText('Активен')).toBeVisible();
  } },
  { name: 'trend-admin-create-validation', route: 'catalog', admin: true, run: async (page) => {
    const dialog = await openTrendAdmin(page);
    await dialog.getByRole('button', { name: /Новый тренд/ }).click();
    const form = page.getByRole('dialog', { name: 'Добавить тренд' });
    await form.getByRole('button', { name: 'Опубликовать тренд' }).click();
    await expect(form.getByRole('alert')).toContainText('Добавьте название');
  } },
  { name: 'trend-admin-preview-upload', route: 'catalog', admin: true, run: async (page) => {
    const dialog = await openTrendAdmin(page);
    await dialog.getByRole('button', { name: /Новый тренд/ }).click();
    const form = page.getByRole('dialog', { name: 'Добавить тренд' });
    await form.locator('input[type="file"]').setInputFiles({ name: 'preview.png', mimeType: 'image/png', buffer: Buffer.from('preview') });
    await expect(form.getByAltText('Превью тренда')).toBeVisible();
    await expect(form.getByText('Фото или видео. Файл сохраняется постоянно.')).toBeVisible();
  } },
  { name: 'trend-admin-hide-restore', route: 'catalog', admin: true, run: async (page) => {
    const dialog = await openTrendAdmin(page);
    await dialog.getByRole('button', { name: 'Скрыть' }).click();
    await expect(dialog.getByText('Скрыт')).toBeVisible();
    await dialog.getByRole('button', { name: 'Вернуть' }).click();
    await expect(dialog.getByText('Активен')).toBeVisible();
  } },

  // Dynamic catalog and pricing from backend/admin pricing contract.
  { name: 'catalog-image-variant-price', route: 'catalog', run: async (page) => {
    await page.locator('.model-card').filter({ hasText: 'Nano Banana' }).last().click();
    await expect(page.locator('.variant-row').filter({ hasText: 'Nano Banana 2' })).toContainText('25 ROX');
  } },
  { name: 'catalog-video-variant-price', route: 'catalog', run: async (page) => {
    await page.getByRole('button', { name: 'Видео', exact: true }).click();
    await page.locator('.model-card').filter({ hasText: 'Seedance' }).last().click();
    await expect(page.locator('.variant-row').filter({ hasText: 'Seedance 2.5' })).toContainText('60 ROX');
  } },
  { name: 'catalog-audio-variant-price', route: 'catalog', run: async (page) => {
    await page.getByRole('button', { name: 'Музыка', exact: true }).click();
    await page.locator('.model-card').filter({ hasText: 'Музыка' }).last().click();
    await expect(page.locator('.variant-row').filter({ hasText: 'ROXY Music' })).toContainText('100 ROX');
  } },
  { name: 'catalog-prompt-tools', route: 'catalog', run: async (page) => {
    await expect(page.getByText('Описание по фото')).toBeVisible();
    await expect(page.getByText('Описание по видео').first()).toBeVisible();
  } },
  { name: 'catalog-image-trend-launch', route: 'catalog', run: async (page) => {
    await page.locator("[data-trend-launch='true']", { hasText: 'Неоновый портрет' }).click();
    await expect(page).toHaveURL(/trend_portrait/);
  } },
  { name: 'catalog-video-trend-launch', route: 'catalog', run: async (page) => {
    await page.locator("[data-trend-launch='true']", { hasText: 'Короткий клип' }).click();
    await expect(page).toHaveURL(/trend_video/);
  } },

  // Generation lifecycle, reference memory and history restoration.
  { name: 'create-fresh-prompt', route: 'create', run: async (page) => {
    await expect(page.locator('textarea.control').first()).toHaveValue('');
  } },
  { name: 'create-live-quote', route: 'create', run: async (page) => {
    await page.locator('textarea.control').first().fill('Новый портрет');
    await expect(page.getByText('25 ROX').first()).toBeVisible();
  } },
  { name: 'create-submit-queues', route: 'create', run: async (page) => {
    await page.locator('textarea.control').first().fill('Портрет для обложки');
    const request = page.waitForRequest((entry) => new URL(entry.url()).pathname === '/api/v1/generations' && entry.method() === 'POST');
    await page.getByRole('button', { name: /Создать · 25 ROX/ }).click();
    await request;
    await expect(page.locator('.preview-card')).toBeVisible();
  } },
  { name: 'create-saved-reference', route: 'create', run: async (page) => {
    await page.locator('.saved-reference-pick').first().click();
    await expect(page.locator('.upload-list')).toContainText('saved.png');
  } },
  { name: 'history-settings-restore', route: 'history', run: async (page) => {
    await page.locator('.history-card').first().click();
    await page.getByRole('button', { name: 'Использовать настройки' }).click();
    await expect(page.locator('textarea.control').first()).toHaveValue('Портрет в неоне');
  } },
  { name: 'create-video-duration-contract', route: 'create', run: async (page) => {
    await page.getByRole('button', { name: 'Видео', exact: true }).click();
    await chooseFamily(page, 'Seedance');
    await page.locator('.variant-row').first().click();
    await expect(page.getByText('Длительность')).toBeVisible();
  } },

  // Partner links, publication and wallet/payment surfaces.
  { name: 'partner-referral-start-fallback', route: 'partners', run: async (page) => {
    await expect(page.getByText('https://t.me/roxy_aicreativebot?start=ref_777')).toBeVisible();
  } },
  { name: 'partner-profile-start-fallback', route: 'partners', run: async (page) => {
    await expect(page.getByText('https://t.me/roxy_aicreativebot?start=profile_777_ref_777')).toBeVisible();
  } },
  { name: 'partner-reward-ledger', route: 'partners', run: async (page) => {
    await expect(page.getByText('+75 ROX')).toBeVisible();
    await expect(page.getByText('@anna')).toBeVisible();
  } },
  { name: 'profile-publish-feed', route: 'profile', run: async (page) => {
    await page.locator('.media-tile').first().click();
    const request = page.waitForRequest((entry) => entry.url().includes('/publish'));
    await page.getByRole('button', { name: 'В ленту + профиль' }).click();
    await request;
    await expect(page.getByText('Работа опубликована в ленте и профиле')).toBeVisible();
  } },
  { name: 'wallet-card-package', route: 'home', run: async (page) => {
    await page.locator('.balance-button').click();
    await expect(page.getByText('Выберите пакет')).toBeVisible();
    await expect(page.getByText(/100 ROX/).first()).toBeVisible();
  } },
  { name: 'bottom-nav-route-integrity', route: 'home', run: async (page) => {
    const nav = page.getByRole('navigation', { name: 'Основная навигация' });
    await expect(nav.locator('button:visible')).toHaveCount(5);
    await bottomButton(page, 'Лента').click();
    await expect(page.locator('.tiktok-feed-surface')).toBeVisible();
  } },
];

const scenarios = viewports.flatMap((viewport) => cases.map((scenario) => ({ viewport, scenario })));
if (cases.length !== 30 || viewports.length !== 5 || scenarios.length !== 150) {
  throw new Error(`ROXY system-risk matrix must be 30 x 5 = 150, got ${cases.length} x ${viewports.length} = ${scenarios.length}`);
}

test.describe('ROXY Mini App — 150 additional system-risk scenarios', () => {
  test.describe.configure({ mode: 'parallel' });

  for (const [index, entry] of scenarios.entries()) {
    test(`${String(index + 301).padStart(3, '0')} ${entry.scenario.name} @ ${entry.viewport.width}x${entry.viewport.height}`, async ({ page }) => {
      await boot(page, entry.scenario, entry.viewport);
      await entry.scenario.run(page);
    });
  }
});
