import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=pinterest-repeat&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

const sceneAnalysis = {
  scene: 'woman standing beside a stone balcony in an Italian street',
  composition: 'vertical medium-full portrait, subject slightly right of center',
  camera: 'eye-level camera, natural portrait perspective',
  pose: 'weight on right leg, left knee relaxed, torso slightly rotated',
  lighting: 'soft warm daylight from camera-left',
  environment: 'warm stone walls and narrow European street',
  wardrobe: 'light fitted top with dark straight-leg trousers',
  expression: 'calm confidence',
  gaze: 'directly into camera',
  must_preserve: ['hand placement', 'head angle', 'subject scale', 'background geometry'],
};

async function mockApi(page) {
  await installTelegram(page);
  let uploadIndex = 0;
  const runBodies = [];

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me') {
      return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100.00' });
    }
    if (path === '/api/v1/uploads/kie' && request.method() === 'POST') {
      uploadIndex += 1;
      const url = uploadIndex === 1
        ? 'https://media.example.test/scene.jpg'
        : `https://media.example.test/me-${uploadIndex - 1}.jpg`;
      return json({ url, name: uploadIndex === 1 ? 'scene.jpg' : 'me.jpg', mime_type: 'image/jpeg' }, 201);
    }
    if (path === '/api/v1/pinterest-repeat/analyze') {
      expect(request.postDataJSON()).toEqual({ scene_reference_url: 'https://media.example.test/scene.jpg' });
      await new Promise((resolve) => setTimeout(resolve, 100));
      return json({ analysis: sceneAnalysis, model: 'gemini-2.5-pro', cached: false });
    }
    if (path === '/api/v1/pinterest-repeat/quote') {
      const body = request.postDataJSON();
      const changed = body.height_cm === 180;
      if (changed) await new Promise((resolve) => setTimeout(resolve, 700));
      const cost = changed ? '18.00' : '12.00';
      return json({
        mode: 'pinterest_repeat',
        model_id: 'nano-banana-pro',
        unit_price_rox: cost,
        cost_rox: cost,
        effective_cost_rox: cost,
        retail_cost_rox: cost,
        cost_rub: cost,
        billing_seconds: null,
        admin_free: false,
      });
    }
    if (path === '/api/v1/pinterest-repeat/run' && request.method() === 'POST') {
      runBodies.push(request.postDataJSON());
      return json({
        id: 'gen-repeat-1',
        status: 'queued',
        mode: 'pinterest_repeat',
        cost_rox: '18.00',
        admin_free: false,
        idempotency_replayed: false,
      }, 202);
    }
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [], max_generation_quantity: 4 });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/prompt-tools') return json({ admin_free: false, items: [] });
    if (path === '/api/v1/trend-collections') return json({ items: [] });
    return json({ items: [] });
  });

  return { runBodies };
}

const sceneFile = {
  name: 'scene.jpg',
  mimeType: 'image/jpeg',
  buffer: Buffer.from('fake-scene-image'),
};

const identityFile = {
  name: 'me.heic',
  mimeType: 'application/octet-stream',
  buffer: Buffer.from('fake-identity-image'),
};

test('Pinterest repeat analyzes the scene and blocks stale-quote submit', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { runBodies } = await mockApi(page);
  await page.goto('/mini-app/pinterest-repeat/');

  await expect(page.getByRole('heading', { name: 'Повтори фото с Pinterest' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Референс' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Ваши ракурсы' })).toBeVisible();
  await expect(page.getByText('РЕФЕРЕНС', { exact: true })).toBeVisible();
  await expect(page.getByText('ТЫ', { exact: true })).toBeVisible();
  await expect(page.getByText('КОГО ВСТАВЛЯЕМ', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Желаемое выражение лица')).toHaveCount(0);

  await page.locator('input[type="file"]').first().setInputFiles(sceneFile);
  await expect(page.getByAltText('Референс сцены')).toBeVisible();
  await expect(page.getByText('Разбираем сцену, позу, свет и эмоцию…')).toBeVisible();

  // Once the reference upload control disappears, the first remaining file input
  // is the identity picker. Empty MIME + .heic mirrors iOS/WebView uploads.
  await page.locator('input[type="file"]').first().setInputFiles(identityFile);
  const identityPreviews = page.getByAltText('Ваш ракурс 1');
  await expect(identityPreviews).toHaveCount(2);
  await expect(identityPreviews.nth(0)).toBeVisible();
  await expect(identityPreviews.nth(1)).toBeVisible();
  await expect(page.getByText('1–5 ракурсов одного человека · сейчас 1/5')).toBeVisible();
  await expect(page.getByText('сцена, свет и поза считаны с референса')).toBeVisible();
  await expect(page.getByText('эмоция: calm confidence · взгляд: directly into camera')).toBeVisible();
  await expect(page.getByText('камера: eye-level camera, natural portrait perspective')).toBeVisible();

  const create = page.getByRole('button', { name: 'Создать →' });
  const price = page.locator('.pin-summary strong');
  await expect(price).toHaveText('12 ROX');
  await expect(create).toBeEnabled();

  await page.getByLabel('Рост').fill('180');
  await expect(price).toHaveText('Считаем…');
  await expect(create).toBeDisabled();

  // Even a programmatic click must not submit while the request no longer
  // matches the rendered quote.
  await create.evaluate((button) => button.click());
  await page.waitForTimeout(150);
  expect(runBodies).toHaveLength(0);

  await expect(price).toHaveText('18 ROX', { timeout: 3000 });
  await expect(create).toBeEnabled();

  const runRequestPromise = page.waitForRequest((request) => {
    const path = new URL(request.url()).pathname;
    return path === '/api/v1/pinterest-repeat/run' && request.method() === 'POST';
  });
  await create.click();
  const runRequest = await runRequestPromise;
  const submitted = runRequest.postDataJSON();

  expect(submitted).toEqual({
    scene_reference_url: 'https://media.example.test/scene.jpg',
    identity_reference_urls: ['https://media.example.test/me-1.jpg'],
    height_cm: 180,
    weight_kg: 55,
    scene_analysis: sceneAnalysis,
  });
  expect(runRequest.headers()['idempotency-key']).toBeTruthy();
  await expect.poll(() => runBodies.length).toBe(1);
});

test('Pinterest URL resolver is wired as an alternative scene source', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100.00' });
    if (path === '/api/v1/pinterest-repeat/resolve') {
      expect(request.postDataJSON()).toEqual({ url: 'https://pin.it/example' });
      return json({
        source_url: 'https://www.pinterest.com/pin/123/',
        reference_url: 'https://media.example.test/references/pinterest-scene.jpg',
      });
    }
    if (path === '/api/v1/pinterest-repeat/analyze') {
      expect(request.postDataJSON()).toEqual({
        scene_reference_url: 'https://media.example.test/references/pinterest-scene.jpg',
      });
      return json({ analysis: sceneAnalysis, model: 'gemini-2.5-pro', cached: true });
    }
    return json({ items: [] });
  });

  await page.goto('/mini-app/pinterest-repeat/');
  await page.getByPlaceholder('ссылка на пин с Pinterest').fill('https://pin.it/example');
  await page.getByRole('button', { name: 'Загрузить' }).click();
  await expect(page.getByAltText('Референс сцены')).toHaveAttribute(
    'src',
    'https://media.example.test/references/pinterest-scene.jpg',
  );
  await expect(page.getByText('https://www.pinterest.com/pin/123/')).toBeVisible();
  await expect(page.getByText('эмоция: calm confidence · взгляд: directly into camera')).toBeVisible();
});

test('retry after a lost run response reuses the same Idempotency-Key', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  let uploadIndex = 0;
  const runKeys = [];

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/me') {
      return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100.00' });
    }
    if (path === '/api/v1/uploads/kie' && request.method() === 'POST') {
      uploadIndex += 1;
      return json({
        url: uploadIndex === 1 ? 'https://media.example.test/scene.jpg' : 'https://media.example.test/me.jpg',
        name: uploadIndex === 1 ? 'scene.jpg' : 'me.jpg',
        mime_type: 'image/jpeg',
      }, 201);
    }
    if (path === '/api/v1/pinterest-repeat/analyze') {
      return json({ analysis: sceneAnalysis, model: 'gemini-2.5-pro', cached: false });
    }
    if (path === '/api/v1/pinterest-repeat/quote') {
      return json({
        mode: 'pinterest_repeat',
        model_id: 'nano-banana-pro',
        unit_price_rox: '12.00',
        cost_rox: '12.00',
        effective_cost_rox: '12.00',
        retail_cost_rox: '12.00',
        cost_rub: '12.00',
        billing_seconds: null,
        admin_free: false,
      });
    }
    if (path === '/api/v1/pinterest-repeat/run' && request.method() === 'POST') {
      runKeys.push(request.headers()['idempotency-key']);
      if (runKeys.length === 1) {
        return json({ detail: 'Временная ошибка сети' }, 503);
      }
      return json({
        id: 'gen-repeat-replayed',
        status: 'queued',
        mode: 'pinterest_repeat',
        cost_rox: '12.00',
        admin_free: false,
        idempotency_replayed: true,
      }, 202);
    }
    return json({ items: [] });
  });

  await page.goto('/mini-app/pinterest-repeat/');
  await page.locator('input[type="file"]').first().setInputFiles(sceneFile);
  await page.locator('input[type="file"]').first().setInputFiles(identityFile);

  await expect(page.getByText('сцена, свет и поза считаны с референса')).toBeVisible();
  const create = page.getByRole('button', { name: 'Создать →' });
  await expect(page.locator('.pin-summary strong')).toHaveText('12 ROX');
  await create.click();
  await expect(page.locator('.pin-error')).toContainText('Временная ошибка сети');
  await expect(create).toBeEnabled();

  await create.click();
  await expect.poll(() => runKeys.length).toBe(2);
  expect(runKeys[0]).toBeTruthy();
  expect(runKeys[1]).toBe(runKeys[0]);
});
