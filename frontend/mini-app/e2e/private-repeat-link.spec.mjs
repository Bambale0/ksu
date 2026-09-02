import { expect, test } from '@playwright/test';

const token = '0123456789abcdef0123456789abcdef_AAAAAAAAAAAAAAAA';
const payload = `repeat_${token}`;

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
  let createdBody = null;

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
      prompt: 'Неоновый портрет',
      input_url: null,
      billing_seconds: null,
      parameters: { resolution: '2K' },
      references_required: true,
    });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/uploads/kie' && method === 'POST') return json({
      url: 'https://recipient.local/my-reference.png',
      name: 'my-reference.png',
      reference: { id: 'recipient-ref', kind: 'image', url: 'https://recipient.local/my-reference.png' },
    }, 201);
    if (path === '/api/v1/generations/quote' && method === 'POST') return json({ cost_rox: '25.00', enough_balance: true });
    if (path === '/api/v1/generations' && method === 'POST') {
      createdBody = request.postDataJSON();
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

  return { createdBody: () => createdBody };
}

test('private repeat link never exposes owner media and accepts recipient references', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockPrivateRepeat(page);
  await page.goto(`/mini-app/?startapp=${encodeURIComponent(payload)}`);

  await expect(page.getByText('Исходная работа остаётся приватной.', { exact: false })).toBeVisible();
  await expect(page.getByDisplayValue('Неоновый портрет')).toBeVisible();
  await expect(page.getByDisplayValue('2K')).toBeVisible();
  await expect(page.getByText('Добавьте свои референсы')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('private.example');

  await page.locator('input[type="file"]').setInputFiles({
    name: 'my-reference.png',
    mimeType: 'image/png',
    buffer: Buffer.from('recipient-owned-image'),
  });

  const launch = page.getByRole('button', { name: /Повторить · 25\.00 ROX/ });
  await expect(launch).toBeEnabled();
  await launch.click();

  await page.waitForURL('**/mini-app/?route=history&generation=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa');
  await expect(page.getByText('Исходная работа остаётся приватной.', { exact: false })).toHaveCount(0);

  const body = state.createdBody();
  expect(body.model_id).toBe('nano-banana-2');
  expect(body.prompt).toBe('Неоновый портрет');
  expect(body.input_url).toBeUndefined();
  expect(body.parameters.reference_images).toEqual(['https://recipient.local/my-reference.png']);
  expect(JSON.stringify(body)).not.toContain('private.example');
});
