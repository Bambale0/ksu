import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&auth_date=1787760000&hash=test',
        initDataUnsafe: {
          user: { id: 999, first_name: 'iPhone Diagnostic' },
          start_param: '',
        },
        ready() {},
        expand() {},
        close() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        setBottomBarColor() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  const reports = [];

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/client-logs') {
      reports.push({
        body: request.postDataJSON(),
        headers: request.headers(),
      });
      return json({ accepted: true });
    }
    if (path === '/api/v1/me') return json({
      id: 'diagnostic-user',
      telegram_id: 999,
      first_name: 'iPhone Diagnostic',
      balance_rox: '100.00',
      is_admin: false,
      billing_mode: 'wallet',
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ promos: [], sections: [] });
    if (path === '/api/v1/notifications') return json({ items: [], unread_count: 0 });
    return json({ items: [] });
  });

  return reports;
}

test('post-bootstrap client rejection is reported without launch URL secrets', async ({ page }) => {
  await installTelegram(page);
  const reports = await mockApi(page);

  await page.goto('/mini-app/?route=home&startapp=ref_777');
  await expect(page.locator('.home-screen')).toBeVisible();

  await page.evaluate(() => {
    window.setTimeout(() => {
      void Promise.reject(new Error('ios-webkit-diagnostic-probe'));
    }, 0);
  });

  await expect.poll(() => reports.length).toBe(1);
  const report = reports[0];

  expect(report.body.kind).toBe('unhandled_rejection');
  expect(report.body.message).toContain('ios-webkit-diagnostic-probe');
  expect(report.body.pathname).toBe('/mini-app/');
  expect(JSON.stringify(report.body)).not.toContain('startapp=ref_777');
  expect(JSON.stringify(report.body)).not.toContain('query_id=e2e');
  expect(report.headers['x-telegram-init-data']).toContain('query_id=e2e');
});
