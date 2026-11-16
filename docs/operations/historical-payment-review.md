# KSU: review of historical payments with unknown creation result

Scope: `tanyapi`, epic [#616](https://github.com/Bambale0/ksu/issues/616) and [#609](https://github.com/Bambale0/ksu/issues/609). Use this guide for **read-only triage** only. No provider charges or live checkout tests.

## 1. Produce privacy-safe aggregates

From `/root/ksu` with the production image already deployed:

```bash
docker compose exec -T app python -m scripts.audit_historical_payments
```

The command starts a PostgreSQL `SET TRANSACTION READ ONLY` transaction. It emits counts grouped by provider, state, age, external-invoice presence, retry schedule and local `PaymentRequest` linkage. No user IDs, invoice IDs, request keys, email, payloads, or payment amounts are printed.

Do **not** pipe this output into a command that changes payment status, account balance, refund ledger, or creates new invoices.

## 2. Meaning of the Card cohorts

An unknown local create result is **not** proof of a failed payment. As of 2026-11-16:
- 64 `card/creation_unknown` records have no `external_id`.
- 54 have a matching local `PaymentRequest.status=unknown`, which can help trace the original intent *under authorized, controlled access*.
- 10 have no local `PaymentRequest`, so there is no persisted local request to use as evidence.
- 62 are older than 30 days; 2 are 7–30 days old.

This is a historical snapshot, not a current guaranteed count. The `card` provider does **not** offer an invoice-creation idempotency token in KSU's current create API. Re-sending create calls may issue a second payable invoice.

## 3. Rules for each evidence review

1. Determine the initial attempt time and provider from authorized application records; access personal/payment identifiers **only** within the permitted operator workflow, not in routine reports.
2. Seek an authoritative, signed provider webhook, immutable merchant/provider record, or supported invoice lookup. Correlate using verified fields; an approximate amount/time match alone is not proof.
3. Distinguish `provider paid`, `provider not paid/expired`, `incomplete evidence` and `refund/reversal pending`. A timeout or absent invoice lookup does not imply failure.
4. Confirm previous account credits and reversal entries before proposing any accounting action. Reuse the existing idempotent ledger and require an independent approval for a manual adjustment.
5. Maintain an access-controlled case record of evidence source, reviewer, time, verification result, and approval. Never place raw provider tokens, user data or card details in GitHub issues or CI logs.
6. Leave the local state unchanged if evidence is insufficient; mark it for manual follow-up in the operator system, **not** by inventing a terminal payment state.

## 4. Safety checks and exit criteria

- Never replay an invoice-creation request for a `creation_unknown` record just to see whether it works.
- Never call settlement/credit/refund APIs using only local `creation_unknown` as evidence.
- Never change `payments`, `payment_requests` or ROX ledgers through manual bulk SQL.
- If a provider lookup is not supported or the invoice cannot be reliably identified, keep the cohort open and document what evidence is missing.
- Validate new code with PR tests, mandatory GitHub Actions gates, and a production health/log check.
- Acceptance: each historic record is either backed by verified provider evidence or explicitly categorized as unresolved; no double credits or additional invoices.

See `app/services/payment_backlog.py` for the aggregate-only classifier and `app/services/card_payments.py` for the conservative provider reconciliation behavior.
