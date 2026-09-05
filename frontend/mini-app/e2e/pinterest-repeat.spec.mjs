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

test('Pinterest repeat keeps scene and identity separate and blocks stale-quote submit', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { runBodies } = await mockApi(page);
  await page.goto('/mini-app/pinterest-repeat/');

  await expect(page.getByRole('heading', { name: 'Повтори фото с Pinterest' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Референс' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ваши ракурсы' })).toBeVisible();

  await page.locator('input[type="file"]').first().setInputFiles(sceneFile);
  await expect(page.getByAltText('Референс сцены')).toBeVisible();

  // After the reference uploader disappears, the first remaining file input is
  // the identity picker. Empty MIME + .heic mirrors iOS/WebView uploads.
  await page.locator('input[type="file"]').first().setInputFiles(identityFile);
  await expect(page.getByAltText('Ваш ракурс 1')).toBeVisible();

  const create = page.getByRole('button', { name: 'Создать' });
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
  });
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
        reference_url: 'https://i.pinimg.com/originals/aa/bb/scene.jpg',
      });
    }
    return json({ items: [] });
  });

  await page.goto('/mini-app/pinterest-repeat/');
  await page.getByPlaceholder('https://pin.it/…').fill('https://pin.it/example');
  await page.getByRole('button', { name: 'Загрузить' }).click();
  await expect(page.getByAltText('Референс сцены')).toHaveAttribute(
    'src',
    'https://i.pinimg.com/originals/aa/bb/scene.jpg',
  );
});
