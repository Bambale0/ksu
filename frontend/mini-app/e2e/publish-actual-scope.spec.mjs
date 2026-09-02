import { expect, test } from '@playwright/test';

const sourceUrl = 'https://cdn.roxy.local/publish-scope-source.png';

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=publish-scope&hash=test',
        initDataUnsafe: { user: { id: 778, first_name: 'Scope', username: 'scope_user' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockPublish(page, publishResponse) {
  await installTelegram(page);
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/action-context')) return json(route, {
      generation: {
        id: 'gen_scope', status: 'succeeded', media_type: 'image', result_url: sourceUrl,
        model_id: 'nano-banana-pro', model_title: 'NanoBanana PRO', prompt: 'Scope check',
        prompt_hidden: false, publication_scope: 'private',
      },
      action: { id: 'publish', label: '📤 Опубликовать', derivative: false },
      candidate_models: [],
      defaults: { model_id: null, prompt: '', parameters: {}, billing_seconds: null, input_url: null },
      source_url: sourceUrl,
      source_references: { images: [], videos: [] },
      edit_presets: [],
    });
    if (url.pathname === '/api/v1/feed/gen_scope/publish') return json(route, publishResponse);
    if (url.pathname === '/api/v1/me') return json(route, { id: 'user_scope', telegram_id: 778, first_name: 'Scope', username: 'scope_user', balance_rox: '150.00' });
    if (url.pathname === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (url.pathname === '/api/v1/generations') return json(route, { items: [], has_more: false, next_before: null });
    if (url.pathname === '/api/v1/feed' || url.pathname === '/api/v1/trends') return json(route, { items: [] });
    return json(route, {});
  });
}

async function openPublish(page, response) {
  await mockPublish(page, response);
  await page.goto('/mini-app/?route=generation-action&generation=gen_scope&action=publish');
  await expect(page.getByText('📤 Опубликовать').first()).toBeVisible();
}

async function submit(page) {
  const requestPromise = page.waitForRequest((request) => request.url().endsWith('/api/v1/feed/gen_scope/publish') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  return requestPromise;
}

test('profile-only publish never claims the work is in the public feed', async ({ page }) => {
  await openPublish(page, { publication_scope: 'profile', downgraded_to_profile: false, share: {} });
  await page.getByRole('button', { name: 'В профиль' }).click();

  const request = await submit(page);
  expect(request.postDataJSON().publication_scope).toBe('profile');

  const status = page.getByRole('status');
  await expect(status.getByRole('heading', { name: 'Работа опубликована в профиль!' })).toBeVisible();
  await expect(status).toContainText('Теперь она доступна в вашем профиле.');
  await expect(status).not.toContainText('Теперь она доступна в ленте');
});

test('feed downgrade uses the server publication scope instead of the requested scope', async ({ page }) => {
  await openPublish(page, { publication_scope: 'profile', downgraded_to_profile: true, share: {} });

  const request = await submit(page);
  expect(request.postDataJSON().publication_scope).toBe('feed');

  const status = page.getByRole('status');
  await expect(status.getByRole('heading', { name: 'Работа опубликована в профиль!' })).toBeVisible();
  await expect(status).toContainText('Лента сейчас недоступна, поэтому работа опубликована только в профиль.');
  await expect(status).not.toContainText('Теперь она доступна в ленте');
});

test('successful feed publish still reports feed and profile visibility', async ({ page }) => {
  await openPublish(page, { publication_scope: 'feed', downgraded_to_profile: false, share: {} });
  await submit(page);

  const status = page.getByRole('status');
  await expect(status.getByRole('heading', { name: 'Работа опубликована!' })).toBeVisible();
  await expect(status).toContainText('Теперь она доступна в ленте и профиле.');
});
