import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: { fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }], defaults: {} },
};

async function mockHomeCatalog(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=home-catalog&hash=test',
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

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', is_admin: false });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/me/overview') return json({ notifications: {}, support: {}, social: {}, partner: {}, payments: {} });
    return json({ items: [] });
  });
}

async function expectCanonicalCatalog(page) {
  const oldHome = page.locator('.bottom-nav button[data-roxy-customer-route="home"]');
  const catalog = page.locator('.bottom-nav button[data-roxy-customer-route="catalog"]');

  await expect(oldHome).toBeHidden();
  await expect(catalog).toBeVisible();
  await expect(catalog.locator('small')).toHaveText('Каталог');
  await expect(catalog).toHaveAttribute('aria-current', 'page');
  await expect(catalog).toHaveAttribute('data-home-catalog', 'true');
  await expect(catalog).toHaveClass(/active/);
  await expect(page.locator('#roxy-catalog-feature-hub')).toBeVisible();
  await expect(page.locator('#roxy-home-live-trends')).toBeVisible();
  await expect(page.locator('#roxy-home-trend-folders')).toBeVisible();
  await expect(page.locator('.ai-reference-home-card')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Что создаём?' })).toBeHidden();
  await expect(page.locator('#roxy-catalog-trend-folders')).toHaveCount(0);
}

test('bot startup opens the same visible Catalog root', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=home');

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});

test('tapping visible Catalog always opens canonical home instead of the old catalog screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=home');

  await page.locator('.bottom-nav button[data-roxy-customer-route="create"]').click();
  await expect(page).toHaveURL(/[?&]route=create(?:&|$)/);

  const catalog = page.locator('.bottom-nav button[data-roxy-customer-route="catalog"]');
  await expect(catalog).toBeVisible();
  await catalog.click();

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});

test('legacy route=catalog normalizes to the same visible Catalog root', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHomeCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
  await expectCanonicalCatalog(page);
});
