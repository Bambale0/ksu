import { expect, test } from '@playwright/test';

test('support exposes the direct Telegram contact', async ({ page }) => {
  await page.addInitScript(() => {
    window.__supportTelegramUrl = '';
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {},
        expand() {},
        close() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        openTelegramLink(url) { window.__supportTelegramUrl = url; },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' }) });
    }
    if (path === '/api/v1/support/tickets') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
  });

  await page.goto('/mini-app/support/');

  await expect(page.getByText('@korkinaxenia')).toBeVisible();
  const contact = page.getByRole('button', { name: 'Написать @korkinaxenia' });
  await expect(contact).toBeVisible();
  await contact.click();

  await expect.poll(() => page.evaluate(() => window.__supportTelegramUrl)).toBe('https://t.me/korkinaxenia');
});
