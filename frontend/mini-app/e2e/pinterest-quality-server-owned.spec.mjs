import { expect, test } from '@playwright/test';

const sceneAnalysis = {
  scene: 'portrait beside a stone balcony',
  composition: 'vertical medium-full portrait',
  camera: 'eye-level camera',
  pose: 'weight on right leg, torso slightly rotated',
  lighting: 'soft daylight from camera-left',
  environment: 'warm stone street',
  wardrobe: 'light top with dark trousers',
  expression: 'calm confidence',
  gaze: 'directly into camera',
  must_preserve: ['head angle', 'subject scale'],
};

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=pinterest-quality&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

test('Pinterest quality retry is server-owned and the client submits one paid generation only', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  let uploadIndex = 0;
  let runCount = 0;

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
        url: uploadIndex === 1
          ? 'https://media.example.test/scene.jpg'
          : 'https://media.example.test/me.jpg',
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
      runCount += 1;
      return json({
        id: 'gen-quality-server-owned',
        status: 'queued',
        mode: 'pinterest_repeat',
        cost_rox: '12.00',
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

  await page.goto('/mini-app/pinterest-repeat/');
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'scene.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('scene'),
  });
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'me.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('identity'),
  });

  await expect(page.getByText('сцена, свет и поза считаны с референса')).toBeVisible();
  await expect(page.locator('.pin-summary strong')).toHaveText('12 ROX');
  await page.getByRole('button', { name: 'Создать →' }).click();

  await expect.poll(() => runCount).toBe(1);
  await page.waitForTimeout(400);
  expect(runCount).toBe(1);
});
