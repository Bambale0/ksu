import { expect, test } from '@playwright/test';

const model = {
  id: 'nano-banana-2',
  title: 'Nano Banana 2',
  family: 'nanobanana',
  media_type: 'image',
  operation: 'generate_or_edit',
  price_rox: '15.00',
  ui_schema: { groups: [], fields: [], defaults: {} },
};

const systemCategory = {
  id: 'trends',
  system_key: 'trends',
  title: 'Тренды',
  description: 'Общий список',
  aliases: [],
  sort_order: 0,
  is_active: true,
  item_count: 0,
  photo_count: 0,
  video_count: 0,
};

const ugcCategory = {
  id: 'ugc',
  title: 'UGC',
  description: 'Отзывы и распаковки',
  aliases: ['ugc', 'review', 'распаковка'],
  sort_order: 10,
  is_active: true,
  item_count: 4,
  photo_count: 3,
  video_count: 1,
};

const adsCategory = {
  id: 'ads',
  title: 'Реклама',
  description: 'Рекламные креативы',
  aliases: ['ads', 'реклама'],
  sort_order: 20,
  is_active: true,
  item_count: 2,
  photo_count: 2,
  video_count: 0,
};

const ugcTrend = {
  id: 'trend_ugc',
  title: 'UGC распаковка',
  is_active: true,
  collection_id: 'ugc',
  payload: {
    media_type: 'video',
    preview_url: '/ugc.mp4',
    model_id: model.id,
    prompt: 'ugc prompt',
    description: 'Живой отзыв о продукте',
    tags: ['ugc', 'review'],
  },
};

const adsTrend = {
  id: 'trend_ads',
  title: 'Рекламный баннер',
  is_active: true,
  collection_id: 'ads',
  payload: {
    media_type: 'image',
    preview_url: '/ads.jpg',
    model_id: model.id,
    prompt: 'ads prompt',
    description: 'Креатив для рекламы',
    tags: ['ads', 'sale'],
  },
};

async function mockAdminHome(page) {
  const state = {
    categories: [systemCategory, ugcCategory, adsCategory],
    assignments: { trend_ugc: 'ugc', trend_ads: 'ads' },
    createdBody: null,
  };

  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'Admin', username: 'admin_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/me') return json({ id: 'admin_1', telegram_id: 777, first_name: 'Admin', username: 'admin_user', balance_rox: '150.00', is_admin: true });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [] });
    if (path === '/api/v1/trends/manage') return json({ items: [ugcTrend, adsTrend], models: [model] });
    if (path === '/api/v1/trend-collections' && method === 'GET') return json({ items: state.categories });
    if (path === '/api/v1/trend-collections/manage' && method === 'GET') {
      return json({ schema_version: 1, initialized: true, collections: state.categories, assignments: state.assignments });
    }
    if (path === '/api/v1/trend-collections/manage' && method === 'POST') {
      state.createdBody = request.postDataJSON();
      const created = {
        id: 'beauty',
        title: state.createdBody.title,
        description: state.createdBody.description,
        aliases: state.createdBody.hashtags,
        sort_order: state.createdBody.sort_order,
        is_active: state.createdBody.is_active,
        item_count: 0,
        photo_count: 0,
        video_count: 0,
      };
      state.categories = [...state.categories, created];
      return json(created, 201);
    }
    if (path.startsWith('/api/v1/trend-collections/manage/items/') && method === 'PUT') {
      const trendId = decodeURIComponent(path.split('/').at(-1));
      const body = request.postDataJSON();
      state.assignments[trendId] = body.collection_id;
      return json({ trend_id: trendId, collection_id: body.collection_id });
    }
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/referrals/stats') return json({});
    if (path === '/api/v1/referrals/rewards' || path === '/api/v1/referrals/invitations') return json({ items: [] });
    return json({ items: [] });
  });

  return state;
}

test('admin can search categories and trends by hashtag, assign a result, and create normalized hashtags', async ({ page }) => {
  const state = await mockAdminHome(page);
  await page.goto('/mini-app/?route=home');

  const folders = page.locator('#roxy-home-trend-folders');
  const manage = folders.getByTestId('trend-category-admin-open');
  await expect(manage).toBeVisible();
  await expect(manage).toHaveText('Управлять');
  await manage.click();

  const dialog = page.getByRole('dialog', { name: 'Управление категориями' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId('trend-category-admin-card-ugc')).toBeVisible();
  await expect(dialog.getByTestId('trend-category-admin-card-ads')).toBeVisible();

  const search = dialog.getByTestId('trend-category-admin-search');
  await search.fill('#UGC');
  await expect(dialog.getByTestId('trend-category-admin-card-ugc')).toBeVisible();
  await expect(dialog.getByTestId('trend-category-admin-card-ads')).toHaveCount(0);
  await expect(dialog.getByTestId('trend-category-admin-trend-trend_ugc')).toBeVisible();
  await expect(dialog.getByTestId('trend-category-admin-trend-trend_ads')).toHaveCount(0);

  await dialog.getByLabel('Категория для UGC распаковка').selectOption('ads');
  await expect.poll(() => state.assignments.trend_ugc).toBe('ads');

  await search.fill('');
  await dialog.getByRole('button', { name: '＋ Новая категория' }).click();
  await dialog.getByLabel('Название').fill('Beauty');
  await dialog.getByLabel('Описание').fill('Макияж и бьюти-креативы');
  await dialog.getByTestId('trend-category-admin-hashtags').fill('#Beauty beauty #BEAUTY, #макияж');
  await dialog.getByTestId('trend-category-admin-save').click();

  await expect.poll(() => state.createdBody).toMatchObject({
    title: 'Beauty',
    description: 'Макияж и бьюти-креативы',
    hashtags: ['beauty', 'макияж'],
    sort_order: 100,
    is_active: true,
  });
  await expect(dialog.getByTestId('trend-category-admin-card-beauty')).toBeVisible();
});

test('category management is hidden from non-admin users', async ({ page }) => {
  await mockAdminHome(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'user_2', telegram_id: 778, balance_rox: '50.00', is_admin: false }),
    });
  });
  await page.goto('/mini-app/?route=home');

  await expect(page.getByTestId('trend-category-admin-open')).toHaveCount(0);
});
