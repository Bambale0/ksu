import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

// Exercise the real standalone admin form while keeping provider requests mocked.
test('admin provider routes preserve revision and idempotency through MFA retry', async ({ page }) => {
  const adminRoot = new URL('../../../app/web/admin_app/', import.meta.url);
  const routes = { 'seedance-2.0': ['neironych', 'kie'], 'seedance-2.5': ['neironych', 'kie'], 'nano-banana-pro': ['neironych', 'nexus'] };
  const options = Object.fromEntries(Object.entries(routes).map(([model, route]) => [model, [route, [route[0]], [route[1]]]]));
  let revision = 7;
  let verified = false;
  const writes = [];
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'test-admin-init' } }; });
  await page.route('https://telegram.org/**', (route) => route.fulfill({ body: '' }));
  await page.route('http://127.0.0.1:3017/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/admin-app/control.html') return route.fulfill({ contentType: 'text/html', body: readFileSync(new URL('control.html', adminRoot), 'utf8') });
    if (path === '/admin-app/control.js') return route.fulfill({ contentType: 'application/javascript', body: readFileSync(new URL('control.js', adminRoot), 'utf8') });
    if (path.endsWith('.css')) return route.fulfill({ contentType: 'text/css', body: readFileSync(new URL(path.split('/').pop(), adminRoot), 'utf8') });
    if (path === '/api/v1/admin/auth/login') return json({ token: 'test-token', mfa_verified: true });
    if (path === '/api/v1/admin/auth/me') return json({ role: 'admin', is_active: true, telegram_id: 123 });
    if (path === '/api/v1/admin/dashboard') return json({});
    if (path === '/api/v1/admin/runtime') return json({ generation_provider_routes: { revision, routes, options } });
    if (path === '/api/v1/admin/auth/step-up') {
      verified = true;
      return json({ step_up_until: '2099-01-01T00:00:00Z' });
    }
    if (path === '/api/v1/admin/runtime/provider-routes') {
      writes.push({ body: req.postDataJSON(), headers: req.headers() });
      if (!verified) return json({ detail: 'Fresh MFA step-up required' }, 403);
      if (writes.length > 2) return json({ detail: 'Provider routes changed; reload settings before saving' }, 422);
      Object.assign(routes, req.postDataJSON().routes);
      revision += 1;
      return json({ revision, routes });
    }
    return json({ detail: `Unexpected request: ${path}` }, 404);
  });
  await page.goto('http://127.0.0.1:3017/admin-app/control.html');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByRole('button', { name: 'Настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Провайдеры генерации', exact: true }).click();
  const nano = page.locator('select[name="nano-banana-pro"]');
  await expect(nano).toHaveValue('neironych,nexus');
  await nano.selectOption('nexus');
  await page.getByRole('button', { name: 'Сохранить маршруты', exact: true }).click();
  await expect(page.locator('#controlStepDialog')).toBeVisible();
  await page.locator('#controlStepOtp').fill('123456');
  await page.locator('#controlStepVerify').click();
  await expect(page.locator('#controlFormDialog')).not.toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[0].body).toEqual({ routes: { ...routes }, expected_revision: 7 });
  expect(writes[0].headers['idempotency-key']).toBe(writes[1].headers['idempotency-key']);
  expect(writes[1].headers['x-admin-confirm']).toBe('confirmed');
  expect(writes[1].headers.authorization).toBe('Bearer test-token');
  await page.getByRole('button', { name: 'Провайдеры генерации', exact: true }).click();
  await expect(nano).toHaveValue('nexus');
  await page.getByRole('button', { name: 'Сохранить маршруты', exact: true }).click();
  await expect(page.locator('#controlFormMessage')).toContainText('reload settings');
  await expect(page.locator('#controlFormDialog')).toBeVisible();
  expect(writes[2].body.expected_revision).toBe(8);
  expect(errors).toEqual([]);
});
