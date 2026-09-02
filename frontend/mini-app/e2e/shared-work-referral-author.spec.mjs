import { expect, test } from '@playwright/test';

const generationId = '22222222-3333-4444-8555-666666666666';
const authorCode = '777';
const sharerCode = '888';
const payload = `feed_${generationId}_ref_${sharerCode}`;
const image = 'https://cdn.roxy.local/shared-by-someone-else.png';
const copiedLink = `https://t.me/roxy_bot?startapp=feed_${generationId}_ref_999`;

async function installTelegram(page) {
  await page.addInitScript((startParam) => {
    window.__copiedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { async writeText(value) { window.__copiedText = String(value); } },
    });
    window.Telegram = {
      WebApp: {
        initData: 'query_id=shared-referrer&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Recipient' }, start_param: startParam },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, payload);
}

async function mockApp(page) {
  const shareBodies = [];

  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'viewer-999', telegram_id: 999, first_name: 'Recipient', balance_rox: '100.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });

    if (path === `/api/v1/feed/${generationId}` && request.method() === 'GET') return json({
      id: generationId,
      model: 'nano-banana-2',
      preview_url: image,
      result_url: image,
      result_urls: [image],
      media: [{ url: image, content_type: 'image/png' }],
      prompt: 'Работа Маши, которой поделился Вася',
      prompt_hidden: false,
      prompt_actions_allowed: true,
      author_referral_code: authorCode,
      author: { telegram_id: Number(authorCode), username: 'creator', display_name: 'Creator' },
      publication_scope: 'feed',
      is_public_feed: true,
      is_profile_visible: true,
      surface: 'feed',
    });

    if (path === `/api/v1/feed/${generationId}/share` && request.method() === 'POST') {
      shareBodies.push(request.postDataJSON());
      return json({ id: generationId, shares_count: 4, link: copiedLink });
    }

    if (path === `/api/v1/profiles/${authorCode}/feed`) return json({
      author: { id: 'creator-777', telegram_id: 777, username: 'creator', display_name: 'Creator', referral_code: authorCode },
      items: [],
    });
    if (path === '/api/v1/social/profiles/creator-777') return json({
      id: 'creator-777', username: 'creator', display_name: 'Creator', referral_code: authorCode,
      profile_discoverable: true, is_self: false, subscribed_by_me: false, follower_count: 1,
    });

    return json({ items: [] });
  });

  return shareBodies;
}

test('a shared-work referrer may differ from the author without blocking work actions', async ({ page }) => {
  await installTelegram(page);
  const shareBodies = await mockApp(page);

  await page.goto(`/mini-app/?startapp=${encodeURIComponent(payload)}`);
  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Creator', { exact: true })).toBeVisible();
  await expect(page.getByText('Работа Маши, которой поделился Вася')).toBeVisible();

  await expect(page.getByText('Реферальная подпись не совпадает с автором работы.')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Повторить', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Скопировать ссылку', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Профиль автора', exact: true })).toBeEnabled();

  await page.getByRole('button', { name: 'Скопировать ссылку', exact: true }).click();
  await expect.poll(() => shareBodies.length).toBe(1);
  expect(shareBodies[0]).toEqual({ surface: 'feed' });
  await expect.poll(() => page.evaluate(() => window.__copiedText)).toBe(copiedLink);
  await expect(page.getByText('Ссылка на работу скопирована')).toBeVisible();

  await page.getByRole('button', { name: 'Профиль автора', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/mini-app/\\?start_payload=profile_${authorCode}`));
  expect(page.url()).not.toContain(`profile_${sharerCode}`);
});
