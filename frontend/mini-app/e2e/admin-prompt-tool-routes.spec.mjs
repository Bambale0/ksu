import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const qwen = { provider: 'neironych', model: 'qwen3.8-max' };
const gpt = { provider: 'nexus', model: 'gpt-6-sol' };
const choices = [[qwen, gpt], [gpt, qwen], [qwen], [gpt]];
const origin = 'http://127.0.0.1:3017';

async function openRuntime(page, { expireFirstWrite = true } = {}) {
  const adminRoot = new URL('../../../app/web/admin_app/', import.meta.url);
  const state = {
    revision: 4, routes: { image_analysis: [qwen, gpt], video_prompt: [qwen, gpt] },
    writes: [], stepUps: [], errors: [], unexpectedRequests: [], rejectStale: false,
  };
  page.on('pageerror', (error) => state.errors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'synthetic-prompt-route-admin' } }; });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.hostname === 'telegram.org') return route.fulfill({ contentType: 'application/javascript', body: '' });
    if (url.origin !== origin) return route.abort();
    if (path === '/admin-app/control.html') return route.fulfill({ contentType: 'text/html', body: readFileSync(new URL('control.html', adminRoot), 'utf8') });
    if (path === '/admin-app/control.js') return route.fulfill({ contentType: 'application/javascript', body: readFileSync(new URL('control.js', adminRoot), 'utf8') });
    if (path.endsWith('.css')) return route.fulfill({ contentType: 'text/css', body: readFileSync(new URL(path.split('/').pop(), adminRoot), 'utf8') });
    if (path === '/api/v1/admin/auth/login') return json({ token: 'synthetic-admin-token', mfa_verified: true });
    if (path === '/api/v1/admin/auth/me') return json({ role: 'owner', is_active: true, telegram_id: 123 });
    if (path === '/api/v1/admin/dashboard') return json({});
    if (path === '/api/v1/admin/runtime') return json({
      prompt_tool_provider_routes: {
        revision: state.revision, routes: state.routes,
        options: { image_analysis: choices, video_prompt: choices },
      },
    });
    if (path === '/api/v1/admin/auth/step-up') {
      state.stepUps.push(request.postDataJSON());
      return json({ step_up_until: '2099-01-01T00:00:00Z' });
    }
    if (path === '/api/v1/admin/runtime/prompt-tool-routes') {
      state.writes.push({ body: request.postDataJSON(), headers: request.headers() });
      if (expireFirstWrite && state.writes.length === 1) return json({ detail: 'Fresh MFA step-up required' }, 403);
      if (state.rejectStale) return json({ detail: 'Prompt tool routes changed; reload settings before saving' }, 422);
      state.routes = request.postDataJSON().routes;
      state.revision += 1;
      return json({ revision: state.revision, routes: state.routes, idempotency_replayed: false });
    }
    if (path.startsWith('/api/')) state.unexpectedRequests.push(`${request.method()} ${path}`);
    return json({ detail: `Unexpected request: ${path}` }, 404);
  });
  await page.goto(`${origin}/admin-app/control.html`);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByRole('button', { name: 'Настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Анализ фото и видео', exact: true }).click();
  await expect(page.locator('#controlFormFields').getByText('Описание по фото', { exact: true })).toBeVisible();
  await expect(page.locator('#controlFormFields').getByText('Промпт по видео', { exact: true })).toBeVisible();
  return state;
}

async function verifyStepUp(page, otp = '123456') {
  await expect(page.locator('#controlStepDialog')).toBeVisible();
  await page.locator('#controlStepOtp').fill(otp);
  await page.locator('#controlStepVerify').click();
}

test('photo and video provider choices keep their revision and command identity through MFA retry', async ({ page }) => {
  const state = await openRuntime(page);
  // Wrapped select labels include option text in getByLabel; use the public
  // field names while checking the visible human labels in openRuntime.
  const photo = page.locator('select[name="image_analysis"]');
  const video = page.locator('select[name="video_prompt"]');
  await expect(photo).toHaveValue(JSON.stringify([qwen, gpt]));
  await expect(video).toHaveValue(JSON.stringify([qwen, gpt]));
  await expect(photo.locator('option')).toHaveText([
    'Нейроныч · Qwen 3.8 Max → Nexus · GPT-6 Sol',
    'Nexus · GPT-6 Sol → Нейроныч · Qwen 3.8 Max',
    'Нейроныч · Qwen 3.8 Max',
    'Nexus · GPT-6 Sol',
  ]);
  await expect(page.locator('#controlFormFields select')).toHaveCount(2);
  await photo.selectOption(JSON.stringify([gpt]));
  await video.selectOption(JSON.stringify([gpt, qwen]));
  await page.getByRole('button', { name: 'Сохранить маршруты анализа', exact: true }).click();
  await expect(page.locator('#controlStepDescription')).toContainText('новых задач');
  expect(state.writes).toHaveLength(0);
  await verifyStepUp(page);
  await expect.poll(() => state.writes.length).toBe(1);
  await verifyStepUp(page, '654321');
  await expect(page.locator('#controlFormDialog')).not.toBeVisible();
  expect(state.stepUps).toEqual([{ otp: '123456' }, { otp: '654321' }]);
  expect(state.writes).toHaveLength(2);
  const payload = {
    routes: { image_analysis: [gpt], video_prompt: [gpt, qwen] }, expected_revision: 4,
  };
  expect(state.writes[0].body).toEqual(payload);
  expect(state.writes[1].body).toEqual(payload);
  expect(state.writes[0].headers['idempotency-key']).toBeTruthy();
  expect(state.writes[1].headers['idempotency-key']).toBe(state.writes[0].headers['idempotency-key']);
  expect(state.writes[1].headers['x-admin-confirm']).toBe('confirmed');
  expect(state.writes[1].headers.authorization).toBe('Bearer synthetic-admin-token');

  await page.getByRole('button', { name: 'Анализ фото и видео', exact: true }).click();
  await expect(photo).toHaveValue(JSON.stringify([gpt]));
  await expect(video).toHaveValue(JSON.stringify([gpt, qwen]));
  await photo.selectOption(JSON.stringify([qwen]));
  state.rejectStale = true;
  await page.getByRole('button', { name: 'Сохранить маршруты анализа', exact: true }).click();
  await verifyStepUp(page);
  await expect(page.locator('#controlFormMessage')).toContainText('reload settings');
  await expect(page.locator('#controlFormDialog')).toBeVisible();
  await expect(photo).toHaveValue(JSON.stringify([qwen]));
  expect(state.writes[2].body.expected_revision).toBe(5);
  expect(state.writes[2].headers['idempotency-key']).not.toBe(state.writes[1].headers['idempotency-key']);
  expect(state.errors).toEqual([]);
  expect(state.unexpectedRequests).toEqual([]);
});

test('canceling MFA keeps the photo and video route form usable without a write', async ({ page }) => {
  const state = await openRuntime(page, { expireFirstWrite: false });
  const photo = page.locator('select[name="image_analysis"]');
  await photo.selectOption(JSON.stringify([gpt]));
  await page.getByRole('button', { name: 'Сохранить маршруты анализа', exact: true }).click();
  await expect(page.locator('#controlStepDialog')).toBeVisible();
  await page.locator('#controlStepCancel').click();
  await expect(page.locator('#controlFormMessage')).toHaveText('Подтверждение отменено');
  await expect(photo).toHaveValue(JSON.stringify([gpt]));
  expect(state.writes).toEqual([]);
  await page.getByRole('button', { name: 'Сохранить маршруты анализа', exact: true }).click();
  await verifyStepUp(page);
  await expect(page.locator('#controlFormDialog')).not.toBeVisible();
  expect(state.writes).toHaveLength(1);
  expect(state.errors).toEqual([]);
  expect(state.unexpectedRequests).toEqual([]);
});
