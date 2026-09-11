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

const packages = {
  starter: {
    credits: '100',
    bonus_credits: '0',
    total_credits: '100',
    prices: { RUB: '100' },
  },
};

async function mockRoxy(page, { initialLanguage = 'ru', telegramLanguage = 'ru' } = {}) {
  const preferenceWrites = [];
  let preferences = {
    ui_language: initialLanguage,
    notifications_enabled: true,
    marketing_notifications: false,
    profile_discoverable: false,
  };

  await page.addInitScript((languageCode) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: {
          user: {
            id: 777,
            first_name: 'QA',
            username: 'qa_user',
            language_code: languageCode,
          },
        },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {}, openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, telegramLanguage);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me/preferences' && method === 'GET') return json(preferences);
    if (path === '/api/v1/me/preferences' && method === 'PUT') {
      preferences = request.postDataJSON();
      preferenceWrites.push(preferences);
      return json(preferences);
    }
    if (path === '/api/v1/me') return json({
      id: 'user_1',
      telegram_id: 777,
      first_name: 'QA',
      username: 'qa_user',
      language_code: telegramLanguage,
      balance_rox: '150.00',
      preferences,
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (/^\/api\/v1\/profiles\/[^/]+\/feed$/.test(path)) return json({ items: [] });
    if (path === '/api/v1/referrals/stats') return json({
      referral_link: 'https://t.me/roxy?start=ref_777',
      first_line: 0,
      second_line: 0,
      partner_balance_rub: '0.00',
    });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/payments/card/packages') return json({
      provider: 'card',
      label: 'Оплата картой',
      configured: true,
      currencies: ['RUB'],
      packages,
    });
    if (path === '/api/v1/payments/yookassa/packages') return json({
      provider: 'yookassa',
      label: 'ЮKassa',
      configured: true,
      currencies: ['RUB'],
      packages,
    });
    if (path === '/api/v1/payments/crypto/packages') return json({
      provider: 'cryptobot',
      label: 'CryptoBot',
      configured: true,
      currencies: ['RUB'],
      packages,
    });
    if (path === '/api/v1/payments' && method === 'GET') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    return json({ items: [] });
  });

  return preferenceWrites;
}

test('topbar RU / EN switch changes the customer UI and persists the preference', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await mockRoxy(page, { initialLanguage: 'ru' });

  await page.goto('/mini-app/?route=home');

  const switcher = page.getByRole('group', { name: 'Язык интерфейса' });
  await expect(switcher.getByRole('button', { name: 'RU' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Что создаём?', { exact: true })).toBeVisible();

  await switcher.getByRole('button', { name: 'EN' }).click();

  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.balance-button span')).toHaveText('Balance');
  await expect(page.getByText('What are we creating?', { exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toContainText('Studio');
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toEqual({
    ui_language: 'en',
    notifications_enabled: true,
    marketing_notifications: false,
    profile_discoverable: false,
  });

  await page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'RU' }).click();

  await expect(page.getByRole('group', { name: 'Язык интерфейса' }).getByRole('button', { name: 'RU' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Что создаём?', { exact: true })).toBeVisible();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].ui_language).toBe('ru');
});

test('saved English applies on a direct standalone payment route', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page, { initialLanguage: 'en' });

  await page.goto('/mini-app/payments/');

  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('heading', { name: 'ROX top-ups' })).toBeVisible();
  await expect(page.getByText('Payment method', { exact: true })).toBeVisible();
  await expect(page.locator('.balance-button span')).toHaveText('Balance');
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test('legacy auto follows Telegram language without changing the account preference', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  const writes = await mockRoxy(page, { initialLanguage: 'auto', telegramLanguage: 'en' });

  await page.goto('/mini-app/?route=home');

  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('What are we creating?', { exact: true })).toBeVisible();
  expect(writes).toHaveLength(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});


test('settings cannot overwrite a language chosen from the topbar', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await mockRoxy(page, { initialLanguage: 'en' });

  await page.goto('/mini-app/settings/');
  await expect(page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'EN' }))
    .toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox')).toHaveCount(0);

  await page.getByRole('group', { name: 'Interface language' }).getByRole('button', { name: 'RU' }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].ui_language).toBe('ru');

  const marketing = page.locator('.toggle-row').filter({ hasText: 'Новости и предложения' });
  await marketing.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();

  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toMatchObject({
    ui_language: 'ru',
    notifications_enabled: true,
    marketing_notifications: true,
    profile_discoverable: false,
  });
});
