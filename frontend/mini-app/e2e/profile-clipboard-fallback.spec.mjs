import { expect, test } from '@playwright/test';

const profileLink = 'https://t.me/roxy_bot/app?startapp=profile_88001';

async function installRejectingClipboard(page) {
  await page.addInitScript(() => {
    window.__legacyCopied = '';
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        async writeText() { throw new Error('NotAllowedError: WebView clipboard rejected'); },
      },
    });
    Object.defineProperty(Document.prototype, 'execCommand', {
      configurable: true,
      value(command) {
        if (command !== 'copy') return false;
        const textarea = document.querySelector('textarea');
        window.__legacyCopied = textarea?.value || '';
        return true;
      },
    });
    window.Telegram = {
      WebApp: {
        initData: 'query_id=profile-copy&hash=test',
        initDataUnsafe: { user: { id: 88001, first_name: 'Creator', username: 'creator_88001' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockApi(page) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me') return json({
      id: 'profile-copy-user',
      telegram_id: 88001,
      first_name: 'Creator',
      username: 'creator_88001',
      balance_rox: '100.00',
      profile_link: profileLink,
      created_at: '2026-09-02T00:00:00Z',
      is_active: true,
    });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed' || path === '/api/v1/trends') return json({ items: [] });
    if (/^\/api\/v1\/profiles\/88001\/feed$/.test(path)) return json({ items: [] });
    if (request.method() === 'OPTIONS') return route.continue();
    return json({ items: [] });
  });
}

test('profile share falls back when Telegram WebView exposes Clipboard API but rejects writeText', async ({ page }) => {
  await installRejectingClipboard(page);
  await mockApi(page);
  await page.goto('/mini-app/?route=profile', { waitUntil: 'domcontentloaded' });

  const share = page.getByRole('button', { name: 'Поделиться профилем' });
  await expect(share).toBeVisible();
  await share.click();

  await expect.poll(() => page.evaluate(() => window.__legacyCopied)).toBe(profileLink);
  await expect(page.getByRole('status').filter({ hasText: 'Ссылка скопирована' })).toBeVisible();
});
