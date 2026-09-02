import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '20.00',
  ui_schema: {
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
    ],
    defaults: {},
  },
};

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'Admin' } },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
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

    if (path === '/api/v1/me') {
      return json({
        id: 'user-1',
        telegram_id: 777,
        first_name: 'Admin',
        balance_rox: '100.00',
        is_admin: true,
        billing_mode: 'admin_free',
      });
    }
    if (path === '/api/v1/generations/models') {
      return json({ models: [model], families: [] });
    }
    if (path === '/api/v1/generations/quote') {
      return json({
        model_id: model.id,
        cost_rox: '20.00',
        cost_rub: '20.00',
        retail_cost_rox: '20.00',
        effective_cost_rox: '0.00',
        effective_cost_rub: '0.00',
        admin_free: true,
      });
    }
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: true, items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    return json({ items: [] });
  });
}

test('Create displays the effective ROX debit instead of retail quote', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=create');

  const prompt = page.locator('textarea').first();
  await expect(prompt).toBeVisible();
  await prompt.fill('Неоновый портрет');

  const quote = page.locator('.quote-box');
  await expect(quote.locator('strong')).toHaveText('0 ROX');
  await expect(quote).not.toContainText('20 ROX');

  const create = page.locator('.create-summary button.primary').first();
  await expect(create).toContainText('Создать · 0 ROX');
  await expect(create).not.toContainText('20 ROX');
});
