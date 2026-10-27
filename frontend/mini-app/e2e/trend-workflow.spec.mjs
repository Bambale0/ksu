import { expect, test } from '@playwright/test';

const TREND_ID = '56156156-1111-4111-8111-561561561111';
const RUN_ID = '56156156-2222-4222-8222-561561562222';
const PHOTO_GENERATION_ID = '56156156-3333-4333-8333-561561563333';
const VIDEO_GENERATION_ID = '56156156-4444-4444-8444-561561564444';
const PHOTO_BYTES = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABgAAAAgCAIAAACHPC9vAAAAJ0lEQVR4nGMMiK9goAZgooopowaNGjRq0KhBowaNGjRq0KhBA24QAK8vAWeEfhD0AAAAAElFTkSuQmCC', 'base64');
const PHOTO_URL = 'https://media.example.invalid/photo-owned.jpg';
const VIDEO_URL = 'https://media.example.invalid/video-owned.mp4';
const PREVIEW_URL = 'https://media.example.invalid/trend-preview.jpg';

const workflowTrend = {
  id: TREND_ID,
  title: 'Фото в видео',
  description: 'Подготовьте фото, затем оживите его.',
  schema_version: 2,
  workflow_type: 'sequential_photo_video',
  media_type: 'image',
  preview_url: PREVIEW_URL,
  preview_thumbnail_url: PREVIEW_URL,
  steps: [
    {
      id: 'prepare_photo',
      kind: 'image',
      title: 'Подготовить фото',
      instructions: 'Загрузите своё фото и фото одежды.',
      inputs: [
        { id: 'person_photo', label: 'Ваше фото', help: 'Чёткий портрет без очков.', type: 'image', required: true, order: 0 },
        { id: 'outfit_photo', label: 'Фото одежды', help: 'Покажите вещь целиком.', type: 'image', required: false, order: 1 },
        { id: 'occasion', label: 'Случай', help: 'Например, прогулка или праздник.', type: 'select', required: true, order: 2, options: ['Прогулка', 'Праздник'] },
        { id: 'personalization', label: 'Личная надпись', help: 'Необязательное поле для персонализации.', type: 'text', required: false, order: 3 },
      ],
    },
    { id: 'animate_photo', kind: 'video', title: 'Оживить фото', instructions: 'Выберите готовое фото.', inputs: [] },
  ],
};

function workflow(status = 'created', photoStatus = 'pending', videoStatus = 'pending') {
  return {
    id: RUN_ID,
    title: workflowTrend.title, description: workflowTrend.description,
    trend_id: TREND_ID,
    status,
    recipe_version: 2,
    workflow_type: 'sequential_photo_video',
    steps: [
      {
        id: 'prepare_photo',
        kind: 'image',
        title: 'Подготовить фото',
        instructions: 'Загрузите своё фото и фото одежды.',
        inputs: workflowTrend.steps[0].inputs,
        status: photoStatus,
        generation_id: photoStatus === 'ready' ? PHOTO_GENERATION_ID : photoStatus === 'running' ? PHOTO_GENERATION_ID : null,
        media_asset_id: photoStatus === 'ready' ? 'asset-photo-1' : null,
        media: photoStatus === 'ready' ? { id: 'asset-photo-1', url: PHOTO_URL, kind: 'image' } : null,
        media_options: photoStatus === 'ready' ? [{ id: 'asset-photo-1', url: PHOTO_URL, kind: 'image' }, { id: 'asset-photo-2', url: 'https://media.example.invalid/photo-owned-2.jpg', kind: 'image' }] : [],
        attempts: photoStatus === 'ready' ? 1 : 0,
        reconcile_required: false,
        command_id: null,
        attempt_history: [],
      },
      {
        id: 'animate_photo',
        kind: 'video',
        title: 'Оживить фото',
        instructions: 'Выберите готовое фото.',
        inputs: [],
        status: videoStatus,
        generation_id: videoStatus === 'ready' ? VIDEO_GENERATION_ID : null,
        media_asset_id: videoStatus === 'ready' ? 'asset-video-1' : null,
        media: videoStatus === 'ready' ? { id: 'asset-video-1', url: VIDEO_URL, kind: 'video' } : null,
        media_options: [],
        attempts: videoStatus === 'ready' ? 1 : 0,
        reconcile_required: false,
        command_id: null,
        attempt_history: [],
      },
    ],
  };
}

async function setup(page, { legacy = false, ambiguousPhotoRun = false, delayedMedia = false, hiddenTemplate = false, quoteFailsOnce = false, failPhoto = false, retryQuoteCost = null, failVideo = false, retryVideoQuoteCost = null, ambiguousVideoRun = false, lostCreate = false, photoReadyGate = null } = {}) {
  const state = { quoteBodies: [], runBodies: [], photoRuns: 0, videoRuns: 0, photoQuotes: 0, videoQuotes: 0, workflowReads: 0, workflowCreates: 0, errors: [] };
  let photoReady = false;
  let photoFailed = false;
  let quoteFailure = quoteFailsOnce;
  let videoAmbiguity = ambiguousVideoRun;
  let creationLoss = lostCreate;
  let videoReady = false;
  let videoFailed = false;
  let ambiguous = ambiguousPhotoRun;
  let workflowCreated = hiddenTemplate;
  let mediaReads = 0;
  let photoCommandId = null;
  let videoCommandId = null;
  const workflowView = (...args) => {
    const view = workflow(...args);
    view.steps[0].command_id = photoCommandId;
    view.steps[1].command_id = videoCommandId;
    if (photoCommandId && view.steps[0].status !== 'pending') view.steps[0].generation_id = PHOTO_GENERATION_ID;
    if (videoCommandId && view.steps[1].status !== 'pending') view.steps[1].generation_id = VIDEO_GENERATION_ID;
    return view;
  };

  page.on('pageerror', (error) => state.errors.push(error.message));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=trend-workflow&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('https://media.example.invalid/**', (route) => route.fulfill({ contentType: 'image/png', body: PHOTO_BYTES }));
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'viewer', telegram_id: 777, first_name: 'QA', balance_rox: '1000' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === `/api/v1/trends/${TREND_ID}/workflow` && request.method() === 'GET') return workflowCreated ? json(workflowView(photoReady ? 'step1_ready' : 'created', photoReady ? 'ready' : 'pending', videoReady ? 'ready' : 'pending')) : json({}, 404);
    if (path === `/api/v1/trends/${TREND_ID}` && request.method() === 'GET') {
      if (hiddenTemplate) return json({}, 404);
      if (legacy) return json({ id: TREND_ID, title: 'Старый тренд', description: 'Старый сценарий', media_type: 'image', cost_rox: '25', reference_requirements: { min: 0, max: 0 } });
      return json(workflowTrend);
    }
    if (path === `/api/v1/trends/${TREND_ID}/workflow` && request.method() === 'POST') { workflowCreated = true; state.workflowCreates += 1; if (creationLoss) { creationLoss = false; return route.abort('failed'); } return json(workflowView(), 201); }
    if (path === '/api/v1/uploads/kie') return json({ url: 'https://upload.example.invalid/photo-input.jpg', name: 'person.jpg', mime_type: 'image/jpeg' }, 201);
    if (path === `/api/v1/trends/workflows/${RUN_ID}` && request.method() === 'GET') {
      state.workflowReads += 1;
      if (photoReady && photoReadyGate) await photoReadyGate;
      if (videoReady) return json(workflowView('completed', 'ready', 'ready'));
      if (videoFailed) return json(workflowView('failed', 'ready', 'failed'));
      if (photoFailed) { const view = workflowView('failed', 'failed', 'pending'); view.steps[0].generation_id = PHOTO_GENERATION_ID; return json(view); }
      if (photoReady && delayedMedia && mediaReads++ < 2) return json(workflowView('running', 'awaiting_media', 'pending'));
      if (photoReady) return json(workflowView('step1_ready', 'ready', 'pending'));
      return json(workflowView(state.photoRuns ? 'running' : 'created', state.photoRuns ? 'running' : 'pending', 'pending'));
    }
    if (path.includes(`/api/v1/trends/workflows/${RUN_ID}/steps/`) && path.endsWith('/quote')) {
      const body = request.postDataJSON();
      state.quoteBodies.push(body);
      const isVideo = path.includes('/animate_photo/');
      if (isVideo) state.videoQuotes += 1;
      else state.photoQuotes += 1;
      if (quoteFailure) { quoteFailure = false; return json({ detail: 'Synthetic quote outage' }, 503); }
      const cost = isVideo
        ? (retryVideoQuoteCost && state.videoQuotes > 1 ? retryVideoQuoteCost : '12.00')
        : (retryQuoteCost && state.photoQuotes > 1 ? retryQuoteCost : '25.00');
      return json({ cost_rox: cost, retail_cost_rox: cost, admin_free: false, billing_seconds: isVideo ? 5 : null });
    }
    if (path.includes(`/api/v1/trends/workflows/${RUN_ID}/steps/`) && path.endsWith('/run')) {
      const body = request.postDataJSON();
      state.runBodies.push({ body, key: request.headers()['idempotency-key'] });
      if (path.includes('/prepare_photo/')) {
        state.photoRuns += 1;
        photoCommandId = request.headers()['idempotency-key'];
        if (ambiguous) {
          ambiguous = false;
          return route.abort('failed');
        }
        if (failPhoto && state.photoRuns === 1) { photoFailed = true; const view = workflowView('failed', 'failed', 'pending'); view.steps[0].generation_id = PHOTO_GENERATION_ID; return json(view, 202); }
        photoFailed = false;
        photoReady = true;
        return json(workflowView('running', 'running', 'pending'), 202);
      }
      state.videoRuns += 1;
      if (videoAmbiguity) { videoAmbiguity = false; return route.abort('failed'); }
      videoCommandId = request.headers()['idempotency-key'];
      if (failVideo && state.videoRuns === 1) { videoFailed = true; return json(workflowView('failed', 'ready', 'failed'), 202); }
      videoFailed = false;
      videoReady = true;
      return json(workflowView('completed', 'ready', 'ready'), 202);
    }
    return json({ items: [], has_more: false });
  });
  await page.goto(`/mini-app/trend/?id=${TREND_ID}`);
  return state;
}

const imageFile = { name: 'person.png', mimeType: 'image/png', buffer: PHOTO_BYTES };

test('v2 matches the two-card locked-step reference and explains Step 1 in a modal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await setup(page);
  await expect(page.getByRole('heading', { name: 'Подготовить фото' })).toBeVisible();
  const stages = page.getByRole('navigation', { name: 'Этапы сценария' });
  const photoCard = stages.getByRole('button', { name: /Шаг 1.*Подготовить фото/i });
  const locked = stages.getByRole('button', { name: /Шаг 2.*Оживить фото.*Сначала Шаг 1/i });
  await expect(photoCard.getByRole('img', { name: /Шаг 1/i })).toHaveAttribute('src', PREVIEW_URL);
  await expect(locked.getByRole('img', { name: /Шаг 2/i })).toHaveAttribute('src', PREVIEW_URL);
  await expect(locked.getByText('Сначала Шаг 1', { exact: true })).toBeVisible();
  await expect(locked).toHaveAttribute('aria-haspopup', 'dialog');
  await expect(locked).toBeVisible();
  await locked.click();
  const dialog = page.getByRole('dialog', { name: 'Сначала Шаг 1' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/загружается фото, которое вы создадите на Шаге 1/i)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Отмена' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'Перейти к Шагу 1' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: 'Отмена' })).toBeFocused();
  await dialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(dialog).toBeHidden();
  await expect(locked).toBeFocused();

  await locked.click();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(locked).toBeFocused();

  await locked.click();
  await dialog.locator('..').click({ position: { x: 2, y: 2 } });
  await expect(dialog).toBeHidden();
  await expect(locked).toBeFocused();

  await locked.click();
  await page.getByRole('dialog', { name: 'Сначала Шаг 1' }).getByRole('button', { name: 'Перейти к Шагу 1' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator('[data-step="prepare_photo"]')).toBeFocused();

  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await expect.poll(() => state.quoteBodies.length).toBeGreaterThan(0);
  expect(state.quoteBodies.at(-1)).toEqual(expect.objectContaining({
    image_inputs: [{ slot_id: 'person_photo', url: 'https://upload.example.invalid/photo-input.jpg' }],
    values: { occasion: 'Прогулка' },
  }));
  expect(state.quoteBodies.at(-1)).not.toHaveProperty('reference_urls');
});

test('ready Step 1 unlocks the visual Step 2 card without showing the modal', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await page.getByRole('button', { name: /Создать фото/ }).click();
  await expect.poll(() => state.workflowReads).toBeGreaterThan(0);
  const stages = page.getByRole('navigation', { name: 'Этапы сценария' });
  const videoCard = stages.getByRole('button', { name: /Шаг 2.*Оживить фото/i });
  await expect(videoCard).not.toHaveAttribute('aria-haspopup', 'dialog');
  await expect(videoCard.getByText('Сначала Шаг 1', { exact: true })).toHaveCount(0);
  await videoCard.click();
  await expect(page.getByRole('dialog', { name: 'Сначала Шаг 1' })).toHaveCount(0);
  await expect(page.locator('[data-step="animate_photo"]')).toBeVisible();
});

test('an open lock explanation closes when Step 1 becomes ready in the background', async ({ page }) => {
  let releasePhotoReady;
  const photoReadyGate = new Promise((resolve) => { releasePhotoReady = resolve; });
  await setup(page, { photoReadyGate });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await page.getByRole('button', { name: /Создать фото/ }).click();
  const stages = page.getByRole('navigation', { name: 'Этапы сценария' });
  const videoCard = stages.getByRole('button', { name: /Шаг 2.*Оживить фото/i });
  await videoCard.click();
  await expect(page.getByRole('dialog', { name: 'Сначала Шаг 1' })).toBeVisible();
  releasePhotoReady();
  await expect(page.getByRole('dialog', { name: 'Сначала Шаг 1' })).toHaveCount(0);
  await expect(videoCard).not.toHaveAttribute('aria-haspopup', 'dialog');
  await expect(videoCard).toBeFocused();
});

test('v2 requires explicit stage-two consent and de-duplicates a double click', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await expect(page.getByRole('button', { name: /Создать фото/ })).toBeEnabled();
  await page.getByRole('button', { name: /Создать фото/ }).click();
  // A fast completed poll may replace the queued state before the next frame.
  await expect.poll(() => state.workflowReads).toBeGreaterThan(0);
  await expect(page.locator('[data-step="animate_photo"]')).toBeVisible();
  await expect(page.getByRole('button', { name: /Оживить это фото/ })).toBeVisible();
  await page.getByRole('button', { name: /Оживить это фото/ }).dblclick();
  await expect.poll(() => state.videoRuns).toBe(1);
  expect(state.runBodies.filter(({ body }) => body.media_asset_id === 'asset-photo-1')).toHaveLength(1);
  expect(state.runBodies.at(-1).body).not.toHaveProperty('image_inputs');
});

test('ambiguous stage-one network keeps the command key while status is reconciled', async ({ page }) => {
  const state = await setup(page, { ambiguousPhotoRun: true });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await expect(page.getByRole('button', { name: /Создать фото/ })).toBeEnabled();
  await page.getByRole('button', { name: /Создать фото/ }).click();
  // This fixture accepted the task but deliberately keeps it in progress.
  // Recovery must show that original task, not invent a finished photo or resubmit.
  await expect(page.getByText(/Состояние: выполняется/)).toBeVisible();
  await expect(page.getByText(/задача 56156156-3333-4333-8333-561561563333/)).toBeVisible();
  await expect.poll(() => state.workflowReads).toBeGreaterThan(0);
  expect(state.runBodies).toHaveLength(1);
  expect(state.runBodies[0].key).toBeTruthy();
});

test('legacy v1 trend keeps the existing one-step controls', async ({ page }) => {
  await setup(page, { legacy: true });
  await expect(page.getByRole('button', { name: /Сгенерировать/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Подготовить фото' })).toHaveCount(0);
});

test('workflow cards have no horizontal overflow at mobile and desktop acceptance widths', async ({ page }, testInfo) => {
  await setup(page);
  const stages = page.getByRole('navigation', { name: 'Этапы сценария' });
  const photoCard = stages.getByRole('button', { name: /Шаг 1.*Подготовить фото/i });
  const videoCard = stages.getByRole('button', { name: /Шаг 2.*Оживить фото/i });
  for (const width of [320, 375, 390, 430, 768]) {
    await page.setViewportSize({ width, height: 852 });
    await expect(page.getByRole('heading', { name: 'Подготовить фото', exact: true })).toBeVisible();
    await expect(page.locator('[data-step="prepare_photo"]')).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`workflow-${width}.png`), fullPage: true });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const photoBox = await photoCard.boundingBox();
    const videoBox = await videoCard.boundingBox();
    const chipBox = await videoCard.getByText('Сначала Шаг 1', { exact: true }).boundingBox();
    expect(photoBox).not.toBeNull();
    expect(videoBox).not.toBeNull();
    expect(chipBox).not.toBeNull();
    expect(Math.abs(photoBox.width - videoBox.width)).toBeLessThanOrEqual(1);
    expect(Math.abs((photoBox.width / photoBox.height) - 0.8)).toBeLessThan(0.03);
    expect(Math.abs((chipBox.x + chipBox.width / 2) - (videoBox.x + videoBox.width / 2))).toBeLessThanOrEqual(1);
    await expect(videoCard.locator('img')).not.toHaveCSS('filter', 'none');
  }
});

test('reload resumes the owner workflow without creating or charging another run', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await expect(page.getByRole('button', { name: /Создать фото/ })).toBeEnabled();
  await page.getByRole('button', { name: /Создать фото/ }).click();
  await expect.poll(() => state.photoRuns).toBe(1);
  await page.reload();
  await expect(page.locator('[data-step="animate_photo"]')).toBeVisible();
  expect(state.workflowCreates).toBe(1);
});

test('ready photo exposes owned media choices and quotes the selected asset', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption({ label: 'Прогулка' });
  await page.getByRole('button', { name: /Создать фото/ }).click();
  await expect(page.getByRole('radio', { name: /Вариант 2/ })).toBeVisible();
  await page.getByRole('radio', { name: /Вариант 2/ }).click();
  await expect.poll(() => state.quoteBodies.at(-1)?.media_asset_id).toBe('asset-photo-2');
});


test('stable inputs do not repeatedly request quotes', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption('Прогулка');
  await expect(page.getByRole('button', { name: /Создать фото/ })).toBeEnabled();
  const before = state.quoteBodies.length;
  await page.waitForTimeout(500);
  expect(state.quoteBodies.length).toBe(before);
  expect(state.errors).toEqual([]);
});

test('media ingestion continues polling until the private photo can be previewed', async ({ page }) => {
  const state = await setup(page, { delayedMedia: true });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption('Прогулка');
  await page.getByRole('button', { name: /Создать фото/ }).click();
  await expect(page.getByText(/Состояние: сохраняем результат/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Оживить это фото/ })).toBeEnabled({ timeout: 12000 });
  expect(state.videoRuns).toBe(0);
  expect(state.workflowReads).toBeGreaterThanOrEqual(3);
});

test('a hidden template still resumes its owned immutable workflow', async ({ page }) => {
  const state = await setup(page, { hiddenTemplate: true });
  await expect(page.getByRole('heading', { name: 'Подготовить фото' })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`workflow=${RUN_ID}`));
  expect(state.workflowCreates).toBe(0);
  expect(state.errors).toEqual([]);
});

test('the chosen photo preview matches the exact asset sent for animation', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption('Прогулка');
  await page.getByRole('button', { name: /Создать фото/ }).click();
  await page.getByRole('radio', { name: /Вариант 2/ }).click();
  await expect(page.getByAltText('Готовое фото для оживления')).toHaveAttribute('src', /photo-owned-2.jpg/);
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  expect(state.runBodies.at(-1).body.media_asset_id).toBe('asset-photo-2');
  expect(state.videoRuns).toBe(1);
});


async function prepareWorkflowPhoto(page) {
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption('Прогулка');
  await page.getByRole('button', { name: /Создать фото/ }).click();
}

test('quote outage can be retried without editing private inputs', async ({ page }) => {
  const state = await setup(page, { quoteFailsOnce: true });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай').selectOption('Прогулка');
  await expect(page.getByRole('button', { name: /Создать фото/ })).toBeDisabled();
  await page.getByRole('button', { name: 'Обновить стоимость' }).click();
  await expect(page.getByRole('button', { name: /Создать фото.*25/ })).toBeEnabled();
  expect(state.runBodies).toHaveLength(0);
});

test('failed attempt refreshes quote before separate paid retry consent', async ({ page }) => {
  const state = await setup(page, { failPhoto: true });
  let releaseRetryQuote;
  const retryQuoteGate = new Promise((resolve) => { releaseRetryQuote = resolve; });
  let retryQuoteRequested = false;
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/prepare_photo/quote`, async (route) => {
    if (state.photoRuns > 0) {
      retryQuoteRequested = true;
      await retryQuoteGate;
    }
    await route.fallback();
  });

  try {
    await prepareWorkflowPhoto(page);
    // A disabled terminal-state button can render before React's quote effect.
    // Observe the actual request, then hold its response to verify the pay gate.
    await expect.poll(() => retryQuoteRequested).toBe(true);
    const photo = page.locator('[data-step="prepare_photo"]');
    await expect(photo.getByRole('button', { name: 'Считаю стоимость…' })).toBeDisabled();
    expect(state.photoRuns).toBe(1);
    await expect(photo.getByRole('checkbox', { name: /Подтверждаю новую оплату/ })).toHaveCount(0);

    releaseRetryQuote();
    await expect.poll(() => state.photoQuotes).toBeGreaterThan(1);
    await expect(photo.getByRole('button', { name: /Повторить фото.*25/ })).toBeDisabled();
    await expect(photo.getByRole('checkbox', { name: /Подтверждаю новую оплату/ })).not.toBeChecked();
    expect(state.photoRuns).toBe(1);
    await photo.getByRole('checkbox', { name: /Подтверждаю новую оплату/ }).check();
    await photo.getByRole('button', { name: /Повторить фото/ }).click();
    await expect.poll(() => state.photoRuns).toBe(2);
    expect(state.runBodies[1].body.retry).toBe(true);
    expect(state.runBodies[1].key).not.toBe(state.runBodies[0].key);
  } finally {
    releaseRetryQuote();
  }
});

test('changed retry price is visible and has a separate consent gate', async ({ page }) => {
  const state = await setup(page, { failPhoto: true, retryQuoteCost: '31.00' });
  await prepareWorkflowPhoto(page);
  await expect(page.getByText(/Цена изменилась: было 25 ROX, сейчас 31 ROX/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить фото.*31/ })).toBeDisabled();
  expect(state.photoRuns).toBe(1);
  await page.getByRole('checkbox', { name: /Подтверждаю новую оплату/ }).check();
  await page.getByRole('button', { name: /Повторить фото.*31/ }).click();
  await expect.poll(() => state.photoRuns).toBe(2);
});

test('unaccepted ambiguous video can replay the exact original command safely', async ({ page }) => {
  const state = await setup(page, { ambiguousVideoRun: true });
  await prepareWorkflowPhoto(page);
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  await page.getByRole('button', { name: 'Повторить тот же запрос' }).click();
  await expect(page.getByRole('button', { name: 'Видео готово', exact: true })).toBeVisible();
  expect(state.runBodies[2]).toEqual(state.runBodies[1]);
});

test('unresolved video command identity survives reload without storing private form data', async ({ page }) => {
  const state = await setup(page, { ambiguousVideoRun: true });
  await prepareWorkflowPhoto(page);
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  await expect(page.getByRole('button', { name: 'Повторить тот же запрос' })).toBeVisible();
  const oldKey = state.runBodies[1].key;
  const stored = await page.evaluate(() => JSON.stringify(sessionStorage));
  expect(stored).toContain(oldKey);
  expect(stored).not.toContain('media_asset_id');
  expect(stored).not.toContain('quoted_cost_rox');
  expect(stored).not.toContain('values');
  expect(stored).not.toContain('photo-input.jpg');
  expect(stored).not.toContain('query_id=');
  await page.reload();
  await expect(page.getByRole('button', { name: /Оживить это фото/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Повторить тот же запрос' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Проверить статус' })).toBeVisible();
  expect(state.runBodies).toHaveLength(2);
  expect(state.runBodies[1].key).toBe(oldKey);
});

test('reload preserves only accepted price metadata for a fresh failed-video retry quote', async ({ page }) => {
  const state = await setup(page, { failVideo: true, retryVideoQuoteCost: '31.00' });
  await prepareWorkflowPhoto(page);
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  await expect(page.getByText(/Цена изменилась: было 12 ROX, сейчас 31 ROX/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить видео.*31/ })).toBeDisabled();
  const storedBeforeReload = await page.evaluate(() => JSON.stringify(sessionStorage));
  expect(storedBeforeReload).toContain('12');
  expect(storedBeforeReload).not.toContain('media_asset_id');
  expect(storedBeforeReload).not.toContain('quoted_cost_rox');
  await page.reload();
  await expect(page.getByText(/Цена изменилась: было 12 ROX, сейчас 31 ROX/)).toBeVisible();
  await expect(page.getByRole('button', { name: /Повторить видео.*31/ })).toBeDisabled();
  await page.locator('[data-step="animate_photo"]').getByRole('checkbox', { name: /Подтверждаю новую оплату/ }).check();
  await page.getByRole('button', { name: /Повторить видео.*31/ }).click();
  await expect.poll(() => state.videoRuns).toBe(2);
});

test('lost run creation response reconciles v2 and never exposes the v1 run button', async ({ page }) => {
  const state = await setup(page, { lostCreate: true });
  await expect(page.getByRole('heading', { name: 'Подготовить фото', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Сгенерировать/ })).toHaveCount(0);
  expect(state.workflowCreates).toBe(1);
  expect(state.runBodies).toHaveLength(0);
});


test('delayed paid retry keeps its identity when reload still shows the old failed generation', async ({ page }) => {
  const state = await setup(page, { failVideo: true });
  await prepareWorkflowPhoto(page);
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  await expect(page.getByRole('button', { name: /Повторить видео/ })).toBeVisible();
  const oldKey = state.runBodies[1].key;
  let delayedAccepted = false;
  const delayed = [];
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}`, route => {
    const view = workflow(delayedAccepted ? 'running' : 'failed', 'ready', delayedAccepted ? 'running' : 'failed');
    view.steps[0].command_id = state.runBodies[0].key;
    view.steps[1].command_id = delayedAccepted ? delayed[0].key : oldKey;
    view.steps[1].generation_id = delayedAccepted ? '56156156-5555-4555-8555-561561565555' : VIDEO_GENERATION_ID;
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(view) });
  });
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/animate_photo/run`, route => {
    delayed.push({ key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() });
    return route.abort('failed');
  });
  await page.locator('[data-step="animate_photo"]').getByRole('checkbox', { name: /Подтверждаю новую оплату/ }).check();
  await page.getByRole('button', { name: /Повторить видео/ }).click();
  await expect.poll(() => delayed.length).toBe(1);
  await page.reload();
  await expect(page.getByRole('button', { name: /Повторить видео/ })).toBeDisabled();
  const consent = page.locator('[data-step="animate_photo"]').getByRole('checkbox', { name: /Подтверждаю новую оплату/ });
  if (await consent.count()) await consent.check();
  await expect(page.getByRole('button', { name: /Повторить видео/ })).toBeDisabled();
  const stored = await page.evaluate(() => JSON.stringify(sessionStorage));
  expect(stored).toContain(delayed[0].key);
  expect(delayed[0].key).not.toBe(oldKey);
  delayedAccepted = true;
  await page.getByRole('button', { name: 'Проверить статус' }).click();
  await expect(page.getByRole('button', { name: /Восстановить тот же запуск/ })).toHaveCount(0);
  expect(delayed).toHaveLength(1);
});

test('unaccepted photo recovers after reload by reentering private inputs with the same key', async ({ page }) => {
  await setup(page);
  const requests = [];
  let accepted = false;
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}`, route => {
    const view = workflow(accepted ? 'running' : 'created', accepted ? 'running' : 'pending', 'pending');
    view.steps[0].command_id = accepted ? requests[1].key : null;
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(view) });
  });
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/prepare_photo/run`, route => {
    requests.push({ key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() });
    if (requests.length === 1) return route.abort('failed');
    accepted = true;
    const view = workflow('running', 'running', 'pending');
    view.steps[0].command_id = requests[1].key;
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(view) });
  });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай', { exact: true }).selectOption('Праздник');
  await page.getByLabel('Личная надпись').fill('Секретное слово');
  await page.getByRole('button', { name: /Создать фото.*25/ }).click();
  await expect(page.getByRole('button', { name: 'Повторить тот же запрос' })).toBeVisible();
  await page.reload();
  await expect(page.locator('[data-slot-id="person_photo"] input[type=file]')).toBeEnabled();
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай', { exact: true }).selectOption('Прогулка');
  await page.getByLabel('Личная надпись').fill('Новое приватное значение');
  await page.getByRole('checkbox', { name: /Подтверждаю восстановление запуска/ }).check();
  await page.getByRole('button', { name: /Восстановить тот же запуск.*25/ }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].key).toBe(requests[0].key);
  expect(requests[1].body.values).not.toEqual(requests[0].body.values);
  const stored = await page.evaluate(() => JSON.stringify(sessionStorage));
  for (const forbidden of ['image_inputs', 'photo-input.jpg', 'Прогулка', 'Праздник', 'Секретное слово', 'Новое приватное значение', 'query_id=']) expect(stored).not.toContain(forbidden);
});

test('price rejection refreshes consent without losing an unresolved command identity', async ({ page }) => {
  await setup(page);
  let cost = '25.00';
  const requests = [];
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/prepare_photo/quote`, route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ cost_rox: cost, retail_cost_rox: cost, admin_free: false }) }));
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/prepare_photo/run`, route => {
    requests.push({ key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() });
    if (requests.length === 1) {
      cost = '31.00';
      return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Price changed; confirm current quote' }) });
    }
    const view = workflow('running', 'running', 'pending');
    view.steps[0].command_id = requests[1].key;
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(view) });
  });
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай', { exact: true }).selectOption('Праздник');
  await page.getByRole('button', { name: /Создать фото.*25/ }).click();
  const restore = page.getByRole('button', { name: /Восстановить тот же запуск.*31/ });
  await expect(restore).toBeDisabled();
  expect(requests).toHaveLength(1);
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).toContain(requests[0].key);
  await page.getByRole('checkbox', { name: /Подтверждаю восстановление запуска/ }).check();
  await restore.click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].key).toBe(requests[0].key);
  expect(requests[1].body.quoted_cost_rox).toBe('31.00');
});

test('storage fails closed before any new paid step is submitted', async ({ page }) => {
  const state = await setup(page);
  await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
  await page.getByLabel('Случай', { exact: true }).selectOption('Праздник');
  await page.evaluate(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (String(key).startsWith('roxy:trend-operation:')) throw new DOMException('Synthetic storage quota', 'QuotaExceededError');
      return original.call(this, key, value);
    };
  });
  await page.getByRole('button', { name: /Создать фото.*25/ }).click();
  await expect(page.getByRole('alert').filter({ hasText: /сохранить.*запуск/i })).toBeVisible();
  expect(state.runBodies).toHaveLength(0);
});


for (const kind of ['photo', 'video']) {
  test(`each consecutive failed ${kind} attempt requotes and resets paid consent`, async ({ page }) => {
    const state = await setup(page);
    if (kind === 'video') await prepareWorkflowPhoto(page);
    const stepId = kind === 'photo' ? 'prepare_photo' : 'animate_photo';
    const requests = [];
    let quoteCount = 0;
    let lastReceipt = null;
    const view = () => {
      const result = workflow('failed', kind === 'photo' ? 'failed' : 'ready', kind === 'video' ? 'failed' : 'pending');
      if (kind === 'video') result.steps[0].command_id = state.runBodies[0].key;
      const step = result.steps[kind === 'photo' ? 0 : 1];
      step.generation_id = `56156156-6666-4666-8666-${String(requests.length).padStart(12, '0')}`;
      step.command_id = lastReceipt;
      step.attempts = requests.length;
      return result;
    };
    await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/${stepId}/quote`, route => {
      quoteCount += 1;
      const cost = requests.length >= 2 ? '31.00' : '25.00';
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ cost_rox: cost, retail_cost_rox: cost, admin_free: false }) });
    });
    await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/${stepId}/run`, route => {
      requests.push(route.request().postDataJSON());
      lastReceipt = route.request().headers()['idempotency-key'];
      return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(view()) });
    });
    await page.route(`**/api/v1/trends/workflows/${RUN_ID}`, async route => {
      if (!requests.length) return route.fallback();
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(view()) });
    });
    if (kind === 'photo') {
      await page.locator('[data-slot-id="person_photo"] input[type=file]').setInputFiles(imageFile);
      await page.getByLabel('Случай').selectOption('Прогулка');
    }
    const stage = page.locator(`[data-step="${stepId}"]`);
    await stage.getByRole('button', { name: kind === 'photo' ? /Создать фото/ : /Оживить это фото/ }).click();
    const consent = stage.getByRole('checkbox', { name: /Подтверждаю новую оплату/ });
    await expect(consent).not.toBeChecked();
    await consent.check();
    await stage.getByRole('button', { name: /Повторить/ }).click();
    await expect.poll(() => requests.length).toBe(2);
    await expect(stage.getByRole('checkbox', { name: /Подтверждаю новую оплату/ })).not.toBeChecked();
    await expect(stage.getByRole('button', { name: /Повторить.*31/ })).toBeDisabled();
    expect(quoteCount).toBeGreaterThanOrEqual(2);
    expect(requests).toHaveLength(2);
  });
}

test('personalized video can reenter private fields after an unaccepted request and reload', async ({ page }) => {
  const state = await setup(page);
  await prepareWorkflowPhoto(page);
  await expect(page.getByRole('button', { name: /Оживить это фото/ })).toBeEnabled();
  const requests = [];
  const current = () => {
    const view = workflow(requests.length > 1 ? 'running' : 'step1_ready', 'ready', requests.length > 1 ? 'running' : 'pending');
    view.steps[0].command_id = state.runBodies[0].key;
    view.steps[1].inputs = [{ id: 'motion', label: 'Движение', type: 'text', required: true, order: 0 }];
    if (requests.length > 1) {
      view.steps[1].command_id = requests[1].key;
      view.steps[1].generation_id = VIDEO_GENERATION_ID;
    }
    return view;
  };
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}`, route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(current()) }));
  await page.route(`**/api/v1/trends/workflows/${RUN_ID}/steps/animate_photo/run`, route => {
    requests.push({ key: route.request().headers()['idempotency-key'], body: route.request().postDataJSON() });
    if (requests.length === 1) return route.abort('failed');
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(current()) });
  });
  await page.reload();
  await page.getByLabel('Движение').fill('Мой приватный танец');
  await page.getByRole('button', { name: /Оживить это фото/ }).click();
  await expect(page.getByRole('button', { name: 'Повторить тот же запрос' })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Движение')).toBeEnabled();
  await page.getByLabel('Движение').fill('Другое приватное движение');
  await page.getByRole('checkbox', { name: /Подтверждаю восстановление запуска/ }).check();
  await page.getByRole('button', { name: /Восстановить тот же запуск/ }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].key).toBe(requests[0].key);
  expect(requests[1].body.values.motion).toBe('Другое приватное движение');
  const stored = await page.evaluate(() => JSON.stringify(sessionStorage));
  expect(stored).not.toContain('приватн');
});
