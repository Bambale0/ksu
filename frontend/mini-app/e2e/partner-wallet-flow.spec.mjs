import { expect, test } from '@playwright/test';

async function installTelegram(page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'query_id=partner-e2e&hash=test',
        initDataUnsafe: { user: { id: 88001, first_name: 'Partner', username: 'partner_e2e' } },
        ready() {},
        expand() {},
        close() {},
        onEvent() {},
        offEvent() {},
        openLink() {},
        openTelegramLink() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
      },
    };
  });
}

async function mockPartnerApi(page, { failTransfer = false } = {}) {
  const calls = [];
  let available = 125;
  let withdrawalStatus = 'pending';

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    if (path === '/api/v1/referrals/stats') {
      return json({
        withdrawable_rub: available.toFixed(2),
        pending_referral_rub: '15.00',
        partner_total_earned_rub: '180.00',
        transferred_to_rox: (125 - available).toFixed(2),
        pending_withdrawals: withdrawalStatus === 'pending' ? '30.00' : '0.00',
        minimum_withdrawal_rub: '10.00',
        rub_per_rox: '1.00',
        rox_balance: '10000.00',
      });
    }
    if (path === '/api/v1/referrals/withdrawals' && method === 'GET') {
      return json({
        items: [{
          id: 'withdrawal-1',
          amount: '30.00',
          amount_rub: '30.00',
          status: withdrawalStatus,
          created_at: '2026-08-28T10:00:00Z',
          updated_at: '2026-08-28T10:00:00Z',
          can_cancel: withdrawalStatus === 'pending',
        }],
      });
    }
    if (path === '/api/v1/referrals/wallet-transfers' && method === 'GET') {
      return json({ items: [] });
    }
    if (path === '/api/v1/referrals/wallet-transfers' && method === 'POST') {
      const body = JSON.parse(request.postData() || '{}');
      calls.push({ kind: 'transfer', body });
      if (failTransfer) return json({ detail: 'Idempotency key was already used for another transfer amount' }, 409);
      available -= Number(body.amount || 0);
      return json({
        id: 'transfer-1',
        amount_rub: Number(body.amount).toFixed(2),
        rox_amount: Number(body.amount).toFixed(2),
        created_at: '2026-08-28T10:01:00Z',
      }, 201);
    }
    if (path === '/api/v1/referrals/withdrawals' && method === 'POST') {
      const body = JSON.parse(request.postData() || '{}');
      calls.push({ kind: 'withdrawal', body });
      return json({
        id: 'withdrawal-new',
        amount: Number(body.amount).toFixed(2),
        amount_rub: Number(body.amount).toFixed(2),
        status: 'pending',
        created_at: '2026-08-28T10:02:00Z',
        updated_at: '2026-08-28T10:02:00Z',
        can_cancel: true,
      }, 201);
    }
    if (path === '/api/v1/referrals/withdrawals/withdrawal-1/cancel' && method === 'POST') {
      calls.push({ kind: 'cancel' });
      withdrawalStatus = 'canceled';
      return json({
        id: 'withdrawal-1',
        amount: '30.00',
        amount_rub: '30.00',
        status: 'canceled',
        created_at: '2026-08-28T10:00:00Z',
        updated_at: '2026-08-28T10:03:00Z',
        can_cancel: false,
      });
    }
    return json({ detail: `Unexpected ${method} ${path}` }, 500);
  });

  return { calls };
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegram(page);
});

test('partner wallet renders real RUB accounting and states that ROX is not withdrawable', async ({ page }) => {
  await mockPartnerApi(page);
  await page.goto('/mini-app/partner-wallet/');

  await expect(page.getByText('Доход и выплаты')).toBeVisible();
  await expect(page.getByText('125 ₽')).toBeVisible();
  await expect(page.getByText('15 ₽')).toBeVisible();
  await expect(page.getByText('180 ₽')).toBeVisible();
  await expect(page.getByText(/ROX .* на карту не выводится/)).toBeVisible();
  await expect(page.getByText('Минимальная сумма: 10 ₽', { exact: false })).toBeVisible();
  await expect(page.getByText('10000 ROX')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});

test('partner converts earnings to ROX with an idempotency key and refreshed balance', async ({ page }) => {
  const audit = await mockPartnerApi(page);
  await page.goto('/mini-app/partner-wallet/');

  await page.getByLabel('Сумма, ₽').first().fill('25');
  await page.getByRole('button', { name: 'Перевести в ROX' }).click();

  await expect(page.getByText('25 ₽ переведено в 25 ROX')).toBeVisible();
  await expect(page.getByText('100 ₽')).toBeVisible();
  expect(audit.calls).toHaveLength(1);
  expect(audit.calls[0].kind).toBe('transfer');
  expect(audit.calls[0].body.amount).toBe(25);
  expect(typeof audit.calls[0].body.idempotency_key).toBe('string');
  expect(audit.calls[0].body.idempotency_key.length).toBeGreaterThanOrEqual(8);
});

test('partner can create and cancel a payout request', async ({ page }) => {
  const audit = await mockPartnerApi(page);
  await page.goto('/mini-app/partner-wallet/');

  const amountFields = page.getByLabel('Сумма, ₽');
  await amountFields.nth(1).fill('30');
  await page.getByLabel('Реквизиты').fill('СБП +79990000000');
  await page.getByRole('button', { name: 'Создать заявку' }).click();
  await expect(page.getByText('Заявка на выплату создана')).toBeVisible();

  await page.getByRole('button', { name: 'Отменить' }).click();
  await expect(page.getByText('Заявка отменена')).toBeVisible();
  expect(audit.calls.some((item) => item.kind === 'withdrawal')).toBe(true);
  expect(audit.calls.some((item) => item.kind === 'cancel')).toBe(true);
});

test('partner wallet surfaces a conflicting transfer retry instead of hiding it', async ({ page }) => {
  await mockPartnerApi(page, { failTransfer: true });
  await page.goto('/mini-app/partner-wallet/');

  await page.getByLabel('Сумма, ₽').first().fill('25');
  await page.getByRole('button', { name: 'Перевести в ROX' }).click();

  await expect(page.getByRole('alert')).toContainText('Idempotency key was already used');
});
