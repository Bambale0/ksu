import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
const adminRoot = new URL('../../../app/web/admin_app/', import.meta.url);
const cases = [
  { mode: 'main', view: 'users', endpoint: '/users', title: 'Пользователи', filter: 'q', value: 'customer' },
  { mode: 'main', view: 'generations', endpoint: '/generations', title: 'Генерации', filter: 'status', value: 'failed' },
  { mode: 'main', view: 'payments', endpoint: '/payments', title: 'Платежи', filter: 'provider', value: 'card' },
  { mode: 'main', view: 'withdrawals', endpoint: '/withdrawals', title: 'Партнёрские выводы', filter: 'status', value: 'pending', noTotal: true },
  { mode: 'main', view: 'referrals', endpoint: '/referrals/rewards', title: 'Реферальные начисления', filter: 'status', value: 'available' },
  { mode: 'main', view: 'promos', endpoint: '/promocodes', title: 'Партнёрские промокоды' },
  { mode: 'main', view: 'security', endpoint: '/security/sessions', title: 'Активные сессии' },
  { mode: 'main', view: 'security', endpoint: '/audit', title: 'Журнал действий', noTotal: true },
  { mode: 'control', view: 'Пользователи', endpoint: '/control/users', title: 'Пользователи', filter: 'q', value: 'customer' },
  { mode: 'control', view: 'Платежи', endpoint: '/control/payments', title: 'Платежи' },
  { mode: 'control', view: 'Операции', endpoint: '/control/operations', title: 'Операции генерации', noTotal: true },
  { mode: 'control', view: 'Рассылки', endpoint: '/notifications/campaigns', title: 'Durable campaigns' },
  { mode: 'control', view: 'Контент', endpoint: '/cms/documents', title: 'CMS documents' },
  { mode: 'control', view: 'Промо', endpoint: '/control/promocodes', title: 'Промокоды' },
  { mode: 'control', view: 'Модерация', endpoint: '/prompts', title: 'Модерация описаний' },
  { mode: 'control', view: 'Модерация', endpoint: '/trends', title: 'Тренды' },
  { mode: 'control', view: 'Партнёры', endpoint: '/partners/withdrawals', title: 'Withdrawals', noTotal: true },
];
const allEndpoints = new Set([...cases.map((entry) => '/api/v1/admin' + entry.endpoint), '/api/v1/admin/creator-partnership/applications', '/api/v1/admin/creator-partnership/agreements']);
function row(index, old) {
  const text = old ? 'old-record-beyond-first-page' : 'recent-' + index;
  return { id: text, first_name: text, username: text, telegram_id: index + 100, is_active: true,
    model_id: text, provider: text, amount: '10', credits: '10', currency: 'RUB', user_id: text,
    status: 'pending', reason: text, partner_user_id: text, source_user_id: text, code: text, uses_count: 0,
    name: text, title: text, slug: text, prompt: text, action: text, user: { username: text, telegram_id: index + 100 }, terms_summary: text, monthly_rox: '20', channel_name: text, channel_url: 'https://example.invalid/channel', payload: { model_id: 'test-model', tags: [] }, integrity_valid: true, metadata: {},
    created_at: '2026-11-06T00:00:00Z', updated_at: '2026-11-06T00:00:00Z' };
}
async function setup(page, mode, options = {}) {
  const requests = [], errors = [], unexpected = [], readPaths = [];
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: 'test-admin-init' } }; });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('https://telegram.org/**', (route) => route.fulfill({ body: '' }));
  await page.route('http://127.0.0.1:3018/**', async (route) => {
    const req = route.request(), parsed = new URL(req.url()), path = parsed.pathname;
    if (path.startsWith('/api/') && req.method() === 'GET') readPaths.push(path);
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path.startsWith('/admin-app/')) {
      const file = path.split('/').pop() || 'index.html';
      return route.fulfill({ contentType: file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html',
        body: readFileSync(new URL(file, adminRoot), 'utf8') });
    }
    if (path === '/api/v1/admin/auth/login') return json({ token: 'fixture-token', mfa_verified: true, permissions: options.permissions || ['*'] });
    if (path === '/api/v1/admin/auth/me') return json({ is_active: true, role: 'owner', telegram_id: 1, permissions: options.permissions || ['*'] });
    if (path === '/api/v1/admin/dashboard' || path.endsWith('/promocodes/program') || path === '/api/v1/admin/security/overview' || path === '/api/v1/admin/partners/analytics') return json({});
    if (path === '/api/v1/admin/trends/options') return json({ models: [] });
    if (path === '/api/v1/admin/control/tickets' || path === '/api/v1/admin/support/tickets') return json({ items: [], total: 0, limit: 50, offset: 0, has_more: false });
    if (allEndpoints.has(path)) {
      const query = Object.fromEntries(parsed.searchParams);
      requests.push({ path, query });
      const limit = Number(query.limit || 50), offset = Number(query.offset || 0);
      const data = { items: offset ? [row(offset, true)] : Array.from({ length: limit }, (_, i) => row(i, false)), limit, offset };
      if (!options.noTotal) data.total = limit + 1;
      return json(data);
    }
    unexpected.push(path);
    return json({ detail: 'Unexpected ' + path }, 404);
  });
  await page.goto('http://127.0.0.1:3018/admin-app/' + ({ control: 'control.html', creator: 'creator-partnership.html', trends: 'trends.html' }[mode] || '') + '?launch=preserved');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  return { requests, errors, unexpected, readPaths };
}
for (const entry of cases) {
  test(entry.mode + ' ' + entry.endpoint + ' reaches old records and retains filters on next, refresh and back', async ({ page }) => {
    const ctx = await setup(page, entry.mode, entry);
    await (entry.mode === 'main' ? page.locator('[data-view="' + entry.view + '"]') : page.getByRole('button', { name: entry.view, exact: true })).click();
    if (entry.filter) {
      if (entry.mode === 'control') {
        await page.getByLabel('Поиск', { exact: true }).fill(entry.value);
        await page.getByRole('button', { name: 'Найти', exact: true }).click();
      } else {
        const field = page.locator('.filter-bar [name="' + entry.filter + '"]');
        if (await field.evaluate((node) => node.tagName === 'SELECT')) await field.selectOption(entry.value);
        else await field.fill(entry.value);
        await page.getByRole('button', { name: 'Применить', exact: true }).click();
      }
    }
    const pager = page.getByRole('navigation', { name: 'Страницы: ' + entry.title, exact: true });
    await pager.getByRole('button', { name: 'Следующая страница', exact: true }).click();
    await expect(page.getByText('old-record-beyond-first-page', { exact: false }).first()).toBeVisible();
    const last = () => ctx.requests.filter((item) => item.path.endsWith(entry.endpoint)).at(-1);
    expect(Number(last().query.offset)).toBe(Number(last().query.limit));
    if (entry.filter) expect(last().query[entry.filter]).toBe(entry.value);
    await page.locator(entry.mode === 'main' ? '#refreshButton' : '#controlRefresh').click();
    await expect(pager.getByRole('button', { name: 'Предыдущая страница', exact: true })).toBeEnabled();
    expect(Number(last().query.offset)).toBe(Number(last().query.limit));
    await pager.getByRole('button', { name: 'Предыдущая страница', exact: true }).click();
    await expect.poll(() => last().query.offset).toBe('0');
    if (entry.filter) expect(last().query[entry.filter]).toBe(entry.value);
    expect(ctx.errors).toEqual([]);
    expect(ctx.unexpected).toEqual([]);
  });
}
test('control navigation honors live read permissions and skips forbidden landing requests', async ({ page }) => {
  const ctx = await setup(page, 'control', { permissions: ['support.read'] });
  await expect(page.locator('#controlNav').getByRole('button', { name: 'Поддержка', exact: true })).toBeVisible();
  await expect(page.locator('#controlNav').getByRole('button', { name: 'Платежи', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Партнёрские условия', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Очередь поддержки', exact: true })).toBeVisible();
  expect(ctx.readPaths).not.toContain('/api/v1/admin/dashboard');
  expect(ctx.errors).toEqual([]);
  expect(ctx.unexpected).toEqual([]);
});
for (const mode of ['main', 'control']) {
  test(mode + ' links existing creator management only with partners.read', async ({ page }) => {
    await setup(page, mode);
    const link = page.getByRole('link', { name: 'Партнёрские условия', exact: true }).first();
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', /creator-partnership\.html.*launch=preserved/);
  });
}

test('creator applications and agreements paginate independently and retain the application filter', async ({ page }) => {
  const ctx = await setup(page, 'creator');
  const appPager = page.getByRole('navigation', { name: 'Страницы: Заявки', exact: true });
  const agreementPager = page.getByRole('navigation', { name: 'Страницы: Соглашения', exact: true });
  await agreementPager.getByRole('button', { name: 'Следующая страница', exact: true }).click();
  await expect(page.locator('#agreements')).toContainText('old-record-beyond-first-page');
  await page.locator('#statusFilter').selectOption('pending');
  await appPager.getByRole('button', { name: 'Следующая страница', exact: true }).click();
  await expect(page.locator('#applications')).toContainText('old-record-beyond-first-page');
  const last = (suffix) => ctx.requests.filter((item) => item.path.endsWith(suffix)).at(-1);
  expect(last('/applications').query).toMatchObject({ offset: '100', status: 'pending' });
  expect(last('/agreements').query.offset).toBe('100');
  await page.locator('#refreshButton').click();
  await expect.poll(() => last('/applications').query.offset).toBe('100');
  expect(last('/applications').query.status).toBe('pending');
  await appPager.getByRole('button', { name: 'Предыдущая страница', exact: true }).click();
  await expect.poll(() => last('/applications').query.offset).toBe('0');
  expect(last('/agreements').query.offset).toBe('100');
  expect(ctx.errors).toEqual([]);
  expect(ctx.unexpected).toEqual([]);
});
test('dedicated trends search covers server pages and retains active filter', async ({ page }) => {
  const ctx = await setup(page, 'trends');
  await page.locator('#trendSearch').fill('birthday');
  await page.locator('#trendStatusFilter').selectOption('active');
  const last = () => ctx.requests.filter((item) => item.path.endsWith('/trends')).at(-1);
  await expect.poll(() => last().query.q).toBe('birthday');
  const pager = page.getByRole('navigation', { name: 'Страницы: Тренды', exact: true });
  await pager.getByRole('button', { name: 'Следующая страница', exact: true }).click();
  await expect(page.locator('#trendList')).toContainText('old-record-beyond-first-page');
  expect(last().query).toMatchObject({ offset: '200', q: 'birthday', is_active: 'true' });
  await page.locator('#trendRefresh').click();
  await expect(pager.getByRole('button', { name: 'Предыдущая страница', exact: true })).toBeEnabled();
  expect(last().query.offset).toBe('200');
  expect(ctx.errors).toEqual([]);
  expect(ctx.unexpected).toEqual([]);
});

test('main creator link stays hidden for a support-only operator', async ({ page }) => {
  const ctx = await setup(page, 'main', { permissions: ['support.read'] });
  await expect(page.getByRole('link', { name: 'Партнёрские условия', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Очередь поддержки', exact: true })).toBeVisible();
  expect(ctx.unexpected).toEqual([]);
});
test('prompt-only moderation does not request forbidden social data', async ({ page }) => {
  const ctx = await setup(page, 'control', { permissions: ['prompts.read'] });
  await expect(page.getByRole('heading', { name: 'Модерация описаний', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Тренды', exact: true })).toHaveCount(0);
  expect(ctx.readPaths).not.toContain('/api/v1/admin/trends');
  expect(ctx.readPaths).not.toContain('/api/v1/admin/dashboard');
  expect(ctx.errors).toEqual([]);
  expect(ctx.unexpected).toEqual([]);
});
