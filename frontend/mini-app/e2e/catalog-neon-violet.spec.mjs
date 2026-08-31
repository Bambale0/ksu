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

async function mockCatalog(page) {
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

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    return json({ items: [] });
  });
}

test('catalog service cards render neon violet instead of Telegram link blue', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  const section = page.locator('#roxy-backend-parity-features');
  await expect(section.getByRole('heading', { name: 'Сервисы ROXY' })).toBeVisible();

  const card = section.locator('.roxy-service-card', { hasText: 'Аккаунт и сервисы' });
  const title = card.locator('strong');
  const copy = card.locator('small');
  await expect(card).toBeVisible();

  const rendered = await card.evaluate((node) => ({
    cardColor: getComputedStyle(node).color,
    cardFill: getComputedStyle(node).getPropertyValue('-webkit-text-fill-color'),
    titleColor: getComputedStyle(node.querySelector('strong')).color,
    titleFill: getComputedStyle(node.querySelector('strong')).getPropertyValue('-webkit-text-fill-color'),
    copyColor: getComputedStyle(node.querySelector('small')).color,
    copyFill: getComputedStyle(node.querySelector('small')).getPropertyValue('-webkit-text-fill-color'),
  }));

  expect(rendered).toEqual({
    cardColor: 'rgb(201, 140, 255)',
    cardFill: 'rgb(201, 140, 255)',
    titleColor: 'rgb(215, 164, 255)',
    titleFill: 'rgb(215, 164, 255)',
    copyColor: 'rgb(189, 140, 255)',
    copyFill: 'rgb(189, 140, 255)',
  });
});

test('trend library is the first catalog content below the heading', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  const trends = page.locator('#roxy-live-trends');
  await expect(trends).toBeVisible();

  await expect.poll(() => trends.evaluate((node) => node.previousElementSibling?.classList.contains('screen-head') === true)).toBe(true);
});
