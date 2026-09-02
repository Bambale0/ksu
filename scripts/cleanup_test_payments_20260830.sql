-- One-time cleanup of known test payment records created on 2026-08-30.
-- IMPORTANT: review the preview rows below and keep the referenced PostgreSQL
-- backup available before executing this script in production.
-- Backup: /root/ksu/backups/pre-test-payment-cleanup-20260830.dump
--
-- Safety contract:
-- * never select rows merely because their provider is cryptopay/tbank;
-- * scope every match to the 2026-08-30 UTC test window;
-- * require an explicit test user or an explicit synthetic test marker;
-- * abort before DELETE if the candidate set is unexpectedly large.

BEGIN;

CREATE TEMP TABLE test_payments ON COMMIT DROP AS
SELECT id, user_id
FROM payments
WHERE created_at >= TIMESTAMPTZ '2026-08-30 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-08-31 00:00:00+00'
  AND (
       user_id = '90120784-86d7-4771-91c9-3ee54eabdf24'
       OR coalesce(payload->>'billing_email','') LIKE 'smoke+%@%'
       OR coalesce(external_id,'') LIKE 'card-bonus%'
       OR coalesce(external_id,'') LIKE 'card-fixed%'
       OR coalesce(payload->>'payment_url','') LIKE '%pay.example%'
  );

DO $$
DECLARE
  candidate_count integer;
BEGIN
  SELECT count(*) INTO candidate_count FROM test_payments;
  IF candidate_count > 100 THEN
    RAISE EXCEPTION 'Refusing test-payment cleanup: % candidate payments exceeds safety limit 100', candidate_count;
  END IF;
END $$;

-- Human-readable preview retained in execution logs before any destructive step.
SELECT p.id, p.provider, p.status, p.amount, p.rox_amount, p.user_id, p.created_at
FROM payments p
JOIN test_payments t ON t.id = p.id
ORDER BY p.created_at, p.id;

CREATE TEMP TABLE affected_users ON COMMIT DROP AS
SELECT DISTINCT user_id FROM test_payments
UNION
SELECT DISTINCT wt.user_id
FROM wallet_transactions wt
JOIN test_payments t
  ON wt.reference_type = 'payment'
 AND wt.reference_id = t.id::text;

DELETE FROM wallet_transactions wt
USING test_payments t
WHERE wt.reference_type = 'payment'
  AND wt.reference_id = t.id::text;

-- Seed transactions are removed only for the explicit test account and only in
-- the same test-day window. Never delete seed-looking kinds globally.
DELETE FROM wallet_transactions
WHERE user_id = '90120784-86d7-4771-91c9-3ee54eabdf24'
  AND created_at >= TIMESTAMPTZ '2026-08-30 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-08-31 00:00:00+00'
  AND kind IN ('test_seed','integration_seed');

DELETE FROM payments p
USING test_payments t
WHERE p.id = t.id;

UPDATE wallets w
SET balance = coalesce((
  SELECT wt.balance_after
  FROM wallet_transactions wt
  WHERE wt.user_id = w.user_id
  ORDER BY wt.created_at DESC, wt.id DESC
  LIMIT 1
), 0)
WHERE w.user_id IN (SELECT user_id FROM affected_users);

SELECT (SELECT count(*) FROM test_payments) AS deleted_test_payments,
       (SELECT count(*) FROM payments) AS payments_left,
       (SELECT count(*) FROM payments WHERE status='succeeded') AS succeeded_left;

COMMIT;
