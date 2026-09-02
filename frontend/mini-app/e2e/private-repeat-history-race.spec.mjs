import { expect, test } from '@playwright/test';

const aId = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa';
const bId = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb';
const aImage = 'https://cdn.roxy.local/work-a.png';
const bImage = 'https://cdn.roxy.local/work-b.png';
const aPrompt = 'Промпт именно работы A';
const bPrompt = 'Новый промпт работы B';

function model() {
  return {
    id: 'nano-banana-2',
    title: 'Nano Banana 2',
    family: 'nano-banana',
    operation: 'auto',
    media_type: 'image',
    price_rox: '25.00',
    ui_schema: { defaults: { prompt: '' }, fields: [] },
  };
}

function generation(id, resultUrl, prompt, createdAt) {
  return {
    id,
    status: 'succeeded',
    prompt,
    prompt_hidden: false,
    prompt_actions_allowed: true,
    model: model(),
    result_url: resultUrl,
    result_urls: [resultUrl],
    media: [{ url: resultUrl, content_type: 'image/png' }],
    created_at: createdAt,
    publication_scope: 'private',
  };
}

const workA = generation(aId, aImage, aPrompt, '2026-09-02T08:00:00Z');
const workB = generation(bId, bImage, bPrompt, '2026-09-02T08:01:00Z');

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.__copiedText = '';
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        async writeText(value) { window.__copiedText = String(value); },
      },
    });
    window.Telegram = {
      WebApp: {
        initData: 'query_id=history-race&hash=test',
        initDataUnsafe: { user: { id: 999, first_name: 'History' } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockRace(page) {
  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/me') return json({ id: 'history-user', telegram_id: 999, first_name: 'History', balance_rox: '340.00', created_at: '2026-09-02T00:00:00Z', is_active: true });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json({ models: [model()], families: [] });
    if (path === '/api/v1/feed' || path === '/api/v1/trends') return json({ items: [] });

    if (path === '/api/v1/generations') {
      const limit = url.searchParams.get('limit');
      if (limit === '12') return json({ items: [], has_more: false, next_before: null });
      if (limit === '24' || limit === '50') {
        // The rendered DOM below is work A, while both independent enhancers see
        // a newer snapshot where B has been inserted before A. This keeps the
        // race deterministic even when React dev/StrictMode repeats requests.
        return json({ items: [workB, workA], has_more: false, next_before: null });
      }
      return json({ items: [], has_more: false, next_before: null });
    }

    if (path === `/api/v1/generations/${aId}/repeat-link` && request.method() === 'POST') {
      return json({ link: 'https://t.me/roxy_bot/app?startapp=repeat_a', payload: 'repeat_a', private: true });
    }
    if (path === `/api/v1/generations/${bId}/repeat-link` && request.method() === 'POST') {
      return json({ link: 'https://t.me/roxy_bot/app?startapp=repeat_b', payload: 'repeat_b', private: true });
    }
    if (path === `/api/v1/generations/${aId}`) return json(workA);
    if (path === `/api/v1/generations/${bId}`) return json(workB);
    return json({ items: [] });
  });
}

async function injectRenderedWorkA(page) {
  await page.evaluate(({ image }) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'history-card';
    card.innerHTML = `
      <span class="media-thumb"><img src="${image}" alt="" /></span>
      <div><strong>Nano Banana 2</strong><small>02 сент. · 11:00 · Готово</small></div>
      <span class="status succeeded">Готово</span>
    `;
    document.body.appendChild(card);
  }, { image: aImage });
}

async function injectPreviewA(page) {
  await page.evaluate(({ image, prompt }) => {
    const preview = document.createElement('div');
    preview.className = 'preview-card';
    preview.innerHTML = `
      <div class="preview-media"><img src="${image}" alt="Результат" /></div>
      <div class="preview-copy">
        <span class="kicker">Моя работа</span>
        <h2>Nano Banana 2</h2>
        <p class="prompt-copy">${prompt}</p>
        <div class="preview-actions"></div>
      </div>
    `;
    document.body.appendChild(preview);
  }, { image: aImage, prompt: aPrompt });
}

test('History enhancers keep the rendered work identity when a newer generation shifts their snapshots', async ({ page }) => {
  await installTelegram(page);
  await mockRace(page);
  await page.goto('/mini-app/?route=home', { waitUntil: 'domcontentloaded' });

  // Keep RoxyApp out of the identity setup. The synthetic DOM represents the
  // already-rendered snapshot A; the enhancers deliberately receive [B, A].
  await injectRenderedWorkA(page);
  const card = page.locator('.history-card').first();
  await expect(card.locator('img')).toHaveAttribute('src', aImage);

  const copyPrompt = card.getByRole('button', { name: 'Скопировать промпт', exact: true });
  await expect(copyPrompt).toContainText(aPrompt);
  await expect(copyPrompt).not.toContainText(bPrompt);
  await expect(copyPrompt).toHaveAttribute('data-generation-id', aId);
  await copyPrompt.click();
  await expect.poll(() => page.evaluate(() => window.__copiedText)).toBe(aPrompt);

  // Old repeat-link code remembered history-card index 0 here, which points to
  // B in the enhancer snapshot. The fixed code never treats position as identity.
  await card.locator('img').click();
  await injectPreviewA(page);

  const preview = page.locator('.preview-card').first();
  await expect(preview).toBeVisible();
  await expect(preview.getByText(aPrompt, { exact: true })).toBeVisible();

  const repeat = preview.getByRole('button', { name: 'Скопировать приватную ссылку на повтор' });
  await expect(repeat).toBeVisible();
  await expect(repeat).toHaveAttribute('data-private-repeat-link', aId);

  const request = page.waitForRequest((candidate) => candidate.method() === 'POST' && candidate.url().includes('/repeat-link'));
  await repeat.click();
  const posted = await request;
  expect(new URL(posted.url()).pathname).toBe(`/api/v1/generations/${aId}/repeat-link`);
  await expect.poll(() => page.evaluate(() => window.__copiedText)).toBe('https://t.me/roxy_bot/app?startapp=repeat_a');
});
