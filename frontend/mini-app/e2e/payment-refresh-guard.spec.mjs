import { expect, test } from '@playwright/test';

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=payment-refresh&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

test('payment refresh disables stale actions until authoritative data returns', async ({ page }) => {
  await installTelegram(page);
  let yooKassaLoads = 0;
  const catalog = {
    provider: 'yookassa',
    label: 'ЮKassa',
    configured: true,
    currencies: ['RUB'],
    packages: {
      starter: { credits: '300', bonus_credits: '30', total_credits: '330', prices: { RUB: '300' } },
    },
  };

  await page.route('**/api/v1/payments/yookassa/packages', async (route) => {
    yooKassaLoads += 1;
    if (yooKassaLoads > 1) await new Promise((resolve) => setTimeout(resolve, 400));
    return json(route, catalog);
  });
  await page.route('**/api/v1/payments/card/packages', (route) => json(route, { ...catalog, provider: 'card', label: 'Lava Top', configured: false, packages: {} }));
  await page.route('**/api/v1/payments/crypto/packages', (route) => json(route, { ...catalog, provider: 'cryptobot', label: 'CryptoBot', configured: false, packages: {} }));
  await page.route('**/api/v1/payments?limit=50', (route) => json(route, { items: [] }));
  await page.route('**/api/v1/promocodes/active', (route) => json(route, { active: false, program_active: true }));

  await page.goto('/mini-app/payments/');
  const checkout = page.getByRole('button', { name: /Оплатить 300 RUB через ЮKassa/ });
  const refresh = page.getByRole('button', { name: 'Обновить' });
  await expect(checkout).toBeEnabled();
  await expect(refresh).toBeEnabled();

  await refresh.click();
  await expect(page.getByText('Загружаем способы оплаты и историю…')).toBeVisible();
  await expect(checkout).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Обновляю…' })).toBeDisabled();
  await expect(page.getByText('Пополнений пока нет.')).toHaveCount(0);

  await expect(checkout).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Обновить' })).toBeEnabled();
  await expect(page.getByText('Пополнений пока нет.')).toBeVisible();
});
