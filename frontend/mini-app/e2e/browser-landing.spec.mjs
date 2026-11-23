import { expect, test } from '@playwright/test';

async function openAppLogin(page, query = '') {
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
  await page.goto('/mini-app/' + query, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Твоя творческая студия' })).toBeVisible();
}

test('unauthenticated /mini-app/ shows application sign-in, not marketing landing', async ({ page }) => {
  await openAppLogin(page);
  await expect(page.locator('.roxy-app-login')).toBeVisible();
  await expect(page.locator('.roxy-login-widget')).toHaveCount(1);
  await expect(page.locator('.roxy-film-mosaic')).toHaveCount(0);
  await expect(page.locator('.roxy-browser-landing')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Посмотреть возможности ROXY' })).toHaveAttribute('href', '/');
  await expect(page.getByText('KSU')).toHaveCount(0);
});

test('Telegram login preserves a referral startapp payload', async ({ page }) => {
  await openAppLogin(page, '?startapp=ref_777');
  const launch = page.getByRole('link', { name: /Открыть в Telegram/ }).first();
  await expect(launch).toHaveAttribute('href', 'https://t.me/RoxyTestBot?startapp=ref_777');
});

for (const width of [320, 390, 768, 1280]) {
  test('unauthenticated app login fits inside ' + width + 'px', async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await openAppLogin(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator('.roxy-app-login-panel')).toBeVisible();
  });
}

test('failed Telegram login config yields an accessible error rather than marketing fallback', async ({ page }) => {
  await page.route('**/api/v1/browser-auth/config', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'temporary outage' }),
  }));
  await page.goto('/mini-app/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.roxy-app-login-error[role="alert"]')).toContainText('Вход через Telegram временно недоступен.');
  await expect(page.locator('.roxy-browser-landing')).toHaveCount(0);
});
