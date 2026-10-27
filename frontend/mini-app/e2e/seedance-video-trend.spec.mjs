
import { expect, test } from '@playwright/test';

const ID = '12345678-1234-4234-8234-123456789abc';
for (const images of [0, 1]) {
  test('video trend requires verified typed media before run, images=' + images, async ({ page }) => {
    const runs = [];
    const errors = [];
    let uploadIndex = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.Telegram = { WebApp: {
        initData: 'query_id=video-trend&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      } };
    });
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (path === '/api/v1/trends/' + ID && request.method() === 'GET') return json({
        id: ID, title: 'Видео-сценарий', media_type: 'video', preview_url: null,
        model: { id: 'seedance-2.5', title: 'Seedance 2.5' }, cost_rox: '100.00',
        reference_requirements: { kind: images ? 'multimodal' : 'video', min: images + 1, max: images + 1,
          image: { min: images, max: images }, video: { min: 1, max: 1 } },
      });
      if (path.endsWith('/run')) { runs.push(request.postDataJSON()); return json({ id: 'result', status: 'queued' }, 202); }
      if (request.method() === 'POST') {
        const video = request.postDataBuffer()?.includes(Buffer.from('video/mp4'));
        uploadIndex += 1;
        return json({ url: 'https://media.example/upload-' + uploadIndex + (video ? '.mp4' : '.png'),
          reference: { kind: video ? 'video' : 'image' }, probe_status: 'ready' });
      }
      if (path === '/api/v1/me') return json({ id: 'viewer', telegram_id: 777, first_name: 'QA', balance_rox: '1000' });
      if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
      if (path === '/api/v1/generations/models') return json({ models: [], families: [] });
      return json({ items: [], has_more: false });
    });
    await page.goto('/mini-app/trend/?id=' + ID);
    const run = page.getByRole('button', { name: 'Сгенерировать · 100 ROX', exact: true });
    await expect(run).toBeDisabled();
    expect(runs).toEqual([]);
    if (images) {
      await page.locator('input[accept="image/*"]').setInputFiles({ name: 'face.png', mimeType: 'image/png', buffer: Buffer.from('synthetic image') });
      await expect(page.getByText('face.png', { exact: true })).toBeVisible();
      await expect(run).toBeDisabled();
    }
    const video = page.getByLabel('Видеореференсы тренда');
    await expect(video).toHaveAttribute('accept', 'video/mp4,video/quicktime');
    await video.setInputFiles({ name: 'motion.mp4', mimeType: 'video/mp4', buffer: Buffer.from('synthetic video') });
    await expect(page.getByText('motion.mp4', { exact: true })).toBeVisible();
    await expect(run).toBeEnabled();
    await page.getByRole('button', { name: 'Удалить видео 1', exact: true }).click();
    await expect(run).toBeDisabled();
    await video.setInputFiles({ name: 'motion.mp4', mimeType: 'video/mp4', buffer: Buffer.from('synthetic video') });
    await expect(run).toBeEnabled();
    await run.click();
    await expect.poll(() => runs.length).toBe(1);
    expect(runs[0].reference_urls).toHaveLength(images);
    expect(runs[0].video_reference_urls).toHaveLength(1);
    expect(runs[0].video_reference_urls[0]).toContain('.mp4');
    expect(errors).toEqual([]);
  });
}
