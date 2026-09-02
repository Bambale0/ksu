-- Удаление тестовых платежных записей (2026-08-30)
-- Бэкап: /root/ksu/backups/pre-test-payment-cleanup-20260830.dump
BEGIN;

CREATE TEMP TABLE test_payments ON COMMIT DROP AS
SELECT id FROM payments
WHERE user_id = '90120784-86d7-4771-91c9-3ee54eabdf24'  -- telegram 339795159
   OR provider IN ('cryptopay','tbank')                  -- интеграционные/seed-записи
   OR coalesce(payload->>'billing_email','') LIKE 'smoke+%'
   OR coalesce(payload->>'billing_email','') = 'buyer@example.com'
   OR coalesce(external_id,'') LIKE 'card-bonus%'
   OR coalesce(external_id,'') LIKE 'card-fixed%'
   OR coalesce(payload->>'payment_url','') LIKE '%pay.example%';

CREATE TEMP TABLE affected_users ON COMMIT DROP AS
SELECT DISTINCT user_id FROM (
  SELECT wt.user_id FROM wallet_transactions wt
    JOIN test_payments t ON wt.reference_type='payment' AND wt.reference_id=t.id::text
  UNION
  SELECT user_id FROM wallet_transactions WHERE kind IN ('test_seed','integration_seed')
  UNION
  SELECT p.user_id FROM test_payments t JOIN payments p ON p.id=t.id
) s;

DELETE FROM wallet_transactions wt
  USING test_payments t
  WHERE wt.reference_type='payment' AND wt.reference_id=t.id::text;

DELETE FROM wallet_transactions WHERE kind IN ('test_seed','integration_seed');

DELETE FROM payments p USING test_payments t WHERE p.id=t.id;

UPDATE wallets w SET balance = coalesce((
  SELECT wt.balance_after FROM wallet_transactions wt WHERE wt.user_id=w.user_id
  ORDER BY wt.created_at DESC, wt.id DESC LIMIT 1), 0)
WHERE w.user_id IN (SELECT user_id FROM affected_users);

SELECT (SELECT count(*) FROM payments) AS payments_left,
       (SELECT count(*) FROM payments WHERE status='succeeded') AS succeeded_left,
       (SELECT count(*) FROM wallet_transactions WHERE kind IN ('test_seed','integration_seed')) AS seed_txs_left;

SELECT p.provider, p.status, p.amount, p.rox_amount, u.telegram_id, p.created_at
FROM payments p JOIN users u ON u.id=p.user_id WHERE p.status='succeeded';

COMMIT;
