import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.confirm = () => true;
    window.Telegram = {
      WebApp: {
        initData: 'query_id=partner-rox-e2e&hash=test',
        initDataUnsafe: { user: { id: 88002, first_name: 'Sponsor', username: 'sponsor_e2e' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {}, openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  const calls = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'sender-id', telegram_id: 88002, first_name: 'Sponsor', username: 'sponsor_e2e', balance_rox: '7000.00', is_admin: false });
    if (path === '/api/v1/me/overview') return json({});
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/referrals/stats') return json({ first_line: 1, second_line: 0, partner_balance_rub: '0.00', referral_link: 'https://t.me/example?start=ref_88002' });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/referrals/invitations') return json({ items: [{ user_id: '11111111-1111-4111-8111-111111111111', username: 'creator', first_name: 'Creator', line: 1, joined_at: '2026-09-03T00:00:00Z' }] });
    if (path === '/api/v1/referrals/rox-transfers' && method === 'POST') {
      calls.push(request.postDataJSON());
      await new Promise((resolve) => setTimeout(resolve, 80));
      return json({ id: '22222222-2222-4222-8222-222222222222', recipient_user_id: '11111111-1111-4111-8111-111111111111', amount_rox: '5500', balance_rox: '1500.00' }, 201);
    }
    return json({ items: [] });
  });
  return calls;
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
});

test('partner transfers ROX to a direct referral and rapid double click submits once', async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto('/mini-app/?route=partners');

  const panel = page.locator('[data-partner-rox-transfer]');
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Creator', { exact: false })).toBeVisible();
  await panel.getByLabel('Сколько ROX').fill('5500');

  const submit = panel.getByRole('button', { name: 'Перевести 5 500 ROX' });
  await expect(submit).toBeEnabled();
  await submit.evaluate((button) => { button.click(); button.click(); });

  await expect(panel.getByRole('status')).toContainText('Переведено');
  expect(calls).toHaveLength(1);
  expect(calls[0]).toMatchObject({ recipient_user_id: '11111111-1111-4111-8111-111111111111', amount_rox: 5500 });
  expect(typeof calls[0].idempotency_key).toBe('string');
  expect(calls[0].idempotency_key.length).toBeGreaterThanOrEqual(8);
  await expect(panel.getByText('1 500 ROX', { exact: false })).toBeVisible();
});
