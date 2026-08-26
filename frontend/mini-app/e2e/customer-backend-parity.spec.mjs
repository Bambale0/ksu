import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano_banana',
  media_type: 'image',
  operation: 'generate_or_edit',
  known_fields: ['prompt', 'aspect_ratio'],
  price_rox: '15.00',
  ui_schema: {
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'aspect_ratio', label: 'Соотношение сторон', control: 'combobox', suggestions: ['1:1', '16:9'] },
    ],
    defaults: { aspect_ratio: '1:1' },
  },
};

const generation = {
  id: '11111111-1111-4111-8111-111111111111',
  status: 'succeeded',
  model,
  prompt: 'Неоновый портрет',
  prompt_hidden: false,
  result_url: 'https://cdn.roxy.test/result.png',
  result_urls: ['https://cdn.roxy.test/result.png'],
  media: [{ id: '22222222-2222-4222-8222-222222222222', url: 'https://cdn.roxy.test/result.png', download_url: '/api/v1/media/22222222-2222-4222-8222-222222222222/download', content_type: 'image/png', size_bytes: 2048 }],
  created_at: '2026-08-26T05:00:00Z',
};

const overview = {
  account: { username: 'qa_user', first_name: 'QA', last_name: null, created_at: '2026-08-20T00:00:00Z' },
  balance: { bonus_rox: '150.00', withdrawable_rox: '100.00', rub_accounting_equivalent: '150.00' },
  generations: { total: 3, statuses: { succeeded: 2, generating: 1 } },
  payments: { total: 1, currencies: { RUB: { count: 1, successful_count: 1, successful_amount: '100.00', credited_rox: '110.00' } } },
  support: { total: 1, statuses: { open: 1 } },
  partner: { first_line: 2, second_line: 1, available_rub: '1200.00', pending_rub: '300.00', withdrawable_rox: '1200.00', withdrawals: {} },
  social: { following: 2, followers: 4 },
  notifications: { unread: 1 },
  preferences: { ui_language: 'auto', notifications_enabled: true, marketing_notifications: false, profile_discoverable: false },
};

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  await installTelegram(page);
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/me/overview') return json(overview);
    if (path === '/api/v1/me/preferences') return json(overview.preferences);
    if (path === '/api/v1/notifications') return json({ items: [{ id: '33333333-3333-4333-8333-333333333333', kind: 'generation_done', title: 'Готово', body: 'Ваша работа готова', is_read: false, created_at: '2026-08-26T05:10:00Z' }], unread_count: 1 });
    if (path === '/api/v1/notifications/read-all') return json({ updated: 1 });
    if (/^\/api\/v1\/notifications\/[^/]+\/read$/.test(path)) return json({ is_read: true });

    if (path === '/api/v1/support/tickets' && method === 'GET') return json({ items: [{ id: '44444444-4444-4444-8444-444444444444', topic: 'Оплата', status: 'open', created_at: '2026-08-26T04:00:00Z', updated_at: '2026-08-26T05:00:00Z', can_reply: true, can_close: true, can_reopen: false }] });
    if (path === '/api/v1/support/tickets' && method === 'POST') return json({ id: '44444444-4444-4444-8444-444444444444', topic: 'Оплата', status: 'open', created_at: '2026-08-26T04:00:00Z', updated_at: '2026-08-26T05:00:00Z', can_reply: true, can_close: true, can_reopen: false }, 201);
    if (/^\/api\/v1\/support\/tickets\/[^/]+$/.test(path)) return json({ id: '44444444-4444-4444-8444-444444444444', topic: 'Оплата', status: 'open', created_at: '2026-08-26T04:00:00Z', updated_at: '2026-08-26T05:00:00Z', can_reply: true, can_close: true, can_reopen: false, messages: [{ id: 'm1', body: 'Помогите', author: 'user', created_at: '2026-08-26T04:00:00Z' }] });
    if (path.startsWith('/api/v1/support/tickets/')) return json({ status: 'ok' });

    if (path === '/api/v1/promocodes/redeem') return json({ status: 'ok', reward_rox: '25.00', balance_rox: '175.00' });
    if (path === '/api/v1/referrals/stats') return json({ partner_balance_rub: '1200.00', pending: '300.00', total_earned: '5000.00', transferred_to_rox: '1000.00', pending_withdrawals: '0.00', minimum_withdrawal: '500.00', rub_per_rox: '1.00' });
    if (path === '/api/v1/referrals/withdrawals') return json({ items: [] });
    if (path === '/api/v1/referrals/wallet-transfers') return json({ items: [] });

    if (path === '/api/v1/social/subscriptions') return json({ items: [{ id: '55555555-5555-4555-8555-555555555555', display_name: 'Автор', username: 'author', referral_code: '888', profile_discoverable: true, subscribed_by_me: true, subscribed_at: '2026-08-25T00:00:00Z' }] });
    if (path === '/api/v1/social/subscriptions/feed') return json({ items: [] });

    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations') return json({ items: [generation], has_more: false, next_before: null });
    if (path === '/api/v1/generation-history/hidden') return json({ items: [], has_more: false, next_before: null });
    if (/^\/api\/v1\/generations\/[^/]+\/actions$/.test(path)) return json({ generation, actions: [{ id: 'edit', label: 'Изменить', derivative: true }, { id: 'animate', label: 'Оживить', derivative: true }] });

    if (path === '/api/v1/creator-partnership') return json({ application: null, agreement: null, grants: [], total_granted_rox: '0.00' });
    if (path === '/api/v1/presets') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });

    if (path === '/api/v1/payments/card/packages') return json({ provider: 'card', label: 'Оплата картой', currencies: ['RUB'], packages: { starter: { credits: '100.00', bonus_credits: '10.00', total_credits: '110.00', prices: { RUB: '100.00' } } } });
    if (path === '/api/v1/payments') return json({ items: [] });

    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    return json({ items: [] });
  });

  await page.route('https://cdn.roxy.test/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64') }));
}

const surfaces = [
  ['/mini-app/account/', 'QA'],
  ['/mini-app/notifications/', '1 непрочитанных'],
  ['/mini-app/support/', 'Помощь ROXY'],
  ['/mini-app/settings/', 'Аккаунт ROXY'],
  ['/mini-app/promocodes/', 'Получить ROX'],
  ['/mini-app/partner-wallet/', 'Доход и выплаты'],
  ['/mini-app/subscriptions/', 'Мои подписки'],
  ['/mini-app/history-manager/', 'Управление работами'],
  ['/mini-app/actions/', 'Действия с результатами'],
  ['/mini-app/creator-partnership/', 'Creator-партнёрство'],
  ['/mini-app/presets/', 'Мои настройки'],
  ['/mini-app/payments/', 'Пополнения ROX'],
  ['/mini-app/downloads/', 'Скачать результаты'],
];

for (const [url, title] of surfaces) {
  test(`${url} opens as a real customer surface`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page);
    await page.goto(url);
    await expect(page.locator('.standalone-screen h1')).toContainText(title);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  });
}

test('promo redemption is wired to backend and updates balance result', async ({ page }) => {
  await mockApi(page);
  await page.goto('/mini-app/promocodes/');
  await page.getByPlaceholder('ROXY2026').fill('WELCOME');
  await page.getByRole('button', { name: 'Применить промокод' }).click();
  await expect(page.getByText('+25')).toBeVisible();
  await expect(page.getByText('175')).toBeVisible();
});

test('notifications can be marked read in the customer center', async ({ page }) => {
  await mockApi(page);
  await page.goto('/mini-app/notifications/');
  await page.getByRole('button', { name: /Прочитать все/ }).click();
  await expect(page.locator('.standalone-screen h1')).toHaveText('Всё просмотрено');
});
