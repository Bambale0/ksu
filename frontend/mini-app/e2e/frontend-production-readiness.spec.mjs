import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.__supportTelegramUrl = '';
    window.Telegram = {
      WebApp: {
        initData: 'query_id=frontend-audit&hash=test',
        initDataUnsafe: { user: { id: 777, first_name: 'QA', username: 'qa_user' } },
        ready() {}, expand() {}, close() {}, onEvent() {}, offEvent() {}, openLink() {},
        openTelegramLink(url) { window.__supportTelegramUrl = url; },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}


async function expectTouchTargets(page) {
  const undersized = await page.locator('button:visible').evaluateAll((buttons) => buttons
    .map((button) => {
      const rect = button.getBoundingClientRect();
      return {
        label: button.getAttribute('aria-label') || button.textContent?.trim() || button.className || 'button',
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10,
      };
    })
    .filter((item) => item.width < 43.5 || item.height < 43.5));
  expect(undersized).toEqual([]);
}

async function mockMe(page) {
  await page.route('**/api/v1/me', (route) => json(route, {
    id: 'user_1',
    telegram_id: 777,
    first_name: 'QA',
    username: 'qa_user',
    balance_rox: '150.00',
  }));
}

test('settings never exposes editable defaults before preferences load and can retry a failed load', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  let attempts = 0;
  await page.route('**/api/v1/me/preferences', async (route) => {
    if (route.request().method() !== 'GET') {
      return json(route, {
        ui_language: 'en',
        notifications_enabled: false,
        marketing_notifications: false,
        profile_discoverable: true,
      });
    }
    attempts += 1;
    if (attempts === 1) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      return json(route, { detail: 'internal preference storage exploded' }, 503);
    }
    return json(route, {
      ui_language: 'en',
      notifications_enabled: false,
      marketing_notifications: false,
      profile_discoverable: true,
    });
  });

  await page.goto('/mini-app/settings/');
  await expect(page.getByText('Загружаем настройки…')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled();

  await expect(page.getByRole('alert')).toContainText('Сервис временно недоступен');
  await expect(page.getByRole('alert')).not.toContainText('internal preference storage exploded');
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();

  await expect(page.getByLabel('Язык интерфейса')).toHaveValue('en');
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeEnabled();
  await expectTouchTargets(page);
});

test('notification loading does not flash empty state and one notification cannot double-submit read', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  let readRequests = 0;
  await page.route('**/api/v1/notifications?limit=100', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, {
      unread_count: 1,
      items: [{
        id: 'notice_1',
        kind: 'generation',
        title: 'Готово',
        body: 'Генерация завершена',
        is_read: false,
        created_at: '2026-09-16T06:00:00Z',
      }],
    });
  });
  await page.route('**/api/v1/notifications/notice_1/read', async (route) => {
    readRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, { ok: true });
  });

  await page.goto('/mini-app/notifications/');
  await expect(page.getByText('Загружаем уведомления…')).toBeVisible();
  await expect(page.getByText('Уведомлений пока нет.')).toHaveCount(0);

  const notice = page.getByRole('button', { name: /Готово/ });
  await expect(notice).toBeVisible();
  await notice.click();
  await expect(notice).toBeDisabled();
  await notice.click({ force: true });
  await expect.poll(() => readRequests).toBe(1);
  await expectTouchTargets(page);
});

test('subscriptions distinguish loading from empty and media cards have an accessible name', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  await page.route('**/api/v1/social/subscriptions?limit=100', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, {
      items: [{
        id: 'author_1',
        display_name: 'Анна',
        username: 'anna',
        referral_code: 'anna',
        profile_discoverable: true,
        subscribed_by_me: true,
        subscribed_at: '2026-09-16T06:00:00Z',
      }],
    });
  });
  await page.route('**/api/v1/social/subscriptions/feed?limit=50&offset=0', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, {
      items: [{
        id: 'feed_1',
        preview_url: 'https://cdn.roxy.test/feed.jpg',
        result_url: null,
        result_urls: [],
        media: [],
        author: { display_name: 'Анна', telegram_id: 777 },
      }],
    });
  });
  await page.route('https://cdn.roxy.test/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlVfFsAAAAASUVORK5CYII=', 'base64'),
  }));

  await page.goto('/mini-app/subscriptions/');
  await expect(page.getByText('Загружаем подписки…')).toBeVisible();
  await expect(page.getByText('Здесь появятся публикации авторов, на которых вы подпишетесь.')).toHaveCount(0);

  await expect(page.getByRole('button', { name: /Открыть работу Анна/ })).toBeVisible();
  await expectTouchTargets(page);
});

test('support contact is server-owned and disappears when direct contact is not configured', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  let configured = true;

  await page.route('**/api/v1/support/contact', (route) => json(route, configured
    ? { configured: true, url: 'https://t.me/roxy_support', handle: '@roxy_support' }
    : { configured: false, url: null, handle: null }));
  await page.route('**/api/v1/support/tickets?limit=100', (route) => json(route, { items: [] }));

  await page.goto('/mini-app/support/');
  const contact = page.getByRole('button', { name: 'Написать @roxy_support' });
  await expect(contact).toBeVisible();
  await contact.click();
  await expect.poll(() => page.evaluate(() => window.__supportTelegramUrl)).toBe('https://t.me/roxy_support');

  configured = false;
  await page.reload();
  await expect(page.getByRole('button', { name: /Написать @/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Создать обращение' })).toBeVisible();
  await expectTouchTargets(page);
});
