import { expect, test } from '@playwright/test';

const generationId = '11111111-2222-4333-8444-555555555555';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'Viewer' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function openSeedanceReplay(page, sourceHasVideoReference) {
  let uploadCount = 0;
  await installTelegram(page);
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'video/mp4',
    body: '',
  }));
  await page.route('**/api/v1/**', (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === `/api/v1/feed/${generationId}/remix/prepare`) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          source_generation_id: generationId,
          source_feed_gen_id: generationId,
          surface: 'feed',
          model_id: 'seedance-2.5',
          effective_model_id: 'seedance-2.5',
          model_title: 'Seedance 2.5',
          prompt: '',
          prompt_hidden: true,
          prompt_editable: false,
          settings: { duration: 10, resolution: '720p', aspect_ratio: '9:16' },
          reference_requirements: { image_count: 1, video_count: 0, audio_count: 0, required: true },
          source_has_video_reference: sourceHasVideoReference,
          preview_url: 'https://cdn.roxy.local/rendered-result.mp4',
          media: [],
        }),
      });
    }
    if (url.pathname === '/api/v1/uploads/kie' && route.request().method() === 'POST') {
      uploadCount += 1;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          url: `https://cdn.roxy.local/viewer-${uploadCount}.jpg`,
          name: `viewer-${uploadCount}.jpg`,
          reference: {
            id: `viewer-reference-${uploadCount}`,
            kind: 'image',
            url: `https://cdn.roxy.local/viewer-${uploadCount}.jpg`,
          },
        }),
      });
    }
    if (url.pathname === `/api/v1/feed/${generationId}/remix/quote`) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ cost_rox: '70.00', enough_balance: true }),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  await page.goto(`/mini-app/remix/?source=${generationId}&surface=feed`);
  await expect(page.getByRole('heading', { name: 'Добавьте фото внешности' })).toBeVisible();
  return { uploadCount: () => uploadCount };
}

test('Seedance repeat explains that author video drives motion and only accepts identity photos', async ({ page }) => {
  await openSeedanceReplay(page, true);

  await expect(page.getByText(/Исходный видео-референс автора задаст движение и сцену/)).toBeVisible();
  await expect(page.getByText(/ссылка на видео автора останется скрыта/)).toBeVisible();
  await expect(page.locator('.screen-head p')).toContainText('Видео автора задаст движение, а ваши фото — внешность');
  await expect(page.locator('input[type="file"]')).toHaveAttribute('accept', 'image/*');
  await expect(page.getByText(/своё видео/)).toHaveCount(0);
});

test('Seedance photo fallback says the rendered result will not be reused as motion', async ({ page }) => {
  await openSeedanceReplay(page, false);

  await expect(page.getByText(/У автора нет видео-референса/)).toBeVisible();
  await expect(page.getByText(/не подставляя готовый ролик/)).toBeVisible();
  await expect(page.locator('.screen-head p')).toContainText('внешность переносим с ваших фото');
  await expect(page.locator('input[type="file"]')).toHaveAttribute('accept', 'image/*');
});

test('Seedance repeat caps a multi-file selection to the exact identity-photo count', async ({ page }) => {
  const state = await openSeedanceReplay(page, true);

  await page.locator('input[type="file"]').setInputFiles([
    { name: 'identity-one.png', mimeType: 'image/png', buffer: Buffer.from('one') },
    { name: 'identity-two.png', mimeType: 'image/png', buffer: Buffer.from('two') },
  ]);

  await expect.poll(state.uploadCount).toBe(1);
  await expect(page.getByText(/добавлено 1/)).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
});
