import { expect, test } from '@playwright/test';

async function mockPayments(page) {
  await page.addInitScript(() => {
    window.__openedPaymentLinks = [];
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink(url) { window.__openedPaymentLinks.push(url); },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  const checkoutKeys = [];
  let checkoutCount = 0;

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/payments/card/packages') return json({ provider: 'card', label: 'Lava Top', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments/yookassa/packages') return json({ provider: 'yookassa', label: 'ЮKassa', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments/crypto/packages') return json({
      provider: 'cryptobot',
      label: 'CryptoBot',
      configured: true,
      currencies: ['RUB'],
      packages: {
        starter: { credits: '300', bonus_credits: '50', total_credits: '350', prices: { RUB: '326.09' } },
      },
    });
    if (path === '/api/v1/payments/crypto/2328/packages') return json({ provider: '2328', label: '2328', configured: false, currencies: ['RUB'], packages: {} });
    if (path === '/api/v1/payments' && request.method() === 'GET') return json({ items: [] });

    if (path === '/api/v1/payments/crypto/checkout' && request.method() === 'POST') {
      checkoutCount += 1;
      checkoutKeys.push(request.headers()['idempotency-key']);
      if (checkoutCount === 1) {
        return json({ detail: 'provider response was lost' }, 502);
      }
      return json({
        id: `payment-${checkoutCount}`,
        status: 'pending',
        provider: 'cryptobot',
        label: 'CryptoBot',
        package_id: 'starter',
        amount: '326.09',
        currency: 'RUB',
        credits: '350',
        rox: '350',
        payment_url: `https://pay.example.test/invoice-${checkoutCount}`,
        created_at: '2026-09-02T12:00:00+00:00',
        updated_at: '2026-09-02T12:00:00+00:00',
      }, 201);
    }

    return json({ items: [] });
  });

  return checkoutKeys;
}

test('ambiguous checkout retry reuses the same idempotency key', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const checkoutKeys = await mockPayments(page);
  await page.goto('/mini-app/payments/?provider=cryptobot');

  const pay = page.getByRole('button', { name: /Оплатить 326\.09 RUB через CryptoBot/ });
  await expect(pay).toBeVisible();

  await pay.click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(pay).toBeEnabled();

  await pay.click();
  await expect(page.getByText(/Счёт CryptoBot создан/)).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__openedPaymentLinks.length)).toBe(1);

  expect(checkoutKeys).toHaveLength(2);
  expect(checkoutKeys[0]).toBeTruthy();
  expect(checkoutKeys[1]).toBe(checkoutKeys[0]);

  await pay.click();
  await expect.poll(() => checkoutKeys.length).toBe(3);
  expect(checkoutKeys[2]).toBeTruthy();
  expect(checkoutKeys[2]).not.toBe(checkoutKeys[1]);
});
