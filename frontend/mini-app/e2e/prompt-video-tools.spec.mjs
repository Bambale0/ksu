import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {},
        expand() {},
        close() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockPromptTools(page) {
  const calls = { videoPrompt: null, uploadHeaders: null };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/prompt-tools') return json({ items: [
      { id: 'prompt_builder', enabled: true, cost_credits: '10.00' },
      { id: 'video_prompt', enabled: true, cost_credits: '30.00', model: 'gpt-5-5' },
    ] });
    if (path === '/api/v1/uploads/kie') {
      calls.uploadHeaders = request.headers();
      return json({ url: 'https://cdn.roxy.test/gallery.mov', mime_type: 'video/quicktime', size: 9 }, 201);
    }
    if (path === '/api/v1/prompt-tools/video-prompt') {
      calls.videoPrompt = request.postDataJSON();
      return json({ id: 'prompt_task', status: 'queued' }, 202);
    }
    if (path === '/api/v1/prompt-tools/prompt_task') {
      return json({
        id: 'prompt_task',
        status: 'succeeded',
        result: {
          prompt_ru: 'Готовый кинематографичный промпт',
          prompt_en: 'Finished cinematic prompt',
          camera_movement_ru: 'Плавный dolly-in',
          timeline_ru: ['Общий план', 'Камера приближается', 'Финальный крупный план'],
          visual_style_ru: 'Мягкий контровой свет',
          audio_notes_ru: 'Тихий городской фон',
          negative_prompt: 'flicker, jitter',
          key_details: ['контровой свет', 'плавный dolly-in'],
          model_hint: 'Seedance 2.0',
        },
      });
    }
    return json({ items: [] });
  });
  return calls;
}

test('video prompt uses gallery video and renders tanyapi cinematic analysis', async ({ page }) => {
  await installTelegram(page);
  const calls = await mockPromptTools(page);

  await page.goto('/mini-app/prompt-tools/?mode=video');
  await expect(page.getByRole('heading', { name: 'Промпт по фото / видео' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Видео', exact: true })).toHaveClass(/active/);
  await expect(page.getByText('Длительность целевой сцены')).toHaveCount(0);

  await page.locator('textarea').fill('Вытащи динамику, камеру и финальный кадр');
  await page.locator("input[type='file']").setInputFiles({
    name: 'IMG_1234.MOV',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('mov-bytes'),
  });
  await expect(page.getByText('Видео загружено · заменить')).toBeVisible();

  await page.getByRole('button', { name: 'Создать промпт' }).click();
  await expect(page.getByText('Готовый кинематографичный промпт')).toBeVisible();
  await expect(page.getByText('Плавный dolly-in')).toBeVisible();
  await expect(page.getByText('• Камера приближается')).toBeVisible();
  await expect(page.getByText('Мягкий контровой свет')).toBeVisible();
  await expect(page.getByText('Тихий городской фон')).toBeVisible();
  await expect(page.getByText('Seedance 2.0')).toBeVisible();

  expect(calls.videoPrompt).toEqual({
    video_url: 'https://cdn.roxy.test/gallery.mov',
    instruction: 'Вытащи динамику, камеру и финальный кадр',
  });
});

test('Seedance prompt mode still shows duration picker', async ({ page }) => {
  await installTelegram(page);
  await mockPromptTools(page);

  await page.goto('/mini-app/prompt-tools/?mode=seedance');
  await expect(page.getByRole('heading', { name: 'Промпт по фото / видео' })).toBeVisible();
  await expect(page.getByText('Длительность целевой сцены')).toBeVisible();
  await expect(page.getByRole('button', { name: '5 сек', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '10 сек', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '15 сек', exact: true })).toBeVisible();
});
