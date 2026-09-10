import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt'],
  price_rox: '15.00',
  ui_schema: {
    fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }],
    defaults: {},
  },
};

const cryptoPackages = {
  starter: { credits: '100.00', bonus_credits: '10.00', total_credits: '110.00', prices: { RUB: '100.00' } },
};

async function mockApi(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {}, openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/me/overview') return json({ notifications: { unread: 0 }, support: { statuses: {} }, social: { following: 0, followers: 0 }, partner: { available_rub: '0.00', pending_rub: '0.00' }, payments: { total: 0 } });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [] });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy?start=ref_777', first_line: 0, second_line: 0, partner_balance_rub: '0.00' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/payments/card/packages') return json({
      provider: 'kassa',
      label: 'Оплата картой',
      currencies: ['RUB'],
      packages: cryptoPackages,
    });
    if (path === '/api/v1/payments/yookassa/packages') return json({
      provider: 'yookassa',
      label: 'ЮKassa',
      configured: true,
      currencies: ['RUB'],
      packages: cryptoPackages,
    });
    if (path === '/api/v1/payments/crypto/packages') return json({
      provider: 'cryptobot',
      label: 'CryptoBot',
      configured: true,
      currencies: ['RUB'],
      packages: cryptoPackages,
    });
    if (path === '/api/v1/payments/crypto/2328/packages') return json({
      provider: '2328',
      label: '2328',
      configured: true,
      currencies: ['RUB'],
      packages: cryptoPackages,
    });
    if (path === '/api/v1/payments/crypto/checkout' && request.method() === 'POST') return json({
      id: 'crypto-payment-1',
      status: 'pending',
      provider: 'cryptobot',
      label: 'CryptoBot',
      payment_url: 'https://t.me/CryptoBot?start=invoice-test',
    }, 201);
    if (path === '/api/v1/payments/crypto/2328/checkout' && request.method() === 'POST') return json({
      id: 'crypto-payment-2',
      status: 'pending',
      provider: '2328',
      label: '2328',
      payment_url: 'https://go.2328.io/invoice-test',
    }, 201);
    return json({ items: [] });
  });
}

test('quick wallet uses backend bonus values and links to payment lifecycle', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/?route=profile');
  await expect(page.locator('.profile-screen')).toBeVisible();

  await page.locator('button.balance-button').click();
  await expect(page).toHaveURL(/\/mini-app\/payments\//);
  await expect(page.getByRole('button', { name: 'Lava Top · резерв', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'ЮKassa', exact: true })).toHaveClass(/active/);
  await expect(page.getByRole('button', { name: /100 \+ 10 бонус/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /\+50 бонус/ })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});


test('quick wallet keeps YooKassa primary and exposes Lava only as reserve', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const providerCatalogRequests = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/payments/card/packages' || path === '/api/v1/payments/crypto/packages' || path === '/api/v1/payments/crypto/2328/packages') {
      providerCatalogRequests.push(path);
    }
  });
  await mockApi(page);
  await page.goto('/mini-app/?route=profile');
  await page.locator('button.balance-button').click();
  await expect(page).toHaveURL(/\/mini-app\/payments\//);

  await expect(page.getByRole('button', { name: 'ЮKassa', exact: true })).toHaveClass(/active/);
  await expect(page.getByRole('button', { name: 'Lava Top · резерв', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'CryptoBot', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '2328', exact: true })).toHaveCount(0);
  await expect(page.getByText('ЮKassa — основной способ оплаты. Lava Top доступна как резерв, если основной способ временно не проходит.')).toHaveCount(1);
  expect(providerCatalogRequests).toEqual(['/api/v1/payments/card/packages']);
});


test('reserve Lava deep link selects card checkout without exposing crypto', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/mini-app/payments/?provider=card');

  await expect(page.getByRole('button', { name: 'Lava Top · резерв', exact: true })).toHaveClass(/active/);
  await expect(page.getByRole('button', { name: 'ЮKassa', exact: true })).not.toHaveClass(/active/);
  await expect(page.getByRole('button', { name: 'CryptoBot', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '2328', exact: true })).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: /Email для чека/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test('Lava automatically becomes active when YooKassa is unavailable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.route('**/api/v1/payments/yookassa/packages', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ provider: 'yookassa', label: 'ЮKassa', configured: false, currencies: ['RUB'], packages: {} }),
  }));
  await page.goto('/mini-app/payments/');

  await expect(page.getByRole('button', { name: 'ЮKassa', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Lava Top · резерв', exact: true })).toHaveClass(/active/);
  await expect(page.getByText('ЮKassa сейчас недоступна — включён резервный способ Lava Top.')).toBeVisible();
});
