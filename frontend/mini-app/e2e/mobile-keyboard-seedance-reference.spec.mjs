import { expect, test } from '@playwright/test';

const referenceUrl = 'https://cdn.roxy.local/reference.png';

const seedance = {
  id: 'seedance-2.0',
  title: 'Seedance 2.0',
  family: 'seedance',
  operation: 'multimodal_video',
  media_type: 'video',
  price_rox: '11.00',
  ui_schema: {
    defaults: {
      prompt: '',
      duration: 5,
      resolution: '720p',
      aspect_ratio: '16:9',
      generate_audio: false,
      web_search: false,
      nsfw_checker: true,
    },
    groups: [
      { id: 'prompt', title: 'Описание' },
      { id: 'references', title: 'Референсы' },
      { id: 'output', title: 'Параметры' },
    ],
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', group: 'prompt', required: true },
      { name: 'first_frame_url', label: 'Референс', control: 'file', group: 'references', accept: 'image/*', max_items: 1 },
      { name: 'last_frame_url', label: 'Последний кадр', control: 'file', group: 'references', accept: 'image/*', max_items: 1 },
      { name: 'reference_image_urls', label: 'Изображения', control: 'files', group: 'references', accept: 'image/*', max_items: 8 },
      { name: 'reference_video_urls', label: 'Видео', control: 'files', group: 'references', accept: 'video/*', max_items: 3 },
      { name: 'reference_audio_urls', label: 'Аудио', control: 'files', group: 'references', accept: 'audio/*', max_items: 3 },
      { name: 'duration', label: 'Длительность', control: 'combobox', group: 'output', suggestions: [5, 10, 15] },
      { name: 'resolution', label: 'Качество', control: 'combobox', group: 'output', suggestions: ['480p', '720p'] },
      { name: 'aspect_ratio', label: 'Формат', control: 'combobox', group: 'output', suggestions: ['16:9', '9:16'] },
    ],
    scenario: {
      default: 'text',
      items: [
        {
          id: 'text', title: 'Текст', visible_fields: [],
          clear_fields: ['first_frame_url', 'last_frame_url', 'reference_image_urls', 'reference_video_urls', 'reference_audio_urls'],
        },
        {
          id: 'first_frame', title: 'Референс', visible_fields: ['first_frame_url'],
          clear_fields: ['last_frame_url', 'reference_image_urls', 'reference_video_urls', 'reference_audio_urls'],
          required_fields: ['first_frame_url'],
        },
        {
          id: 'first_last', title: 'Первый + последний', visible_fields: ['first_frame_url', 'last_frame_url'],
          clear_fields: ['reference_image_urls', 'reference_video_urls', 'reference_audio_urls'],
          required_fields: ['first_frame_url', 'last_frame_url'],
        },
        {
          id: 'references', title: 'Мультиреференсы', visible_fields: ['reference_image_urls', 'reference_video_urls', 'reference_audio_urls'],
          clear_fields: ['first_frame_url', 'last_frame_url'],
          required_any: ['reference_image_urls', 'reference_video_urls', 'reference_audio_urls'],
        },
      ],
    },
  },
};

const family = {
  id: 'seedance',
  title: 'Seedance',
  media_types: ['video'],
  variant_count: 1,
  price_from_rox: '11.00',
  variants: [{ id: seedance.id, title: seedance.title, version: '2.0', media_type: 'video', operation: seedance.operation, price_rox: '11.00' }],
};

function money(value) {
  return `${Number(value).toFixed(2)}`;
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockRoxy(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    if (path === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', balance_rox: '500.00' });
    if (path === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json(route, { models: [seedance], families: [family], max_generation_quantity: 6 });
    if (path === '/api/v1/generations/quote') {
      const payload = route.request().postDataJSON();
      const quantity = Number(payload.quantity || 1);
      return json(route, {
        quantity,
        unit_price_rox: '55.00',
        cost_rox: money(55 * quantity),
        cost_rub: money(55 * quantity),
      });
    }
    if (path === '/api/v1/uploads/kie') return json(route, { url: referenceUrl, name: 'reference.png', mime_type: 'image/png', size: 4, replayed: false }, 201);
    if (path === '/api/v1/references') return json(route, { items: [] });
    if (path === '/api/v1/generations' && method === 'POST') {
      const payload = route.request().postDataJSON();
      const quantity = Number(payload.quantity || 1);
      const ids = Array.from({ length: quantity }, (_, index) => `gen_new_${index + 1}`);
      return json(route, { id: ids[0], ids, quantity, status: 'queued', cost_rox: money(55 * quantity) }, 202);
    }
    if (path.startsWith('/api/v1/generations/gen_new_')) return json(route, { id: path.split('/').pop(), status: 'queued', model: seedance, created_at: new Date().toISOString(), result_url: null, result_urls: [] });
    if (path === '/api/v1/generations') return json(route, { items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json(route, { items: [] });
    if (path === '/api/v1/trends') return json(route, { items: [] });
    if (path === '/api/v1/prompt-tools') return json(route, { admin_free: false, items: [] });
    return json(route, {});
  });
}

test('prompt focus hides fixed bottom navigation on a touch-first mobile context', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();
  try {
    await mockRoxy(page);
    await page.goto('/mini-app/?route=create');

    const prompt = page.getByRole('textbox', { name: /Описание/ });
    const nav = page.getByRole('navigation', { name: 'Основная навигация' });
    await expect(nav).toBeVisible();
    await prompt.focus();
    await expect(nav).toBeHidden();
    await prompt.fill('Портрет, плавное движение камеры');
    await prompt.blur();
    await expect(nav).toBeVisible();
  } finally {
    await context.close();
  }
});

test('Seedance reference upload survives retry and is sent as first_frame_url', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=create');

  await page.getByRole('button', { name: 'Референс', exact: true }).click();
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) });
  await expect(page.getByText('1 загружено')).toBeVisible();
  await expect.poll(() => fileInput.evaluate((input) => input.value)).toBe('');

  // Selecting the exact same filename again must still be accepted on iOS-like flows.
  await fileInput.setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) });
  await expect(page.getByText('1 загружено')).toBeVisible();
  await page.getByRole('textbox', { name: /Описание/ }).fill('Персонаж поворачивает голову и улыбается');
  await expect(page.getByText('55 ROX', { exact: true })).toBeVisible();

  const submitted = page.waitForRequest((request) => request.url().endsWith('/api/v1/generations') && request.method() === 'POST');
  await page.getByRole('button', { name: /Создать · 55 ROX/ }).click();
  const request = await submitted;
  const payload = request.postDataJSON();
  expect(payload.model_id).toBe('seedance-2.0');
  expect(payload.quantity).toBe(1);
  expect(payload.parameters.first_frame_url).toBe(referenceUrl);
  expect(payload.parameters.reference_image_urls).toBeUndefined();
});

test('Seedance multimodal reference mode sends reference_image_urls without frame fields', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=create');

  await page.getByRole('button', { name: 'Мультиреференсы', exact: true }).click();
  const imageInput = page.locator('input[type="file"]').first();
  await imageInput.setInputFiles({ name: 'reference.png', mimeType: 'image/png', buffer: Buffer.from([1, 2, 3, 4]) });
  await expect(page.getByText('1 загружено')).toBeVisible();
  await page.getByRole('textbox', { name: /Описание/ }).fill('Собери видео по визуальному референсу, без первого кадра');
  await expect(page.getByText('55 ROX', { exact: true })).toBeVisible();

  const submitted = page.waitForRequest((request) => request.url().endsWith('/api/v1/generations') && request.method() === 'POST');
  await page.getByRole('button', { name: /Создать · 55 ROX/ }).click();
  const request = await submitted;
  const payload = request.postDataJSON();
  expect(payload.model_id).toBe('seedance-2.0');
  expect(payload.quantity).toBe(1);
  expect(payload.parameters.reference_image_urls).toEqual([referenceUrl]);
  expect(payload.parameters.first_frame_url).toBeUndefined();
  expect(payload.parameters.last_frame_url).toBeUndefined();
  expect(payload.parameters.reference_video_urls).toBeUndefined();
  expect(payload.parameters.reference_audio_urls).toBeUndefined();
});

test('Mini App quantity picker sends six launches and total quote', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockRoxy(page);
  await page.goto('/mini-app/?route=create');

  await page.getByRole('textbox', { name: /Описание/ }).fill('Сделай шесть разных вариантов динамичного видео');
  await page.getByRole('button', { name: '6', exact: true }).click();
  await expect(page.getByText('Стоимость за 6')).toBeVisible();
  await expect(page.getByText('330 ROX', { exact: true })).toBeVisible();

  const submitted = page.waitForRequest((request) => request.url().endsWith('/api/v1/generations') && request.method() === 'POST');
  await page.getByRole('button', { name: /Создать · 330 ROX/ }).click();
  const request = await submitted;
  const payload = request.postDataJSON();
  expect(payload.model_id).toBe('seedance-2.0');
  expect(payload.quantity).toBe(6);
  expect(payload.prompt).toBe('Сделай шесть разных вариантов динамичного видео');
});
