import { expect, test } from '@playwright/test';

async function mockPaymentsShell(page) {
  await page.addInitScript(() => {
    window.__telegramShareCalls = [];
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {},
        openTelegramLink(url) { window.__telegramShareCalls.push(url); },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/payments/card/packages') return json({ provider: 'card', label: 'Lava Top', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments/yookassa/packages') return json({ provider: 'yookassa', label: 'ЮKassa', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments/crypto/packages') return json({ provider: 'cryptobot', label: 'CryptoBot', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments/crypto/2328/packages') return json({ provider: '2328', label: '2328', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments') return json({ items: [] });
    return json({ items: [] });
  });
}

test('Telegram share sends the work link exactly once', async ({ page }) => {
  await mockPaymentsShell(page);
  await page.goto('/mini-app/payments/');

  await expect.poll(() => page.evaluate(() => Boolean(window.Telegram?.WebApp?.__roxyShareCopyUxPatched))).toBe(true);

  const targetLink = 'https://t.me/RoxyExampleBot?startapp=feed_00000000-0000-4000-8000-000000000001_ref_777';
  const duplicateShareUrl = `https://t.me/share/url?url=${encodeURIComponent(targetLink)}&text=${encodeURIComponent(`Посмотри мою работу в ROXY ✨\n${targetLink}`)}`;

  await page.evaluate((url) => window.Telegram.WebApp.openTelegramLink(url), duplicateShareUrl);
  const dialog = page.getByRole('dialog', { name: 'Поделиться работой' });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: /Поделиться в Telegram/ }).click();

  await expect.poll(() => page.evaluate(() => window.__telegramShareCalls.length)).toBe(1);
  const actual = await page.evaluate(() => window.__telegramShareCalls[0]);
  const parsed = new URL(actual);

  expect(parsed.pathname).toBe('/share/url');
  expect(parsed.searchParams.get('url')).toBe(targetLink);
  expect(parsed.searchParams.get('text')).toBe('Посмотри мою работу в ROXY ✨');
  expect(actual.split(encodeURIComponent(targetLink)).length - 1).toBe(1);
});
