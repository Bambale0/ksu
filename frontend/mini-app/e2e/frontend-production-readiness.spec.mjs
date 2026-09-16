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


test('promo bootstrap failure is an error with retry, never a fake inactive promo', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  let attempts = 0;
  await page.route('**/api/v1/promocodes/active', (route) => {
    attempts += 1;
    if (attempts === 1) return json(route, { detail: 'database stack trace should stay private' }, 503);
    return json(route, { active: false, program_active: true });
  });

  await page.goto('/mini-app/promocodes/');
  await expect(page.getByRole('alert')).toContainText('Сервис временно недоступен');
  await expect(page.getByLabel('Промокод')).toHaveCount(0);
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(page.getByLabel('Промокод')).toBeVisible();
});

test('creator application is unavailable until authoritative partnership status loads', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  await page.route('**/api/v1/creator-partnership', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, { application: null, agreement: null, grants: [], total_granted_rox: '0' });
  });

  await page.goto('/mini-app/creator-partnership/');
  await expect(page.getByText('Загружаем статус партнёрства…')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Отправить заявку' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Отправить заявку' })).toBeVisible();
});

test('partner withdrawal honors the server minimum before allowing submit', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  await page.route('**/api/v1/referrals/stats', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    return json(route, {
      withdrawable_rub: '1500',
      pending_referral_rub: '0',
      partner_total_earned_rub: '1500',
      transferred_to_rox: '0',
      pending_withdrawals: '0',
      minimum_withdrawal_rub: '500',
      rub_per_rox: '1',
    });
  });
  await page.route('**/api/v1/referrals/withdrawals?limit=50', (route) => json(route, { items: [] }));
  await page.route('**/api/v1/referrals/wallet-transfers?limit=50', (route) => json(route, { items: [] }));

  await page.goto('/mini-app/partner-wallet/');
  await expect(page.getByText('Загружаем партнёрский баланс…')).toBeVisible();

  const amount = page.getByLabel('Сумма, ₽').nth(1);
  const requisites = page.getByLabel('Реквизиты');
  const submit = page.getByRole('button', { name: 'Создать заявку' });
  await amount.fill('100');
  await requisites.fill('СБП');
  await expect(submit).toBeDisabled();
  await amount.fill('500');
  await expect(submit).toBeEnabled();
});

test('payments show bootstrap progress instead of a false unavailable state', async ({ page }) => {
  await installTelegram(page);
  await mockMe(page);
  const packages = {
    provider: 'yookassa',
    label: 'ЮKassa',
    configured: true,
    currencies: ['RUB'],
    packages: {
      starter: { credits: '300', bonus_credits: '30', total_credits: '330', prices: { RUB: '300' } },
    },
  };
  await page.route('**/api/v1/payments/yookassa/packages', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    return json(route, packages);
  });
  await page.route('**/api/v1/payments/card/packages', (route) => json(route, { ...packages, provider: 'card', label: 'Lava Top', configured: false, packages: {} }));
  await page.route('**/api/v1/payments/crypto/packages', (route) => json(route, { ...packages, provider: 'cryptobot', label: 'CryptoBot', configured: false, packages: {} }));
  await page.route('**/api/v1/payments?limit=50', (route) => json(route, { items: [] }));
  await page.route('**/api/v1/promocodes/active', (route) => json(route, { active: false, program_active: true }));

  await page.goto('/mini-app/payments/');
  await expect(page.getByText('Загружаем способы оплаты и историю…')).toBeVisible();
  await expect(page.getByText('Пополнение сейчас недоступно.')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'ЮKassa', exact: true })).toBeVisible();
});
