import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('admin can change the Neironych balance alert policy after MFA step-up', async ({ page }) => {
  const adminRoot = new URL('../../../app/web/admin_app/', import.meta.url);
  let policy = { enabled: true, threshold_rub: '1000.00', revision: 1 };
  let verified = false;
  const writes = [];
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'test-admin-init' } }; });
  await page.route('https://telegram.org/**', (route) => route.fulfill({ body: '' }));
  await page.route('http://127.0.0.1:3018/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });
    if (path === '/admin-app/control.html') return route.fulfill({
      contentType: 'text/html', body: readFileSync(new URL('control.html', adminRoot), 'utf8'),
    });
    if (path === '/admin-app/control.js') return route.fulfill({
      contentType: 'application/javascript', body: readFileSync(new URL('control.js', adminRoot), 'utf8'),
    });
    if (path.endsWith('.css')) return route.fulfill({
      contentType: 'text/css', body: readFileSync(new URL(path.split('/').pop(), adminRoot), 'utf8'),
    });
    if (path === '/api/v1/admin/auth/login') return json({ token: 'test-token', mfa_verified: true });
    if (path === '/api/v1/admin/auth/me') return json({ role: 'admin', is_active: true, telegram_id: 123 });
    if (path === '/api/v1/admin/dashboard') return json({});
    if (path === '/api/v1/admin/runtime') return json({
      neironych_balance_alert: policy,
      generation_provider_routes: { revision: 1, routes: {}, options: {} },
    });
    if (path === '/api/v1/admin/auth/step-up') {
      verified = true;
      return json({ step_up_until: '2099-01-01T00:00:00Z' });
    }
    if (path === '/api/v1/admin/runtime/neironych-balance-alert') {
      writes.push({ body: request.postDataJSON(), headers: request.headers() });
      if (!verified) return json({ detail: 'Fresh MFA step-up required' }, 403);
      policy = {
        enabled: request.postDataJSON().enabled,
        threshold_rub: request.postDataJSON().threshold_rub,
        revision: policy.revision + 1,
      };
      return json(policy);
    }
    return json({ detail: `Unexpected request: ${path}` }, 404);
  });

  await page.goto('http://127.0.0.1:3018/admin-app/control.html');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByRole('button', { name: 'Настройки', exact: true }).click();
  await page.getByRole('button', { name: 'Алерт Нейроныча', exact: true }).click();
  await expect(page.locator('select[name="enabled"]')).toHaveValue('true');
  await page.locator('select[name="enabled"]').selectOption('false');
  await page.locator('input[name="threshold_rub"]').fill('750.25');
  await page.getByRole('button', { name: 'Сохранить алерт', exact: true }).click();
  await expect(page.locator('#controlStepDialog')).toBeVisible();
  await page.locator('#controlStepOtp').fill('123456');
  await page.locator('#controlStepVerify').click();
  await expect(page.locator('#controlFormDialog')).not.toBeVisible();

  expect(writes).toHaveLength(1);
  expect(writes[0].body).toEqual({
    enabled: false, threshold_rub: '750.25', expected_revision: 1,
  });
  expect(writes[0].headers['x-admin-confirm']).toBe('confirmed');
  expect(writes[0].headers['idempotency-key']).toBeTruthy();
  expect(errors).toEqual([]);
});
