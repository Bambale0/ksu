import { expect, test } from '@playwright/test';

const model = {
  id: 'double-submit-model',
  title: 'Double Submit Model',
  family: 'double_submit',
  media_type: 'image',
  operation: 'generate',
  price_rox: '10.00',
  ui_schema: {
    defaults: {},
    fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
  },
};

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=double-submit&hash=test',
        initDataUnsafe: { user: { id: 778, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  await installTelegram(page);
  let creates = 0;
  await page.exposeFunction('__createCount', () => creates);
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 778, first_name: 'QA', balance_rox: '100.00', is_admin: false });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [], max_generation_quantity: 4 });
    if (path === '/api/v1/generations/quote') return json({ model_id: model.id, cost_rox: '10.00', effective_cost_rox: '10.00', retail_cost_rox: '10.00' });
    if (path === '/api/v1/generations' && request.method() === 'POST') {
      creates += 1;
      await new Promise((resolve) => setTimeout(resolve, 250));
      return json({ id: `gen-${creates}`, status: 'queued' });
    }
    if (path.startsWith('/api/v1/generations/gen-')) return json({ id: path.split('/').pop(), status: 'succeeded', model, result_url: 'https://example.test/result.png' });
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

test('rapid double click submits exactly one generation request', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=create');

  const prompt = page.locator('textarea').first();
  await prompt.fill('Один запуск, даже если нажать дважды');

  const create = page.locator('.create-summary button.primary').first();
  await expect(create).toBeEnabled();
  await expect(create).toContainText('Создать · 10 ROX');

  const request = page.waitForRequest((candidate) => {
    const path = new URL(candidate.url()).pathname;
    return path === '/api/v1/generations' && candidate.method() === 'POST';
  });

  await create.evaluate((button) => {
    button.click();
    button.click();
  });

  await request;
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => window.__createCount())).toBe(1);
});
