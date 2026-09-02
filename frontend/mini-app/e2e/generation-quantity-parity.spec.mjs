import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt'],
  price_rox: '15.00',
  ui_schema: {
    fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
    defaults: { prompt: 'portrait' },
  },
};

async function mockCreate(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  const quoteQuantities = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ max_generation_quantity: 4, models: [model], families: [] });
    if (path === '/api/v1/generations/quote' && request.method() === 'POST') {
      const body = request.postDataJSON();
      quoteQuantities.push(body.quantity);
      return json({ cost_rox: String(15 * Number(body.quantity || 1)), cost_rub: '0.00', unit_price_rox: '15.00' });
    }
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [], has_more: false });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    return json({ items: [] });
  });

  return quoteQuantities;
}

test('create screen exposes one visible quantity control with only 1-4 launches', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const quoteQuantities = await mockCreate(page);
  await page.goto('/mini-app/?route=create');

  const create = page.locator('.create-screen');
  await expect(create).toBeVisible();

  const quantityPanel = create.locator('.generation-quantity-panel');
  await expect(quantityPanel).toHaveCount(1);
  await expect(quantityPanel).toBeVisible();
  await expect(create.locator('[data-roxy-legacy-quantity-hidden="true"]')).toBeHidden();

  for (const count of [1, 2, 3, 4]) {
    await expect(quantityPanel.getByRole('button', { name: String(count), exact: true })).toBeVisible();
  }
  await expect(quantityPanel.getByRole('button', { name: '5', exact: true })).toHaveCount(0);
  await expect(quantityPanel.getByRole('button', { name: '6', exact: true })).toHaveCount(0);

  await quantityPanel.getByRole('button', { name: '4', exact: true }).click();
  await expect(quantityPanel.getByRole('button', { name: '4', exact: true })).toHaveClass(/active/);
  await expect(quantityPanel).toContainText('Стоимость за 4');
  await expect.poll(() => quoteQuantities.includes(4)).toBe(true);
  expect(await page.evaluate(() => window.__roxyMaxGenerationQuantity)).toBe(4);
});
