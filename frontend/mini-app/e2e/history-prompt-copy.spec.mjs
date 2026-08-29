import { expect, test } from '@playwright/test';

const prompt = 'Сохрани этот промпт после неудачной генерации';
const failedId = '11111111-2222-4333-8444-555555555555';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.__copiedPrompt = '';
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        async writeText(value) { window.__copiedPrompt = String(value); },
      },
    });
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'History' } },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

function model() {
  return {
    id: 'nano-banana-2',
    title: 'Nano Banana 2',
    family: 'nano-banana',
    operation: 'auto',
    media_type: 'image',
    price_rox: '25.00',
    ui_schema: { defaults: { prompt: '' }, fields: [] },
  };
}

function failedGeneration({ hidden = false } = {}) {
  return {
    id: failedId,
    status: 'failed',
    prompt,
    prompt_hidden: hidden,
    model: model(),
    error: 'provider failed',
    created_at: '2026-08-29T12:18:00Z',
  };
}

async function mockApp(page, generation) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'history-user', telegram_id: 999, first_name: 'History', balance_rox: '340.00', created_at: '2026-08-29T00:00:00Z', is_active: true });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model()], families: [] });
    if (path === '/api/v1/feed' || path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/generations') {
      const limit = url.searchParams.get('limit');
      if (limit === '24') return json({ items: [generation], has_more: false, next_before: null });
      return json({ items: [], has_more: false, next_before: null });
    }
    if (path === `/api/v1/generations/${failedId}`) return json(generation);
    return json({ items: [] });
  });
}

test('history prompt copies on tap without opening the generation', async ({ page }) => {
  await installTelegram(page);
  await mockApp(page, failedGeneration());
  await page.goto('/mini-app/?route=history', { waitUntil: 'domcontentloaded' });

  const copyPrompt = page.getByRole('button', { name: 'Скопировать промпт', exact: true });
  await expect(copyPrompt).toContainText(prompt);
  await copyPrompt.click();

  await expect.poll(() => page.evaluate(() => window.__copiedPrompt)).toBe(prompt);
  await expect(page.getByRole('status')).toContainText('Промпт скопирован');
  await expect(page.locator('.preview-card')).toHaveCount(0);
});

test('hidden history prompt is never exposed as a copy action', async ({ page }) => {
  await installTelegram(page);
  await mockApp(page, failedGeneration({ hidden: true }));
  await page.goto('/mini-app/?route=history', { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('button', { name: 'Скопировать промпт', exact: true })).toHaveCount(0);
  await expect(page.getByText(prompt)).toHaveCount(0);
});
