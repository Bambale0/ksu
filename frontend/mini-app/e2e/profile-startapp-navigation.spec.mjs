import { expect, test } from '@playwright/test';

const PROFILE_PAYLOAD = 'profile_777';

async function installTelegram(page) {
  await page.addInitScript(({ payload }) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=profile-navigation&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Viewer' }, start_param: payload },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, { payload: PROFILE_PAYLOAD });
}

async function mockApi(page) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/profiles/777/feed') return json({
      author: { display_name: 'Creator 777', referral_code: '777' },
      items: [],
    });
    if (path === '/api/v1/me') return json({
      id: 'viewer', telegram_id: 999, first_name: 'Viewer', balance_rox: '100.00',
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    return json({ items: [] });
  });
}

async function openProfile(page) {
  await page.goto(`/mini-app/?startapp=${encodeURIComponent(PROFILE_PAYLOAD)}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Профиль ROXY')).toBeVisible();
  await expect(page.getByText('Creator 777')).toBeVisible();
}

test('public profile can leave a sticky Telegram start_param for ROXY and Feed', async ({ page }) => {
  await installTelegram(page);
  await mockApi(page);

  await openProfile(page);
  await page.getByRole('button', { name: 'Открыть ROXY' }).click();
  await expect(page).toHaveURL(/\/mini-app\/?\?route=home/);
  await expect(page.getByText('Что создаём?')).toBeVisible();
  await page.waitForTimeout(300);
  await expect(page.getByText('Что создаём?')).toBeVisible();

  // An explicit fresh deep link to the same profile must still work in this WebView session.
  await openProfile(page);
  await page.getByRole('button', { name: 'Открыть ленту' }).click();
  await expect(page).toHaveURL(/\/mini-app\/?\?route=feed/);
  await expect(page.getByText('Работы сообщества')).toBeVisible();
  await page.waitForTimeout(300);
  await expect(page.getByText('Работы сообщества')).toBeVisible();
});
