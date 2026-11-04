import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2', title: 'Nano Banana 2', family: 'nano_banana',
  media_type: 'image', operation: 'generate_or_edit', price_rox: '15.00',
  ui_schema: {
    groups: [{ id: 'prompt', title: 'Описание' }],
    fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true }],
    defaults: {},
  },
};

async function mockDesign(page) {
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=audit-design&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/telegram-web-app.js*', (route) => route.fulfill({ contentType: 'application/javascript', body: '' }));
  await page.route('**/api/v1/**', async (route) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) return route.abort();
    const path = new URL(route.request().url()).pathname;
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [{
      id: 'nano_banana', family: 'nano_banana', title: 'Nano Banana', media_types: ['image'],
      variant_count: 1, price_from_rox: '15.00',
      variants: [{ id: model.id, title: model.title, version: '2', media_type: 'image', operation: 'auto', price_rox: '15.00' }],
    }] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/promocodes/active') return json({ active: false, code: null });
    if (path === '/api/v1/me/overview') return json({ notifications: {}, support: {}, social: {}, partner: {}, payments: {} });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy?start=ref_777', first_line: 2, second_line: 1, partner_balance_rub: '1200' });
    return json({ items: [] });
  });
}

async function openDesign(page, route) {
  await page.goto(`/mini-app/?route=${route}`);
  await expect(page.locator('.roxy-app')).toBeVisible();
}

test('creation shows its own instructions instead of CSS-generated generic copy', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDesign(page);
  await openDesign(page, 'create');
  const head = page.locator('.create-screen .screen-head');
  await expect(head.locator('p')).toHaveText('Опишите идею, добавьте примеры и выберите подходящий формат.');
  await expect(head.locator('p')).toBeVisible();
  expect(await head.evaluate((node) => getComputedStyle(node, '::after').content)).not.toContain('Выберите действие');
});

for (const width of [320, 390]) {
  test(`model names, prices and navigation remain legible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await mockDesign(page);
    await openDesign(page, 'create');
    const title = page.locator('.family-card strong').filter({ hasText: 'Nano Banana' }).first();
    await expect(title).toBeVisible();
    const titleSize = await title.evaluate((node) => ({ scroll: node.scrollWidth, client: node.clientWidth }));
    expect(titleSize.scroll).toBeLessThanOrEqual(titleSize.client + 1);
    const price = page.locator('.family-card .price-pill').first();
    expect(await price.evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(11);
    const labels = page.locator('.bottom-nav button small');
    await expect(labels).toHaveCount(5);
    for (const label of await labels.all()) {
      await expect(label).toBeVisible();
      expect(await label.evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(11);
    }
  });
}

test('secondary catalog services can be expanded with the keyboard and opened', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDesign(page);
  await openDesign(page, 'home');
  const services = page.locator('#roxy-backend-parity-features');
  const group = services.locator('details').filter({ has: page.locator('.roxy-service-card', { hasText: 'Поддержка' }) });
  await expect(group).toHaveCount(1);
  const support = group.locator('.roxy-service-card', { hasText: 'Поддержка' });
  await expect(support).toBeHidden();
  await group.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(support).toBeVisible();
  await support.click();
  await expect(page).toHaveURL(/\/mini-app\/support\//);
});

test('catalog tool cards use the desktop width instead of one long column', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockDesign(page);
  await openDesign(page, 'home');
  const cards = page.locator('#roxy-catalog-feature-hub .catalog-feature-grid').first().locator('.catalog-feature-card');
  await expect(cards).toHaveCount(3);
  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  expect(Math.abs(first.y - second.y)).toBeLessThanOrEqual(1);
  expect(second.x).toBeGreaterThan(first.x + first.width);
});

test('history uses public action names and no internal implementation copy', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDesign(page);
  await openDesign(page, 'history');
  const panel = page.locator('[data-customer-parity-panel]');
  await expect(panel.getByRole('heading', { name: 'Управление работами' })).toBeVisible();
  await expect(panel).not.toContainText(/backend|\bedit\b|\banimate\b|\brepeat\b/i);
  await expect(panel.getByRole('button', { name: /Действия с работами/ })).toBeVisible();
});

test('partner transfer fields keep the product form styling and editable focus', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDesign(page);
  await openDesign(page, 'partners');
  const transfer = page.locator('[data-partner-rox-transfer]');
  const recipient = transfer.getByLabel('ID пользователя', { exact: true });
  await expect(recipient).toBeVisible();
  const style = await recipient.evaluate((node) => ({ height: node.getBoundingClientRect().height, radius: parseFloat(getComputedStyle(node).borderRadius) }));
  expect(style.height).toBeGreaterThanOrEqual(44);
  expect(style.radius).toBeGreaterThanOrEqual(10);
  await recipient.fill('123456789');
  await expect(recipient).toHaveValue('123456789');
  await expect(recipient).toBeFocused();
  await expect(transfer.getByRole('button', { name: 'Перевести ROX', exact: true })).toBeDisabled();
});
