import { expect, test } from '@playwright/test';

async function openLanding(page, query = '') {
  await page.route('**/api/v1/browser-auth/config', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ bot_username: 'RoxyTestBot' }),
  }));
  await page.route('https://telegram.org/js/telegram-widget.js?22', (route) => route.fulfill({
    status: 200,
    contentType: 'application/javascript',
    body: 'window.__roxyWidgetLoaded = true;',
  }));
  await page.goto(`/${query}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Создавай фото и видео с AI' })).toBeVisible();
}

test('browser visitors see the full ROXY landing with working sections', async ({ page }) => {
  await openLanding(page);

  await expect(page.locator('.roxy-browser-landing')).toBeVisible();
  await expect(page.locator('#features')).toContainText('Всё для твоего креатива');
  await expect(page.locator('#how')).toContainText('Три шага от идеи до результата');
  await expect(page.locator('#examples')).toContainText('Найди свой визуальный стиль');
  await expect(page.locator('#telegram-login')).toContainText('Войти с Telegram');
  const mosaic = page.locator('.roxy-film-mosaic');
  await expect(mosaic.locator('.roxy-film-tile')).toHaveCount(9);
  await expect(page.locator('.roxy-film-chrome')).toBeVisible();
  const atlas = await page.locator('.roxy-film-tile-portrait').evaluate((node) => getComputedStyle(node).backgroundImage);
  expect(atlas).toContain('/mini-app/roxy-film/atlas-1920.webp');
  expect(atlas).toContain('/mini-app/roxy-film/atlas-3840.webp');
  const image = await page.request.get('/mini-app/roxy-film/atlas-1920.webp');
  expect(image.status()).toBe(200);
  expect(image.headers()['content-type']).toContain('image/webp');
  expect((await image.body()).byteLength).toBeGreaterThan(100_000);
  await expect(page.locator('.roxy-examples-mosaic figure')).toHaveCount(6);
  await expect(page.getByText('KSU')).toHaveCount(0);

  const nav = page.locator('.roxy-landing-nav');
  await page.evaluate(() => window.scrollTo(0, Math.min(document.body.scrollHeight, 1200)));
  await expect.poll(() => nav.evaluate((node) => Math.round(node.getBoundingClientRect().top))).toBe(0);
});

test('Telegram CTA preserves a referral startapp payload', async ({ page }) => {
  await openLanding(page, '?startapp=ref_777');

  const launch = page.getByRole('link', { name: /Запустить в Telegram/ }).first();
  await expect(launch).toHaveAttribute('href', 'https://t.me/RoxyTestBot?startapp=ref_777');
});

for (const width of [320, 390, 768, 1280]) {
  test(`film-mosaic landing stays within the viewport at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await openLanding(page);
    await expect(page.locator('.roxy-landing-actions .roxy-landing-button-primary')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.getByRole('link', { name: /Запустить в Telegram/ }).first()).toBeVisible();
  });
}

test('browser user can reach Telegram login and return to gallery', async ({ page }) => {
  await openLanding(page);
  await page.getByRole('link', { name: /Начать создавать/ }).click();
  await expect(page).toHaveURL(/#telegram-login$/);
  await expect(page.locator('#telegram-login .roxy-login-widget')).toHaveCount(1);
  await page.locator('.roxy-landing-footer').getByRole('link', { name: 'Галерея' }).click();
  await expect(page).toHaveURL(/#examples$/);
  await expect(page.locator('.roxy-examples-mosaic figure')).toHaveCount(6);
});


test('mobile menu opens, navigates and closes cleanly', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page);
  const details = page.locator('.roxy-landing-mobile-menu');
  const trigger = details.locator('summary');
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(details).toHaveAttribute('open', '');
  await details.getByRole('link', { name: 'Возможности' }).click();
  await expect(page).toHaveURL(/#features$/);
  await expect(details).not.toHaveAttribute('open', '');
});

test('root is marketing while /mini-app/ is the guest app sign-in', async ({ page }) => {
  await openLanding(page);
  await expect(page.locator('.roxy-browser-landing')).toBeVisible();
  await page.locator('.roxy-film-hero-copy').getByRole('link', { name: /Начать создавать/ }).click();
  await expect(page).toHaveURL(/\/mini-app\//);
  await expect(page.locator('.roxy-app-login')).toBeVisible();
  await expect(page.locator('.roxy-browser-landing')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Вход в ROXY' })).toBeVisible();
  await page.getByRole('link', { name: /На сайт ROXY/ }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('.roxy-browser-landing')).toBeVisible();
});

test('deleted /landing/ route never serves marketing', async ({ page }) => {
  const response = await page.goto('/landing/', { waitUntil: 'domcontentloaded' });
  expect(response?.status()).toBe(404);
});
