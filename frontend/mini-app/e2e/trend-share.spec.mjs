import { expect, test } from '@playwright/test';

const TREND_ID = '12345678-1234-4234-8234-123456789abc';
const SHARE_LINK = `https://t.me/RoxyExampleBot?startapp=trend_${TREND_ID}`;
const SHARE_URL = `https://t.me/share/url?url=${encodeURIComponent(SHARE_LINK)}&text=${encodeURIComponent('Попробуй тренд «Плёночный портрет» в ROXY ✨')}`;

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.__trendShareUrl = '';
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {},
        expand() {},
        close() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        openTelegramLink(url) { window.__trendShareUrl = url; },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockTrendApi(page) {
  await page.route('**/api/v1/trends/**', (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === `/api/v1/trends/${TREND_ID}` && request.method() === 'GET') {
      return json({
        id: TREND_ID,
        title: 'Плёночный портрет',
        description: 'Мягкий плёночный портрет',
        media_type: 'image',
        preview_url: null,
        model: { id: 'nano-banana-pro', title: 'Nano Banana Pro' },
        cost_rox: '25.00',
        admin_free: false,
        reference_requirements: { min: 0, max: 0 },
      });
    }
    if (path === `/api/v1/trends/${TREND_ID}/share` && request.method() === 'POST') {
      return json({
        id: TREND_ID,
        link: SHARE_LINK,
        copy_link: SHARE_LINK,
        share_text: 'Попробуй тренд «Плёночный портрет» в ROXY ✨',
        share_url: SHARE_URL,
      });
    }
    return json({ detail: 'Not found' }, 404);
  });
}

test('trend detail shares through native Telegram chooser', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  await mockTrendApi(page);

  await page.goto(`/mini-app/trend/?id=${TREND_ID}`);
  await expect(page.getByRole('heading', { name: 'Плёночный портрет' })).toBeVisible();
  const shareRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname === `/api/v1/trends/${TREND_ID}/share`
      && request.method() === 'POST'
  );
  await page.getByRole('button', { name: 'Поделиться трендом', exact: true }).click();
  await shareRequest;

  await expect.poll(() => page.evaluate(() => window.__trendShareUrl)).toBe(SHARE_URL);
});

test('shared trend startapp opens the exact trend', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  await mockTrendApi(page);

  await page.goto(`/mini-app/?startapp=trend_${TREND_ID}`);
  await expect(page).toHaveURL(new RegExp(`/mini-app/trend/\\?id=${TREND_ID}$`));
  await expect(page.getByRole('heading', { name: 'Плёночный портрет' })).toBeVisible();
});
