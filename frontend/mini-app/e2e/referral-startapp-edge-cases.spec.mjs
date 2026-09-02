import { expect, test } from '@playwright/test';

const generationId = '11111111-2222-4333-8444-555555555555';
const missingGenerationId = '22222222-3333-4444-8555-666666666666';
const image = 'https://cdn.roxy.local/edge.png';

const models = [
  {
    id: 'nano-banana-2',
    title: 'Nano Banana 2',
    family: 'nano-banana',
    operation: 'auto',
    media_type: 'image',
    price_rox: '25.00',
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
];

function feedCard({ id = generationId, authorCode = '777' } = {}) {
  return {
    id,
    model: 'Nano Banana 2',
    preview_url: image,
    result_url: image,
    result_urls: [image],
    media: [{ url: image, content_type: 'image/png' }],
    prompt: `Edge prompt ${authorCode}`,
    prompt_hidden: false,
    prompt_actions_allowed: true,
    author_referral_code: authorCode,
    author: { telegram_id: Number(authorCode), username: `creator${authorCode}`, display_name: `Creator ${authorCode}` },
    publication_scope: 'feed',
    is_public_feed: true,
    is_profile_visible: true,
    surface: 'feed',
    likes_count: 0,
    shares_count: 0,
    comments_count: 0,
    liked_by_me: false,
  };
}

function remixDraft(surface = 'feed') {
  return {
    source_generation_id: generationId,
    source_feed_gen_id: generationId,
    surface,
    model_id: 'nano-banana-2',
    effective_model_id: 'nano-banana-2',
    model_title: 'Nano Banana 2',
    prompt: 'Edge prompt 777',
    prompt_hidden: false,
    prompt_editable: true,
    settings: {},
    reference_requirements: { image_count: 0, video_count: 0, audio_count: 0, required: false },
    preview_url: image,
    media: [{ url: image, content_type: 'image/png' }],
  };
}

async function installTelegram(page, startParam = '') {
  await page.addInitScript(({ payload }) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Edge' }, start_param: payload },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        openLink(url) { window.__lastOpenedLink = url; },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { payload: startParam });
}

async function mockApp(page) {
  const feedItemCalls = [];
  const profileFeedCalls = [];
  const prepareCalls = [];
  let remixCalls = 0;

  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'edge_user', telegram_id: 999, first_name: 'Edge', balance_rox: '100.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models, families });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });

    const feedMatch = path.match(/^\/api\/v1\/feed\/([^/]+)$/);
    if (feedMatch) {
      const id = decodeURIComponent(feedMatch[1]);
      feedItemCalls.push({ id, surface: url.searchParams.get('surface') || 'feed' });
      if (id === generationId) return json(feedCard());
      if (id === missingGenerationId) return json({ detail: 'Работа не найдена' }, 404);
      return json({ detail: 'Unexpected feed id' }, 500);
    }

    if (path === `/api/v1/feed/${generationId}/remix/prepare`) {
      const surface = url.searchParams.get('surface') || 'feed';
      prepareCalls.push(surface);
      return json(remixDraft(surface));
    }

    if (path === `/api/v1/feed/${generationId}/remix/quote`) {
      return json({ model_id: 'nano-banana-2', cost_rox: '25.00', retail_cost_rox: '25.00', unit_price_rox: '25.00', admin_free: false });
    }

    if (path === `/api/v1/feed/${generationId}/remix`) {
      remixCalls += 1;
      return json({ detail: 'Open the repeat editor and add your own references before launch' }, 409);
    }

    if (path === `/api/v1/feed/${generationId}/share`) {
      return json({ id: generationId, shares_count: 1, link: 'https://t.me/roxy_aicreativebot?startapp=feed_link' });
    }

    const profileMatch = path.match(/^\/api\/v1\/profiles\/([^/]+)\/feed$/);
    if (profileMatch) {
      const referralCode = decodeURIComponent(profileMatch[1]);
      profileFeedCalls.push(referralCode);
      return json({ author: { username: `creator${referralCode}`, display_name: `Creator ${referralCode}`, referral_code: referralCode }, items: [feedCard({ authorCode: referralCode })] });
    }

    if (method === 'OPTIONS') return route.continue();
    return json({ items: [] });
  });

  return { feedItemCalls, profileFeedCalls, prepareCalls, remixCalls: () => remixCalls };
}

async function openWithPayload(page, query, telegramPayload = '') {
  await installTelegram(page, telegramPayload);
  const audit = await mockApp(page);
  await page.goto(`/mini-app/${query}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('ROXY').first()).toBeVisible({ timeout: 6_000 });
  return audit;
}

test('Banano-compatible startapp query opens the exact feed work without start_payload', async ({ page }) => {
  const payload = `feed_${generationId}_ref_777`;
  const audit = await openWithPayload(page, `?startapp=${encodeURIComponent(payload)}`);

  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Creator 777')).toBeVisible();
  await expect(page.getByText('Edge prompt 777')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Повторить$/ })).toBeEnabled();
  expect(audit.feedItemCalls).toEqual([{ id: generationId, surface: 'feed' }]);
  expect(audit.remixCalls()).toBe(0);
});

test('start_payload has priority over startapp when both are present', async ({ page }) => {
  const good = `feed_${generationId}_ref_777`;
  const bad = `feed_${missingGenerationId}_ref_777`;
  const audit = await openWithPayload(page, `?start_payload=${encodeURIComponent(good)}&startapp=${encodeURIComponent(bad)}`);

  await expect(page.getByText('Creator 777')).toBeVisible();
  expect(audit.feedItemCalls).toEqual([{ id: generationId, surface: 'feed' }]);
});

test('malformed feed payload is ignored and does not call feed item APIs', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=feed_not-a-uuid_ref_777');

  await expect(page.getByText('Что создаём?')).toBeVisible();
  await expect(page.locator('.preview-card')).toHaveCount(0);
  expect(audit.feedItemCalls).toEqual([]);
  expect(audit.remixCalls()).toBe(0);
});

test('bare referral payload opens the normal app shell, not a random work', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=ref_777');

  await expect(page.getByText('Что создаём?')).toBeVisible();
  await expect(page.locator('.preview-card')).toHaveCount(0);
  expect(audit.feedItemCalls).toEqual([]);
});

test('feed target 404 falls back to profile lookup and then shows a safe error', async ({ page }) => {
  const payload = `feed_${missingGenerationId}_ref_777`;
  const audit = await openWithPayload(page, `?startapp=${encodeURIComponent(payload)}`);

  await expect(page.getByText('Работа не найдена')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Открыть всю ленту' })).toBeVisible();
  expect(audit.feedItemCalls).toEqual([
    { id: missingGenerationId, surface: 'feed' },
    { id: missingGenerationId, surface: 'profile' },
  ]);
  expect(audit.remixCalls()).toBe(0);
});

test('feed referral identifies the sharer and may differ from the author', async ({ page }) => {
  const payload = `feed_${generationId}_ref_999`;
  const audit = await openWithPayload(page, `?startapp=${encodeURIComponent(payload)}`);

  // Shared-work attribution is allowed to differ from publication ownership.
  await expect(page.getByText('Creator 777')).toBeVisible();
  await expect(page.getByText('Реферальная подпись не совпадает с автором работы.')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Повторить$/ })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Скопировать ссылку' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Профиль автора' })).toBeEnabled();
  expect(audit.feedItemCalls).toEqual([{ id: generationId, surface: 'feed' }]);
  expect(audit.remixCalls()).toBe(0);
});

test('remix startapp opens work in remix mode and then opens the reference composer', async ({ page }) => {
  const payload = `remix_${generationId}_ref_777`;
  const audit = await openWithPayload(page, `?startapp=${encodeURIComponent(payload)}`);

  await expect(page.getByText('Remix ROXY')).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить эту работу/ })).toBeEnabled();
  expect(audit.remixCalls()).toBe(0);
  await page.getByRole('button', { name: /Повторить эту работу/ }).click();
  await expect(page).toHaveURL(new RegExp(`/mini-app/remix/\\?source=${generationId}&surface=feed`));
  await expect.poll(() => audit.prepareCalls.length).toBe(1);
  expect(audit.remixCalls()).toBe(0);
  await expect(page.getByText(/Референсы исходной публикации не копируются/)).toBeVisible();
});

test('profile startapp opens an author profile directly', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=profile_777');

  await expect(page.getByText('Профиль ROXY')).toBeVisible();
  await expect(page.getByText('Creator 777')).toBeVisible();
  await expect(page.locator('[data-profile-startapp-posts]')).toBeVisible();
  expect(audit.profileFeedCalls).toEqual(['777']);
  expect(audit.feedItemCalls).toEqual([]);
});

test('profile startapp with matching ref opens the same author profile', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=profile_777_ref_777');

  await expect(page.getByText('Creator 777')).toBeVisible();
  expect(audit.profileFeedCalls).toEqual(['777']);
  expect(audit.feedItemCalls).toEqual([]);
});

test('legacy posts startapp opens a matching author profile', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=posts_777_ref_777');

  await expect(page.getByText('Creator 777')).toBeVisible();
  expect(audit.profileFeedCalls).toEqual(['777']);
  expect(audit.feedItemCalls).toEqual([]);
});

test('mismatched profile startapp is ignored instead of opening another author', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=profile_777_ref_999');

  await expect(page.getByText('Что создаём?')).toBeVisible();
  expect(audit.profileFeedCalls).toEqual([]);
  expect(audit.feedItemCalls).toEqual([]);
});

test('mismatched legacy posts startapp is ignored instead of opening another author', async ({ page }) => {
  const audit = await openWithPayload(page, '?startapp=posts_777_ref_999');

  await expect(page.getByText('Что создаём?')).toBeVisible();
  expect(audit.profileFeedCalls).toEqual([]);
  expect(audit.feedItemCalls).toEqual([]);
});
