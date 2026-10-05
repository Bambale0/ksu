import { expect, test } from '@playwright/test';

const ID = '12345678-1234-4234-8234-123456789abc';
const OTHER_ID = '87654321-4321-4321-8321-cba987654321';
const instructions = 'Строго 1 референс — фото лица.\nЗагрузите чёткое фото без очков ✨';
const secondInstructions = '1-е фото — ваше лицо.\n2-е фото — образ, который нужно повторить.';

async function setup(page, description = instructions, maximum = 1) {
  const writes = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.__telegramBackHandler = null;
    window.Telegram = { WebApp: {
      initData: 'query_id=trend-instructions&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
      BackButton: {
        show() {}, hide() {},
        onClick(callback) { window.__telegramBackHandler = callback; },
        offClick(callback) { if (window.__telegramBackHandler === callback) window.__telegramBackHandler = null; },
      },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (request.method() !== 'GET') writes.push(path);
    if (path === `/api/v1/trends/${ID}` || path === `/api/v1/trends/${OTHER_ID}`) return json({
      id: path.endsWith(OTHER_ID) ? OTHER_ID : ID,
      title: path.endsWith(OTHER_ID) ? 'Второй образ' : 'ЧУМА ПОДОЖДЕТ',
      description: path.endsWith(OTHER_ID) ? secondInstructions : description,
      media_type: 'image', preview_url: null,
      model: { id: 'nano-banana-pro', title: 'Nano Banana Pro' },
      cost_rox: '25', reference_requirements: { min: 1, max: path.endsWith(OTHER_ID) ? 2 : maximum },
    });
    if (path === '/api/v1/me') return json({ id: 'viewer', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
    return json({ items: [], has_more: false });
  });
  return { writes, errors };
}

test('trend instruction is visible before upload and preserves line breaks', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  const { writes, errors } = await setup(page);
  await page.goto(`/mini-app/trend/?id=${ID}`);
  const note = page.getByRole('note', { name: 'Инструкция к тренду' });
  await expect(note).toBeVisible();
  await expect(note.locator('p')).toHaveText(instructions);
  await expect(note.locator('p')).toHaveCSS('white-space', 'pre-wrap');
  const upload = page.locator('input[type=file]');
  await expect(upload).toHaveCount(1);
  expect(await upload.getAttribute('multiple')).toBeNull();
  expect(await note.evaluate((element) => element.getBoundingClientRect().bottom)).toBeLessThan(
    await upload.evaluate(element => element.closest('label').getBoundingClientRect().top),
  );
  await expect(page.getByRole('button', { name: 'Сгенерировать · 25 ROX' })).toBeDisabled();
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  await page.screenshot({ path: 'test-results/trend-instructions-mobile.png', fullPage: true });
});

test('description is per trend and does not impose a global single-photo limit', async ({ page }) => {
  await setup(page);
  await page.goto(`/mini-app/trend/?id=${ID}`);
  await expect(page.getByRole('note').locator('p')).toHaveText(instructions);
  await page.goto(`/mini-app/trend/?id=${OTHER_ID}`);
  await expect(page.getByRole('note').locator('p')).toHaveText(secondInstructions);
  await expect(page.locator('input[type=file]')).toHaveAttribute('multiple', '');
  await expect(page.getByRole('note')).toHaveCount(1);
});

test('callout survives native Back and explicit reopen without duplication', async ({ page }) => {
  await setup(page);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await page.goto(`/mini-app/?startapp=trend_${ID}`);
    await expect(page).toHaveURL(new RegExp(`/mini-app/trend/\\?id=${ID}$`));
    await expect(page.getByRole('note').locator('p')).toHaveText(instructions);
    await expect(page.getByRole('note')).toHaveCount(1);
    await expect.poll(() => page.evaluate(() => typeof window.__telegramBackHandler)).toBe('function');
    await page.evaluate(() => window.__telegramBackHandler());
    await expect(page).toHaveURL(/\/mini-app\/\?route=home$/);
    await expect(page.getByRole('note', { name: 'Инструкция к тренду' })).toHaveCount(0);
  }
});

test('empty descriptions do not leave an empty instruction panel', async ({ page }) => {
  await setup(page, '   \n ');
  await page.goto(`/mini-app/trend/?id=${ID}`);
  await expect(page.getByRole('heading', { name: 'ЧУМА ПОДОЖДЕТ' })).toBeVisible();
  await expect(page.getByRole('note', { name: 'Инструкция к тренду' })).toHaveCount(0);
});

test('long text and markup stay literal and fit a narrow viewport', async ({ page }) => {
  const text = '<img src=x onerror=alert(1)>\n' + 'Референс'.repeat(45);
  await page.setViewportSize({ width: 320, height: 740 });
  const { errors } = await setup(page, text);
  await page.goto(`/mini-app/trend/?id=${ID}`);
  const note = page.getByRole('note', { name: 'Инструкция к тренду' });
  await expect(note.locator('p')).toHaveText(text);
  await expect(note.locator('img')).toHaveCount(0);
  expect(await note.evaluate(element => element.scrollWidth <= element.clientWidth)).toBeTruthy();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
