import { expect, test } from '@playwright/test';

const model = {
  id: 'audit-recovery-model', title: 'Audit Recovery Model', family: 'audit_recovery',
  media_type: 'image', operation: 'generate', price_rox: '15.00',
  ui_schema: { defaults: {}, fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }] },
};
const generation = {
  id: 'audit-generation', status: 'succeeded', model, prompt: 'Сохранённое описание',
  result_url: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/%3E',
  created_at: '2026-11-04T10:00:00Z', media_ready: true,
};

async function setup(page, options = {}) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=audit-recovery&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/telegram-web-app.js*', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
  const state = { modelFailure: false, historyFailure: false, quoteFailure: false, models: [model], history: [], historyRequests: [], creates: [], quotes: [], ...options };
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && !['/api/v1/generations/quote', '/api/v1/generations'].includes(path)) return route.abort();
    if (path === '/api/v1/me') return json({ id: 'audit-user', telegram_id: 777, first_name: 'QA', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') {
      if (state.modelGate) await state.modelGate;
      return state.modelFailure ? json({ detail: 'Simulated models failure' }, 500) : json({ models: state.models, families: [], max_generation_quantity: 4 });
    }
    if (path === '/api/v1/generations/quote') {
      state.quotes.push(request.postDataJSON());
      if (state.quoteGate) await state.quoteGate;
      return state.quoteFailure ? json({ detail: 'Simulated quote failure' }, 500) : json({ model_id: model.id, cost_rox: '15.00', effective_cost_rox: '15.00', enough_balance: true });
    }
    if (path === '/api/v1/generations' && request.method() === 'POST') {
      state.creates.push(request.postDataJSON());
      await new Promise(resolve => setTimeout(resolve, 200));
      return json({ id: generation.id, status: 'queued' }, 202);
    }
    if (path === '/api/v1/generations') {
      const before = new URL(request.url()).searchParams.get('before');
      state.historyRequests.push(before);
      if (state.historyGate) await state.historyGate;
      return state.historyFailure || (before && before === state.historyFailureBefore)
        ? json({ detail: 'Simulated history failure' }, 500)
        : json({ items: before ? state.moreHistory || [] : state.history, has_more: before ? false : Boolean(state.historyHasMore), next_before: before ? null : state.historyNextBefore || null });
    }
    if (path.startsWith('/api/v1/generations/')) return json(generation);
    if (path.startsWith('/api/v1/profiles/')) return json({ items: [] });
    if (path === '/api/v1/prompt-tools') return json({ items: [], admin_free: false });
    return json({ items: [] });
  });
  return { state, pageErrors };
}

test('model failure has a retry and recovers the create form', async ({ page }) => {
  const { state, pageErrors } = await setup(page, { modelFailure: true });
  await page.goto('/mini-app/?route=create');
  await expect(page.getByText('Не удалось загрузить модели', { exact: true })).toBeVisible();
  await expect(page.getByText('Каталог моделей загружается', { exact: true })).toHaveCount(0);
  await expect(page.locator('.bottom-nav')).toBeVisible();
  state.modelFailure = false;
  await page.getByRole('button', { name: 'Повторить загрузку моделей', exact: true }).click();
  await expect(page.locator('.create-screen textarea')).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test('pending model load does not prevent navigating to profile', async ({ page }) => {
  let release;
  const modelGate = new Promise(resolve => { release = resolve; });
  await setup(page, { modelGate });
  await page.goto('/mini-app/?route=create');
  try {
    await expect(page.locator('.bottom-nav')).toBeVisible();
    await page.locator('.bottom-nav [data-roxy-customer-route="profile"]').click();
    await expect(page.locator('.profile-screen')).toBeVisible();
  } finally { release(); }
});

test('an empty model catalog is an explicit recoverable state', async ({ page }) => {
  const { state } = await setup(page, { models: [] });
  await page.goto('/mini-app/?route=create');
  await expect(page.getByText('Модели пока недоступны', { exact: true })).toBeVisible();
  state.models = [model];
  await page.getByRole('button', { name: 'Повторить загрузку моделей', exact: true }).click();
  await expect(page.locator('.create-screen textarea')).toBeVisible();
});

test('history loading and failure never claim the history is empty; retry recovers', async ({ page }) => {
  let release;
  const historyGate = new Promise(resolve => { release = resolve; });
  const { state, pageErrors } = await setup(page, { historyFailure: true, historyGate });
  await page.goto('/mini-app/?route=history');
  try {
    await expect(page.getByText('Загружаю историю…', { exact: true })).toBeVisible();
    await expect(page.getByText('История пока пуста.', { exact: true })).toHaveCount(0);
  } finally { release(); }
  await expect(page.getByText('Не удалось загрузить историю', { exact: true })).toBeVisible();
  await expect(page.getByText('История пока пуста.', { exact: true })).toHaveCount(0);
  state.historyFailure = false;
  state.history = [generation];
  await page.getByRole('button', { name: 'Повторить загрузку истории', exact: true }).click();
  await expect(page.locator('.history-card')).toHaveCount(1);
  expect(pageErrors).toEqual([]);
});

test('quote failure retries the same draft and cannot submit before the fresh quote', async ({ page }) => {
  const { state, pageErrors } = await setup(page, { quoteFailure: true });
  await page.goto('/mini-app/?route=create');
  const prompt = page.locator('.create-screen textarea').first();
  const create = page.locator('.create-summary button.primary');
  await prompt.fill('Описание не теряется после ошибки цены');
  const retry = page.getByRole('button', { name: 'Повторить расчёт цены', exact: true });
  await expect(retry).toBeVisible();
  await expect(create).toBeDisabled();
  let release;
  state.quoteGate = new Promise(resolve => { release = resolve; });
  state.quoteFailure = false;
  try {
    await retry.click();
    await expect.poll(() => state.quotes.length).toBe(2);
    await expect(create).toBeDisabled();
    await create.evaluate(button => button.click());
    expect(state.creates).toHaveLength(0);
    await expect(prompt).toHaveValue('Описание не теряется после ошибки цены');
  } finally { release(); }
  await expect(create).toBeEnabled();
  await expect(create).toContainText('15 ROX');
  await create.evaluate(button => { button.click(); button.click(); });
  await expect.poll(() => state.creates.length).toBe(1);
  expect(state.quotes[0]).toEqual(state.quotes[1]);
  expect(state.creates[0].prompt).toBe('Описание не теряется после ошибки цены');
  expect(pageErrors).toEqual([]);
});

test('history pagination retry retains existing work and retries the failed cursor', async ({ page }) => {
  const { state, pageErrors } = await setup(page, {
    history: [generation], historyHasMore: true, historyNextBefore: 'next-page',
    historyFailureBefore: 'next-page', moreHistory: [{ ...generation, id: 'audit-generation-2' }],
  });
  await page.goto('/mini-app/?route=history');
  await expect(page.locator('.history-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Показать ещё', exact: true }).click();
  await expect(page.getByText('Не удалось загрузить историю', { exact: true })).toBeVisible();
  await expect(page.locator('.history-card')).toHaveCount(1);
  state.historyFailureBefore = null;
  await page.getByRole('button', { name: 'Повторить загрузку истории', exact: true }).click();
  await expect(page.locator('.history-card')).toHaveCount(2);
  expect(state.historyRequests.at(-1)).toBe('next-page');
  expect(pageErrors).toEqual([]);
});

test('a late history page cannot overwrite a newer refresh or its cursor', async ({ page }) => {
  const { state, pageErrors } = await setup(page, {
    history: [generation], historyHasMore: true, historyNextBefore: 'old-cursor',
  });
  let releaseOldPage;
  let markOldPageStarted;
  const oldPageGate = new Promise(resolve => { releaseOldPage = resolve; });
  const oldPageStarted = new Promise(resolve => { markOldPageStarted = resolve; });
  await page.route('**/api/v1/generations?**', async route => {
    if (new URL(route.request().url()).searchParams.get('before') !== 'old-cursor') return route.fallback();
    markOldPageStarted();
    await oldPageGate;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      items: [{ ...generation, id: 'late-old-work', model: { ...model, title: 'Устаревшая работа' } }],
      has_more: false, next_before: null,
    }) });
  });
  await page.goto('/mini-app/?route=history');
  await expect(page.locator('.history-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Показать ещё', exact: true }).click();
  await oldPageStarted;
  try {
    await page.locator('.bottom-nav [data-roxy-customer-route="profile"]').click();
    await expect(page.locator('.profile-screen')).toBeVisible();
    state.history = [{ ...generation, id: 'current-work', model: { ...model, title: 'Актуальная работа' } }];
    state.historyNextBefore = 'current-cursor';
    state.moreHistory = [{ ...generation, id: 'current-work-2', model: { ...model, title: 'Актуальная вторая работа' } }];
    await page.goBack();
    await expect(page.locator('.history-card')).toHaveCount(1);
    await expect(page.locator('.history-card').getByText('Актуальная работа', { exact: true })).toBeVisible();
    const oldResponse = page.waitForResponse(response => new URL(response.url()).searchParams.get('before') === 'old-cursor');
    releaseOldPage();
    await (await oldResponse).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator('.history-card')).toHaveCount(1);
    await expect(page.getByText('Устаревшая работа', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Загружаю историю…', { exact: true })).toHaveCount(0);
    const more = page.getByRole('button', { name: 'Показать ещё', exact: true });
    await expect(more).toBeEnabled();
    await more.click();
    await expect(page.locator('.history-card')).toHaveCount(2);
    expect(state.historyRequests.at(-1)).toBe('current-cursor');
    expect(pageErrors).toEqual([]);
  } finally { releaseOldPage(); }
});

test('model dialog contains keyboard focus and restores it on Escape', async ({ page }) => {
  await setup(page);
  await page.goto('/mini-app/?route=create');
  const opener = page.locator('.family-card').first();
  await opener.focus();
  await opener.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'audit_recovery', exact: true });
  await expect(dialog).toBeVisible();
  const close = dialog.getByRole('button', { name: 'Закрыть', exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.locator('.variant-row').last()).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
});

test('profile image tiles have a useful accessible name', async ({ page }) => {
  await setup(page, { history: [generation] });
  await page.goto('/mini-app/?route=profile');
  await expect(page.locator('.media-grid').getByRole('button', { name: /Открыть работу.*Audit Recovery Model/ })).toBeVisible();
});

