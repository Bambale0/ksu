import { expect, test } from '@playwright/test';

const generationId = '11111111-2222-4333-8444-555555555555';
const feedPayload = `feed_${generationId}_ref_777`;
const image = 'https://cdn.roxy.local/back-work.png';

async function installStickyTelegram(page, startParam) {
  await page.addInitScript(({ payload }) => {
    window.__telegramBackHandler = null;
    window.__pressTelegramBack = () => window.__telegramBackHandler?.();
    window.Telegram = {
      WebApp: {
        initData: 'query_id=standalone-back&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Viewer' }, start_param: payload },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        BackButton: {
          show() {}, hide() {},
          onClick(callback) { window.__telegramBackHandler = callback; },
          offClick(callback) {
            if (window.__telegramBackHandler === callback) window.__telegramBackHandler = null;
          },
        },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { payload: startParam });
}

async function mockApp(page) {
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({
      id: 'viewer-999', telegram_id: 999, first_name: 'Viewer', balance_rox: '100.00',
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === `/api/v1/feed/${generationId}`) return json({
      id: generationId,
      model: 'Nano Banana 2',
      preview_url: image,
      result_url: image,
      result_urls: [image],
      media: [{ url: image, content_type: 'image/png' }],
      prompt: 'Back navigation portrait',
      prompt_hidden: false,
      prompt_actions_allowed: true,
      author_referral_code: '777',
      author: { telegram_id: 777, username: 'creator', display_name: 'Creator' },
      publication_scope: 'feed',
      is_public_feed: true,
      is_profile_visible: true,
      surface: 'feed',
    });
    if (path === '/api/v1/profiles/777/feed') return json({
      author: {
        id: 'creator-777', telegram_id: 777, username: 'creator',
        display_name: 'Creator', referral_code: '777',
      },
      items: [],
    });
    if (path === '/api/v1/social/profiles/creator-777') return json({
      id: 'creator-777', telegram_id: 777, username: 'creator', display_name: 'Creator',
      referral_code: '777', profile_discoverable: true, is_self: false,
      subscribed_by_me: false, follower_count: 12,
    });
    return json({ items: [] });
  });
}

async function pressTelegramBack(page) {
  await expect.poll(() => page.evaluate(() => typeof window.__telegramBackHandler === 'function')).toBe(true);
  await page.evaluate(() => window.__pressTelegramBack());
}

test('direct public profile native Back reaches Home instead of reopening itself', async ({ page }) => {
  await installStickyTelegram(page, 'profile_777');
  await mockApp(page);

  await page.goto('/mini-app/?startapp=profile_777');
  await expect(page.getByText('Профиль ROXY')).toBeVisible();
  await expect(page.getByText('Creator', { exact: true })).toBeVisible();

  await pressTelegramBack(page);

  await expect(page).toHaveURL(/\/mini-app\/?\?route=home/);
  await expect(page.getByText('Что создаём?')).toBeVisible();
  await expect(page.getByText('Профиль ROXY')).toHaveCount(0);
});

test('shared work to author profile native Back returns to the work, not the profile again', async ({ page }) => {
  await installStickyTelegram(page, feedPayload);
  await mockApp(page);

  await page.goto(`/mini-app/?startapp=${encodeURIComponent(feedPayload)}`);
  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Back navigation portrait')).toBeVisible();

  await page.getByRole('button', { name: 'Профиль автора' }).click();
  await expect(page).toHaveURL(/\/mini-app\/?\?start_payload=profile_777/);
  await expect(page.getByText('Профиль ROXY')).toBeVisible();

  await pressTelegramBack(page);

  await expect(page).toHaveURL(new RegExp(`/mini-app/\\?startapp=${encodeURIComponent(feedPayload)}`));
  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Back navigation portrait')).toBeVisible();
  await expect(page.getByText('Профиль ROXY')).toHaveCount(0);
});
