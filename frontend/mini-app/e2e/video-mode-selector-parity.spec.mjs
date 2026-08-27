import { expect, test } from '@playwright/test';

async function mockPromptToolsApi(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=mode-selector&auth_date=1787760000&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Mode Test' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        setHeaderColor() {}, setBackgroundColor() {}, setBottomBarColor() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.pathname === '/api/v1/me') return json({ id: 'mode-user', telegram_id: 999, first_name: 'Mode Test', balance_rox: '100.00', is_admin: false, billing_mode: 'wallet' });
    if (url.pathname === '/api/v1/prompt-tools') return json({ items: [] });
    return json({ items: [] });
  });
}

test('photo and video tabs use the same active-state contract', async ({ page }) => {
  await mockPromptToolsApi(page);
  await page.goto('/mini-app/prompt-tools');

  const tabs = page.getByRole('tablist', { name: 'Режим промпта' });
  const photo = tabs.getByRole('tab', { name: /Фото/ });
  const video = tabs.getByRole('tab', { name: /Видео/ });

  await expect(photo).toHaveAttribute('aria-selected', 'true');
  await expect(photo).toContainText('✅');
  await expect(video).toHaveAttribute('aria-selected', 'false');
  await expect(video).not.toContainText('✅');

  await video.click();

  await expect(video).toHaveAttribute('aria-selected', 'true');
  await expect(video).toContainText('✅');
  await expect(photo).toHaveAttribute('aria-selected', 'false');
  await expect(photo).not.toContainText('✅');
  await expect(page).toHaveURL(/mode=video/);
});
