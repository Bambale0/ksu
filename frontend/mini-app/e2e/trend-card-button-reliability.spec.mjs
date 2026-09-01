import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: { groups: [], fields: [], defaults: {} },
};

const trend = {
  id: 'trend_click_guard',
  title: 'Тренд для проверки кнопок',
  description: 'Не даём карточке съедать вложенные действия',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

async function mockApp(page) {
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

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', is_admin: false });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/referrals/stats') return json({});
    if (path === '/api/v1/referrals/rewards' || path === '/api/v1/referrals/invitations') return json({ items: [] });
    return json({ items: [] });
  });
}

test('nested buttons inside a trend-launch card keep their own click handler', async ({ page }) => {
  await mockApp(page);
  await page.goto('/mini-app/?route=home');
  await expect(page.locator('#roxy-home-live-trends')).toBeVisible();

  await page.evaluate(() => {
    window.__nestedTrendActionClicks = 0;
    const card = document.createElement('div');
    card.id = 'trend-click-fixture';
    card.dataset.trendLaunch = 'true';
    card.dataset.trendId = 'trend_click_guard';
    card.setAttribute('role', 'button');
    card.tabIndex = 0;

    const nested = document.createElement('button');
    nested.id = 'nested-trend-action';
    nested.type = 'button';
    nested.textContent = 'Вложенное действие';
    nested.addEventListener('click', () => {
      window.__nestedTrendActionClicks += 1;
    });
    card.append(nested);
    document.body.append(card);
  });

  const before = page.url();
  await page.getByRole('button', { name: 'Вложенное действие' }).click();

  await expect.poll(() => page.evaluate(() => window.__nestedTrendActionClicks)).toBe(1);
  expect(page.url()).toBe(before);
});
