import { expect, test } from '@playwright/test';

const ticketA = {
  id: '11111111-1111-4111-8111-111111111111', topic: 'Вопрос об оплате', status: 'open',
  created_at: '2026-10-24T06:00:00Z', updated_at: '2026-10-24T06:00:00Z',
  can_reply: true, can_close: true, can_reopen: false, messages: [],
};
const ticketB = { ...ticketA, id: '22222222-2222-4222-8222-222222222222', topic: 'Вопрос о генерации' };

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockSupport(page) {
  const errors = [];
  page.__supportAuditErrors = errors;
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    if (page.__supportExpected503 && message.text().includes('Failed to load resource: the server responded with a status of 503')) return;
    errors.push(message.text());
  });
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=support-audit&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } };
  });
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/support/contact') return json(route, { configured: false });
    if (path === '/api/v1/support/tickets') return json(route, { items: [ticketA, ticketB] });
    if (path === `/api/v1/support/tickets/${ticketA.id}`) return json(route, ticketA);
    if (path === `/api/v1/support/tickets/${ticketB.id}`) return json(route, ticketB);
    return json(route, { items: [] });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/mini-app/support/');
  return errors;
}

test.afterEach(async ({ page }) => {
  expect(page.__supportAuditErrors || []).toEqual([]);
});

async function holdRequest(page, path) {
  let release;
  let arrived;
  const requests = [];
  const gate = new Promise((resolve) => { release = resolve; });
  const requested = new Promise((resolve) => { arrived = resolve; });
  await page.route(`**${path}`, async (route) => {
    requests.push(route.request());
    arrived();
    const { body, status } = await gate;
    await json(route, body, status);
  });
  return {
    requested,
    requests,
    async finish(body, status = 200) {
      const response = page.waitForResponse((value) => new URL(value.url()).pathname === path);
      release({ body, status });
      await (await response).finished();
      // Give the completed response's React update two rendering frames. This
      // checks that a late response stays ignored, rather than asserting early.
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    },
  };
}

test('support keeps the latest selected conversation when an older detail request finishes last', async ({ page }) => {
  const errors = await mockSupport(page);
  const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketA.id}`);
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await delayed.requested;
  await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  await delayed.finish(ticketA);
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: ticketA.topic, exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('support reply drafts stay with their conversation when switching tickets', async ({ page }) => {
  await mockSupport(page);
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  const reply = page.getByPlaceholder('Написать ответ', { exact: true });
  await reply.fill('Уточнение только об оплате');
  await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  await expect(reply).toHaveValue('');
  await reply.fill('Уточнение только о генерации');
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await expect(page.getByRole('heading', { name: ticketA.topic, exact: true })).toBeVisible();
  await expect(reply).toHaveValue('Уточнение только об оплате');
});

test('closing a conversation invalidates an in-flight detail refresh', async ({ page }) => {
  await mockSupport(page);
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await expect(page.getByRole('heading', { name: ticketA.topic, exact: true })).toBeVisible();
  const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketA.id}`);
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await delayed.requested;
  await page.getByRole('button', { name: 'Закрыть окно', exact: true }).click();
  await delayed.finish(ticketA);
  await expect(page.getByRole('heading', { name: ticketA.topic, exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Закрыть окно', exact: true })).toHaveCount(0);
});

for (const destination of ['dismiss', 'other ticket']) {
  test(`a completed reply does not override navigation to ${destination}`, async ({ page }) => {
    await mockSupport(page);
    await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
    await page.getByPlaceholder('Написать ответ', { exact: true }).fill('Уточнение об оплате');
    const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketA.id}/messages`);
    await page.getByRole('button', { name: 'Отправить', exact: true }).click();
    await delayed.requested;
    await expect(page.getByRole('button', { name: 'Отправляю…', exact: true }).last()).toBeDisabled();
    expect(delayed.requests[0].postDataJSON()).toEqual({ message: 'Уточнение об оплате' });
    if (destination === 'dismiss') {
      await page.getByRole('button', { name: 'Закрыть окно', exact: true }).click();
    } else {
      await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
      await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
    }
    await delayed.finish({ id: 'message_new', body: 'Уточнение об оплате', author: 'user', created_at: ticketA.created_at }, 201);
    await expect(page.getByRole('button', { name: 'Создать обращение', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: ticketA.topic, exact: true })).toHaveCount(0);
    if (destination === 'other ticket') {
      await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
    }
    expect(delayed.requests).toHaveLength(1);
  });
}

test('support replaces old actions with loading feedback and retries failed details', async ({ page }) => {
  await mockSupport(page);
  page.__supportExpected503 = true;
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toBeVisible();
  const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketB.id}`);
  await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
  await delayed.requested;
  await expect(page.getByRole('status')).toContainText('Загружаем диалог…');
  await expect(page.getByRole('button', { name: 'Закрыть обращение', exact: true })).toHaveCount(0);
  await delayed.finish({ detail: 'internal support storage exception' }, 503);
  const alert = page.locator('.action-error[role="alert"]');
  await expect(alert).toContainText('Сервис временно недоступен');
  await expect(alert).not.toContainText('internal support storage exception');
  await page.unroute(`**/api/v1/support/tickets/${ticketB.id}`);
  await page.getByRole('button', { name: 'Повторить загрузку диалога', exact: true }).click();
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Закрыть обращение', exact: true })).toBeEnabled();
});

test('a stale failed detail request cannot replace the current conversation with an error', async ({ page }) => {
  await mockSupport(page);
  page.__supportExpected503 = true;
  const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketA.id}`);
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await delayed.requested;
  await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
  await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toBeVisible();
  await delayed.finish({ detail: 'internal support storage exception' }, 503);
  await expect(page.locator('.action-error[role="alert"]')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Закрыть обращение', exact: true })).toBeEnabled();
});

test('support can close and reopen the selected conversation through the existing API', async ({ page }) => {
  await mockSupport(page);
  let current = { ...ticketA };
  await page.route(`**/api/v1/support/tickets/${ticketA.id}`, (route) => json(route, current));
  await page.route(`**/api/v1/support/tickets/${ticketA.id}/close`, (route) => {
    expect(route.request().method()).toBe('POST');
    current = { ...current, status: 'closed', can_reply: false, can_close: false, can_reopen: true };
    return json(route, current);
  });
  await page.route(`**/api/v1/support/tickets/${ticketA.id}/reopen`, (route) => {
    expect(route.request().method()).toBe('POST');
    current = { ...ticketA };
    return json(route, current);
  });
  await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
  await page.getByRole('button', { name: 'Закрыть обращение', exact: true }).click();
  await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Переоткрыть', exact: true }).click();
  await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Закрыть обращение', exact: true })).toBeEnabled();
});

test('a completed new ticket does not override a subsequently selected conversation', async ({ page }) => {
  await mockSupport(page);
  await page.getByRole('textbox', { name: 'Тема', exact: true }).fill('Новый вопрос');
  await page.getByRole('textbox', { name: 'Сообщение', exact: true }).fill('Проверка новой заявки');
  const delayed = await holdRequest(page, '/api/v1/support/tickets');
  await page.getByRole('button', { name: 'Создать обращение', exact: true }).click();
  await delayed.requested;
  await expect(page.getByRole('textbox', { name: 'Сообщение', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
  await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toBeVisible();
  await delayed.finish({ ...ticketA, id: '33333333-3333-4333-8333-333333333333', topic: 'Новый вопрос' }, 201);
  await expect(page.getByRole('button', { name: 'Создать обращение', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
  expect(delayed.requests[0].postDataJSON()).toEqual({ topic: 'Новый вопрос', message: 'Проверка новой заявки' });
});

for (const action of ['close', 'reply']) {
  test(`completing ${action} refreshes its ticket if the user has navigated away and returned`, async ({ page }) => {
    await mockSupport(page);
    let detail = { ...ticketA };
    await page.route(`**/api/v1/support/tickets/${ticketA.id}`, (route) => json(route, detail));
    await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
    const delayed = await holdRequest(page, `/api/v1/support/tickets/${ticketA.id}/${action === 'close' ? 'close' : 'messages'}`);
    if (action === 'reply') await page.getByPlaceholder('Написать ответ', { exact: true }).fill('Новый ответ');
    await page.getByRole('button', { name: action === 'close' ? 'Закрыть обращение' : 'Отправить', exact: true }).click();
    await delayed.requested;
    await page.getByRole('button', { name: new RegExp(ticketB.topic) }).click();
    await expect(page.getByRole('heading', { name: ticketB.topic, exact: true })).toBeVisible();
    await page.getByRole('button', { name: new RegExp(ticketA.topic) }).click();
    await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toBeVisible();
    detail = action === 'close'
      ? { ...ticketA, status: 'closed', can_reply: false, can_close: false, can_reopen: true }
      : { ...ticketA, messages: [{ id: 'message_return', author: 'user', body: 'Новый ответ', created_at: ticketA.created_at }] };
    await delayed.finish(action === 'close' ? detail : detail.messages[0]);
    await expect(page.getByRole('button', { name: 'Создать обращение', exact: true })).toBeVisible();
    if (action === 'close') {
      await expect(page.getByRole('button', { name: 'Переоткрыть', exact: true })).toBeVisible();
      await expect(page.getByPlaceholder('Написать ответ', { exact: true })).toHaveCount(0);
    } else {
      await expect(page.locator('.transaction-list').getByText('Новый ответ', { exact: true })).toBeVisible();
    }
  });
}
