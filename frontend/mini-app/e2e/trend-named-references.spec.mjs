import { expect, test } from '@playwright/test';

const ID = '12345678-1234-4234-8234-123456789abc';
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64');
const slots = ['Персонаж', 'Одежда', 'Автомобиль', 'Фон'].map((label, order) => ({
  id: `image_${order + 1}`, label, description: `Фото: ${label}`, kind: 'image', source: 'user', order, required: true,
}));

async function setup(page, schema = { mode: 'strict', slots }) {
  const state = { runs: [], uploads: 0, errors: [] };
  page.on('pageerror', e => state.errors.push(e.message));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=named&hash=test', initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === `/api/v1/trends/${ID}/run`) { state.runs.push(req.postDataJSON()); return json({ detail: 'Проверка без платного запуска' }, 422); }
    if (path === '/api/v1/uploads/kie') {
      state.uploads++;
      return json({ url: `https://cdn.example/ref-${state.uploads}.png`, reference: { kind: 'image' }, probe_status: 'ready' });
    }
    if (path === `/api/v1/trends/${ID}`) return json({
      id: ID, title: 'Именные референсы', media_type: 'image', cost_rox: '25',
      reference_schema: schema, reference_requirements: { image: { min: 4, max: 4 } },
      user_fields: [{ key: 'Возраст', label: 'Возраст', type: 'number', required: true }],
    });
    if (path === '/api/v1/me') return json({ id: 'viewer', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    return json({ items: [], has_more: false });
  });
  return state;
}

test('four named slots retain identity on replace/delete and require personal fields', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  const state = await setup(page);
  await page.goto(`/mini-app/trend/?id=${ID}`);
  const run = page.getByRole('button', { name: 'Сгенерировать · 25 ROX' });
  await expect(page.getByRole('group', { name: 'Image1 · Персонаж' })).toBeVisible();
  await expect(page.locator('input[type=file]')).toHaveCount(4);
  await expect(run).toBeDisabled();
  for (const index of [3, 0, 2, 1]) {
    await page.getByLabel(`Загрузить ${slots[index].label}`, { exact: true }).setInputFiles({ name: `${index}.png`, mimeType: 'image/png', buffer: png });
    await expect(page.getByRole('status').filter({ hasText: /из 4/ })).toHaveText(`${[3, 0, 2, 1].indexOf(index) + 1} из 4`);
  }
  await expect(run).toBeDisabled();
  await page.getByLabel('Возраст', { exact: false }).fill('25');
  await expect(run).toBeEnabled();
  await page.getByRole('button', { name: 'Удалить Одежда', exact: true }).click();
  await expect(run).toBeDisabled();
  await page.getByLabel('Загрузить Одежда', { exact: true }).setInputFiles({ name: 'replacement.png', mimeType: 'image/png', buffer: png });
  await expect(run).toBeEnabled();
  await run.click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0].reference_inputs).toEqual([
    { slot_id: 'image_1', kind: 'image', url: 'https://cdn.example/ref-2.png' },
    { slot_id: 'image_2', kind: 'image', url: 'https://cdn.example/ref-5.png' },
    { slot_id: 'image_3', kind: 'image', url: 'https://cdn.example/ref-3.png' },
    { slot_id: 'image_4', kind: 'image', url: 'https://cdn.example/ref-1.png' },
  ]);
  expect(state.runs[0].reference_urls).toEqual([]);
  expect(state.errors).toEqual([]);
  await page.screenshot({ path: 'test-results/named-reference-slots-mobile.png', fullPage: true });
});
