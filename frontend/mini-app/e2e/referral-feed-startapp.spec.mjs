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

async function installFeedRoutes(page, audit = {}) {
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
    if (url.pathname === `/api/v1/feed/${generationId}/remix/prepare`) {
      audit.prepareCalls = (audit.prepareCalls || 0) + 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        source_generation_id: generationId,
        source_feed_gen_id: generationId,
        surface: url.searchParams.get('surface') === 'profile' ? 'profile' : 'feed',
        model_id: 'nano-banana-2',
        effective_model_id: 'nano-banana-2',
        model_title: 'Nano Banana 2',
        prompt: 'Кинематографичный портрет',
        prompt_hidden: false,
        prompt_editable: true,
        settings: {},
        reference_requirements: { image_count: 0, video_count: 0, audio_count: 0, required: false },
        preview_url: image,
        media: [{ url: image, content_type: 'image/png' }],
      }) });
    }
    if (url.pathname === `/api/v1/feed/${generationId}/remix/quote`) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        model_id: 'nano-banana-2', cost_rox: '25.00', retail_cost_rox: '25.00', unit_price_rox: '25.00', admin_free: false,
      }) });
    }
    if (url.pathname === `/api/v1/feed/${generationId}/remix`) {
      audit.remixCalls = (audit.remixCalls || 0) + 1;
      return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
        detail: 'Open the repeat editor and add your own references before launch',
      }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

test('referral startapp opens the exact feed work and sends Repeat to the composer', async ({ page }) => {
  const audit = { remixCalls: 0, prepareCalls: 0 };
  await installTelegramStartParam(page, payload);
  await installFeedRoutes(page, audit);

  await page.goto(`/mini-app/?tgWebAppStartParam=${encodeURIComponent(payload)}`);
  await expect(page.getByText('Лента ROXY')).toBeVisible();
  await expect(page.getByText('Creator')).toBeVisible();
  await expect(page.getByText('Кинематографичный портрет')).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить/ })).toBeVisible();
  expect(audit.remixCalls).toBe(0);

  await page.getByRole('button', { name: /Повторить/ }).click();
  await expect(page).toHaveURL(new RegExp(`/mini-app/remix/\\?source=${generationId}&surface=feed`));
  await expect.poll(() => audit.prepareCalls).toBe(1);
  expect(audit.remixCalls).toBe(0);
  await expect(page.getByText(/Референсы исходной публикации не копируются/)).toBeVisible();
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
