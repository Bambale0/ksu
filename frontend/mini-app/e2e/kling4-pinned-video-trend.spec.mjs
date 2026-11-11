import { expect, test } from '@playwright/test';

const ID = '12345678-1234-4234-8234-123456789abc';
const VIDEO = 'https://media.example/pinned-motion.mp4';
const photo = name => ({ name, mimeType: 'image/png', buffer: Buffer.from('synthetic photo') });

function init(page, admin = false) {
  return page.addInitScript(({ admin }) => {
    window.Telegram = { WebApp: {
      initData: 'query_id=kling-pinned&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: admin ? 'Admin' : 'Viewer' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  }, { admin });
}

test('Kling 4 customer trend only asks for two photos, not video, prompt or quality', async ({ page }) => {
  const runs = [];
  let uploaded = 0;
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await init(page);
  await page.route('**/api/v1/**', route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === `/api/v1/trends/${ID}` && request.method() === 'GET') return json({
      id: ID, title: 'Танец вдвоём', media_type: 'video',
      model: { id: 'kling-4.0', title: 'Kling 4.0' }, preview_url: null,
      cost_rox: '300.00', aspect_ratio_options: [],
      reference_requirements: { kind: 'image', min: 2, max: 2, image: { min: 2, max: 2 }, video: { min: 0, max: 0 } },
    });
    if (path === `/api/v1/trends/${ID}/run`) {
      runs.push(request.postDataJSON());
      return json({ id: 'created', status: 'queued' }, 202);
    }
    if (path === '/api/v1/uploads/kie') {
      uploaded += 1;
      return json({ url: `https://media.example/visitor-${uploaded}.png`, reference: { kind: 'image' }, probe_status: 'ready' });
    }
    if (path === '/api/v1/me') return json({ id: 'viewer', balance_rox: '1000', is_admin: false });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    return json({ items: [] });
  });
  await page.goto(`/mini-app/trend/?id=${ID}`);
  const run = page.getByRole('button', { name: /Сгенерировать · 300 ROX/ });
  await expect(run).toBeDisabled();
  await expect(page.getByText('Добавьте 2 изображения.')).toBeVisible();
  await expect(page.getByLabel('Видеореференсы тренда')).toHaveCount(0);
  await expect(page.getByRole('radiogroup', { name: 'Формат кадра' })).toHaveCount(0);
  await page.locator('input[accept="image/*"]').setInputFiles([photo('face-1.png'), photo('face-2.png')]);
  await expect(page.getByText('face-1.png')).toBeVisible();
  await expect(page.getByText('face-2.png')).toBeVisible();
  await expect(run).toBeEnabled();
  await run.click();
  await expect.poll(() => runs.length).toBe(1);
  expect(runs[0].reference_urls).toEqual([
    'https://media.example/visitor-1.png', 'https://media.example/visitor-2.png',
  ]);
  expect(runs[0].video_reference_urls || []).toEqual([]);
  expect(JSON.stringify(runs[0])).not.toContain(VIDEO);
  expect(errors).toEqual([]);
});

test('admin attaches permanent video and publishes locked 2-photo Kling trend', async ({ page }) => {
  const writes = [];
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await init(page, true);
  const model = {
    id: 'kling-4.0', title: 'Kling 4.0', family: 'kling', media_type: 'video', operation: 'multimodal_video',
    price_rox: '30', reference_capacity: 8,
    known_fields: ['prompt', 'image_urls', 'video_urls', 'duration', 'resolution', 'aspect_ratio'],
    required_fields: ['prompt'],
    ui_schema: {
      defaults: { duration: 5, resolution: '720p', aspect_ratio: '9:16' },
      groups: [], fields: [
        { name: 'duration', label: 'Длительность', control: 'number', min: 3, max: 30 },
        { name: 'resolution', label: 'Разрешение', control: 'combobox', suggestions: ['720p', '1080p'] },
        { name: 'aspect_ratio', label: 'Формат', control: 'combobox', suggestions: ['16:9', '9:16', '1:1'] },
      ],
    },
  };
  await page.route('**/api/v1/**', route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'admin', first_name: 'Admin', is_admin: true, balance_rox: '1000' });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/trends/manage' && request.method() === 'GET') return json({ items: [], models: [model] });
    if (path === '/api/v1/uploads/kie') return json({ url: 'https://media.example/preview.jpg', reference: { kind: 'image' } }, 201);
    if (path === '/api/v1/uploads/template-video') return json({
      url: VIDEO, name: 'motion.mp4', mime_type: 'video/mp4', size: 1024, duration_ms: 5000,
      probe_status: 'ready', reference: { id: 'admin-video', kind: 'video' },
    }, 201);
    if (path === '/api/v1/trends/manage' && request.method() === 'POST') {
      writes.push(request.postDataJSON());
      return json({ id: ID, is_active: true, ...request.postDataJSON() }, 201);
    }
    if (request.method() === 'GET') return json({ items: [], has_more: false });
    return json({ detail: `Unexpected mutation: ${path}` }, 400);
  });
  await page.goto('/mini-app/?route=home');
  await page.getByRole('button', { name: 'Управлять трендами' }).click();
  await page.getByRole('button', { name: '＋ Новый тренд' }).click();
  const form = page.getByRole('dialog', { name: 'Добавить тренд' });
  await form.getByLabel('Название', { exact: true }).fill('Танец вдвоём');
  await form.getByLabel('Скрытый промпт').fill('Follow @video_1 with @image_1 and @image_2');
  await form.getByLabel('Загрузить постоянное видео Kling 4.0').setInputFiles({
    name: 'motion.mp4', mimeType: 'video/mp4', buffer: Buffer.from('synthetic video'),
  });
  await expect(form.getByText('Референсы пользователя: ровно два фото')).toBeVisible();
  await expect(form.getByLabel('Минимум фото')).toHaveValue('2');
  await expect(form.getByLabel('Максимум фото')).toHaveValue('2');
  await expect(form.getByLabel('Минимум фото')).toBeDisabled();
  await form.getByLabel('Загрузить превью').setInputFiles(photo('preview.png'));
  await form.getByRole('button', { name: 'Опубликовать тренд' }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].payload.template_video_url).toBe(VIDEO);
  expect(writes[0].payload.min_references).toBe(2);
  expect(writes[0].payload.max_references).toBe(2);
  expect(writes[0].payload.parameters).toMatchObject({ aspect_ratio: '9:16', resolution: '720p', duration: 5 });
  expect(errors).toEqual([]);
});
