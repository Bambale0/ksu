import { expect, test } from '@playwright/test';

const trend = {
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Тестовый тренд',
  description: 'Проверка первого запуска',
  media_type: 'image',
  model: { id: 'nano-banana-2', title: 'Nano Banana 2', family: 'nanobanana' },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

const retainedStartParam = 'feed_22222222-2222-4222-8222-222222222222_ref_777';

async function mockApi(page) {
  await page.addInitScript((startParam) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: {
          user: { id: 777, first_name: 'QA', username: 'qa_user' },
          start_param: startParam,
        },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, retainedStartParam);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === `/api/v1/trends/${trend.id}` && method === 'GET') return json(trend);
    if (path === `/api/v1/trends/${trend.id}/run` && method === 'POST') {
      return json({ detail: { code: 'onboarding_required', version: '1' } }, 428);
    }
    if (path === '/api/v1/onboarding') {
      return json({ enabled: true, completed: false, title: 'ROXY', body: 'Добро пожаловать' });
    }
    if (path === '/api/v1/onboarding/complete') return json({ enabled: false, completed: true });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', balance_rox: '100.00' });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    return json({ items: [] });
  });
}

test('428 onboarding_required bypasses retained deep links and opens friendly onboarding', async ({ page }) => {
  await mockApi(page);
  await page.goto(`/mini-app/trend/?id=${trend.id}`);

  const generate = page.getByRole('button', { name: /Сгенерировать/ });
  await expect(generate).toBeEnabled();
  await generate.click();

  await expect(page).toHaveURL(/\/mini-app\/\?onboarding=1$/);
  await expect(page.locator('.onboarding-card')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('onboarding_required');
});
