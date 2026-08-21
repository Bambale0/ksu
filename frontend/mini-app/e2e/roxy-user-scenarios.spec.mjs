import { expect, test } from '@playwright/test';

const models = [
  {
    id: 'nano-banana-2',
    title: 'Nano Banana 2',
    family: 'nano-banana',
    operation: 'auto',
    media_type: 'image',
    price_rox: '25.00',
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
    id: 'seedance-2.5',
    title: 'Seedance 2.5',
    family: 'seedance',
    operation: 'auto',
    media_type: 'video',
    price_rox: '60.00',
    ui_schema: {
      defaults: { prompt: '' },
      fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
      groups: [{ id: 'main', title: 'Настройки' }],
      billing_seconds: { label: 'Длительность', min: 1, max: 10, required: true },
    },
  },
  {
    id: 'roxy-music',
    title: 'ROXY Music',
    family: 'music',
    operation: 'text_to_audio',
    media_type: 'audio',
    price_rox: '100.00',
    ui_schema: {
      defaults: { prompt: '' },
      fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
      groups: [{ id: 'main', title: 'Настройки' }],
    },
  },
];

const families = [
  {
    id: 'nano-banana',
    title: 'Nano Banana',
    media_types: ['image'],
    variant_count: 1,
    price_from_rox: '25.00',
    variants: [{ id: 'nano-banana-2', title: 'Nano Banana 2', version: '2', media_type: 'image', operation: 'auto', price_rox: '25.00' }],
  },
  {
    id: 'seedance',
    title: 'Seedance',
    media_types: ['video'],
    variant_count: 1,
    price_from_rox: '60.00',
    variants: [{ id: 'seedance-2.5', title: 'Seedance 2.5', version: '2.5', media_type: 'video', operation: 'auto', price_rox: '60.00' }],
  },
  {
    id: 'music',
    title: 'Музыка',
    media_types: ['audio'],
    variant_count: 1,
    price_from_rox: '100.00',
    variants: [{ id: 'roxy-music', title: 'ROXY Music', version: 'Music', media_type: 'audio', operation: 'text_to_audio', price_rox: '100.00' }],
  },
];

const resultImage = 'https://cdn.roxy.local/result.png';
const savedImage = 'https://cdn.roxy.local/saved.png';
const generation = {
  id: 'gen_1',
  status: 'succeeded',
  model: models[0],
  result_url: resultImage,
  result_urls: [resultImage],
  media: [{ url: resultImage, kind: 'image' }],
  prompt: 'Портрет в неоне',
  prompt_actions_allowed: true,
  created_at: '2026-08-21T08:30:00Z',
  is_profile_visible: false,
  publication_scope: 'private',
};
const feedCard = {
  ...generation,
  id: 'feed_1',
  preview_url: resultImage,
  model: 'Nano Banana 2',
  likes_count: 12,
  shares_count: 3,
  comments_count: 2,
  liked_by_me: false,
  is_mine: true,
  publication_scope: 'feed',
  is_profile_visible: true,
  is_public_feed: true,
  surface: 'feed',
  feed_published_at: '2026-08-21T08:40:00Z',
};
const trends = [
  { id: 'trend_portrait', title: 'Неоновый портрет', description: 'Готовая идея для яркого аватара', media_type: 'image', cost_rox: '25.00', model: { title: 'Nano Banana 2' } },
  { id: 'trend_video', title: 'Короткий клип', description: 'Видео для Reels и Shorts', media_type: 'video', cost_rox: '60.00', model: { title: 'Seedance 2.5' } },
];
const savedReferences = [
  {
    id: 'ref_saved_1',
    kind: 'image',
    label: 'Сохранённый портрет',
    url: savedImage,
    filename: 'saved.png',
    content_type: 'image/png',
    source: 'mini_app_upload',
    created_at: '2026-08-21T08:10:00Z',
    updated_at: '2026-08-21T08:10:00Z',
    last_used_at: '2026-08-21T08:10:00Z',
  },
];

const routes = ['home', 'feed', 'catalog', 'create', 'partners', 'profile'];
const viewports = [
  { width: 320, height: 568 },
  { width: 360, height: 740 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
];
const checksByRoute = {
  home: ['shell', 'create-image', 'create-video', 'create-audio', 'catalog', 'history', 'partners', 'wallet', 'profile', 'feed'],
  feed: ['shell', 'top-day', 'top', 'refresh', 'preview', 'like', 'share', 'comments', 'remix', 'create'],
  catalog: ['shell', 'image-filter', 'video-filter', 'audio-filter', 'nano-family', 'seedance-family', 'image-trend', 'video-trend', 'create-nano', 'create'],
  create: ['fresh', 'prompt', 'image-family', 'video-family', 'audio-family', 'validation', 'submit', 'fresh-after-return', 'reuse', 'saved-reference'],
  partners: ['shell', 'referral-link', 'copy-referral', 'stats', 'rewards', 'invitations', 'refresh', 'copy-profile', 'profile', 'create'],
  profile: ['shell', 'counts', 'publications', 'work-preview', 'publication-preview', 'publish', 'reuse', 'wallet', 'profile-link', 'create'],
};

const scenarios = routes.flatMap((route) =>
  viewports.flatMap((viewport) =>
    checksByRoute[route].map((check) => ({ route, viewport, check })),
  ),
);

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockRoxy(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        openLink(url) { window.__lastOpenedLink = url; },
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
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/onboarding/complete') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json(route, { models, families });
    if (path === '/api/v1/generations/quote') return json(route, { cost_rox: '25.00', cost_rub: '25.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') return json(route, { id: 'gen_new', status: 'queued', cost_rox: '25.00' });
    if (path === '/api/v1/generations') return json(route, { items: [generation], has_more: false, next_before: null });
    if (path.endsWith('/recreate')) return json(route, { model_id: 'nano-banana-2', prompt: 'Портрет в неоне', input_url: null, billing_seconds: null, parameters: { resolution: '1K', reference_images: [savedImage] } });
    if (path.startsWith('/api/v1/generations/')) return json(route, path.endsWith('/gen_new') ? { ...generation, id: 'gen_new', status: 'queued', result_url: null, result_urls: [], media: [] } : generation);

    if (path === '/api/v1/feed') return json(route, { items: [feedCard] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json(route, { author: { display_name: 'QA' }, items: [feedCard] });
    if (path.includes('/publish')) return json(route, { publication_scope: 'feed', downgraded_to_profile: false, item: feedCard });
    if (path.includes('/remove')) return json(route, { id: 'feed_1', publication_scope: 'private', is_public_feed: false, is_profile_visible: false });
    if (path.includes('/like')) return json(route, { id: 'feed_1', surface: 'feed', liked_by_me: method !== 'DELETE', likes_count: method === 'DELETE' ? 12 : 13 });
    if (path.includes('/share')) return json(route, { id: 'feed_1', shares_count: 4, link: 'https://t.me/roxy_aicreativebot?start=feed_1' });
    if (path.includes('/comments') && method === 'POST') return json(route, { id: 'comment_new', generation_id: 'feed_1', surface: 'feed', text: 'Круто', created_at: '2026-08-21T09:00:00Z', author: { display_name: 'QA' } });
    if (path.includes('/comments')) return json(route, { items: [{ id: 'comment_1', generation_id: 'feed_1', surface: 'feed', text: 'Отличная работа', created_at: '2026-08-21T08:50:00Z', author: { display_name: 'User' } }] });
    if (path.includes('/remix')) return json(route, { id: 'gen_remix', status: 'queued' });

    if (path === '/api/v1/trends') return json(route, { items: trends });
    if (path.includes('/api/v1/trends/') && path.endsWith('/run')) return json(route, { id: 'trend_run', status: 'queued', cost_rox: '25.00' });

    if (path === '/api/v1/references') return json(route, { items: savedReferences });
    if (path === '/api/v1/references/touch') return json(route, { touched: 1 });
    if (path.startsWith('/api/v1/references/') && method === 'DELETE') return route.fulfill({ status: 204, body: '' });
    if (path === '/api/v1/uploads/kie') return json(route, { url: savedImage, name: 'saved.png', mime_type: 'image/png', size: 68, replayed: true, reference: savedReferences[0] }, 201);

    if (path === '/api/v1/referrals/stats') return json(route, {
      referral_link: 'https://t.me/roxy_aicreativebot?start=ref_777',
      first_line: 2,
      second_line: 1,
      partner_balance_rub: '1200.00',
      available: '1200.00',
    });
    if (path === '/api/v1/referrals/invitations') return json(route, { items: [{ user_id: 'invite_1', first_name: 'Анна', username: 'anna', line: 1, joined_at: '2026-08-20T10:00:00Z' }] });
    if (path === '/api/v1/referrals/rewards') return json(route, { items: [{ id: 'reward_1', line: 1, status: 'completed', amount: '75.00', amount_rox: '75.00', net_amount_rox: '75.00', created_at: '2026-08-20T11:00:00Z', source_user: { first_name: 'Анна', username: 'anna' } }] });

    if (path === '/api/v1/me/transactions') return json(route, []);
    if (path === '/api/v1/payments/card/packages') return json(route, { provider: 'card', label: 'Оплата картой', currencies: ['RUB'], packages: { starter: { credits: '100', prices: { RUB: '100' } } } });
    if (path === '/api/v1/payments/card/checkout') return json(route, { id: 'pay_1', status: 'pending', payment_url: 'https://pay.roxy.local/checkout' });
    if (path === '/api/v1/payments') return json(route, { items: [] });

    return json(route, { items: [] });
  });
}

async function boot(page, scenario) {
  await page.setViewportSize(scenario.viewport);
  await mockRoxy(page);
  await page.goto(`/mini-app/?route=${scenario.route}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('ROXY').first()).toBeVisible({ timeout: 6_000 });
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(nav).toBeVisible();
  await expect(nav.locator('button')).toHaveCount(6);
  await expect(page.locator('.bottom-nav button.central small')).toHaveText('Создать');
  await expect(page.locator('.bottom-nav button small')).not.toContainText('\n');
}

function bottomButton(page, label) {
  return page.locator('.bottom-nav button').filter({ hasText: label }).first();
}

async function openFeedPreview(page) {
  await page.locator('.media-tile').first().click();
  await expect(page.locator('.preview-card')).toBeVisible();
}

async function openPrivatePreview(page) {
  await page.locator('.media-tile').first().click();
  await expect(page.locator('.preview-card')).toBeVisible();
}

async function chooseFamily(page, name) {
  await page.locator('.family-card').filter({ hasText: name }).first().click();
  await expect(page.locator('.bottom-sheet')).toBeVisible();
  await page.locator('.variant-row').first().click();
}

async function runHome(page, check) {
  if (check === 'shell') {
    await expect(page.getByText('Что создаём?')).toBeVisible();
    await expect(page.locator('.format-card')).toHaveCount(3);
  } else if (check === 'create-image') {
    await page.locator('.format-card').filter({ hasText: 'Фото' }).click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  } else if (check === 'create-video') {
    await page.locator('.format-card').filter({ hasText: 'Видео' }).click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
    await expect(page.getByText('Seedance').first()).toBeVisible();
  } else if (check === 'create-audio') {
    await page.locator('.format-card').filter({ hasText: 'Музыка' }).click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  } else if (check === 'catalog') {
    await page.getByRole('button', { name: /Каталог/ }).first().click();
    await expect(page.getByText('Готовые сценарии')).toBeVisible();
  } else if (check === 'history') {
    await page.getByRole('button', { name: 'Все' }).last().click();
    await expect(page.getByText('Все генерации')).toBeVisible();
  } else if (check === 'partners') {
    await page.locator('.promo-slide').first().click();
    await expect(page.getByText('Кабинет автора')).toBeVisible();
  } else if (check === 'wallet') {
    await page.locator('.balance-button').click();
    await expect(page.getByText('Выберите пакет')).toBeVisible();
  } else if (check === 'profile') {
    await bottomButton(page, 'Профиль').click();
    await expect(page.getByText('QA').first()).toBeVisible();
  } else if (check === 'feed') {
    await bottomButton(page, 'Лента').click();
    await expect(page.getByText('Работы сообщества')).toBeVisible();
  }
}

async function runFeed(page, check) {
  if (check === 'shell') {
    await expect(page.getByText('Работы сообщества')).toBeVisible();
    await expect(page.locator('.media-tile')).toHaveCount(1);
  } else if (check === 'top-day') {
    await page.getByRole('button', { name: 'Топ дня' }).click();
    await expect(page.getByRole('button', { name: 'Топ дня' })).toHaveClass(/active/);
  } else if (check === 'top') {
    await page.getByRole('button', { name: 'Топ', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Топ', exact: true })).toHaveClass(/active/);
  } else if (check === 'refresh') {
    await page.getByRole('button', { name: 'Обновить' }).click();
    await expect(page.locator('.media-tile')).toHaveCount(1);
  } else if (check === 'preview') {
    await openFeedPreview(page);
    await expect(page.getByText('Портрет в неоне')).toBeVisible();
  } else if (check === 'like') {
    await openFeedPreview(page);
    await page.getByRole('button', { name: /Лайк · 12/ }).click();
    await expect(page.getByRole('button', { name: /Лайк есть · 13/ })).toBeVisible();
  } else if (check === 'share') {
    await openFeedPreview(page);
    await page.getByRole('button', { name: /Поделиться · 3/ }).click();
    await expect(page.getByRole('button', { name: /Поделиться · 4/ })).toBeVisible();
  } else if (check === 'comments') {
    await openFeedPreview(page);
    await page.getByRole('button', { name: /Комментарии · 2/ }).click();
    await expect(page.getByText('Отличная работа')).toBeVisible();
  } else if (check === 'remix') {
    await openFeedPreview(page);
    await page.getByRole('button', { name: 'Повторить' }).click();
    await expect(page.getByText('Повтор запущен: queued')).toBeVisible();
  } else if (check === 'create') {
    await bottomButton(page, 'Создать').click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  }
}

async function runCatalog(page, check) {
  if (check === 'shell') {
    await expect(page.getByText('Готовые сценарии')).toBeVisible();
    await expect(page.getByText('Полный каталог')).toBeVisible();
  } else if (check === 'image-filter') {
    await page.getByRole('button', { name: 'Фото', exact: true }).click();
    await expect(page.getByText('Nano Banana').first()).toBeVisible();
  } else if (check === 'video-filter') {
    await page.getByRole('button', { name: 'Видео', exact: true }).click();
    await expect(page.getByText('Seedance').first()).toBeVisible();
  } else if (check === 'audio-filter') {
    await page.getByRole('button', { name: 'Музыка', exact: true }).click();
    await expect(page.getByText('Музыка').first()).toBeVisible();
  } else if (check === 'nano-family') {
    await page.locator('.model-card').filter({ hasText: 'Nano Banana' }).last().click();
    await expect(page.locator('.bottom-sheet')).toBeVisible();
    await expect(page.getByText('Nano Banana 2')).toBeVisible();
  } else if (check === 'seedance-family') {
    await page.locator('.model-card').filter({ hasText: 'Seedance' }).last().click();
    await expect(page.locator('.bottom-sheet')).toBeVisible();
    await expect(page.getByText('Seedance 2.5')).toBeVisible();
  } else if (check === 'image-trend') {
    await page.locator('.model-card').filter({ hasText: 'Неоновый портрет' }).click();
    await expect(page.locator('.preview-card')).toBeVisible();
  } else if (check === 'video-trend') {
    await page.locator('.model-card').filter({ hasText: 'Короткий клип' }).click();
    await expect(page.locator('.preview-card')).toBeVisible();
  } else if (check === 'create-nano') {
    await page.locator('.model-card').filter({ hasText: 'Nano Banana' }).last().click();
    await page.locator('.variant-row').first().click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
    await expect(page.getByText('Nano Banana 2').first()).toBeVisible();
  } else if (check === 'create') {
    await bottomButton(page, 'Создать').click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  }
}

async function runCreate(page, check) {
  const prompt = page.locator('textarea.control').first();
  if (check === 'fresh') {
    await expect(page.getByText('Новая генерация')).toBeVisible();
    await expect(prompt).toHaveValue('');
  } else if (check === 'prompt') {
    await prompt.fill('Лис в неоновом городе');
    await expect(prompt).toHaveValue('Лис в неоновом городе');
    await expect(page.getByText('25 ROX')).toBeVisible();
  } else if (check === 'image-family') {
    await chooseFamily(page, 'Nano Banana');
    await expect(page.getByText('Nano Banana 2').first()).toBeVisible();
  } else if (check === 'video-family') {
    await page.getByRole('button', { name: 'Видео', exact: true }).click();
    await chooseFamily(page, 'Seedance');
    await expect(page.getByText('Длительность')).toBeVisible();
  } else if (check === 'audio-family') {
    await page.getByRole('button', { name: 'Музыка', exact: true }).click();
    await chooseFamily(page, 'Музыка');
    await expect(page.getByText('ROXY Music').first()).toBeVisible();
  } else if (check === 'validation') {
    await expect(page.getByRole('button', { name: /^Создать/ }).last()).toBeDisabled();
    await expect(page.getByText(/Заполните «Промпт»/)).toBeVisible();
  } else if (check === 'submit') {
    await prompt.fill('Портрет для обложки');
    const submit = page.getByRole('button', { name: /Создать · 25 ROX/ });
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.locator('.preview-card')).toBeVisible();
    await expect(page.getByText(/ROXY можно закрыть/)).toBeVisible();
  } else if (check === 'fresh-after-return') {
    await prompt.fill('Этот текст не должен пережить новый запуск');
    await bottomButton(page, 'Студия').click();
    await bottomButton(page, 'Создать').click();
    await expect(page.locator('textarea.control').first()).toHaveValue('');
  } else if (check === 'reuse') {
    await page.goto('/mini-app/?route=history', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.history-card')).toHaveCount(1);
    await page.locator('.history-card').first().click();
    await page.getByRole('button', { name: 'Использовать настройки' }).click();
    await expect(page.getByText('Использовать настройки').first()).toBeVisible();
    await expect(page.locator('textarea.control').first()).toHaveValue('Портрет в неоне');
  } else if (check === 'saved-reference') {
    await expect(page.getByText('Сохранённые референсы')).toBeVisible();
    await page.locator('.saved-reference-pick').first().click();
    await expect(page.locator('.upload-list')).toContainText('saved.png');
  }
}

async function runPartners(page, check) {
  if (check === 'shell') {
    await expect(page.getByText('Кабинет автора')).toBeVisible();
  } else if (check === 'referral-link') {
    await expect(page.getByText('https://t.me/roxy_aicreativebot?start=ref_777')).toBeVisible();
  } else if (check === 'copy-referral') {
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', { name: 'Скопировать реф-ссылку' }).click();
    await expect(page.getByText('Ссылка скопирована')).toBeVisible();
  } else if (check === 'stats') {
    await expect(page.getByText('2').first()).toBeVisible();
    await expect(page.getByText('1').first()).toBeVisible();
    await expect(page.getByText(/1[\s ]?200 ₽/)).toBeVisible();
  } else if (check === 'rewards') {
    await expect(page.getByText('Последние начисления')).toBeVisible();
    await expect(page.getByText('+75 ROX')).toBeVisible();
  } else if (check === 'invitations') {
    await expect(page.getByText('Новые приглашения')).toBeVisible();
    await expect(page.getByText('@anna')).toBeVisible();
  } else if (check === 'refresh') {
    await page.getByRole('button', { name: 'Обновить' }).click();
    await expect(page.getByText('Кабинет автора')).toBeVisible();
  } else if (check === 'copy-profile') {
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.getByRole('button', { name: 'Скопировать ссылку на профиль' }).click();
    await expect(page.getByText('Ссылка скопирована')).toBeVisible();
  } else if (check === 'profile') {
    await bottomButton(page, 'Профиль').click();
    await expect(page.getByText('QA').first()).toBeVisible();
  } else if (check === 'create') {
    await bottomButton(page, 'Создать').click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  }
}

async function runProfile(page, check) {
  if (check === 'shell') {
    await expect(page.getByText('QA').first()).toBeVisible();
  } else if (check === 'counts') {
    await expect(page.locator('.profile-stats')).toContainText('1');
    await expect(page.locator('.profile-stats')).toContainText('12');
  } else if (check === 'publications') {
    await page.getByRole('button', { name: 'Публикации' }).click();
    await expect(page.locator('.media-tile')).toHaveCount(1);
  } else if (check === 'work-preview') {
    await openPrivatePreview(page);
    await expect(page.getByRole('button', { name: 'Использовать настройки' })).toBeVisible();
  } else if (check === 'publication-preview') {
    await page.getByRole('button', { name: 'Публикации' }).click();
    await openFeedPreview(page);
    await expect(page.getByRole('button', { name: /Лайк/ })).toBeVisible();
  } else if (check === 'publish') {
    await openPrivatePreview(page);
    await page.getByRole('button', { name: 'В ленту + профиль' }).click();
    await expect(page.getByText('Работа опубликована в ленте и профиле')).toBeVisible();
  } else if (check === 'reuse') {
    await openPrivatePreview(page);
    await page.getByRole('button', { name: 'Использовать настройки' }).click();
    await expect(page.getByText('Использовать настройки').first()).toBeVisible();
    await expect(page.locator('textarea.control').first()).toHaveValue('Портрет в неоне');
  } else if (check === 'wallet') {
    await page.locator('.balance-button').click();
    await expect(page.getByText('Выберите пакет')).toBeVisible();
  } else if (check === 'profile-link') {
    await bottomButton(page, 'Партнёры').click();
    await expect(page.getByRole('button', { name: 'Скопировать ссылку на профиль' })).toBeVisible();
  } else if (check === 'create') {
    await bottomButton(page, 'Создать').click();
    await expect(page.getByText('Новая генерация')).toBeVisible();
  }
}

const routeRunners = {
  home: runHome,
  feed: runFeed,
  catalog: runCatalog,
  create: runCreate,
  partners: runPartners,
  profile: runProfile,
};

test.describe('ROXY Mini App — 300 isolated user scenarios', () => {
  test.describe.configure({ mode: 'parallel' });

  test('scenario matrix is exactly 300 cases', async () => {
    expect(routes).toHaveLength(6);
    expect(viewports).toHaveLength(5);
    for (const route of routes) expect(checksByRoute[route]).toHaveLength(10);
    expect(scenarios).toHaveLength(300);
  });

  for (const [index, scenario] of scenarios.entries()) {
    test(`${String(index + 1).padStart(3, '0')} ${scenario.route}/${scenario.check} @ ${scenario.viewport.width}x${scenario.viewport.height}`, async ({ page }) => {
      await boot(page, scenario);
      await routeRunners[scenario.route](page, scenario.check);
    });
  }
});
