import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt'],
  price_rox: '15.00',
  ui_schema: { fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }], defaults: {} },
};

async function mockNewUser(page) {
  let completed = false;

  await page.addInitScript(() => {
    window.__roxyBackCallback = null;
    window.__roxyBackVisible = false;
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: {
          show() { window.__roxyBackVisible = true; },
          hide() { window.__roxyBackVisible = false; },
          onClick(callback) { window.__roxyBackCallback = callback; },
          offClick(callback) {
            if (window.__roxyBackCallback === callback) window.__roxyBackCallback = null;
          },
        },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/onboarding/complete' && request.method() === 'POST') {
      completed = true;
      return json({ enabled: true, version: '2', completed: true, completed_version: '2' });
    }
    if (path === '/api/v1/onboarding') {
      return json({ enabled: true, version: '2', completed, rules_url: null, privacy_url: null });
    }
    if (path === '/api/v1/me') {
      return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', created_at: '2026-01-01T00:00:00Z', is_active: true });
    }
    if (path === '/api/v1/me/overview') return json({ works_count: 0, publications_count: 0, likes_count: 0 });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/feed') return json({ items: [], has_more: false });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path.includes('/notifications')) return json({ items: [], unread_count: 0 });
    return json({ items: [] });
  });
}

async function next(page, label = 'Дальше') {
  await page.getByRole('button', { name: label, exact: true }).click();
}

test('new user completes full six-step onboarding and enters Create', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockNewUser(page);
  await page.goto('/mini-app/?route=home');

  const onboarding = page.locator('.roxy-onboarding-v2');
  await expect(onboarding).toBeVisible();
  await expect(page.getByRole('heading', { name: 'QA, знакомьтесь с ROXY' })).toBeVisible();
  await expect(page.getByLabel('Шаг 1 из 6')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Пропустить' })).toBeVisible();

  await next(page, 'Покажите, как всё устроено');
  await expect(page.getByRole('heading', { name: 'Выберите задачу — ROXY подберёт нужный инструмент' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean(window.__roxyBackVisible))).toBe(true);

  await page.evaluate(() => window.__roxyBackCallback?.());
  await expect(page.getByRole('heading', { name: 'QA, знакомьтесь с ROXY' })).toBeVisible();

  await next(page, 'Покажите, как всё устроено');
  await next(page);
  await expect(page.getByRole('heading', { name: 'Опишите идею и добавьте свои материалы' })).toBeVisible();
  await next(page);
  await expect(page.getByRole('heading', { name: 'Готовая работа не потеряется' })).toBeVisible();
  await next(page);
  await expect(page.getByRole('heading', { name: 'Публикуйте только то, чем хотите делиться' })).toBeVisible();
  await next(page);
  await expect(page.getByRole('heading', { name: 'Стоимость видна до запуска' })).toBeVisible();
  await expect(onboarding.getByText('150', { exact: true })).toBeVisible();

  await next(page, 'Начать создавать');
  await page.waitForURL('**/mini-app/?route=create');
  await expect(page.locator('.roxy-onboarding-v2')).toHaveCount(0);
});
