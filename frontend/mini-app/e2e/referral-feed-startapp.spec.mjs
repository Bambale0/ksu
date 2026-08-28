import { expect, test } from '@playwright/test';

const generationId = '11111111-2222-4333-8444-555555555555';
const payload = `feed_${generationId}_ref_777`;
const image = 'https://cdn.roxy.local/channel-work.png';

async function installTelegramStartParam(page, startParam) {
  await page.addInitScript(({ startParam: value }) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Guest' }, start_param: value },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { startParam });
}

async function installFeedRoutes(page, onRemix = () => {}) {
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/v1/feed/${generationId}`) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: generationId,
        model: 'Nano Banana 2',
        preview_url: image,
        result_url: image,
        result_urls: [image],
        media: [{ url: image, content_type: 'image/png' }],
        prompt: 'Кинематографичный портрет',
        prompt_hidden: false,
        prompt_actions_allowed: true,
        author_referral_code: '777',
        author: { telegram_id: 777, username: 'creator', display_name: 'Creator' },
        publication_scope: 'feed',
        is_public_feed: true,
        is_profile_visible: true,
        surface: 'feed',
      }) });
    }
    if (url.pathname === `/api/v1/feed/${generationId}/remix`) {
      onRemix();
      return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({
        id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', status: 'queued', source_feed_gen_id: generationId, action_type: 'remix',
      }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

test('referral startapp opens the exact feed work and waits for explicit Repeat', async ({ page }) => {
  let remixCalls = 0;
  await installTelegramStartParam(page, payload);
  await installFeedRoutes(page, () => { remixCalls += 1; });

  await page.goto(`/mini-app/?tgWebAppStartParam=${encodeURIComponent(payload)}`);
  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Creator')).toBeVisible();
  await expect(page.getByText('Кинематографичный портрет')).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить/ })).toBeVisible();
  expect(remixCalls).toBe(0);

  await page.getByRole('button', { name: /Повторить/ }).click();
  await expect.poll(() => remixCalls).toBe(1);
});

test('remix startapp opens the repeat screen for the exact work', async ({ page }) => {
  const remixPayload = `remix_${generationId}_ref_777`;
  await installTelegramStartParam(page, remixPayload);
  await installFeedRoutes(page);

  await page.goto(`/mini-app/?startapp=${encodeURIComponent(remixPayload)}`);

  await expect(page.getByText('Remix ROXY')).toBeVisible();
  await expect(page.getByText('Creator')).toBeVisible();
  await expect(page.getByText('Кинематографичный портрет')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Повторить эту работу' })).toBeVisible();
});
