import { expect, test } from '@playwright/test';

test.describe('Infinite Feed landing', () => {
  test('presents the creator story and links into ROXY', async ({ page }) => {
    await page.goto('/mini-app/landing/');

    await expect(page.getByRole('heading', { name: /Вдохновляйся/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Создавай любой контент' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Лучшие AI‑модели в одном месте' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Лента вдохновения' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'От идеи до публикации' })).toBeVisible();

    const openRoxy = page.getByRole('link', { name: /Открыть ROXY/ }).first();
    await expect(openRoxy).toHaveAttribute('href', '/mini-app/');
  });

  test('keeps the mobile landing readable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/mini-app/landing/');

    await expect(page.getByText('ROXY · твоя вселенная креатива')).toBeVisible();
    await expect(page.getByRole('link', { name: /Открыть ROXY/ }).first()).toBeVisible();
    await expect(page.locator('main')).not.toHaveCSS('overflow-x', 'visible');
  });
});
