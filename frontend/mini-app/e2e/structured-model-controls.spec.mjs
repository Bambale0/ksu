import { expect, test } from '@playwright/test';

function makeModel(kind) {
  if (kind === 'kling') return {
    id: 'kling-3.0', title: 'Kling 3.0', family: 'kling', media_type: 'video', operation: 'text_or_image_to_video', price_rox: '15.00',
    ui_schema: {
      groups: [{ id: 'prompt', title: 'Описание' }, { id: 'output', title: 'Результат' }, { id: 'advanced', title: 'Дополнительно' }, { id: 'references', title: 'Референсы' }],
      fields: [
        { name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: false },
        { name: 'duration', label: 'Длительность', control: 'combobox', group: 'output', suggestions: [5], required: true },
        { name: 'multi_shots', label: 'Multi-shot', control: 'toggle', group: 'output', required: false },
        { name: 'multi_prompt', label: 'Кадры multi-shot', control: 'json', group: 'advanced', required: false },
        { name: 'kling_elements', label: 'Element references', control: 'json', group: 'references', required: false },
      ],
      defaults: { duration: 5, multi_shots: false },
    },
  };
  return {
    id: 'gemini-omni-video', title: 'Gemini Omni', family: 'gemini', media_type: 'video', operation: 'multimodal_video', price_rox: '14.00',
    ui_schema: {
      groups: [{ id: 'prompt', title: 'Описание' }, { id: 'references', title: 'Референсы' }, { id: 'output', title: 'Результат' }],
      fields: [
        { name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true },
        { name: 'audio_ids', label: 'Gemini Omni audio IDs', control: 'json', group: 'references', required: false },
        { name: 'video_list', label: 'Видео-референс', control: 'json', group: 'references', required: false },
        { name: 'character_ids', label: 'Character IDs', control: 'json', group: 'references', required: false },
        { name: 'duration', label: 'Длительность', control: 'combobox', group: 'output', suggestions: [4], required: true },
      ],
      defaults: { duration: 4 },
    },
  };
}

async function mock(page, kind) {
  const model = makeModel(kind);
  const family = { id: kind, family: kind, title: model.title, media_types: ['video'], variant_count: 1, price_from_rox: model.price_rox, variants: [{ id: model.id, title: model.title, version: model.title, media_type: 'video', operation: model.operation, price_rox: model.price_rox }] };
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: 'e2e', initDataUnsafe: { user: { id: 777 } }, ready() {}, expand() {}, onEvent() {}, offEvent() {}, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} }, HapticFeedback: { impactOccurred() {} } } };
  });
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/generations/models') return reply({ models: [model], families: [family] });
    if (path === '/api/v1/me') return reply({ telegram_id: 777, balance_rox: '100.00' });
    if (path === '/api/v1/generations') return reply({ items: [], has_more: false });
    if (path === '/api/v1/feed') return reply({ items: [] });
    if (path === '/api/v1/trends') return reply({ items: [] });
    if (path === '/api/v1/onboarding') return reply({ enabled: false, completed: true });
    if (path === '/api/v1/references') return reply({ items: [] });
    if (path === '/api/v1/prompt-tools') return reply({ items: [] });
    if (path === '/api/v1/generations/quote') return reply({ cost_rox: '10.00', cost_rub: '100.00', enough_balance: true });
    return reply({ items: [] });
  });
}

test('Kling multi-shot and elements use guided controls instead of visible JSON', async ({ page }) => {
  await mock(page, 'kling');
  await page.goto('/mini-app/?route=create');
  await expect(page.locator('[data-structured-kind="multi_prompt"]')).toBeVisible();
  await expect(page.locator('[data-structured-kind="kling_elements"]')).toBeVisible();
  await expect(page.getByRole('button', { name: '+ Добавить сцену' })).toBeVisible();
  await expect(page.getByRole('button', { name: '+ Добавить элемент' })).toBeVisible();
  await expect(page.locator('textarea.structured-json-source')).toHaveCount(2);
  for (const textarea of await page.locator('textarea.structured-json-source').all()) await expect(textarea).toBeHidden();
});

test('Gemini media/id arrays use guided controls instead of visible JSON', async ({ page }) => {
  await mock(page, 'gemini');
  await page.goto('/mini-app/?route=create');
  await expect(page.locator('[data-structured-kind="audio_ids"]')).toBeVisible();
  await expect(page.locator('[data-structured-kind="video_list"]')).toBeVisible();
  await expect(page.locator('[data-structured-kind="character_ids"]')).toBeVisible();
  await expect(page.locator('textarea.structured-json-source')).toHaveCount(3);
  for (const textarea of await page.locator('textarea.structured-json-source').all()) await expect(textarea).toBeHidden();
});

test('ROXY brand keeps its Home contract from Catalog', async ({ page }) => {
  await mock(page, 'kling');
  await page.goto('/mini-app/?route=catalog');
  await page.locator('.topbar .brand').click();
  await expect(page).toHaveURL(/route=home/);
  await expect(page.locator('.home-screen')).toBeVisible();
});
