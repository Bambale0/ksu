import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt', 'input_url'],
  price_rox: '15.00',
  ui_schema: {
    fields: [
      {
        name: 'prompt',
        label: 'Промпт',
        control: 'textarea',
        required: true,
        placeholder: 'Опишите желаемый результат',
      },
    ],
    defaults: {},
  },
};

const feedCard = {
  id: 'feed_language_1',
  status: 'succeeded',
  model: 'nano-banana-2',
  prompt: 'мая Каталог',
  prompt_hidden: false,
  prompt_actions_allowed: true,
  result_url: 'https://cdn.roxy.test/language.png',
  result_urls: ['https://cdn.roxy.test/language.png'],
  media: [{ url: 'https://cdn.roxy.test/language.png', kind: 'image' }],
  preview_url: 'https://cdn.roxy.test/language.png',
  likes_count: 1,
  shares_count: 0,
  comments_count: 1,
  liked_by_me: false,
  is_mine: false,
  surface: 'feed',
  publication_scope: 'feed',
  is_profile_visible: true,
  is_public_feed: true,
  feed_published_at: '2026-05-03T08:40:00Z',
  created_at: '2026-05-03T08:30:00Z',
  author: {
    id: 'author-language',
    display_name: 'Каталог мая',
    username: 'may_catalog',
  },
};

async function mockRoxy(page, { initialLanguage = 'ru', telegramLanguage = 'ru' } = {}) {
  const writes = [];
  let preferences = {
    ui_language: initialLanguage,
    notifications_enabled: true,
    marketing_notifications: false,
    profile_discoverable: false,
  };

  await page.addInitScript((languageCode) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=language-e2e&hash=test',
        initDataUnsafe: {
          user: {
            id: 777,
            first_name: 'QA',
            username: 'qa_user',
            language_code: languageCode,
          },
        },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {}, openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, telegramLanguage);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me/preferences' && method === 'GET') return json(preferences);
    if (path === '/api/v1/me/preferences' && method === 'PATCH') {
      const patch = request.postDataJSON() || {};
      preferences = { ...preferences, ...patch };
      writes.push({ method, body: patch });
      return json(preferences);
    }
    if (path === '/api/v1/me/preferences' && method === 'PUT') {
      const body = request.postDataJSON() || {};
      preferences = body;
      writes.push({ method, body });
      return json(preferences);
    }
    if (path === '/api/v1/me') return json({
      id: 'user_1',
      telegram_id: 777,
      first_name: 'QA',
      username: 'qa_user',
      language_code: telegramLanguage,
      balance_rox: '150.00',
      preferences,
      is_admin: false,
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [feedCard] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/promocodes/active') return json({ active: false, code: null });
    if (path === '/api/v1/me/overview') return json({ notifications: {}, support: {}, social: {}, partner: {}, payments: {} });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: '', first_line: 0, second_line: 0, partner_balance_rub: '0' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/batch-generations') return json({ items: [] });
    if (/^\/api\/v1\/profiles\/[^/]+$/.test(path)) return json({
      id: 'author-language',
      display_name: 'Каталог мая',
      username: 'may_catalog',
      follower_count: 0,
      subscribed_by_me: false,
    });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [] });
    if (path.includes('/comments')) return json({
      items: [{
        id: 'comment-language-1',
        text: 'мая Каталог',
        created_at: '2026-05-03T08:50:00Z',
        author: { display_name: 'Каталог мая', username: 'may_catalog' },
      }],
    });
    return json({ items: [] });
  });

  await page.route('https://cdn.roxy.test/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  return writes;
}

test('RU EN switch uses partial preference PATCH on canonical Catalog root', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await mockRoxy(page, { initialLanguage: 'ru' });

  await page.goto('/mini-app/?route=home');

  const switcher = page.getByRole('group', { name: 'Язык интерфейса' });
  await expect(switcher.getByRole('button', { name: 'RU' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.bottom-nav button[data-roxy-customer-route="catalog"]')).toBeVisible();

  await switcher.getByRole('button', { name: 'EN' }).click();

  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.balance-button span')).toHaveText('Balance');
  await expect(page.locator('.bottom-nav')).toContainText('Catalog');
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({ method: 'PATCH', body: { ui_language: 'en' } });
});

test('English mode translates textarea placeholders and runtime batch counts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page, { initialLanguage: 'en' });

  await page.goto('/mini-app/batch/');

  const prompt = page.locator('textarea[placeholder]').first();
  await expect(prompt).toHaveAttribute('placeholder', 'What should be changed in each image?');

  const input = page.locator('input[type="file"]').first();
  await input.setInputFiles([
    { name: 'a.png', mimeType: 'image/png', buffer: Buffer.from('a') },
    { name: 'b.png', mimeType: 'image/png', buffer: Buffer.from('b') },
    { name: 'c.png', mimeType: 'image/png', buffer: Buffer.from('c') },
  ]);
  await expect(page.getByText('3 images selected', { exact: true })).toBeVisible();
});

test('English UI never rewrites feed author names, prompts or comments', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page, { initialLanguage: 'en' });

  await page.goto('/mini-app/?route=feed');

  const surface = page.locator('.tiktok-feed-surface');
  await expect(surface).toBeVisible();
  await expect(surface.locator('.tiktok-feed-author-line strong').first()).toHaveText('Каталог мая');
  await expect(surface.locator('.tiktok-feed-prompt').first()).toHaveText('мая Каталог');

  await surface.getByRole('button', { name: 'Comments' }).first().click();
  const comments = page.locator('.tiktok-comments-list');
  await expect(comments.locator('.tiktok-comment strong').first()).toHaveText('Каталог мая');
  await expect(comments.locator('.tiktok-comment p').first()).toHaveText('мая Каталог');
});

test('legacy auto follows Telegram English without persisting a manual choice', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  const writes = await mockRoxy(page, { initialLanguage: 'auto', telegramLanguage: 'en' });

  await page.goto('/mini-app/settings/');

  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  expect(writes).toHaveLength(0);
});
