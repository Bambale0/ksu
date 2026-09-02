import { expect, test } from '@playwright/test';

const sourceUrl = 'https://cdn.roxy.local/source.png';

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockPublish(page) {
  await installTelegram(page);
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64') }));
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/action-context')) return json(route, {
      generation: { id: 'gen_source', status: 'succeeded', media_type: 'image', result_url: sourceUrl, model_id: 'nano-banana-pro', model_title: 'NanoBanana PRO', prompt: 'Портрет в неоновом свете', prompt_hidden: false, publication_scope: 'private' },
      action: { id: 'publish', label: '📤 Опубликовать', derivative: false },
      candidate_models: [], defaults: { model_id: null, prompt: '', parameters: {}, billing_seconds: null, input_url: null },
      source_url: sourceUrl, source_references: { images: [], videos: [] }, edit_presets: [],
    });
    if (url.pathname === '/api/v1/feed/gen_source/publish') return json(route, { publication_scope: 'feed', downgraded_to_profile: false });
    if (url.pathname === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (url.pathname === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (url.pathname === '/api/v1/generations') return json(route, { items: [], has_more: false, next_before: null });
    if (url.pathname === '/api/v1/feed') return json(route, { items: [] });
    if (url.pathname === '/api/v1/trends') return json(route, { items: [] });
    return json(route, {});
  });
}

async function openPublish(page) {
  await mockPublish(page);
  await page.goto('/mini-app/?route=generation-action&generation=gen_source&action=publish');
  await expect(page.getByText('📤 Опубликовать').first()).toBeVisible();
  return page.getByLabel('Показать описание');
}

async function publishRequest(page) {
  const published = page.waitForRequest((request) => request.url().endsWith('/api/v1/feed/gen_source/publish') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  return published;
}

test('publish respects enabled Show description toggle despite global privacy guard', async ({ page }) => {
  const showDescription = await openPublish(page);
  await expect(showDescription).not.toBeChecked();
  await showDescription.check();
  await expect(showDescription).toBeChecked();

  const request = await publishRequest(page);
  expect(request.postDataJSON().prompt_visible).toBe(true);
  expect(await page.evaluate(() => window.__roxyPublishPrivacy?.hidePrompt)).toBe(false);
});

test('publish keeps description private when Show description stays disabled', async ({ page }) => {
  const showDescription = await openPublish(page);
  await expect(showDescription).not.toBeChecked();

  const request = await publishRequest(page);
  expect(request.postDataJSON().prompt_visible).toBe(false);
  expect(await page.evaluate(() => window.__roxyPublishPrivacy?.hidePrompt)).toBe(true);
});
