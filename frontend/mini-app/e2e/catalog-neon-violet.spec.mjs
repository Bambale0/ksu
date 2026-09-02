import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockCatalog(page) {
  await installTelegram(page);
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/me') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'user_1', telegram_id: 999, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' }) });
    if (url.pathname === '/api/v1/onboarding') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false, completed: true }) });
    if (url.pathname === '/api/v1/catalog/features') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [
      { id: 'prompt', title: 'Промпт', description: 'Создание промпта', price_rox: 7, route: '/mini-app/prompt-tools/?mode=prompt' },
      { id: 'prompt-seedance', title: 'Сценарий для видео', description: 'Seedance сценарий', price_rox: 7, route: '/mini-app/prompt-tools/?mode=seedance' },
    ] }) });
    if (url.pathname === '/api/v1/trends') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    if (url.pathname === '/api/v1/feed') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    if (url.pathname === '/api/v1/generations') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], has_more: false, next_before: null }) });
    if (url.pathname === '/api/v1/models') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
}

test('catalog uses the neon violet visual system for sections and feature cards', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  const visual = await page.evaluate(() => {
    const section = document.querySelector('.catalog-section');
    const card = document.querySelector('.catalog-feature-card');
    const title = document.querySelector('.catalog-section-title');
    const copy = document.querySelector('.catalog-section-copy');
    const sectionStyle = getComputedStyle(section);
    const cardStyle = getComputedStyle(card);
    const titleStyle = getComputedStyle(title);
    const copyStyle = getComputedStyle(copy);
    return {
      sectionBorder: sectionStyle.borderColor,
      sectionShadow: sectionStyle.boxShadow,
      sectionBackground: sectionStyle.backgroundImage,
      cardBorder: cardStyle.borderColor,
      cardShadow: cardStyle.boxShadow,
      cardBackground: cardStyle.backgroundImage,
      cardFill: cardStyle.backgroundColor,
      titleColor: titleStyle.color,
      titleFill: titleStyle.webkitTextFillColor,
      copyColor: copyStyle.color,
      copyFill: copyStyle.webkitTextFillColor,
    };
  });

  expect(visual).toMatchObject({
    sectionBorder: 'rgba(168, 85, 247, 0.48)',
    cardBorder: 'rgba(168, 85, 247, 0.46)',
    cardFill: 'rgb(201, 140, 255)',
    titleColor: 'rgb(215, 164, 255)',
    titleFill: 'rgb(215, 164, 255)',
    copyColor: 'rgb(189, 140, 255)',
    copyFill: 'rgb(189, 140, 255)',
  });
});

test('Seedance catalog card advertises the real 5-second minimum price', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockCatalog(page);
  await page.goto('/mini-app/?route=catalog');

  const seedance = page.locator('[data-catalog-feature="prompt-seedance"]');
  await expect(seedance).toBeVisible();
  await expect(seedance.locator('.catalog-feature-pill')).toHaveText('от 30 ROX');

  await seedance.click();

  await expect(page).toHaveURL(/\/mini-app\/prompt-tools\/\?mode=seedance/);
  await expect(page.getByRole('button', { name: 'Сценарий' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Стоимость').locator('..').getByRole('heading', { name: '30 ROX' })).toBeVisible();
  await expect(page.getByRole('button', { name: '5 сек', exact: true })).toHaveClass(/active/);
});
