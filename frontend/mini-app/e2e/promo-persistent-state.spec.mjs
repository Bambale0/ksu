import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.__openedPaymentLinks = [];
    window.Telegram = {
      WebApp: {
        initData: 'query_id=promo-persisted&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'Promo', username: 'promo_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink(url) { window.__openedPaymentLinks.push(url); },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

test('active promo persists on payments and is attached to a new payment automatically', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);

  let checkoutBody = null;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/promocodes/active') return json({
      active: true,
      program_active: true,
      code: 'KSENIA50',
      promo_id: '11111111-1111-4111-8111-111111111111',
      partner_user_id: '22222222-2222-4222-8222-222222222222',
      activated_at: '2026-09-15T12:00:00+00:00',
      welcome_rox_granted: '25.00',
      welcome_rox_current: '25.00',
      first_line_percent: '30.00',
      topup_partner_rox: '10.00',
      topup_user_rox: '50.00',
      topup_user_min_rub: '1000.00',
      package_discount_percent: '0',
    });
    if (path === '/api/v1/payments/card/packages') return json({
      provider: 'card', label: 'Lava Top', configured: false, currencies: ['RUB'], packages: {},
    });
    if (path === '/api/v1/payments/yookassa/packages') return json({
      provider: 'yookassa',
      label: 'ЮKassa',
      configured: true,
      currencies: ['RUB'],
      packages: {
        starter: {
          credits: '1000',
          bonus_credits: '100',
          total_credits: '1100',
          prices: { RUB: '1086.96' },
        },
      },
    });
    if (path === '/api/v1/payments/crypto/packages') return json({
      provider: 'cryptobot', label: 'CryptoBot', configured: false, currencies: ['RUB'], packages: {},
    });
    if (path === '/api/v1/payments' && request.method() === 'GET') return json({ items: [] });
    if (path === '/api/v1/payments' && request.method() === 'POST') {
      checkoutBody = request.postDataJSON();
      return json({
        id: '33333333-3333-4333-8333-333333333333',
        status: 'pending',
        provider: 'yookassa',
        label: 'ЮKassa',
        package_id: 'starter',
        amount: '1086.96',
        currency: 'RUB',
        credits: '1100',
        rox: '1100',
        base_credits: '1000',
        package_bonus_credits: '100',
        promo_bonus_credits: '0',
        bonus_credits: '100',
        promo_code: 'KSENIA50',
        promo_bonus_status: 'activated',
        payment_url: 'https://pay.example.test/promo-persisted',
        created_at: '2026-09-15T12:10:00+00:00',
        updated_at: '2026-09-15T12:10:00+00:00',
      }, 201);
    }
    return json({ items: [] });
  });

  await page.goto('/mini-app/payments/');

  await expect(page.getByText('Промокод применён', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'KSENIA50' })).toBeVisible();
  await expect(page.getByText('ROX уже начислено', { exact: true })).toBeVisible();
  await expect(page.getByText(/ROX от.*000.*₽/)).toBeVisible();
  await expect(page.getByText(/Обычный бонус выбранного пакета сохраняется/)).toBeVisible();
  await expect(page.getByText('+100 ROX 🎁', { exact: true })).toBeVisible();
  await expect(page.getByText('+50 ROX по промокоду 🎟️', { exact: true })).toBeVisible();
  await expect(page.getByText('Итого 1 150 ROX', { exact: true })).toBeVisible();
  await expect(page.getByText(/Промокод KSENIA50 уже закреплён/)).toBeVisible();
  await expect(page.getByText('Есть промокод?', { exact: true })).toHaveCount(0);

  const pay = page.getByRole('button', { name: /Оплатить 1 087 RUB через ЮKassa/ });
  await expect(pay).toBeVisible();
  await pay.click();

  await expect.poll(() => checkoutBody).not.toBeNull();
  expect(checkoutBody).toMatchObject({
    provider: 'yookassa',
    package_id: 'starter',
    promo_code: 'KSENIA50',
  });
  await expect.poll(() => page.evaluate(() => window.__openedPaymentLinks.length)).toBe(1);
  await expect(page.getByText(/Промокод добавит ещё \+50 ROX/)).toBeVisible();
});


test('promo startapp link forwards its code into the redeem flow', async ({ page }) => {
  await installTelegram(page);
  let redeemBody = null;

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/promocodes/redeem' && request.method() === 'POST') {
      redeemBody = request.postDataJSON();
      return json({
        status: 'activated',
        code: 'KOR42',
        welcome_rox: '25.00',
        reward_rox: '25.00',
        first_line_percent: '30.00',
        topup_partner_rox: '10.00',
        balance_rox: '25.00',
      });
    }
    if (path === '/api/v1/promocodes/active') return json({ active: false, program_active: true });
    if (path === '/api/v1/payments' && request.method() === 'GET') return json({ items: [] });
    return json({});
  });

  await page.goto('/mini-app/?startapp=promo_KOR42');

  await expect(page).toHaveURL(/\/mini-app\/payments\/\?promo=KOR42/);
  await expect.poll(() => redeemBody).toEqual({ code: 'KOR42' });
});
