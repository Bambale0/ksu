import { expect, test } from '@playwright/test';

const token = '0123456789abcdef0123456789abcdef_AAAAAAAAAAAAAAAA';
const payload = `repeat_${token}`;
const secretPrompt = 'SERVER_ONLY_SENTINEL_PROMPT';
const secretSetting = 'SERVER_ONLY_SENTINEL_SETTING';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nano-banana',
  operation: 'auto',
  media_type: 'image',
  price_rox: '25.00',
  ui_schema: {
    defaults: { resolution: '1K' },
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'reference_images', label: 'Референсы', control: 'files', accept: 'image/*', max_items: 4 },
      { name: 'resolution', label: 'Качество', control: 'combobox', suggestions: ['1K', '2K'] },
    ],
    scenario: {
      default: 'text',
      items: [
        { id: 'text', title: 'Текст', visible_fields: ['prompt', 'resolution'] },
        { id: 'references', title: 'Референсы', visible_fields: ['prompt', 'reference_images', 'resolution'], required_fields: ['reference_images'] },
      ],
    },
  },
};

async function mockPrivateRepeat(page) {
  const repeatBodies = [];

  await page.addInitScript((startParam) => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 888, first_name: 'Recipient' }, start_param: startParam },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  }, payload);

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/onboarding') return json({ enabled: true, version: '2', completed: true });
    if (path === '/api/v1/me') return json({ id: 'recipient', telegram_id: 888, first_name: 'Recipient', balance_rox: '100.00', created_at: '2026-09-02T00:00:00Z', is_active: true });
    if (path === `/api/v1/generation-repeat-links/${token}`) return json({
      model_id: model.id,
      references_required: true,
      reference_fields: ['reference_images'],
    });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/uploads/kie' && method === 'POST') return json({
      url: 'https://recipient.local/my-reference.png',
      name: 'my-reference.png',
      reference: { id: 'recipient-ref', kind: 'image', url: 'https://recipient.local/my-reference.png' },
    }, 201);
    if (path === `/api/v1/generation-repeat-links/${token}/quote` && method === 'POST') {
      repeatBodies.push({ kind: 'quote', body: request.postDataJSON() });
      return json({ cost_rox: '25.00', enough_balance: true });
    }
    if (path === `/api/v1/generation-repeat-links/${token}/launch` && method === 'POST') {
      repeatBodies.push({ kind: 'launch', body: request.postDataJSON() });
      return json({ id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', status: 'queued', cost_rox: '25.00' }, 202);
    }
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/references') return json({ items: [] });
    if (path === '/api/v1/discovery/home') return json({ slides: [] });
    if (path === '/api/v1/me/overview') return json({ works_count: 0, publications_count: 0, likes_count: 0 });
    if (path.includes('/notifications')) return json({ items: [], unread_count: 0 });
    return json({ items: [] });
  });

  return { repeatBodies };
}

test('private repeat keeps source prompt and settings completely server-only', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockPrivateRepeat(page);
  await page.goto(`/mini-app/?startapp=${encodeURIComponent(payload)}`);

  const bodyText = page.locator('body');
  await expect(bodyText).toContainText('Промпт и настройки исходной работы скрыты.');
  await expect(page.getByText('Добавьте свой референс')).toBeVisible();
  await expect(page.getByLabel('Описание')).toHaveCount(0);
  await expect(page.getByLabel('Качество')).toHaveCount(0);
  await expect(bodyText).not.toContainText(secretPrompt);
  await expect(bodyText).not.toContainText(secretSetting);
  await expect(page.locator('input[type="file"]')).toHaveCount(1);

  const html = await page.content();
  expect(html).not.toContain(secretPrompt);
  expect(html).not.toContain(secretSetting);

  await page.locator('input[type="file"]').setInputFiles({
    name: 'my-reference.png',
    mimeType: 'image/png',
    buffer: Buffer.from('recipient-owned-image'),
  });

  const launch = page.getByRole('button', { name: /Повторить · 25\.00 ROX/ });
  await expect(launch).toBeEnabled();
  await launch.click();

  await page.waitForURL('**/mini-app/?route=history&generation=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');

  expect(state.repeatBodies.some((item) => item.kind === 'quote')).toBeTruthy();
  const launched = state.repeatBodies.find((item) => item.kind === 'launch');
  expect(launched.body).toEqual({
    parameters: { reference_images: ['https://recipient.local/my-reference.png'] },
  });

  const serializedBodies = JSON.stringify(state.repeatBodies);
  expect(serializedBodies).not.toContain('prompt');
  expect(serializedBodies).not.toContain('resolution');
  expect(serializedBodies).not.toContain('billing_seconds');
  expect(serializedBodies).not.toContain(secretPrompt);
  expect(serializedBodies).not.toContain(secretSetting);
  expect(serializedBodies).not.toContain('private.example');
});
