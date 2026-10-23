import { expect, test } from '@playwright/test';

const audioUrl = 'https://cdn.example.invalid/template-audio.mp3';
const seedance = {
  id: 'seedance-2.5', title: 'Seedance 2.5', family: 'seedance', media_type: 'video',
  known_fields: ['prompt', 'reference_image_urls', 'reference_audio_urls', 'duration', 'resolution', 'aspect_ratio'],
  required_fields: ['prompt', 'duration'], duration_field: 'duration', reference_capacity: 30,
};
const imageModel = { id: 'nano-banana-pro', title: 'Nano Banana Pro', family: 'nanobanana', media_type: 'image', known_fields: ['image_input'] };
const recipe = {
  model_id: seedance.id, media_type: 'video', prompt: 'Анимация @Image1 со звуком @Audio1',
  preview_url: 'https://cdn.example.invalid/preview.jpg', input_mode: 'image',
  min_references: 1, max_references: 1, billing_seconds: 10,
  parameters: { resolution: '720p', duration: 10, aspect_ratio: '9:16' },
};

async function setup(page, { admin = true, audio = false } = {}) {
  const state = { writes: [], uploads: 0, errors: [], items: [{
    id: 'template_1', title: 'Шаблон со звуком', is_active: true,
    payload: { ...recipe, parameters: { ...recipe.parameters, ...(audio ? { reference_audio_urls: [audioUrl] } : {}) } },
  }] };
  page.on('pageerror', error => state.errors.push(error.message));
  await page.setViewportSize({ width: 393, height: 852 });
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=template-audio&hash=test', initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('https://cdn.example.invalid/**', route => route.fulfill({ status: 200, body: '' }));
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'admin', first_name: 'QA', telegram_id: 777, is_admin: admin, balance_rox: '1000' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (path === '/api/v1/trends/manage' && request.method() === 'GET') return json({ items: state.items, models: [seedance, imageModel] });
    if (path.startsWith('/api/v1/trends/manage') && request.method() !== 'GET') {
      const body = request.postDataJSON();
      state.writes.push(body);
      state.items = [{ id: 'template_1', ...body }];
      return json(state.items[0]);
    }
    if (path === '/api/v1/uploads/template-audio') {
      state.uploads += 1;
      expect(request.postDataBuffer().toString()).toContain('filename="reference.mp3"');
      return json({ url: audioUrl, mime_type: 'audio/mpeg', probe_status: 'ready', duration_ms: 10000, reference: { id: 'audio_1', kind: 'audio' } }, 201);
    }
    return json({ items: [], has_more: false });
  });
  await page.goto('/mini-app/?route=catalog');
  return state;
}

async function edit(page, action = 'Редактировать') {
  await page.getByRole('button', { name: 'Управлять трендами' }).click();
  const manager = page.getByRole('dialog', { name: 'Управление трендами' });
  await manager.getByRole('button', { name: action, exact: true }).click();
  return page.getByRole('dialog', { name: action === 'Дублировать' ? 'Добавить тренд' : 'Редактировать тренд' });
}

const file = { name: 'reference.mp3', mimeType: 'audio/mpeg', buffer: Buffer.from('synthetic audio; upload response is mocked') };

test('admin uploads a verified model audio reference into the template recipe', async ({ page }) => {
  const state = await setup(page);
  const form = await edit(page);
  await form.getByLabel('Добавить аудиореференс').setInputFiles(file);
  await expect(form.getByText('@Audio1', { exact: true })).toBeVisible();
  await expect(form.locator('audio')).toHaveAttribute('src', audioUrl);
  const audioGroup = form.getByRole('group', { name: 'Аудиореференсы шаблона' });
  await audioGroup.scrollIntoViewIfNeeded();
  expect(await audioGroup.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/template-audio-reference-mobile.png' });
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload.parameters).toEqual({ ...recipe.parameters, reference_audio_urls: [audioUrl] });
  expect(state.writes[0].payload.prompt).toBe(recipe.prompt);
  expect(state.uploads).toBe(1);
  expect(state.errors).toEqual([]);
});

test('new template can attach audio without editing JSON', async ({ page }) => {
  const state = await setup(page);
  await page.getByRole('button', { name: 'Управлять трендами' }).click();
  await page.getByRole('button', { name: /Новый тренд/ }).click();
  const form = page.getByRole('dialog', { name: 'Добавить тренд' });
  await form.getByLabel('Название', { exact: true }).fill('Новый аудиошаблон');
  await form.getByLabel('URL превью').fill(recipe.preview_url);
  await form.getByLabel('Скрытый промпт').fill('Создай видео со звуком @Audio1');
  await form.getByLabel('Длительность, сек').fill('10');
  await form.getByLabel('Добавить аудиореференс').setInputFiles(file);
  await expect(form.getByText('@Audio1', { exact: true })).toBeVisible();
  await form.getByRole('button', { name: 'Опубликовать тренд' }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload.parameters).toEqual({ reference_audio_urls: [audioUrl], duration: 10 });
});

test('editing and duplicating retain saved audio; removal preserves other settings', async ({ page }) => {
  const state = await setup(page, { audio: true });
  let form = await edit(page, 'Дублировать');
  await expect(form.locator('audio')).toHaveAttribute('src', audioUrl);
  await form.getByRole('button', { name: 'Опубликовать тренд' }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].payload.parameters.reference_audio_urls).toEqual([audioUrl]);
  await page.getByRole('dialog', { name: 'Управление трендами' }).getByRole('button', { name: 'Редактировать', exact: true }).click();
  form = page.getByRole('dialog', { name: 'Редактировать тренд' });
  await form.getByRole('button', { name: 'Удалить аудиореференс 1' }).click();
  await expect(form.locator('audio')).toHaveCount(0);
  await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1].payload.parameters).toEqual(recipe.parameters);
  expect(state.uploads).toBe(0);
});

for (const response of [
  { name: 'unverified duration', status: 201, body: { url: audioUrl, probe_status: 'failed', duration_ms: null, reference: { kind: 'audio' } } },
  { name: 'wrong media kind', status: 201, body: { url: audioUrl, probe_status: 'ready', duration_ms: 10000, reference: { kind: 'video' } } },
  { name: 'failed upload', status: 503, body: { detail: 'Temporarily unavailable' } },
]) {
  test(`${response.name} does not attach an audio URL and permits retry`, async ({ page }) => {
    const state = await setup(page);
    const form = await edit(page);
    await page.route('**/api/v1/uploads/template-audio', route => route.fulfill({ status: response.status, contentType: 'application/json', body: JSON.stringify(response.body) }));
    await form.getByLabel('Добавить аудиореференс').setInputFiles(file);
    await expect(form.getByRole('alert')).toBeVisible();
    await expect(form.locator('audio')).toHaveCount(0);
    await expect(form.getByLabel('Добавить аудиореференс')).toBeEnabled();
    await form.getByText('Дополнительные параметры модели', { exact: true }).click();
    expect(JSON.parse(await form.getByLabel('JSON параметров').inputValue())).toEqual(recipe.parameters);
    expect(state.writes).toEqual([]);
    await page.unroute('**/api/v1/uploads/template-audio');
    await form.getByLabel('Добавить аудиореференс').setInputFiles(file);
    await expect(form.locator('audio')).toHaveAttribute('src', audioUrl);
    expect(state.errors).toEqual([]);
  });
}

test('an upload locks conflicting edits and cannot change a newly opened draft', async ({ page }) => {
  const state = await setup(page);
  let pending;
  await page.route('**/api/v1/uploads/template-audio', route => { pending = route; });
  let form = await edit(page);
  await form.getByLabel('Добавить аудиореференс').setInputFiles(file);
  await expect.poll(() => Boolean(pending)).toBe(true);
  await expect(form.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled();
  await expect(form.getByRole('combobox', { name: /^Модель/ })).toBeDisabled();
  await form.getByText('Дополнительные параметры модели', { exact: true }).click();
  await expect(form.getByLabel('JSON параметров')).toBeDisabled();
  await form.getByRole('button', { name: 'Отмена', exact: true }).click();
  await page.getByRole('dialog', { name: 'Управление трендами' }).getByRole('button', { name: /Новый тренд/ }).click();
  form = page.getByRole('dialog', { name: 'Добавить тренд' });
  await form.getByLabel('Название', { exact: true }).fill('Другой шаблон');
  const response = page.waitForResponse('**/api/v1/uploads/template-audio');
  await pending.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ url: audioUrl, probe_status: 'ready', duration_ms: 10000, reference: { kind: 'audio' } }) });
  await response;
  await expect(form.getByLabel('Название', { exact: true })).toHaveValue('Другой шаблон');
  await expect(form.locator('audio')).toHaveCount(0);
  await expect(form.getByLabel('Добавить аудиореференс')).toBeEnabled();
  expect(state.writes).toEqual([]);
});

test('unsupported models cannot upload audio and keep removal available for legacy entries', async ({ page }) => {
  await setup(page, { audio: true });
  const form = await edit(page);
  await form.getByRole('combobox', { name: /^Модель/ }).selectOption(imageModel.id);
  await expect(form.getByLabel('Добавить аудиореференс')).toHaveCount(0);
  await expect(form.getByText('Выбранная модель не поддерживает эти аудиореференсы.', { exact: false })).toBeVisible();
  await form.getByRole('button', { name: 'Удалить аудиореференс 1' }).click();
  await expect(form.getByRole('group', { name: 'Аудиореференсы шаблона' })).toHaveCount(0);
});

test('regular users have no template audio editor', async ({ page }) => {
  await setup(page, { admin: false });
  await expect(page.getByRole('heading', { name: 'Готовые сценарии' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Управлять трендами' })).toHaveCount(0);
});

for (const mimeType of ['', 'application/octet-stream', 'binary/octet-stream']) {
  test(`server classifies audio with browser MIME ${mimeType || 'empty'}`, async ({ page }) => {
    const state = await setup(page);
    const form = await edit(page);
    await form.getByLabel('Добавить аудиореференс').setInputFiles({ ...file, mimeType });
    await expect(form.locator('audio')).toHaveAttribute('src', audioUrl);
    await form.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await expect.poll(() => state.writes.length).toBe(1);
    expect(state.writes[0].payload.parameters.reference_audio_urls).toEqual([audioUrl]);
    expect(state.uploads).toBe(1);
  });
}
