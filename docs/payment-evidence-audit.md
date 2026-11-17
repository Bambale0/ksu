# KSU historical payment provider-evidence audit (#609)

This runbook concerns **observations, not settlement**. It must not update
\`payments\`, \`wallet_transactions\`, promotions, invoice requests or refunds.
A payment older than 90 days is **not** automatically failed.

## Safety controls

- Run only a known released Docker SHA with an authorized operator.
- The first invocation **does not call any provider**. It reads KSU PostgreSQL
  in a \`SET TRANSACTION READ ONLY\` transaction and prints aggregate metadata.
- \`--probe\` explicitly requests **1–5 status inquiries** for one provider,
  one at a time, oldest-first. Only unresolved payments with an existing
  \`external_id\` are eligible; the 64 Card \`creation_unknown\` with missing IDs
  are never probed or associated by buyer email, amount, or currency.
- Card/Crypto Pay use provider GET invoice queries. T-Bank \`/v2/GetState\`
  and 2328 \`/v1/payment/info\` are *non-mutating status inquiries* despite
  being transported over HTTP POST. No create, refund, cancel, payout, wallet
  credit, or reconciliation mutation is invoked.
- Every response is matched against its provider invoice ID **and** local
  order/payload ownership plus exact amount/currency before classifying the
  observed status. Unknown or incomplete evidence stays unverified.
- The report exposes **only aggregate counts**. Do not paste raw provider
  payloads, tokens, emails, invoice IDs, wallet IDs or payment URLs into issues.
- Rate limiting: at most five lookups per invocation, no concurrency or
  automatic retries. Stop on provider rate limiting, repeated transport errors,
  or when credentials are missing.

## Commands

No network queries (safest first):

\`\`\`bash
docker exec ksu-app-1 python -m scripts.audit_provider_payment_evidence --provider tbank --limit 3
\`\`\`

Bounded read-only status inquiry, only if approved:

\`\`\`bash
docker exec ksu-app-1 python -m scripts.audit_provider_payment_evidence --provider tbank --limit 3 --probe
\`\`\`

Use \`--provider card|cryptobot|tbank|2328\` and optionally \`--older-than-days 7\`.
The 90+ day oldest category can be inspected with \`--older-than-days 90\`
**only when records exist**. The CLI intentionally makes no JSON output
that identifies a specific invoice or authorizes an action.

## Interpretation

- \`verified_provider_paid\`: provider reports a paid state and invoice,
  ownership, exact currency and amount match. This is **only evidence** for
  a separate, auditable provider/ledger reconciliation — never permission
  to credit ROX from this script.
- \`verified_provider_terminal\`: provider reports a terminal state. No
  \`failed\` or refund transition follows automatically.
- \`provider_refund_evidence\`: a refund/reversal signal may need partial
  refund and existing ledger comparison; no reversal occurs here.
- \`verified_provider_pending\`: still requires follow-up; absence of paid
  status is not proof of failure.
- \`provider_not_found_unproven\`, \`identity_unverified\`,
  \`provider_status_unrecognized\`, \`provider_lookup_unavailable\`: do not
  infer any settlement decision. Retry sparingly or escalate for manual
  evidence review.

Operator recovery must independently verify signed webhook/provider API
evidence, match amount/currency/owner and *existing credit ledger*, record
who reviewed and the evidence code, obtain a second approver for manual
credit/refund, and use only the established idempotent transaction path.
Those operator mutation capabilities are **not** implemented by this audit.
