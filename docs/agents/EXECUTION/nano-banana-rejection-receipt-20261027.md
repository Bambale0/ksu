# Nano Banana verified pre-acceptance fallback — 2026-10-27

## Audit baseline and incident evidence

- Baseline: `main` / production `e9037324a096ea3992cd5f63e8044811a4a5bf5a`.
- Read-only production review at 2026-10-27 12:00 UTC found 39 Nano Banana jobs in the prior 24 hours: 28 succeeded and 11 failed. Five zero-cost Nexus failures were provider safety rejections. Six paid Neironych failures were refunded once (150 ROX total): two definite 422 rejections and four submissions whose acceptance could not be proven, including one structured HTTP 503 `provider_temporarily_unavailable`.
- No Nano Banana generation or outbox row was non-terminal. Application health, worker heartbeats and the deployed immutable image were healthy. The confirmed defect is therefore the cross-service response contract, not a crashed KSU worker.
- KSU currently treats every Neironych image HTTP 503 as ambiguous because a paid POST may have been accepted before the response was lost. It cannot safely advance to Nexus without proof of non-acceptance.
- Provider PR `Bambale0/ooo#125` defines an opt-in `X-Submission-Receipt: v1` contract. Only after rollback and a durable, unbilled idempotency fence does it return `X-Submission-State: not-accepted-v1`, the exact client request ID and the SHA-256 of the idempotency key. Bare/malformed/mismatched 503 responses remain ambiguous. The provider PR is open and is a gateway-first release dependency; its existence is not production availability evidence.

## Existing / partial / missing / reuse

- Existing: immutable request-body/idempotency snapshots, typed Neironych errors, fail-closed unknown-submission handling, atomic route fallback, one debit/refund, provider attempt history and durable generation outbox.
- Partial: KSU already sends an idempotency key but does not opt into or verify the rejection receipt.
- Missing: strict receipt validation bound to this exact invocation, plus a public provider/service regression proving a verified rejection advances once while every unverified outcome remains on Neironych.
- Reuse: `NeironychImageClient`, `NeironychProviderError`, `error_disposition`, `switch_to_fallback` and existing generation/outbox tests. No schema, price, catalog, permission or route-policy change.

## Acceptance and safety boundary

1. Nano Banana image requests send a stable client request ID and explicitly request receipt version 1.
2. A response authorizes fallback only when status, exact JSON body, receipt version, client request ID and idempotency-key digest all match.
3. A verified non-acceptance becomes the existing `fallback` disposition and advances atomically to the already configured next provider without a refund/recharge.
4. Bare 503, wrong/missing headers, mismatched identities, malformed bodies, timeouts, 422/provider rejection and safety/policy errors retain their current fail-closed behavior.
5. No request prompt, reference URL, credential or receipt identity is logged. No production data or paid provider call is used for verification.
6. Gateway must deploy first. Until the receipt contract is live, the KSU client remains backward-compatible and fail-closed.

## Verification matrix

| Area | Plan |
|---|---|
| Unit/domain | Receipt verifier positive case and every mismatched/malformed negative case. |
| Database/repository | Real Generation/Wallet/Outbox path: verified rejection advances to Nexus, keeps one debit, no refund and one provider attempt. |
| Authorization | N/A: no user/admin endpoint or ownership change. Existing generation ownership remains authoritative. |
| Migrations | N/A: no schema change. |
| Provider contract | HTTP MockTransport asserts request headers and exact receipt semantics against `ooo#125`. |
| Idempotency/reconciliation | Receipt is bound to the saved idempotency key; unverified outcomes remain uncertain; accepted/external IDs never switch. |
| API integration | Existing generation API is unchanged; focused provider/service tests plus normal CI. |
| Frontend/Mini App/bot | No UI payload change; exact-head product CI remains required. |
| Smoke/deployability | Ruff, compile, focused PostgreSQL tests, full exact-head CI. Gateway-first then KSU exact-SHA deploy if separately authorized. |
| Observability/audit | Existing sanitized provider response and fallback history; no new sensitive fields. |
| No-hardcode/admin | Receipt version/header names are protocol constants; provider route remains revisioned admin configuration. |
| Performance | Constant-time header/body checks; no query or external-call increase. |
| Rollback | Revert client opt-in; older gateway responses already remain ambiguous. Do not replay historical unknown jobs. |

## Plan and progress

1. Record this audit before production-code changes.
2. RED: add a real HTTP/provider-to-generation regression for the verified receipt and negative identity cases.
3. GREEN: add the smallest strict verifier and wire it into Neironych image errors.
4. Run focused tests, then lint/compile/diff and broader provider/reliability tests.
5. Review against this contract and repository standards; open a focused PR only after verification. No merge, deployment or runtime-route mutation without separate authorization.

Guidance: repository `AGENTS.md`; local `.clinerules` systematic-debugging, TDD and verification-before-completion (local `.agents` is absent); remote `Bambale0/skills` diagnosing-bugs/TDD/code-review; `Bambale0/claw` backend integration; `Bambale0/dev-agents-pack` debugger; `wondelai/skills` Release It; `agentskills/agentskills` and `anthropics/skills` catalogs had no additional provider-receipt workflow. No skill scripts executed.

## Release continuation 2026-10-27
User now explicitly authorizes gateway-first merge/deploy and cloud execution.
Reproduced both reported review findings. Receipt identities now compare bytes;
non-ASCII identities and malformed JSON remain uncertain without fallback.
HTTP 422 rejects before receipt disposition. The real HTTP-to-PostgreSQL regression
now follows the configured Nexus step, re-enters both submission services and proves
one Neironych POST, one Nexus submission, one original generation debit, no refund
and no repeated charge. 47 recovery/protocol tests passed on isolated PostgreSQL 17.
No production DB, route, price, permission or paid provider call was changed.

Refreshed guidance: .agents AGENTS/README/index and pytest-skill,
Bambale0/skills diagnosing-bugs + TDD, claw backend-integration,
dev-agents-pack debugger, wondelai Release It, anthropics webapp-testing.
agentskills/agentskills supplied skill format/discovery only, no applicable receipt workflow.
Gateway #125 required three further review corrections and remains the release dependency.


## Gateway production evidence — 2026-10-27 14:37 UTC
- ooo#125 merged as e445aeac7ff9573d41ae93a7dbfc3549d52774f4.
- Main CI 40520580548 succeeded. Deploy workflow 40521230818 attempt 2 succeeded
  after a verified 193164176-byte PostgreSQL backup and concurrent index migration
  20261027_0037. All four gateway services run image
  sha256:db9de7c986caeb7157ea363ed050cb97cb8f5806eb76f8468375e7ef88300202
  with that revision; public readiness has DB/Redis ok.
- Positive receipt response was verified inside the deployed image using an
  in-memory Generation: exact 503/body/state/client-ID/key digest, no DB/provider.
- KSU partner authenticated GET /v1/balance returned 200. A proven malformed JSON
  array returned live 422 without a rejection receipt, before admission.

### Verification incident (explicit deviation from the no-paid-request requirement)
An initially chosen n=2 image smoke body was mistakenly assumed invalid.
The local precheck failed, but orchestration incorrectly continued and sent one
POST. Gateway generation 5da3feff-68a1-4dae-a5e8-053c2cb76455 reached upstream.
It ended failed/not_chargeable/provider_response_invalid; its partner ledger has
zero operations and KSU was not debited. Upstream procurement outcome/cost remains
unconfirmed and its hold remains for reconciliation. No retry, manual refund,
balance or routing change was performed. This was an operator verification error,
not evidence of a safe non-charging provider call. Subsequent smoke uses only
in-memory mocks or a JSON array proven to reject before reserve.


CI infrastructure correction: canceled run 40519857281 logs show Azure HTTP
Ubuntu downloads consuming ~20 minutes before any E2E test. The ROXY E2E runner
now uses the canonical HTTPS Ubuntu archive for those mirror entries and a
five-minute tooling-step budget plus bounded APT retries/timeouts. Package signature
verification and all product/browser tests remain unchanged; production OS untouched.
