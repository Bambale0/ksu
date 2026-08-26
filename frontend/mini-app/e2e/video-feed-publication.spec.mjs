import { expect, test } from '@playwright/test';

const generationId = '00000000-0000-4000-8000-000000000257';
const sourceVideoUrl = 'https://cdn.roxy.local/generated-video.mp4';

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockVideoPublishFlow(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=video-feed-e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route(sourceVideoUrl, (route) => route.fulfill({
    status: 200,
    contentType: 'video/mp4',
    body: Buffer.from('000000186674797069736f6d0000020069736f6d69736f32', 'hex'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === `/api/v1/generations/${generationId}/action-context` && url.searchParams.get('action') === 'publish') {
      return json(route, {
        generation: {
          id: generationId,
          status: 'succeeded',
          media_type: 'video',
          result_url: sourceVideoUrl,
          model_id: 'kling-3.0',
          model_title: 'Kling 3.0',
          prompt: 'cinematic video',
          prompt_hidden: false,
          publication_scope: 'private',
        },
        action: { id: 'publish', label: '📤 Опубликовать', derivative: false },
        candidate_models: [],
        defaults: { model_id: null, prompt: '', parameters: {}, billing_seconds: null, input_url: null },
        source_url: sourceVideoUrl,
        source_references: { images: [], videos: [] },
        edit_presets: [],
      });
    }

    if (path === `/api/v1/feed/${generationId}/publish` && method === 'POST') {
      return json(route, {
        publication_scope: 'feed',
        downgraded_to_profile: false,
        share: {
          link: `https://t.me/roxy_bot/app?startapp=feed_${generationId}_ref_777`,
          share_url: `https://t.me/share/url?url=https%3A%2F%2Ft.me%2Froxy_bot%2Fapp`,
          share_text: 'Посмотри моё видео в ROXY ✨',
        },
      });
    }

    if (path === '/api/v1/references') return json(route, { items: [] });
    return json(route, {});
  });
}

test('generated video can be published to feed from the same post-generation action', async ({ page }) => {
  await mockVideoPublishFlow(page);
  await page.goto(`/mini-app/?route=generation-action&generation=${generationId}&action=publish`);

  await expect(page.getByText('📤 Опубликовать').first()).toBeVisible();
  const video = page.locator(`video[src="${sourceVideoUrl}"]`);
  await expect(video).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Лента + профиль' })).toHaveClass(/active/);

  const published = page.waitForRequest((request) => (
    request.url().endsWith(`/api/v1/feed/${generationId}/publish`) && request.method() === 'POST'
  ));
  await page.getByRole('button', { name: 'Опубликовать' }).click();

  const request = await published;
  expect(request.postDataJSON()).toEqual({
    publication_scope: 'feed',
    prompt_visible: false,
    references_visible: false,
  });
  await expect(page.getByRole('heading', { name: 'Работа опубликована!' })).toBeVisible();
  await expect(page.getByText('Теперь она доступна в ленте.')).toBeVisible();
});
