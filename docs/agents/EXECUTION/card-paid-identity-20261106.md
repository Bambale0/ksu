# Card settlement identity audit — 2026-11-06

## Confirmed defect and scope before implementation

PR #581 review comment 4490119236 identifies conditional invoice checks which allow
a successful authoritative lookup without amount or currency to grant locally
expected ROX. Source inspection also confirms that an absent invoice ID passes,
that a payment.success event can override a non-successful authoritative status,
and that the internal complete method can grant credit without validating its
provider payload.

The owned change is restricted to card settlement validation, focused regression
tests, two existing completion fixtures, and this execution record. No production
payments, balances, catalog prices, messages or credentials are changed. Existing
expected amounts are never rewritten or rounded.

## Required behavior

- Before wallet, bonus or referral mutation, require the same external invoice ID,
  an exact finite amount, matching currency, and a successful authoritative state.
- A verified success webhook is a reconciliation signal. Its body cannot supply
  missing authoritative money or override pending/failed/unknown lookup state.
- A successful sparse or malformed invoice enters the existing integrity
  quarantine; webhook delivery receives non-success.
- A sparse pending response remains pending without being terminalized merely for
  absent money fields. Pending invoice creation continues to use its existing
  provider contract.
- Preserve all currently supported top-level, amountTotal, receipt and nested
  amount representations. Every supplied money value remains checked for mismatch.
- Retain the existing payment row lock and canonical wallet idempotency key.
  Concurrent valid completion must produce one payment ledger transaction.

The current official portal was read on 2026-11-06:
https://developers.lava.top/en (authoritative GET /api/v1/invoices/{id} and payment
events), linked Swagger https://gate.lava.top/docs. The integration applies its
existing stricter rule: authoritative lookup evidence is required for settlement.

## Validation plan

Actual HTTP webhook tests use the real authentication, route, provider lookup and
payload unwrapping with a synthetic HTTP transport, then inspect isolated durable
payment/wallet state. Direct service tests cover invalid identity, supported
money shapes and concurrent idempotency. Reproduce RED before changing product
code, then run focused and existing card/payment compatibility suites in the
isolated PostgreSQL/Redis harness.

## RED evidence

The isolated 26-case regression run produced 19 failed / 7 passed in 6.41s
(job_9af96c22e787, test-run-20261106T074405Z-3789374.log). Failures
proved actual HTTP 200 and durable succeeded/credit for sparse paid invoices,
payment.success overriding pending/failed/unknown lookup state, and direct
complete accepting missing/mismatched/non-finite identity. Existing malformed
lookup rejection and valid concurrent completion controls passed.

## Adjacent state protection audit before implementation

Independent review found two concrete paths at the same settlement boundary:
`refund_review` is omitted from the complete/pending/failed preservation guards,
so a delayed PAID/PENDING/FAILED response can remove an existing manual review.
Also, non-success reconciliation uses the ORM snapshot loaded before awaiting the
provider and can overwrite a concurrently settled payment. The network lookup
must remain outside the payment lock; after it returns, classification must
refresh current persisted state under FOR UPDATE.

Add three real webhook replay cases starting from an actual paid invoice and
authoritative refund without a refund amount, plus two Event-barrier HTTP lookup
races with a concurrent successful transaction. No sleep-based synchronization,
new refund policy, wallet key or manual settlement mechanism is introduced.

The bounded state RED produced 5 failed / 26 deselected in 4.80s
(job_7463b742ea39, test-run-20261106T074851Z-3803358.log). PAID,
PENDING and FAILED each removed refund_review. A delayed FAILED lookup
overwrote concurrently committed succeeded; a delayed PENDING lookup replaced
the committed PAID provider evidence with PENDING. The canonical wallet credit
was already present, so this was a durable state/evidence regression rather than
a second credit.

## Deterministic lookup rejection boundary before implementation

Final independent review identified the remaining early return: an HTTP 400/404
lookup rejection calls the generic failure helper before the new row refresh.
That helper does not protect manual refund_review or refresh a stale caller.
Exercise two actual HTTP404 responses (existing manual review and a delayed
rejection while another transaction settles) before moving both successful
responses and deterministic errors through the same post-I/O lock. Keep the
generic helper unchanged so its existing caller payload semantics are preserved.
The preceding response-path checkpoint passed all 91 selected tests in 18.76s
(job_6fe54ec929a4, test-run-20261106T074939Z-3805120.log).

The actual-HTTP404 RED produced 2 failed / 31 deselected in 4.46s
(job_52752a64dade, test-run-20261106T075132Z-3808649.log): both a
concurrently committed succeeded payment and existing refund_review became
failed. The provider transport was blocked by Events while the independent
completion committed, proving the rejection branch used stale state.

The first final compatibility run passed 92 cases and found one old fake-session
error (job_893dd254c9ce): _PaymentSession did not implement scalar because the
old card rejection path returned before any locked query. Add only that async
fake method returning its existing Payment; keep all terminal status, commit and
reason assertions unchanged. The 33 new real-database cases already passed.

## Final verified result and freeze

Final isolated compatibility run: **93 passed in 18.88s**, exit 0
(job_e8b9916fb771, test-run-20261106T075335Z-3815611.log). This includes
33 new settlement/state regressions and 60 existing card integrity, catalog,
bonus, recovery, reconciliation, admin-provider and refund cases. Ruff and AST
passed all five Python files; scoped diff whitespace check passed.

The final card service now checks full paid identity immediately before any
wallet/bonus/referral mutation, uses only authoritative successful status for
settlement, and refreshes the current payment under its row lock after either a
successful lookup or a deterministic lookup rejection. Existing settled states
and manual refund_review survive delayed responses and lookup failures. Valid
nested money shapes, sparse pending/create responses, actual refund accounting
and the canonical payment credit idempotency key retain their existing contract.

Root and support_audit independently reviewed the final production diff, all 33
new cases and the three fixture corrections. No source blockers remained.
Production financial records and external provider state were not changed.
The earlier paid amount mismatch remains unresolved operationally; this fix does
not accept different prices or credit historical mismatches.

Frozen files in this slice:

- app/services/card_payments.py
- tests/test_card_paid_identity.py
- tests/test_card_invoice_integrity.py
- tests/test_card_payment_bonuses.py
- tests/test_payment_reconciliation.py
- docs/agents/EXECUTION/card-paid-identity-20261106.md

Exact published-head CI and automated review remain separate release gates.

## Exact-head CI fixture correction

On f3f75d928c0e264a60339a5012ad63f11efd3e64, CI run42184167229 /
job127780441955 stopped at one failure after 1767 passes (76.85s):
test_partner_promo_payment_is_first_line_only_and_refunds_are_proportional
called complete with only status=paid. The strict guard correctly rejected the
missing invoice ID. The earlier fixture search wrongly restricted test filenames
to card/payment/promo and missed referral coverage.

A repository-wide caller inventory without that filename filter found two
success/replay calls in the same referral fixture requiring the real invoice ID,
amount and currency. Update only their synthetic authoritative payload; preserve
all first-line commission, partner bonus, refund and replay assertions. Product
code is frozen and unchanged. Validate the affected end-to-end referral file
together with paid-identity, card-bonus and invoice-integrity compatibility.

### Full caller inventory and fixture verification

The unfiltered Python caller scan (including imported aliases and module-qualified
calls) found these nine card completion call sites:

| File / entry | Calls | Contract |
| --- | ---: | --- |
| app/services/card_payments.py / reconcile | 1 | Authoritative invoice from provider lookup |
| tests/test_referral_partner_end_to_end.py | 2 | Success and exact replay now use created invoice identity |
| tests/test_card_invoice_integrity.py | 1 | Concurrent valid webhook settlement fixture |
| tests/test_card_paid_identity.py | 4 | Intentional invalid evidence, valid concurrent and delayed-race controls |
| tests/test_card_payment_bonuses.py | 1 | Valid paid invoice for exact bonus/referral accounting |

The affected four-file compatibility run passed **70 tests in 14.84s**, exit 0
(job_182bc311ea74, test-run-20261106T080159Z-3826617.log). Ruff passed;
all existing assertions in the referral/refund test file are AST-identical to
their pre-change form, and the scoped diff whitespace check passed. Root read
the full referral flow and independently approved the fixture adaptation.

The production card service blob remains unchanged:
c7cf0479ec92609b3746bc06f6486d59b0976751.
Only tests/test_referral_partner_end_to_end.py and this execution document change
in this CI follow-up. Both are frozen; the next published head must rerun the
six required CI workflows.
