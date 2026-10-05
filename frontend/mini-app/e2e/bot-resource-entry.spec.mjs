import { expect, test } from '@playwright/test';

const RESOURCE = '11111111-2222-4333-8444-555555555555';
const payloads = [
  `feed_${RESOURCE}_ref_777`,
  `feed_${RESOURCE}`,
  `remix_${RESOURCE}`,
];

for (const payload of payloads) {
  test(`bot resource button resolves exact resource: ${payload}`, async ({ page }) => {
    const requested = [];
    await page.addInitScript(() => {
      window.Telegram = { WebApp: {
        initData: 'query_id=bot-entry&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Viewer' }, start_param: 'ref_123' },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      } };
    });
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      const json = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (path.startsWith('/api/v1/feed/')) {
        requested.push(path);
        return json({
          id: RESOURCE, model: 'Exact model', result_url: '',
          author: { display_name: 'Exact Entry Author', telegram_id: 777 },
          prompt_hidden: true, prompt_actions_allowed: false,
        });
      }
      if (path === '/api/v1/me') return json({ id: 'viewer', telegram_id: 999, first_name: 'Viewer', balance_rox: '100' });
      if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
      if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
      return json({ items: [], has_more: false });
    });
    await page.goto(`/mini-app/?route=feed&start_payload=${payload}&startapp=${payload}`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Exact Entry Author', { exact: true })).toBeVisible();
    expect(requested).toContain('/api/v1/feed/11111111-2222-4333-8444-555555555555');
    expect(requested.every(path => path === '/api/v1/feed/11111111-2222-4333-8444-555555555555')).toBeTruthy();
    await expect(page.getByRole('button', { name: 'Открыть всю ленту' })).toBeVisible();
  });
}
