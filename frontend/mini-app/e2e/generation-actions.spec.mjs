import { expect, test } from '@playwright/test';

const sourceUrl = 'https://cdn.roxy.local/source.png';

const imageModel = {
  id: 'nano-banana-edit',
  title: 'Nano Banana Edit',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'image_edit',
  ui_schema: {
    defaults: { aspect_ratio: '1:1', output_format: 'png' },
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'aspect_ratio', label: 'Формат', control: 'combobox', suggestions: ['1:1', '9:16'] },
      { name: 'output_format', label: 'Формат файла', control: 'combobox', suggestions: ['png', 'jpeg'] },
    ],
    groups: [{ id: 'main', title: 'Настройки' }],
  },
};

const repeatModel = {
  id: 'nano-banana-pro',
  title: 'NanoBanana PRO',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  ui_schema: {
    defaults: { aspect_ratio: '1:1', resolution: '1K', output_format: 'png' },
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'aspect_ratio', label: 'Формат', control: 'combobox', suggestions: ['1:1', '9:16'] },
      { name: 'resolution', label: 'Качество', control: 'combobox', suggestions: ['1K', '2K'] },
      { name: 'output_format', label: 'Формат файла', control: 'combobox', suggestions: ['png', 'jpeg'] },
    ],
    groups: [{ id: 'main', title: 'Настройки' }],
  },
};

const animateModel = {
  id: 'grok-video-i2v',
  title: 'Grok Imagine · Image to Video',
  family: 'grok',
  media_type: 'video',
  operation: 'image_to_video',
  ui_schema: {
    defaults: { aspect_ratio: '16:9', duration: 6, resolution: '480p', mode: 'normal' },
    fields: [
      { name: 'prompt', label: 'Промпт', control: 'textarea', required: true },
      { name: 'aspect_ratio', label: 'Формат', control: 'combobox', suggestions: ['16:9', '9:16'] },
      { name: 'duration', label: 'Длительность', control: 'number', min: 1, max: 30 },
      { name: 'resolution', label: 'Качество', control: 'combobox', suggestions: ['480p'] },
    ],
    groups: [{ id: 'main', title: 'Настройки' }],
  },
};

const actionLabels = {
  remix: '✨ Ремикс',
  repeat: '🔁 Ещё вариант',
  edit: '💅 Изменить образ',
  animate: '🎬 Оживить',
  publish: '📤 Опубликовать',
};

function contextFor(action) {
  const generation = {
    id: 'gen_source',
    status: 'succeeded',
    media_type: 'image',
    result_url: sourceUrl,
    model_id: 'nano-banana-pro',
    model_title: 'NanoBanana PRO',
    prompt: 'Портрет в неоновом свете',
    prompt_hidden: false,
    publication_scope: 'private',
  };

  if (action === 'publish') {
    return {
      generation,
      action: { id: action, label: actionLabels[action], derivative: false },
      candidate_models: [],
      defaults: { model_id: null, prompt: '', parameters: {}, billing_seconds: null, input_url: null },
      source_url: sourceUrl,
      source_references: { images: [], videos: [] },
      edit_presets: [],
    };
  }

  const model = action === 'animate' ? animateModel : action === 'repeat' ? repeatModel : imageModel;
  return {
    generation,
    action: { id: action, label: actionLabels[action], derivative: true },
    candidate_models: [model],
    defaults: {
      model_id: model.id,
      prompt: action === 'repeat' ? generation.prompt : '',
      parameters: { ...(model.ui_schema.defaults || {}) },
      billing_seconds: null,
      input_url: action === 'repeat' ? 'https://cdn.roxy.local/original-ref.png' : sourceUrl,
    },
    source_url: sourceUrl,
    source_references: { images: [], videos: [] },
    edit_presets: action === 'edit' ? [
      { id: 'clothes', label: 'Одежда' },
      { id: 'hair', label: 'Причёска' },
      { id: 'background', label: 'Фон' },
      { id: 'custom', label: 'Своё' },
    ] : [],
  };
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockActionApp(page, { rejectContext = false } = {}) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('https://cdn.roxy.local/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path.endsWith('/action-context')) {
      if (rejectContext) return json(route, { detail: 'Action is not available for this generation' }, 409);
      return json(route, contextFor(url.searchParams.get('action')));
    }
    if (/\/api\/v1\/generations\/gen_source\/actions\//.test(path) && method === 'POST') {
      return json(route, { id: 'gen_child', status: 'queued', parent_generation_id: 'gen_source', action_type: 'repeat', cost_rox: '25.00' }, 202);
    }
    if (path === '/api/v1/generations/quote') {
      return json(route, { cost_rox: '25.00', effective_cost_rox: '25.00', cost_rub: '25.00' });
    }
    if (path === '/api/v1/feed/gen_source/publish' && method === 'POST') {
      return json(route, { publication_scope: 'feed', downgraded_to_profile: false });
    }
    if (path === '/api/v1/references') return json(route, { items: [] });

    // Fallbacks keep the ordinary ROXY shell quiet if a derivative submit redirects
    // to History before the test finishes inspecting the request.
    if (path === '/api/v1/me') return json(route, { id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00' });
    if (path === '/api/v1/onboarding') return json(route, { enabled: false, completed: true });
    if (path === '/api/v1/generations/models') return json(route, { models: [repeatModel, animateModel], families: [] });
    if (path === '/api/v1/generations') return json(route, { items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json(route, { items: [] });
    if (path === '/api/v1/trends') return json(route, { items: [] });
    if (path === '/api/v1/prompt-tools') return json(route, { admin_free: false, items: [] });
    if (path === '/api/v1/referrals/stats') return json(route, { referral_link: '', first_line: 0, second_line: 0, partner_balance_rub: '0.00', total_earned_rub: '0.00' });
    return json(route, {});
  });
}

async function openAction(page, action) {
  await page.goto(`/mini-app/?route=generation-action&generation=gen_source&action=${action}`);
  await expect(page.getByText(actionLabels[action]).first()).toBeVisible();
  await expect(page.getByAltText('Исходная генерация')).toBeVisible();
}

test('Remix opens exact source, quotes and submits an explicit derivative', async ({ page }) => {
  await mockActionApp(page);
  await openAction(page, 'remix');
  await expect(page.getByRole('heading', { name: 'Что изменить?' })).toBeVisible();
  await page.getByPlaceholder('Например: сделай вечерний свет и красное платье').fill('Сделай платье синим');
  await expect(page.getByText('25 ROX')).toBeVisible();

  const submitted = page.waitForRequest((request) => request.url().includes('/generations/gen_source/actions/remix') && request.method() === 'POST');
  await page.getByRole('button', { name: /Ремикс/ }).last().click();
  const request = await submitted;
  const body = request.postDataJSON();
  expect(body.model_id).toBe('nano-banana-edit');
  expect(body.prompt).toBe('Сделай платье синим');
});

test('Repeat restores the previous prompt and compatible settings explicitly', async ({ page }) => {
  await mockActionApp(page);
  await openAction(page, 'repeat');
  await expect(page.getByRole('textbox')).toHaveValue('Портрет в неоновом свете');
  await expect(page.getByLabel('Качество')).toHaveValue('1K');
  await expect(page.getByText('Описание и подходящие настройки перенесены из выбранной работы.')).toBeVisible();
});

test('Edit exposes focused presets while keeping the source result fixed', async ({ page }) => {
  await mockActionApp(page);
  await openAction(page, 'edit');
  await expect(page.getByRole('heading', { name: 'Как изменить образ?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Одежда' })).toBeVisible();
  await page.getByRole('button', { name: 'Причёска' }).click();
  await page.getByPlaceholder('Опиши только нужное изменение').fill('Длинные рыжие волосы');
  await expect(page.getByText('25 ROX')).toBeVisible();
});

test('Animate opens an I2V model with the generated image as the source', async ({ page }) => {
  await mockActionApp(page);
  await openAction(page, 'animate');
  await expect(page.getByRole('heading', { name: 'Как оживить кадр?' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Grok Imagine · Image to Video' })).toBeVisible();
  await page.getByPlaceholder('Например: плавный поворот головы, лёгкое движение камеры').fill('Лёгкий поворот головы');
  await expect(page.getByText('25 ROX')).toBeVisible();
});

test('Publish controls target the exact generation and preserve hidden references', async ({ page }) => {
  await mockActionApp(page);
  await openAction(page, 'publish');
  await page.getByRole('button', { name: 'В профиль' }).click();

  const published = page.waitForRequest((request) => request.url().endsWith('/api/v1/feed/gen_source/publish') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Опубликовать' }).click();
  const request = await published;
  expect(request.postDataJSON()).toEqual({ publication_scope: 'profile', prompt_visible: false, references_visible: false });
});

test('Unsupported derivative deep link degrades to a safe action error screen', async ({ page }) => {
  await mockActionApp(page, { rejectContext: true });
  await page.goto('/mini-app/?route=generation-action&generation=gen_source&action=remix');
  await expect(page.getByRole('heading', { name: 'Действие недоступно' })).toBeVisible();
  await expect(page.getByText('Action is not available for this generation')).toBeVisible();
});
