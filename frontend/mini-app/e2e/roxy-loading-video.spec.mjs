import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=roxy-loader&hash=test',
      initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
}

test('loading video selects responsive codecs and disappears as soon as app data is ready', async ({ page }) => {
  await installTelegram(page);
  let releaseMe;
  const meGate = new Promise((resolve) => { releaseMe = resolve; });
  await page.route('**/api/v1/me', async (route) => {
    await meGate;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ telegram_id: 777, first_name: 'QA', balance_rox: '100' }),
    });
  });
  await page.route('**/api/v1/generations/models', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ models: [], families: [] }),
  }));
  await page.goto('/mini-app/', { waitUntil: 'domcontentloaded' });

  const splash = page.locator('.splash-video');
  await expect(splash).toBeVisible();
  const video = splash.locator('video');
  await expect(video).toHaveJSProperty('autoplay', true);
  await expect(video).toHaveJSProperty('muted', true);
  await expect(video).toHaveJSProperty('playsInline', true);
  await expect(video).toHaveJSProperty('loop', true);
  await expect(video).toHaveJSProperty('controls', false);
  await expect(video).toHaveJSProperty('preload', 'auto');
  const sources = await video.locator('source').evaluateAll((nodes) => nodes.map((item) => ({
    src: item.getAttribute('src'),
    media: item.getAttribute('media'),
    type: item.getAttribute('type'),
  })));
  expect(sources).toEqual([
    { src: '/mini-app/loading/roxy-loading-mobile-9x16.mp4', media: '(max-width: 767px) and (orientation: portrait)', type: 'video/mp4' },
    { src: '/mini-app/loading/roxy-loading-mobile-9x16.webm', media: '(max-width: 767px) and (orientation: portrait)', type: 'video/webm' },
    { src: '/mini-app/loading/roxy-loading-web-16x9.webm', media: null, type: 'video/webm' },
    { src: '/mini-app/loading/roxy-loading-web-16x9.mp4', media: null, type: 'video/mp4' },
  ]);

  releaseMe();
  await expect(splash).toHaveCount(0);
  await expect(page.locator('.roxy-app')).toBeVisible();
});

test('media autoplay failure leaves a branded non-blocking fallback', async ({ page }) => {
  await installTelegram(page);
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = () => Promise.reject(new Error('autoplay blocked'));
  });
  await page.route('**/api/v1/me', async () => new Promise(() => {}));
  await page.goto('/mini-app/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.splash-video.splash-video-fallback')).toBeVisible();
  await expect(page.locator('.splash-video-fallback-mark')).toBeVisible();
});
test('native phone splash animates immediately while the media is buffering', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
  let resolveMe;
  const waiting = new Promise((resolve) => { resolveMe = resolve; });
  await page.route('**/api/v1/me', async (route) => {
    await waiting;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ telegram_id: 777, first_name: 'QA', balance_rox: '100' }),
    });
  });
  await page.route('**/api/v1/onboarding', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: '{"enabled":true,"completed":false,"version":"qa"}',
  }));
  await page.route('**/mini-app/loading/*', (route) => route.abort());
  await page.route('**/api/v1/generations/models', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '{"models":[],"families":[]}',
  }));
  await page.goto('/mini-app/', { waitUntil: 'domcontentloaded' });
  const splash = page.locator('.splash-video');
  await expect(splash).toBeVisible();
  await expect(splash.locator('.splash-video-fallback-mark')).toBeVisible();
  const onboardingOverlay = page.locator('.onboarding-overlay.roxy-onboarding-v2');
  await expect(onboardingOverlay).toBeVisible();
  const splashLayer = await splash.evaluate((node) => Number(getComputedStyle(node).zIndex));
  const onboardingLayer = await onboardingOverlay.evaluate((node) => Number(getComputedStyle(node).zIndex));
  expect(splashLayer).toBeGreaterThan(onboardingLayer);

  await expect.poll(async () => splash.locator('.splash-video-fallback-mark').evaluate(
    (element) => getComputedStyle(element).animationName,
  )).toContain('roxy-boot-pulse');
  expect(await splash.locator('video').locator('source').first().getAttribute('type')).toBe('video/mp4');
  resolveMe();
  await expect(splash).toHaveCount(0);
});
