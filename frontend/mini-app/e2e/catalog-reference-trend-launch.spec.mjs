import { expect, test } from '@playwright/test';

const trendId = 'trend_reference_required';
const trend = {
  id: trendId,
  title: 'Портрет с референсом',
  description: 'Нужна фотография пользователя',
  media_type: 'image',
  model: { id: 'nano-banana-2', title: 'Nano Banana 2', family: 'nano-banana' },
  cost_rox: '25.00',
  reference_requirements: { kind: 'image', min: 1, max: 2 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

async function mockApp(page) {
  let runCalls = 0;

  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=reference-trend&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_777', telegram_id: 777, first_name: 'QA', balance_rox: '100.00', is_active: true });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === `/api/v1/trends/${trendId}` && request.method() === 'GET') return json(trend);
    if (path === `/api/v1/trends/${trendId}/run`) {
      runCalls += 1;
      return json({ id: 'should-not-run-directly' });
    }
    return json({ items: [] });
  });

  return { runCalls: () => runCalls };
}

test('reference-required catalog trend opens the reference composer instead of dead-ending', async ({ page }) => {
  const audit = await mockApp(page);
  await page.goto('/mini-app/?route=catalog', { waitUntil: 'domcontentloaded' });

  const card = page.locator('.model-card').filter({ hasText: trend.title }).first();
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute('data-trend-id', trendId);

  await card.click();

  await expect(page).toHaveURL(new RegExp(`/mini-app/trend/\\?id=${trendId}$`));
  await expect(page.getByText(trend.title, { exact: true })).toBeVisible();
  await expect(page.getByText('Добавить референсы', { exact: true })).toBeVisible();
  expect(audit.runCalls()).toBe(0);
});
