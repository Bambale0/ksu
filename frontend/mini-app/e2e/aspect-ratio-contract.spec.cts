import { expect, test, type Page } from '@playwright/test';
import {
  aspectRatioError,
  explicitAspectRatioOptions,
  normalizeAspectRatioFields,
  normalizeAspectRatioValues,
  selectedAspectRatio,
} from '../lib/aspect-ratio';

async function installTelegram(page: Page) {
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=aspect-ratio&hash=test', initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
}

test('contract: removes only literal automatic aspect ratios', () => {
  expect(explicitAspectRatioOptions(['auto', 'AUTO', ' auto ', '1:1', '9:16', 'adaptive']))
    .toEqual(['1:1', '9:16', 'adaptive']);
  const schema = {
    defaults: { aspect_ratio: 'AuTo', audio_setting: 'auto', duration: -1 },
    fields: [
      { name: 'aspect_ratio', label: 'Формат', suggestions: ['auto', '1:1', '9:16'] },
      { name: 'audio_setting', label: 'Звук', suggestions: ['auto', 'on', 'off'] },
      { name: 'duration', label: 'Длительность', suggestions: [-1, 5, 10] },
    ],
  };
  expect(normalizeAspectRatioFields(schema)[0]).toMatchObject({ required: true, suggestions: ['1:1', '9:16'] });
  expect(normalizeAspectRatioFields(schema)[1]).toEqual(schema.fields[1]);
  expect(normalizeAspectRatioFields(schema)[2]).toEqual(schema.fields[2]);
  expect(normalizeAspectRatioValues(schema.defaults)).toEqual({ aspect_ratio: '', audio_setting: 'auto', duration: -1 });
  expect(schema.defaults.aspect_ratio).toBe('AuTo');
});

test('contract: stale values require selection without silently choosing square', () => {
  const field = { name: 'aspect_ratio', label: 'Формат', suggestions: ['1:1', '9:16'] };
  expect(selectedAspectRatio({ aspect_ratio_options: ['1:1', '9:16'], default_aspect_ratio: 'auto' })).toBe('');
  expect(selectedAspectRatio({ aspect_ratio_options: ['1:1', '9:16'], default_aspect_ratio: '9:16' })).toBe('9:16');
  expect(aspectRatioError(field, normalizeAspectRatioValues({ aspect_ratio: 'AUTO' }).aspect_ratio)).toBeTruthy();
  expect(aspectRatioError(field, 'auto')).toBeTruthy();
  expect(aspectRatioError(field, '9:16')).toBe('');
});

test('contract: source-derived omission and adaptive duration/audio remain valid', () => {
  // Public Seedance controls list fixed ratios while saved recipes may carry adaptive.
  const field = { name: 'aspect_ratio', label: 'Формат', suggestions: ['16:9', '9:16'] };
  expect(aspectRatioError(field, undefined)).toBe('');
  expect(aspectRatioError(field, null)).toBe('');
  expect(aspectRatioError(field, 'adaptive')).toBe('');
  expect(normalizeAspectRatioValues({ audio_setting: 'auto', duration: 0 })).toEqual({ audio_setting: 'auto', duration: 0 });
});

test('Create clears a legacy automatic ratio and quotes only the explicit choice', async ({ page }) => {
  const quotes: Array<{ parameters: Record<string, unknown> }> = [];
  const model = {
    id: 'schema-driven-image-model', title: 'Image model', family: 'image', media_type: 'image', operation: 'text_to_image',
    ui_schema: {
      defaults: { aspect_ratio: 'AUTO' },
      fields: [
        { name: 'prompt', label: 'Описание', control: 'textarea', required: true },
        { name: 'aspect_ratio', label: 'Соотношение сторон', control: 'combobox', suggestions: ['auto', '1:1', '9:16'] },
      ],
    },
  };
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: 'query_id=aspect-ratio&hash=test', initDataUnsafe: { user: { id: 777, first_name: 'QA' } },
      ready() {}, expand() {}, onEvent() {}, offEvent() {},
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
    } };
  });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/generations/quote') {
      quotes.push(request.postDataJSON());
      if (quotes.length > 1) await new Promise((resolve) => setTimeout(resolve, 500));
      return json({ model_id: model.id, cost_rox: '12', effective_cost_rox: '12' });
    }
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    return json({ items: [] });
  });
  await page.goto('/mini-app/?route=create');
  await page.locator('textarea').first().fill('Портрет у окна');
  const ratio = page.getByLabel('Соотношение сторон');
  await expect(ratio).toHaveValue('');
  await expect(ratio.locator('option')).toHaveText(['Выберите', '1:1', '9:16']);
  await expect(page.locator('.create-summary button.primary')).toBeDisabled();
  await page.waitForTimeout(400);
  expect(quotes).toEqual([]);
  await ratio.selectOption('9:16');
  await expect.poll(() => quotes.length).toBeGreaterThan(0);
  expect(quotes.at(-1)?.parameters.aspect_ratio).toBe('9:16');
  const create = page.locator('.create-summary button.primary');
  await expect(create).toBeEnabled();
  await ratio.selectOption('1:1');
  await expect(create).toBeDisabled();
  await expect.poll(() => quotes.length).toBe(2);
  await ratio.selectOption('');
  await page.waitForTimeout(650);
  await expect(create).toBeDisabled();
  await expect(page.locator('.quote-box strong')).toHaveText('—');
});

test('Batch requires an explicit ratio before uploads and pricing', async ({ page }) => {
  await installTelegram(page);
  const quotes: Array<{ parameters: Record<string, unknown> }> = [];
  let uploads = 0;
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/generations/models') return json({ models: [{
      id: 'batch-image-model', title: 'Batch image', media_type: 'image', family: 'image', operation: 'image_edit', known_fields: ['image_urls', 'aspect_ratio'],
      ui_schema: { defaults: { aspect_ratio: 'auto' }, fields: [{ name: 'aspect_ratio', label: 'Соотношение сторон', suggestions: ['auto', '4:3', '9:16'] }] },
    }], families: [] });
    if (path === '/api/v1/uploads/kie') {
      uploads += 1;
      return json({ url: `https://media.example.test/photo-${uploads}.jpg` });
    }
    if (path === '/api/v1/batch-generations/quote') {
      quotes.push(route.request().postDataJSON());
      return json({ input_count: 2, per_item_cost_credits: '12', total_cost_credits: '24' });
    }
    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    return json({ items: [] });
  });
  await page.goto('/mini-app/batch/');
  await page.locator('input[type="file"]').setInputFiles([
    { name: 'first.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('first') },
    { name: 'second.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('second') },
  ]);
  const ratio = page.getByLabel('Соотношение сторон');
  await expect(ratio).toHaveValue('');
  await expect(ratio.locator('option')).toHaveText(['Выберите', '4:3', '9:16']);
  await page.getByRole('button', { name: 'Рассчитать стоимость' }).click();
  await expect(page.getByRole('alert')).toHaveText('Выберите соотношение сторон');
  expect(uploads).toBe(0);
  expect(quotes).toEqual([]);
  await ratio.selectOption('4:3');
  await page.getByRole('button', { name: 'Рассчитать стоимость' }).click();
  await expect.poll(() => quotes.length).toBe(1);
  expect(quotes[0].parameters.aspect_ratio).toBe('4:3');
});

test('Legacy batch retry preserves the selected ratio and an uncertain attempt across refresh and reload', async ({ page }) => {
  await installTelegram(page);
  const quoteRatios: Array<string | null> = [];
  const attempts: Array<{ key?: string; body: unknown }> = [];
  let reads = 0;
  const job = {
    id: 'legacy-batch', model_id: 'server-image-model', prompt: 'Saved recipe', status: 'partial',
    input_count: 2, succeeded_count: 1, failed_count: 1, active_count: 0, progress_percent: 100, total_charged_credits: '12', items: [],
    aspect_ratio_options: ['auto', '4:3', '9:16'], aspect_ratio_required: true, default_aspect_ratio: null,
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.pathname === '/api/v1/generations/models') return json({ models: [], families: [] });
    if (url.pathname === '/api/v1/batch-generations') {
      reads += 1;
      return json({ items: [job] });
    }
    if (url.pathname === '/api/v1/batch-generations/legacy-batch/retry-quote') {
      quoteRatios.push(url.searchParams.get('aspect_ratio'));
      await new Promise((resolve) => setTimeout(resolve, 300));
      return json({ failed_count: 1, total_cost_credits: '12' });
    }
    if (url.pathname === '/api/v1/batch-generations/legacy-batch/retry') {
      attempts.push({ key: request.headers()['idempotency-key'], body: request.postDataJSON() });
      if (attempts.length === 1) return json({ detail: 'Ответ на повтор потерян' }, 503);
      return json({ ...job, status: 'running', failed_count: 0, active_count: 1, retried_count: 1 });
    }
    if (url.pathname === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (url.pathname === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    return json({ items: [] });
  });
  await page.goto('/mini-app/batch/');
  const card = page.locator('.tool-result-card');
  const ratio = card.getByLabel('Соотношение сторон');
  const retry = card.getByRole('button', { name: 'Повторить ошибки', exact: true });
  await expect(ratio).toHaveValue('');
  await expect(ratio.locator('option')).toHaveText(['Выберите', '4:3', '9:16']);
  await expect(retry).toBeDisabled();
  expect(quoteRatios).toEqual([]);
  await ratio.selectOption('4:3');
  await ratio.selectOption('9:16');
  await retry.click();
  await expect(ratio).toBeDisabled();
  await expect(page.getByRole('alert')).toHaveText('Ответ на повтор потерян');
  expect(quoteRatios).toEqual(['9:16']);
  expect(attempts).toHaveLength(1);
  expect(attempts[0].body).toEqual({ aspect_ratio: '9:16' });
  expect(attempts[0].key).toBeTruthy();

  await page.getByRole('button', { name: 'Обновить', exact: true }).click();
  await expect.poll(() => reads).toBe(2);
  await expect(ratio).toBeDisabled();
  await expect(ratio).toHaveValue('9:16');
  await page.reload();
  await expect.poll(() => reads).toBe(3);
  await expect(ratio).toBeDisabled();
  await expect(ratio).toHaveValue('9:16');
  await card.getByRole('button', { name: 'Повторить тот же запрос', exact: true }).click();
  await expect.poll(() => attempts.length).toBe(2);
  expect(attempts[1]).toEqual(attempts[0]);
  expect(quoteRatios).toEqual(['9:16']);
});

for (const scenario of ['hd', 'edit']) {
  test(`AI Reference ${scenario} quotes and runs the same explicit ratio`, async ({ page }) => {
    await installTelegram(page);
    const quotes: Array<{ aspect_ratio?: string }> = [];
    const runs: Array<{ aspect_ratio?: string }> = [];
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (path === '/api/v1/ai-reference/options') {
        expect(new URL(request.url()).searchParams.get('scenario')).toBe(scenario);
        return json({ model_id: 'server-image-model', aspect_ratio_options: ['auto', '4:3', '9:16'], aspect_ratio_required: true, default_aspect_ratio: null });
      }
      if (path === '/api/v1/uploads/kie') return json({ url: 'https://media.example.test/portrait.jpg' });
      if (path === '/api/v1/ai-reference/quote') {
        quotes.push(request.postDataJSON());
        if (quotes.length > 1) await new Promise((resolve) => setTimeout(resolve, 500));
        return json({ cost_rox: '12', effective_cost_rox: '12', admin_free: false });
      }
      if (path === '/api/v1/ai-reference/run') {
        runs.push(request.postDataJSON());
        return json({ id: 'reference-result', status: 'queued' });
      }
      if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
      if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
      return json({ items: [] });
    });
    await page.goto(`/mini-app/ai-reference/?scenario=${scenario}`);
    await page.locator('input[type="file"]').setInputFiles({ name: 'portrait.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('photo') });
    if (scenario === 'edit') await page.getByLabel('Что изменить?').fill('Добавь дневной свет');
    const ratio = page.getByLabel('Соотношение сторон');
    await expect(ratio).toHaveValue('');
    await expect(ratio.locator('option')).toHaveText(['Выберите', '4:3', '9:16']);
    const run = page.locator('.ai-ref-run');
    await expect(run).toBeDisabled();
    expect(quotes).toEqual([]);
    await ratio.selectOption('4:3');
    await expect(run).toBeEnabled();
    expect(quotes.at(-1)?.aspect_ratio).toBe('4:3');
    await ratio.selectOption('9:16');
    await expect(run).toBeDisabled();
    await expect(run).toBeEnabled();
    await run.click();
    await expect.poll(() => runs.length).toBe(1);
    expect(quotes.at(-1)?.aspect_ratio).toBe('9:16');
    expect(runs[0].aspect_ratio).toBe('9:16');
  });
}

for (const defaultRatio of ['AUTO', '9:16']) {
test(`Remix ${defaultRatio === 'AUTO' ? 'clears a legacy automatic ratio' : 'preserves an inherited explicit ratio'}`, async ({ page }) => {
  await installTelegram(page);
  const quotes: Array<{ aspect_ratio?: string }> = [];
  const runs: Array<{ aspect_ratio?: string }> = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/v1/feed/source/remix/prepare') return json({
      source_generation_id: 'source', source_feed_gen_id: 'source', surface: 'feed', model_id: 'image', effective_model_id: 'image', model_title: 'Повтор изображения',
      prompt: 'Портрет', prompt_hidden: false, prompt_editable: true, settings: {},
      aspect_ratio_options: ['auto', '4:3', '9:16'], aspect_ratio_required: true, default_aspect_ratio: defaultRatio,
      reference_requirements: { image_count: 0, video_count: 0, audio_count: 0, required: false },
    });
    if (path === '/api/v1/feed/source/remix/quote') {
      quotes.push(request.postDataJSON());
      return json({ cost_rox: '12', admin_free: false });
    }
    if (path === '/api/v1/feed/source/remix/launch') {
      runs.push(request.postDataJSON());
      return json({ id: 'remix-result', status: 'queued' });
    }
    if (path === '/api/v1/me') return json({ id: 'user-1', telegram_id: 777, first_name: 'QA', balance_rox: '100' });
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    return json({ items: [] });
  });
  await page.goto('/mini-app/remix/?source=source&surface=feed');
  const ratio = page.getByLabel('Соотношение сторон');
  await expect(ratio).toHaveValue(defaultRatio === 'AUTO' ? '' : defaultRatio);
  await expect(ratio.locator('option')).toHaveText(['Выберите', '4:3', '9:16']);
  if (defaultRatio === 'AUTO') {
    const run = page.getByRole('button', { name: 'Повторить', exact: true });
    await expect(run).toBeDisabled();
    expect(quotes).toEqual([]);
    await ratio.selectOption('4:3');
  }
  const pricedRun = page.getByRole('button', { name: 'Повторить · 12 ROX' });
  await expect(pricedRun).toBeEnabled();
  await pricedRun.click();
  await expect.poll(() => runs.length).toBe(1);
  const expectedRatio = defaultRatio === 'AUTO' ? '4:3' : defaultRatio;
  expect(quotes.at(-1)?.aspect_ratio).toBe(expectedRatio);
  expect(runs[0].aspect_ratio).toBe(expectedRatio);
});
}
