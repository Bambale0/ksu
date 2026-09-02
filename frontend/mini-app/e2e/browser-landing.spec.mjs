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
  await page.goto(`/mini-app/${query}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Создавай фото и видео с AI' })).toBeVisible();
}

test('browser visitors see the full ROXY landing with working sections', async ({ page }) => {
  await openLanding(page);

  await expect(page.locator('.roxy-browser-landing')).toBeVisible();
  await expect(page.locator('#features')).toContainText('Всё для твоего креатива');
  await expect(page.locator('#how')).toContainText('Три шага от идеи до результата');
  await expect(page.locator('#examples')).toContainText('Найди свой визуальный стиль');
  await expect(page.locator('#telegram-login')).toContainText('Войти с Telegram');
  const hero = page.locator('.roxy-landing-hero-art img');
  await expect(hero).toHaveAttribute('src', /^data:image\/webp;base64,/);
  await expect.poll(() => hero.evaluate((image) => image.complete && image.naturalWidth > 0)).toBe(true);
  await expect(page.getByText('KSU')).toHaveCount(0);
});

test('Telegram CTA preserves a referral startapp payload', async ({ page }) => {
  await openLanding(page, '?startapp=ref_777');

  const launch = page.getByRole('link', { name: /Запустить в Telegram/ }).first();
  await expect(launch).toHaveAttribute('href', 'https://t.me/RoxyTestBot?startapp=ref_777');
});

test('landing stays inside the mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page);

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await expect(page.getByRole('link', { name: /Запустить/ }).first()).toBeVisible();
});
