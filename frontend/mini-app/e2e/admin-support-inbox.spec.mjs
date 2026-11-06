import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

const ticketId = '11111111-1111-4111-8111-111111111111';
const oldId = '22222222-2222-4222-8222-222222222222';
const otherId = '33333333-3333-4333-8333-333333333333';
const adminRoot = new URL('../../../app/web/admin_app/', import.meta.url);

async function fixture(page, mode, options = {}) {
  const apiBase = mode === 'main' ? '/api/v1/admin/support/tickets' : '/api/v1/admin/control/tickets';
  const url = mode === 'main' ? '/admin-app/' : '/admin-app/control.html';
  const reads = [];
  const writes = [];
  const pageErrors = [];
  const unexpectedRequests = [];
  let ticket = {
    id: ticketId, user_id: 'user-1', topic: 'Видео не скачивается', status: options.closed ? 'closed' : 'open',
    priority: 'normal', assigned_admin_id: null, updated_at: '2026-11-06T00:00:00Z',
    user: { id: 'user-1', username: 'support_customer', telegram_id: 123, first_name: 'Ирина', last_name: '' },
    needs_reply: true, last_message: { body: 'Последнее сообщение пользователя', is_admin: false },
    messages: [{ id: 'latest', body: 'Последнее сообщение пользователя', is_admin: false, created_at: '2026-11-06T00:00:00Z' }],
    messages_total: 101, messages_has_more: true, messages_before: oldId,
  };
  let failures = options.transportFailure ? 1 : 0;
  let verified = false;
  let revoked = false;
  let releaseReply;
  const replyGate = new Promise((resolve) => { releaseReply = resolve; });
  let releaseOther;
  const otherGate = new Promise((resolve) => { releaseOther = resolve; });
  let otherReads = 0;
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('dialog', (dialog) => dialog.accept());
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'test-admin-init' } }; });
  await page.route('https://telegram.org/**', (route) => route.fulfill({ body: '' }));
  await page.route('http://127.0.0.1:3018/**', async (route) => {
    const request = route.request();
    const parsed = new URL(request.url());
    const path = parsed.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path.startsWith('/admin-app/')) {
      const filename = path.split('/').pop() || 'index.html';
      const contentType = filename.endsWith('.css') ? 'text/css' : filename.endsWith('.js') ? 'application/javascript' : 'text/html';
      return route.fulfill({ contentType, body: readFileSync(new URL(filename, adminRoot), 'utf8') });
    }
    if (path === '/api/v1/admin/auth/login') return json({ token: 'test-token', mfa_verified: true });
    if (path === '/api/v1/admin/auth/me') return json({
      role: options.readonly ? 'auditor' : 'owner', is_active: true, telegram_id: 123, username: 'operator',
      permissions: options.readonly ? ['support.read'] : ['*'],
    });
    if (path === '/api/v1/admin/dashboard') return json({});
    if (path === '/api/v1/admin/control/operations') return json({ items: [{ id: 'operation-1', provider: 'test', status: 'failed', cost_credits: 10 }] });
    if (path === '/api/v1/admin/control/operations/operation-1/refund') {
      writes.push({ path, body: request.postDataJSON(), headers: request.headers() });
      return json({ operation_id: 'operation-1', status: options.refundStatus, refunded_credits: options.refundStatus === 'no_charge' ? '0' : '10' });
    }
    if (path === '/api/v1/admin/security/overview') return json({});
    if (path === '/api/v1/admin/audit') return json({ items: [] });
    if (path === '/api/v1/admin/security/sessions') return json({ items: revoked ? [] : [{ id: 'session-1', admin_id: 'admin-1', mfa_verified: true }] });
    if (path === '/api/v1/admin/auth/step-up') { verified = true; return json({ step_up_until: '2099-01-01T00:00:00Z' }); }
    if (path === '/api/v1/admin/security/sessions/session-1' && request.method() === 'DELETE') {
      writes.push({ path, body: request.postDataJSON(), headers: request.headers() });
      if (!verified) return json({ detail: 'Fresh MFA step-up required' }, 403);
      revoked = true;
      return json({ id: 'session-1', status: 'revoked' });
    }
    if (path === apiBase && request.method() === 'GET') {
      reads.push({ path, query: Object.fromEntries(parsed.searchParams) });
      const offset = Number(parsed.searchParams.get('offset') || 0);
      return json({
        items: [{ ...ticket, topic: offset ? 'Обращение со второй страницы' : ticket.topic },
          ...(options.secondTicket ? [{ ...ticket, id: otherId, topic: 'Другое обращение' }] : [])],
        total: 51, limit: 50, offset, has_more: offset === 0,
      });
    }
    if (path === apiBase + '/' + otherId && request.method() === 'GET') {
      reads.push({ path, query: Object.fromEntries(parsed.searchParams) });
      if (options.delayOther && otherReads++ === 0) await otherGate;
      return json({ ...ticket, id: otherId, topic: 'Другое обращение', messages_has_more: false, messages_before: null,
        messages: [{ id: 'other-message', body: 'Сообщение другого пользователя', is_admin: false, created_at: '2026-11-06T00:00:00Z' }] });
    }
    if (path === apiBase + '/' + ticketId && request.method() === 'GET') {
      reads.push({ path, query: Object.fromEntries(parsed.searchParams) });
      if (parsed.searchParams.has('before')) return json({
        ...ticket, messages: [{ id: oldId, body: 'Первое сообщение в истории', is_admin: false, created_at: '2026-01-01T00:00:00Z' }],
        messages_has_more: false, messages_before: null,
      });
      return json(ticket);
    }
    if (path.startsWith(apiBase + '/' + ticketId + '/') && request.method() !== 'GET') {
      writes.push({ path, body: request.postDataJSON(), headers: request.headers() });
      if (path.endsWith('/messages') || path.endsWith('/reply')) {
        if (failures > 0) { failures--; return route.abort('failed'); }
        if (options.delayReply) await replyGate;
        ticket = { ...ticket, messages: [...ticket.messages, { id: 'reply-1', body: request.postDataJSON().body,
          is_admin: true, created_at: '2026-11-06T01:00:00Z', delivery_status: 'pending', delivery_attempts: 0 }] };
        return json({ message_id: 'reply-1', outbox_id: 'outbox-1', delivery_status: 'pending', ticket_status: ticket.status, idempotency_replayed: writes.length > 1 });
      }
      if (path.endsWith('/status') || path.endsWith('/update')) {
        ticket = { ...ticket, status: request.postDataJSON().status };
        return json(ticket);
      }
    }
    unexpectedRequests.push(path);
    return json({ detail: 'Unexpected request: ' + path }, 404);
  });
  await page.goto('http://127.0.0.1:3018' + url + (options.deepLink ? '?support_ticket=' + ticketId : ''));
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.locator(mode === 'main' ? '#authView' : '#controlAuth')).not.toBeVisible();
  if (!options.deepLink) await (mode === 'main' ? page.locator('[data-view="support"]') : page.getByRole('button', { name: 'Поддержка', exact: true })).click();
  return { reads, writes, pageErrors, unexpectedRequests, releaseReply, releaseOther };
}

for (const mode of ['main', 'control']) {
  test(mode + ': support search and pages expose existing tickets', async ({ page }) => {
    const ctx = await fixture(page, mode);
    await expect(page.getByText('@support_customer', { exact: false }).first()).toBeVisible();
    await page.getByRole('button', { name: 'Следующая страница', exact: true }).click();
    await expect(page.getByText('Обращение со второй страницы', { exact: true })).toBeVisible();
    expect(ctx.reads.at(-1).query.offset).toBe('50');
    await page.getByLabel('Поиск обращений', { exact: true }).fill('support_customer');
    await page.getByRole('button', { name: 'Найти', exact: true }).click();
    await expect.poll(() => ctx.reads.at(-1).query.q).toBe('support_customer');
    expect(ctx.reads.at(-1).query.offset).toBe('0');
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });

  test(mode + ': deep link, older messages and safe reply retry', async ({ page }) => {
    const ctx = await fixture(page, mode, { deepLink: true, transportFailure: true });
    await expect(page.getByText('Последнее сообщение пользователя', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Загрузить предыдущие сообщения', exact: true }).click();
    await expect(page.getByText('Первое сообщение в истории', { exact: true })).toBeVisible();
    await expect(page.getByText('Последнее сообщение пользователя', { exact: true })).toBeVisible();
    await page.getByLabel('Ответ пользователю', { exact: true }).fill('Поможем сохранить видео');
    await page.getByRole('button', { name: 'Отправить ответ', exact: true }).click();
    await expect(page.getByLabel('Ответ пользователю', { exact: true })).toHaveValue('Поможем сохранить видео');
    await expect(page.getByRole('button', { name: 'Отправить ответ', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Отправить ответ', exact: true }).click();
    await expect(page.getByText('Поможем сохранить видео', { exact: true })).toBeVisible();
    await expect(page.getByText('В очереди отправки', { exact: true })).toBeVisible();
    const replies = ctx.writes.filter((w) => w.body.body);
    expect(replies).toHaveLength(2);
    expect(replies[0].headers['idempotency-key']).toBeTruthy();
    expect(replies[1].headers['idempotency-key']).toBe(replies[0].headers['idempotency-key']);
    expect(replies[1].headers['x-admin-confirm']).toBe('true');
    await expect(page.getByLabel('Ответ пользователю', { exact: true })).toHaveValue('');
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });

  test(mode + ': closed conversations reopen and remain usable on mobile', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const ctx = await fixture(page, mode, { deepLink: true, closed: true });
    await page.getByRole('button', { name: 'Открыть обращение заново', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Отправить ответ', exact: true })).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath('support-inbox-mobile.png'), fullPage: true });
    expect(ctx.writes.at(-1).body.status).toBe('open');
    expect(ctx.writes.at(-1).headers['idempotency-key']).toBeTruthy();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });

  test(mode + ': read-only operator cannot send or change status', async ({ page }) => {
    const ctx = await fixture(page, mode, { deepLink: true, readonly: true });
    await expect(page.getByText('Последнее сообщение пользователя', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Отправить ответ', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Сохранить статус', exact: true })).toHaveCount(0);
    expect(ctx.writes).toEqual([]);
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });
}

test('session revocation requires a reason and MFA confirmation', async ({ page }) => {
  const ctx = await fixture(page, 'main');
  await page.locator('[data-view="security"]').click();
  await page.getByRole('button', { name: 'Отозвать', exact: true }).click();
  await expect(page.getByLabel('Причина отзыва', { exact: true })).toBeVisible();
  await page.getByLabel('Причина отзыва', { exact: true }).fill('Сессия больше не нужна');
  await page.locator('#formSubmit').click();
  await expect(page.locator('#stepUpDialog')).toBeVisible();
  await page.locator('#stepUpOtp').fill('123456');
  await page.locator('#stepUpVerify').click();
  await page.locator('#stepUpExecute').click();
  await expect(page.locator('#stepUpDialog')).not.toBeVisible();
  const revokes = ctx.writes.filter((w) => w.path.endsWith('/session-1'));
  expect(revokes).toHaveLength(2);
  expect(revokes.every((w) => w.body.reason === 'Сессия больше не нужна')).toBeTruthy();
  await expect(page.getByRole('button', { name: 'Отозвать', exact: true })).toHaveCount(0);
  expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
});

for (const mode of ['main', 'control']) {
  test(mode + ': pending reply preserves new draft and blocks duplicate after refresh', async ({ page }) => {
    const ctx = await fixture(page, mode, { deepLink: true, delayReply: true });
    const draft = page.getByLabel('Ответ пользователю', { exact: true });
    await draft.fill('Первый ответ');
    await page.getByRole('button', { name: 'Отправить ответ', exact: true }).click();
    await expect.poll(() => ctx.writes.length).toBe(1);
    await draft.fill('Следующий ответ, ещё не отправлен');
    await page.getByRole('button', { name: 'Обновить переписку', exact: true }).click();
    await expect(draft).toHaveValue('Следующий ответ, ещё не отправлен');
    await expect(page.getByRole('button', { name: 'Отправить ответ', exact: true })).toBeDisabled();
    ctx.releaseReply();
    await expect(page.getByText('Первый ответ', { exact: true })).toBeVisible();
    await expect(draft).toHaveValue('Следующий ответ, ещё не отправлен');
    await expect(page.getByRole('button', { name: 'Отправить ответ', exact: true })).toBeEnabled();
    expect(ctx.writes).toHaveLength(1);
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });

  test(mode + ': late reply never reopens a conversation after returning to queue', async ({ page }) => {
    const ctx = await fixture(page, mode, { deepLink: true, delayReply: true });
    await page.getByLabel('Ответ пользователю', { exact: true }).fill('Ответ после задержки');
    await page.getByRole('button', { name: 'Отправить ответ', exact: true }).click();
    await expect.poll(() => ctx.writes.length).toBe(1);
    await page.getByRole('button', { name: '← К очереди', exact: true }).click();
    await expect(page.getByLabel('Поиск обращений', { exact: true })).toBeVisible();
    ctx.releaseReply();
    await page.getByRole('button', { name: 'Обновить обращения', exact: true }).click();
    await expect(page.getByLabel('Поиск обращений', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Ответ пользователю', { exact: true })).toHaveCount(0);
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });

  test(mode + ': concurrent opening never mixes two users conversations', async ({ page }) => {
    const ctx = await fixture(page, mode, { deepLink: true, secondTicket: true, delayOther: true });
    await expect(page.getByText('Последнее сообщение пользователя', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '← К очереди', exact: true }).click();
    await page.locator('.support-ticket').filter({ hasText: 'Другое обращение' }).getByRole('button', { name: 'Открыть', exact: true }).click();
    await expect.poll(() => ctx.reads.filter((r) => r.path.endsWith(otherId)).length).toBe(1);
    await page.locator(mode === 'main' ? '#refreshButton' : '#controlRefresh').click();
    await expect(page.getByText('Сообщение другого пользователя', { exact: true })).toBeVisible();
    await expect(page.getByText('Последнее сообщение пользователя', { exact: true })).toHaveCount(0);
    ctx.releaseOther();
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });
}

for (const [status, notice] of [
  ['already_refunded', 'Возврат уже был выполнен'],
  ['no_charge', 'Списания по операции нет — возврат не требуется'],
]) {
  test('operation refund displays ' + status + ' without claiming a new credit', async ({ page }) => {
    const ctx = await fixture(page, 'control', { refundStatus: status });
    await page.getByRole('button', { name: 'Операции', exact: true }).click();
    await page.getByRole('button', { name: 'Вернуть', exact: true }).click();
    await page.getByLabel('Причина', { exact: true }).fill('Проверка возврата по обращению');
    await page.locator('#controlFormSubmit').click();
    await page.locator('#controlStepOtp').fill('123456');
    await page.locator('#controlStepVerify').click();
    await expect(page.locator('#controlToast')).toHaveText(notice);
    expect(ctx.writes.filter((w) => w.path.endsWith('/refund'))).toHaveLength(1);
    expect(ctx.pageErrors).toEqual([]);
    expect(ctx.unexpectedRequests).toEqual([]);
  });
}
