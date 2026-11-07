import { expect, test } from '@playwright/test';

function model(keyframes = false) {
  return { id: keyframes ? 'kling-4.0-keyframe' : 'kling-4.0', title: 'Kling 4.0', family: 'kling', media_type: 'video', operation: 'multimodal_video', price_rox: '30', ui_schema: {
    defaults: { duration: 5, resolution: '720p', aspect_ratio: '16:9' },
    groups: [{ id: 'prompt', title: 'Описание' }, { id: 'output', title: 'Результат' }, { id: 'references', title: 'Референсы' }],
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true, group: 'prompt', max_length: 8000 },
      { name: 'duration', label: 'Длительность', control: 'combobox', suggestions: [3, 5, 30], group: 'output' },
      { name: 'resolution', label: 'Разрешение', control: 'combobox', suggestions: ['720p', '1080p'], group: 'output' },
      ...(keyframes ? [
        { name: 'first_frame_url', label: 'Первый кадр', control: 'file', accept: 'image/png', group: 'references' },
        { name: 'keyframe_urls', label: 'Промежуточные кадры', control: 'files', accept: 'image/png', max_items: 8, group: 'references' },
        { name: 'last_frame_url', label: 'Последний кадр', control: 'file', accept: 'image/png', group: 'references' },
      ] : [
        { name: 'elements', label: 'Персонажи и объекты', control: 'json', editor: 'kling_elements', max_items: 7, group: 'references' },
        { name: 'voices', label: 'Голоса', control: 'json', editor: 'kling_voices', max_items: 3, group: 'references' },
      ]),
    ],
  } };
}

async function setup(page, keyframes = false, uploadHandler, reuse) {
  const chosen = model(keyframes);
  const submitted = [];
  let uploadIndex = 0;
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: 'e2e', initDataUnsafe: { user: { id: 777 } }, ready() {}, expand() {}, onEvent() {}, offEvent() {}, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} }, HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} } } };
  });
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/generations/models') return reply({ models: [chosen], families: [] });
    if (reuse && path === '/api/v1/generations/source/recreate') return reply({ model_id: chosen.id, prompt: '@Hero greets @Narrator', parameters: reuse });
    if (reuse && path === '/api/v1/generations/source') return reply({ id: 'source', status: 'succeeded', model: chosen, result_url: 'https://cdn.example/result.mp4' });
    if (reuse && path === '/api/v1/generations' && request.method() === 'GET') return reply({ items: [{ id: 'source', status: 'succeeded', model: chosen, result_url: 'https://cdn.example/result.mp4' }], has_more: false });
    if (path === '/api/v1/me') return reply({ id: 'user-1', telegram_id: 777, balance_rox: '10000' });
    if (path === '/api/v1/onboarding') return reply({ enabled: false, completed: true });
    if (path.includes('/upload')) {
      uploadIndex += 1;
      if (uploadHandler) await uploadHandler(uploadIndex);
      return reply({ url: `https://cdn.example/upload-${uploadIndex}.png`, reference: { id: `ref-${uploadIndex}` } });
    }
    if (path === '/api/v1/generations/quote') return reply({ model_id: chosen.id, cost_rox: '150', effective_cost_rox: '150' });
    if (path === '/api/v1/generations' && request.method() === 'POST') {
      submitted.push(request.postDataJSON());
      return reply({ id: 'kling4-result', status: 'queued', model: chosen });
    }
    if (path.startsWith('/api/v1/generations/kling4-result')) return reply({ id: 'kling4-result', status: 'succeeded', model: chosen, result_url: 'https://cdn.example/result.mp4' });
    return reply({ items: [], has_more: false });
  });
  await page.goto('/mini-app/?route=create');
  await expect(page.locator('.create-summary')).toBeVisible();
  return submitted;
}

const image = name => ({ name, mimeType: 'image/png', buffer: Buffer.from('synthetic image') });
const audio = { name: 'voice.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic audio') };

test('Kling 4 named subjects and voices submit arrays through native upload controls', async ({ page }) => {
  const submitted = await setup(page);
  await page.locator('textarea').first().fill('@Hero speaks using @Narrator');
  await page.getByRole('button', { name: 'Добавить персонажа', exact: true }).click();
  await page.getByLabel('Имя персонажа 1', { exact: true }).fill('Hero');
  await page.getByLabel('Изображения персонажа 1', { exact: true }).setInputFiles([image('front.png'), image('side.png')]);
  await expect(page.getByRole('button', { name: 'Убрать Изображения персонажа 1 2', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Добавить голос', exact: true }).click();
  await page.getByLabel('Имя голоса 1', { exact: true }).fill('Narrator');
  await page.getByLabel('Аудио голоса 1', { exact: true }).setInputFiles(audio);
  await expect(page.getByRole('button', { name: 'Убрать Аудио голоса 1 1', exact: true })).toBeVisible();
  const create = page.locator('.create-summary button.primary');
  await expect(create).toBeEnabled();
  await create.click();
  await expect.poll(() => submitted.length).toBe(1);
  expect(submitted[0].parameters.elements).toEqual([{ name: 'Hero', image_urls: ['https://cdn.example/upload-1.png', 'https://cdn.example/upload-2.png'], tag: 'character' }]);
  expect(submitted[0].parameters.voices).toEqual([{ name: 'Narrator', audio_url: 'https://cdn.example/upload-3.png' }]);
  expect(submitted[0].model_id).toBe('kling-4.0');
});

test('Kling 4 blocks submit during a pending nested upload and allows retry after rejection', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await setup(page, false, async () => gate);
  await page.locator('textarea').first().fill('A sunset');
  await page.getByRole('button', { name: 'Добавить голос', exact: true }).click();
  await page.getByLabel('Имя голоса 1', { exact: true }).fill('Narrator');
  const editor = page.locator('[data-kling-editor="kling_voices"]');
  await editor.getByLabel('Аудио голоса 1', { exact: true }).setInputFiles(image('bad.png'));
  await expect(editor.getByRole('alert')).toBeVisible();
  try {
    await editor.getByLabel('Аудио голоса 1', { exact: true }).setInputFiles(audio);
    await expect(editor).toHaveAttribute('aria-busy', 'true');
    await expect(page.locator('.create-summary button.primary')).toBeDisabled();
  } finally { release(); }
  await expect(editor).toHaveAttribute('aria-busy', 'false');
  await expect(editor.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('.create-summary button.primary')).toBeEnabled();
});

test('Kling 4 keyframes preserve first middle last order in the create request', async ({ page }) => {
  const submitted = await setup(page, true);
  await page.locator('textarea').first().fill('@first_frame to @keyframe_1 to @last_frame');
  for (const [label, files] of [['Первый кадр', [image('first.png')]], ['Промежуточные кадры', [image('middle.png')]], ['Последний кадр', [image('last.png')]]]) {
    const field = page.locator('.field').filter({ has: page.locator('.label', { hasText: label }) }).first();
    await field.locator('input[type=file]').setInputFiles(files);
    await expect(field.locator('.upload-list button')).toHaveCount(1);
  }
  await expect(page.locator('.create-summary button.primary')).toBeEnabled();
  await page.locator('.create-summary button.primary').click();
  await expect.poll(() => submitted.length).toBe(1);
  expect(submitted[0].parameters).toMatchObject({ first_frame_url: 'https://cdn.example/upload-1.png', keyframe_urls: ['https://cdn.example/upload-2.png'], last_frame_url: 'https://cdn.example/upload-3.png' });
});

test('Kling 4 reuses saved subject and voice arrays without editing them', async ({ page }) => {
  const references = { elements: [{ name: 'Hero', image_urls: ['https://cdn.example/a.png', 'https://cdn.example/b.png'], tag: 'character' }], voices: [{ name: 'Narrator', audio_url: 'https://cdn.example/voice.wav' }], duration: 5, resolution: '720p' };
  const submitted = await setup(page, false, undefined, references);
  await page.goto('/mini-app/?route=history');
  await page.locator('.history-card').first().click();
  await page.getByRole('button', { name: 'Использовать настройки', exact: true }).click();
  await expect(page.getByLabel('Имя персонажа 1', { exact: true })).toHaveValue('Hero');
  await expect(page.getByLabel('Имя голоса 1', { exact: true })).toHaveValue('Narrator');
  const create = page.locator('.create-summary button.primary');
  await expect(create).toBeEnabled();
  await create.click();
  await expect.poll(() => submitted.length).toBe(1);
  expect(submitted[0].parameters.elements).toEqual(references.elements);
  expect(submitted[0].parameters.voices).toEqual(references.voices);
});
