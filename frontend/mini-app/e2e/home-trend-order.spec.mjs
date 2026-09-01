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

const trend = {
  id: 'trend_home_order',
  title: 'Актуальный тренд',
  description: 'Проверка верхней ленты',
  media_type: 'image',
  model: { id: model.id, title: model.title, family: model.family },
  cost_rox: '15.00',
  reference_requirements: { kind: 'none', min: 0, max: 0 },
  prompt_hidden: true,
  prompt_actions_allowed: false,
};

const birthdayTrend = {
  ...trend,
  id: 'trend_birthday',
  title: 'Поздравление с днём рождения',
  description: 'Шаблон из папки',
};

const birthdayVideoTrend = {
  ...birthdayTrend,
  id: 'trend_birthday_video',
  title: 'Видео-поздравление',
  media_type: 'video',
};

async function mockHome(page, { delayedFolderTabs = false } = {}) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });

  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path === '/api/v1/generations/models') return json({ models: [model], families: [] });
    if (path === '/api/v1/me') return json({ id: 'user_1', telegram_id: 777, first_name: 'QA', username: 'qa_user', balance_rox: '150.00', is_admin: false });
    if (path === '/api/v1/generations') return json({ items: [], has_more: false, next_before: null });
    if (path === '/api/v1/feed') return json({ items: [] });
    if (path === '/api/v1/trends') return json({ items: [trend] });
    if (path === '/api/v1/trend-collections') return json({ items: [
      { id: 'trends', system_key: 'trends', title: 'Тренды', description: 'Instagram', sort_order: 0, is_active: true, item_count: 1, photo_count: 1, video_count: 0 },
      { id: 'birthday', system_key: 'birthday', title: 'День рождения', description: 'Праздничные идеи', sort_order: 10, is_active: true, item_count: 2, photo_count: 1, video_count: 1 },
    ] });
    if (path === '/api/v1/trend-collections/birthday/items') {
      const mediaType = url.searchParams.get('media_type');
      if (delayedFolderTabs) await new Promise((resolve) => setTimeout(resolve, mediaType === 'image' ? 180 : 20));
      return json({
        collection: { id: 'birthday', title: 'День рождения' },
        items: mediaType === 'video' ? [birthdayVideoTrend] : [birthdayTrend],
      });
    }
    if (path === '/api/v1/onboarding') return json({ enabled: false, completed: true });
    if (path === '/api/v1/referrals/stats') return json({});
    if (path === '/api/v1/referrals/rewards' || path === '/api/v1/referrals/invitations') return json({ items: [] });
    return json({ items: [] });
  });
}

test('home shows live trends and then category cards without an extra section heading', async ({ page }) => {
  await mockHome(page);
  await page.goto('/mini-app/?route=home');

  const home = page.locator('.home-screen');
  const promo = home.locator(':scope > .promo-slider');
  const trends = home.locator(':scope > #roxy-home-live-trends');
  const folders = home.locator(':scope > #roxy-home-trend-folders');

  await expect(home).toBeVisible();
  await expect(promo).toBeVisible();
  await expect(trends.locator('.live-trend-card', { hasText: trend.title })).toBeVisible();
  await expect(folders.getByRole('button', { name: /День рождения/ })).toBeVisible();
  await expect(folders.locator('.home-trend-folders-head')).toHaveCount(0);
  await expect(folders.getByRole('heading', { name: 'Папки трендов' })).toHaveCount(0);

  await expect.poll(() => home.evaluate((node) => {
    const promo = node.querySelector(':scope > .promo-slider');
    const trends = node.querySelector(':scope > #roxy-home-live-trends');
    const folders = node.querySelector(':scope > #roxy-home-trend-folders');
    return {
      trendsAfterPromo: Boolean(promo && trends && promo.nextElementSibling === trends),
      foldersAfterTrends: Boolean(trends && folders && trends.nextElementSibling === folders),
    };
  })).toEqual({ trendsAfterPromo: true, foldersAfterTrends: true });

  await folders.getByRole('button', { name: /День рождения/ }).click();
  await expect(folders.getByRole('heading', { name: 'День рождения' })).toBeVisible();
  await expect(folders.getByRole('button', { name: /Категории/ })).toBeVisible();
  await expect(folders.getByRole('tab', { name: /Фото/ })).toBeVisible();
  await expect(folders.getByRole('tab', { name: /Видео/ })).toBeVisible();
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayTrend.title })).toBeVisible();
});

test('catalog keeps live trends and category cards directly below promo before feature catalog', async ({ page }) => {
  await mockHome(page);
  await page.goto('/mini-app/?route=catalog');

  const catalog = page.locator('.roxy-catalog-feature-mode');
  const trends = catalog.locator(':scope > #roxy-live-trends');
  const folders = catalog.locator(':scope > #roxy-catalog-trend-folders');
  await expect(catalog).toBeVisible();
  await expect(trends.locator('.live-trend-card', { hasText: trend.title })).toBeVisible();
  await expect(folders.getByRole('button', { name: /День рождения/ })).toBeVisible();
  await expect(folders.locator('.home-trend-folders-head')).toHaveCount(0);
  await expect(folders.getByRole('heading', { name: 'Папки трендов' })).toHaveCount(0);

  await expect.poll(() => catalog.evaluate((screen) => {
    const children = Array.from(screen.children);
    const promo = screen.querySelector(':scope > .promo-carousel');
    const trends = screen.querySelector(':scope > #roxy-live-trends');
    const folders = screen.querySelector(':scope > #roxy-catalog-trend-folders');
    const foldersIndex = folders ? children.indexOf(folders) : -1;
    const featureHub = screen.querySelector(':scope > #roxy-catalog-feature-hub');
    const featureHubIndex = featureHub ? children.indexOf(featureHub) : -1;
    return {
      trendsDirectlyAfterPromo: Boolean(promo && trends && promo.nextElementSibling === trends),
      foldersDirectlyAfterTrends: Boolean(trends && folders && trends.nextElementSibling === folders),
      featureCatalogAfterFolders: foldersIndex >= 0 && featureHubIndex > foldersIndex,
    };
  })).toEqual({
    trendsDirectlyAfterPromo: true,
    foldersDirectlyAfterTrends: true,
    featureCatalogAfterFolders: true,
  });

  await folders.getByRole('button', { name: /День рождения/ }).click();
  const back = folders.getByRole('button', { name: /Категории/ });
  await expect(folders.getByRole('heading', { name: 'День рождения' })).toBeVisible();
  await expect(back).toBeVisible();
  await expect.poll(() => back.evaluate((node) => getComputedStyle(node).borderRadius)).toBe('999px');
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayTrend.title })).toBeVisible();
});

test('catalog ignores stale folder responses when switching photo and video tabs quickly', async ({ page }) => {
  await mockHome(page, { delayedFolderTabs: true });
  await page.goto('/mini-app/?route=catalog');

  const folders = page.locator('#roxy-catalog-trend-folders');
  await folders.getByRole('button', { name: /День рождения/ }).click();
  await folders.getByRole('tab', { name: /Видео/ }).click();

  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayVideoTrend.title })).toBeVisible();
  await page.waitForTimeout(220);
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayVideoTrend.title })).toBeVisible();
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayTrend.title })).toHaveCount(0);
});

test('home ignores stale folder responses when switching photo and video tabs quickly', async ({ page }) => {
  await mockHome(page, { delayedFolderTabs: true });
  await page.goto('/mini-app/?route=home');

  const folders = page.locator('#roxy-home-trend-folders');
  await folders.getByRole('button', { name: /День рождения/ }).click();
  await folders.getByRole('tab', { name: /Видео/ }).click();

  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayVideoTrend.title })).toBeVisible();
  await page.waitForTimeout(220);
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayVideoTrend.title })).toBeVisible();
  await expect(folders.locator('.home-trend-folder-item', { hasText: birthdayTrend.title })).toHaveCount(0);
});
