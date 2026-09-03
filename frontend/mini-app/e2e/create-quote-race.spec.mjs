import { expect, test } from '@playwright/test';

const model = {
  id: 'quote-race-model',
  title: 'Quote Race Model',
  family: 'quote_race',
  media_type: 'image',
  operation: 'generate',
  price_rox: '10.00',
  ui_schema: {
    defaults: { quality: 'standard' },
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'quality', label: 'Качество', control: 'select', suggestions: ['standard', 'pro'] },
    ],
  },
};

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=quote-race&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
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

    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100.00' });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [], max_generation_quantity: 4 });
    if (path === '/api/v1/generations/quote') {
      const body = request.postDataJSON();
      const pro = body?.parameters?.quality === 'pro';
      if (pro) await new Promise((resolve) => setTimeout(resolve, 700));
      return json({
        model_id: model.id,
        cost_rox: pro ? '30.00' : '10.00',
        effective_cost_rox: pro ? '30.00' : '10.00',
        retail_cost_rox: pro ? '30.00' : '10.00',
        cost_rub: pro ? '30.00' : '10.00',
      });
    }
    if (path === '/api/v1/generations' && request.method() === 'POST') return json({ id: 'gen-1', status: 'queued' });
    if (path === '/api/v1/generations/gen-1') return json({ id: 'gen-1', status: 'succeeded', model, result_url: 'https://example.test/result.png' });
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

test('changing a price-sensitive field blocks old-quote submit until the fresh quote resolves', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=create');

  const prompt = page.locator('textarea').first();
  const quoteBox = page.locator('.quote-box');
  const create = page.locator('.create-summary button.primary').first();
  await expect(prompt).toBeVisible();
  await expect(quoteBox.locator('strong')).toHaveText('10 ROX');
  await prompt.fill('Тест billing race');

  // Prompt content affects the generation, not its price. It must not create a
  // temporary billing lock or force the customer to wait for a quote that the
  // application intentionally does not request for free-form copy changes.
  expect(await create.getAttribute('data-roxy-quote-stale')).toBeNull();
  expect(await quoteBox.getAttribute('data-roxy-quote-stale')).toBeNull();
  await expect(create).toBeEnabled();
  await expect(create).toContainText('Создать · 10 ROX');

  let generationPosts = 0;
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/generations' && request.method() === 'POST') generationPosts += 1;
  });

  const quality = page.getByLabel('Качество');
  await quality.selectOption('pro');

  await expect(create).toHaveAttribute('data-roxy-quote-stale', 'true');
  await expect(create).toHaveAttribute('aria-disabled', 'true');
  await expect(quoteBox).toHaveAttribute('data-roxy-quote-stale', 'true');

  // Programmatic click bypasses pointer styling; the capture guard must still
  // prevent the old 10 ROX quote from submitting the new 30 ROX payload.
  await create.evaluate((button) => button.click());
  await page.waitForTimeout(150);
  expect(generationPosts).toBe(0);

  await expect(quoteBox.locator('strong')).toHaveText('30 ROX', { timeout: 3000 });
  await expect(create).not.toHaveAttribute('data-roxy-quote-stale', 'true');
  await expect(create).not.toHaveAttribute('aria-disabled', 'true');
  await expect(create).toContainText('Создать · 30 ROX');
  await expect(create).toBeEnabled();

  const generationRequestPromise = page.waitForRequest((request) => {
    const path = new URL(request.url()).pathname;
    return path === '/api/v1/generations' && request.method() === 'POST';
  });
  await create.click();
  const generationRequest = await generationRequestPromise;
  const submitted = generationRequest.postDataJSON();
  expect(submitted.parameters.quality).toBe('pro');
  expect(submitted.prompt).toBe('Тест billing race');
  expect(generationPosts).toBe(1);
});
