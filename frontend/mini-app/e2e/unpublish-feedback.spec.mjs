import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=unpublish-feedback&hash=test',
        initDataUnsafe: { user: { id: 991, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  await installTelegram(page);
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/feed/gen-1/remove' && request.method() === 'POST') {
      return json({ id: 'gen-1', publication_scope: 'private', is_public_feed: false, is_profile_visible: false });
    }
    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 991, first_name: 'QA', balance_rox: '100.00' });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [], max_generation_quantity: 4 });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    return json({ items: [] });
  });
}

test('successful unpublish cannot be reported as a new profile publication', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=home');

  const response = await page.evaluate(async () => {
    const result = await fetch('/api/v1/feed/gen-1/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_scope: 'private' }),
    });
    return result.status;
  });
  expect(response).toBe(200);

  await page.evaluate(() => {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.setAttribute('role', 'status');
    toast.textContent = 'Работа опубликована в профиле';
    document.body.appendChild(toast);
  });

  const toast = page.locator('.toast[role="status"]');
  await expect(toast).toHaveText('Публикация убрана');
  await expect(toast).toHaveAttribute('data-roxy-unpublish-feedback', 'true');
  await expect(page.getByText('Работа опубликована в профиле')).toHaveCount(0);
});

test('normal profile publication feedback is untouched without a successful remove', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=home');

  await page.evaluate(() => {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.setAttribute('role', 'status');
    toast.textContent = 'Работа опубликована в профиле';
    document.body.appendChild(toast);
  });

  const toast = page.locator('.toast[role="status"]');
  await expect(toast).toHaveText('Работа опубликована в профиле');
  await expect(toast).not.toHaveAttribute('data-roxy-unpublish-feedback', 'true');
});
