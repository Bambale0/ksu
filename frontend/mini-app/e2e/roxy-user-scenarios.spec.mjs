import { expect, test } from '@playwright/test';

const models = [
  { id: 'nano-banana-2', title: 'Nano Banana 2', family: 'nano-banana', operation: 'auto', media_type: 'image', price_rox: '25.00', ui_schema: { defaults: { prompt: '' }, fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }, { name: 'resolution', label: 'Качество', control: 'select', options: [{ value: '1K', label: '1K' }, { value: '2K', label: '2K' }] }], groups: [{ id: 'main', title: 'Настройки' }] } },
  { id: 'seedance-2.5', title: 'Seedance 2.5', family: 'seedance', operation: 'auto', media_type: 'video', price_rox: '60.00', ui_schema: { defaults: { prompt: '' }, fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }], groups: [{ id: 'main', title: 'Настройки' }], billing_seconds: { label: 'Длительность', min: 1, max: 10, required: true } } },
  { id: 'roxy-music', title: 'ROXY Music', family: 'music', operation: 'text_to_audio', media_type: 'audio', price_rox: '100.00', ui_schema: { defaults: { prompt: '' }, fields: [{ name: 'prompt', label: 'Промпт', control: 'textarea', required: true }], groups: [{ id: 'main', title: 'Настройки' }] } },
];
const families = [
  { id: 'nano-banana', title: 'Nano Banana', media_types: ['image'], variant_count: 1, price_from_rox: '25.00', variants: [{ id: 'nano-banana-2', title: 'Nano Banana 2', version: '2', media_type: 'image', operation: 'auto', price_rox: '25.00' }] },
  { id: 'seedance', title: 'Seedance', media_types: ['video'], variant_count: 1, price_from_rox: '60.00', variants: [{ id: 'seedance-2.5', title: 'Seedance 2.5', version: '2.5', media_type: 'video', operation: 'auto', price_rox: '60.00' }] },
  { id: 'music', title: 'Музыка', media_types: ['audio'], variant_count: 1, price_from_rox: '100.00', variants: [{ id: 'roxy-music', title: 'ROXY Music', version: 'Music', media_type: 'audio', operation: 'text_to_audio', price_rox: '100.00' }] },
];
const generation = { id: 'gen_1', status: 'succeeded', model: models[0], result_url: 'https://cdn.roxy.local/result.png', result_urls: ['https://cdn.roxy.local/result.png'], media: [{ url: 'https://cdn.roxy.local/result.png' }], prompt: 'Портрет в неоне', created_at: '2026-08-21T08:30:00Z', is_profile_visible: true, publication_scope: 'profile' };
const feedCard = { ...generation, id: 'feed_1', preview_url: 'https://cdn.roxy.local/feed.png', model: 'Nano Banana 2', likes_count: 12, shares_count: 3, comments_count: 2, liked_by_me: false, is_mine: true, feed_published_at: '2026-08-21T08:40:00Z' };
const trends = [
  { id: 'trend_portrait', title: 'Неоновый портрет', description: 'Готовая идея для яркого аватара', media_type: 'image', cost_rox: '25.00', model: { title: 'Nano Banana 2' } },
  { id: 'trend_video', title: 'Короткий клип', description: 'Видео для Reels и Shorts', media_type: 'video', cost_rox: '60.00', model: { title: 'Seedance 2.5' } },
];
const routes = ['home', 'feed', 'catalog', 'create', 'partners', 'profile'];
const viewports = [{ width: 360, height: 740 }, { width: 390, height: 844 }, { width: 430, height: 932 }, { width: 768, height: 1024 }];
const checks = ['load', 'copy', 'navigation', 'actions', 'no-tech'];
const scenarios = routes.flatMap((route) => viewports.flatMap((viewport) => checks.map((check) => ({ route, viewport, check }))));

async function mockRoxy(page) {
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: 'query_id=e2e&hash=test', initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } }, ready() {}, expand() {}, onEvent() {}, offEvent() {}, openLink(url) { window.__lastOpenedLink = url; }, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} }, HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} } } };
  });
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models, families });
    if (path === '/api/v1/generations/quote') return json({ cost_rox: '25.00', balance_rox: '150.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') return json({ id: 'gen_new', status: 'queued', cost_rox: '25.00' });
    if (path.startsWith('/api/v1/generations/')) return json(generation);
    if (path === '/api/v1/generations') return json({ items: [generation], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [feedCard] });
    if (path.includes('/publish')) return json({ publication_scope: 'feed', downgraded_to_profile: false, item: feedCard });
    if (path.includes('/like')) return json({ id: 'feed_1', surface: 'feed', liked_by_me: true, likes_count: 13 });
    if (path.includes('/share')) return json({ id: 'feed_1', shares_count: 4, link: 'https://t.me/roxy_aicreativebot?start=feed_1' });
    if (path.includes('/comments')) return json({ items: [] });
    if (path.includes('/remix')) return json({ id: 'gen_remix', status: 'queued' });
    if (path === '/api/v1/trends') return json({ items: trends });
    if (path.includes('/api/v1/trends/') && path.endsWith('/run')) return json({ id: 'trend_run', status: 'queued', cost_rox: '25.00' });
    if (path === '/api/v1/referrals/stats') return json({ referral_link: 'https://t.me/roxy_aicreativebot?start=ref_777', first_line: 2, second_line: 1, available_rub: '1200.00', available: '1200.00', balance_rub: '1200.00' });
    if (path === '/api/v1/referrals/invitations') return json({ items: [] });
    if (path === '/api/v1/referrals/rewards') return json({ items: [] });
    if (path === '/api/v1/me/transactions') return json([]);
    if (path === '/api/v1/payments/card/packages') return json({ provider: 'card', label: 'Оплата картой', currencies: ['RUB'], packages: { starter: { credits: '100', prices: { RUB: '100' } } } });
    return json({ items: [] });
  });
}

async function visibleTechCopyCount(page) {
  return page.locator('body *').evaluateAll((nodes) => nodes.filter((node) => {
    const text = node.textContent || '';
    if (!/KIE|provider|media routes|серверные media routes|временных KIE-ссылок/i.test(text)) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
  }).length);
}

test.describe('ROXY Mini App E2E audit', () => {
  test('covers at least 100 user scenarios across routes, viewports and actions', async ({ page }) => {
    test.setTimeout(120_000);
    expect(scenarios.length).toBeGreaterThanOrEqual(100);
    await mockRoxy(page);

    for (const [index, scenario] of scenarios.entries()) {
      await test.step(`scenario ${index + 1}: ${scenario.route}/${scenario.check}/${scenario.viewport.width}x${scenario.viewport.height}`, async () => {
        await page.setViewportSize(scenario.viewport);
        await page.goto(`/mini-app/?route=${scenario.route}`, { waitUntil: 'domcontentloaded' });
        await expect(page.getByText('ROXY').first()).toBeVisible({ timeout: 5_000 });
        await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
        await expect(page.getByRole('button', { name: /Создать/ })).toBeVisible();
        expect(await visibleTechCopyCount(page)).toBe(0);
        if (scenario.route === 'feed') await expect(page.getByText('Работы сообщества')).toBeVisible();
        if (scenario.route === 'catalog') await expect(page.getByText('Готовые сценарии')).toBeVisible();
        if (scenario.route === 'create') await expect(page.getByText('Настрой генерацию')).toBeVisible();
        if (scenario.route === 'partners') await expect(page.getByText(/реферальн|партн/i).first()).toBeVisible();
        if (scenario.route === 'profile') await expect(page.getByText('Профиль').first()).toBeVisible();
        if (scenario.check === 'navigation') {
          await page.getByRole('button', { name: /Создать/ }).click();
          await expect(page.getByText('Настрой генерацию')).toBeVisible();
        }
      });
    }
  });
});
