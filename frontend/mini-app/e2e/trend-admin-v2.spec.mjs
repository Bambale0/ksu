import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const stepPreviewPng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64');
const stepVideoFixtures = {
  chromium: { extension: 'webm', contentType: 'video/webm', body: readFileSync(new URL('../../../tests/fixtures/trend-preview-portrait.webm', import.meta.url)) },
  webkit: { extension: 'mp4', contentType: 'video/mp4', body: readFileSync(new URL('../../../tests/fixtures/trend-preview-portrait.mp4', import.meta.url)) },
};

function fulfillStepVideo(route, { body, contentType }) {
  const headers = { 'accept-ranges': 'bytes' };
  const range = route.request().headers().range;
  if (!range) return route.fulfill({ status: 200, contentType, headers, body });
  const match = /^bytes=(\d*)-(\d*)$/.exec(range);
  const from = match?.[1] ? Number(match[1]) : Math.max(0, body.length - Number(match?.[2]));
  const to = match?.[1] && match[2] ? Math.min(Number(match[2]), body.length - 1) : body.length - 1;
  if (!match || (!match[1] && !match[2]) || !Number.isSafeInteger(from) || !Number.isSafeInteger(to)
    || from >= body.length || to < from) {
    return route.fulfill({ status: 416, headers: { ...headers, 'content-range': 'bytes */' + body.length }, body: '' });
  }
  return route.fulfill({
    status: 206, contentType,
    headers: { ...headers, 'content-range': 'bytes ' + from + '-' + to + '/' + body.length },
    body: body.subarray(from, to + 1),
  });
}

const photoModel = {
  id: 'photo-catalog-model',
  title: 'Фото из каталога',
  family: 'photo',
  media_type: 'image',
  operation: 'text_to_image',
  known_fields: ['prompt', 'resolution', 'aspect_ratio'],
  required_fields: ['prompt'],
  price_rox: '15.00',
  ui_schema: {
    defaults: { resolution: '1024' },
    fields: [
      { name: 'resolution', label: 'Разрешение', control: 'combobox', suggestions: ['1024', '2048'] },
      { name: 'aspect_ratio', label: 'Соотношение сторон', control: 'combobox', suggestions: ['1:1', '9:16'] },
    ],
  },
};

const videoModel = {
  id: 'video-i2v-model',
  title: 'Видео из изображения',
  family: 'video',
  media_type: 'video',
  operation: 'image_to_video',
  known_fields: ['prompt', 'first_frame_url', 'duration', 'resolution'],
  required_fields: ['prompt', 'duration'],
  price_rox: '22.00',
  min_seconds: 5,
  max_seconds: 10,
  ui_schema: {
    defaults: { duration: 5 },
    fields: [
      { name: 'duration', label: 'Длительность', control: 'combobox', suggestions: [5, 10], required: true, min: 5, max: 10 },
      { name: 'resolution', label: 'Разрешение видео', control: 'combobox', suggestions: ['720p', '1080p'] },
    ],
  },
};

const invalidVideoModel = {
  ...videoModel,
  id: 'video-without-image-input',
  title: 'Видео без I2V входа',
  operation: 'text_to_video',
  known_fields: ['prompt', 'duration'],
};

function v2Payload(videoModelId = videoModel.id) {
  return {
    schema_version: 2,
    workflow_type: 'sequential_photo_video',
    description: 'Фото превращается в видео.',
    preview_url: 'https://cdn.example.invalid/workflow.jpg',
    tags: ['workflow'],
    sort_order: 5,
    usage_count: 3,
    pricing_source: 'generation_service_catalog',
    steps: [
      {
        id: 'prepare_photo',
        kind: 'image',
        title: 'Подготовить фото',
        instructions: 'Выберите фото.',
        model_id: photoModel.id,
        prompt: 'Подготовь фото @Image1',
        parameters: { resolution: '1024' },
        inputs: [{ id: 'person_photo', label: 'Ваше фото', help: 'Портрет.', type: 'image', required: true, order: 0 }],
      },
      {
        id: 'animate_photo',
        kind: 'video',
        title: 'Оживить фото',
        instructions: 'Опишите движение.',
        model_id: videoModelId,
        prompt: 'Оживи @Image1',
        parameters: { duration: 5 },
        inputs: [],
        bindings: [{ from: 'prepare_photo.output_image', to: 'first_frame_url' }],
      },
    ],
  };
}

async function setup(page, { items = [], models = [photoModel, videoModel], touch = false } = {}) {
  const state = { items, models, writes: [], errors: [], unexpectedWrites: [] };
  page.on('pageerror', (error) => state.errors.push(error.message));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=admin-v2&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'Admin' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'admin', telegram_id: 777, first_name: 'Admin', is_admin: true, balance_rox: '1000' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/trends/manage' && request.method() === 'GET') return json({ items: state.items, models: state.models, limits: { max_references: 16, max_tags: 20 } });
    if (path === '/api/v1/trends/manage' && request.method() === 'POST') {
      const body = request.postDataJSON();
      state.writes.push(body);
      const created = { id: `created-${state.writes.length}`, title: body.title, payload: body.payload, is_active: true };
      state.items = [created, ...state.items];
      return json(created, 201);
    }
    if (path.startsWith('/api/v1/trends/manage/') && request.method() === 'PATCH') {
      const body = request.postDataJSON();
      state.writes.push(body);
      const id = path.split('/').at(-1);
      const updated = { ...state.items.find((item) => item.id === id), title: body.title, payload: body.payload, is_active: body.is_active };
      state.items = state.items.map((item) => item.id === id ? updated : item);
      return json(updated);
    }
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (request.method() !== 'GET') state.unexpectedWrites.push(request.method() + ' ' + path);
    return json({ items: [] });
  });
  await page.goto('/mini-app/?route=home');
  const manageButton = page.getByRole('button', { name: 'Управлять трендами' });
  if (touch) await manageButton.tap();
  else await manageButton.click();
  return state;
}

async function openCreate(page) {
  const manager = page.getByRole('dialog', { name: 'Управление трендами' });
  await manager.getByRole('button', { name: '＋ Новый тренд', exact: true }).click();
  return page.getByRole('dialog', { name: 'Добавить тренд', exact: true });
}

test('admin creates a v2 photo-to-video recipe from catalog-driven controls', async ({ page }) => {
  const state = await setup(page);
  const form = await openCreate(page);
  await form.getByRole('combobox', { name: 'Тип шаблона', exact: true }).selectOption('sequential_photo_video');
  await form.getByLabel('Название', { exact: true }).fill('Портрет в движении');
  await form.getByLabel('URL превью', { exact: true }).fill('https://cdn.example.invalid/workflow.jpg');
  await form.getByLabel('Название шага фото', { exact: true }).fill('Подготовить фото');
  await form.getByLabel('Инструкции к фото', { exact: true }).fill('Выберите фото.');
  await form.getByLabel('Промпт фото', { exact: true }).fill('Подготовь фото @Image1');
  await form.getByLabel('Название шага видео', { exact: true }).fill('Оживить фото');
  await form.getByLabel('Инструкции к видео', { exact: true }).fill('Опишите движение.');
  await form.getByLabel('Промпт видео', { exact: true }).fill('Оживи @Image1');
  await form.getByRole('button', { name: 'Опубликовать тренд', exact: true }).click();

  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload).toMatchObject({
    schema_version: 2,
    workflow_type: 'sequential_photo_video',
    steps: [
      { id: 'prepare_photo', kind: 'image', model_id: photoModel.id },
      { id: 'animate_photo', kind: 'video', model_id: videoModel.id, bindings: [{ from: 'prepare_photo.output_image', to: 'first_frame_url' }] },
    ],
  });
  expect(state.writes[0].payload.steps).toHaveLength(2);
  expect(state.writes[0].payload).not.toHaveProperty('price');
  expect(state.errors).toEqual([]);
});

test('admin uploads separate images for workflow steps 1 and 2', async ({ page }) => {
  const state = await setup(page);
  let uploads = 0;
  await page.route('**/api/v1/uploads/kie', route => {
    uploads += 1;
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ url: `https://cdn.example.invalid/step-${uploads}.jpg` }),
    });
  });
  const form = await openCreate(page);
  await form.getByRole('combobox', { name: 'Тип шаблона', exact: true }).selectOption('sequential_photo_video');
  await form.getByLabel('Название', { exact: true }).fill('Тренд с обложками шагов');
  await form.getByLabel('URL превью', { exact: true }).fill('https://cdn.example.invalid/workflow.jpg');
  await form.getByLabel('Промпт фото', { exact: true }).fill('Подготовь фото @Image1');
  await form.getByLabel('Промпт видео', { exact: true }).fill('Оживи @Image1');

  await form.getByLabel('Загрузить фото шага 1', { exact: true }).setInputFiles({
    name: 'step-1.png', mimeType: 'image/png', buffer: Buffer.from('synthetic-step-1'),
  });
  // Both upload inputs stay disabled until the current upload completes.
  await expect(form.getByLabel('URL фото шага 1', { exact: true })).toHaveValue('https://cdn.example.invalid/step-1.jpg');
  await expect(form.getByLabel('Загрузить фото шага 2', { exact: true })).toBeEnabled();
  await form.getByLabel('Загрузить фото шага 2', { exact: true }).setInputFiles({
    name: 'step-2.png', mimeType: 'image/png', buffer: Buffer.from('synthetic-step-2'),
  });
  await expect(form.getByLabel('URL фото шага 1', { exact: true })).toHaveValue('https://cdn.example.invalid/step-1.jpg');
  await expect(form.getByLabel('URL фото шага 2', { exact: true })).toHaveValue('https://cdn.example.invalid/step-2.jpg');
  await form.getByRole('button', { name: 'Опубликовать тренд', exact: true }).click();

  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload.steps.map(step => step.preview_url)).toEqual([
    'https://cdn.example.invalid/step-1.jpg',
    'https://cdn.example.invalid/step-2.jpg',
  ]);
  expect(uploads).toBe(2);
  expect(state.errors).toEqual([]);
});

test('editing and duplicating a v2 recipe preserve both structural steps and metadata', async ({ page }) => {
  const original = { id: 'workflow-1', title: 'Исходный workflow', is_active: true, payload: v2Payload() };
  const state = await setup(page, { items: [original] });
  const manager = page.getByRole('dialog', { name: 'Управление трендами' });
  await manager.getByRole('button', { name: 'Редактировать', exact: true }).click();
  const form = page.getByRole('dialog', { name: 'Редактировать тренд', exact: true });
  await form.locator('label').filter({ hasText: 'Описание' }).locator('textarea').fill('Изменённое описание без потери шагов.');
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload.steps).toEqual(original.payload.steps);
  expect(state.writes[0].payload.schema_version).toBe(2);
  expect(state.writes[0].payload.workflow_type).toBe('sequential_photo_video');

  await page.getByRole('dialog', { name: 'Управление трендами' }).getByRole('button', { name: 'Дублировать', exact: true }).click();
  const duplicate = page.getByRole('dialog', { name: 'Добавить тренд', exact: true });
  await duplicate.getByRole('button', { name: 'Опубликовать тренд', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1].payload.steps).toEqual(original.payload.steps);
  expect(state.items[0].id).not.toBe(original.id);
});

test('v2 save blocks when the selected video model has no compatible image binding', async ({ page }) => {
  const state = await setup(page, { models: [photoModel, invalidVideoModel] });
  const form = await openCreate(page);
  await form.getByRole('combobox', { name: 'Тип шаблона', exact: true }).selectOption('sequential_photo_video');
  await form.getByLabel('Название', { exact: true }).fill('Невалидный workflow');
  await form.getByLabel('URL превью', { exact: true }).fill('https://cdn.example.invalid/workflow.jpg');
  await form.getByLabel('Промпт фото', { exact: true }).fill('Фото @Image1');
  await form.getByLabel('Промпт видео', { exact: true }).fill('Видео @Image1');
  await form.getByRole('button', { name: 'Опубликовать тренд', exact: true }).click();
  await expect(form.getByRole('combobox', { name: 'Модель видео', exact: true })).toHaveValue('');
  await expect(form.getByText('В список попадают только модели с серверно подтверждённой I2V-возможностью.')).toBeVisible();
  expect(state.writes).toEqual([]);
});

test('ordinary v1 editor remains v1-shaped', async ({ page }) => {
  const state = await setup(page);
  const form = await openCreate(page);
  await expect(form.getByRole('combobox', { name: 'Тип шаблона', exact: true })).toHaveValue('legacy');
  await expect(form.getByLabel('Промпт фото', { exact: true })).toHaveCount(0);
  await form.getByLabel('Название', { exact: true }).fill('Обычный шаблон');
  await form.getByLabel('URL превью', { exact: true }).fill('https://cdn.example.invalid/legacy.jpg');
  await form.getByLabel('Скрытый промпт', { exact: true }).fill('Legacy prompt');
  await form.getByRole('button', { name: 'Опубликовать тренд', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload).not.toHaveProperty('schema_version');
  expect(state.writes[0].payload).not.toHaveProperty('steps');
});


test('failed preview upload can retry the same file', async ({ page }) => {
  await setup(page);
  let uploads = 0;
  await page.route('**/api/v1/uploads/kie', route => {
    uploads += 1;
    return route.fulfill({ status: uploads === 1 ? 503 : 201, contentType: 'application/json', body: JSON.stringify(uploads === 1 ? { detail: 'Synthetic upload outage' } : { url: 'https://cdn.example.invalid/retried.jpg' }) });
  });
  const form = await openCreate(page);
  const input = form.getByLabel('Загрузить превью', { exact: true });
  const file = { name: 'same.png', mimeType: 'image/png', buffer: Buffer.from('synthetic-preview') };
  await input.setInputFiles(file);
  await expect.poll(() => uploads).toBe(1);
  await expect(input).toHaveValue('');
  await input.setInputFiles(file);
  await expect(form.getByLabel('URL превью', { exact: true })).toHaveValue('https://cdn.example.invalid/retried.jpg');
  expect(uploads).toBe(2);
});

test.describe('workflow step video preview', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

  test('step 2 video preview uploads by touch, decodes, saves and survives editing', async ({ page, browserName }) => {
    const fixture = stepVideoFixtures[browserName];
    if (!fixture) throw new Error('No step video fixture for ' + browserName);
    const photoUrl = 'https://step-preview.example.invalid/photo.png';
    const videoUrl = 'https://step-preview.example.invalid/video.' + fixture.extension;
    const videoFile = { name: 'step-2.' + fixture.extension, mimeType: fixture.contentType, buffer: fixture.body };
    await page.route('https://telegram.org/js/telegram-web-app.js*', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
    await page.route('https://step-preview.example.invalid/**', route => (
      new URL(route.request().url()).pathname === '/photo.png'
        ? route.fulfill({ status: 200, contentType: 'image/png', body: stepPreviewPng })
        : fulfillStepVideo(route, fixture)
    ));
    const state = await setup(page, { touch: true });
    // WebKit's inspector flattens multipart data without the File segments.
    // Observe the actual File bytes at fetch entry, then forward the original
    // arguments and promise unchanged; this does not replace upload behavior.
    await page.evaluate(() => {
      const originalFetch = window.fetch.bind(window);
      window.__stepPreviewFileReads = [];
      window.fetch = (...args) => {
        const [input, init] = args;
        let path;
        try {
          path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname;
        } catch {
          return originalFetch(...args);
        }
        if (path === '/api/v1/uploads/kie') {
          const snapshot = init?.body instanceof FormData
            ? Promise.all(Array.from(init.body.entries(), async ([field, value]) => (
              value instanceof File ? {
                field, name: value.name, type: value.type, size: value.size,
                bytes: Array.from(new Uint8Array(await value.arrayBuffer())),
              } : { field, value }
            )))
            : Promise.resolve({ error: 'Upload body is not FormData' });
          window.__stepPreviewFileReads.push(snapshot.catch(error => ({ error: String(error) })));
        }
        return originalFetch(...args);
      };
    });
    const expectedPhotoFile = {
      field: 'file', name: 'step-1.png', type: 'image/png', size: stepPreviewPng.length,
      bytes: Array.from(stepPreviewPng),
    };
    const expectedVideoFile = {
      field: 'file', name: videoFile.name, type: fixture.contentType, size: fixture.body.length,
      bytes: Array.from(fixture.body),
    };
    const uploads = [];
    await page.route('**/api/v1/uploads/kie', route => {
      const request = route.request();
      expect(request.method()).toBe('POST');
      const body = request.postDataBuffer();
      const photo = body.includes(Buffer.from('filename="step-1.png"'));
      expect(body.includes(Buffer.from(photo ? 'image/png' : fixture.contentType))).toBe(true);
      if (!photo) expect(body.includes(Buffer.from('filename="' + videoFile.name + '"'))).toBe(true);
      uploads.push(photo ? 'image' : 'video');
      return route.fulfill({
        status: 201, contentType: 'application/json',
        body: JSON.stringify({ url: photo ? photoUrl : videoUrl, mime_type: photo ? 'image/png' : fixture.contentType }),
      });
    });
    const manager = page.getByRole('dialog', { name: 'Управление трендами', exact: true });
    await manager.getByRole('button', { name: '＋ Новый тренд', exact: true }).tap();
    const form = page.getByRole('dialog', { name: 'Добавить тренд', exact: true });
    await form.getByRole('combobox', { name: 'Тип шаблона', exact: true }).selectOption('sequential_photo_video');
    await form.getByLabel('Название', { exact: true }).fill('Тренд с видео второго шага');
    await form.getByLabel('URL превью', { exact: true }).fill(photoUrl);
    await form.getByLabel('Промпт фото', { exact: true }).fill('Подготовь фото @Image1');
    await form.getByLabel('Промпт видео', { exact: true }).fill('Оживи @Image1');
    const photoStep = form.locator('.inline-trend-workflow-step').nth(0);
    const videoStep = form.locator('.inline-trend-workflow-step').nth(1);
    const photoInput = photoStep.locator('input[type=file]');
    const videoInput = videoStep.locator('input[type=file]');
    await expect(photoInput).toHaveAttribute('accept', 'image/*');

    // The native filter and application validation must both keep Step 1 photo-only.
    let chooser = page.waitForEvent('filechooser');
    await photoInput.tap();
    await (await chooser).setFiles(videoFile);
    await expect(form.getByRole('alert')).toContainText('изображение');
    expect(uploads).toEqual([]);
    expect(await page.evaluate(() => window.__stepPreviewFileReads.length)).toBe(0);
    chooser = page.waitForEvent('filechooser');
    await photoInput.tap();
    await (await chooser).setFiles({ name: 'step-1.png', mimeType: 'image/png', buffer: stepPreviewPng });
    await expect(photoStep.locator('input[type=url]')).toHaveValue(photoUrl);
    await expect.poll(() => photoStep.locator('img').evaluate(node => node.complete && node.naturalWidth > 0)).toBe(true);
    expect(await page.evaluate(() => Promise.all(window.__stepPreviewFileReads))).toEqual([[expectedPhotoFile]]);
    await expect(videoInput).toBeEnabled();
    await expect(videoInput).toHaveAttribute('accept', /video\/\*/);

    chooser = page.waitForEvent('filechooser');
    await videoInput.tap();
    await (await chooser).setFiles(videoFile);
    await expect(videoStep.locator('input[type=url]')).toHaveValue(videoUrl);
    const preview = videoStep.locator('video');
    await preview.scrollIntoViewIfNeeded();
    await expect(preview).toBeVisible();
    await expect(preview).toHaveAttribute('src', videoUrl);
    await expect.poll(() => preview.evaluate(node => ({
      loaded: node.readyState >= 1, width: node.videoWidth, height: node.videoHeight, error: node.error?.code || null,
    }))).toEqual({ loaded: true, width: 32, height: 96, error: null });
    expect(await page.evaluate(() => Promise.all(window.__stepPreviewFileReads))).toEqual([[expectedPhotoFile], [expectedVideoFile]]);
    await expect(form.getByRole('alert')).toHaveCount(0);
    await form.getByRole('button', { name: 'Опубликовать тренд', exact: true }).tap();
    await expect.poll(() => state.writes.length).toBe(1);
    expect(state.writes[0].payload.steps.map(step => step.preview_url)).toEqual([photoUrl, videoUrl]);
    expect(state.writes[0].payload.steps[1].bindings).toEqual([{ from: 'prepare_photo.output_image', to: 'first_frame_url' }]);
    await expect(form).toHaveCount(0);

    await manager.getByRole('button', { name: 'Редактировать', exact: true }).tap();
    const editor = page.getByRole('dialog', { name: 'Редактировать тренд', exact: true });
    const savedStep = editor.locator('.inline-trend-workflow-step').nth(1);
    await expect(savedStep.locator('input[type=url]')).toHaveValue(videoUrl);
    await savedStep.locator('video').scrollIntoViewIfNeeded();
    await expect(savedStep.locator('video')).toHaveAttribute('src', videoUrl);
    await expect.poll(() => savedStep.locator('video').evaluate(node => node.readyState >= 1 && node.videoWidth > 0 && !node.error)).toBe(true);
    await editor.getByLabel('Название', { exact: true }).fill('Тренд с видео после редактирования');
    await editor.getByRole('button', { name: 'Сохранить', exact: true }).tap();
    await expect.poll(() => state.writes.length).toBe(2);
    expect(state.writes[1].payload.steps).toEqual(state.writes[0].payload.steps);
    expect(uploads).toEqual(['image', 'video']);
    expect(state.unexpectedWrites).toEqual([]);
    expect(state.errors).toEqual([]);
  });
});
